# ============================================================
# backend/services/gsc_service.py
# KrashiMitra — Google Search Console staleness sweep
# ------------------------------------------------------------
# IndexNow (backend/utils/indexnow.py) already tells Bing/Yandex/etc. within
# hours whenever the mandi feed changes — but its own docstring says it
# straight: "Google does NOT participate". For Google, the only levers are
# sitemap <lastmod>, on-page dateModified (see bhav.py's `_fresh_iso` /
# `_doc(updated=...)`), and Search Console itself. This module is the third
# one: it asks Google, via the URL Inspection API, when it last actually
# crawled a sample of /bhav pages, and records how far behind Google's copy
# is. It only MEASURES. The bug it was built for — a Google snippet dated
# "13 Jul" still showing on 2 Aug — is fixed by Google crawling more often,
# and Google crawls more often when pages answer fast, not when asked.
#
# Auth: service-account OAuth2 JWT-bearer flow (RFC 7523), read from
# GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 (base64 of the downloaded key JSON).
# No google-auth / google-api-python-client dependency — this codebase
# already prefers plain HTTP (see requirements.txt's Gemini/Ollama note),
# and python-jose (already a dependency) signs the RS256 assertion just
# fine, so `requests` alone gets us the rest of the way.
#
# The service account must be added as a user on the krashimitra.in Search
# Console property — see docs/MEMORY note bhav-page-freshness-signals for
# the full setup story.
#
# Quota (Google's stated default): URL Inspection ~2,000/day, 600/min per
# site. BATCH_SIZE stays well under it.
#
# NO INDEXING API. Until 28 Sep 2026 this sweep also sent stale /bhav pages
# to the Indexing API. Google limits that API to JobPosting and
# BroadcastEvent pages and says every submission goes through spam
# detection. It also did nothing: on 27 Sep the site's top /bhav pages had
# last been crawled 5-10 days earlier despite a month of submissions. Do not
# add it back.
# ============================================================

import base64
import json
import logging
import os
import random
import time
from datetime import date, datetime

import requests
from jose import jwt as _jose_jwt

logger = logging.getLogger("krishi.gsc")

# Must match the EXACT property registered in Search Console — a URL-prefix
# property usually keeps the trailing slash; a domain property instead uses
# "sc-domain:krashimitra.in". Override via env if inspect_url starts 403ing.
SITE_URL = os.getenv("GSC_SITE_URL", "https://krashimitra.in/")

TOKEN_URL    = "https://oauth2.googleapis.com/token"
INSPECT_URL  = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
ANALYTICS_URL = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
                 "{site}/searchAnalytics/query")

SCOPE_WEBMASTERS = "https://www.googleapis.com/auth/webmasters"

# A page whose Google copy is this many days older than its real data is
# counted as stale in the sweep's report.
STALE_AFTER_DAYS = 5
BATCH_SIZE = 150

_sa_cache: dict | None = None
_SA_UNSET = object()
_token_cache: dict[str, tuple[float, str]] = {}   # scope -> (expiry_epoch, token)


def _service_account() -> dict | None:
    global _sa_cache
    if _sa_cache is not None:
        return None if _sa_cache is _SA_UNSET else _sa_cache
    blob = os.getenv("GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64", "").strip()
    if not blob:
        _sa_cache = _SA_UNSET
        return None
    try:
        _sa_cache = json.loads(base64.b64decode(blob))
        return _sa_cache
    except Exception as e:
        logger.error(f"GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 is set but unreadable: {e}")
        _sa_cache = _SA_UNSET
        return None


def configured() -> bool:
    return _service_account() is not None


def _access_token(scope: str) -> str | None:
    """Service-account JWT-bearer OAuth2 flow — no google-auth needed."""
    cached = _token_cache.get(scope)
    if cached and cached[0] - 60 > time.time():
        return cached[1]

    sa = _service_account()
    if not sa:
        return None

    now = int(time.time())
    claims = {"iss": sa["client_email"], "scope": scope, "aud": TOKEN_URL,
              "iat": now, "exp": now + 3600}
    try:
        assertion = _jose_jwt.encode(claims, sa["private_key"], algorithm="RS256")
        res = requests.post(TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }, timeout=15)
        res.raise_for_status()
        body = res.json()
        _token_cache[scope] = (now + int(body.get("expires_in", 3600)), body["access_token"])
        return body["access_token"]
    except Exception as e:
        logger.error(f"GSC token exchange failed (scope={scope}): {e}")
        return None


def inspect_url(url: str) -> dict | None:
    """One URL Inspection API call → indexStatusResult, or None on any
    failure. Callers must treat None as 'unknown', never as 'stale'."""
    token = _access_token(SCOPE_WEBMASTERS)
    if not token:
        return None
    try:
        res = requests.post(
            INSPECT_URL, headers={"Authorization": f"Bearer {token}"},
            json={"inspectionUrl": url, "siteUrl": SITE_URL}, timeout=20)
        if res.status_code != 200:
            logger.warning(f"URL Inspection {res.status_code} for {url}: {res.text[:200]}")
            return None
        return res.json().get("inspectionResult", {}).get("indexStatusResult")
    except requests.RequestException as e:
        logger.warning(f"URL Inspection failed for {url}: {e}")
        return None


def search_analytics(start: str, end: str, dimensions: list[str] | None = None,
                     row_limit: int = 25000, filters: list[dict] | None = None,
                     search_type: str = "web", data_state: str = "final") -> list[dict]:
    """Search Analytics API → the performance numbers (clicks, impressions,
    ctr, position) behind the GSC Performance report.

    This is deliberately read-only and on-demand: nothing in the scheduled
    sweep calls it. `inspect_url` above answers "has Google seen the fresh
    page?"; this answers "did anyone click it?" — the two halves of the same
    question, and the reason the recrawl work exists at all.

    Rows come back as {keys: [...dimension values in order...], clicks,
    impressions, ctr, position}; `keys` is flattened into `dimensions` here so
    callers never have to remember the ordering. Google caps a response at
    25,000 rows, so anything larger pages through startRow.

    data_state="final" excludes the most recent ~2 days, which Google is still
    counting — use "all" only when a same-day directional read matters more
    than the number being right.
    """
    token = _access_token(SCOPE_WEBMASTERS)
    if not token:
        return []

    dims = dimensions or ["query"]
    url = ANALYTICS_URL.format(site=requests.utils.quote(SITE_URL, safe=""))
    out: list[dict] = []
    start_row = 0

    while True:
        body = {"startDate": start, "endDate": end, "dimensions": dims,
                "rowLimit": min(row_limit, 25000), "startRow": start_row,
                "type": search_type, "dataState": data_state}
        if filters:
            body["dimensionFilterGroups"] = [{"filters": filters}]
        try:
            res = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                                json=body, timeout=60)
        except requests.RequestException as e:
            logger.warning(f"Search Analytics call failed: {e}")
            break
        if res.status_code != 200:
            logger.warning(f"Search Analytics {res.status_code}: {res.text[:300]}")
            break

        rows = res.json().get("rows", [])
        for r in rows:
            out.append({**{d: k for d, k in zip(dims, r.get("keys", []))},
                        "clicks": r.get("clicks", 0),
                        "impressions": r.get("impressions", 0),
                        "ctr": r.get("ctr", 0.0),
                        "position": r.get("position", 0.0)})
        # A short page is the last page; Google does not send a next-page token.
        if len(rows) < min(row_limit, 25000) or len(out) >= row_limit:
            break
        start_row += len(rows)

    return out


def _bhav_targets() -> list[tuple[str, str]]:
    """(url, expected_fresh_iso) for every /bhav district page that has a
    real reported date — same idx["dates"] value the sitemap's <lastmod>
    and the page's own dateModified already use (bhav.py's _fresh_iso), so
    'stale' here means the same thing everywhere else in the codebase."""
    from backend.routes.bhav import _get_index, _is_crop, SITE
    idx = _get_index()
    out = []
    for cs, cn in idx.get("crops", {}).items():
        if not _is_crop(cn):
            continue
        for ss in idx["states"].get(cs, {}):
            for ds in idx["dists"].get(cs, {}).get(ss, {}):
                fresh = idx.get("dates", {}).get(cs, {}).get(ss, {}).get(ds, "")
                if fresh:
                    out.append((f"{SITE}/bhav/{cs}/{ss}/{ds}", fresh))
    return out


def run_stale_check(batch_size: int = BATCH_SIZE) -> dict:
    """Sample `batch_size` /bhav URLs and measure how old Google's copy of
    each one is. Two numbers come out of it:

    - crawl age: days since Google last fetched the page. This is the one
      that moves when pages get faster, so it is the headline.
    - stale: pages whose Google copy is STALE_AFTER_DAYS or more older than
      the page's real data date.

    Logged to sync_log (source='gsc_recrawl') so health_service can report
    on it without ever calling Google itself, same as the mandi feed check.
    Read-only: nothing here asks Google to do anything (see the header on
    why the Indexing API is gone)."""
    from backend.services.sync_log_service import record_sync

    started = datetime.utcnow()
    if not configured():
        record_sync("gsc_recrawl", "skipped", detail="GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 not set")
        return {"skipped": True}

    targets = _bhav_targets()
    sample = random.sample(targets, min(batch_size, len(targets)))
    today = date.today()

    checked = stale = errors = 0
    ages: list[int] = []
    for url, expected in sample:
        status = inspect_url(url)
        if status is None:
            errors += 1
            continue
        checked += 1
        last_crawl = (status.get("lastCrawlTime") or "")[:10]  # YYYY-MM-DD
        try:
            crawled = date.fromisoformat(last_crawl)
        except ValueError:
            continue                    # never crawled: no age to report
        ages.append((today - crawled).days)
        try:
            if (date.fromisoformat(expected) - crawled).days >= STALE_AFTER_DAYS:
                stale += 1
        except ValueError:
            pass

    ages.sort()
    median = ages[len(ages) // 2] if ages else None
    within2 = sum(1 for a in ages if a <= 2)
    detail = (f"{checked} जांचे · Google की कॉपी: आधी {median} दिन से पुरानी, "
              f"{within2} पेज 2 दिन के अंदर crawl · {stale} बासी (>{STALE_AFTER_DAYS} दिन)"
              if ages else f"{checked} जांचे · crawl तारीख़ नहीं मिली")
    detail += f" · {errors} त्रुटि"
    # "failed" only when NOTHING was inspected successfully (auth broken, API
    # down) — same rule sync_log_service.mandi_freshness uses for its own
    # feed: a run that delivered *some* rows is success/partial, never failed.
    run_status = "failed" if checked == 0 else ("success" if errors == 0 else "partial")
    record_sync("gsc_recrawl", run_status,
                rows=checked, detail=detail, started_at=started)
    logger.info(f"GSC crawl-age check: {detail}")
    return {"checked": checked, "stale": stale, "errors": errors,
            "median_crawl_age_days": median, "crawled_within_2_days": within2}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_stale_check(batch_size=20), indent=2, ensure_ascii=False))

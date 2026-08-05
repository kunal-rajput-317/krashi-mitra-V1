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
# crawled a sample of /bhav pages, and requests a recrawl (Indexing API) for
# whichever have drifted well behind the real data date. That's what closes
# the loop on the bug this was built for — a Google snippet dated "13 Jul"
# still showing on 2 Aug for a page whose live data was already correct.
#
# Auth: service-account OAuth2 JWT-bearer flow (RFC 7523), read from
# GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 (base64 of the downloaded key JSON).
# No google-auth / google-api-python-client dependency — this codebase
# already prefers plain HTTP (see requirements.txt's Gemini/Ollama note),
# and python-jose (already a dependency) signs the RS256 assertion just
# fine, so `requests` alone gets us the rest of the way.
#
# The service account must be added as a user on the krashimitra.in Search
# Console property (Owner, so the Indexing API scope also works) — see
# docs/MEMORY note bhav-page-freshness-signals for the full setup story.
#
# Quotas (Google's stated defaults): URL Inspection ~2,000/day, 600/min per
# site; Indexing API ~200 publish calls/day per project. BATCH_SIZE stays
# well under the first; only pages actually found stale ever consume the
# second, which self-limits it in practice.
#
# The Indexing API is documented by Google as being for JobPosting/
# BroadcastEvent pages specifically. It is still called here for ordinary
# /bhav pages because in practice Google generally still processes the
# request — but this is NOT a documented guarantee, so every call here is
# best-effort, logged, and never allowed to look like a different failure.
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
INDEXING_URL = "https://indexing.googleapis.com/v3/urlNotifications:publish"
ANALYTICS_URL = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
                 "{site}/searchAnalytics/query")

SCOPE_WEBMASTERS = "https://www.googleapis.com/auth/webmasters"
SCOPE_INDEXING   = "https://www.googleapis.com/auth/indexing"

# A few days of recrawl lag is normal (see MANDI_WARN-style thresholds in
# health_service.py); only ask Google to look again once the gap is wide
# enough that it's clearly not just "hasn't gotten to it yet today".
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


def request_indexing(url: str) -> int:
    """Best-effort Indexing API ping. Returns the HTTP status code (200 =
    accepted), or 0 when the call could not be made at all.

    The code is returned rather than a bool because *which* non-200 it is
    changes what to do about it, and the sweep's sync_log line is the only
    place that survives long enough to be read: 403 means Google is enforcing
    its documented JobPosting/BroadcastEvent-only scope and this lever is
    simply not available for /bhav pages; 429 means quota, which is
    self-correcting; 401 means the credential broke. Reporting a bare
    "0 recrawl sent" made all three look identical."""
    token = _access_token(SCOPE_INDEXING)
    if not token:
        return 0
    try:
        res = requests.post(
            INDEXING_URL, headers={"Authorization": f"Bearer {token}"},
            json={"url": url, "type": "URL_UPDATED"}, timeout=20)
        if res.status_code != 200:
            logger.info(f"Indexing API {res.status_code} for {url}: {res.text[:200]}")
        return res.status_code
    except requests.RequestException as e:
        logger.warning(f"Indexing API call failed for {url}: {e}")
        return 0


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
    """Sample `batch_size` /bhav URLs, compare Google's last crawl against
    the real data date, and request re-indexing for whatever is
    STALE_AFTER_DAYS or more behind. Logged to sync_log (source=
    'gsc_recrawl') so health_service can report on it without ever calling
    Google itself — same pattern as the mandi feed check."""
    from backend.services.sync_log_service import record_sync

    started = datetime.utcnow()
    if not configured():
        record_sync("gsc_recrawl", "skipped", detail="GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 not set")
        return {"skipped": True}

    targets = _bhav_targets()
    sample = random.sample(targets, min(batch_size, len(targets)))

    checked = stale = requested = errors = 0
    idx_codes: dict[int, int] = {}
    for url, expected in sample:
        status = inspect_url(url)
        if status is None:
            errors += 1
            continue
        checked += 1
        last_crawl = (status.get("lastCrawlTime") or "")[:10]  # YYYY-MM-DD
        if not last_crawl or last_crawl >= expected:
            continue
        try:
            behind = (date.fromisoformat(expected) - date.fromisoformat(last_crawl)).days
        except ValueError:
            continue
        if behind < STALE_AFTER_DAYS:
            continue
        stale += 1
        code = request_indexing(url)
        idx_codes[code] = idx_codes.get(code, 0) + 1
        if code == 200:
            requested += 1

    # Spell out the rejection codes. "0 recrawl भेजे" on its own reads like
    # "nothing was stale", which is the opposite of what it means.
    rejected = ", ".join(f"{c}×{n}" for c, n in sorted(idx_codes.items())
                         if c != 200)
    detail = (f"{checked} जांचे, {stale} बासी (>{STALE_AFTER_DAYS} दिन), "
              f"{requested} recrawl भेजे" + (f" (अस्वीकृत {rejected})" if rejected else "")
              + f", {errors} त्रुटि")
    # "failed" only when NOTHING was inspected successfully (auth broken, API
    # down) — same rule sync_log_service.mandi_freshness uses for its own
    # feed: a run that delivered *some* rows is success/partial, never failed.
    run_status = "failed" if checked == 0 else ("success" if errors == 0 else "partial")
    record_sync("gsc_recrawl", run_status,
                rows=checked, detail=detail, started_at=started)
    logger.info(f"GSC stale check: {detail}")
    return {"checked": checked, "stale": stale, "requested": requested, "errors": errors}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_stale_check(batch_size=20), indent=2, ensure_ascii=False))

# ============================================================
# backend/services/infra_service.py
# KrashiMitra — how much runway is left on the three free plans
# ------------------------------------------------------------
# The site runs on three free tiers, and every outage this project has had
# was a *quota* outage, not a software one:
#
#   • Netlify hit its usage cap on 11 Aug — 503 on every URL, then the DNS
#     zone stopped answering. The Render app was healthy the whole time.
#   • Neon flips the compute read-only at its 512 MB branch cap: reads fine,
#     every write 500s, and the Neon dashboard still says "All OK".
#   • Neon Free is 100 CU-hours/project/month. A 0.25 CU compute left always
#     on burns that in 16.7 days — the arithmetic, not the traffic, is the
#     ceiling.
#
# None of that is visible in /health, and by design: health_service.py may
# never call a third-party API (rule 1 in that file), because a status page
# that burns a metered quota causes the outage it reports. So the runway
# question lives here instead — admin-only, memoised for CACHE_TTL_SEC, and
# reached only when a person opens the panel.
#
# What this module does NOT do: it never writes, never schedules, and never
# runs on a timer. Every number is fetched live from the provider's own
# billing API when asked for.
#
# ── The shape ────────────────────────────────────────────────
# Each provider returns the same envelope so the panel can render any of them
# without knowing which is which:
#
#   {key, label, icon, status, detail, configured, setup{}, platform{},
#    meters[], facts[], links[], error}
#
# A *meter* is one metered allowance — bandwidth, build minutes, CU-hours,
# storage — normalised to {used, included, unit, pct} plus the projection
# that actually matters: at the current burn rate, does it run out before the
# billing period does, and on what date. `days_left` is the number to read.
#
# Nothing here raises. A provider whose token is missing reports itself as
# "off" with the exact steps to switch it on; a provider whose API is down
# reports "unknown" and says why. One broken probe never takes the page down.
#
# Runnable manually:  python -m backend.services.infra_service
# ============================================================

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger("krishi.infra")

CACHE_TTL_SEC = 300          # 5 min — these are billing numbers, they crawl
HTTP_TIMEOUT = 8
UA = {"User-Agent": "KrashiMitra-admin-infra/1.0"}

_cache: tuple[float, dict] | None = None

# A meter turns yellow here and red at 100%. 75% matches DB_STORAGE_WARN_PCT
# in db_health_service so the two never disagree about the same database.
WARN_PCT = int(os.getenv("INFRA_WARN_PCT", "75"))
# …and yellow early if the *projection* says it won't survive the month, even
# while today's number still looks comfortable.
PROJECT_WARN_PCT = 100

GB = 1024 ** 3

# ── Free-plan allowances ─────────────────────────────────────
# Only used where the provider's API does not report its own limit. Each is
# overridable by env so a plan upgrade does not need a code change.
def _envnum(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


NETLIFY_BANDWIDTH_GB   = _envnum("NETLIFY_BANDWIDTH_GB", 100)     # Free: 100 GB/mo
NETLIFY_BUILD_MINUTES  = _envnum("NETLIFY_BUILD_MINUTES", 300)    # Free: 300 min/mo
# 5 GB, NOT the 100 GB the marketing pages imply. Render suspended this
# workspace over exactly this cap on 17 Aug 2026 — `x-render-routing:
# suspend-by-user`, 503 on every proxied route while Netlify kept serving the
# static homepage. A meter defaulted to 100 GB would have read 4% used on the
# morning the service died, which is worse than having no meter at all.
RENDER_BANDWIDTH_GB    = _envnum("RENDER_BANDWIDTH_GB", 5)        # Free/Hobby: 5 GB/mo
RENDER_INSTANCE_HOURS  = _envnum("RENDER_INSTANCE_HOURS", 750)    # Free: 750 h/mo, all free services
NEON_COMPUTE_HOURS     = _envnum("NEON_COMPUTE_HOURS", 100)       # Free: 100 CU-hours/project/mo
NEON_TRANSFER_GB       = _envnum("NEON_TRANSFER_GB", 5)           # Free: 5 GB egress/mo

STATUS_PAGES = {
    "netlify": ("https://www.netlifystatus.com/api/v2/status.json", "https://www.netlifystatus.com"),
    "render":  ("https://status.render.com/api/v2/status.json",     "https://status.render.com"),
    # Neon publishes no JSON status API (neonstatus.com/api/v2/* is a 404), and
    # it would be misleading here anyway: through the read-only episodes the
    # dashboard reported "All OK" because the *service* was fine and only the
    # quota was not. The write canary below is the honest signal.
}


# ── formatting ───────────────────────────────────────────────

def _bytes(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} TB"


def _hours(h) -> str:
    if h is None:
        return "—"
    return f"{h:.1f} h" if h < 100 else f"{h:,.0f} h"


def _fmt(value, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "bytes":
        return _bytes(value)
    if unit == "hours":
        return _hours(value)
    if unit == "minutes":
        return f"{value:,.0f} min"
    return f"{value:,.0f}"


def _iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).isoformat() if dt else ""


def _ist(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return (dt.astimezone(timezone.utc) + timedelta(hours=5, minutes=30)).strftime(
        "%d %b %Y, %I:%M %p IST")


def _ago(dt: datetime | None) -> str:
    if not dt:
        return "—"
    secs = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    if secs < 0:
        return "अभी"
    mins = secs / 60
    if mins < 1:
        return "अभी"
    if mins < 60:
        return f"{int(mins)} मिनट पहले"
    hrs = mins / 60
    if hrs < 48:
        return f"{hrs:.1f} घंटे पहले"
    return f"{hrs / 24:.1f} दिन पहले"


def _parse_dt(v) -> datetime | None:
    """Accepts ISO-8601 with or without Z, and epoch seconds. Always returns
    an aware UTC datetime — mixing naive and aware here is how a projection
    silently produces a negative burn rate."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(v).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _month_window() -> tuple[datetime, datetime]:
    """Calendar month in UTC — the fallback billing period for providers whose
    API does not name one (Netlify build minutes, Render bandwidth)."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1, hour=0, minute=0,
                                               second=0, microsecond=0)
    return start, nxt


# ── the meter ────────────────────────────────────────────────

def _meter(key: str, label: str, used, included, unit: str,
           period: tuple[datetime | None, datetime | None] | None = None,
           note: str = "", warn_pct: int = WARN_PCT) -> dict:
    """One metered allowance, plus the burn-rate projection.

    `days_left` is what the panel leads with: at the rate used so far this
    period, how many days until the allowance is gone. It is deliberately NOT
    "days until the period resets" — on Neon Free those two numbers differ by
    a fortnight, and that gap is the whole reason this file exists.
    """
    m = {
        "key": key, "label": label, "unit": unit, "note": note,
        "used": used, "included": included,
        "used_txt": _fmt(used, unit),
        "included_txt": _fmt(included, unit) if included else "—",
        "pct": None, "status": "unknown",
        "projected": None, "projected_txt": "—", "projected_pct": None,
        "days_left": None, "exhausted_at": "", "period_pct": None,
        "period_start": "", "period_end": "",
    }
    if used is None:
        m["status"] = "unknown"
        return m
    if not included:
        # Metered but with no published cap — still worth watching, never a
        # verdict. (Neon's bytes-hour figures land here.)
        m["status"] = "ok"
        return m

    pct = used * 100.0 / included
    m["pct"] = round(pct, 1)

    start, end = (period or (None, None))
    if start and end and end > start:
        now = datetime.now(timezone.utc)
        total = (end - start).total_seconds()
        elapsed = max(1.0, min(total, (now - start).total_seconds()))
        m["period_start"], m["period_end"] = _iso(start), _iso(end)
        m["period_pct"] = round(elapsed * 100.0 / total, 1)
        rate = used / elapsed                        # units per second
        m["projected"] = rate * total
        m["projected_txt"] = _fmt(m["projected"], unit)
        m["projected_pct"] = round(m["projected"] * 100.0 / included, 1)
        if rate > 0:
            secs_left = (included - used) / rate
            m["days_left"] = round(max(0.0, secs_left) / 86400, 1)
            if secs_left > 0:
                # Cap the readout at the period end — "runs out in 90 days" is
                # noise when the allowance resets in 12.
                m["exhausted_at"] = _iso(min(now + timedelta(seconds=secs_left), end)) \
                    if now + timedelta(seconds=secs_left) < end else ""
            else:
                m["exhausted_at"] = _iso(now)

    if pct >= 100:
        m["status"] = "down"
    elif pct >= warn_pct or (m["projected_pct"] or 0) >= PROJECT_WARN_PCT:
        m["status"] = "warn"
    else:
        m["status"] = "ok"
    return m


# ── HTTP ─────────────────────────────────────────────────────

def _get(url: str, headers: dict | None = None, params: dict | None = None):
    """(data, error). Never raises — a provider that is down must not take
    the panel down with it."""
    try:
        r = requests.get(url, headers={**UA, **(headers or {})}, params=params,
                         timeout=HTTP_TIMEOUT)
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"
    if r.status_code == 401 or r.status_code == 403:
        return None, f"HTTP {r.status_code} — the API token was refused"
    if r.status_code >= 400:
        return None, f"HTTP {r.status_code}: {r.text[:120]}"
    try:
        return r.json(), ""
    except ValueError:
        return None, "the response was not JSON"


def _platform_status(key: str) -> dict:
    """The provider's own public status page. No key, no quota — and it is
    the one signal that tells an outage apart from our own bug."""
    entry = STATUS_PAGES.get(key)
    if not entry:
        return {}
    url, page = entry
    data, err = _get(url)
    if err or not isinstance(data, dict):
        return {"indicator": "unknown", "description": err or "status page unreadable",
                "url": page}
    st = data.get("status") or {}
    return {"indicator": st.get("indicator", "unknown"),
            "description": st.get("description", "—"), "url": page}


def _platform_rank(platform: dict) -> str:
    ind = (platform or {}).get("indicator")
    if ind == "none":
        return "ok"
    if ind in ("minor",):
        return "warn"
    if ind in ("major", "critical"):
        return "down"
    return "unknown"


def _off(key, label, icon, env, where, how, links) -> dict:
    """A provider with no token. Not a failure — but the panel must say
    exactly what to paste where, or it is a dead end."""
    return {
        "key": key, "label": label, "icon": icon, "status": "off",
        "configured": False,
        "detail": f"{env} सेट नहीं — इस सेवा का हिसाब नहीं दिख सकता",
        "setup": {"env": env, "where": where, "how": how},
        "platform": _platform_status(key), "meters": [], "facts": [],
        "links": links, "error": "",
    }


_SEV = {"ok": 0, "off": 0, "unknown": 1, "warn": 2, "down": 3}


def _worse(p: dict, status: str, detail: str) -> None:
    """Raise a card's verdict, never lower it.

    Plain assignment is a trap here: the checks run in the order they are
    cheapest to make, not in order of importance, so a late "last deploy
    failed" (warn) would otherwise overwrite an early "the service is
    suspended and every route is 503ing" (down) and the card would report the
    smaller problem.
    """
    if _SEV.get(status, 0) > _SEV.get(p.get("status", "ok"), 0):
        p["status"], p["detail"] = status, detail
    elif not p.get("detail") and detail:
        p["detail"] = detail


def _roll_up(provider: dict) -> dict:
    """Worst of (meters, platform status) becomes the card's verdict."""
    rank = {"ok": 0, "off": 0, "unknown": 1, "warn": 2, "down": 3}
    ranks = [rank.get(m["status"], 1) for m in provider["meters"]]
    ranks.append(rank.get(provider.get("status", "ok"), 0))
    # Only providers that publish a status page contribute one. Neon has none,
    # and scoring its absence as "unknown" would paint a perfectly healthy
    # database amber for a reason that has nothing to do with the database.
    if provider.get("platform"):
        ranks.append(rank.get(_platform_rank(provider["platform"]), 1))
    worst = max(ranks)
    provider["status"] = {0: "ok", 1: "unknown", 2: "warn", 3: "down"}[worst]
    return provider


# ── Netlify ──────────────────────────────────────────────────
# The static site: every page a farmer opens, plus ads.txt. When this runs
# out the whole front end 503s and Google stops being able to read ads.txt.

def _netlify() -> dict:
    token = os.getenv("NETLIFY_AUTH_TOKEN", "").strip()
    links = [["Netlify dashboard", "https://app.netlify.com"],
             ["Usage & billing", "https://app.netlify.com/teams/-/billing"]]
    if not token:
        return _off("netlify", "Netlify — वेबसाइट", "🌐", "NETLIFY_AUTH_TOKEN",
                    "https://app.netlify.com/user/applications#personal-access-tokens",
                    "User settings → Applications → Personal access tokens → "
                    "New access token. Paste it into Render → Environment as "
                    "NETLIFY_AUTH_TOKEN.", links)

    p = {"key": "netlify", "label": "Netlify — वेबसाइट", "icon": "🌐",
         "status": "ok", "configured": True, "detail": "", "setup": {},
         "platform": _platform_status("netlify"), "meters": [], "facts": [],
         "links": links, "error": ""}
    hdr = {"Authorization": f"Bearer {token}"}
    base = "https://api.netlify.com/api/v1"

    accounts, err = _get(f"{base}/accounts", headers=hdr)
    if err or not isinstance(accounts, list) or not accounts:
        p["status"] = "unknown"
        p["error"] = err or "Netlify returned no accounts for this token"
        p["detail"] = f"Netlify का हिसाब नहीं पढ़ा जा सका — {p['error']}"
        return _roll_up(p)

    want = os.getenv("NETLIFY_ACCOUNT_SLUG", "").strip()
    acct = next((a for a in accounts if a.get("slug") == want or a.get("id") == want),
                accounts[0])
    slug = acct.get("slug") or acct.get("id")
    plan = acct.get("type_name") or acct.get("type") or "—"
    p["facts"].append(["Team", f"{acct.get('name', '—')} · {plan}"])
    period = _month_window()

    # Netlify reports allowances two ways and neither is guaranteed present:
    # `capabilities` on the account object (documented-ish, {included, used}),
    # and two undocumented per-account endpoints the dashboard itself uses.
    # Read all of them, prefer whichever actually returned numbers, and treat
    # every field as optional — this shape has changed before.
    caps = acct.get("capabilities") or {}

    def _cap(name):
        c = caps.get(name) or {}
        if not isinstance(c, dict):
            return None, None
        return c.get("used"), c.get("included")

    bw_used, bw_inc = _cap("bandwidth")
    bw_period = period
    bw, bw_err = _get(f"{base}/accounts/{slug}/bandwidth", headers=hdr)
    if isinstance(bw, dict):
        bw_used = bw.get("used", bw_used)
        bw_inc = bw.get("included", bw_inc)
        ps, pe = _parse_dt(bw.get("period_start_date")), _parse_dt(bw.get("period_end_date"))
        if ps and pe:
            bw_period = (ps, pe)
        if bw.get("last_updated_at"):
            p["facts"].append(["Bandwidth गिनती अपडेट",
                               _ago(_parse_dt(bw["last_updated_at"]))])
    p["meters"].append(_meter(
        "bandwidth", "Bandwidth", bw_used, bw_inc or NETLIFY_BANDWIDTH_GB * GB, "bytes",
        bw_period,
        "पूरी साइट यहीं से जाती है। खत्म होते ही हर URL 503 — 11 अगस्त वाली घटना यही थी।"))

    bm_used, bm_inc = _cap("build_minutes")
    bm_period = period
    st, _ = _get(f"{base}/{acct.get('id', slug)}/builds/status", headers=hdr)
    if isinstance(st, dict):
        mins = st.get("minutes") or {}
        if isinstance(mins, dict):
            bm_used = mins.get("current", bm_used)
            bm_inc = (mins.get("included_minutes_with_packs")
                      or mins.get("included_minutes") or bm_inc)
            ps, pe = _parse_dt(mins.get("period_start_date")), _parse_dt(mins.get("period_end_date"))
            if ps and pe:
                bm_period = (ps, pe)
        if st.get("build_count") is not None:
            p["facts"].append(["इस period में builds", f"{st['build_count']:,}"])
        if st.get("active") is not None:
            p["facts"].append(["अभी चल रहे builds", str(st.get("active"))])
    p["meters"].append(_meter(
        "build_minutes", "Build minutes", bm_used, bm_inc or NETLIFY_BUILD_MINUTES,
        "minutes", bm_period,
        "हर push पर एक build। खत्म होने पर पुरानी साइट चलती रहती है, नया deploy रुक जाता है।"))

    # The live site itself — is the last deploy the one we think it is?
    site_id = os.getenv("NETLIFY_SITE_ID", "").strip()
    site, _serr = _get(f"{base}/sites/{site_id}" if site_id else f"{base}/sites",
                       headers=hdr, params=None if site_id else {"per_page": 5})
    if isinstance(site, list):
        site = next((s for s in site
                     if "krashimitra" in str(s.get("name", "")).lower()
                     or "krashimitra" in str(s.get("custom_domain", "")).lower()),
                    site[0] if site else None)
    if isinstance(site, dict):
        dep = site.get("published_deploy") or {}
        state = dep.get("state") or site.get("state") or "—"
        p["facts"] += [
            ["Site", site.get("custom_domain") or site.get("name") or "—"],
            ["आख़िरी publish", f"{state} · {_ago(_parse_dt(dep.get('published_at') or site.get('published_deploy', {}).get('created_at')))}"],
        ]
        if state not in ("ready", "—"):
            p["status"] = "warn"
            p["detail"] = f"आख़िरी deploy की स्थिति '{state}' है"

    worst = max(p["meters"], key=lambda m: m["pct"] or 0, default=None)
    if not p["detail"]:
        p["detail"] = (f"{worst['label']} {worst['pct']}% इस्तेमाल "
                       f"({worst['used_txt']} / {worst['included_txt']})"
                       if worst and worst["pct"] is not None
                       else "हिसाब मिल गया, पर किसी meter में आंकड़ा नहीं आया")
    return _roll_up(p)


# ── Render ───────────────────────────────────────────────────
# The API: /bhav, /naksha, every price page, the schedulers. Not metered the
# way the other two are — the free plan's real limits are 512 MB RAM (which
# OOMs the AI stack) and 750 instance-hours shared across every free service.

from backend.origin import backend_origin

# config/backend-origin.txt, so this probe cannot be the thing that goes stale
# after a Render rename — the rename is precisely what it is here to detect.
RENDER_ORIGIN = (os.getenv("RENDER_ORIGIN", "").strip() or backend_origin()).rstrip("/")
# A route that is actually served by Render, not by Netlify's static build. The
# homepage is the wrong probe: on 17 Aug it stayed perfectly green off Netlify
# while every proxied route 503'd.
RENDER_PROBE_PATH = os.getenv("RENDER_PROBE_PATH", "/health")
# Longer than HTTP_TIMEOUT on purpose — this one request may have to wake a
# sleeping free instance. The keep-alive workflow allows 90s for the same
# reason; 30s is the compromise that survives a normal cold start (~14s
# measured) without making a human wait on a dead host.
ORIGIN_TIMEOUT = int(os.getenv("RENDER_ORIGIN_TIMEOUT", "30"))


def _render_origin_probe() -> tuple[list, str, str]:
    """One request to our own Render origin. Returns (facts, status, detail).

    Worth the round trip for two things no billing API reports:

    1. `x-render-routing: suspend-by-user` — what a workspace suspended over
       the bandwidth cap actually looks like from outside. The /services API
       may still describe the service as healthy, and Netlify keeps serving
       the static homepage, so from inside the dashboard nothing looks wrong.
    2. Whether responses are really compressed. GZipMiddleware was added after
       the suspension, but Render fronts services with Cloudflare and it was
       never confirmed from outside whether compression survives the edge —
       and at a 5 GB cap, a 5.6x difference on Hindi pages is the difference
       between comfortable and suspended.
    """
    facts: list[list[str]] = []
    try:
        # Accept: text/html, so /health returns its status *page* rather than
        # the 16-byte {"status":"ok"}. Both are equally DB-free (that is the
        # keep-alive contract), but only the page is above GZipMiddleware's
        # minimum_size=500 — asking for the JSON would report "not compressed"
        # for every response forever, which is the wrong answer to the one
        # question this probe was added to settle.
        r = requests.get(RENDER_ORIGIN + RENDER_PROBE_PATH, timeout=ORIGIN_TIMEOUT,
                         headers={**UA, "Accept-Encoding": "gzip",
                                  "Accept": "text/html,application/xhtml+xml"},
                         allow_redirects=False)
    except requests.exceptions.Timeout:
        # A free instance sleeps after ~15 idle minutes and takes up to ~50s to
        # wake — measured 14s on this service. That is normal operation, not an
        # outage, and calling it "down" would leave this card permanently red
        # for a backend that is working, which is how a status page stops being
        # read. A real suspension does NOT time out: Cloudflare answers it
        # instantly with 404 + x-render-routing, handled below.
        return ([["Origin", f"{ORIGIN_TIMEOUT}s में जवाब नहीं"]], "warn",
                f"Render {ORIGIN_TIMEOUT}s में नहीं जागी — free instance सो रही "
                "हो सकती है (ठंडी शुरुआत ~50s तक लेती है)। दोबारा जाँचिए।")
    except Exception as e:
        return ([["Origin", f"{RENDER_ORIGIN} — {type(e).__name__}"]], "down",
                f"Render origin जवाब नहीं दे रहा ({str(e)[:60]})")

    routing = (r.headers.get("x-render-routing") or "").lower()
    enc = (r.headers.get("content-encoding") or "—")
    facts.append(["Origin", f"HTTP {r.status_code}"
                            + (f" · {routing}" if routing else "")])
    facts.append(["Compression", enc])

    if "suspend" in routing:
        return (facts, "down",
                "Render ने service suspend कर दी है — homepage Netlify से चलता "
                "रहेगा पर /bhav, /naksha, /go/* सब 503 दे रहे हैं")
    if "no-server" in routing:
        # Nothing is listening at this hostname at all. Two causes, and they
        # look identical from outside: the service is gone/suspended, or it was
        # renamed and this URL is stale — which has already cost this project
        # days of a silently stopped mandi feed once (see monitor.yml).
        return (facts, "down",
                f"{RENDER_ORIGIN} पर कोई service ही नहीं मिल रही (no-server) — "
                "या तो service बंद/suspend है, या hostname बदल गया है। "
                "Netlify से homepage चलता रहेगा, पर हर proxied route 404/503।")
    if r.status_code >= 500:
        return (facts, "down", f"Render origin पर HTTP {r.status_code}")
    if r.status_code >= 400:
        return (facts, "warn", f"Render origin पर HTTP {r.status_code}")
    # requests transparently decodes gzip, so a compressed response is proven
    # by the header alone; its absence on a body big enough to qualify is the
    # real signal (minimum_size=500 in main.py).
    if enc == "—" and len(r.content) >= 500:
        return (facts, "warn",
                "जवाब compress नहीं हो रहे — हिंदी पेज 5.6× ज़्यादा bandwidth "
                "खाएँगे और 5 GB cap जल्दी भरेगा")
    return (facts, "ok", "")


def _render() -> dict:
    key = os.getenv("RENDER_API_KEY", "").strip()
    links = [["Render dashboard", "https://dashboard.render.com"]]

    # Run before the token check on purpose. A suspension is exactly when the
    # billing API is least likely to help, and this needs no credentials.
    origin_facts, origin_status, origin_detail = _render_origin_probe()

    if not key:
        card = _off("render", "Render — API सर्वर", "⚙️", "RENDER_API_KEY",
                    "https://dashboard.render.com/u/settings#api-keys",
                    "Account settings → API Keys → Create API key. Paste it "
                    "into Render → Environment as RENDER_API_KEY (the service "
                    "may read its own account).", links)
        card["facts"] = origin_facts
        if origin_status != "ok":
            card["status"] = origin_status
            card["detail"] = origin_detail
        return _roll_up(card)

    p = {"key": "render", "label": "Render — API सर्वर", "icon": "⚙️",
         "status": origin_status if origin_status != "ok" else "ok",
         "configured": True, "detail": origin_detail, "setup": {},
         "platform": _platform_status("render"), "meters": [],
         "facts": list(origin_facts), "links": links, "error": ""}
    hdr = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    base = "https://api.render.com/v1"

    svc_id = os.getenv("RENDER_SERVICE_ID", "").strip()
    svc = None
    if svc_id:
        svc, err = _get(f"{base}/services/{svc_id}", headers=hdr)
    else:
        rows, err = _get(f"{base}/services", headers=hdr, params={"limit": 20})
        if isinstance(rows, list):
            # The list endpoint wraps each row as {cursor, service}.
            services = [r.get("service", r) for r in rows if isinstance(r, dict)]
            svc = next((s for s in services if s.get("type") == "web_service"),
                       services[0] if services else None)
    if not isinstance(svc, dict):
        p["error"] = err or "Render returned no services for this key"
        _worse(p, "unknown", f"Render का हिसाब नहीं पढ़ा जा सका — {p['error']}")
        return _roll_up(p)

    svc_id = svc.get("id") or svc_id
    plan = ((svc.get("serviceDetails") or {}).get("plan")
            or svc.get("plan") or "—")
    suspended = svc.get("suspended") == "suspended"
    p["facts"] += [
        ["Service", f"{svc.get('name', '—')} · {svc.get('region', '—')}"],
        ["Plan", str(plan)],
        ["Branch", str(svc.get("branch") or "—")],
        ["Suspended", "हाँ" if suspended else "नहीं"],
    ]
    if svc.get("dashboardUrl"):
        p["links"].append(["यह service", svc["dashboardUrl"]])
    if suspended:
        _worse(p, "down", "Service suspended है — API बंद है")

    start, end = _month_window()
    band, berr = _get(f"{base}/metrics/bandwidth", headers=hdr,
                      params={"resource": svc_id, "startTime": _iso(start),
                              "endTime": _iso(datetime.now(timezone.utc))})
    used = _sum_metric(band)
    p["meters"].append(_meter(
        "bandwidth", "Bandwidth", used, RENDER_BANDWIDTH_GB * GB, "bytes",
        (start, end),
        f"Free/Hobby में सिर्फ़ {RENDER_BANDWIDTH_GB:.0f} GB/महीना। 17 अगस्त 2026 "
        "को यही cap पार होने पर Render ने पूरा workspace suspend कर दिया था — "
        "Netlify से homepage चलता रहा और हर proxied route (/bhav, /naksha, "
        "/go/*, /sitemap.xml) 503 देने लगा। हिंदी पेज gzip के बिना 5.6× बड़े "
        "जाते हैं, इसलिए compression ही असली बचत है।"))
    if used is None and berr:
        p["facts"].append(["Bandwidth", f"नहीं मिला — {berr[:60]}"])

    # 750 free instance-hours are shared across every free service in the
    # account, and one always-on service already eats ~730 of them. Rendered
    # with warn_pct=100 on purpose: a single service can never exceed the
    # hours in a month, so this bar sitting at 95% late in the month is
    # arithmetic, not a warning, and colouring it amber every month would
    # train you to ignore the whole page.
    hours_in_month = (end - start).total_seconds() / 3600
    now = datetime.now(timezone.utc)
    elapsed_h = (now - start).total_seconds() / 3600
    p["meters"].append(_meter(
        "instance_hours", "Instance hours (अनुमान)", elapsed_h,
        RENDER_INSTANCE_HOURS, "hours", (start, end),
        f"इस महीने में {hours_in_month:.0f} घंटे हैं और free plan देता है "
        f"{RENDER_INSTANCE_HOURS:.0f} — यानी एक ही service 24×7 चल सकती है, "
        "दूसरी free service के लिए जगह नहीं बचती। यह service के चालू रहने का "
        "अनुमान है, Render का बिल नहीं।", warn_pct=100))

    dep, _ = _get(f"{base}/services/{svc_id}/deploys", headers=hdr, params={"limit": 1})
    if isinstance(dep, list) and dep:
        d = dep[0].get("deploy", dep[0]) if isinstance(dep[0], dict) else {}
        dstatus = d.get("status") or "—"
        p["facts"].append(["आख़िरी deploy",
                           f"{dstatus} · {_ago(_parse_dt(d.get('finishedAt') or d.get('createdAt')))}"])
        commit = (d.get("commit") or {}).get("message", "")
        if commit:
            p["facts"].append(["Commit", str(commit).splitlines()[0][:70]])
        if dstatus in ("build_failed", "update_failed", "canceled", "deactivated"):
            _worse(p, "warn", f"आख़िरी deploy {dstatus} — लाइव कोड पुराना है")

    # Restarts are the tell for the 512 MB ceiling: an OOM kill looks like a
    # perfectly healthy server one request at a time, and only the event log
    # shows it happened four times last night.
    evs, _ = _get(f"{base}/services/{svc_id}/events", headers=hdr, params={"limit": 50})
    if isinstance(evs, list) and evs:
        day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = []
        for row in evs:
            e = row.get("event", row) if isinstance(row, dict) else {}
            ts = _parse_dt(e.get("timestamp"))
            if ts and ts >= day_ago:
                recent.append(str(e.get("type") or ""))
        bad = [t for t in recent
               if any(w in t for w in ("failed", "restart", "crash", "unhealthy",
                                       "server_failed", "suspend"))]
        p["facts"].append(["पिछले 24h के events", f"{len(recent)} · {len(bad)} चिंता वाले"])
        if len(bad) >= 3:
            _worse(p, "warn", f"पिछले 24 घंटों में {len(bad)} बार restart/fail — "
                              "512 MB RAM की सीमा हो सकती है")

    if not p["detail"]:
        p["detail"] = f"{svc.get('name', 'service')} चालू है · plan {plan}"
    return _roll_up(p)


def _sum_metric(payload) -> float | None:
    """Render's metrics endpoints return a list of series, each with a
    `values` array of {timestamp, value}. Sum every point across every series;
    the shape has varied between endpoints, so anything unrecognised returns
    None rather than a confidently wrong zero."""
    if not isinstance(payload, list) or not payload:
        return None
    total, seen = 0.0, False
    for series in payload:
        if not isinstance(series, dict):
            continue
        for pt in series.get("values") or []:
            if isinstance(pt, dict) and pt.get("value") is not None:
                try:
                    total += float(pt["value"])
                    seen = True
                except (TypeError, ValueError):
                    pass
    return total if seen else None


# ── Neon ─────────────────────────────────────────────────────
# The database. Two independent limits, and they fail in opposite ways:
# storage (512 MB) silently flips the compute read-only, and compute
# (100 CU-hours) simply stops the project until the month rolls over.
#
# This card is the one that works with NO token at all — the write canary and
# the storage figures come straight out of Postgres.

def _neon() -> dict:
    p = {"key": "neon", "label": "Neon — डेटाबेस", "icon": "🗄️",
         "status": "ok", "configured": bool(os.getenv("NEON_API_KEY", "").strip()),
         "detail": "", "setup": {}, "platform": {}, "meters": [], "facts": [],
         "links": [["Neon console", "https://console.neon.tech"]], "error": ""}

    # 1. What Postgres itself says — free, exact, and the number that actually
    #    decides whether writes work.
    try:
        from backend.services.db_health_service import check as db_check
        st = db_check()
    except Exception as e:
        st = {}
        p["error"] = f"DB probe failed: {str(e)[:120]}"

    if st:
        p["meters"].append(_meter(
            "storage", "Storage (इस branch की)", st.get("size_bytes") or None,
            st.get("limit_bytes") or None, "bytes", None,
            "cap पर पहुँचते ही Neon compute को read-only कर देता है: पेज चलते "
            "रहते हैं, पर signup/order/alert कुछ भी सेव नहीं होता। असली इस्तेमाल "
            "इससे ज़्यादा है — cap change-history भी गिनता है।"))
        writable = bool(st.get("writable"))
        p["facts"].append(["लिख सकते हैं", "हाँ" if writable else "नहीं"])
        if not writable:
            p["status"] = "down"
            p["detail"] = ("डेटाबेस read-only है — कुछ भी सेव नहीं हो रहा। "
                           + (st.get("reason") or "")[:100])

    # 2. What the billing API says. Compute hours are invisible from inside
    #    Postgres, and they are the limit that ends the month early.
    token = os.getenv("NEON_API_KEY", "").strip()
    if not token:
        p["setup"] = {
            "env": "NEON_API_KEY",
            "where": "https://console.neon.tech/app/settings/api-keys",
            "how": "Neon console → Account settings → API keys → Create new "
                   "API key. Paste it into Render → Environment as NEON_API_KEY. "
                   "इसके बिना ऊपर वाला storage तो दिखता है, पर CU-hours नहीं।",
        }
        p["facts"].append(["CU-hours", "NEON_API_KEY के बिना नहीं दिख सकता"])
        if not p["detail"]:
            p["detail"] = (f"Storage {st.get('size_pretty', '—')} / "
                           f"{st.get('limit_pretty', '—')} · compute के आंकड़े "
                           "के लिए NEON_API_KEY चाहिए")
        return _roll_up(p)

    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base = "https://console.neon.tech/api/v2"
    pid = os.getenv("NEON_PROJECT_ID", "").strip()

    if pid:
        data, err = _get(f"{base}/projects/{pid}", headers=hdr)
        proj = (data or {}).get("project") if isinstance(data, dict) else None
    else:
        data, err = _get(f"{base}/projects", headers=hdr)
        projects = (data or {}).get("projects") if isinstance(data, dict) else None
        proj = None
        if projects:
            # Match the project the app is actually connected to, so a console
            # with several projects cannot report the wrong one's runway.
            host = os.getenv("DATABASE_URL", "")
            proj = next((x for x in projects
                         if x.get("id") and x["id"] in host), projects[0])
    if not isinstance(proj, dict):
        p["error"] = err or "Neon returned no project for this key"
        p["facts"].append(["Neon API", p["error"]])
        if not p["detail"]:
            p["detail"] = f"CU-hours नहीं पढ़े जा सके — {p['error']}"
        return _roll_up(p)

    p["facts"].append(["Project", f"{proj.get('name', '—')} · {proj.get('region_id', '—')}"])
    period = (_parse_dt(proj.get("consumption_period_start")),
              _parse_dt(proj.get("consumption_period_end")))
    if not (period[0] and period[1]):
        period = _month_window()

    cpu_sec = proj.get("compute_time_seconds")
    cu_hours = (cpu_sec / 3600.0) if isinstance(cpu_sec, (int, float)) else None
    p["meters"].append(_meter(
        "compute", "Compute (CU-hours)", cu_hours, NEON_COMPUTE_HOURS, "hours", period,
        f"Free plan में {NEON_COMPUTE_HOURS:.0f} CU-hours/महीना। 0.25 CU का "
        "compute हमेशा चालू रहे तो यह 16-17 दिन में खत्म हो जाता है — इसीलिए "
        "keep-alive ping DB को नहीं छूता और watchdog 3 घंटे का है।"))

    transfer = proj.get("data_transfer_bytes")
    p["meters"].append(_meter(
        "transfer", "Data transfer (egress)", transfer, NEON_TRANSFER_GB * GB,
        "bytes", period, "Neon से बाहर जाने वाला डेटा। Free plan: 5 GB/महीना।"))

    active = proj.get("active_time_seconds")
    if isinstance(active, (int, float)):
        p["facts"].append(["Compute जागा रहा", _hours(active / 3600.0)])
    written = proj.get("written_data_bytes")
    if isinstance(written, (int, float)):
        p["facts"].append(["लिखा गया WAL", _bytes(written)])
    if period[1]:
        p["facts"].append(["अगला reset", _ist(period[1])])

    if not p["detail"]:
        worst = max((m for m in p["meters"] if m["pct"] is not None),
                    key=lambda m: m["pct"], default=None)
        p["detail"] = (f"{worst['label']} {worst['pct']}% "
                       f"({worst['used_txt']} / {worst['included_txt']})"
                       if worst else "आंकड़े मिल गए")
    return _roll_up(p)


# ── the runner ───────────────────────────────────────────────

_PROBES = (("netlify", _netlify), ("render", _render), ("neon", _neon))


def _verdict(providers: list[dict]) -> dict:
    """One line at the top of the page: what breaks first, and when.

    Sorting by percentage would rank a bandwidth meter at 60% above a compute
    meter at 40% that is burning four times as fast. Runway is the only
    ordering that answers "what do I have to deal with this week", so the
    headline is driven by days_left and falls back to percentage only when
    nothing has a measurable burn rate.
    """
    worst = max((_SEV.get(p["status"], 1) for p in providers), default=0)
    status = {0: "ok", 1: "unknown", 2: "warn", 3: "down"}[worst]

    metered = [(p, m) for p in providers for m in p["meters"]]
    running_out = sorted(
        [(p, m) for p, m in metered
         if m.get("days_left") is not None and m.get("exhausted_at")],
        key=lambda pm: pm[1]["days_left"])
    fullest = sorted([(p, m) for p, m in metered if m.get("pct") is not None],
                     key=lambda pm: -pm[1]["pct"])

    # Something already broken outranks anything merely running low. Leading
    # with a meter here is how a red banner ends up saying "storage 33%" on the
    # morning the API is returning 404 to every request — reassuring text under
    # an alarm colour is worse than no banner.
    broken = [p for p in providers if p["status"] == "down"]
    if broken:
        prov = broken[0]
        headline = f"{prov['label'].split('—')[0].strip()} बंद है"
        sub = prov["detail"] or "नीचे उसका कार्ड देखिए।"
        return {"status": status, "headline": headline, "sub": sub,
                "at_risk": [{"provider": p["label"], "meter": m["label"],
                             "days_left": m["days_left"], "pct": m["pct"]}
                            for p, m in running_out[:3]]}

    if running_out:
        prov, m = running_out[0]
        headline = (f"{prov['label'].split('—')[0].strip()} का {m['label']} "
                    f"{m['days_left']:.0f} दिन में खत्म हो जाएगा")
        sub = (f"अभी {m['used_txt']} / {m['included_txt']} ({m['pct']}%) — "
               f"इसी रफ़्तार से चला तो period खत्म होने से पहले ही सीमा आ जाएगी।")
    elif [p for p in providers if p["status"] == "warn"]:
        # Warned for a reason no meter can express — a restart storm, a failed
        # deploy, a degraded platform. Say that reason rather than a number.
        prov = [p for p in providers if p["status"] == "warn"][0]
        headline = f"{prov['label'].split('—')[0].strip()} पर ध्यान चाहिए"
        sub = prov["detail"] or "नीचे उसका कार्ड देखिए।"
    elif fullest:
        prov, m = fullest[0]
        headline = (f"सबसे ज़्यादा भरा हुआ: {prov['label'].split('—')[0].strip()} "
                    f"{m['label']} — {m['pct']}%")
        sub = (f"{m['used_txt']} / {m['included_txt']}. "
               "किसी भी meter की रफ़्तार period खत्म होने से पहले सीमा तक "
               "नहीं पहुँच रही।")
    else:
        headline = "कोई भी हिसाब नहीं पढ़ा जा सका"
        sub = "नीचे हर सेवा के कार्ड में वजह लिखी है।"

    return {"status": status, "headline": headline, "sub": sub,
            "at_risk": [{"provider": p["label"], "meter": m["label"],
                         "days_left": m["days_left"], "pct": m["pct"]}
                        for p, m in running_out[:3]]}


def run(use_cache: bool = True) -> dict:
    """Every provider, probed in parallel. Memoised for CACHE_TTL_SEC.

    Parallel because this is three providers × up to five HTTP calls each:
    serially that is a 20-second admin page, and an admin page slow enough to
    be annoying is an admin page nobody opens.
    """
    global _cache
    now = time.time()
    if use_cache and _cache and now - _cache[0] < CACHE_TTL_SEC:
        cached = dict(_cache[1])
        cached["from_cache"] = True
        cached["cached_age_sec"] = round(now - _cache[0])
        return cached

    t0 = time.perf_counter()
    providers: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(_PROBES)) as pool:
        futures = [(key, pool.submit(fn)) for key, fn in _PROBES]
        for key, fut in futures:
            try:
                providers.append(fut.result(timeout=45))
            except Exception as e:
                logger.error(f"infra probe '{key}' failed: {e}")
                providers.append({
                    "key": key, "label": key.title(), "icon": "❓",
                    "status": "unknown", "configured": False,
                    "detail": f"जाँच नहीं हो सकी: {str(e)[:120]}",
                    "setup": {}, "platform": {}, "meters": [], "facts": [],
                    "links": [], "error": str(e)[:200],
                })

    order = {k: i for i, (k, _) in enumerate(_PROBES)}
    providers.sort(key=lambda p: order.get(p["key"], 99))

    payload = {
        "checked_at": _ist(datetime.now(timezone.utc)),
        "took_ms": round((time.perf_counter() - t0) * 1000),
        "cache_ttl": CACHE_TTL_SEC,
        "from_cache": False,
        "cached_age_sec": 0,
        "verdict": _verdict(providers),
        "providers": providers,
    }
    _cache = (now, payload)
    return payload


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run(use_cache=False), indent=2, ensure_ascii=False))

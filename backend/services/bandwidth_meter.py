# ============================================================
# backend/services/bandwidth_meter.py
# KrashiMitra — where Render's outbound bandwidth actually goes
#
# Render meters every byte this process sends and suspends the whole workspace
# at 5 GB/month. It has done so twice (17 Aug, 16 Sep 2026), and on 24 Sep the
# graph was on course for a third — 3.22 GB used by the 24th — while nobody
# could say WHICH responses were spending it: the access log records path,
# status and time, never size, and Render's graph is one line for the service.
#
# Everything that reaches this origin is, by definition, something Cloudflare
# did not serve from cache (a MISS, a BYPASS, or a stale-while-revalidate
# refresh). So counting bytes here counts exactly what Render bills for, split
# the two ways that decide what to fix:
#   * group — which part of the site (bhav, naksha, images/articles, js/css…)
#   * agent — who asked (googlebot, bingbot, gptbot, … or human)
#
# Counters live in memory and are folded into the bandwidth_usage table once an
# hour (and on shutdown), one row per (day, group, agent). Hourly on purpose:
# Neon's compute went read-only in September from write churn, and a
# per-request INSERT here would be the worst possible version of that — this is
# a few dozen UPSERTs an hour on a table that never grows past ~100 rows a day.
# ============================================================

import logging
import re
import threading
from datetime import date, datetime, timedelta

log = logging.getLogger("krishi.bandwidth")

# ── Who asked ────────────────────────────────────────────────
# Named bots first (order matters: "googlebot-image" before "googlebot"), then
# a generic catch for anything that calls itself a bot/crawler/spider or is an
# HTTP library. Everything else is counted as a person.
_AGENTS = [
    ("googlebot-image", re.compile(r"googlebot-image", re.I)),
    ("googlebot",       re.compile(r"googlebot|google-inspectiontool|storebot-google|googleother|adsbot-google|mediapartners-google", re.I)),
    ("bingbot",         re.compile(r"bingbot|bingpreview|msnbot", re.I)),
    ("gptbot",          re.compile(r"gptbot|oai-searchbot|chatgpt-user", re.I)),
    ("claudebot",       re.compile(r"claudebot|claude-user|claude-searchbot|anthropic", re.I)),
    ("perplexity",      re.compile(r"perplexity", re.I)),
    ("bytespider",      re.compile(r"bytespider|tiktokspider", re.I)),
    ("meta",            re.compile(r"meta-externalagent|facebookexternalhit|facebookbot|whatsapp", re.I)),
    ("applebot",        re.compile(r"applebot", re.I)),
    ("yandex",          re.compile(r"yandex", re.I)),
    ("seo-tools",       re.compile(r"ahrefs|semrush|mj12bot|dotbot|dataforseo|rogerbot|serpstat|blexbot|seokicks|barkrowler", re.I)),
    ("ccbot",           re.compile(r"ccbot|amazonbot|petalbot|duckduckbot|baiduspider", re.I)),
    ("script",          re.compile(r"python-requests|python-urllib|httpx|aiohttp|curl/|wget|go-http-client|okhttp|java/|node-fetch|axios|headless", re.I)),
    ("other-bot",       re.compile(r"bot|crawl|spider|slurp|fetch|scan|monitor|preview", re.I)),
]


def agent_of(user_agent: str) -> str:
    ua = user_agent or ""
    if not ua:
        return "no-ua"
    for name, rx in _AGENTS:
        if rx.search(ua):
            return name
    return "human"


# ── Which part of the site ───────────────────────────────────
_IMG_EXT = (".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".avif")
_FONT_EXT = (".woff2", ".woff", ".ttf")
_MAX_GROUPS = 300          # a scanner inventing paths must not grow this forever


def group_of(path: str, status: int) -> str:
    """A short, bounded label for a request path.

    Errors are pooled by class first: a bot walking /wp-admin/* must not mint a
    new group per guess, and "how many bytes go on 404s" is itself the answer
    worth having."""
    if status >= 500:
        return "5xx"
    if status == 404:
        return "404"
    p = (path or "/").lower()
    last = p.rsplit("/", 1)[-1]
    if last.endswith(_IMG_EXT):
        parts = [s for s in p.split("/") if s]
        # images/articles/x.webp → images/articles ; assets/logo.png → images/assets
        if parts and parts[0] == "images":
            return f"images/{parts[1]}" if len(parts) >= 3 else "images"
        if parts and parts[0] == "uploads":
            return "uploads"
        return f"images/{parts[0]}" if len(parts) >= 2 else "images"
    if last.endswith(_FONT_EXT):
        return "fonts"
    if last.endswith((".js", ".css")):
        return "js/css"
    if last.endswith((".geojson",)):
        return "geojson"
    if last.endswith(".pdf"):
        return "pdf"
    if p in ("/", "/index.html"):
        return "home"
    seg = p.strip("/").split("/", 1)[0]
    if seg.endswith(".html"):
        seg = seg[:-5]
    if seg == "api" and "/" in p.strip("/"):
        # /api/weather?… → api/weather — the API is several different costs.
        seg = "api/" + p.strip("/").split("/")[1]
    return seg or "home"


# ── The counters ─────────────────────────────────────────────
_lock = threading.Lock()
# (day_iso, group, agent) → [requests, bytes]
_pending: dict = {}
# Everything since boot, never cleared by a flush — the admin view reads this
# plus the table, so the last hour is never missing from the answer.
_started_at = datetime.utcnow()


def record(path: str, status: int, user_agent: str, nbytes: int) -> None:
    grp = group_of(path, status)
    agt = agent_of(user_agent)
    key_day = date.today().isoformat()
    with _lock:
        if len(_pending) >= _MAX_GROUPS * 4 and (key_day, grp, agt) not in _pending:
            grp = "other"
        row = _pending.setdefault((key_day, grp, agt), [0, 0])
        row[0] += 1
        row[1] += nbytes


def pending_snapshot() -> dict:
    with _lock:
        return {k: list(v) for k, v in _pending.items()}


def flush() -> int:
    """Fold the in-memory counters into bandwidth_usage. Returns rows written.

    The counters are swapped out before the DB call so requests never wait on
    Postgres; if the write fails they are merged back, so a sleeping Neon costs
    a delayed number, never a lost one."""
    global _pending
    with _lock:
        batch, _pending = _pending, {}
    if not batch:
        return 0
    try:
        from sqlalchemy import text
        from backend.database.db import engine
        with engine.begin() as conn:
            for (day, grp, agt), (n, b) in batch.items():
                conn.execute(text(
                    "INSERT INTO bandwidth_usage (day, grp, agent, requests, bytes) "
                    "VALUES (:d, :g, :a, :n, :b) "
                    "ON CONFLICT (day, grp, agent) DO UPDATE SET "
                    "requests = bandwidth_usage.requests + EXCLUDED.requests, "
                    "bytes = bandwidth_usage.bytes + EXCLUDED.bytes"),
                    {"d": day, "g": grp, "a": agt, "n": n, "b": b})
        return len(batch)
    except Exception as e:
        log.warning(f"bandwidth flush failed, keeping counters in memory: {e}")
        with _lock:
            for k, (n, b) in batch.items():
                row = _pending.setdefault(k, [0, 0])
                row[0] += n
                row[1] += b
        return 0


def report(days: int = 7) -> dict:
    """Bytes by group and by agent over the last `days` days, stored + unflushed."""
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    rows: dict = {}
    db_error = None
    try:
        from sqlalchemy import text
        from backend.database.db import engine
        with engine.connect() as conn:
            for day, grp, agt, n, b in conn.execute(text(
                    "SELECT day, grp, agent, requests, bytes FROM bandwidth_usage "
                    "WHERE day >= :s"), {"s": since}):
                k = (str(day), grp, agt)
                r = rows.setdefault(k, [0, 0])
                r[0] += int(n)
                r[1] += int(b)
    except Exception as e:
        db_error = str(e)[:200]
    for k, (n, b) in pending_snapshot().items():
        if k[0] >= since:
            r = rows.setdefault(k, [0, 0])
            r[0] += n
            r[1] += b

    def _roll(idx):
        out: dict = {}
        for k, (n, b) in rows.items():
            o = out.setdefault(k[idx], {"requests": 0, "bytes": 0})
            o["requests"] += n
            o["bytes"] += b
        return sorted(({"name": name, **v} for name, v in out.items()),
                      key=lambda x: -x["bytes"])

    total = sum(b for _, b in rows.values())
    by_day = sorted(_roll(0), key=lambda x: x["name"])
    # group × agent, top 25 — "bhav pages to googlebot" is the line you act on
    pairs: dict = {}
    for (_, g, a), (n, b) in rows.items():
        o = pairs.setdefault((g, a), {"requests": 0, "bytes": 0})
        o["requests"] += n
        o["bytes"] += b
    top_pairs = sorted(({"group": g, "agent": a, **v} for (g, a), v in pairs.items()),
                       key=lambda x: -x["bytes"])[:25]
    return {
        "days": days,
        "since": since,
        "total_bytes": total,
        "total_requests": sum(n for n, _ in rows.values()),
        "by_group": _roll(1),
        "by_agent": _roll(2),
        "by_day": by_day,
        "top_pairs": top_pairs,
        "counting_since": _started_at.isoformat(timespec="seconds") + "Z",
        "db_error": db_error,
    }


# ── The middleware ───────────────────────────────────────────
class BandwidthMeterMiddleware:
    """Pure ASGI, so it sees the exact bytes handed to the server — after
    GZipMiddleware (which sits innermost) and including redirects and errors
    raised by the other middleware. It never touches the response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        state = {"status": 0, "bytes": 0}

        async def _send(message):
            t = message.get("type")
            if t == "http.response.start":
                state["status"] = message.get("status", 0)
                # status line + headers — small, but a 301 is almost nothing else
                state["bytes"] += 17 + sum(len(k) + len(v) + 4
                                           for k, v in message.get("headers", []))
            elif t == "http.response.body":
                state["bytes"] += len(message.get("body", b"") or b"")
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            try:
                ua = ""
                for k, v in scope.get("headers", []):
                    if k == b"user-agent":
                        ua = v.decode("latin-1", "replace")
                        break
                record(scope.get("path", "/"), state["status"], ua, state["bytes"])
            except Exception:
                pass   # a meter must never be the reason a request failed

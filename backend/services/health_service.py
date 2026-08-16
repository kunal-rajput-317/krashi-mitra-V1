# ============================================================
# backend/services/health_service.py
# KrashiMitra — feature-by-feature health
# ------------------------------------------------------------
# `{"status":"ok"}` only answers "is the process alive". It stayed green
# through every outage this site has actually had: the mandi feed silently
# stopping, Neon flipping the compute read-only (reads fine, every write 500),
# the weather cache going cold, a scheduler that never started. This module
# answers the real question instead — *which feature* is broken — one check per
# user-visible capability, each independently sandboxed so a failing probe
# reports itself as broken rather than taking the page down with it.
#
# Two rules this file exists under:
#
#   1. It NEVER calls a third-party API. Every judgement is derived from what
#      the last automatic run left behind (sync_log, table contents, files on
#      disk). A health page that burns the data.gov quota is a health page that
#      causes outages. The single exception is _chk_ads_txt, which fetches 59
#      bytes from our own origin — see the reasoning in that function; a purely
#      on-disk check provably could not catch the failure it exists for.
#   2. A pass is memoised for CACHE_TTL_SEC. The database is Neon: round-the-
#      clock traffic is what quota-blocked the compute in July and took the
#      whole site down, which is why the staleness watchdog runs 3-hourly and
#      why /health itself never touches the DB. A refreshing browser tab, a
#      crawler and the monitor workflow all share one set of queries.
#
# Public output carries status + facts a farmer could already read off the
# site (feed freshness, district counts). Business numbers and infra internals
# (accounts, orders, storage headroom, which keys are configured) only appear
# for `detailed=True`, which the route gates behind the admin password.
#
# Runnable manually:  python -m backend.services.health_service
# ============================================================

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from backend.database.db import SessionLocal

logger = logging.getLogger("krishi.health")

BASE_DIR = Path(__file__).resolve().parents[2]
IST = timedelta(hours=5, minutes=30)

# Set at import time — routes/health.py imports this module at app start-up,
# so this is the process boot, not the first request.
BOOT_AT = datetime.utcnow()

CACHE_TTL_SEC = 60
_cache: dict[bool, tuple[float, dict]] = {}

# ── Thresholds ───────────────────────────────────────────────
# Mandi: six fetches a day (08/10/13/16/20 + 23:11 IST). One missed daytime
# window is worth a warning; 30h without fresh rows is the same line the
# monitor workflow already pages on, so the two never disagree.
MANDI_WARN_HOURS   = 14
MANDI_DOWN_HOURS   = 30
# The snapshot itself ages more slowly than the feed — it is merged, not
# rebuilt, so yesterday's prices stay up while today's are still arriving.
SNAPSHOT_WARN_HOURS = 30
SNAPSHOT_DOWN_HOURS = 72
# Weather refreshes every 2h for a fixed district list.
WEATHER_WARN_HOURS  = 5
WEATHER_DOWN_HOURS  = 12
WEATHER_STALE_SHARE = 0.25   # share of districts that may be stale before it matters
# History drives the deltas and the trend chart; a 3-day hole flattens both.
HISTORY_WARN_DAYS = 3

# "off" is a feature that is deliberately not switched on — it never drags the
# overall verdict down, it just says so.
_RANK = {"ok": 0, "off": 0, "warn": 1, "down": 2}
_WORST = {v: k for k, v in {"ok": 0, "warn": 1, "down": 2}.items()}


# ── formatting ───────────────────────────────────────────────

def _ist(dt: datetime | None) -> str:
    return (dt + IST).strftime("%d %b %Y, %I:%M %p IST") if dt else "—"


def _ago(dt: datetime | None) -> str:
    """Human 'x पहले' for a naive-UTC timestamp."""
    if not dt:
        return "—"
    secs = max(0.0, (datetime.utcnow() - dt).total_seconds())
    if secs < 90:
        return "अभी"
    mins = secs / 60
    if mins < 60:
        return f"{int(mins)} मिनट पहले"
    hrs = mins / 60
    if hrs < 48:
        return f"{hrs:.1f} घंटे पहले"
    return f"{hrs / 24:.1f} दिन पहले"


def _hours_since(dt: datetime | None) -> float | None:
    if not dt:
        return None
    return max(0.0, (datetime.utcnow() - dt).total_seconds() / 3600)


def _dur(seconds: float) -> str:
    mins = seconds / 60
    if mins < 60:
        return f"{int(mins)} मिनट"
    hrs = mins / 60
    if hrs < 48:
        return f"{hrs:.1f} घंटे"
    return f"{hrs / 24:.1f} दिन"


def _num(n) -> str:
    return f"{int(n):,}" if n is not None else "—"


def _yn(v: bool) -> str:
    return "हाँ" if v else "नहीं"


# ── query helpers ────────────────────────────────────────────

def _scalar(db, sql: str, **params):
    return db.execute(text(sql), params).scalar()


def _row(db, sql: str, **params):
    return db.execute(text(sql), params).first()


def _approx_count(db, table: str) -> tuple[int, bool]:
    """(rows, is_estimate). Uses the planner's reltuples for tables that can
    reach hundreds of thousands of rows — an exact count(*) there is a seq scan
    every single time this page loads. Falls back to a real count when the
    table has never been analysed (reltuples is -1 on a fresh table)."""
    try:
        n = _scalar(db, "SELECT reltuples::bigint FROM pg_class WHERE relname = :t", t=table)
        if n is not None and int(n) > 0:
            return int(n), True
    except Exception:
        pass
    return int(_scalar(db, f"SELECT count(*) FROM {table}") or 0), False


_db_state_cache: tuple[float, dict] | None = None


def _db_state() -> dict:
    """db_health_service.check() — the write canary plus storage figures. Two
    cards read it (लिखना and स्टोरेज) and it costs its own connection plus a
    round-trip each time, so a pass runs it once."""
    global _db_state_cache
    now = time.time()
    if _db_state_cache and now - _db_state_cache[0] < CACHE_TTL_SEC:
        return _db_state_cache[1]
    from backend.services.db_health_service import check
    st = check()
    _db_state_cache = (now, st)
    return st


def _status_counts(db, table: str) -> dict:
    """{status: n} for the work-log tables (queued|done|empty|error)."""
    rows = db.execute(text(f"SELECT status, count(*) FROM {table} GROUP BY status")).all()
    return {(r[0] or "?"): int(r[1]) for r in rows}


# ── individual checks ────────────────────────────────────────
# Each returns {status, detail, facts[]}. `facts` is a list of [label, value]
# pairs rendered as the small print under the card. Raising is allowed — the
# runner turns an exception into a "down" card naming the check.

def _chk_api(db, detailed):
    up = (datetime.utcnow() - BOOT_AT).total_seconds()
    facts = [["चालू है", _dur(up)], ["शुरू हुआ", _ist(BOOT_AT)]]
    if detailed:
        facts.append(["होस्ट", "Render" if os.getenv("RENDER") else "local"])
        facts.append(["वर्कर PID", str(os.getpid())])
    # A restart wipes the APScheduler state and re-runs the boot fetches, so a
    # server that keeps rebooting looks healthy one request at a time while
    # nothing scheduled ever completes. Say it out loud.
    status = "warn" if up < 300 else "ok"
    detail = ("अभी-अभी शुरू हुआ है — शेड्यूल किए गए काम अभी चल रहे हैं"
              if status == "warn" else f"चालू · {_dur(up)} से बिना रुके")
    return {"status": status, "detail": detail, "facts": facts}


def _chk_db_read(db, detailed):
    t0 = time.perf_counter()
    _scalar(db, "SELECT 1")
    ms = round((time.perf_counter() - t0) * 1000)
    # The first query after an idle spell pays Neon's compute wake-up — several
    # seconds, and completely normal. Warning on that would leave the page
    # permanently yellow for a database that is working fine, so only flag a
    # round-trip slow enough to be near the 20s pool timeout.
    status = "ok" if ms < 8000 else "warn"
    if status == "warn":
        detail = f"डेटाबेस बहुत धीमा है — {ms} ms"
    elif ms > 1500:
        detail = f"जवाब {ms} ms में (कंप्यूट अभी नींद से जागा)"
    else:
        detail = f"जवाब {ms} ms में"
    return {"status": status, "detail": detail, "facts": [["राउंड-ट्रिप", f"{ms} ms"]]}


def _chk_db_write(db, detailed):
    """The canary that catches the failure nothing else can see: Neon turns the
    compute read-only on its storage cap, so every page keeps serving while no
    signup, order, appeal or alert can be saved."""
    st = _db_state()
    facts = [["लिख सकते हैं", _yn(st["writable"])]]
    if detailed:
        facts += [["स्टोरेज", f"{st['size_pretty']} / {st['limit_pretty']}"],
                  ["इस्तेमाल", f"{st['pct_used']}%"]]
    if not st["writable"]:
        return {"status": "down",
                "detail": "डेटाबेस कुछ भी सेव नहीं कर पा रहा — साइनअप, ऑर्डर, "
                          "अलर्ट और लिस्टिंग रुकी हुई हैं",
                "facts": facts + ([["वजह", st["reason"][:120]]] if detailed and st["reason"] else [])}
    if st["warn"]:
        return {"status": "warn",
                "detail": "लिखना ठीक है, पर स्टोरेज भर रहा है — भरते ही सब सेव होना बंद हो जाएगा",
                "facts": facts}
    return {"status": "ok", "detail": "नया डेटा सेव हो रहा है", "facts": facts}


def _chk_scheduler(db, detailed):
    """APScheduler is what makes the whole site unattended. If it did not start,
    nothing else here will look wrong for another day — and then everything will."""
    from backend.services.mandi_scheduler   import scheduler as mandi_sched
    from backend.services.weather_scheduler import scheduler as weather_sched

    facts, running, total = [], 0, 0
    for label, sched in (("मंडी", mandi_sched), ("मौसम", weather_sched)):
        total += 1
        if not sched.running:
            facts.append([label, "बंद है"])
            continue
        running += 1
        jobs = sched.get_jobs()
        nxt = min((j.next_run_time for j in jobs if j.next_run_time), default=None)
        facts.append([label, f"{len(jobs)} काम · अगला {nxt:%d %b, %I:%M %p} IST"
                             if nxt else f"{len(jobs)} काम · कोई समय तय नहीं"])

    if running == 0:
        return {"status": "down",
                "detail": "कोई ऑटो-शेड्यूलर नहीं चल रहा — भाव और मौसम अपने आप अपडेट नहीं होंगे",
                "facts": facts}
    if running < total:
        return {"status": "warn", "detail": f"{total} में से {running} शेड्यूलर चल रहे हैं",
                "facts": facts}
    return {"status": "ok", "detail": "भाव और मौसम अपने आप अपडेट हो रहे हैं", "facts": facts}


def _chk_mandi_feed(db, detailed):
    """Did the last data.gov→DB run actually deliver rows?"""
    from backend.services.sync_log_service import mandi_freshness
    f = mandi_freshness(MANDI_DOWN_HOURS)
    if f.get("error"):
        return {"status": "warn", "detail": "फ़ेच का रिकॉर्ड पढ़ा नहीं जा सका", "facts": []}

    age  = f.get("last_fresh_age_hours")
    rows = f.get("last_fresh_rows")
    facts = [["आख़िरी सफल फ़ेच", f.get("last_fresh_at") or "—"],
             ["आख़िरी कोशिश", f"{f.get('last_run_status') or '—'} · {f.get('last_run_at') or '—'}"]]
    if age is None:
        return {"status": "down", "detail": "कभी कोई सफल फ़ेच दर्ज नहीं हुआ", "facts": facts}
    if f.get("stale") or age > MANDI_DOWN_HOURS:
        return {"status": "down",
                "detail": f"{age} घंटे से कोई नया भाव नहीं आया — फ़ीड अटकी है",
                "facts": facts}
    if age > MANDI_WARN_HOURS:
        return {"status": "warn",
                "detail": f"आख़िरी नया भाव {age} घंटे पहले — एक फ़ेच विंडो छूटी है",
                "facts": facts}
    return {"status": "ok",
            "detail": f"आख़िरी फ़ेच {age} घंटे पहले · {_num(rows)} भाव आए",
            "facts": facts}


def _chk_mandi_snapshot(db, detailed):
    """What /mandi, /bhav and every price page actually read."""
    r = _row(db, """SELECT count(*), max(fetched_at),
                           count(DISTINCT district), count(DISTINCT commodity),
                           count(DISTINCT state)
                    FROM mandi_prices""")
    n, newest, districts, crops, states = (r[0] or 0), r[1], (r[2] or 0), (r[3] or 0), (r[4] or 0)
    facts = [["आख़िरी अपडेट", f"{_ist(newest)} · {_ago(newest)}"],
             ["दायरा", f"{states} राज्य · {districts} ज़िले · {crops} फ़सलें"]]
    if n == 0:
        return {"status": "down", "detail": "स्नैपशॉट खाली है — भाव पेज पर दिखाने को कुछ नहीं",
                "facts": facts}
    hrs = _hours_since(newest)
    detail = f"{_num(n)} भाव · {districts} ज़िले · {crops} फ़सलें"
    if hrs is None or hrs > SNAPSHOT_DOWN_HOURS:
        return {"status": "down", "detail": f"{detail} — पर {_ago(newest)} से बासी", "facts": facts}
    if hrs > SNAPSHOT_WARN_HOURS:
        return {"status": "warn", "detail": f"{detail} — आख़िरी ताज़गी {_ago(newest)}", "facts": facts}
    return {"status": "ok", "detail": detail, "facts": facts}


def _chk_mandi_history(db, detailed):
    """Append-only daily rows behind the deltas, sparklines and trend chart."""
    n, approx = _approx_count(db, "mandi_price_history")
    r = _row(db, "SELECT min(arrival_dt), max(arrival_dt) FROM mandi_price_history")
    oldest, newest = r[0], r[1]
    span = (newest - oldest).days + 1 if (oldest and newest) else 0
    facts = [["दायरा", f"{oldest:%d %b} — {newest:%d %b}" if oldest and newest else "—"],
             ["रखे हुए दिन", str(span)]]
    if not n or not newest:
        return {"status": "down", "detail": "कोई इतिहास नहीं — घट-बढ़ और ग्राफ़ खाली रहेंगे",
                "facts": facts}
    label = f"{'≈' if approx else ''}{_num(n)} दिन-भाव · {span} दिन का इतिहास"
    lag = (datetime.utcnow().date() - newest).days
    if lag > HISTORY_WARN_DAYS:
        return {"status": "warn", "detail": f"{label} — पर नया दिन {lag} दिन से नहीं जुड़ा",
                "facts": facts}
    return {"status": "ok", "detail": label, "facts": facts}


def _chk_gsc(db, detailed):
    """Daily Search Console staleness sweep for /bhav (see gsc_service.py) —
    the fix for a Google snippet showing a stale 'today's price' weeks after
    the real one moved on. This check NEVER calls Google itself; it only
    reads what the last scheduled sweep left in sync_log, same as the mandi
    feed check above."""
    from backend.services.gsc_service import configured
    if not configured():
        return {"status": "off", "detail": "GSC क्रेडेंशियल कॉन्फ़िगर नहीं (GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 खाली)",
                "facts": []}
    from backend.database.db import SyncLog
    r = (db.query(SyncLog).filter(SyncLog.source == "gsc_recrawl")
           .order_by(SyncLog.finished_at.desc()).first())
    if not r:
        return {"status": "warn", "detail": "कॉन्फ़िगर है पर अभी तक एक भी स्वीप नहीं चली", "facts": []}
    facts = [["आख़िरी स्वीप", f"{_ist(r.finished_at)} · {_ago(r.finished_at)}"],
             ["नतीजा", r.detail or "—"]]
    hrs = _hours_since(r.finished_at)
    if hrs is not None and hrs > 48:
        return {"status": "warn", "detail": f"स्वीप {_ago(r.finished_at)} से नहीं चली", "facts": facts}
    if r.status == "failed":
        return {"status": "warn", "detail": "आख़िरी स्वीप में एक भी पेज नहीं जांचा जा सका — token/अनुमति जांचें",
                "facts": facts}
    return {"status": "ok", "detail": f"{r.rows} पेज जांचे गए · {_ago(r.finished_at)}", "facts": facts}


def _chk_weather(db, detailed):
    if not os.getenv("OPENWEATHER_API_KEY", "").strip():
        return {"status": "down", "detail": "OPENWEATHER_API_KEY सेट नहीं — मौसम रिफ़्रेश नहीं हो सकता",
                "facts": []}
    r = _row(db, """SELECT count(*), max(updated_at),
                           sum(CASE WHEN is_stale THEN 1 ELSE 0 END)
                    FROM weather_cache""")
    n, newest, stale = (r[0] or 0), r[1], (r[2] or 0)
    facts = [["ज़िले", str(n)],
             ["आख़िरी रिफ़्रेश", f"{_ist(newest)} · {_ago(newest)}"]]
    if stale:
        facts.append(["बासी ज़िले", str(stale)])
    if n == 0:
        return {"status": "down", "detail": "मौसम कैश खाली है", "facts": facts}
    hrs = _hours_since(newest)
    detail = f"{n} ज़िले · आख़िरी अपडेट {_ago(newest)}"
    if hrs is None or hrs > WEATHER_DOWN_HOURS:
        return {"status": "down", "detail": f"{detail} — रिफ़्रेश रुक गया है", "facts": facts}
    # A handful of districts OpenWeather has no station for are stale forever.
    # Flagging those keeps the card permanently yellow and trains you to ignore
    # it, so only a share big enough to mean the fetch itself is struggling warns.
    if hrs > WEATHER_WARN_HOURS:
        return {"status": "warn", "detail": f"{detail} — रिफ़्रेश में देर हो रही है", "facts": facts}
    if stale > n * WEATHER_STALE_SHARE:
        return {"status": "warn", "detail": f"{detail} · {stale} ज़िले बासी", "facts": facts}
    return {"status": "ok",
            "detail": detail + (f" ({stale} ज़िले बासी)" if stale else ""), "facts": facts}


def _chk_seasonality(db, detailed):
    """/bhav's "पिछले N साल का रुझान" panel — monthly medians built lazily from
    the data.gov archive after a page asks for its slice."""
    n, _ = _approx_count(db, "mandi_price_monthly")
    st = _status_counts(db, "mandi_season_slices")
    done, err = st.get("done", 0), st.get("error", 0)
    queued = st.get("queued", 0)
    facts = [["स्लाइस", f"{done} बने · {queued} कतार में · {err} फेल"],
             ["महीने-सारांश", _num(n)]]
    if not st:
        return {"status": "off", "detail": "अभी किसी पेज ने रुझान माँगा ही नहीं", "facts": facts}
    if done == 0 and err:
        return {"status": "down", "detail": f"{err} स्लाइस फेल, एक भी नहीं बना", "facts": facts}
    if err > done:
        return {"status": "warn", "detail": f"{err} स्लाइस फेल हो रहे हैं ({done} बने)", "facts": facts}
    return {"status": "ok", "detail": f"{_num(n)} महीने-सारांश · {done} स्लाइस तैयार", "facts": facts}


def _chk_kcc(db, detailed):
    """/sawal — real Kisan Call Centre Q&A, harvested crop by crop."""
    n = int(_scalar(db, "SELECT count(*) FROM kcc_qa") or 0)
    st = _status_counts(db, "kcc_crop_builds")
    done, err, queued = st.get("done", 0), st.get("error", 0), st.get("queued", 0)
    facts = [["फ़सलें", f"{done} तैयार · {queued} कतार में · {err} फेल"],
             ["सवाल-जवाब", _num(n)]]
    if not st:
        return {"status": "off", "detail": "अभी हार्वेस्ट शुरू नहीं हुआ", "facts": facts}
    if n == 0 and err:
        return {"status": "down", "detail": f"{err} फ़सलें फेल, एक भी सवाल-जवाब नहीं", "facts": facts}
    if err > done:
        return {"status": "warn", "detail": f"{err} फ़सलों का हार्वेस्ट फेल हो रहा है", "facts": facts}
    return {"status": "ok", "detail": f"{_num(n)} सवाल-जवाब · {done} फ़सलें तैयार", "facts": facts}


def _chk_ai_chat(db, detailed):
    """The /chat pipeline. Deliberately does NOT touch RAG/Chroma — loading the
    embedding model is what OOMs a 512MB instance, and a health check that
    causes the outage it reports is worse than no check."""
    from backend.config import get_setting
    keys = [k for k in ("GEMINI_API_KEY", "GEMINI_API_KEY2", "GEMINI_API_KEY_2",
                        "GEMINI_API_KEY3", "GEMINI_API_KEY_3")
            if os.getenv(k, "").strip()]
    cached = None
    try:
        from cache.cache_engine import get_cache_stats
        cached = get_cache_stats().get("total_entries")
    except Exception:
        pass

    facts = [["तैयार जवाब (कैश)", _num(cached)],
             ["RAG", "चालू" if get_setting("rag_enabled", True) else "बंद"]]
    if detailed:
        facts.append(["Gemini कुंजियाँ", str(len(keys))])
        facts.append(["मॉडल", str(get_setting("gemini_model", "—"))])

    if not keys and not get_setting("ollama_enabled", False):
        return {"status": "down", "detail": "कोई AI मॉडल कॉन्फ़िगर नहीं — सवाल का जवाब नहीं मिलेगा",
                "facts": facts}
    return {"status": "ok",
            "detail": f"जवाब देने को तैयार · कैश में {_num(cached)} जवाब", "facts": facts}


def _chk_alerts(db, detailed):
    """Bhav alerts ride on Web Push; without VAPID keys the bell is a no-op."""
    from backend.services.push_service import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY
    configured = bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)
    alerts = int(_scalar(db, "SELECT count(*) FROM mandi_alerts") or 0)
    devices = int(_scalar(db, "SELECT count(*) FROM push_subscriptions WHERE active") or 0)

    facts = []
    if detailed:
        facts = [["चालू अलर्ट", _num(alerts)], ["जुड़े डिवाइस", _num(devices)]]
    if not configured:
        if alerts:
            return {"status": "warn",
                    "detail": f"VAPID कुंजी नहीं — {alerts} लगे अलर्ट किसी को नहीं जाएँगे",
                    "facts": facts}
        return {"status": "off", "detail": "वेब पुश कॉन्फ़िगर नहीं है", "facts": facts}
    return {"status": "ok", "detail": "भाव अलर्ट भेजने को तैयार", "facts": facts}


def _chk_bazar(db, detailed):
    r = _row(db, "SELECT count(*), max(created_at) FROM bazar_posts WHERE status = 'active'")
    n, newest = (r[0] or 0), r[1]
    facts = [["आख़िरी लिस्टिंग", f"{_ist(newest)} · {_ago(newest)}" if newest else "—"]]
    if n == 0:
        return {"status": "ok", "detail": "फ़ीड चालू है, अभी कोई लिस्टिंग नहीं", "facts": facts}
    return {"status": "ok", "detail": f"{_num(n)} चालू लिस्टिंग · आख़िरी {_ago(newest)}",
            "facts": facts}


def _chk_email(db, detailed):
    """OTP/reset mail. Without this nobody can finish a signup."""
    resend = bool(os.getenv("RESEND_API_KEY", "").strip()
                  and os.getenv("RESEND_FROM_EMAIL", "").strip())
    smtp = bool(os.getenv("SMTP_EMAIL", "").strip() and os.getenv("SMTP_PASSWORD", "").strip())
    facts = []
    if detailed:
        facts = [["Resend", _yn(resend)], ["SMTP fallback", _yn(smtp)]]
    if not (resend or smtp):
        return {"status": "down", "detail": "कोई मेल भेजने का रास्ता नहीं — OTP नहीं जाएगा",
                "facts": facts}
    return {"status": "ok", "detail": f"OTP मेल जा रहे हैं ({'Resend' if resend else 'SMTP'})",
            "facts": facts}


def _chk_articles(db, detailed):
    d = BASE_DIR / "frontend" / "articles"
    files = sorted(d.glob("*.html")) if d.is_dir() else []
    newest = max((f.stat().st_mtime for f in files), default=0)
    facts = [["आख़िरी बदलाव",
              _ago(datetime.utcfromtimestamp(newest)) if newest else "—"]]
    if not files:
        return {"status": "down", "detail": "एक भी लेख फ़ाइल नहीं मिली", "facts": facts}
    return {"status": "ok", "detail": f"{len(files)} लेख पेज लाइव", "facts": facts}


def _chk_ads_txt(db, detailed):
    """Is ads.txt actually being SERVED — not merely present in the repo?

    This is the one check that leaves the box, and it is a deliberate, narrow
    exception to rule 1 at the top of this file. That rule exists so a health
    page cannot burn a metered third-party quota; this fetches 59 bytes from
    our own origin, has no API key and no quota, and is memoised with every
    other check (CACHE_TTL_SEC).

    It earns the exception because no filesystem check could have caught the
    failure it is here for. frontend/ads.txt was committed and correct the
    whole time AdSense reported "Ads.txt status: Not found" — what actually
    happened is that Netlify hit its usage cap, served 503 on every URL and
    then stopped answering DNS for the zone, so Google's crawl of ads.txt
    failed. Every on-disk check was green throughout. Without ads.txt Google
    may stop paying out on the inventory, so a silent failure here costs real
    money and nothing else on this page would have shown it.
    """
    import requests

    url = "https://krashimitra.in/ads.txt"
    pub = "pub-2792326360609634"          # the AdSense account this site bills to
    try:
        r = requests.get(url, timeout=6, allow_redirects=False,
                         headers={"User-Agent": "KrashiMitra-health/1.0"})
    except Exception as e:
        return {"status": "down",
                "detail": f"ads.txt माँगा नहीं जा सका — साइट बंद हो सकती है ({str(e)[:60]})",
                "facts": [["URL", url]]}

    ctype = (r.headers.get("content-type") or "").split(";")[0].strip()
    facts = [["HTTP", str(r.status_code)], ["प्रकार", ctype or "—"],
             ["आकार", f"{len(r.content)} bytes"]]

    if r.status_code in (301, 302, 307, 308):
        return {"status": "warn",
                "detail": f"ads.txt रीडायरेक्ट हो रहा है → {r.headers.get('location', '?')[:60]}",
                "facts": facts}
    if r.status_code != 200:
        return {"status": "down", "detail": f"ads.txt पर {r.status_code} — Google इसे नहीं पढ़ पाएगा",
                "facts": facts}
    # A missing static file is served as the 200-HTML fallback, never a 404 —
    # so status alone proves nothing. The publisher line is the real test.
    if pub not in r.text:
        return {"status": "down",
                "detail": "ads.txt में पब्लिशर ID नहीं मिली — फ़ाइल बदल गई या HTML लौट रहा है",
                "facts": facts}
    if ctype != "text/plain":
        return {"status": "warn", "detail": f"ads.txt का content-type {ctype} है, text/plain चाहिए",
                "facts": facts}
    return {"status": "ok", "detail": "ads.txt लाइव है और पब्लिशर ID सही है", "facts": facts}


def _chk_naksha(db, detailed):
    """/naksha is server-rendered from one JSON + self-hosted district GeoJSON."""
    cfg = BASE_DIR / "backend" / "data" / "naksha_states.json"
    if not cfg.is_file():
        return {"status": "down", "detail": "naksha_states.json गायब है", "facts": []}
    data = json.loads(cfg.read_text(encoding="utf-8"))
    states = data.get("states", data) if isinstance(data, dict) else data
    n_states = len(states)
    geo = list((BASE_DIR / "frontend" / "data").glob("*-districts.geojson"))
    facts = [["राज्य/UT", str(n_states)], ["ज़िला बाउंड्री फ़ाइलें", str(len(geo))]]
    if not geo:
        return {"status": "down", "detail": "कोई ज़िला बाउंड्री फ़ाइल नहीं — नक्शे खाली दिखेंगे",
                "facts": facts}
    return {"status": "ok", "detail": f"{n_states} राज्य · {len(geo)} ज़िला-नक्शे", "facts": facts}


# ── admin-only cards ─────────────────────────────────────────

def _chk_accounts(db, detailed):
    total = int(_scalar(db, "SELECT count(*) FROM users") or 0)
    week = int(_scalar(db, "SELECT count(*) FROM users WHERE created_at > :t",
                       t=datetime.utcnow() - timedelta(days=7)) or 0)
    newest = _scalar(db, "SELECT max(created_at) FROM users")
    return {"status": "ok", "detail": f"{_num(total)} खाते · पिछले 7 दिन में {week} नए",
            "facts": [["आख़िरी साइनअप", f"{_ist(newest)} · {_ago(newest)}" if newest else "—"]]}


def _chk_orders(db, detailed):
    total = int(_scalar(db, "SELECT count(*) FROM orders") or 0)
    newest = _scalar(db, "SELECT max(created_at) FROM orders")
    by_status = _status_counts(db, "orders")
    # Order.status is stored capitalised ("Pending" / "Quoted" / …) — fold it
    # so a casing change in the admin panel can't silently zero this out.
    folded = {}
    for k, v in by_status.items():
        folded[k.lower()] = folded.get(k.lower(), 0) + v
    pending = folded.get("pending", 0) + folded.get("booked", 0)
    facts = [["आख़िरी ऑर्डर", f"{_ist(newest)} · {_ago(newest)}" if newest else "—"],
             ["स्थिति", " · ".join(f"{k}: {v}" for k, v in sorted(by_status.items())) or "—"]]
    status = "warn" if pending else "ok"
    detail = (f"{_num(total)} ऑर्डर · {pending} पर आपका जवाब बाकी" if pending
              else f"{_num(total)} ऑर्डर · कुछ लंबित नहीं")
    return {"status": status, "detail": detail, "facts": facts}


def _chk_integrations(db, detailed):
    """Which outside services are wired up. Booleans only — never a key, never
    a fragment of one."""
    from backend.config import get_setting
    # tier: "core"     — the site has no content without it
    #       "feature"  — one feature silently stops working
    #       "optional" — an admin convenience; its absence is normal, so it is
    #                    reported as a fact and never colours the card
    items = [
        ("data.gov.in (भाव)", "core",     "DATA_GOV_API_KEY"),
        ("OpenWeather",       "core",     "OPENWEATHER_API_KEY"),
        ("Gemini",            "feature",  "GEMINI_API_KEY"),
        ("Resend (मेल)",      "feature",  "RESEND_API_KEY"),
        ("Web Push (VAPID)",  "feature",  "VAPID_PRIVATE_KEY"),
        ("Anthropic (सीडर)",  "optional", "ANTHROPIC_API_KEY"),
    ]
    got = {name: (tier, bool(os.getenv(env, "").strip())) for name, tier, env in items}
    facts = [[name, _yn(ok)] for name, (_, ok) in got.items()]
    facts.append(["Ollama fallback", _yn(bool(get_setting("ollama_enabled", False)))])

    core    = [n for n, (t, ok) in got.items() if t == "core" and not ok]
    feature = [n for n, (t, ok) in got.items() if t == "feature" and not ok]
    if core:
        return {"status": "down", "detail": "ज़रूरी कुंजी गायब: " + ", ".join(core), "facts": facts}
    if feature:
        return {"status": "warn", "detail": "कॉन्फ़िगर नहीं: " + ", ".join(feature), "facts": facts}
    return {"status": "ok", "detail": "सभी ज़रूरी सेवाएँ कॉन्फ़िगर हैं", "facts": facts}


def _chk_storage(db, detailed):
    from backend.services.db_health_service import WARN_PCT
    st = _db_state()
    tables = db.execute(text("""
        SELECT relname, pg_total_relation_size(c.oid) AS bytes
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        ORDER BY bytes DESC LIMIT 5""")).all()

    def _mb(b):
        return f"{b / 1024 / 1024:.1f} MB"

    facts = [[t[0], _mb(t[1])] for t in tables]
    detail = f"{st['size_pretty']} / {st['limit_pretty']} ({st['pct_used']}%)"
    if not st["writable"]:
        return {"status": "down", "detail": detail + " — कैप पर पहुँच गया", "facts": facts}
    if st["pct_used"] >= WARN_PCT:
        return {"status": "warn", "detail": detail, "facts": facts}
    return {"status": "ok", "detail": detail, "facts": facts}


# ── registry ─────────────────────────────────────────────────
# (group key, group label, group note, [(check key, label, icon, fn, admin_only)])

_GROUPS = [
    ("core", "बुनियाद", "इनमें से कुछ गिरा तो बाकी सब गिरेगा", [
        ("api",       "वेबसाइट सर्वर",     "🌐", _chk_api,       False),
        ("db_read",   "डेटाबेस — पढ़ना",    "🗄️", _chk_db_read,   False),
        ("db_write",  "डेटाबेस — लिखना",   "✍️", _chk_db_write,  False),
        ("scheduler", "ऑटो-शेड्यूलर",      "⏱️", _chk_scheduler, False),
    ]),
    ("data", "डेटा फ़ीड", "रोज़ अपने आप आने वाला डेटा", [
        ("mandi_feed",     "मंडी भाव फ़ेच",   "📥", _chk_mandi_feed,     False),
        ("mandi_snapshot", "आज के भाव",       "🌾", _chk_mandi_snapshot, False),
        ("mandi_history",  "भाव इतिहास",      "📈", _chk_mandi_history,  False),
        ("weather",        "मौसम",            "🌦️", _chk_weather,        False),
        ("seasonality",    "मौसमी रुझान",     "📅", _chk_seasonality,    False),
        ("kcc",            "किसान कॉल सेंटर", "☎️", _chk_kcc,            False),
        ("gsc",            "Google री-इंडेक्स", "📡", _chk_gsc,          False),
    ]),
    ("features", "सुविधाएँ", "किसान जो पेज रोज़ खोलते हैं", [
        ("ai_chat",  "AI सवाल-जवाब",   "🤖", _chk_ai_chat,  False),
        ("alerts",   "भाव अलर्ट",      "🔔", _chk_alerts,   False),
        ("bazar",    "कृषि बाज़ार",     "🛒", _chk_bazar,    False),
        ("email",    "ईमेल / OTP",     "✉️", _chk_email,    False),
        ("articles", "लेख",            "📰", _chk_articles, False),
        ("naksha",   "नक्शा",          "🗺️", _chk_naksha,   False),
        ("ads_txt",  "ads.txt (विज्ञापन)", "💰", _chk_ads_txt, False),
    ]),
    ("private", "निजी (एडमिन)", "सिर्फ़ एडमिन पासवर्ड के साथ दिखता है", [
        ("accounts",     "खाते",          "👤", _chk_accounts,     True),
        ("orders",       "ऑर्डर",         "📦", _chk_orders,       True),
        ("storage",      "डेटाबेस स्टोरेज", "💾", _chk_storage,      True),
        ("integrations", "बाहरी सेवाएँ",   "🔌", _chk_integrations, True),
    ]),
]


def _run_one(db, key, label, icon, fn, detailed) -> dict:
    t0 = time.perf_counter()
    try:
        out = fn(db, detailed)
        status = out.get("status", "ok")
        detail, facts = out.get("detail", ""), out.get("facts", [])
    except Exception as e:
        # A probe that blew up tells us nothing about the feature, so say
        # exactly that instead of quietly reporting the feature as healthy.
        logger.error(f"health check '{key}' failed: {e}")
        status, detail, facts = "down", f"जाँच नहीं हो सकी: {str(e)[:120]}", []
    card = {"key": key, "label": label, "icon": icon, "status": status,
            "detail": detail, "facts": [list(f) for f in facts]}
    if detailed:
        card["took_ms"] = round((time.perf_counter() - t0) * 1000)
    return card


def run_checks(detailed: bool = False, use_cache: bool = True) -> dict:
    """Every feature check, grouped. Memoised for CACHE_TTL_SEC."""
    now = time.time()
    hit = _cache.get(detailed)
    if use_cache and hit and now - hit[0] < CACHE_TTL_SEC:
        return hit[1]

    t0 = time.perf_counter()
    groups, worst = [], 0
    db = SessionLocal()
    try:
        for gkey, glabel, gnote, checks in _GROUPS:
            cards = []
            for key, label, icon, fn, admin_only in checks:
                if admin_only and not detailed:
                    continue
                card = _run_one(db, key, label, icon, fn, detailed)
                worst = max(worst, _RANK.get(card["status"], 0))
                cards.append(card)
            if cards:
                groups.append({"key": gkey, "label": glabel, "note": gnote, "checks": cards})
    finally:
        db.close()

    now_utc = datetime.utcnow()
    payload = {
        "status":     _WORST[worst],
        "detailed":   detailed,
        "checked_at": _ist(now_utc),
        "took_ms":    round((time.perf_counter() - t0) * 1000),
        "cache_ttl":  CACHE_TTL_SEC,
        "groups":     groups,
        "counts": {
            s: sum(1 for g in groups for c in g["checks"] if c["status"] == s)
            for s in ("ok", "warn", "down", "off")
        },
    }
    _cache[detailed] = (now, payload)
    return payload


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_checks(detailed=True, use_cache=False), indent=2, ensure_ascii=False))

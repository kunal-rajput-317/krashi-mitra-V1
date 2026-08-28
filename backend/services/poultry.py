# ============================================================
# services/poultry.py
# अंडे का रेट — the zone registry and the rate store behind /farm/poultry
#
# TWO LAYERS, TWO STORES — the same split rental.py makes, for the same
# reasons.
#   The REGISTRY (which zones exist, their slug, their Hindi name, their
#   state) is data/poultry_zones.json, re-read whenever its mtime changes.
#   Editorial, rarely changing, and a diff someone can read.
#   The RATES are Postgres, written by the scheduler from the NECC sheet.
#
# A ZONE NECC ADDS STILL GETS A PAGE. The registry is a translation table, not
# a gate: an unknown zone falls through to a derived slug and its English name
# as the Hindi one. Dropping a real, published rate because nobody had typed a
# translation for it would be the registry deciding what data exists, which is
# backwards.
#
# THE PAGES NEVER FETCH. Everything here reads Postgres; the only thing that
# talks to e2necc.com is the scheduler (poultry_scheduler.py). Same rule the
# mandi seasonality layer follows — user traffic must not be able to hammer,
# or get blocked by, someone else's server.
#
# THE STORE IS IDEMPOTENT. NECC restates the whole month on every fetch and
# revises earlier days in place, so writes are upserts keyed by
# zone_slug|date. Re-running today's fetch ten times changes nothing; a
# revision NECC publishes on the 5th for the 3rd is picked up automatically.
# ============================================================

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func

from backend.database.db import PoultryRate, PoultryRateHistory

log = logging.getLogger("krishi.poultry")

_PATH = Path(__file__).resolve().parents[1] / "data" / "poultry_zones.json"

# ~34 zones x 365 days = ~12.4k rows/year. Two years of history costs about as
# much as a week of the mandi feed, and buys the "इस समय पिछले साल" comparison
# without a separate summary table — see PoultryRateHistory's docstring.
POULTRY_HISTORY_DAYS = 760

# How many days back the sparkline on a hub row reaches.
SPARK_DAYS = 15

_cache: dict | None = None
_mtime: float = -1.0


# ── the registry ────────────────────────────────────────────

def _load() -> dict:
    """The parsed registry, re-read only when it changes on disk. A bad edit
    keeps the last good copy rather than blanking every zone name."""
    global _cache, _mtime
    try:
        m = _PATH.stat().st_mtime
    except OSError:
        return _cache or {}
    if _cache is None or m != _mtime:
        try:
            parsed = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _cache or {}
        if isinstance(parsed, dict) and parsed.get("zones"):
            _cache, _mtime = parsed, m
        elif _cache is None:
            _cache, _mtime = {}, m
    return _cache or {}


def _slugify(text: str) -> str:
    """'Bengaluru (CC)' -> 'bengaluru-cc'. Only ever reached by a zone NECC
    added that the registry has not been taught yet — a registered zone uses
    its declared slug, which is the correctly-spelled one."""
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def zone_meta(necc_name: str) -> dict:
    """Everything we know about one NECC zone label, always answerable.

    `known` is False for a zone that is not in the registry — the page still
    renders it, and the flag is what lets an admin (or a test) notice that the
    source has grown a zone we should name properly.
    """
    z = _load().get("zones", {}).get(necc_name)
    if z:
        return {**z, "necc_name": necc_name, "known": True}
    # NECC's labels carry a trailing centre marker, "Bhopal (CC)" style. Strip
    # it for the display name so an unregistered zone reads as a place, not as
    # a code.
    display = re.sub(r"\s*\((?:CC|PC|[A-Z]{2})\)\s*$", "", necc_name).strip()
    return {"slug": _slugify(display) or _slugify(necc_name),
            "hi": display, "state_hi": "", "state": "",
            "centre": "CC" if "(CC)" in necc_name else "PC",
            "necc_name": necc_name, "known": False}


def zones() -> dict:
    """slug -> meta, for every registered zone. Used by the sitemap to know
    which URLs are legitimate before a single row has been fetched."""
    return {m["slug"]: m
            for m in (zone_meta(n) for n in _load().get("zones", {}))}


# ── writing ─────────────────────────────────────────────────

def _dates_from_sheet(row: dict, month: int, year: int) -> list[tuple[date, int]]:
    """A parsed month row -> [(date, paise)] in date order, skipping days the
    month does not have (a 31st column in a 30-day month is always "-", but a
    source glitch should not raise either)."""
    out = []
    for day, paise in sorted(row["days"].items()):
        try:
            out.append((date(year, month, day), paise))
        except ValueError:
            continue
    return out


def store_sheet(db, sheet: dict) -> dict:
    """Write one parsed month into history + snapshot. Returns a summary.

    History is upserted per (zone, date) because NECC revises published days
    in place; the snapshot is rewritten only when the sheet carries a date at
    least as recent as the one already stored, so replaying an OLD month can
    never drag today's headline number backwards.
    """
    month, year = sheet["month"], sheet["year"]
    written = revised = 0
    zones_seen = []

    for row in sheet["rows"]:
        meta = zone_meta(row["zone"])
        slug = meta["slug"]
        if not meta["known"]:
            # The zone still gets stored and still gets a page — but nobody
            # would otherwise find out that it is sitting there with an English
            # name on a Hindi page until a farmer saw it. Say so once per fetch.
            log.warning("egg rate: zone %r is not in poultry_zones.json — "
                        "serving as %r with no Hindi name", row["zone"], slug)
        series = _dates_from_sheet(row, month, year)
        if not series:
            continue
        zones_seen.append(slug)

        keys = [f"{slug}|{d.isoformat()}" for d, _ in series]
        existing = {h.row_key: h for h in
                    db.query(PoultryRateHistory)
                      .filter(PoultryRateHistory.row_key.in_(keys)).all()}
        for (d, paise), key in zip(series, keys):
            prior = existing.get(key)
            if prior is None:
                db.add(PoultryRateHistory(
                    zone_slug=slug, section=row["section"], paise=paise,
                    rate_date=d, row_key=key))
                written += 1
            elif prior.paise != paise:
                prior.paise, prior.section = paise, row["section"]
                revised += 1

        last_date, last_paise = series[-1]
        prev_paise = series[-2][1] if len(series) > 1 else None
        spark = ",".join(str(p) for _, p in series[-SPARK_DAYS:])

        snap = db.query(PoultryRate).filter(PoultryRate.zone_slug == slug).first()
        if snap is None:
            db.add(PoultryRate(
                zone_slug=slug, zone_name=row["zone"], section=row["section"],
                paise=last_paise, rate_date=last_date, prev_paise=prev_paise,
                change_paise=(last_paise - prev_paise) if prev_paise else None,
                spark=spark, month_avg=row.get("avg")))
        elif last_date >= snap.rate_date:
            snap.zone_name = row["zone"]
            snap.section = row["section"]
            snap.paise = last_paise
            snap.rate_date = last_date
            snap.prev_paise = prev_paise
            snap.change_paise = (last_paise - prev_paise) if prev_paise else None
            snap.spark = spark
            snap.month_avg = row.get("avg")

    db.commit()
    return {"month": f"{year:04d}-{month:02d}", "zones": len(zones_seen),
            "written": written, "revised": revised}


def trim_history(db) -> int:
    """Drop history past the retention ceiling. Returns rows deleted."""
    cutoff = date.today() - timedelta(days=POULTRY_HISTORY_DAYS)
    n = (db.query(PoultryRateHistory)
           .filter(PoultryRateHistory.rate_date < cutoff)
           .delete(synchronize_session=False))
    db.commit()
    return n


# ── reading ─────────────────────────────────────────────────

def _decorate(snap: PoultryRate) -> dict:
    meta = zone_meta(snap.zone_name)
    return {
        "slug": snap.zone_slug, "necc_name": snap.zone_name,
        "hi": meta["hi"], "state_hi": meta["state_hi"], "centre": meta["centre"],
        "section": snap.section, "paise": snap.paise, "date": snap.rate_date,
        "prev": snap.prev_paise, "change": snap.change_paise,
        "month_avg": snap.month_avg,
        "spark": [int(x) for x in (snap.spark or "").split(",") if x.strip().isdigit()],
    }


def latest(db, section: str = "") -> list[dict]:
    """Every zone's current rate, dearest first. `section` filters to
    "necc" or "prevailing"; empty returns both."""
    q = db.query(PoultryRate)
    if section:
        q = q.filter(PoultryRate.section == section)
    return sorted((_decorate(s) for s in q.all()),
                  key=lambda r: -r["paise"])


def zone(db, slug: str) -> dict | None:
    snap = db.query(PoultryRate).filter(PoultryRate.zone_slug == slug).first()
    return _decorate(snap) if snap else None


def series(db, slug: str, days: int = 30) -> list[dict]:
    """The last `days` reported rates for one zone, oldest first."""
    cutoff = date.today() - timedelta(days=days)
    rows = (db.query(PoultryRateHistory)
              .filter(PoultryRateHistory.zone_slug == slug,
                      PoultryRateHistory.rate_date >= cutoff)
              .order_by(PoultryRateHistory.rate_date).all())
    return [{"date": r.rate_date, "paise": r.paise} for r in rows]


def last_year(db, slug: str, on: date, window: int = 5) -> dict | None:
    """The same zone around this date a year ago — the "क्या पिछले साल भी इतना
    था" answer. A window because a single calendar day may not have reported;
    None when history does not reach back that far, which is the honest answer
    in the section's first year rather than a comparison against nothing."""
    target = on - timedelta(days=365)
    rows = (db.query(PoultryRateHistory)
              .filter(PoultryRateHistory.zone_slug == slug,
                      PoultryRateHistory.rate_date >= target - timedelta(days=window),
                      PoultryRateHistory.rate_date <= target + timedelta(days=window))
              .all())
    if not rows:
        return None
    paise = round(sum(r.paise for r in rows) / len(rows))
    return {"paise": paise, "date": target, "n": len(rows)}


def updated(db) -> date | None:
    """The most recent date ANY zone reported — the section's real dateModified.
    Never today's date, never render time (see bhav.py::_doc)."""
    return db.query(func.max(PoultryRate.rate_date)).scalar()


def coverage(db) -> dict:
    """Small status read for /admin and the health page."""
    return {
        "zones": db.query(func.count(PoultryRate.zone_slug)).scalar() or 0,
        "history_rows": db.query(func.count(PoultryRateHistory.id)).scalar() or 0,
        "latest": updated(db),
        "oldest": db.query(func.min(PoultryRateHistory.rate_date)).scalar(),
    }


# ── formatting (one place, so no page invents its own) ───────

def rupees(paise: int) -> str:
    """550 -> '5.50' — rupees per egg, always two decimals."""
    return f"{paise / 100:.2f}"


def per_hundred(paise: int) -> str:
    """550 -> '550' — rupees per 100 eggs, the way the trade quotes it.
    Numerically the same integer; named so no caller has to remember why."""
    return f"{paise:,}"

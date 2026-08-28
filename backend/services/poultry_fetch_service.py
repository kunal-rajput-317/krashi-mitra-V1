# ============================================================
# backend/services/poultry_fetch_service.py
# अंडे का रेट — the daily fetch, and the one-time history backfill.
#
# The only place that both talks to e2necc.com and opens a DB session. The
# parser (poultry_necc) knows nothing about Postgres; the store (poultry)
# knows nothing about HTTP; this joins them and owns the retry/failure policy.
#
# A FAILED FETCH IS NOT AN OUTAGE. Every page reads Postgres, so a NECC that
# is down, slow or reshaped leaves yesterday's rates on the pages with an
# honest date on them. Nothing here raises into a request path, and nothing
# here empties a table it could not refill.
#
# THE BACKFILL RUNS ONCE, NOT EVERY BOOT. One request returns a whole month,
# so 14 requests buy fourteen months — enough for the zone pages' trend AND
# the "इस समय पिछले साल" comparison to be true on the day the section ships,
# instead of a year later. It is gated on history actually being empty, so a
# restarting dyno re-fetches nothing.
# ============================================================

import logging
import time
from datetime import date

from backend.database.db import SessionLocal, PoultryRateHistory
from backend.services import poultry, poultry_necc

log = logging.getLogger("krishi.poultry_fetch")

# 14 = twelve months of trend + the two months either side that make a
# year-ago comparison land on real reported days rather than a gap.
BACKFILL_MONTHS = 14

# Courtesy gap between backfill requests. The daily job makes ONE request, so
# this only ever applies to the one-time catch-up.
BACKFILL_PAUSE_S = 2.0


def _months_back(n: int) -> list[tuple[int, int]]:
    """[(month, year)] for the last n months, oldest first."""
    today = date.today()
    out = []
    m, y = today.month, today.year
    for _ in range(n):
        out.append((m, y))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(out))


def fetch_and_store(month: int = 0, year: int = 0) -> dict:
    """Fetch one month (default: the current one) and store it.

    Returns a summary dict; on failure returns {"ok": False, "error": ...}
    rather than raising, because every caller is a scheduler job whose only
    sensible response to a bad upstream day is to try again tomorrow.
    """
    try:
        sheet = poultry_necc.fetch_month(month, year)
    except Exception as e:
        log.warning("egg rate fetch failed (keeping stored rates): %s", e)
        return {"ok": False, "error": str(e)}

    db = SessionLocal()
    try:
        summary = poultry.store_sheet(db, sheet)
        summary["trimmed"] = poultry.trim_history(db)
        summary["ok"] = True
        log.info("egg rates %s | %d zones | %d new, %d revised",
                 summary["month"], summary["zones"],
                 summary["written"], summary["revised"])
        return summary
    except Exception as e:
        db.rollback()
        log.error("egg rate store failed: %s", e)
        return {"ok": False, "error": str(e)}
    finally:
        db.close()


def history_is_empty() -> bool:
    db = SessionLocal()
    try:
        return db.query(PoultryRateHistory.id).first() is None
    finally:
        db.close()


def backfill(months: int = BACKFILL_MONTHS) -> dict:
    """Fetch the last `months` sheets, oldest first.

    Oldest first on purpose: store_sheet only advances the snapshot when a
    sheet's newest date is at least as recent as the stored one, so finishing
    on the current month guarantees the headline number is today's.
    """
    done, failed = [], []
    for i, (m, y) in enumerate(_months_back(months)):
        summary = fetch_and_store(m, y)
        (done if summary.get("ok") else failed).append(f"{y:04d}-{m:02d}")
        if i < months - 1:
            time.sleep(BACKFILL_PAUSE_S)
    log.info("egg rate backfill done | %d months stored, %d failed",
             len(done), len(failed))
    return {"stored": done, "failed": failed}


if __name__ == "__main__":  # python -m backend.services.poultry_fetch_service
    logging.basicConfig(level=logging.INFO)
    print(backfill() if history_is_empty() else fetch_and_store())

"""One mandi fetch, run from outside Render (.github/workflows/mandi-fetch.yml).

Since the data.gov.in outage (25 Sep 2026) api.data.gov.in refuses
connections from Render ("[Errno 113] No route to host", "[Errno 111]
Connection refused", seen 14 Oct on a fresh Render account too) while the
same requests work from India and from abroad. This runs the very same
fetch_and_store into the same database. Render then notices the newer rows
(mandi_scheduler._pick_up_outside_fetch), reloads /bhav's in-memory copy and
sends the alerts. Alerts and IndexNow stay on Render; this job only stores
prices and builds seasonality summaries.

Needs DATABASE_URL and DATA_GOV_API_KEY in the environment.
"""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def main() -> int:
    for k in ("DATABASE_URL", "DATA_GOV_API_KEY"):
        if not os.getenv(k, "").strip():
            print(f"{k} is not set (add it as a GitHub Actions secret)")
            return 1

    from backend.services.mandi_fetch_service import fetch_and_store

    summary = fetch_and_store()
    print("summary:", summary)

    # Render skips its own drain when its fetch finds the API down, so the
    # season queue would never move while Render is blocked.
    if summary.get("fetched") and not summary.get("api_down"):
        try:
            from backend.services.mandi_season_service import drain_queue
            drain_queue()
        except Exception as e:
            print(f"season summary drain failed (non-fatal): {e}")

    # A down API is data.gov.in's outage, not this job's failure: the monitor
    # workflow already alerts on stale prices, so don't email six times a day.
    return 0


if __name__ == "__main__":
    sys.exit(main())

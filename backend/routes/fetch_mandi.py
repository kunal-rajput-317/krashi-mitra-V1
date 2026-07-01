# ============================================================
# Krashi_mitra — Mandi Price Fetcher (manual trigger)
# ------------------------------------------------------------
# DEPRECATED as a standalone implementation. The real pipeline
# now lives in backend/services/mandi_fetch_service.py and runs
# automatically via backend/services/mandi_scheduler.py (daily).
#
# This file is kept as a convenience wrapper so the old workflow
#   python -m backend.routes.fetch_mandi
# still works for an on-demand fetch.
# ============================================================

from backend.services.mandi_fetch_service import fetch_and_store

if __name__ == "__main__":
    summary = fetch_and_store()
    print(f"\n✅ Done: {summary}")

# ============================================================
# KrashiMitra — read the /bhav district description test
#
#   python tools/desc_test_report.py              # from START + 7 days to today - 3
#   python tools/desc_test_report.py --from 2026-10-05 --to 2026-10-19
#
# Group A's description quotes "औसत ₹X/क्विंटल"; group B's does not
# (backend/utils/desc_test.py). Both are compared inside the same position
# band, because CTR depends on position far more than on any snippet, and a
# few large pages can sit in either half by chance.
#
# Google needs to recrawl a page before its new description shows, so the
# default window opens a week after START. Only final Search Console days are
# used (the last ~3 days keep changing). Never put the numbers this prints
# into the repo: it is public.
# ============================================================

import argparse
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from backend.services import gsc_service  # noqa: E402
from backend.utils import desc_test  # noqa: E402

BANDS = [("1-3", 0, 3.5), ("4-6", 3.5, 6.5), ("7-10", 6.5, 10.5), ("11+", 10.5, 1e9)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start",
                    default=(date.fromisoformat(desc_test.START) + timedelta(days=7)).isoformat())
    ap.add_argument("--to", dest="end", default=(date.today() - timedelta(days=3)).isoformat())
    a = ap.parse_args()
    if a.start > a.end:
        print(f"Too early: the window {a.start} → {a.end} is empty. "
              f"Run again after {(date.fromisoformat(a.start) + timedelta(days=3)).isoformat()}.")
        return 0
    if not gsc_service.configured():
        print("GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 is not set in .env")
        return 1

    rows = gsc_service.search_analytics(
        a.start, a.end, ["page"], row_limit=100000, data_state="final",
        filters=[{"dimension": "page", "operator": "contains", "expression": "/bhav/"}])

    agg = defaultdict(lambda: [0, 0, 0])          # (group, band) → clicks, impr, pages
    for r in rows:
        path = r["page"].split("krashimitra.in", 1)[-1].split("?")[0].strip("/").split("/")
        # District pages only: /bhav/<crop>/<state>/<district>, not /bhav/rajya/…
        if len(path) != 4 or path[1] in ("rajya", "api", "mandi"):
            continue
        g = desc_test.variant(path[1], path[2], path[3])
        band = next(n for n, lo, hi in BANDS if lo <= r["position"] < hi)
        x = agg[(g, band)]
        x[0] += r["clicks"]; x[1] += r["impressions"]; x[2] += 1

    print(f"District description test, {a.start} → {a.end} (final Search Console days)")
    print("A = price in the description, B = no price\n")
    print(f"{'position':>9} | {'A clicks/impr':>16} {'A CTR':>7} | {'B clicks/impr':>16} {'B CTR':>7}")
    for band, _, _ in BANDS:
        ca, ia, _ = agg[("A", band)]
        cb, ib, _ = agg[("B", band)]
        fa = f"{100 * ca / ia:.2f}%" if ia else "—"
        fb = f"{100 * cb / ib:.2f}%" if ib else "—"
        print(f"{band:>9} | {f'{ca}/{ia}':>16} {fa:>7} | {f'{cb}/{ib}':>16} {fb:>7}")
    print("\nRead a band only when both halves have a few thousand impressions in it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# ============================================================
# KrashiMitra — Search Console performance report
#
# backend/services/gsc_service.py already talks to Google as the service
# account, but only ever asked it crawl questions ("when did you last fetch
# this /bhav page?"). This pulls the other half — the Performance report:
# which queries and pages actually earn impressions and clicks.
#
# It exists because the site's stated bottleneck is CTR, not indexation
# (~0.5% site-wide), and you cannot fix a CTR problem you can only see as a
# single site-wide average. The interesting rows are the ones an average
# hides: pages ranking 5-20 that would earn clicks from a nudge, and pages
# already ranking well whose title/description are losing the click.
#
#   python tools/gsc_report.py                      # last 28d vs previous 28d
#   python tools/gsc_report.py --days 90
#   python tools/gsc_report.py --page /bhav         # only URLs containing this
#   python tools/gsc_report.py --json               # full rows, machine-readable
#
# First-time setup, so the key never passes through a chat window or a shell
# history entry — download the service-account JSON from Google Cloud, then:
#
#   python tools/gsc_report.py --install-key ~/Downloads/krashimitra-xxxx.json
#
# which base64s it into .env as GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64, the
# same variable name Render already uses. .env is gitignored.
#
# Raw rows are written to scratch/ (also gitignored) so a later run can diff
# against them without re-querying — Google's Search Analytics quota is
# generous but not free, and the data for a given past date never changes.
# ============================================================

import argparse
import base64
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

OUT_DIR = ROOT / "scratch" / "gsc"

# Position bands. 1-3 owns the answer, 4-10 is on page one but below the
# fold, 11-20 is page two — the band where a ranking improvement converts to
# real clicks, and so the band worth spending effort on.
BANDS = [("1-3", 0, 3.5), ("4-10", 3.5, 10.5), ("11-20", 10.5, 20.5),
         ("21+", 20.5, 1e9)]


def install_key(path: str) -> int:
    """Write the service-account JSON into .env as base64, in place."""
    src = Path(path).expanduser()
    if not src.is_file():
        print(f"no such file: {src}")
        return 1
    try:
        raw = src.read_bytes()
        sa = json.loads(raw)
    except Exception as e:
        print(f"not readable as JSON: {e}")
        return 1
    if sa.get("type") != "service_account" or "private_key" not in sa:
        print("that JSON is not a service-account key (no private_key)")
        return 1

    blob = base64.b64encode(raw).decode()
    env = ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    key = "GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64"
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={blob}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"installed key for {sa.get('client_email')} into {env}")
    print("that account must be a user on the krashimitra.in Search Console "
          "property (it already is, if the daily recrawl sweep is running)")
    return 0


def _band(pos: float) -> str:
    for name, lo, hi in BANDS:
        if lo <= pos < hi:
            return name
    return "21+"


def _section(url: str) -> str:
    """Group a URL into the page family it belongs to, so a report over
    14k /bhav URLs still says something at a glance."""
    p = url.split("krashimitra.in", 1)[-1] or "/"
    for prefix in ("/bhav/net-price", "/bhav", "/naksha", "/map", "/articles",
                   "/product", "/dukanlisting", "/sawal"):
        if p == prefix or p.startswith(prefix + "/"):
            return prefix
    return p if p.count("/") <= 1 else "/" + p.split("/")[1]


def _fmt(rows, cols, widths):
    print("  " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(str(v)[:w].ljust(w) for v, w in zip(r, widths)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install-key", metavar="PATH")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--page", default="", help="substring filter on URL")
    ap.add_argument("--json", action="store_true", help="dump rows as JSON")
    args = ap.parse_args()

    if args.install_key:
        return install_key(args.install_key)

    from backend.services import gsc_service as gsc
    if not gsc.configured():
        print("GOOGLE_SEARCH_CONSOLE_CREDENTIALS_B64 is not set locally.\n"
              "It is set on Render (the daily sweep uses it); to read the "
              "performance data from here, download the service-account key "
              "and run:\n\n  python tools/gsc_report.py --install-key <file>.json")
        return 2

    # Google finalises Search Analytics ~2 days behind; asking for yesterday
    # returns a number that will still change, which would make every
    # period-over-period comparison lie.
    end = date.today() - timedelta(days=3)
    start = end - timedelta(days=args.days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=args.days - 1)

    filters = ([{"dimension": "page", "operator": "contains", "expression": args.page}]
               if args.page else None)

    def pull(s, e, dims):
        return gsc.search_analytics(s.isoformat(), e.isoformat(),
                                    dimensions=dims, filters=filters)

    print(f"\nkrashimitra.in — Search Console")
    print(f"period   {start} → {end}  ({args.days} days)")
    print(f"compared {prev_start} → {prev_end}")
    if args.page:
        print(f"filter   page contains '{args.page}'")

    queries = pull(start, end, ["query"])
    pages = pull(start, end, ["page"])
    prev_pages = pull(prev_start, prev_end, ["page"])
    pairs = pull(start, end, ["page", "query"])

    if not queries and not pages:
        print("\nno rows returned — check that the service account still has "
              "access to the property, and that GSC_SITE_URL matches its "
              "exact registered form")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = f"{start}_{end}"
    for name, rows in (("queries", queries), ("pages", pages), ("pairs", pairs)):
        (OUT_DIR / f"{name}_{stamp}.json").write_text(
            json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps({"queries": queries, "pages": pages, "pairs": pairs},
                         ensure_ascii=False, indent=2))
        return 0

    # ── totals ────────────────────────────────────────────────
    def tot(rows):
        c = sum(r["clicks"] for r in rows)
        i = sum(r["impressions"] for r in rows)
        return c, i, (c / i * 100 if i else 0)

    c, i, ctr = tot(pages)
    pc, pi, pctr = tot(prev_pages)

    def delta(now, before):
        if not before:
            return "  —"
        d = (now - before) / before * 100
        return f"{d:+.0f}%"

    print(f"\n── totals ──")
    print(f"  clicks       {c:>8,}   {delta(c, pc)}")
    print(f"  impressions  {i:>8,}   {delta(i, pi)}")
    print(f"  CTR          {ctr:>7.2f}%   (was {pctr:.2f}%)")
    print(f"  clicks/day   {c/args.days:>8.1f}")

    # ── where impressions live, by page family ────────────────
    fam = defaultdict(lambda: [0, 0, 0])   # clicks, impressions, urls
    for r in pages:
        f = fam[_section(r["page"])]
        f[0] += r["clicks"]; f[1] += r["impressions"]; f[2] += 1
    rows = sorted(fam.items(), key=lambda kv: -kv[1][1])[:12]
    print(f"\n── by page family ── ({len(pages):,} URLs earned an impression)")
    _fmt([[k, f"{v[2]:,}", f"{v[0]:,}", f"{v[1]:,}",
           f"{v[0]/v[1]*100:.2f}%" if v[1] else "—"] for k, v in rows],
         ["family", "urls", "clicks", "impr", "CTR"], [22, 7, 8, 9, 7])

    # ── the CTR opportunity: seen a lot, clicked rarely ───────
    # Ranking in the top 10 and still not being clicked is a title/snippet
    # problem, not a ranking problem — the cheapest traffic in the report.
    opp = [r for r in pages
           if r["impressions"] >= 200 and r["position"] <= 10.5
           and r["ctr"] < 0.02]
    opp.sort(key=lambda r: -r["impressions"])
    print(f"\n── top-10 rankings losing the click ── ({len(opp)} pages, "
          f"{sum(r['impressions'] for r in opp):,} impressions)")
    _fmt([[r["page"].split("krashimitra.in")[-1], f"{r['impressions']:,}",
           r["clicks"], f"{r['ctr']*100:.2f}%", f"{r['position']:.1f}"]
          for r in opp[:20]],
         ["page", "impr", "clicks", "CTR", "pos"], [46, 8, 7, 7, 5])

    # ── the ranking opportunity: page two ─────────────────────
    near = [r for r in pages if 10.5 < r["position"] <= 20.5
            and r["impressions"] >= 100]
    near.sort(key=lambda r: -r["impressions"])
    print(f"\n── page two (pos 11-20) ── ({len(near)} pages, "
          f"{sum(r['impressions'] for r in near):,} impressions, "
          f"{sum(r['clicks'] for r in near):,} clicks)")
    _fmt([[r["page"].split("krashimitra.in")[-1], f"{r['impressions']:,}",
           r["clicks"], f"{r['position']:.1f}"] for r in near[:20]],
         ["page", "impr", "clicks", "pos"], [50, 8, 7, 5])

    # ── position bands ────────────────────────────────────────
    band = defaultdict(lambda: [0, 0, 0])
    for r in pages:
        b = band[_band(r["position"])]
        b[0] += r["clicks"]; b[1] += r["impressions"]; b[2] += 1
    print(f"\n── position bands ──")
    _fmt([[n, f"{band[n][2]:,}", f"{band[n][0]:,}", f"{band[n][1]:,}",
           f"{band[n][0]/band[n][1]*100:.2f}%" if band[n][1] else "—"]
          for n, _, _ in BANDS],
         ["band", "urls", "clicks", "impr", "CTR"], [6, 7, 8, 9, 7])

    # ── queries ───────────────────────────────────────────────
    qs = sorted(queries, key=lambda r: -r["impressions"])
    print(f"\n── top queries by impressions ── ({len(queries):,} queries)")
    _fmt([[r["query"], f"{r['impressions']:,}", r["clicks"],
           f"{r['ctr']*100:.1f}%", f"{r['position']:.1f}"] for r in qs[:25]],
         ["query", "impr", "clicks", "CTR", "pos"], [42, 8, 7, 7, 5])

    zero = [r for r in qs if r["clicks"] == 0 and r["impressions"] >= 100]
    print(f"\n── high-impression queries with ZERO clicks ── "
          f"({len(zero)} queries, {sum(r['impressions'] for r in zero):,} impressions)")
    _fmt([[r["query"], f"{r['impressions']:,}", f"{r['position']:.1f}"]
          for r in zero[:25]],
         ["query", "impr", "pos"], [52, 8, 5])

    # ── movers ────────────────────────────────────────────────
    before = {r["page"]: r for r in prev_pages}
    moved = []
    for r in pages:
        b = before.get(r["page"])
        if b and (r["impressions"] + b["impressions"]) >= 300:
            moved.append((r["impressions"] - b["impressions"], r, b))
    moved.sort(key=lambda t: t[0])
    print(f"\n── biggest impression losses vs previous {args.days}d ──")
    _fmt([[r["page"].split("krashimitra.in")[-1], f"{d:+,}",
           f"{b['position']:.1f}→{r['position']:.1f}"] for d, r, b in moved[:12]],
         ["page", "impr Δ", "pos"], [48, 10, 12])
    print(f"\n── biggest impression gains ──")
    _fmt([[r["page"].split("krashimitra.in")[-1], f"{d:+,}",
           f"{b['position']:.1f}→{r['position']:.1f}"]
          for d, r, b in reversed(moved[-12:])],
         ["page", "impr Δ", "pos"], [48, 10, 12])

    print(f"\nraw rows → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

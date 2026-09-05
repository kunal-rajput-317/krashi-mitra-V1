"""One command that answers: is the site about to stop?

Every outage this project has actually had shares one property - the homepage
stayed green while the site was broken. krashimitra.in serves its static
homepage from Netlify, so Render can be renamed, suspended, out of bandwidth,
or the database can go read-only, and the page a person checks first still
returns 200. That is why each of these was found late:

  Render renamed the subdomain  (3x)   every proxied route 404s, homepage fine
  Render bandwidth suspended    17 Aug  x-render-routing: suspend-by-user
  Netlify quota exceeded        11 Aug  usage_exceeded 503 on every URL
  Neon flipped read-only        --      all writes 500, every read looks fine
  gzip silently off             --      Hindi pages cost 5.6x the bandwidth

This checks all of them from the outside and exits non-zero if anything
CRITICAL is wrong, so it can be a workflow step rather than something to
remember.

    python tools/preflight.py           # network checks only (fast, no env)
    python tools/preflight.py --db      # also prove the database can WRITE
    python tools/preflight.py --quiet   # print only the problems

It reads config/backend-origin.txt for the backend address, so it takes no
arguments and cannot go stale the way a hardcoded URL in a doc does.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

SITE = "https://krashimitra.in"
UA = ("Mozilla/5.0 (Linux; Android 12; Pixel 5) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36")
TIMEOUT = 30

OK, WARN, CRIT, SKIP = "ok", "warn", "critical", "skip"
MARK = {OK: "  OK  ", WARN: " WARN ", CRIT: " FAIL ", SKIP: " SKIP "}

results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> str:
    results.append((status, name, detail))
    return status


def fetch(url: str, head: bool = False, gzip_ok: bool = False, timeout: int = TIMEOUT):
    """Return (status, headers, body) without raising on an HTTP error code."""
    req = urllib.request.Request(url, method="HEAD" if head else "GET")
    req.add_header("User-Agent", UA)
    if gzip_ok:
        req.add_header("Accept-Encoding", "gzip")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = b"" if head else r.read(200_000)
            return r.status, {k.lower(): v for k, v in r.headers.items()}, raw
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        return e.code, hdrs, (b"" if head else e.read(20_000))
    except Exception as e:                      # DNS, TLS, timeout, refused
        return None, {}, str(e).encode()


# ---------------------------------------------------------------- checks ----

def check_origin_agreement() -> str:
    """The URL has one owner. When a copy drifts, the site goes down quietly."""
    try:
        from tools.set_backend_origin import configured_origin, files, scan
    except Exception as e:
        return record(SKIP, "backend URL is consistent", f"cannot import tool: {e}")

    want = configured_origin()
    stale, _ = scan(files(), want)
    if stale:
        where = ", ".join(f"{p.relative_to(REPO)} ({n}x)" for p, n in stale.items())
        return record(CRIT, "backend URL is consistent",
                      f"config says {want} but these disagree: {where}"
                      "\n         fix: python tools/set_backend_origin.py <live-url>")
    return record(OK, "backend URL is consistent", want)


def check_backend_alive(origin: str) -> str:
    # A free-tier Render service scales to zero, and the first request after
    # that has to boot the container. Measured 5 Sept: the same host timed out
    # at 25s cold and answered in 0.7s once warm. Without this retry the check
    # reports a dead backend whenever nobody has visited recently, which is
    # exactly the false alarm that makes people stop trusting a monitor.
    status, _, body = fetch(f"{origin}/health", timeout=90)
    if status is None:
        status, _, body = fetch(f"{origin}/health", timeout=90)
    if status is None:
        return record(CRIT, "backend responds",
                      f"{origin} unreachable - {body.decode(errors='replace')[:80]}"
                      "\n         the Render subdomain has probably changed again")
    if status != 200:
        return record(CRIT, "backend responds", f"{origin}/health -> HTTP {status}")
    return record(OK, "backend responds", f"{origin} 200")


def check_netlify() -> str:
    status, _, body = fetch(SITE)
    if status is None:
        return record(CRIT, "static host (Netlify) serving",
                      body.decode(errors="replace")[:90])
    if status == 503 or b"usage_exceeded" in body.lower():
        return record(CRIT, "static host (Netlify) serving",
                      "usage_exceeded - the Netlify plan quota is spent")
    if status != 200:
        return record(CRIT, "static host (Netlify) serving", f"HTTP {status}")
    return record(OK, "static host (Netlify) serving", "HTTP 200")


def check_proxied_route() -> str:
    """The check a green homepage cannot fake."""
    status, hdrs, body = fetch(f"{SITE}/bhav")
    routing = hdrs.get("x-render-routing", "")
    if "suspend" in routing:
        return record(CRIT, "proxied route (/bhav) is live",
                      f"x-render-routing: {routing} - Render quota is exhausted")
    if status is None:
        return record(CRIT, "proxied route (/bhav) is live",
                      body.decode(errors="replace")[:90])
    if status != 200:
        return record(CRIT, "proxied route (/bhav) is live",
                      f"HTTP {status} - Netlify is serving this, Render is not")
    return record(OK, "proxied route (/bhav) is live",
                  f"HTTP 200 via {routing or 'render'}")


def check_gzip() -> str:
    """Hindi pages are 5.6x bigger uncompressed. This blew the bandwidth cap once."""
    status, hdrs, _ = fetch(f"{SITE}/bhav", gzip_ok=True)
    enc = (hdrs.get("content-encoding") or "").lower()
    if status != 200:
        return record(SKIP, "compression is on", f"could not fetch (HTTP {status})")
    if enc not in ("gzip", "br", "zstd", "deflate"):
        return record(CRIT, "compression is on",
                      "no content-encoding - every Hindi page costs 5.6x the bandwidth")
    return record(OK, "compression is on", enc)


def check_ads_txt() -> str:
    status, hdrs, body = fetch(f"{SITE}/ads.txt")
    ctype = (hdrs.get("content-type") or "").split(";")[0]
    # A missing static file on this site returns 200 with the HTML shell, so the
    # status code proves nothing - the content type is the real test.
    if status != 200 or "html" in ctype:
        return record(WARN, "ads.txt is served",
                      f"HTTP {status}, content-type {ctype or '?'} "
                      "- AdSense cannot verify the site")
    if b"pub-" not in body:
        return record(WARN, "ads.txt is served", "served but contains no publisher line")
    return record(OK, "ads.txt is served", ctype)


def check_db_writable() -> str:
    """Neon flips read-only under quota: reads look perfect, every write 500s."""
    try:
        from backend.services.db_health_service import check as db_check
    except Exception as e:
        return record(SKIP, "database accepts writes", f"cannot import: {type(e).__name__}")
    try:
        res = db_check() or {}
    except Exception as e:
        return record(CRIT, "database accepts writes", f"{type(e).__name__}: {e}")
    ok = res.get("ok", res.get("writable", res.get("can_write")))
    if ok is False:
        return record(CRIT, "database accepts writes",
                      str(res.get("error") or res)[:150] +
                      "\n         Neon is read-only - check the quota, not the code")
    if ok is None:
        return record(WARN, "database accepts writes", f"unclear result: {str(res)[:120]}")
    return record(OK, "database accepts writes", "write canary succeeded")


# ------------------------------------------------------------------ main ----

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", action="store_true",
                    help="also run the database write canary (needs DATABASE_URL)")
    ap.add_argument("--quiet", action="store_true", help="print only problems")
    args = ap.parse_args()

    try:
        from tools.set_backend_origin import configured_origin
        origin = configured_origin()
    except Exception:
        origin = ""

    check_origin_agreement()
    if origin:
        check_backend_alive(origin)
    check_netlify()
    check_proxied_route()
    check_gzip()
    check_ads_txt()
    if args.db:
        check_db_writable()

    worst = (CRIT if any(s == CRIT for s, _, _ in results)
             else WARN if any(s == WARN for s, _, _ in results)
             else OK)

    print()
    for status, name, detail in results:
        if args.quiet and status == OK:
            continue
        print(f"[{MARK[status]}] {name}" + (f"\n         {detail}" if detail else ""))
    print()
    if worst == CRIT:
        print("SOMETHING IS BROKEN. The homepage may still look fine - it always does.")
        # The admin panel runs on Render, so when Render is the thing that is
        # down, the Book goes with it. Point at the offline copy here, in the
        # output someone is already staring at, rather than assume they will
        # remember a command they last needed two months ago.
        print("What to do next, offline (no server, no network):")
        print("    python tools/book.py --critical")
        print("    python tools/book.py <word>       # search the whole Book")
    elif worst == WARN:
        print("Site is up; the warnings above are worth a look.")
    else:
        print("All clear.")
    return 1 if worst == CRIT else 0


if __name__ == "__main__":
    raise SystemExit(main())

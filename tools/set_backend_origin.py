#!/usr/bin/env python3
"""
Point the whole site at a new backend URL.

Render reassigns the .onrender.com subdomain whenever the service is recreated.
It has happened twice, and each time the URL had to be found and replaced in 23
files while the site was down — 26 lines of frontend/_redirects alone. Worse,
the site does not look down: krashimitra.in keeps serving its static homepage
off Netlify while every proxied route 404s, so the rename can go unnoticed for
days.

    python tools/set_backend_origin.py https://krashi-mitra-v1-muup.onrender.com
    python tools/set_backend_origin.py --check     # verify, write nothing
    python tools/set_backend_origin.py             # re-sync from the config file

Python and the GitHub workflows read config/backend-origin.txt directly and
need no rewriting. This tool exists for the two places that genuinely cannot
read a file at request time:

  * frontend/_redirects — Netlify proxy rules; the format has no variables
  * the browser JS/HTML — api-config.js sets window.KRASHIMITRA_API_BASE
    synchronously before any page script runs, so it cannot await a fetch

tests/test_backend_origin.py runs --check, so a file left behind fails the
build instead of quietly 404ing in production.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "backend-origin.txt"

# Any Render host, so a rewrite catches whatever the previous name happened to
# be without anyone having to remember it.
HOST_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.onrender\.com")

# Everything that carries the URL as a literal. Directories are walked with the
# given suffixes. Python is absent on purpose — it imports backend/origin.py.
TARGETS: list[str] = [
    "frontend/_redirects",
    "frontend/api-config.js",
    "frontend/krashibook.js",
    "frontend/location.js",
    "frontend/main.js",
    "frontend/404.html",
    "frontend/index.html",
    "frontend/chat.html",
    "frontend/khoj.html",
    "frontend/login.html",
    "frontend/profile.html",
    "frontend/shop.html",
    "frontend/weather.html",
    "frontend/meri_fasal.html",
    "frontend/krashi_bajar.html",
    "frontend/sarkari_yojana.html",
    "frontend/articles/index.html",
    "frontend/dukanlisting/index.html",
    "backend/data/krashimitra_book.json",
]

# seed_cache.py is deliberately excluded: its `https://your-app.onrender.com` is
# a placeholder in --help text, not a live URL, and rewriting it would turn an
# example into a specific host that reads like an instruction.
IGNORE = {"seed_cache.py"}


def configured_origin() -> str:
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("http"):
            return line.rstrip("/")
    sys.exit(f"error: no http line in {CONFIG.relative_to(REPO)}")


def set_configured_origin(url: str) -> None:
    """Rewrite only the value line, so the file's explanation survives."""
    out, done = [], False
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if not done and line.strip().startswith("http"):
            out.append(url)
            done = True
        else:
            out.append(line)
    if not done:
        out.append(url)
    CONFIG.write_text("\n".join(out) + "\n", encoding="utf-8")


def files() -> list[Path]:
    found = []
    for rel in TARGETS:
        p = REPO / rel
        if p.is_file() and p.name not in IGNORE:
            found.append(p)
        elif not p.is_file():
            print(f"  ! missing, skipped: {rel}")
    return found


def scan(paths: list[Path], want: str) -> tuple[dict[Path, int], dict[Path, set[str]]]:
    """(files needing a rewrite → count, files → the wrong hosts they carry)."""
    stale, hosts = {}, {}
    for p in paths:
        text = p.read_text(encoding="utf-8")
        bad = {h for h in HOST_RE.findall(text) if h != want}
        if bad:
            stale[p] = sum(text.count(h) for h in bad)
            hosts[p] = bad
    return stale, hosts


def main() -> int:
    # Windows hands a cp1252 stdout to a subprocess, and the ✓/✗ below then
    # raise UnicodeEncodeError *after* the check has already succeeded — the
    # tool exited 1 on a clean tree, and tests/test_backend_origin.py, which
    # shells out to `--check`, failed for that reason alone. A guard that goes
    # red when nothing is wrong is a guard that gets ignored, which is how the
    # first rename went unnoticed for days.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # already-wrapped or non-tty
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="new backend origin, e.g. "
                                           "https://krashi-mitra-v1-muup.onrender.com")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 1; write nothing")
    args = ap.parse_args()

    if args.url and args.check:
        return ap.error("pass a url or --check, not both") or 2

    if args.url:
        url = args.url.strip().rstrip("/")
        if not HOST_RE.fullmatch(url) and not url.startswith("https://"):
            return ap.error(f"{url!r} does not look like an https origin") or 2
        set_configured_origin(url)
        print(f"config/backend-origin.txt → {url}")
    else:
        url = configured_origin()
        print(f"origin: {url}"
              + ("  (checking)" if args.check else "  (re-syncing from config)"))

    paths = files()
    stale, hosts = scan(paths, url)

    if args.check:
        if not stale:
            print(f"✓ all {len(paths)} managed files agree")
            return 0
        print(f"\n✗ {len(stale)} file(s) do not point at {url}:\n")
        for p in sorted(stale):
            print(f"  {p.relative_to(REPO).as_posix():44s} "
                  f"{stale[p]:2d}× {', '.join(sorted(hosts[p]))}")
        print("\nfix: python tools/set_backend_origin.py")
        return 1

    if not stale:
        print(f"✓ nothing to change — all {len(paths)} managed files already agree")
        return 0

    total = 0
    for p in sorted(stale):
        text = p.read_text(encoding="utf-8")
        # Rewrite bytes, not lines. _redirects is columnar and api-config.js has
        # the URL inside a ternary; a line-oriented edit would reflow both.
        new = HOST_RE.sub(url, text)
        p.write_text(new, encoding="utf-8", newline="")
        total += stale[p]
        print(f"  {p.relative_to(REPO).as_posix():44s} {stale[p]:2d}×")
    print(f"\n✓ {total} occurrence(s) in {len(stale)} file(s) → {url}")
    print("  Python and .github/workflows read config/backend-origin.txt "
          "directly — nothing to do there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

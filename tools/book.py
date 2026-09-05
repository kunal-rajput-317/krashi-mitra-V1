"""कृषि मित्र Book, in the terminal — the copy that works when nothing else does.

The Book is served by the admin panel, which runs on Render. So the one
document that tells you how to fix Render is behind Render. Every other page
degrades gracefully; this one takes the instructions down with the thing they
are about. Netlify going down (11 Aug) or Neon going read-only would do it too.

This reader removes that circularity. It reads
backend/data/krashimitra_book.json straight off the disk — no server, no
network, no database, no dependencies beyond the standard library. If you have
the repo, you have the Book. It cannot be down.

    python tools/book.py                  # contents + everything critical
    python tools/book.py commands         # one section (key or title)
    python tools/book.py render           # search every entry for a word
    python tools/book.py --all            # the whole thing
    python tools/book.py --critical       # only what is marked critical

Third fallback, if you do not even have a checkout — the JSON renders readably
on GitHub from a phone:
github.com/kunal-rajput-317/krashi-mitra-V1/blob/main/backend/data/krashimitra_book.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOK = REPO / "backend" / "data" / "krashimitra_book.json"

# Devanagari through a Windows console is the whole ballgame here: the default
# cp1252 codec raises UnicodeEncodeError and the reader dies on its own content.
# Reconfigure to UTF-8 and never let an encoding problem be the reason the
# emergency manual will not open.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WIDTH = min(shutil.get_terminal_size((100, 24)).columns, 100)

# Colour only when a real terminal is attached, so piping to a file stays clean.
_tty = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _tty else s


BOLD = lambda s: c("1", s)          # noqa: E731
DIM = lambda s: c("2", s)           # noqa: E731
RED = lambda s: c("1;31", s)        # noqa: E731
YEL = lambda s: c("1;33", s)        # noqa: E731
CYN = lambda s: c("1;36", s)        # noqa: E731
GRN = lambda s: c("32", s)          # noqa: E731

BADGE = {"critical": RED("[!! ज़रूरी ]"), "warn": YEL("[ ध्यान दें ]")}


def load() -> dict:
    try:
        return json.loads(BOOK.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"Book not found at {BOOK}")
    except ValueError as e:
        # A typo in the JSON must not also cost you the ability to read it.
        sys.exit(f"{BOOK.name} is not valid JSON: {e}\n"
                 f"Open the file directly — the text is still all there.")


def wrap(text: str, indent: str = "     ") -> str:
    out = []
    for para in str(text).split("\n"):
        out.append(textwrap.fill(para, width=WIDTH, initial_indent=indent,
                                 subsequent_indent=indent) if para.strip() else "")
    return "\n".join(out)


def show_entry(e: dict) -> None:
    badge = BADGE.get(e.get("level"), "")
    print(f"\n  {BOLD(e.get('title', e.get('id', '?')))} {badge}")
    cmds = e.get("cmds") or ([e["cmd"]] if e.get("cmd") else [])
    for cmd in cmds:
        print(f"     {GRN('$ ' + str(cmd))}")
    if e.get("body"):
        print(wrap(e["body"]))
    if e.get("why"):
        print(wrap(DIM("क्यों: ") + str(e["why"])))
    link = e.get("link") or {}
    if link.get("label"):
        print(wrap(DIM(f"→ {link['label']} {link.get('url', '')}".strip())))


def show_section(s: dict, entries=None) -> None:
    print("\n" + "=" * WIDTH)
    print(f"{s.get('icon', '')} {BOLD(s.get('title', s['key']))}  {DIM('(' + s['key'] + ')')}")
    if s.get("sub"):
        print(wrap(DIM(s["sub"]), indent="  "))
    print("=" * WIDTH)
    for e in (entries if entries is not None else s.get("entries", [])):
        show_entry(e)


def contents(d: dict) -> None:
    print("\n" + BOLD(d.get("title", "Book")))
    if d.get("sub"):
        print(wrap(DIM(d["sub"]), indent="  "))
    print(DIM(f"\n  स्रोत: {BOOK.relative_to(REPO)} (कोई server नहीं, कोई network नहीं)"))
    print("\n  " + BOLD("पन्ने:"))
    for s in d.get("sections", []):
        n = len(s.get("entries", []))
        crit = sum(1 for e in s.get("entries", []) if e.get("level") == "critical")
        tail = RED(f"  {crit} ज़रूरी") if crit else ""
        print(f"    {s.get('icon', ' ')} {CYN(s['key']):<22} {n:>2} entries{tail}"
              f"   {DIM(s.get('title', ''))}")
    print(DIM(f"\n  एक पन्ना खोलिए:  python tools/book.py <key>"))
    print(DIM(f"  कुछ ढूँढिए:      python tools/book.py <शब्द>"))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="section key, or a word to search for")
    ap.add_argument("--all", action="store_true", help="print the entire book")
    ap.add_argument("--critical", action="store_true", help="only critical entries")
    args = ap.parse_args()

    d = load()
    sections = d.get("sections", [])

    if args.all:
        for s in sections:
            show_section(s)
        return 0

    if args.critical:
        for s in sections:
            hits = [e for e in s.get("entries", []) if e.get("level") == "critical"]
            if hits:
                show_section(s, hits)
        return 0

    if not args.query:
        contents(d)
        print("\n" + "=" * WIDTH)
        print(RED("  सबसे ज़रूरी बातें") + DIM("  (पूरा पढ़ने के लिए: --all)"))
        print("=" * WIDTH)
        for s in sections:
            for e in s.get("entries", []):
                if e.get("level") == "critical":
                    show_entry(e)
        return 0

    q = args.query.lower()

    # An exact section key wins over a text search, so `book.py commands` opens
    # the page rather than finding every entry that says "command".
    for s in sections:
        if q in (s["key"].lower(), s.get("title", "").lower()):
            show_section(s)
            return 0

    hits = [(s, e) for s in sections for e in s.get("entries", [])
            if q in json.dumps(e, ensure_ascii=False).lower()]
    if not hits:
        print(f"\n  '{args.query}' कहीं नहीं मिला। पन्ने देखने के लिए: python tools/book.py")
        return 1

    print(f"\n  {BOLD(str(len(hits)))} जगह मिला — '{args.query}'")
    last = None
    for s, e in hits:
        if s is not last:
            print("\n" + "-" * WIDTH)
            print(f"{s.get('icon', '')} {BOLD(s.get('title', s['key']))}")
            last = s
        show_entry(e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

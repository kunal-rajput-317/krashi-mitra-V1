"""Mint the private media-kit link for one prospect.

    python tools/sponsor_kit_link.py "Coromandel"
    python tools/sponsor_kit_link.py --list-check "coromandel.9f2b..."

WHY THIS EXISTS. /sponsor sells without printing a single traffic figure,
because those figures are a competitive disclosure — published, they tell every
other agri publisher which surfaces work here and how big they are. The numbers
live at /sponsor/kit/<token> instead: unlinked, unindexed, and reachable only
with a signature we generated. This is how that signature gets generated.

ONE LINK PER PROSPECT, ALWAYS. The prospect's name is inside the signature, so
a link sent to one brand cannot be edited into another's, and a hit in the logs
names whoever we gave it to. Do not reuse one link across a mailing list; the
whole point is that a leak is attributable.

TO REVOKE EVERYTHING AT ONCE, rotate KM_SPONSOR_KIT_SECRET on Render. Every
outstanding link dies with it, which is the right blunt instrument for "that
deck got forwarded somewhere it shouldn't have".

With KM_SPONSOR_KIT_SECRET unset there is no valid token at all and the kit
route 404s for everyone — the numbers stay private by default rather than
leaking because a deploy forgot an env var. Set it in the Render dashboard, and
locally in .env, to any long random string.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.services import sponsors  # noqa: E402

SITE = os.getenv("KM_SITE", "https://krashimitra.in")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    if not sponsors.kit_enabled():
        print("KM_SPONSOR_KIT_SECRET is not set, so no link can be issued and\n"
              "/sponsor/kit/* 404s for everyone — which is the safe default,\n"
              "not a bug. Set it in .env locally and in the Render dashboard:\n\n"
              "    KM_SPONSOR_KIT_SECRET=<a long random string>\n")
        return 1

    if argv[0] == "--list-check":
        who = sponsors.kit_verify(argv[1]) if len(argv) > 1 else None
        print(f"valid — issued to: {who}" if who else "NOT a link we issued")
        return 0 if who else 1

    for name in argv:
        token = sponsors.kit_token(name)
        if not token:
            print(f"{name!r}: could not be turned into a slug — use letters and digits")
            continue
        print(f"{name}\n  {SITE}/sponsor/kit/{token}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

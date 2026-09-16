#!/usr/bin/env python3
"""Does R2 actually work? Answer it in one command, before trusting it.

Every R2 failure mode on this site is SILENT. media_store.enabled() returns
False when any one of the five variables is blank, and the caller then writes
to Render's ephemeral disk instead — which looks fine until the next redeploy
deletes a farmer's photo. A missing CORS rule is quieter still: images load
perfectly, and only the WhatsApp share card breaks, because it draws onto a
<canvas> with crossOrigin='anonymous'.

So this does a real round trip: sign, PUT, fetch back over the public domain,
check CORS, delete. No test doubles — a green run here means the real thing
works from this machine with these credentials.

    python tools/check_r2.py
"""

import os
import sys
import time
from pathlib import Path

# The default Windows console is cp1252 and cannot encode the box-drawing
# characters below; without this the script dies before it checks anything.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

import requests

from backend.services import media_store as ms

VARS = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET", "R2_PUBLIC_BASE"]
SITE = "https://krashimitra.in"

ok = "\033[32m✓\033[0m"
no = "\033[31m✗\033[0m"


def main() -> int:
    print("\n── 1. configuration ─────────────────────────────")
    missing = []
    for v in VARS:
        val = os.getenv(v, "").strip()
        if not val:
            missing.append(v)
            print(f"  {no} {v:<24} (blank)")
        else:
            # Never print a secret: show only enough to spot a paste error.
            shown = val if "SECRET" not in v and "KEY_ID" not in v else \
                f"{val[:4]}…{val[-4:]} ({len(val)} chars)"
            print(f"  {ok} {v:<24} {shown}")

    if missing:
        print(f"\n  {no} {len(missing)} variable(s) blank -> media_store.enabled() is False,")
        print("     so uploads fall back to the ephemeral disk. Fill these in .env")
        print("     (local) AND in the Render dashboard (production):")
        for v in missing:
            print(f"       {v}")
        return 1

    base = os.getenv("R2_PUBLIC_BASE", "")
    if base.endswith("/"):
        print(f"  ! R2_PUBLIC_BASE has a trailing slash — harmless, it is stripped.")
    if not base.startswith("https://"):
        print(f"  {no} R2_PUBLIC_BASE must start with https:// — got {base!r}")
        return 1
    if not ms.enabled():
        print(f"  {no} media_store.enabled() is still False. Check for typos in the names.")
        return 1

    key = f"_healthcheck/{int(time.time())}.txt"
    body = b"krashimitra r2 check"

    print("\n── 2. upload (signed PUT) ───────────────────────")
    try:
        url = ms.put(body, key, "text/plain")
        print(f"  {ok} stored -> {url}")
    except Exception as e:
        print(f"  {no} upload failed: {e}")
        print("     Usually: wrong secret, or the token lacks Object Read & Write,")
        print("     or R2_BUCKET does not match the bucket name exactly.")
        return 1

    print("\n── 3. public read over the custom domain ────────")
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and r.content == body:
            print(f"  {ok} fetched back, {len(r.content)} bytes match")
        else:
            print(f"  {no} got HTTP {r.status_code} ({len(r.content)} bytes)")
            print("     The bucket is probably not connected to a public custom")
            print("     domain yet: R2 -> bucket -> Settings -> Connect Domain.")
            ms.delete(url)
            return 1
    except Exception as e:
        print(f"  {no} could not fetch {url}: {e}")
        print("     DNS for the custom domain may not have propagated yet.")
        ms.delete(url)
        return 1

    cc = r.headers.get("cache-control", "")
    print(f"  {ok} cache-control: {cc or '(none)'}")

    print("\n── 4. CORS (the silent one) ─────────────────────")
    try:
        c = requests.get(url, headers={"Origin": SITE}, timeout=20)
        allow = c.headers.get("access-control-allow-origin", "")
        if allow in (SITE, "*"):
            print(f"  {ok} access-control-allow-origin: {allow}")
        else:
            print(f"  {no} no CORS header for {SITE} (got {allow or 'nothing'})")
            print("     Images will still load. The WhatsApp share card will not:")
            print("     it draws onto a <canvas> with crossOrigin='anonymous'.")
            print("     Fix: bucket -> Settings -> CORS policy, allow GET from")
            print(f"     {SITE}")
    except Exception as e:
        print(f"  ! CORS probe failed: {e}")

    print("\n── 5. cleanup ───────────────────────────────────")
    print(f"  {ok} removed test object" if ms.delete(url)
          else f"  ! could not delete {key} — harmless, costs a fraction of a cent")

    print(f"\n{ok} R2 is live. Uploads now survive a redeploy.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

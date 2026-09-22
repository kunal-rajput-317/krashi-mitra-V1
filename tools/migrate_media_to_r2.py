#!/usr/bin/env python3
"""Migrate existing media from Postgres (bazar_media) to Cloudflare R2.

When R2 was deferred due to lack of a payment method, photos were stored in
Postgres (services/media_db.py) under a 60 MB cap. Now that R2 is active:
1. Upload each object from bazar_media to R2 under bazar/<key>
2. Verify the R2 object is publicly reachable
3. Update bazar_posts.media_url to point to the new R2 URL
4. Delete the row from bazar_media to free up Neon Postgres storage

Usage:
    python tools/migrate_media_to_r2.py [--dry-run]
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

import requests

from backend.database.db import BazarMedia, BazarPost, SessionLocal
from backend.services import media_db
from backend.services import media_store as ms

ok = "\033[32m✓\033[0m"
no = "\033[31m✗\033[0m"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate bazar photos from DB to R2")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without uploading or deleting")
    args = parser.parse_args()

    print("\n── 1. checking R2 configuration ─────────────────")
    if not ms.enabled():
        print(f"  {no} R2 is not enabled. Please configure all 5 R2_* variables in .env first:")
        for v in ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE"]:
            val = os.getenv(v, "").strip()
            print(f"     {v}: {'SET' if val else 'BLANK'}")
        print("  Run `python tools/check_r2.py` to verify R2 credentials before migrating.\n")
        return 1

    print(f"  {ok} R2 is enabled and ready.")

    print("\n── 2. scanning Postgres bazar_media ─────────────")
    db = SessionLocal()
    try:
        rows = db.query(BazarMedia).all()
        total_count = len(rows)
        total_bytes = sum(r.bytes or len(r.data) for r in rows)
        print(f"  Found {total_count} media row(s) occupying {total_bytes / 1024:.1f} KB in Postgres.")

        if total_count == 0:
            print("  No rows to migrate. Postgres is already clean!\n")
            return 0

        if args.dry_run:
            print("\n  [DRY RUN] Would migrate the following:")
            for r in rows:
                print(f"    - {r.key} ({r.content_type}, {r.bytes} bytes)")
            return 0

        print("\n── 3. uploading to R2 and updating posts ────────")
        migrated = 0
        failed = 0

        for r in rows:
            key = r.key
            r2_key = f"bazar/{key}"
            print(f"  Migrating {key} ({r.bytes} bytes)...")

            try:
                # 1. Put object to R2
                r2_url = ms.put(r.data, r2_key, r.content_type)
                print(f"    {ok} uploaded -> {r2_url}")

                # 2. Verify public read
                resp = requests.get(r2_url, timeout=15)
                if resp.status_code != 200 or resp.content != r.data:
                    raise RuntimeError(f"R2 readback failed (HTTP {resp.status_code})")
                print(f"    {ok} verified readback ({len(resp.content)} bytes)")

                # 3. Update any BazarPost pointing to old DB URL or bare key
                old_db_url = media_db.public_url(key)
                posts = db.query(BazarPost).filter(
                    (BazarPost.media_url == old_db_url) |
                    (BazarPost.media_url.like(f"%{key}%"))
                ).all()

                for p in posts:
                    old_u = p.media_url
                    p.media_url = r2_url
                    print(f"    {ok} updated Post #{p.id} ({p.crop}): {old_u} -> {r2_url}")

                # 4. Remove from Postgres
                db.delete(r)
                db.commit()
                print(f"    {ok} deleted row {key} from bazar_media")
                migrated += 1

            except Exception as e:
                db.rollback()
                failed += 1
                print(f"    {no} FAILED migrating {key}: {e}")

        print(f"\n── Summary ──────────────────────────────────────")
        print(f"  Migrated: {migrated}/{total_count}")
        if failed > 0:
            print(f"  {no} Failed: {failed}")
            return 1

        print(f"  {ok} All Postgres media migrated to R2 and freed from Neon storage!\n")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

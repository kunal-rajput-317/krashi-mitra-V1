# ============================================================
# seed_cache.py
# KrashiMitra — Cache Seeder
# Feeds curated Q&A pairs (cache/seed_qa.json) into the LIVE
# server's semantic cache via the admin API (POST /admin/cache/add).
# The server computes embeddings, so semantic matching works for
# every seeded entry. Safe to re-run — duplicates are skipped.
#
# Usage:
#   python seed_cache.py --url https://your-app.onrender.com -p ADMIN_PASSWORD
#   python seed_cache.py --url http://localhost:8000 -p krashi2025 --verify
#
# NOTE: Render's disk is ephemeral — seeded entries live until the
# next deploy/restart. Just re-run this script after a deploy.
# ============================================================

import argparse
import json
import os
import sys
from pathlib import Path

import requests

# Windows consoles default to cp1252, which can't print Devanagari/emoji
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEED_FILE = Path(__file__).parent / "cache" / "seed_qa.json"

# Paraphrases (NOT in the seed file) used by --verify to prove that
# semantic matching catches differently-worded farmer questions.
VERIFY_QUESTIONS = [
    "गेहूं में पीला रोग लग गया है क्या करूं",
    "dhan ki patti par bhure dhabbe aa gaye hai",
    "पीएम किसान योजना में कितना पैसा मिलता है",
    "ganna kab bona chahiye",
]


def parse_args():
    ap = argparse.ArgumentParser(description="Seed the KrashiMitra semantic cache via the admin API")
    ap.add_argument("--url", default=os.getenv("KM_URL", "http://localhost:8000"),
                    help="Server base URL (or env KM_URL)")
    ap.add_argument("--user", default=os.getenv("ADMIN_USER", "admin"),
                    help="Admin username (or env ADMIN_USER)")
    ap.add_argument("-p", "--password", default=os.getenv("ADMIN_PASS", ""),
                    help="Admin password (or env ADMIN_PASS)")
    ap.add_argument("--file", default=str(SEED_FILE), help="Seed Q&A JSON file")
    ap.add_argument("--verify", action="store_true",
                    help="After seeding, test paraphrase questions against /admin/cache/search")
    ap.add_argument("--dry-run", action="store_true", help="Print entries without sending")
    return ap.parse_args()


def flatten(topics: list[dict]) -> list[tuple[str, str, str]]:
    """[{topic, questions[], answer}] -> [(topic, question, answer), ...]"""
    pairs = []
    for t in topics:
        for q in t["questions"]:
            pairs.append((t["topic"], q, t["answer"]))
    return pairs


def wake_up(base: str):
    """Render free tier sleeps — first request can take ~60s. Poke it once."""
    print(f"[seed] Waking up {base} (Render cold start can take up to 90s)...")
    try:
        requests.get(base, timeout=90)
        print("[seed] Server is awake.")
    except Exception as e:
        print(f"[seed] Wake-up ping failed ({e}) — continuing anyway.")


def main():
    args = parse_args()
    base = args.url.rstrip("/")
    # Tolerate a base URL pasted with the admin path on it — the script
    # adds /admin/... itself, so strip it to avoid /admin/admin/ 405s.
    if base.endswith("/admin"):
        base = base[: -len("/admin")]
        print(f"[seed] Note: stripped trailing /admin from URL -> {base}")

    topics = json.loads(Path(args.file).read_text(encoding="utf-8"))
    pairs = flatten(topics)
    print(f"[seed] {len(topics)} topics -> {len(pairs)} question phrasings")

    if args.dry_run:
        for topic, q, _ in pairs:
            print(f"  [{topic}] {q}")
        return

    if not args.password:
        sys.exit("[seed] Admin password required: -p PASSWORD or env ADMIN_PASS")

    auth = (args.user, args.password)
    wake_up(base)

    saved, dupes, failed = 0, 0, 0
    for topic, question, answer in pairs:
        try:
            r = requests.post(
                f"{base}/admin/cache/add",
                json={"question": question, "answer": answer, "source": "claude"},
                auth=auth,
                timeout=60,  # embedding model may lazy-load on first save
            )
            if r.status_code == 401:
                sys.exit("[seed] ❌ 401 Unauthorized — wrong admin username/password.")
            r.raise_for_status()
            data = r.json()
            if data.get("saved"):
                saved += 1
                print(f"  ✅ saved     [{topic}] {question[:45]}")
            elif data.get("duplicate"):
                dupes += 1
                print(f"  ↩  duplicate [{topic}] {question[:45]}")
            else:
                failed += 1
                print(f"  ⚠  rejected  [{topic}] {question[:45]} -> {data}")
        except requests.RequestException as e:
            failed += 1
            print(f"  ❌ failed    [{topic}] {question[:45]} -> {e}")

    print(f"\n[seed] Done: {saved} saved, {dupes} duplicates skipped, {failed} failed.")

    # Confirm server-side totals
    try:
        r = requests.get(f"{base}/admin/cache/stats", auth=auth, timeout=30)
        r.raise_for_status()
        print(f"[seed] Cache now holds {r.json()['total_entries']} entries "
              f"(semantic={'ON' if r.json().get('semantic_enabled') else 'OFF'}).")
    except Exception as e:
        print(f"[seed] Could not fetch cache stats: {e}")

    if args.verify:
        print("\n[seed] Verifying semantic matching with unseen paraphrases:")
        for q in VERIFY_QUESTIONS:
            try:
                r = requests.post(f"{base}/admin/cache/search",
                                  json={"question": q}, auth=auth, timeout=60)
                r.raise_for_status()
                data = r.json()
                if data.get("hit"):
                    res = data["result"]
                    print(f"  ✅ HIT  score={res['score']}  '{q[:40]}' -> '{res['original_q'][:40]}'")
                else:
                    print(f"  ❌ MISS '{q[:40]}' — would fall through to AI")
            except Exception as e:
                print(f"  ⚠  verify failed for '{q[:30]}': {e}")


if __name__ == "__main__":
    main()

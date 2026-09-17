# -*- coding: utf-8 -*-
# ============================================================
# tools/build_seed_qa.py
# Builds cache/seed_qa.json — the curated Q&A the chat answers from.
#
# The corpus is NEVER hand-edited as JSON, for the same reason articles are
# never hand-written as HTML: the disclaimers, the crop tags and the duplicate
# checks are things an author forgets on exactly the one entry that needed
# them. Content lives in tools/seed_qa/*.py as plain Python lists; this script
# merges them, enforces the rules, and writes the file the runtime reads.
#
# WHAT IT ENFORCES
# ----------------
#   * every topic slug and every question string is unique across the corpus —
#     two entries answering the same question means one of them is unreachable
#   * `crops` names real crops from seed_terms.CROP_TOKENS, so the wrong-crop
#     gate can actually fire (a typo there silently disarms it)
#   * any answer that names an agro-chemical or prints a dose gets the spray
#     advisory appended — detected with tools/article_advisory.py, the same
#     detector the 175 article pages are held to
#   * any answer about a government scheme carries its official source, and
#     never an eligibility promise
#   * no answer states a market price — /bhav is the only place a number that
#     changes daily may appear
#
# Usage:
#   python tools/build_seed_qa.py            # write cache/seed_qa.json
#   python tools/build_seed_qa.py --check    # validate only, non-zero on error
#   python tools/build_seed_qa.py --stats    # what is in the corpus
# ============================================================

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))

import article_advisory as adv                     # noqa: E402
from cache.seed_terms import CROP_TOKENS, tokens   # noqa: E402

OUT = REPO / "cache" / "seed_qa.json"
PKG = REPO / "tools" / "seed_qa"

# ── the two lines the builder appends ─────────────────────────
# Short on purpose: this is a chat bubble on a phone, not an article. It still
# has to carry the two claims that do the work — the label is the authority,
# and a human at the KVK is the place to confirm. See tools/article_advisory.py
# for why those two and not a longer disclaimer.
ADVISORY = (
    "⚠️ मात्रा हमेशा डिब्बे के लेबल से लें — यह सामान्य जानकारी है, किसी एक खेत "
    "की सिफ़ारिश नहीं। छिड़काव से पहले अपने कृषि विज्ञान केंद्र (KVK) से पुष्टि कर लें।"
)

# A scheme answer says where the rule actually lives. It never states who is
# eligible and never promises an amount — that is the standing rule for every
# subsidy surface on this site.
SCHEME_NOTE = "ℹ️ राशि, पात्रता और अंतिम नियम सरकारी पोर्टल पर देखें: {official}"

# Prices change daily and are not ours to state in a stored answer.
_PRICE_CLAIM = re.compile(r"(?:₹|रु\.?|रुपये|rs\.?)\s*\d", re.I)

MIN_ANSWER = 60
MAX_ANSWER = 1100
MIN_QUESTIONS = 2


class BuildError(Exception):
    pass


def _modules() -> list:
    mods = []
    for m in sorted(pkgutil.iter_modules([str(PKG)]), key=lambda x: x.name):
        if m.name.startswith("_"):
            continue
        mods.append(importlib.import_module(f"seed_qa.{m.name}"))
    return mods


def _finish(topic: dict) -> dict:
    """One authored topic -> the record the runtime reads."""
    answer = topic["answer"].strip()

    official = topic.get("official")
    if official and SCHEME_NOTE.format(official=official) not in answer:
        answer += "\n" + SCHEME_NOTE.format(official=official)

    if adv.needs_advisory(answer) and ADVISORY not in answer:
        answer += "\n" + ADVISORY

    return {
        "topic": topic["topic"],
        "crops": sorted(topic.get("crops", [])),
        "tags": sorted(topic.get("tags", [])),
        "questions": list(topic["questions"]),
        "answer": answer,
    }


def _validate(records: list[dict]) -> list[str]:
    errors: list[str] = []
    seen_topics: dict[str, str] = {}
    seen_questions: dict[str, str] = {}

    for r in records:
        slug = r["topic"]
        if not re.fullmatch(r"[a-z0-9_]+", slug or ""):
            errors.append(f"{slug!r}: topic slug must be lowercase a-z0-9_")
        if slug in seen_topics:
            errors.append(f"{slug!r}: duplicate topic slug")
        seen_topics[slug] = slug

        for c in r["crops"]:
            if c not in CROP_TOKENS:
                errors.append(
                    f"{slug}: crop {c!r} is not in seed_terms.CROP_TOKENS — the "
                    f"wrong-crop gate cannot fire on a name it does not know")

        qs = r["questions"]
        if len(qs) < MIN_QUESTIONS:
            errors.append(f"{slug}: only {len(qs)} phrasing(s), need {MIN_QUESTIONS}")
        for q in qs:
            key = " ".join(tokens(q))
            if not key:
                errors.append(f"{slug}: question {q!r} has no content words")
                continue
            if key in seen_questions and seen_questions[key] != slug:
                errors.append(
                    f"{slug}: question {q!r} collides with topic "
                    f"{seen_questions[key]!r} — one of them is unreachable")
            seen_questions.setdefault(key, slug)

        a = r["answer"]
        if not (MIN_ANSWER <= len(a) <= MAX_ANSWER):
            errors.append(f"{slug}: answer is {len(a)} chars (want {MIN_ANSWER}-{MAX_ANSWER})")
        if _PRICE_CLAIM.search(a):
            errors.append(
                f"{slug}: answer states a rupee figure — a stored answer must "
                f"not carry a price; send the farmer to /bhav instead")
        if adv.needs_advisory(a) and ADVISORY not in a:
            errors.append(f"{slug}: names a chemical/dose but carries no advisory")

    return errors


def build() -> list[dict]:
    records: list[dict] = []
    for mod in _modules():
        topics = getattr(mod, "TOPICS", None)
        if not topics:
            raise BuildError(f"{mod.__name__} exports no TOPICS")
        for t in topics:
            records.append(_finish(t))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the curated chat Q&A corpus")
    ap.add_argument("--check", action="store_true", help="validate without writing")
    ap.add_argument("--stats", action="store_true", help="print corpus composition")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    records = build()
    errors = _validate(records)
    questions = sum(len(r["questions"]) for r in records)

    if errors:
        print(f"[seed-qa] ❌ {len(errors)} problem(s):")
        for e in errors[:40]:
            print("   -", e)
        if len(errors) > 40:
            print(f"   ... and {len(errors) - 40} more")
        return 1

    print(f"[seed-qa] {len(records)} topics -> {questions} question phrasings")

    if args.stats:
        by_tag: dict[str, int] = {}
        for r in records:
            for t in r["tags"] or ["untagged"]:
                by_tag[t] = by_tag.get(t, 0) + 1
        for tag, n in sorted(by_tag.items(), key=lambda x: -x[1]):
            print(f"   {tag:<16} {n:>4}")
        crops = sorted({c for r in records for c in r["crops"]})
        print(f"   crops covered: {len(crops)} — {', '.join(crops)}")
        advis = sum(1 for r in records if ADVISORY in r["answer"])
        print(f"   answers carrying the spray advisory: {advis}")

    if args.check:
        print("[seed-qa] ✅ check only — nothing written")
        return 0

    OUT.write_text(
        json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[seed-qa] ✅ wrote {OUT.relative_to(REPO)} "
          f"({round(OUT.stat().st_size / 1024)} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

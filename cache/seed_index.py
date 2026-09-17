# -*- coding: utf-8 -*-
# ============================================================
# cache/seed_index.py
# The curated Q&A corpus, and the matcher that finds an answer in it.
#
# WHY THIS IS NOT THE CACHE
# -------------------------
# cache_engine.py holds what the AI has *learned* — a mutable, self-pruning
# store on Render's ephemeral disk, capped at MAX_CACHE_SIZE and wiped by every
# redeploy. Pouring a thousand curated answers into it would (a) evict the
# learned ones, (b) need re-seeding after every deploy — the manual seam this
# project bans — and (c) cost a thousand embeddings on a dyno that cannot load
# the model at all.
#
# So the corpus lives in the repo (cache/seed_qa.json, built by
# tools/build_seed_qa.py), is loaded read-only at import, and is never written
# to. It ships with the deploy, which means it is never missing and never
# stale-by-restart. No admin has to press anything.
#
# WHY A LEXICAL MATCHER
# ---------------------
# Production runs CACHE_SEMANTIC_ENABLED=false, so there are no embeddings in
# front of a farmer — only SequenceMatcher at 0.94, which is an exact match
# wearing a hat. This scores canonical tokens (see seed_terms.py) with IDF
# weights, so "gehu me urea kab dale" and "गेहूं में यूरिया कब डालें" both reach
# the same answer, and "कब" and "कितना" reach different ones.
#
# THE GATE
# --------
# A match whose crop is not the crop that was asked about is refused, even at a
# high score. Answers here carry chemical names and doses; handing a soybean
# question a wheat answer is the one failure mode that is worse than saying
# nothing. Same rule as /sawal, for the same reason.
# ============================================================

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from cache.seed_terms import CROP_TOKENS, crops_in, tokens

SEED_FILE = Path(__file__).parent / "seed_qa.json"

# Tuned against tests/test_seed_qa.py, which holds real paraphrases that are
# deliberately NOT in the corpus. Raising ACCEPT trades recall for silence;
# silence is the safe direction, so err upward, never downward.
ACCEPT_SCORE = 0.62
SUGGEST_SCORE = 0.28
MAX_SUGGESTIONS = 3


class _Entry:
    __slots__ = ("topic", "answer", "crops", "questions", "tags")

    def __init__(self, topic: str, answer: str, crops: set[str],
                 questions: list[str], tags: list[str]):
        self.topic = topic
        self.answer = answer
        self.crops = crops
        self.questions = questions
        self.tags = tags


# ── module state, built once ──────────────────────────────────
_entries: list[_Entry] = []
_docs: list[tuple[int, str, frozenset[str]]] = []   # (entry idx, question, tokens)
_postings: dict[str, list[int]] = {}               # token -> doc indices
_idf: dict[str, float] = {}
_exact: dict[str, int] = {}                        # normalised question -> doc idx
_loaded = False


def _norm_key(text: str) -> str:
    return " ".join(tokens(text))


def _build(topics: list[dict]) -> None:
    global _entries, _docs, _postings, _idf, _exact
    entries: list[_Entry] = []
    docs: list[tuple[int, str, frozenset[str]]] = []

    for t in topics:
        questions = [q for q in t.get("questions", []) if q and q.strip()]
        answer = (t.get("answer") or "").strip()
        if not questions or not answer:
            continue
        declared = {c for c in t.get("crops", []) if c in CROP_TOKENS}
        e = _Entry(
            topic=t.get("topic", ""),
            answer=answer,
            crops=declared,
            questions=questions,
            tags=list(t.get("tags", [])),
        )
        idx = len(entries)
        entries.append(e)
        for q in questions:
            toks = frozenset(tokens(q))
            if toks:
                docs.append((idx, q, toks))

    postings: dict[str, list[int]] = {}
    for d, (_, _, toks) in enumerate(docs):
        for tok in toks:
            postings.setdefault(tok, []).append(d)

    n = max(len(docs), 1)
    idf = {tok: math.log(1 + n / len(ds)) for tok, ds in postings.items()}

    exact: dict[str, int] = {}
    for d, (_, q, _) in enumerate(docs):
        exact.setdefault(_norm_key(q), d)

    _entries, _docs, _postings, _idf, _exact = entries, docs, postings, idf, exact


def load(force: bool = False) -> int:
    """Read the corpus into memory. Returns the number of topics loaded."""
    global _loaded
    if _loaded and not force:
        return len(_entries)
    try:
        topics = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    except Exception:
        topics = []
    _build(topics if isinstance(topics, list) else [])
    _loaded = True
    return len(_entries)


def _ensure() -> None:
    if not _loaded:
        load()


def _weight(tok: str) -> float:
    # An unseen query word still says something about what was asked, so it
    # counts against coverage rather than being silently free.
    return _idf.get(tok, math.log(1 + max(len(_docs), 1)))


def _score_docs(q_tokens: list[str]) -> list[tuple[float, int]]:
    """Every doc sharing a token with the query, scored, best first."""
    q_set = set(q_tokens)
    if not q_set:
        return []
    q_total = sum(_weight(t) for t in q_set)
    if q_total <= 0:
        return []

    candidates: set[int] = set()
    for tok in q_set:
        candidates.update(_postings.get(tok, ()))

    scored: list[tuple[float, int]] = []
    for d in candidates:
        _, _, toks = _docs[d]
        shared = q_set & toks
        if not shared:
            continue
        matched = sum(_weight(t) for t in shared)
        d_total = sum(_weight(t) for t in toks) or 1.0
        cov_q = matched / q_total          # how much of the question we understood
        cov_d = matched / d_total          # how much of the stored question we used
        if cov_q <= 0 or cov_d <= 0:
            continue
        # Harmonic mean: a stored question that is merely short must not win by
        # being easy to cover, and a long one must not win by containing a lot.
        score = 2 * cov_q * cov_d / (cov_q + cov_d)
        scored.append((score, d))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def _crop_ok(asked: set[str], entry: _Entry) -> bool:
    """The wrong-crop gate. A general answer fits any crop; a wheat answer does
    not fit a soybean question, whatever the score says."""
    if not asked or not entry.crops:
        return True
    return bool(asked & entry.crops)


def search_seed(question: str) -> dict | None:
    """The curated answer for this question, or None — never a near miss."""
    _ensure()
    if not _docs or not (question or "").strip():
        return None

    asked = crops_in(question)

    key = _norm_key(question)
    d = _exact.get(key)
    if d is not None:
        e_idx, orig, _ = _docs[d]
        entry = _entries[e_idx]
        if _crop_ok(asked, entry):
            return {
                "answer": entry.answer,
                "score": 1.0,
                "source": "seed",
                "original_q": orig,
                "topic": entry.topic,
            }

    q_tokens = tokens(question)
    # One bare word — usually just a crop name — is a topic, not a question.
    # Answering it from a thousand-entry corpus is a coin toss, so don't.
    content = [t for t in set(q_tokens) if t not in ("when", "how", "howmuch",
                                                     "which", "why", "where", "apply")]
    if len(content) < 2:
        return None

    for score, d in _score_docs(q_tokens)[:20]:
        if score < ACCEPT_SCORE:
            break
        e_idx, orig, _ = _docs[d]
        entry = _entries[e_idx]
        if not _crop_ok(asked, entry):
            continue
        return {
            "answer": entry.answer,
            "score": round(score, 4),
            "source": "seed",
            "original_q": orig,
            "topic": entry.topic,
        }
    return None


def suggest_seed(question: str, limit: int = MAX_SUGGESTIONS) -> list[str]:
    """The near misses — the questions this corpus *can* answer that look most
    like what was typed. Used when nothing else can answer: a farmer who is
    shown three questions he recognises has been helped; one who is shown an
    apology has not."""
    _ensure()
    if not _docs:
        return []
    asked = crops_in(question)
    out: list[str] = []
    seen_topics: set[str] = set()
    for score, d in _score_docs(tokens(question))[:40]:
        if score < SUGGEST_SCORE:
            break
        e_idx, orig, _ = _docs[d]
        entry = _entries[e_idx]
        if entry.topic in seen_topics or not _crop_ok(asked, entry):
            continue
        seen_topics.add(entry.topic)
        out.append(orig)
        if len(out) >= limit:
            break
    return out


def popular_questions(limit: int = 6) -> list[str]:
    """A spread of questions the corpus answers well — one per topic, taken
    across the file rather than from its first few lines, so the sample is not
    all wheat."""
    _ensure()
    if not _entries:
        return []
    step = max(1, len(_entries) // max(limit, 1))
    out = []
    for i in range(0, len(_entries), step):
        qs = _entries[i].questions
        if qs:
            out.append(qs[0])
        if len(out) >= limit:
            break
    return out


def get_stats() -> dict:
    _ensure()
    return {
        "topics": len(_entries),
        "questions": len(_docs),
        "vocabulary": len(_postings),
        "crops": len({c for e in _entries for c in e.crops}),
        "file_kb": round(SEED_FILE.stat().st_size / 1024, 1) if SEED_FILE.exists() else 0,
        "enabled": os.getenv("SEED_INDEX_ENABLED", "true").lower() != "false",
    }


def enabled() -> bool:
    """One env var to take the corpus out of the pipeline without a deploy."""
    return os.getenv("SEED_INDEX_ENABLED", "true").lower() != "false"

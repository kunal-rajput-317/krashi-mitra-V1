# ============================================================
# backend/services/kcc_service.py
# KrashiMitra — किसान कॉल सेंटर सवाल-जवाब harvester
# ------------------------------------------------------------
# Source: data.gov resource cef25fe2-9231-4128-8aec-2c948fedd43f,
# "Kisan Call Centre (KCC) - Transcripts of farmers queries &
# answers" — ~48M real helpline calls, 2006 → mid-2025. Free on
# the same DATA_GOV_API_KEY the mandi fetch already uses.
#
# WHY THE FILTERING IS SO AGGRESSIVE
# Measured on a 6,000-row sample (Wheat / Uttar Pradesh, 2026-07-29):
#   • 50%  of rows are throwaway weather chatter ("farmer asked query
#          on weather" + a forecast from 2023). Useless and stale.
#   •  0%  of QUESTIONS are in Hindi — they are staff-typed English or
#          romanised shorthand ("genhu me bali ka nhi pdna"). Only the
#          ANSWERS are Hindi, so the answer is the publishable half.
#   •  2%  of answers give advice for a DIFFERENT crop than the row is
#          filed under (105 of 5,720 wheat rows answered about धान).
#          These answers carry pesticide names and doses, so publishing
#          them unfiltered would put wrong-crop spray advice in front of
#          a farmer. This is the single most important reason this file
#          exists rather than a straight copy of the feed.
#
# THE GATE: keep an answer only if it NAMES ITS OWN CROP in Hindi.
# That is ~15% of rows — and 15% of the 1.09M wheat/UP rows is still
# ~160k candidates, so throwing away the other 85% costs us nothing.
# Anything that names no crop, or names someone else's, is dropped.
#
# Manual run:
#   python -m backend.services.kcc_service --build wheat
#   python -m backend.services.kcc_service --drain 2
#   python -m backend.services.kcc_service --audit wheat
# ============================================================

import os
import re
import time
import hashlib
import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database.db import SessionLocal, KccQA, KccCropBuild
from backend.services.mandi_fetch_service import _get_page, _norm, API_KEY

logger = logging.getLogger("krishi.kcc")

KCC_RESOURCE_ID = "cef25fe2-9231-4128-8aec-2c948fedd43f"
KCC_ENDPOINT    = f"https://api.data.gov.in/resource/{KCC_RESOURCE_ID}"

# 500, not the 5000 the mandi resources take. This resource is ~48M rows and
# data.gov's gateway intermittently 504s on a filtered query at limit=1000
# (observed 2026-07-29); 500 has been stable. Raising this to "save calls" is
# a false economy — a 504 costs the whole crop's harvest.
PAGE = int(os.getenv("KCC_PAGE", "500"))
MAX_PAGES_PER_CROP = int(os.getenv("KCC_MAX_PAGES", "8"))
MAX_QA_PER_CROP    = int(os.getenv("KCC_MAX_QA", "60"))
MAX_PER_TOPIC      = int(os.getenv("KCC_MAX_PER_TOPIC", "10"))
DRAIN_BATCH        = int(os.getenv("KCC_DRAIN_BATCH", "2"))
MAX_ATTEMPTS       = 3
REQ_DELAY          = 0.4

MIN_ANS_LEN = 45            # shorter answers are stubs ("boran20% spray kare")
MAX_ANS_LEN = 900           # longer ones are pasted scheme dumps

# Topics worth publishing: evergreen agronomy only. Weather / Government
# Schemes / Market Information / Crop Insurance are all time-sensitive — a
# 2023 forecast or scheme deadline is actively misleading in 2026.
TOPICS = {
    "plant protection":                "कीट व रोग नियंत्रण",
    "weed management":                 "खरपतवार नियंत्रण",
    "nutrient management":             "पोषण व खाद प्रबंधन",
    "fertilizer use and availability": "उर्वरक का उपयोग",
    "cultural practices":              "खेती की विधि",
    "varieties":                       "उन्नत किस्में",
    "seeds":                           "बीज",
    "field preparation":               "खेत की तैयारी",
    "water management":                "सिंचाई व जल प्रबंधन",
}

# Curated crops: slug → (KCC "Crop" value, Hindi name, self-mention aliases).
# The aliases are what the safety gate looks for inside the Hindi answer.
CROPS = {
    "gehu":      ("Wheat",                          "गेहूं",   ("गेहूं", "गेहू", "गेहुँ")),
    "dhan":      ("Paddy (Dhan)",                   "धान",     ("धान", "चावल")),
    "ganna":     ("Sugarcane (Noble Cane)",         "गन्ना",   ("गन्ना", "गन्ने", "ईख")),
    "sarson":    ("Mustard",                        "सरसों",   ("सरसों", "सरसो")),
    "aloo":      ("Potato",                         "आलू",     ("आलू",)),
    "chana":     ("Bengal Gram (Chana)",            "चना",     ("चना", "चने")),
    "makka":     ("Maize (Makka)",                  "मक्का",   ("मक्का", "मक्के")),
    "kapas":     ("Cotton (Kapas)",                 "कपास",    ("कपास",)),
    "soyabean":  ("Soybean (bhat)",                 "सोयाबीन", ("सोयाबीन",)),
    "arhar":     ("Pigeon pea (red gram/arhar/tur)", "अरहर",   ("अरहर", "तुअर", "तूर")),
    "moong":     ("Green Gram (Moong Bean/ Moong)", "मूंग",    ("मूंग", "मुंग")),
    "urad":      ("Black Gram (urd bean)",          "उड़द",    ("उड़द", "उर्द")),
    "bajra":     ("Pearl Millet (Bajra/Bulrush Millet/Spiked Millet)",
                                                    "बाजरा",   ("बाजरा",)),
    "jowar":     ("Sorghum (Jowar/Great Millet)",   "ज्वार",   ("ज्वार",)),
    "mungfali":  ("Groundnut (pea nut/mung phalli)", "मूंगफली", ("मूंगफली", "मुंगफली")),
    "til":       ("Sesame (Gingelly/Til)/Sesamum",  "तिल",     ("तिल",)),
    "tamatar":   ("Tomato",                         "टमाटर",   ("टमाटर",)),
    "pyaj":      ("Onion",                          "प्याज",   ("प्याज", "प्याज़")),
    "mirch":     ("Chillies",                       "मिर्च",   ("मिर्च",)),
    "baingan":   ("Brinjal",                        "बैंगन",   ("बैंगन",)),
    "bhindi":    ("Bhindi(Okra/Ladysfinger)",       "भिंडी",   ("भिंडी",)),
    "aam":       ("Mango",                          "आम",      ("आम का", "आम की", "आम के", "आम में")),
}

# Every other crop's Hindi name — if an answer names one of these and NOT its
# own crop, it is misfiled and must never be published under this crop.
_ALL_ALIASES = {slug: set(a) for slug, (_c, _hi, a) in CROPS.items()}


def _devanagari_share(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "ऀ" <= c <= "ॿ") / len(letters)


def _clean(s: str) -> str:
    """Trim the transcript noise: honorifics, stray pipes, repeated spaces."""
    s = _norm(s).replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip(" |-–—.")
    s = re.sub(r"^(श्रीमान\s*जी|महोदय|सर|किसान\s*भाई|जी)[\s,:-]*", "", s).strip()
    return s


_LEAD = re.compile(
    r"^(प्रिय\s*किसान\s*भाई|प्रिय\s*किसान|किसान\s*भाई|श्रीमान\s*जी|महोदय|सर"
    # bare "जी" survives when the greeting was split across fields
    r"|जी|आप\s*की|आपकी|आपके|आपको|आप)[\s,:।-]*")

# Nearly every KCC answer states its purpose before prescribing: "गेहूं की फसल
# में चूहा नियंत्रण **के लिए** जिंक फास्फाइड …". The text before that marker is
# the farmer's actual question, in the farmer's own Hindi.
_PURPOSE = ("के नियंत्रण के लिए", "के नियंत्रण हेतु", "की रोकथाम के लिए",
            "के लिए", "हेतु")


def derive_question(ans: str, aliases: tuple) -> str | None:
    """Turn an answer into the Hindi question it answers, or None.

    The transcripts' own QueryText cannot be used: it is typed by call-centre
    staff in English or romanised shorthand ("genhu me bali ka nhi pdna") and
    measured 0% Devanagari across a 6,000-row sample. Composing a heading from
    crop+topic instead would give every card on a page the same title — bad to
    read, and 60 near-identical FAQPage entries is a structured-data smell.

    So we recover the question from the answer's own purpose clause. ~44% of
    answers yield one; the rest are dropped, which is affordable given the
    source has millions of rows.
    """
    for marker in _PURPOSE:
        i = ans.find(marker)
        if not (8 <= i <= 110):
            continue
        stem = ans[:i]
        prev = None
        while prev != stem:                 # honorifics stack: "आप आपकी …"
            prev = stem
            stem = _LEAD.sub("", stem).strip(" ,।-")
        stem = re.sub(r"\s+", " ", stem).strip(" ,।-")
        # Upper bound as well as lower: past ~70 chars the "question" is really
        # a whole statement and reads as nonsense with "के लिए क्या करें?"
        # bolted on. The genuinely useful ones are short.
        # The stem must also name the crop, or it is advice for nothing in
        # particular ("ऊंचे पर्वतीय क्षेत्रों के लिए क्या करें?").
        if 12 <= len(stem) <= 70 and any(a in stem for a in aliases):
            return f"{stem} के लिए क्या करें?"
    return None


def _has_contact(ans: str) -> bool:
    """True if the answer is really a contact/helpline dump rather than advice.

    A plain 10-digit regex is not enough — live answers carry landlines and
    toll-free numbers written with spaces and hyphens ("0184 226 7390",
    "1800-11-8989"). So join digits that are separated only by spaces, dots,
    hyphens or brackets, then look for any run of 8+.  Doses are safe: the
    digits in "200 लीटर पानी में 25% ईसी" are split by Devanagari, never joined.
    """
    if "http" in ans.lower() or "@" in ans:
        return True
    joined = re.sub(r"(?<=\d)[\s\-.()+]+(?=\d)", "", ans)
    return bool(re.search(r"\d{8,}", joined))


def is_publishable(row: dict, crop_key: str) -> tuple[bool, str]:
    """
    The safety gate. Returns (ok, reason_when_rejected).

    Order matters only for the reason label — every check must pass.
    """
    kcc_crop, _hi, aliases = CROPS[crop_key]

    topic = (row.get("QueryType") or "").strip().strip("\t").lower()
    if topic not in TOPICS:
        return False, "topic"                     # weather / schemes / market

    ans = _clean(row.get("KccAns") or "")
    if not (MIN_ANS_LEN <= len(ans) <= MAX_ANS_LEN):
        return False, "length"
    if _devanagari_share(ans) < 0.5:
        return False, "not-hindi"                 # we publish a Hindi page

    # THE important one: the answer must name the crop it is filed under.
    # This is what catches the misfiled paddy-answer-under-wheat class — those
    # say धान and never गेहूं, so they fail here.
    #
    # Note we deliberately do NOT also reject answers that mention some other
    # crop alongside their own. Checked against live data: the wheat rat-bait
    # answer says "सरसों का तेल" — mustard OIL as a bait ingredient, not
    # mustard-crop advice. A blanket cross-crop reject would throw away good
    # answers to prevent a case that self-mention already covers.
    if not any(a in ans for a in aliases):
        return False, "no-self-mention"

    if _has_contact(ans):
        return False, "contact-info"

    # Non-answers: "…के लिए बीज दुकान से संपर्क करें" is a deflection, not
    # advice, and makes a worthless card. Only rejected on SHORT answers — a
    # long answer that ends "…या कृषि अधिकारी से संपर्क करें" is still useful.
    if len(ans) < 140 and re.search(r"संपर्क\s*कर|जानकारी\s*लेने", ans):
        return False, "non-answer"

    # Must yield a real Hindi question — see derive_question().
    if not derive_question(ans, aliases):
        return False, "no-question"
    return True, ""


def _answer_key(crop_key: str, ans: str) -> str:
    """Dedup on the answer's shape — the same canned reply recurs thousands of
    times with trivial spacing/number differences."""
    norm = re.sub(r"[^ऀ-ॿ]+", "", ans)
    return hashlib.md5(f"{crop_key}|{norm}".encode("utf-8")).hexdigest()


def harvest(crop_key: str) -> dict:
    """Fetch → gate → dedupe → store one crop's Q&A set."""
    if crop_key not in CROPS:
        return {"ok": False, "error": f"unknown crop {crop_key}"}
    kcc_crop, hi, _aliases = CROPS[crop_key]
    started = time.time()

    kept, seen, rejects = {}, 0, {}
    per_topic: dict[str, int] = {}
    fetch_failed = False

    for page in range(MAX_PAGES_PER_CROP):
        recs = _get_page(
            {"api-key": API_KEY, "format": "json", "limit": PAGE,
             "offset": page * PAGE, "filters[Crop]": kcc_crop},
            f"[kcc {crop_key}] page={page}", endpoint=KCC_ENDPOINT,
        )
        # None = the page hard-failed after retries (gateway 504 etc.);
        # [] = the query genuinely has no more rows. Conflating the two is how
        # a transient outage silently brands a crop "empty" forever.
        if recs is None:
            fetch_failed = True
            break
        if not recs:
            break
        seen += len(recs)
        for r in recs:
            ok, why = is_publishable(r, crop_key)
            if not ok:
                rejects[why] = rejects.get(why, 0) + 1
                continue
            topic = (r.get("QueryType") or "").strip().strip("\t").lower()
            if per_topic.get(topic, 0) >= MAX_PER_TOPIC:
                continue
            ans = _clean(r.get("KccAns"))
            key = _answer_key(crop_key, ans)
            if key in kept:
                continue
            question = derive_question(ans, CROPS[crop_key][2])
            # Two answers can phrase the same problem differently yet reduce to
            # the same question — keep the page (and its FAQ schema) unique.
            if any(v["question"] == question for v in kept.values()):
                continue
            kept[key] = {
                "crop_key": crop_key, "crop": kcc_crop, "topic": topic,
                "question": question,
                "answer":   ans,
                "district": _clean(r.get("DistrictName")).title() or None,
                "state":    _clean(r.get("StateName")).title() or None,
                "year":     r.get("year"), "month": r.get("month"),
                "ans_key":  key, "built_at": datetime.utcnow(),
            }
            per_topic[topic] = per_topic.get(topic, 0) + 1
        if len(kept) >= MAX_QA_PER_CROP or len(recs) < PAGE:
            break
        time.sleep(REQ_DELAY)

    rows = list(kept.values())[:MAX_QA_PER_CROP]

    db = SessionLocal()
    try:
        if rows:
            stmt = pg_insert(KccQA.__table__).values(rows)
            db.execute(stmt.on_conflict_do_nothing(index_elements=["ans_key"]))

        # Three distinct outcomes, and they must not be collapsed:
        #   done  — we kept something
        #   error — the feed never answered, so we know nothing about this crop.
        #           Retryable: data.gov 504s on this resource under load.
        #   empty — we DID read rows and none passed the gate. Not retryable;
        #           re-reading the same rows would reject them again.
        if rows:
            status, note = "done", None
        elif fetch_failed or seen == 0:
            status, note = "error", "data.gov returned nothing (gateway) — will retry"
        else:
            status, note = "empty", f"read {seen} rows, none passed the gate ({rejects})"
        db.execute(
            text("""UPDATE kcc_crop_builds
                       SET status = :st, n_qa = :nq, n_seen = :ns,
                           attempts = attempts + 1, built_at = :bt, note = :nt
                     WHERE crop_key = :k"""),
            {"st": status, "nq": len(rows), "ns": seen, "bt": datetime.utcnow(),
             "k": crop_key, "nt": (note or "")[:200] or None},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"kcc harvest store failed for {crop_key}: {e}")
        db.execute(text("""UPDATE kcc_crop_builds SET status='error',
                             attempts = attempts + 1, note=:n WHERE crop_key=:k"""),
                   {"n": str(e)[:200], "k": crop_key})
        db.commit()
        db.close()
        return {"ok": False, "error": str(e)[:200]}
    finally:
        db.close()

    logger.info(f"🌾 KCC {crop_key} ({hi}): {seen} seen → {len(rows)} kept "
                f"[{status}] ({time.time() - started:.1f}s) rejects={rejects}")
    return {"ok": bool(rows), "status": status, "crop": crop_key,
            "seen": seen, "kept": len(rows), "rejects": rejects}


def ensure_queued() -> None:
    """Make sure every curated crop has a build row. Idempotent."""
    db = SessionLocal()
    try:
        for slug in CROPS:
            db.execute(
                pg_insert(KccCropBuild.__table__)
                .values(crop_key=slug, status="queued")
                .on_conflict_do_nothing(index_elements=["crop_key"])
            )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"kcc ensure_queued skipped: {e}")
    finally:
        db.close()


def drain_queue(limit: int = DRAIN_BATCH) -> dict:
    """Harvest a couple of pending crops. Rides along after the mandi fetch so
    it adds no scheduler wake-ups of its own."""
    ensure_queued()
    db = SessionLocal()
    try:
        pending = [r[0] for r in db.execute(
            text("""SELECT crop_key FROM kcc_crop_builds
                     WHERE status IN ('queued','error') AND attempts < :m
                  ORDER BY attempts ASC, id ASC LIMIT :l"""),
            {"m": MAX_ATTEMPTS, "l": limit})]
    finally:
        db.close()

    if not pending:
        return {"built": 0, "pending": 0}
    built = 0
    for slug in pending:
        try:
            if harvest(slug).get("ok"):
                built += 1
        except Exception as e:
            logger.error(f"kcc drain error on {slug}: {e}")
        time.sleep(REQ_DELAY)
    logger.info(f"🌾 KCC drain: {built}/{len(pending)} crop(s)")
    return {"built": built, "pending": len(pending)}


# ── Read ─────────────────────────────────────────────────────

def get_qa(crop_key: str) -> dict:
    """{topic_hi: [qa, ...]} for one crop, ready to render. Pure DB."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""SELECT topic, question, answer, district, state, year, month
                      FROM kcc_qa WHERE crop_key = :k
                  ORDER BY topic, year DESC NULLS LAST, id"""),
            {"k": crop_key},
        ).fetchall()
    finally:
        db.close()

    out: dict[str, list] = {}
    for topic, q, a, di, stt, yr, mo in rows:
        out.setdefault(TOPICS.get(topic, topic or "अन्य"), []).append(
            {"question": q, "answer": a, "district": di,
             "state": stt, "year": yr, "month": mo})
    return out


# A crop below this many answers makes a thin page not worth indexing.
MIN_QA_TO_PUBLISH = int(os.getenv("KCC_MIN_QA", "8"))


def crops_with_qa() -> list:
    """[(crop_key, hindi, n)] for crops with enough answers to publish."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT crop_key, count(*) FROM kcc_qa GROUP BY crop_key")
        ).fetchall()
    finally:
        db.close()
    counts = {k: n for k, n in rows}
    return [(slug, CROPS[slug][1], counts[slug])
            for slug in CROPS if counts.get(slug, 0) >= MIN_QA_TO_PUBLISH]


if __name__ == "__main__":
    import sys, json as _json

    logging.basicConfig(level=logging.INFO)
    argv = sys.argv[1:]

    if "--audit" in argv:
        # Gate diagnostics on live data — how much survives, and why the rest dies.
        slug = argv[argv.index("--audit") + 1]
        kcc_crop = CROPS[slug][0]
        recs = _get_page({"api-key": API_KEY, "format": "json", "limit": PAGE,
                          "filters[Crop]": kcc_crop},
                         f"[audit {slug}]", endpoint=KCC_ENDPOINT) or []
        tally: dict[str, int] = {}
        for r in recs:
            ok, why = is_publishable(r, slug)
            tally[why or "KEPT"] = tally.get(why or "KEPT", 0) + 1
        logger.info(f"{slug}: {len(recs)} rows -> {_json.dumps(tally, ensure_ascii=False)}")
    elif "--build" in argv:
        logger.info(harvest(argv[argv.index("--build") + 1]))
    else:
        n = DRAIN_BATCH
        if "--drain" in argv:
            j = argv.index("--drain")
            if len(argv) > j + 1 and argv[j + 1].isdigit():
                n = int(argv[j + 1])
        logger.info(drain_queue(n))

# ============================================================
# backend/services/poultry_necc.py
# अंडे का रेट — the NECC daily egg-price sheet, fetched and parsed.
#
# Pure fetch + parse. No database, no FastAPI, no rendering — so the parser
# can be tested against a saved copy of the sheet without a DB or a network,
# which is the only way to notice that a source has changed shape before a
# farmer does.
#
# WHAT THE SOURCE IS. The National Egg Co-ordination Committee publishes one
# HTML sheet per month at e2necc.com/home/eggprice: rows are zones, columns
# are the days of that month. So a single request returns the WHOLE month to
# date, not just today — history comes free with every fetch, and a backfill
# is just the same call with an older (month, year). The form is a plain POST
# with three fields and no viewstate token, verified against months back to
# 2009.
#
# TWO SECTIONS, AND THEY ARE NOT THE SAME CLAIM. The sheet is split by a
# one-cell marker row into "NECC SUGGESTED EGG PRICES" — what NECC recommends
# — and "Prevailing Prices" — what a zone is actually trading at. We keep the
# distinction on every row and the pages say which one they are showing,
# because a suggested price and a traded price are different facts and a
# farmer deciding when to sell needs to know which he is looking at.
#
# THE UNIT IS PAISE PER EGG. The sheet prints "550", meaning Rs 5.50 for one
# egg — identical to Rs 550 per 100 eggs, which is how the trade quotes it.
# Stored as that integer so no rounding ever creeps in, and rendered both ways
# so neither reading can be misunderstood.
#
# NECC'S OWN CONDITION IS A HARD REQUIREMENT, NOT A FOOTER NICETY. The sheet
# states that anyone not authorised by NECC who disseminates these prices
# "must also include the above clarification". CLARIFICATION below is that
# text verbatim; every page that prints a NECC number prints it too, and a
# test fails the build if one does not. This is the condition we are allowed
# to publish the numbers under.
# ============================================================

import logging
import re
from datetime import date

import requests

log = logging.getLogger("krishi.poultry_necc")

NECC_URL = "https://e2necc.com/home/eggprice"

# NECC's own words, quoted exactly as the sheet prints them. Not paraphrased,
# not shortened: the permission is to reproduce the clarification, so a
# tightened-up version of it would not be the clarification.
CLARIFICATION = (
    "The daily egg prices suggested by NECC, on its official website or "
    "through any other medium (including verbal, print and digital media) "
    "are merely suggestive and not mandatory. The suggested prices are "
    "published solely for the reference and information of the trade and "
    "industry. NECC does not by itself or through any person enforce "
    "compliance or adherence with such suggested egg prices in any manner "
    "whatsoever. If any person not authorized by NECC chooses to disseminate "
    "NECC suggested prices through any medium, such person must also include "
    "the above clarification while disseminating NECC suggested prices of eggs."
)

# The same thing in Hindi, for the farmer who cannot read the paragraph above.
# Placed BESIDE the English, never instead of it — the condition is on the
# English text.
CLARIFICATION_HI = (
    "NECC द्वारा सुझाए गए अंडे के दाम केवल सुझाव हैं, अनिवार्य नहीं। ये व्यापार और "
    "उद्योग की जानकारी के लिए प्रकाशित होते हैं। NECC किसी पर इन दामों को मानने की "
    "बाध्यता नहीं डालता। बेचने से पहले अपने स्थानीय व्यापारी से रेट की पुष्टि करें।"
)

_UA = ("Mozilla/5.0 (compatible; KrashiMitraBot/1.0; +https://krashimitra.in) "
       "python-requests")

# A one-cell row inside the price table is a section heading, not a zone.
_SECTIONS = {
    "necc suggested egg prices": "necc",
    "prevailing prices": "prevailing",
}

# An egg has never cost less than Rs 1 or more than Rs 20. Anything outside
# that is the source having changed shape (a merged cell, a stray total row),
# and storing it would put a fictional number on a page farmers price against.
PAISE_MIN, PAISE_MAX = 100, 2000

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<script.*?</script>", re.S | re.I)
_TABLE_RE = re.compile(r"<table.*?</table>", re.S | re.I)
_ROW_RE = re.compile(r"<tr.*?</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<t[dh].*?</t[dh]>", re.S | re.I)


def _text(fragment: str) -> str:
    """Cell markup -> its visible text, whitespace collapsed.

    The sheet indents its cell contents across many lines, so a raw strip()
    of one cell can carry a dozen newlines and a long run of spaces inside it.
    """
    return " ".join(_TAG_RE.sub("", fragment).replace("\xa0", " ").split())


def _paise(cell: str):
    """'550' -> 550; '551.79' -> 552; '-' / '' / junk -> None."""
    s = _text(cell)
    if not s or s in {"-", "--"}:
        return None
    try:
        v = round(float(s.replace(",", "")))
    except ValueError:
        return None
    if not (PAISE_MIN <= v <= PAISE_MAX):
        return None
    return int(v)


def _price_table(html: str) -> str:
    """The zone x day table, found by its header rather than its position.

    Deliberately not `tables[2]`. The page also carries a banner table and the
    month/year form, and a source that adds one more would silently shift the
    index — landing us on the wrong table with no error, which is exactly the
    failure a scraper must not have.
    """
    body = _SCRIPT_RE.sub("", html)
    for tbl in _TABLE_RE.findall(body):
        head = _ROW_RE.search(tbl)
        if head and "name of zone" in _text(head.group(0)).lower():
            return tbl
    raise ValueError("NECC sheet: no table with a 'Name Of Zone / Day' header "
                     "— the source has changed shape")


def parse_sheet(html: str, month: int, year: int) -> dict:
    """One month's sheet -> {"month", "year", "rows": [...]}.

    Each row is {"zone", "section", "days": {day: paise}, "avg": paise|None}.
    Days the month has not reached, and zones that skipped a day, are simply
    absent from `days` — never zero, never carried forward. A gap in this
    source is a gap, and inventing a number to fill it would be the one thing
    a price page can never do.
    """
    rows, section = [], "necc"
    for raw in _ROW_RE.findall(_price_table(html)):
        cells = _CELL_RE.findall(raw)
        if not cells:
            continue
        head = _text(cells[0])
        if len(cells) == 1:
            section = _SECTIONS.get(head.lower(), section)
            continue
        if head.lower().startswith("name of zone"):
            continue
        days = {}
        # cells[1:32] are days 1..31; the sheet always prints 31 columns and
        # fills the tail with "-" in a shorter month, so trusting the column
        # POSITION is safe where trusting the column COUNT would not be.
        for i, cell in enumerate(cells[1:32], start=1):
            v = _paise(cell)
            if v is not None:
                days[i] = v
        if not days:
            continue
        rows.append({
            "zone": head,
            "section": section,
            "days": days,
            "avg": _paise(cells[32]) if len(cells) > 32 else None,
        })
    if not rows:
        raise ValueError("NECC sheet: header found but no zone rows parsed")
    return {"month": month, "year": year, "rows": rows}


def fetch_month(month: int = 0, year: int = 0, timeout: int = 30) -> dict:
    """Fetch and parse one month. No arguments = the current month.

    The current month is a plain GET (that is what the page defaults to); any
    other month is the POST the form makes. Verified to need no __VIEWSTATE,
    so nothing here has to scrape a token out of a previous response.
    """
    if month and year:
        resp = requests.post(
            NECC_URL, timeout=timeout, headers={"User-Agent": _UA},
            data={"ddlMonth": f"{month:02d}", "ddlYear": str(year),
                  "rblReportType": "DailyReport", "btnReport": "Get Sheet"})
    else:
        today = date.today()
        month, year = today.month, today.year
        resp = requests.get(NECC_URL, timeout=timeout, headers={"User-Agent": _UA})
    resp.raise_for_status()
    sheet = parse_sheet(resp.text, month, year)
    log.info("NECC sheet %04d-%02d parsed | %d zones", year, month, len(sheet["rows"]))
    return sheet

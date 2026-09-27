# ============================================================
# backend/utils/desc_test.py
# KrashiMitra — the /bhav district description test
# ------------------------------------------------------------
# Question it answers: does quoting the price in the search snippet cost us
# the click? In the week to 24 Sep 2026, /bhav pages ranked #1 got 2.1% of
# clicks and #2-3 got 1.9%, while articles at #2-3 got 10.2%. The district
# description said "औसत ₹5,550/क्विंटल", so the searcher may already have
# the answer before clicking.
#
# Half the district pages (group B) drop that one figure from the meta
# description; everything else about the page stays the same. A page's group
# is a fixed hash of its URL, so Google always sees the same description for
# the same page, and tools/desc_test_report.py can recompute the groups from
# Search Console URLs alone.
#
# Read the result by position band, never overall: the two halves are
# random, but a few big pages can still tilt a plain average.
# ============================================================

import zlib

# The day the test went live. Search Console rows before this date (plus the
# time Google needs to recrawl a page) belong to the old description.
START = "2026-09-28"


def variant(cs: str, ss: str, ds: str) -> str:
    """'A' = description quotes the average price, 'B' = it does not."""
    return "B" if zlib.crc32(f"{cs}/{ss}/{ds}".encode()) % 2 else "A"

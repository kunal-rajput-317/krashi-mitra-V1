"""A /naksha state title may call itself a map of N districts only if the
map draws N districts.

The title answers "कितने जिले हैं" with today's checked count
(backend/data/district_counts.json), which can be ahead of the drawn map:
on 28 Sep 2026 Rajasthan's title read "41 जिलों का HD मानचित्र" over a map
of 33. Where districts are missing from the drawing, the count may appear
as a fact about the state ("41 जिले"), never as a fact about the image.
"""

import re

from backend.routes import naksha


def _title(html: str) -> str:
    return re.search(r"<title>(.*?)</title>", html).group(1)


def test_no_title_promises_a_map_of_undrawn_districts(db_engine):
    checked = 0
    for key, s in naksha._states().items():
        count, extra, _ = naksha._district_count(key, s)
        if not extra:
            continue
        title = _title(naksha._state_page(key, f"https://krashimitra.in/naksha/{key}")
                       .body.decode())
        assert "जिलों का" not in title, (key, title)
        assert str(count) in title, "the current count still answers the searcher"
        checked += 1
    assert checked, "district_counts.json lists no state with undrawn districts any more"

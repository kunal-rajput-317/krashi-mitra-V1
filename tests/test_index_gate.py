"""Thin-page index gate — which /bhav pages may claim a place in Google's index.

The failure this guards against is not a wrong number on a page. It is the
site quietly deindexing itself. Four things therefore have to hold.

OFF MEANS OFF. `enabled: false` is the shipped state, and while it is false
robots_for() must return "" for everything, no matter how stale. A missing or
corrupt config must also read as off — the failure mode of this feature has to
be "nothing happened", never "everything got noindexed".

NO DATE IS NOT STALE. Pre-migration rows carry no last-reported date. Absence
of evidence is not evidence of staleness, and those pages keep their place.

FOLLOW, ALWAYS. The pages stay live and their links keep feeding the rest of
the site; only the index claim is withdrawn. A robots value that ever came back
`nofollow` would be a different, worse change than the one intended.

AND THE COUNT MUST BE HONEST. split() is what gets read before flipping the
switch, so it has to count the same verdicts the pages will actually render —
including the state rollup, which is as fresh as its newest district.
"""

import json
from datetime import date, timedelta

import pytest

from backend.services import index_gate


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Point the loader at a throwaway JSON and clear its mtime cache."""
    def _write(payload) -> None:
        p = tmp_path / "index_gate.json"
        p.write_text(
            payload if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(index_gate, "_PATH", p)
        monkeypatch.setattr(index_gate, "_cache", None)
        monkeypatch.setattr(index_gate, "_mtime", -1.0)
    return _write


ON = {"enabled": True, "max_age_days": 30, "robots": "noindex, follow"}
TODAY = date(2026, 8, 23)


def iso(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


class TestOffMeansOff:
    def test_disabled_returns_no_robots_however_stale(self, cfg):
        cfg({**ON, "enabled": False})
        assert index_gate.robots_for(iso(5000), TODAY) == ""

    def test_missing_file_reads_as_off(self, tmp_path, monkeypatch):
        monkeypatch.setattr(index_gate, "_PATH", tmp_path / "nope.json")
        monkeypatch.setattr(index_gate, "_cache", None)
        monkeypatch.setattr(index_gate, "_mtime", -1.0)
        assert index_gate.is_enabled() is False
        assert index_gate.robots_for(iso(5000), TODAY) == ""

    def test_corrupt_json_reads_as_off(self, cfg):
        cfg("{ not json at all")
        assert index_gate.is_enabled() is False
        assert index_gate.robots_for(iso(5000), TODAY) == ""

    def test_verdict_is_still_computed_while_off(self, cfg):
        """The whole point of the dry run — /admin/index-gate must be able to
        show the split before anything is applied."""
        cfg({**ON, "enabled": False})
        assert index_gate.verdict(iso(400), TODAY)["index"] is False


class TestFreshnessVerdict:
    @pytest.fixture(autouse=True)
    def _on(self, cfg):
        cfg(ON)

    @pytest.mark.parametrize("days", [0, 1, 15, 29, 30])
    def test_within_the_window_keeps_the_index(self, days):
        assert index_gate.verdict(iso(days), TODAY)["index"] is True
        assert index_gate.robots_for(iso(days), TODAY) == ""

    @pytest.mark.parametrize("days", [31, 60, 400, 5000])
    def test_beyond_the_window_is_noindexed(self, days):
        assert index_gate.verdict(iso(days), TODAY)["index"] is False
        assert index_gate.robots_for(iso(days), TODAY) == "noindex, follow"

    def test_boundary_is_inclusive(self):
        """30d passes, 31d does not — pinned so a later refactor cannot move
        the cut by one day and silently change thousands of pages."""
        assert index_gate.verdict(iso(30), TODAY)["index"] is True
        assert index_gate.verdict(iso(31), TODAY)["index"] is False

    def test_threshold_is_configurable(self, cfg):
        cfg({**ON, "max_age_days": 90})
        assert index_gate.verdict(iso(60), TODAY)["index"] is True

    def test_future_date_is_clamped_not_treated_as_fresh_forever(self):
        """A feed artefact dated tomorrow must not produce a negative age that
        every comparison downstream reads as fresh."""
        assert index_gate.age_days(iso(-5), TODAY) == 0


class TestNoDateKeepsItsPlace:
    @pytest.fixture(autouse=True)
    def _on(self, cfg):
        cfg(ON)

    @pytest.mark.parametrize("value", ["", None, "not-a-date", "0000-00-00"])
    def test_unusable_date_is_indexable(self, value):
        v = index_gate.verdict(value, TODAY)
        assert v["index"] is True
        assert v["age_days"] is None
        assert v["reason"] == "no-date"
        assert index_gate.robots_for(value, TODAY) == ""


class TestRobotsValue:
    def test_follow_is_preserved(self, cfg):
        cfg(ON)
        assert "follow" in index_gate.robots_for(iso(400), TODAY)
        assert "nofollow" not in index_gate.robots_for(iso(400), TODAY)

    def test_falls_back_when_config_omits_it(self, cfg):
        cfg({"enabled": True, "max_age_days": 30})
        assert index_gate.robots_for(iso(400), TODAY) == "noindex, follow"

    def test_zero_or_negative_max_age_falls_back_to_the_default(self, cfg):
        """A 0 would noindex the entire site on the day it was typed."""
        cfg({**ON, "max_age_days": 0})
        assert index_gate.max_age_days() == 30
        cfg({**ON, "max_age_days": -5})
        assert index_gate.max_age_days() == 30

    def test_garbage_max_age_falls_back(self, cfg):
        cfg({**ON, "max_age_days": "soon"})
        assert index_gate.max_age_days() == 30


class TestSplit:
    @pytest.fixture(autouse=True)
    def _on(self, cfg):
        cfg(ON)

    DATES = {
        "wheat": {
            "uttar-pradesh": {
                "barabanki": iso(1),      # fresh
                "bareilly":  iso(20),     # fresh
                "hardoi":    iso(200),    # stale
            },
            "bihar": {
                "patna": iso(500),        # stale — and the whole state is stale
            },
        },
        "tomato": {
            "punjab": {
                "ludhiana": "",           # no date
            },
        },
    }

    def test_district_counts(self):
        out = index_gate.split(self.DATES, TODAY)
        assert out["district"] == {
            "index": 2, "noindex": 2, "no_date": 1,
            "total": 5, "pct_noindex": 40.0,
        }

    def test_state_rolls_up_to_its_newest_district(self):
        """UP has a 200-day-old district but a 1-day-old one too, so the state
        page stays indexed — the same rollup bhav_sitemap() uses for lastmod."""
        out = index_gate.split(self.DATES, TODAY)
        assert out["state"]["index"] == 1      # uttar-pradesh
        assert out["state"]["noindex"] == 1    # bihar
        assert out["state"]["no_date"] == 1    # punjab

    def test_age_buckets_show_what_a_different_cut_would_cost(self):
        out = index_gate.split(self.DATES, TODAY)
        assert out["buckets"]["0-7"] == 1
        assert out["buckets"]["8-30"] == 1
        assert out["buckets"]["91-365"] == 1
        assert out["buckets"]["365+"] == 1
        assert out["buckets"]["no-date"] == 1

    def test_reports_the_settings_it_judged_with(self):
        out = index_gate.split(self.DATES, TODAY)
        assert out["enabled"] is True
        assert out["max_age_days"] == 30
        assert out["robots"] == "noindex, follow"

    def test_empty_index_does_not_divide_by_zero(self):
        out = index_gate.split({}, TODAY)
        assert out["district"]["total"] == 0
        assert out["district"]["pct_noindex"] == 0.0


class TestShippedConfig:
    """Against the real data/index_gate.json."""

    @pytest.fixture(autouse=True)
    def _real(self, monkeypatch):
        monkeypatch.setattr(index_gate, "_cache", None)
        monkeypatch.setattr(index_gate, "_mtime", -1.0)

    def test_ships_disabled(self):
        """It must reach production switched off. Turning it on is a decision
        taken after reading /admin/index-gate, not a side effect of deploying."""
        assert index_gate.is_enabled() is False

    def test_ships_with_a_sane_threshold_and_follow(self):
        assert index_gate.max_age_days() == 30
        assert index_gate.robots_value() == "noindex, follow"

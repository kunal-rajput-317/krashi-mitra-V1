"""Crop-type registry — which /bhav layout a crop's sale cadence earns it.

Three things have to hold, and each of them is a way this could quietly go
wrong rather than fail loudly.

A crop nobody has classified must render EXACTLY as it does today. The whole
point of putting the type in a registry instead of the URL was that 5,624
ranking pages should not move; a resolver that guessed on unknown crops would
give that up for nothing.

The reported `source` must match the path actually taken. A keyword rule that
resolves to the default type is still a rule match — inferring the source
afterwards by comparing against the default reports those as unclassified and
hides the rule, which is exactly how a bad keyword would stay invisible.

And a broken registry must degrade to today's layout, never to an exception.
This resolver runs on every /bhav render.
"""

import json

import pytest

from backend.services import crop_types


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """Point the loader at a throwaway JSON and clear its mtime cache."""
    def _write(payload) -> None:
        p = tmp_path / "crop_types.json"
        p.write_text(
            payload if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        monkeypatch.setattr(crop_types, "_PATH", p)
        monkeypatch.setattr(crop_types, "_cache", None)
        monkeypatch.setattr(crop_types, "_mtime", -1.0)
    return _write


TOY = {
    "default": "staple",
    "types": {
        "perishable": {"hi": "जल्दी खराब", "layout": "daily", "cadence_days": 1},
        "storable":   {"hi": "भंडारण योग्य", "layout": "holding", "cadence_days": 7},
        "staple":     {"hi": "मुख्य फसल", "layout": "season", "cadence_days": 90},
    },
    "crops": {"tomato": "perishable", "potato": "storable", "wheat": "staple"},
    "rules": [
        {"match": ["-gourd"], "type": "perishable"},
        {"match": ["-dal"], "type": "staple"},
    ],
}


class TestResolution:
    def test_explicit_wins(self, registry):
        registry(TOY)
        assert crop_types.crop_type("tomato") == "perishable"
        assert crop_types.crop_type("potato") == "storable"

    def test_rule_catches_the_long_tail(self, registry):
        registry(TOY)
        assert crop_types.crop_type("bottle-gourd") == "perishable"

    def test_explicit_beats_a_rule_that_would_also_match(self, registry):
        """A curated answer must not be overridden by a keyword that happens to
        appear in the slug — the reason bay-leaf-tejpatta is storable and not
        perishable despite containing 'leaf'."""
        registry({**TOY, "crops": {**TOY["crops"], "ivy-gourd": "storable"}})
        assert crop_types.crop_type("ivy-gourd") == "storable"

    def test_rules_are_ordered_first_match_wins(self, registry):
        registry({**TOY, "rules": [
            {"match": ["dry"], "type": "storable"},
            {"match": ["-gourd"], "type": "perishable"},
        ]})
        assert crop_types.crop_type("dry-gourd") == "storable"

    @pytest.mark.parametrize("slug", ["Tomato", "  tomato  ", "tomato", "TOMATO"])
    def test_slug_normalised(self, registry, slug):
        registry(TOY)
        assert crop_types.crop_type(slug) == "perishable"


class TestUnknownCropsKeepTodaysLayout:
    """The guarantee that made a registry cheaper than a URL migration."""

    def test_unclassified_crop_falls_to_default(self, registry):
        registry(TOY)
        assert crop_types.crop_type("gokhru") == "staple"
        assert crop_types.layout_for("gokhru") == "season"

    def test_empty_slug_is_not_an_error(self, registry):
        registry(TOY)
        assert crop_types.crop_type("") == "staple"

    def test_default_naming_a_type_that_does_not_exist_is_ignored(self, registry):
        """A typo in `default` must not poison every lookup on the site."""
        registry({**TOY, "default": "perishble"})
        assert crop_types.crop_type("gokhru") == "staple"

    def test_crops_entry_naming_an_unknown_type_is_ignored(self, registry):
        registry({**TOY, "crops": {"tomato": "perishble"}})
        assert crop_types.crop_type("tomato") == "staple"

    def test_rule_naming_an_unknown_type_is_skipped_not_fatal(self, registry):
        registry({**TOY, "rules": [
            {"match": ["-gourd"], "type": "nonsense"},
            {"match": ["-gourd"], "type": "perishable"},
        ]})
        assert crop_types.crop_type("bottle-gourd") == "perishable"


class TestBrokenRegistryDegrades:
    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(crop_types, "_PATH", tmp_path / "nope.json")
        monkeypatch.setattr(crop_types, "_cache", None)
        monkeypatch.setattr(crop_types, "_mtime", -1.0)
        assert crop_types.crop_type("tomato") == "staple"
        assert crop_types.layout_for("tomato") == "season"

    def test_corrupt_json(self, registry):
        registry("{ this is not json")
        assert crop_types.crop_type("tomato") == "staple"

    def test_no_types_declared(self, registry):
        registry({"crops": {"tomato": "perishable"}})
        assert crop_types.crop_type("tomato") == "staple"


class TestSourceReportingIsHonest:
    """`source` has to describe the path actually taken, or the admin view is
    a lie and a mis-typing keyword rule stays invisible."""

    def test_explicit_reported_as_explicit(self, registry):
        registry(TOY)
        assert crop_types.classify(["tomato"])[0]["source"] == "explicit"

    def test_rule_reported_as_rule_with_the_keyword(self, registry):
        registry(TOY)
        row = crop_types.classify(["bottle-gourd"])[0]
        assert row["source"] == "rule"
        assert row["matched"] == "-gourd"

    def test_rule_resolving_to_the_default_type_is_still_a_rule(self, registry):
        """The regression this class exists for. '-dal' resolves to `staple`,
        which IS the default — reported as "default" it would look like nothing
        classified it, and the rule could be silently wrong forever."""
        registry(TOY)
        row = crop_types.classify(["moong-dal"])[0]
        assert row["type"] == "staple"
        assert row["source"] == "rule"
        assert row["matched"] == "-dal"

    def test_default_reported_as_default_with_no_keyword(self, registry):
        registry(TOY)
        row = crop_types.classify(["gokhru"])[0]
        assert row["source"] == "default"
        assert row["matched"] == ""

    def test_is_explicit_agrees_with_classify(self, registry):
        registry(TOY)
        assert crop_types.is_explicit("tomato") is True
        assert crop_types.is_explicit("bottle-gourd") is False
        assert crop_types.is_explicit("gokhru") is False


class TestMetadata:
    def test_layout_for_maps_through_the_type(self, registry):
        registry(TOY)
        assert crop_types.layout_for("tomato") == "daily"
        assert crop_types.layout_for("potato") == "holding"
        assert crop_types.layout_for("wheat") == "season"

    def test_type_meta_of_an_unknown_type_returns_the_default(self, registry):
        registry(TOY)
        assert crop_types.type_meta("nonsense")["key"] == "staple"

    def test_all_types_lists_every_declared_type(self, registry):
        registry(TOY)
        assert set(crop_types.all_types()) == {"perishable", "storable", "staple"}


class TestShippedRegistry:
    """Against the real data/crop_types.json, not a toy."""

    @pytest.fixture(autouse=True)
    def _real(self, monkeypatch):
        monkeypatch.setattr(crop_types, "_cache", None)
        monkeypatch.setattr(crop_types, "_mtime", -1.0)

    def test_parses_and_declares_the_three_cadences(self):
        assert set(crop_types.all_types()) == {"perishable", "storable", "staple"}

    @pytest.mark.parametrize("slug, expected", [
        # The commodities that carry the traffic — these are the ones a wrong
        # answer would actually be seen on.
        ("wheat", "staple"), ("mustard", "staple"), ("paddy-common", "staple"),
        ("garlic", "storable"), ("onion", "storable"), ("potato", "storable"),
        ("tomato", "perishable"), ("green-chilli", "perishable"),
        ("coriander-leaves", "perishable"), ("bottle-gourd", "perishable"),
    ])
    def test_top_commodities(self, slug, expected):
        assert crop_types.crop_type(slug) == expected

    @pytest.mark.parametrize("slug, expected", [
        # Dried forms that a naive 'leaf'/'leaves' rule reads as fresh produce.
        ("bay-leaf-tejpatta", "storable"),
        ("tendu-leaves-kendu-leaves-bidi-leaves", "storable"),
        ("dry-chillies", "storable"),
        ("ginger-dry", "storable"),
        # ...and a spice seed, which must beat the generic 'seed' rule.
        ("cummin-seed-jeera", "storable"),
    ])
    def test_dried_forms_are_not_perishable(self, slug, expected):
        assert crop_types.crop_type(slug) == expected

    def test_every_explicit_entry_names_a_declared_type(self):
        declared = set(crop_types.all_types())
        data = crop_types._load()
        bad = {k: v for k, v in (data.get("crops") or {}).items() if v not in declared}
        assert not bad, f"crops{{}} names undeclared types: {bad}"

    def test_every_rule_names_a_declared_type(self):
        declared = set(crop_types.all_types())
        bad = [r for r in (crop_types._load().get("rules") or [])
               if r.get("type") not in declared]
        assert not bad, f"rules[] name undeclared types: {bad}"

    def test_no_explicit_entry_is_redundant_with_its_own_rule(self):
        """An explicit entry that a rule would have reached anyway is fine, but
        one that CONTRADICTS its rule is the interesting case — it is load-
        bearing, and deleting it silently changes the crop's layout. This test
        just pins that such entries exist and stay explicit."""
        for slug in ("bay-leaf-tejpatta", "tendu-leaves-kendu-leaves-bidi-leaves"):
            assert crop_types.is_explicit(slug), (
                f"{slug} relies on being explicit — a keyword rule would type it "
                f"as perishable")

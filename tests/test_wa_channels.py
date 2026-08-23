"""राज्यवार WhatsApp चैनल — the join link on every /bhav district page.

Two things have to hold. A state whose channel does not exist yet must keep the
old "message us" card, because a broken invite is worse than no invite. And the
card's tracking attribute must survive being an HTML attribute — the JSON
payload carries double quotes, the attribute is double-quoted, and the raw
version of this markup ended the attribute early.
"""

import json

import pytest

from backend.routes import bhav
from backend.services import wa_channels


@pytest.fixture
def channels(tmp_path, monkeypatch):
    """Point the loader at a throwaway JSON and clear its mtime cache."""
    def _write(mapping: dict):
        p = tmp_path / "wa_channels.json"
        p.write_text(json.dumps({"channels": mapping}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(wa_channels, "_PATH", p)
        monkeypatch.setattr(wa_channels, "_cache", None)
        monkeypatch.setattr(wa_channels, "_mtime", -1.0)
        return p
    return _write


class TestKey:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Uttar Pradesh", "uttar_pradesh"),
            ("uttar-pradesh", "uttar_pradesh"),
            ("Keralam", "kerala"),           # Agmarknet's spelling
            ("Chattisgarh", "chhattisgarh"),
            ("Uttrakhand", "uttarakhand"),
            ("NCT of Delhi", "delhi"),
            ("Pondicherry", "puducherry"),
            ("", ""),
        ],
    )
    def test_normalises(self, raw, expected):
        assert wa_channels._key(raw) == expected

    def test_handle_default(self):
        assert wa_channels.handle("Madhya Pradesh") == "krashimitra_madhya_pradesh"


class TestChannelFor:
    def test_blank_url_is_no_channel(self, channels):
        """The shipped JSON seeds every state with an empty url. Empty must not
        render as a link."""
        channels({"bihar": {"name": "krashimitra_bihar", "url": ""}})
        assert wa_channels.channel_for("Bihar") is None

    def test_unknown_state(self, channels):
        channels({})
        assert wa_channels.channel_for("Bihar") is None

    def test_non_https_ignored(self, channels):
        channels({"bihar": {"url": "javascript:alert(1)"}})
        assert wa_channels.channel_for("Bihar") is None

    def test_live_channel(self, channels):
        channels({"bihar": {"name": "krashimitra_br", "url": "https://whatsapp.com/channel/AB"}})
        got = wa_channels.channel_for("Bihar")
        assert got == {"name": "krashimitra_br", "url": "https://whatsapp.com/channel/AB"}

    def test_name_defaults_to_handle(self, channels):
        channels({"bihar": {"url": "https://whatsapp.com/channel/AB"}})
        assert wa_channels.channel_for("Bihar")["name"] == "krashimitra_bihar"

    def test_agmarknet_spelling_finds_the_channel(self, channels):
        """The feed sends 'Keralam'; the JSON is keyed 'kerala'."""
        channels({"kerala": {"url": "https://whatsapp.com/channel/KL"}})
        assert wa_channels.channel_for("Keralam") is not None

    def test_live_lists_only_working_links(self, channels):
        channels({"bihar": {"url": "https://whatsapp.com/channel/AB"},
                  "punjab": {"url": ""}})
        assert list(wa_channels.live()) == ["bihar"]


class TestCard:
    def test_channel_card_links_to_the_invite(self, channels):
        channels({"madhya_pradesh": {"name": "krashimitra_mp",
                                     "url": "https://whatsapp.com/channel/MP1"}})
        html = bhav._wa_daily("धान", "Raisen", "Madhya Pradesh")
        assert "https://whatsapp.com/channel/MP1" in html
        assert "krashimitra_mp" in html
        assert "मध्य प्रदेश" in html
        assert "wa.me" not in html

    def test_falls_back_when_state_has_no_channel(self, channels):
        channels({"madhya_pradesh": {"url": ""}})
        html = bhav._wa_daily("धान", "Raisen", "Madhya Pradesh")
        assert f"wa.me/{bhav._WA_NUMBER}" in html
        assert "whatsapp.com/channel" not in html

    @pytest.mark.parametrize("state", ["Madhya Pradesh", ""])
    def test_onclick_never_breaks_the_attribute(self, channels, state):
        """The JSON payload's quotes must be escaped, or the browser ends the
        attribute at the first one and the rest becomes stray markup."""
        channels({"madhya_pradesh": {"url": "https://whatsapp.com/channel/MP1"}})
        html = bhav._wa_daily("धान", "Raisen", state)
        attr = html.split('onclick="', 1)[1].split('"', 1)[0]
        assert "kmTrack" in attr and "&quot;" in attr


class TestShippedFile:
    def test_json_is_valid_and_keyed_consistently(self):
        spec = json.loads(wa_channels._PATH.read_text(encoding="utf-8"))
        chans = spec["channels"]
        assert len(chans) >= 30, "every state a farmer can land on needs a row"
        for key, row in chans.items():
            assert wa_channels._key(key) == key, f"{key} is not a normalised key"
            assert set(row) >= {"state", "name", "url"}, key
            assert row["url"] == "" or row["url"].startswith("https://whatsapp.com/"), key

    def test_every_state_bhav_can_render_is_covered(self):
        """A state in the price feed with no row here can never get a channel.

        Andaman & Nicobar and Puducherry are deliberately out: too few mandi
        readers to be worth running a channel for. They fall back to the
        message-us card like any state whose url is still blank, which is why
        dropping a row is safe."""
        NO_CHANNEL = {"andaman_and_nicobar", "puducherry"}
        chans = json.loads(wa_channels._PATH.read_text(encoding="utf-8"))["channels"]
        missing = sorted({wa_channels._key(s) for s in bhav._HI_STATES}
                         - set(chans) - NO_CHANNEL)
        assert not missing, missing
        assert not (NO_CHANNEL & set(chans)), "dropped states must stay dropped"

    def test_every_link_is_a_distinct_channel(self):
        """Two states pointing at one invite means somebody pasted twice — the
        farmer joins the wrong state's channel and every number he reads is
        for a mandi he cannot reach."""
        chans = json.loads(wa_channels._PATH.read_text(encoding="utf-8"))["channels"]
        urls = [r["url"] for r in chans.values() if r["url"]]
        dupes = {u for u in urls if urls.count(u) > 1}
        assert not dupes, dupes

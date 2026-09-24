"""The 🔔 bhav alert must stay deliverable, and its copy must stay true.

On 2026-07-27 commit 1c175c5 deleted `push_enabled()` from push_service while
leaving both of its call sites. `run_mandi_alerts()` then raised NameError on
its very first line, and mandi_scheduler's `except Exception` logged it as
"non-fatal". Nothing else noticed: the /health/checks alert probe reported
"भाव अलर्ट भेजने को तैयार" purely because the VAPID keys existed.

57 days later there were 74 active alerts across 70 live push subscriptions and
`last_notified_on` was NULL on every single row — not one farmer had ever been
notified. The acquisition side was working; delivery had never run once.

These tests fail on the two ways that can happen again: the pass not running at
all, and the pass running but saying something untrue.
"""

from datetime import date

import pytest

from backend.services import push_service as ps


# ── the regression itself ────────────────────────────────────

def test_push_enabled_exists():
    """The deleted function. Call it — a module-level name that is referenced
    but never defined only fails when the line actually executes."""
    assert callable(ps.push_enabled)
    assert isinstance(ps.push_enabled(), bool)


def test_alert_pass_runs_without_nameerror(monkeypatch):
    """The whole pass must reach its own return, not die on an undefined name.

    Forced through the enabled path with VAPID set, because the bug lived after
    the `if not push_enabled()` guard: a deployment with no keys would have
    returned early and looked fine."""
    monkeypatch.setattr(ps, "VAPID_PUBLIC_KEY", "test-public")
    monkeypatch.setattr(ps, "VAPID_PRIVATE_KEY", "test-private")
    monkeypatch.setattr(ps, "send_push", lambda db, sub, payload: False)

    result = ps.run_mandi_alerts()
    assert isinstance(result, dict)
    assert "sent" in result and "enabled" in result


def test_scheduler_still_calls_the_pass():
    """The fix is worthless if nothing invokes it."""
    from pathlib import Path
    src = Path("backend/services/mandi_scheduler.py").read_text(encoding="utf-8")
    assert "run_mandi_alerts()" in src


# ── the copy must not claim a date it does not have ──────────

TODAY = date(2026, 9, 22)


@pytest.mark.parametrize("data_iso,expected", [
    ("2026-09-22", "आज"),
    ("2026-09-21", "कल"),
    ("",           ""),
    ("garbage",    ""),
    (None,         ""),
])
def test_when_word(data_iso, expected):
    assert ps._when_word(data_iso, TODAY) == expected


def test_old_price_is_dated_never_called_today():
    """Roughly half of all mandi×crop pairs get no fresh report on a given day
    and the snapshot carries the last price forward. Saying "आज" over one of
    those is a false claim about the farmer's own market."""
    assert ps._when_word("2026-09-15", TODAY) == "15 सितंबर"


class _Alert:
    """Minimal stand-in — _payload_for_group only reads these fields."""
    id = 1
    user_id = None
    subscription_id = 1
    commodity = "Wheat"
    state = "Uttar Pradesh"
    district = "Varanasi"
    last_price = None


def test_stale_price_body_carries_its_real_date():
    payload = ps._payload_for_group([(_Alert(), 2500, -0.9, "2026-09-19")], TODAY)
    assert "आज" not in payload["body"]
    assert "19 सितंबर" in payload["body"]


def test_todays_price_may_say_today():
    payload = ps._payload_for_group([(_Alert(), 2500, -0.9, "2026-09-22")], TODAY)
    assert payload["body"].startswith("आज")


def test_undated_price_claims_no_day_at_all():
    """An unparseable feed date must drop the time word, not guess at one."""
    payload = ps._payload_for_group([(_Alert(), 2500, -0.9, "")], TODAY)
    assert "आज" not in payload["body"] and "कल" not in payload["body"]


# ── the copy must stay in one script ─────────────────────────

def test_place_name_is_devanagari_not_the_feed_spelling():
    """The feed names districts in English. An untranslated label produced
    "आज Bijnor में गेहूं के भाव" — one sentence in two scripts."""
    payload = ps._payload_for_group([(_Alert(), 2500, -0.9, "2026-09-22")], TODAY)
    assert "Varanasi" not in payload["body"] and "Varanasi" not in payload["title"]
    assert "वाराणसी" in payload["body"]


# ── the operator switch must fail safe ───────────────────────

def test_sending_switch_defaults_to_on():
    """A settings read that fails, or a database with no row yet, must leave the
    shipped behaviour in place — never silently disable delivery."""
    from backend.services.app_settings import DEFAULTS
    assert DEFAULTS["alerts.sending_enabled"] is True
    assert DEFAULTS["alerts.bell_visible"] is True


# ── the custom broadcast must not go out by accident ─────────

def test_broadcast_flags_a_hand_typed_price():
    """Every other number on this site comes from the feed with its own date. A
    broadcast is the one place a price can be typed from memory and land on 70
    lock screens looking exactly like a real bhav alert."""
    from backend.routes.admin import _price_claim_warning as warn
    assert warn("गेहूं ₹2500 पर बिक रहा है")
    assert warn("धान 2400 रुपये")
    assert warn("भाव 2,150/क्विंटल")


def test_broadcast_does_not_flag_ordinary_numbers():
    """A warning on every message would be a warning nobody reads."""
    from backend.routes.admin import _price_claim_warning as warn
    assert warn("कल मंडी बंद रहेगी") is None
    assert warn("आज 5 मंडियां खुलीं") is None


def test_broadcast_defaults_to_a_dry_run():
    """The default must be the harmless one. A caller that forgets `dry` should
    get a preview, never a delivery."""
    from backend.routes.admin import BroadcastIn
    assert BroadcastIn(title="t", body="b").dry is True
    assert BroadcastIn(title="t", body="b").expect_recipients is None


def test_broadcast_payload_has_its_own_tag():
    """A broadcast must not replace a price alert already in the tray."""
    from pathlib import Path
    src = Path("backend/routes/admin.py").read_text(encoding="utf-8")
    assert '"tag": "km-broadcast"' in src


def test_admin_off_does_not_consume_the_day(monkeypatch):
    """Switching sending off must not stamp last_notified_on, or switching it
    back on would skip everything until tomorrow."""
    monkeypatch.setattr(ps, "VAPID_PUBLIC_KEY", "test-public")
    monkeypatch.setattr(ps, "VAPID_PRIVATE_KEY", "test-private")
    import backend.services.app_settings as cfg
    monkeypatch.setattr(cfg, "get_all",
                        lambda: {**cfg.DEFAULTS, "alerts.sending_enabled": False})

    result = ps.run_mandi_alerts()
    assert result["sent"] == 0
    assert result.get("deferred") == "admin_off"

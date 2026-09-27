# ============================================================
# backend/services/alert_stop.py
# KrashiMitra — the one-tap "🔕 बंद करें" on a भाव अलर्ट push
# ------------------------------------------------------------
# LEGAL_RULES §7: every alert has a way to stop it. Until 28 Sep 2026 the only
# ways were tapping the 🔔 again on the right /bhav page, or blocking
# notifications for the whole site in the browser. A farmer who no longer
# wants the wheat price should be able to say so on the notification itself.
#
# The notification is shown by the service worker, which cannot see the
# farmer's login token, and /alerts/mandi/off needs that token for an
# account's alerts. So each push carries a signed stop token naming exactly
# the alerts it reports on. POST /alerts/mandi/stop switches those off and
# nothing else. Tokens do not expire: a stop link must always work.
#
# Signed with a key derived from JWT_SECRET, like services/pay_links.py.
# Without a real secret (a local run with the public repo default) no token
# is made and the push simply has no stop button; production refuses to boot
# with that default anyway (utils/security.py).
# ============================================================

import base64
import hashlib
import hmac
import os

_PUBLIC_DEFAULT = "change_this_secret_in_production"
_SIG_BYTES = 12


def _key() -> bytes:
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if not secret or secret == _PUBLIC_DEFAULT:
        return b""
    return hmac.new(secret.encode(), b"krashimitra-alert-stop-v1", hashlib.sha256).digest()


def _sign(body: str) -> str:
    raw = hmac.new(_key(), body.encode(), hashlib.sha256).digest()[:_SIG_BYTES]
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def token(alert_ids) -> str | None:
    """'12,40.<sig>' for these alert ids, or None when there is no key."""
    ids = sorted({int(i) for i in alert_ids if i is not None})
    if not ids or not _key():
        return None
    body = ",".join(str(i) for i in ids)
    return f"{body}.{_sign(body)}"


def ids_from(tok: str) -> list[int] | None:
    """The alert ids a token names, or None if it is not one we signed.
    compare_digest, never ==."""
    if not _key() or not tok or tok.count(".") != 1:
        return None
    body, sig = tok.split(".")
    if not hmac.compare_digest(_sign(body), sig):
        return None
    try:
        ids = [int(x) for x in body.split(",")]
    except ValueError:
        return None
    return ids or None

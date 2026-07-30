# ============================================================
# utils/logging_config.py
# KrashiMitra — Central logging setup
#
# The backend grew up on print(). Render captures stdout either way, so
# nothing was *lost* — but print() has no level, so a routine "fetched 812
# rows" and a real "DB write failed" are indistinguishable in the log stream,
# and there is no way to quiet one without deleting the line. This module
# gives every module a real logger, one format, and a level knob.
#
# Call setup_logging() once, before any router is imported, so library
# loggers configured at import time inherit our handler rather than the
# root default.
# ============================================================

import logging
import os
import sys
import uuid
from contextvars import ContextVar

# Correlates every log line emitted while handling one request. Without it,
# concurrent requests interleave and a traceback can't be tied back to the
# request that caused it.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def _install_record_factory() -> None:
    """Stamp `request_id` onto every LogRecord at creation time.

    A record factory rather than a logging.Filter: a filter attached to a
    handler only runs when *that* handler processes the record, so whether the
    attribute exists depends on handler ordering — under pytest's caplog, for
    instance, a second handler can receive the record before ours has run.
    The factory runs once, before any handler sees it, so every record from
    every library (httpx, apscheduler, sqlalchemy) carries the field and the
    formatter can never raise KeyError on it.
    """
    existing = logging.getLogRecordFactory()

    # Guard against double-wrapping if setup_logging is somehow re-entered.
    if getattr(existing, "_krashimitra_request_id", False):
        return

    def factory(*args, **kwargs):
        record = existing(*args, **kwargs)
        record.request_id = request_id_var.get()
        return record

    factory._krashimitra_request_id = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Libraries that log one INFO line per operation. At INFO these drown the
# app's own output — httpx logs every outbound AI/weather call, and
# apscheduler logs every job wake-up on a 3-hour timer.
_NOISY = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "urllib3": logging.WARNING,
    "apscheduler.executors.default": logging.WARNING,
    "apscheduler.scheduler": logging.WARNING,
    "sentence_transformers": logging.WARNING,
    "chromadb": logging.WARNING,
}

_configured = False


def setup_logging() -> None:
    """Idempotent — safe to call from both main.py and the test fixtures."""
    global _configured
    if _configured:
        return

    # LOG_LEVEL wins; otherwise DEBUG locally and INFO on Render, so a dev box
    # is chatty and production isn't.
    level_name = os.getenv("LOG_LEVEL", "").strip().upper()
    if not level_name:
        is_prod = bool(os.getenv("RENDER"))
        level_name = "INFO" if is_prod else "DEBUG"
    level = getattr(logging, level_name, logging.INFO)

    _install_record_factory()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    # Replace rather than append: uvicorn installs its own handler, and
    # keeping both prints every line twice.
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    for name, lvl in _NOISY.items():
        logging.getLogger(name).setLevel(lvl)

    # uvicorn.access duplicates what our request middleware already logs.
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    _configured = True
    logging.getLogger(__name__).debug("logging configured at %s", level_name)

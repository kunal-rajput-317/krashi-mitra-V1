# ============================================================
# backend/utils/indexnow.py
# KrashiMitra — IndexNow: push changed URLs to Bing/Yandex/etc.
#
# IndexNow (indexnow.org) is the one legitimate "index many pages now"
# mechanism: POST a URL list and every participating engine (Bing → also
# ChatGPT search / Copilot / DuckDuckGo, Yandex, Seznam, Naver) crawls it
# within hours instead of weeks. Google does NOT participate — Google
# discovery stays sitemap + internal links.
#
# The mandi snapshot changes on every successful data.gov fetch (5×/day),
# which changes every /bhav page, so the scheduler pings after each
# successful fetch (see mandi_scheduler._fetch_and_notify). The protocol
# asks that you submit URLs *when their content changes* — that is exactly
# our trigger, throttled to at most one ping per 2h in case the staleness
# watchdog fires runs back-to-back.
#
# Auth: the key in the payload must match the file served at
# https://krashimitra.in/{KEY}.txt — that file lives in frontend/ (Netlify
# serves frontend/ at the site root). If you rotate INDEXNOW_KEY, add the
# matching frontend/{key}.txt in the same commit or every ping 403s.
#
# Prod-only: a dev laptop running the scheduler must not ping for the
# public host, so anything without RENDER set only logs what it would do.
# ============================================================

import logging
import os
import time

import requests

logger = logging.getLogger("krishi.indexnow")

KEY = os.getenv("INDEXNOW_KEY", "d28e313b91a979ef7cf2522dd07a700b")
HOST = "krashimitra.in"
SITE = f"https://{HOST}"
ENDPOINT = "https://api.indexnow.org/indexnow"

_CHUNK = 10_000          # protocol max per POST
_MIN_INTERVAL = 2 * 3600  # seconds between pings (watchdog can double-fire)
_last_ping: float = 0.0


def submit(urls: list) -> bool:
    """POST a URL list to IndexNow. Returns True if every chunk was accepted
    (200/202). Never raises — indexing pings must not break the data fetch."""
    if not urls:
        return True
    if not os.getenv("RENDER"):
        logger.info(f"[dev] IndexNow skipped — would submit {len(urls)} URLs")
        return True
    ok = True
    for i in range(0, len(urls), _CHUNK):
        payload = {
            "host": HOST,
            "key": KEY,
            "keyLocation": f"{SITE}/{KEY}.txt",
            "urlList": urls[i:i + _CHUNK],
        }
        try:
            res = requests.post(ENDPOINT, json=payload, timeout=30)
            if res.status_code in (200, 202):
                logger.info(f"✅ IndexNow accepted {len(payload['urlList'])} URLs "
                            f"({res.status_code})")
            else:
                # 403 = key file mismatch, 422 = URLs don't match host, 429 = spam
                logger.error(f"❌ IndexNow rejected chunk: {res.status_code} "
                             f"{res.text[:200]}")
                ok = False
        except requests.RequestException as e:
            logger.error(f"❌ IndexNow POST failed: {e}")
            ok = False
    return ok


def _bhav_urls() -> list:
    """Every /bhav URL, same walk as /bhav/sitemap.xml (import here, not at
    module top, to keep utils→routes off the import-time dependency graph)."""
    from backend.routes.bhav import _get_index, _is_crop
    idx = _get_index()
    urls = [f"{SITE}/bhav"]
    for cs, cn in sorted(idx.get("crops", {}).items()):
        if not _is_crop(cn):
            continue
        urls.append(f"{SITE}/bhav/{cs}")
        for ss in sorted(idx["states"].get(cs, {})):
            urls.append(f"{SITE}/bhav/{cs}/{ss}")
            for ds in sorted(idx["dists"].get(cs, {}).get(ss, {})):
                urls.append(f"{SITE}/bhav/{cs}/{ss}/{ds}")
    return urls


def ping_bhav() -> bool:
    """Submit every /bhav URL; throttled. Called after each successful mandi
    fetch — the prices moved, so the pages genuinely changed."""
    global _last_ping
    now = time.time()
    if now - _last_ping < _MIN_INTERVAL:
        logger.info("IndexNow throttled (pinged <2h ago)")
        return True
    _last_ping = now
    return submit(_bhav_urls())

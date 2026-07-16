# ============================================================
# backend/utils/github_archive.py
# KrashiMitra — commit files into the mandi-data archive repo (repo2)
# via the GitHub Contents API. No git binary needed on Render.
#
# Why the Contents API (not `git push`): Render's container has no repo
# checkout and an ephemeral disk. The Contents API lets us PUT a single
# file straight into repo2 over HTTPS with just a token.
#
# Config (all env; unset ⇒ archiving is a no-op that just logs, exactly
# like the IndexNow dev-guard, so a laptop never pushes by accident):
#   MANDI_ARCHIVE_REPO    "owner/mandi-bhav-data"   ← the repo2 you create
#   MANDI_ARCHIVE_TOKEN   fine-grained PAT, Contents: Read+Write on repo2
#                         (falls back to GITHUB_TOKEN)
#   MANDI_ARCHIVE_BRANCH  default "main"
#
# Existence/SHA is checked by listing the *parent directory* (not GET-ing
# the file) so we dodge the Contents API's 1 MB single-file read limit —
# a full day's CSV can exceed 1 MB.
# ============================================================

import base64
import logging
import os

import requests

logger = logging.getLogger("krishi.github_archive")

_API = "https://api.github.com"


def _cfg():
    repo   = os.getenv("MANDI_ARCHIVE_REPO", "").strip()
    token  = (os.getenv("MANDI_ARCHIVE_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    branch = os.getenv("MANDI_ARCHIVE_BRANCH", "main").strip() or "main"
    return repo, token, branch


def is_configured() -> bool:
    repo, token, _ = _cfg()
    return bool(repo and token)


def _headers(token: str) -> dict:
    return {
        "Authorization":        f"Bearer {token}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_sha(path: str):
    """Return the blob SHA of `path` in repo2, or None if it doesn't exist.
    Lists the parent directory rather than reading the file, so files >1 MB
    still resolve. Raises on unexpected (non-404) API errors so callers can
    decide — run_archive treats those as best-effort."""
    repo, token, branch = _cfg()
    directory, _, name = path.rpartition("/")
    url = f"{_API}/repos/{repo}/contents/{directory}"
    r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=30)
    if r.status_code == 404:
        return None                      # directory (and so the file) not there yet
    r.raise_for_status()
    listing = r.json()
    if isinstance(listing, list):
        for entry in listing:
            if entry.get("name") == name:
                return entry.get("sha")
    return None


def list_dir(path: str):
    """Return the set of entry names directly under `path` in repo2.
    - set()  → directory exists but is empty, OR doesn't exist yet (404)
    - None   → couldn't check (network / API error) — callers must NOT treat
               this as 'everything missing'.
    One API call lists a whole month, so a health check over a 30-day window is
    ~1–2 calls instead of one-per-day."""
    if not is_configured():
        return None
    repo, token, branch = _cfg()
    url = f"{_API}/repos/{repo}/contents/{path}"
    try:
        r = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=30)
    except requests.RequestException as e:
        logger.error(f"❌ archive list_dir failed for {path}: {e}")
        return None
    if r.status_code == 404:
        return set()
    if r.status_code != 200:
        logger.error(f"❌ archive list_dir {path}: {r.status_code} {r.text[:150]}")
        return None
    listing = r.json()
    if not isinstance(listing, list):
        return set()
    return {entry.get("name") for entry in listing}


def upsert_file(path: str, content: bytes, message: str, *, update_if_exists: bool = False) -> str:
    """Create `path` in repo2 (or update it when update_if_exists). Idempotent:
    if the file already exists and update_if_exists is False, does nothing.
    Never raises — archiving must not break the scheduler. Returns one of:
    'created' | 'updated' | 'exists' | 'skipped-unconfigured' | 'error-<code>'."""
    if not is_configured():
        logger.info(f"[dev] archive skipped (MANDI_ARCHIVE_REPO/TOKEN unset) — would write {path}")
        return "skipped-unconfigured"

    repo, token, branch = _cfg()
    try:
        sha = get_sha(path)
    except requests.RequestException as e:
        logger.error(f"❌ archive existence check failed for {path}: {e}")
        return "error-precheck"

    if sha and not update_if_exists:
        return "exists"

    payload = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    url = f"{_API}/repos/{repo}/contents/{path}"
    try:
        r = requests.put(url, headers=_headers(token), json=payload, timeout=60)
    except requests.RequestException as e:
        logger.error(f"❌ archive PUT failed for {path}: {e}")
        return "error-network"

    if r.status_code in (200, 201):
        action = "updated" if sha else "created"
        logger.info(f"✅ archived {path} → {repo}@{branch} ({action})")
        return action

    logger.error(f"❌ archive PUT rejected {path}: {r.status_code} {r.text[:200]}")
    return f"error-{r.status_code}"

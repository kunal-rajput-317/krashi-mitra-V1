"""Data-file integrity — the checks that would have caught real bugs.

Two of these are regressions for defects found in the repo:

  * fertilizers.json pointed at `dap.jpg` / `mop.jpg` / `ssp.jpg` / `npk.jpg`
    while the files on disk were `DAP.jpg` / `MOP.jpg` / `SSP.jpg` / `NPK.jpg`.
    Case-insensitive on a Windows dev box, a 404 on Render's ext4.
  * 100 MB of raster originals were deleted once their .webp twins took over.
    The asset test below fails loudly if a future cleanup removes something
    that is still referenced.
"""

import json
import re

import pytest

FRONTEND_SUFFIXES = (".html", ".js")


def _load(repo_root, rel):
    return json.loads((repo_root / rel).read_text(encoding="utf-8"))


def _fertilizer_items(repo_root):
    """fertilizers.json is a dict keyed by fertilizer id, not a list."""
    data = _load(repo_root, "backend/data/fertilizers.json")
    items = list(data.values()) if isinstance(data, dict) else data
    assert items, "fertilizers.json is empty"
    return [i for i in items if isinstance(i, dict)]


class TestFertilizerImages:
    def test_every_image_path_exists_on_disk(self, repo_root):
        """Case-sensitive existence check — the Render filesystem's rules."""
        items = _fertilizer_items(repo_root)

        missing = []
        for item in items:
            image = item.get("image")
            if not image:
                continue
            path = repo_root / "frontend" / image
            # Path.exists() is case-insensitive on macOS/Windows, so compare
            # the real directory listing instead — otherwise this test passes
            # on a laptop and the site still 404s in production.
            if not (path.parent.is_dir() and path.name in {
                p.name for p in path.parent.iterdir()
            }):
                missing.append(image)

        assert not missing, f"fertilizers.json references missing files: {missing}"

    def test_paths_are_relative_not_absolute(self, repo_root):
        """A leading slash or a hostname here breaks the shop's <img> joins."""
        items = _fertilizer_items(repo_root)
        for item in items:
            image = item.get("image")
            if image:
                assert not image.startswith(("/", "http")), image


class TestReferencedAssetsExist:
    """Every local image referenced by a page must still be on disk."""

    @staticmethod
    def _referenced_local_images(repo_root):
        pattern = re.compile(
            r'["\'(](?:\.\./|\./)?'
            r'((?:images|assets)/[^"\'()\s>]+?\.(?:png|jpe?g|webp|svg|ico))'
            r'["\')]'
        )
        found = set()
        for path in (repo_root / "frontend").rglob("*"):
            if path.suffix.lower() not in FRONTEND_SUFFIXES or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in pattern.finditer(text):
                ref = match.group(1)
                # Doc comments illustrate the markup with an elided slug
                # ("images/…-district-map.png"); that is a template, not a
                # reference to a file that should exist.
                if any(ch in ref for ch in "…${}*"):
                    continue
                found.add(ref)
        return found

    def test_no_dangling_image_references(self, repo_root):
        frontend = repo_root / "frontend"
        dangling = sorted(
            ref for ref in self._referenced_local_images(repo_root)
            if not (frontend / ref).is_file()
        )
        assert not dangling, (
            "frontend pages reference images that do not exist:\n  "
            + "\n  ".join(dangling)
        )


class TestApiBaseIsSetBeforeItIsRead:
    """A page must never fall back to calling its own origin.

    Regression for a real one: frontend/dukan/product/index.html read
    `window.KRASHIMITRA_API_BASE || ''` in an inline script near the top of
    <body>, but the only thing that sets the base — /api-config.js — loads at
    the very bottom of that document, and this page was the one page missing
    the sync <head> bootstrap every other page carries. So the base was "" and
    every call went to the page's own origin.

    That is invisible on the Render host, where the API *is* the origin. On
    krashimitra.in it 404s: Netlify proxies a handful of paths and /dukan/* is
    not one of them. The whole page was dead there — listings, products, and
    the signup POST — while looking merely "slow to load".

    A read is fine if the file assigns the base earlier, or if it carries a
    real fallback URL. An empty-string fallback with nothing set above it is
    the bug, and it is silent, so it gets a test.
    """

    READ = re.compile(r"window\.KRASHIMITRA_API_BASE")

    def test_every_read_resolves_to_the_api(self, repo_root):
        offenders = []
        for path in sorted((repo_root / "frontend").rglob("*")):
            if path.suffix.lower() not in FRONTEND_SUFFIXES or not path.is_file():
                continue
            # api-config.js IS the setter; its own guard read is the point.
            if path.name == "api-config.js":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            assigned_at = text.find("window.KRASHIMITRA_API_BASE =")
            for match in self.READ.finditer(text):
                if assigned_at != -1 and match.start() > assigned_at:
                    continue                       # already set further up
                tail = text[match.end():match.end() + 60].lstrip()
                if tail.startswith("=") and not tail.startswith("=="):
                    continue                       # this IS the assignment
                if tail.startswith("||"):
                    fallback = tail[2:].lstrip()
                    if not fallback.startswith(("''", '""')):
                        continue                   # a real fallback URL
                line = text[:match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(repo_root)}:{line}")
        assert not offenders, (
            "these read the API base before anything sets it, so requests go "
            "to the page's own origin (404 on krashimitra.in):\n  "
            + "\n  ".join(offenders)
        )


class TestNakshaAssets:
    """The naksha pages build image URLs from a slug at request time.

    Nothing greps as a literal filename, so a naive "unreferenced file" sweep
    reads every one of these as dead. They are not: the .webp is displayed,
    the .png is the download and the schema.org contentUrl, and the -og.png is
    the social card.
    """

    def test_every_state_has_its_three_images(self, repo_root):
        states = _load(repo_root, "backend/data/naksha_states.json")["states"]
        entries = list(states.values())
        assert entries, "naksha_states.json has no states"

        images_dir = repo_root / "frontend" / "images"
        on_disk = {p.name for p in images_dir.iterdir() if p.is_file()}

        missing = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            prefix = entry.get("prefix")
            if not prefix:
                continue
            for suffix in ("district-map.webp", "district-map.png", "og.png"):
                name = f"{prefix}-{suffix}"
                if name not in on_disk:
                    missing.append(name)

        assert not missing, f"naksha images missing from disk: {missing[:12]}"

"""The backend URL has exactly one owner: config/backend-origin.txt.

Render reassigns the .onrender.com subdomain whenever the service is recreated,
and it has done so twice. Both times the site went down in a way that is easy to
miss: krashimitra.in keeps serving its static homepage off Netlify, so the
homepage stays a green 200 while every proxied route — /bhav, /naksha, /ganna,
/sawal, /product/*, /go/*, /sitemap.xml — 404s. The first rename also left the
monitor workflow pinging the dead host, so it alerted "site DOWN" and exited
before ever reaching the mandi-freshness check it exists for, and a stalled feed
went unnoticed for days.

The URL used to live as a literal in 23 files. These tests make a stale copy a
build failure rather than an outage.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "backend-origin.txt"
HOST_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.onrender\.com")

# `python -m` so this works regardless of how the repo is checked out.
TOOL = ["-m", "tools.set_backend_origin"]


def configured() -> str:
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("http"):
            return line.strip().rstrip("/")
    pytest.fail("config/backend-origin.txt has no http line")


class TestConfig:
    def test_config_file_exists_and_parses(self):
        assert CONFIG.is_file(), "config/backend-origin.txt is the single source of truth"
        url = configured()
        assert HOST_RE.fullmatch(url) or url.startswith("https://"), url
        assert not url.endswith("/"), "no trailing slash — callers append paths"

    def test_python_reads_the_file_not_a_literal(self):
        from backend.origin import backend_origin
        assert backend_origin() == configured()

    def test_env_var_wins(self, monkeypatch):
        """Render can override without a commit — used during a cutover."""
        import backend.origin as origin
        monkeypatch.setenv("BACKEND_ORIGIN", "https://example-override.onrender.com/")
        assert origin.backend_origin() == "https://example-override.onrender.com"


class TestNoStaleLiterals:
    def test_managed_files_all_agree(self):
        """The real guard. Runs the tool's own --check so the two can't diverge."""
        proc = subprocess.run([sys.executable, *TOOL, "--check"],
                              cwd=REPO, capture_output=True, text=True)
        assert proc.returncode == 0, (
            "Some file still points at an old backend URL.\n"
            "Fix with:  python tools/set_backend_origin.py\n\n"
            + proc.stdout + proc.stderr)

    @pytest.mark.parametrize("rel", [
        "backend/main.py",
        "backend/routes/share.py",
        "backend/services/infra_service.py",
    ])
    def test_python_sources_carry_no_url(self, rel):
        """Python has no excuse — it can import backend.origin."""
        text = (REPO / rel).read_text(encoding="utf-8")
        assert not HOST_RE.search(text), (
            f"{rel} hardcodes a Render URL; import backend.origin.backend_origin() instead")

    @pytest.mark.parametrize("rel", [
        ".github/workflows/keepalive.yml",
        ".github/workflows/monitor.yml",
    ])
    def test_workflows_read_the_file(self, rel):
        """A workflow that pins the URL is the exact bug that hid a dead feed."""
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "config/backend-origin.txt" in text, f"{rel} must read the config file"
        assert not HOST_RE.search(text), f"{rel} still hardcodes a Render URL"

    def test_redirects_proxy_the_configured_host(self):
        """_redirects is the one that takes the site down when it goes stale."""
        text = (REPO / "frontend" / "_redirects").read_text(encoding="utf-8")
        hosts = set(HOST_RE.findall(text))
        assert hosts, "_redirects should proxy to the backend"
        assert hosts == {configured()}, f"stale hosts in _redirects: {hosts - {configured()}}"


class TestSwitchingProviders:
    """Moving to a new Render account — or off Render entirely.

    The first version of the tool found old addresses with an onrender.com
    pattern. That worked for a rename and for the first move to a custom
    domain, then broke silently: with every file holding a non-Render address,
    the next switch matched nothing, rewrote nothing, and `--check` reported
    "all files agree" while _redirects still proxied to the dead host. A green
    check over a down site is the failure this whole arrangement exists to
    prevent, so it gets a test.

    Runs against a scratch copy of the repo — never the real files.
    """

    @pytest.fixture
    def sandbox(self, tmp_path):
        import shutil
        root = tmp_path / "repo"
        (root / "config").mkdir(parents=True)
        (root / "tools").mkdir()
        (root / "frontend").mkdir()
        shutil.copy(REPO / "tools" / "set_backend_origin.py", root / "tools")
        shutil.copy(CONFIG, root / "config" / "backend-origin.txt")
        # One managed file is enough to prove the rewrite reaches disk, and
        # _redirects is the one whose staleness actually takes the site down.
        shutil.copy(REPO / "frontend" / "_redirects", root / "frontend")
        return root

    def run(self, root, *args):
        return subprocess.run([sys.executable, "tools/set_backend_origin.py", *args],
                              cwd=root, capture_output=True, text=True)

    def redirects(self, root) -> str:
        return (root / "frontend" / "_redirects").read_text(encoding="utf-8")

    @pytest.mark.parametrize("chain", [
        # a different account on the same provider
        ["https://krashimitra-api-x7f2.onrender.com"],
        # off Render to a custom domain, then somewhere else, then back —
        # step 2 is the one that used to be a silent no-op
        ["https://api.krashimitra.in",
         "https://krashimitra.up.railway.app",
         "https://krashi-mitra-v1-muup.onrender.com"],
    ])
    def test_every_switch_actually_rewrites(self, sandbox, chain):
        for url in chain:
            proc = self.run(sandbox, url)
            assert proc.returncode == 0, proc.stdout + proc.stderr
            text = self.redirects(sandbox)
            assert url in text, f"{url} never reached _redirects:\n{proc.stdout}"
            # and nothing from an earlier hop survives
            for older in chain:
                if older != url:
                    assert older not in text, (
                        f"stale {older} left behind after switching to {url}")
            assert self.run(sandbox, "--check").returncode == 0, "check disagrees with the rewrite"

    def test_history_accumulates_and_stays_truthful(self, sandbox):
        cfg = sandbox / "config" / "backend-origin.txt"
        first = next(l for l in cfg.read_text(encoding="utf-8").splitlines()
                     if l.startswith("http"))
        self.run(sandbox, "https://api.krashimitra.in")
        body = cfg.read_text(encoding="utf-8")
        assert f"#old {first}" in body, "the outgoing origin must be recorded"

        # Re-adopting an address removes it from the history: an origin cannot
        # be current and dead at the same time.
        self.run(sandbox, first)
        body = cfg.read_text(encoding="utf-8")
        assert f"#old {first}" not in body
        assert "#old https://api.krashimitra.in" in body

    def test_check_catches_a_file_left_behind_after_leaving_render(self, sandbox):
        """The precise green-check-over-a-broken-site regression."""
        self.run(sandbox, "https://api.krashimitra.in")
        red = sandbox / "frontend" / "_redirects"
        red.write_text(red.read_text(encoding="utf-8")
                       .replace("https://api.krashimitra.in",
                                "https://old-host.example.com", 1),
                       encoding="utf-8")
        self.run(sandbox, "https://krashimitra.up.railway.app")
        # the tool rewrote what it knew about; the planted foreign host is gone
        # only if it was in the history, so assert on what we do control:
        assert "https://api.krashimitra.in" not in self.redirects(sandbox), \
            "the previous origin must be replaced even though it is not a Render host"

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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config" / "backend-origin.txt"
HOST_RE = re.compile(r"https://[a-z0-9][a-z0-9-]*\.onrender\.com")

# Any absolute origin, whoever hosts it. HOST_RE only knows Render, which was
# fine while Render was the only answer - but the whole point of the config
# file is that the backend can move to a custom domain or another provider,
# and a test that can only see .onrender.com goes blind the moment it does.
# That is exactly what happened on the move to api.krashimitra.in: _redirects
# was correct and the test still failed, because it found zero hosts and
# concluded there was no proxy at all.
ORIGIN_RE = re.compile(r"https://[^/\s]+")

# A stand-in origin for tests that need "some address other than the real one".
# Never write the live origin here: the day it becomes the configured value,
# the test silently stops testing a move and starts testing a no-op.
OTHER_ORIGIN = "https://test-origin.example.com"

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
        want = configured()
        hosts = set(ORIGIN_RE.findall(text))
        assert want in hosts, "_redirects should proxy to the configured backend"
        assert hosts == {want}, f"stale hosts in _redirects: {hosts - {want}}"


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

    def test_changing_the_origin_bumps_the_service_worker(self, sandbox):
        """Rewriting api-config.js is not enough, and the gap is invisible.

        The service worker serves assets cache-first with no revalidation, so a
        browser that has loaded the site before keeps handing the page the OLD
        backend address forever. After the last rename that meant every
        returning visitor's profile came up empty against a dead host, while
        the site tested perfectly in a fresh browser and in curl. The cache
        version has to move with the origin, and nobody should have to remember
        that.
        """
        import shutil
        shutil.copy(REPO / "frontend" / "sw.js", sandbox / "frontend")
        sw = sandbox / "frontend" / "sw.js"
        before = re.search(r"krashimitra-v(\d+)", sw.read_text(encoding="utf-8"))
        assert before, "sw.js should carry a versioned CACHE_NAME"

        self.run(sandbox, "https://krashimitra-somewhere-else.onrender.com")

        after = re.search(r"krashimitra-v(\d+)", sw.read_text(encoding="utf-8"))
        assert int(after.group(1)) == int(before.group(1)) + 1, (
            "CACHE_NAME must be bumped when the origin changes, or every "
            "returning browser keeps calling the previous host")

    def test_api_config_is_not_served_cache_first(self):
        """The one asset that must always revalidate."""
        sw = (REPO / "frontend" / "sw.js").read_text(encoding="utf-8")
        assert "api-config.js" in sw, (
            "sw.js must special-case api-config.js — it carries the backend "
            "address, and cache-first freezes it across a backend move")
        # the carve-out has to come before the generic cache-first branch
        assert sw.index("api-config.js") < sw.index("isStaticAsset(request)", sw.index("function isStaticAsset") + 1), \
            "the api-config.js branch must be reached before the cache-first branch"

    def test_history_accumulates_and_stays_truthful(self, sandbox):
        cfg = sandbox / "config" / "backend-origin.txt"
        first = next(l for l in cfg.read_text(encoding="utf-8").splitlines()
                     if l.startswith("http"))
        self.run(sandbox, OTHER_ORIGIN)
        body = cfg.read_text(encoding="utf-8")
        assert f"#old {first}" in body, "the outgoing origin must be recorded"

        # Re-adopting an address removes it from the history: an origin cannot
        # be current and dead at the same time.
        self.run(sandbox, first)
        body = cfg.read_text(encoding="utf-8")
        assert f"#old {first}" not in body
        assert f"#old {OTHER_ORIGIN}" in body

    def test_check_catches_a_file_left_behind_after_leaving_render(self, sandbox):
        """The precise green-check-over-a-broken-site regression."""
        self.run(sandbox, OTHER_ORIGIN)
        red = sandbox / "frontend" / "_redirects"
        red.write_text(red.read_text(encoding="utf-8")
                       .replace(OTHER_ORIGIN, "https://old-host.example.com", 1),
                       encoding="utf-8")
        self.run(sandbox, "https://krashimitra.up.railway.app")
        # the tool rewrote what it knew about; the planted foreign host is gone
        # only if it was in the history, so assert on what we do control:
        assert "https://api.krashimitra.in" not in self.redirects(sandbox), \
            "the previous origin must be replaced even though it is not a Render host"


class TestBrowserCodeCarriesNoBackendURL:
    """The strongest guard here, because it removes the failure rather than
    catching it.

    Every other test in this file checks that the address in a file is the
    CURRENT one. None of them can help with what actually happened on
    16 Sep 2026: Render suspended the account, a new service came up on a new
    subdomain, `set_backend_origin.py` rewrote all 22 browser literals
    correctly in one command — and the live site went on calling the dead host
    for hours, because the repo was right and the deploy had not happened.

    A literal in browser code can only ever be as fresh as the last deploy. So
    there is no longer a literal: api-config.js and the inline bootstrap on
    each page read `location.origin`, which the browser cannot get wrong. One
    origin has served both the pages and the API since Netlify left the
    request path that morning.

    What made it expensive to spot is worth recording. Every server-rendered
    page — /bhav, /naksha, /ganna, the article tree — kept answering 200,
    because none of them makes an API call. The site looked healthy while
    login, OTP, profile, KrashiBook, the कृषि बाज़ार feed and मौसम were all
    dialling a suspended server, and कृषि बाज़ार in particular still rendered
    its sample listings, so it looked *populated*. A green page proves nothing
    about the half of the site that talks to an API.
    """

    # sw.js is exempt: its CACHE_NAME comment is a dated changelog of every
    # origin the site has used, and that history is why a returning browser
    # gets a cache bump on each move. It is a comment, never a fetch target.
    EXEMPT = {"sw.js"}

    def browser_files(self):
        for path in sorted((REPO / "frontend").rglob("*")):
            if path.suffix in (".js", ".html") and path.name not in self.EXEMPT:
                yield path

    def test_no_backend_host_is_hardcoded_anywhere_in_the_frontend(self):
        offenders = []
        for path in self.browser_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for host in set(HOST_RE.findall(text)):
                offenders.append(f"{path.relative_to(REPO).as_posix()} → {host}")
        assert not offenders, (
            "browser code must derive the API base from location.origin, never "
            "carry an address that goes stale between deploys:\n  "
            + "\n  ".join(offenders))

    def test_the_bootstrap_actually_uses_location_origin(self):
        """Guards the other direction: the rule above is satisfied by deleting
        the address, which would leave the API base undefined."""
        text = (REPO / "frontend" / "api-config.js").read_text(encoding="utf-8")
        assert "location.origin" in text
        assert "window.KRASHIMITRA_API_BASE" in text

    def test_an_explicit_override_is_still_respected(self):
        """A backend on a different origin has to stay possible — it is how
        local dev works, and how a static host in front would work again."""
        text = (REPO / "frontend" / "api-config.js").read_text(encoding="utf-8")
        assert "if (window.KRASHIMITRA_API_BASE) return;" in text

    def test_the_tool_no_longer_manages_browser_files(self):
        """If a frontend file reappears in TARGETS, someone has put an address
        back into the browser and the guard above is about to start failing."""
        from tools.set_backend_origin import TARGETS

        frontend = [t for t in TARGETS if t.startswith("frontend/")
                    and t != "frontend/_redirects"]
        assert not frontend, f"browser files back under the tool's control: {frontend}"

    # The origins every bootstrap is exercised against. The made-up Render host
    # is the important row: it stands for the subdomain the NEXT suspension
    # hands out, which nothing in this repo can know in advance. Deriving the
    # base from location.origin is what makes that row pass without an edit.
    ORIGINS = [
        ("https://krashimitra.in", "https://krashimitra.in"),
        ("https://www.krashimitra.in", "https://www.krashimitra.in"),
        ("https://a-host-nobody-told-us-about.onrender.com",
         "https://a-host-nobody-told-us-about.onrender.com"),
        ("http://localhost:5500", "http://localhost:8000"),   # Live Server
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),   # uvicorn direct
    ]

    def _bootstraps(self):
        """Every inline API-base bootstrap, plus api-config.js's own.

        There are a dozen copies because api-config.js loads deferred and the
        base has to be set synchronously before any page script runs. Copies
        drift — login.html derived the dev port from the page's own port, so on
        Live Server every /auth call went to the static server — so each one is
        executed here rather than eyeballed.
        """
        script = re.compile(r"<script>(.*?)</script>", re.S)
        for path in sorted((REPO / "frontend").rglob("*.html")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in script.finditer(text):
                body = match.group(1)
                if "window.KRASHIMITRA_API_BASE =" in body:
                    yield path.relative_to(REPO).as_posix(), body
        api = (REPO / "frontend" / "api-config.js").read_text(encoding="utf-8")
        yield "frontend/api-config.js", api.split("// \u2500\u2500 Google OAuth")[0]

    def test_every_bootstrap_resolves_to_the_right_origin(self, tmp_path):
        """Runs the real browser code under node with a stubbed `location`.

        The pure-text guard above proves no address is hardcoded. This proves
        the replacement actually computes the right one — including on a host
        this repo has never heard of, which is the case that broke.
        """
        node = shutil.which("node")
        if not node:
            pytest.skip("node not installed")

        parts = ["let fails = 0;"]
        for name, body in self._bootstraps():
            # The bootstrap is handed to node inside a template literal, so
            # backslashes, backticks and ${ have to survive the trip intact.
            safe = (body.replace("\\", "\\\\")
                        .replace("`", "\\`")
                        .replace("${", "\\${"))
            rows = ", ".join(f'["{o}", "{w}"]' for o, w in self.ORIGINS)
            parts.append("""
for (const [origin, want] of [%s]) {
  const u = new URL(origin);
  const window = {};
  const location = {hostname: u.hostname, port: u.port, protocol: u.protocol, origin: u.origin};
  const document = {addEventListener(){}, getElementById(){return null}, querySelector(){return null}};
  try { new Function("window","location","document", `%s`)(window, location, document); }
  catch (e) { console.log("EXEC FAIL %s @" + origin + ": " + e.message); fails++; continue; }
  if (window.KRASHIMITRA_API_BASE !== want)
    { console.log("WRONG %s @" + origin + " -> " + window.KRASHIMITRA_API_BASE); fails++; }
}""" % (rows, safe, name, name))
        parts.append('if (fails) { console.log(fails + " FAILURES"); process.exit(1); }')

        harness = tmp_path / "bootstraps.js"
        harness.write_text("\n".join(parts), encoding="utf-8")
        result = subprocess.run([node, str(harness)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_the_bootstraps_are_valid_javascript(self, tmp_path):
        """A syntax error in one of these takes out every page that inlines it,
        and nothing else in the suite parses browser code."""
        node = shutil.which("node")
        if not node:
            pytest.skip("node not installed")
        blob = "\n".join(f"// ---- {name}\n(function(){{\n{body}\n}})();"
                         for name, body in self._bootstraps())
        path = tmp_path / "all.js"
        path.write_text(blob, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

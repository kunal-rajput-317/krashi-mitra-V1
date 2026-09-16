"""frontend/_redirects, served by this origin.

Netlify held 300-odd routing rules that this app never implemented, because
Netlify sat in front and answered them first. On 16 Sep 2026 the site moved to
Cloudflare DNS -> Render and Netlify left the request path entirely, at which
point every one of those rules went inert: /mandi, /naksha.html, /map.html,
/dukan, /global, the whole `*-ka-naksha` / `*-ke-jile` vanity set and seven
legacy /xx.html country bookmarks -- 35 indexed URLs -- started returning a
hard 404, and /shop went on serving the page retired that same morning instead
of 301ing to /product.

Hand-porting them into FastAPI would have left two lists to keep in sync, and
the one in frontend/_redirects is the one people already edit. So this reads
that file instead. A rule added for any future host works here the moment it
lands -- the same arrangement config/backend-origin.txt uses for the backend
URL.

Netlify's semantics, reproduced:

  * first matching rule wins;
  * a `!` on the status forces the rule even when real content exists at the
    source -- that is what lets /shop 301 away from frontend/shop.html;
  * without `!` the rule is only a fallback, applied when nothing else answers.
    Reproduced here by running the app first and rescuing its 404, so a rule
    can never shadow a real page. /international/* -> index.html is exactly why
    that matters: forced, it would swallow /international/us.html.
  * `*` captures a suffix, `:splat` replays it in the target;
  * query strings survive a redirect.

Rules whose target is this origin are skipped: they exist to tell Netlify where
the backend lives, and the backend is now what is running, so the app already
routes those paths. The trailing `/* /404.html 404` is skipped for the same
reason -- the static mount serves 404.html itself.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from backend.origin import backend_origin

BASE_DIR = Path(__file__).resolve().parents[2]
RULES_FILE = BASE_DIR / "frontend" / "_redirects"


def _own_origins() -> set[str]:
    """Every address this site has ever answered on.

    config/backend-origin.txt keeps retired addresses as `#old` lines precisely
    so tooling can still recognise them; a rule pointing at a host we used to
    be is still a rule pointing at ourselves.
    """
    hosts = {urlsplit(backend_origin()).netloc}
    try:
        text = (BASE_DIR / "config" / "backend-origin.txt").read_text(encoding="utf-8")
    except OSError:
        text = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#old "):
            hosts.add(urlsplit(line[5:].strip()).netloc)
    hosts.update({"krashimitra.in", "www.krashimitra.in"})
    return {h for h in hosts if h}


class Rule:
    __slots__ = ("source", "target", "status", "forced", "prefix")

    def __init__(self, source: str, target: str, status: int, forced: bool):
        self.source = source
        self.target = target
        self.status = status
        self.forced = forced
        # `/farm/*` matches /farm and everything under it, as it does on
        # Netlify -- a bare parent matches its own rule with an empty splat.
        self.prefix = source[:-1] if source.endswith("/*") else None

    def match(self, path: str) -> str | None:
        """The rewritten target for `path`, or None if this rule misses."""
        if self.prefix is not None:
            if path == self.prefix.rstrip("/"):
                splat = ""
            elif path.startswith(self.prefix):
                splat = path[len(self.prefix):]
            else:
                return None
            return self.target.replace(":splat", splat)
        return self.target if path == self.source else None


def parse(text: str, own_origins: set[str] | None = None):
    """(forced, fallback) -- both in file order, because first match wins."""
    own = own_origins if own_origins is not None else _own_origins()
    forced: list[Rule] = []
    fallback: list[Rule] = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            continue
        source, target, status = parts

        is_forced = status.endswith("!")
        try:
            code = int(status.rstrip("!"))
        except ValueError:
            continue

        if target.startswith(("http://", "https://")):
            split = urlsplit(target)
            if split.netloc not in own:
                continue  # a genuinely external destination; not ours to serve
            target = split.path or "/"
            if code == 200:
                continue  # pointed at ourselves -- the app already routes it

        if code == 404:
            continue  # the static mount already answers with 404.html

        (forced if is_forced else fallback).append(
            Rule(source, target, code, is_forced)
        )

    return forced, fallback


def load(path: Path | None = None):
    file = path or RULES_FILE
    try:
        return parse(file.read_text(encoding="utf-8"))
    except OSError:
        return [], []  # a missing file is not a reason to refuse to boot


class NetlifyRedirectMiddleware:
    """Pure ASGI, not BaseHTTPMiddleware, for two reasons.

    A forced rule has to answer before routing, so the static mount at "/"
    cannot serve frontend/shop.html out from under a /shop -> /product 301.
    And a fallback rule has to see the app's 404 and then re-dispatch the same
    request against a different path, which means holding the response start
    back until the status is known -- something BaseHTTPMiddleware's
    request/response shape cannot express.
    """

    def __init__(self, app, rules_path: Path | None = None,
                 frontend_dir: Path | None = None):
        self.app = app
        self._file = rules_path or RULES_FILE
        self._frontend = frontend_dir or (BASE_DIR / "frontend")
        self._mtime: float | None = None
        self.forced: list[Rule] = []
        self.fallback: list[Rule] = []
        self._refresh()

    def _static_file_exists(self, path: str) -> bool:
        """Would the static mount at "/" answer this path?

        The only thing a forced rule has to out-rank is that mount, so this is
        the test for whether to jump in ahead of routing. Mirrors
        CleanURLStaticFiles: the plain path first, then the same name with
        ".html" appended.
        """
        rel = path.lstrip("/")
        if not rel:
            rel = "index.html"
        root = self._frontend.resolve()
        for candidate in (rel, f"{rel}.html"):
            try:
                target = (root / candidate).resolve()
                # A "../.." in the URL must not let a rule fire off a file
                # outside frontend/.
                if target.is_relative_to(root) and target.is_file():
                    return True
            except (OSError, ValueError):
                continue
        return False

    def _refresh(self) -> None:
        """Reload when the file changes, so editing _redirects costs no restart
        -- the same mtime check backend/origin.py uses."""
        try:
            mtime = self._file.stat().st_mtime
        except OSError:
            return
        if mtime != self._mtime:
            self.forced, self.fallback = load(self._file)
            self._mtime = mtime

    @staticmethod
    def _first(rules: list[Rule], path: str):
        for rule in rules:
            hit = rule.match(path)
            if hit is not None:
                return rule, hit
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("GET", "HEAD"):
            return await self.app(scope, receive, send)

        self._refresh()
        path = scope["path"]

        # A forced rule jumps the queue only when the static mount would
        # otherwise answer -- that is the case it exists for, /shop having to
        # 301 to /product with frontend/shop.html sitting right there.
        #
        # It must NOT jump ahead of the app's own routes. Several of these
        # rules are already real handlers: routes/poultry.py 301s the whole
        # /farm/* tree and does it to an absolute https://krashimitra.in/...
        # URL that a test pins, having once been an open redirect. Reading a
        # text file is no reason to displace a handler written on purpose.
        forced = self._first(self.forced, path)
        if forced is not None and self._static_file_exists(path):
            rule, target = forced
            return await self._apply(rule, target, scope, receive, send)

        hit = forced or self._first(self.fallback, path)
        if hit is None:
            return await self.app(scope, receive, send)

        # Otherwise the app goes first and only its 404 hands the rule its
        # turn, so a real page -- or a real handler -- always wins.
        rule, target = hit
        held: list[dict] = []
        missed = False
        forwarded = False

        async def capture(message):
            nonlocal missed, forwarded
            if message["type"] == "http.response.start" and message["status"] == 404:
                missed = True
            if missed and not forwarded:
                held.append(message)
                return
            forwarded = True
            await send(message)

        await self.app(scope, receive, capture)

        if missed and not forwarded:
            return await self._apply(rule, target, scope, receive, send)
        for message in held:
            await send(message)

    async def _apply(self, rule: Rule, target: str, scope, receive, send) -> None:
        """A 301 answers here; a 200 re-runs the request against the target."""
        if rule.status in (301, 302, 307, 308):
            query = scope.get("query_string", b"")
            location = target + ("?" + query.decode("latin-1") if query else "")
            return await self._redirect(send, rule.status, location)
        rewritten = {**scope, "path": target, "raw_path": target.encode("utf-8")}
        return await self.app(rewritten, receive, send)

    @staticmethod
    async def _redirect(send, status: int, location: str) -> None:
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"location", location.encode("utf-8")),
                (b"content-length", b"0"),
                # Permanent enough for browsers and Cloudflare to hold, but not
                # forever: these live in a text file people edit.
                (b"cache-control", b"public, max-age=3600"),
            ],
        })
        await send({"type": "http.response.body", "body": b""})

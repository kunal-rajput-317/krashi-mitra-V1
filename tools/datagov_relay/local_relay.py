"""The data.gov.in relay, run on a PC in India instead of AWS Lambda.

Same code as lambda_function.py (same secret check, same /resource/<id>-only
rule), wrapped in a small local web server. A Cloudflare Tunnel makes it
reachable from Render. Use it while the AWS account is not ready, or when the
AWS relay is refused. It works only while this PC is on and online.

    python tools/datagov_relay/local_relay.py        # listens on 127.0.0.1:8787
    cloudflared tunnel --url http://127.0.0.1:8787   # in a second window

The secret is DATA_GOV_RELAY_SECRET in the repo's .env (git-ignored), the
same value as on Render. No fallback value: the repo is public.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lambda_function  # noqa: E402

PORT = int(os.getenv("RELAY_PORT", "8787"))


def _secret_from_env_file() -> str:
    env = HERE.parent.parent / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATA_GOV_RELAY_SECRET="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class Relay(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlsplit(self.path)
        event = {
            "rawPath": u.path,
            "rawQueryString": u.query,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "requestContext": {"http": {"method": "GET"}},
        }
        r = lambda_function.lambda_handler(event, None)
        body = r["body"].encode("utf-8")
        self.send_response(r["statusCode"])
        self.send_header("Content-Type", r["headers"]["Content-Type"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Path only: the query string carries the data.gov.in API key.
        print(f"{self.log_date_time_string()}  {self.command} "
              f"{urlsplit(self.path).path}  ->  {args[1] if len(args) > 1 else ''}",
              flush=True)


def main():
    secret = os.getenv("DATA_GOV_RELAY_SECRET", "").strip() or _secret_from_env_file()
    if not secret:
        sys.exit("DATA_GOV_RELAY_SECRET is not set (add it to the repo's .env)")
    os.environ["RELAY_SECRET"] = secret
    print(f"data.gov.in relay on http://127.0.0.1:{PORT}  (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Relay).serve_forever()


if __name__ == "__main__":
    main()

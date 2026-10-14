"""data.gov.in relay: an AWS Lambda in the Mumbai region (ap-south-1).

Since the 25 Sep 2026 outage api.data.gov.in refuses servers outside India
(Render Singapore, GitHub's US runners) while it answers from India. Render
has no India region, so backend/services/mandi_fetch_service.py sends its
data.gov.in requests here when DATA_GOV_RELAY_URL is set, and this function
makes them from Mumbai.

It is not an open proxy:
  * every request must carry the X-Relay-Secret header, compared in constant
    time with the RELAY_SECRET environment variable (no fallback value);
  * only GET /resource/<resource id> is forwarded, and only to
    api.data.gov.in.

Standard library only, so the console's inline editor is enough to deploy it.
Setup steps: tools/datagov_relay/README.md
"""
import hmac
import os
import re
import urllib.error
import urllib.request

UPSTREAM = "https://api.data.gov.in"
PATH_OK = re.compile(r"^/resource/[0-9a-f-]{36}$")
TIMEOUT = 100     # data.gov.in answers in 1-6 s; set the Lambda timeout above this
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _reply(status, body, ctype="text/plain; charset=utf-8"):
    return {"statusCode": status, "headers": {"Content-Type": ctype}, "body": body}


def lambda_handler(event, context):
    secret = os.environ.get("RELAY_SECRET", "")
    if not secret:
        return _reply(500, "relay: RELAY_SECRET is not configured")
    given = (event.get("headers") or {}).get("x-relay-secret", "")
    if not hmac.compare_digest(given.encode(), secret.encode()):
        return _reply(403, "relay: forbidden")

    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "")
    if method != "GET" or not PATH_OK.match(path):
        return _reply(404, "relay: only GET /resource/<id> is forwarded")

    url = UPSTREAM + path
    if event.get("rawQueryString"):
        url += "?" + event["rawQueryString"]
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return _reply(r.status, r.read().decode("utf-8", "replace"),
                          r.headers.get("Content-Type", "application/json"))
    except urllib.error.HTTPError as e:
        # Pass data.gov.in's own status through (403 bad key, 429, 5xx), so
        # the fetcher's retry rules behave exactly as on a direct call.
        return _reply(e.code, e.read().decode("utf-8", "replace")[:2000],
                      e.headers.get("Content-Type", "text/plain"))
    except Exception as e:
        return _reply(502, f"relay: upstream unreachable from Mumbai: "
                           f"{type(e).__name__}: {e}"[:500])

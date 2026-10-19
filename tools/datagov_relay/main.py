"""data.gov.in relay as a Google Cloud Run function in Mumbai (asia-south1).

The same relay as lambda_function.py, for when AWS is not available: this
file only adapts Cloud Run's request to the Lambda handler, so the secret
check and the GET /resource/<id>-only rule are the very same code.

Deploy main.py, lambda_function.py and requirements.txt together, entry
point `relay`. Setup steps: tools/datagov_relay/README.md
"""
import functions_framework

import lambda_function


@functions_framework.http
def relay(request):
    event = {
        "rawPath": request.path,
        "rawQueryString": request.query_string.decode("utf-8", "replace"),
        "headers": {k.lower(): v for k, v in request.headers.items()},
        "requestContext": {"http": {"method": request.method}},
    }
    r = lambda_function.lambda_handler(event, None)
    return r["body"], r["statusCode"], {"Content-Type": r["headers"]["Content-Type"]}

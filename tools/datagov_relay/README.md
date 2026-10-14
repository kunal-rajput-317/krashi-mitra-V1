# data.gov.in relay (AWS Lambda, Mumbai)

api.data.gov.in refuses servers outside India. Render has no India region, so
the mandi fetcher sends its data.gov.in requests through this function in AWS
Mumbai. AWS's free tier covers 1 million requests a month, permanently; we use
about 300 a day.

## Set it up once (about 10 minutes)

1. **Pick a secret.** A long random string, e.g. from
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   It goes only into AWS and Render. Never into this repo.
2. **AWS console → region "Asia Pacific (Mumbai) ap-south-1"** (top right).
3. **Lambda → Create function**
   - Author from scratch, name `datagov-relay`, runtime **Python 3.12**,
     architecture arm64.
   - Advanced settings → tick **Enable function URL**, auth type **NONE**
     (the secret header is the lock).
4. **Code tab:** replace `lambda_function.py` with this folder's
   `lambda_function.py`, then **Deploy**.
5. **Configuration → General configuration → Edit:** timeout **2 min**,
   memory **256 MB**.
6. **Configuration → Environment variables:** `RELAY_SECRET` = your secret.
7. Copy the **Function URL** (`https://….lambda-url.ap-south-1.on.aws/`).
8. **Render → the web service → Environment:**
   - `DATA_GOV_RELAY_URL` = the function URL
   - `DATA_GOV_RELAY_SECRET` = the same secret

   Save. Render redeploys. The startup log line
   `🔑 DATA_GOV_API_KEY OK` means the relay works. Then run a manual mandi
   fetch from /admin.

## Test the function by itself

```
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Relay-Secret: YOUR_SECRET" \
  "FUNCTION_URL/resource/9ef84268-d588-465a-a308-a864a43d0070?api-key=YOUR_DATA_GOV_KEY&format=json&limit=5"
```

`200` = working. `403` = wrong secret. `502` = data.gov.in refused Mumbai too.

## Turning it off

Delete `DATA_GOV_RELAY_URL` on Render. The fetcher goes back to calling
data.gov.in directly.

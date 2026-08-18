# Moving the backend to a new Render account — runbook

The URL part is one command. The rest is a short checklist, and it is written
down because the expensive half of this job is not the URL — it is the twenty
values that live only in Render's dashboard and have to be typed again.

Nothing here needs the site to be up. Do the whole thing on the new account
first; the old service keeps serving until step 6.

---

## 0. What actually has to move

| Thing | Moves how |
|---|---|
| build / start command, region, health check, branch, env var **names** | `render.yaml` — Render reads it as a Blueprint |
| env var **values** | by hand, step 3. `sync: false` means "the name is in the repo, the value is not" |
| the public URL | step 5, one command |
| the database | not at all, unless you are also moving Neon — see `tools/neon/README.md` |
| GitHub Actions | nothing. Both workflows read `config/backend-origin.txt` at run time |

---

## 1. Create the service on the new account

Connect the GitHub repo and let Render pick up `render.yaml` (Blueprint).
Keep `branch: main` and `region: singapore` — the region is the closest one to
the user base and changing it costs latency on every request.

Render will assign a **new** `*.onrender.com` subdomain. It has never once
reused the old name. Copy it; you need it in step 5.

## 2. List what the new service needs

```powershell
python -c "import backend.main, backend.services.infra_service as s; print('\n'.join(n for n,r in s._declared_env_vars() if r))"
```

That prints the **required** vars, read straight out of `render.yaml`. The ones
marked `# optional` there have working code-level defaults — the site runs
without them, one feature at a time stays switched off.

You do not have to trust this list. After the deploy, the admin panel's
**Infra & Credits** page shows `ज़रूरी secrets: n/n सेट` and names anything
missing, because a missing value does not fail a deploy — it fails a feature,
quietly, weeks later.

## 3. Copy the values across

From the old dashboard, or from `.env` locally. Two that are easy to get wrong:

- **`DATABASE_URL`** — same Neon project as before. Paste it whole, including
  `?sslmode=require`.
- **`ADMIN_USER` / `ADMIN_PASS`** — these gate `/admin` and `/health?full=1`.
  Getting them wrong locks you out of the page that would tell you what else
  is wrong.

## 4. Deploy and check it answers

```bash
curl -s https://<new-host>.onrender.com/health
```

A free instance sleeps after ~15 idle minutes, so the first call can take up to
~50s. That is normal; retry before concluding anything.

## 5. Point the site at it — the one command

```powershell
python tools/set_backend_origin.py https://<new-host>.onrender.com
python tools/set_backend_origin.py --check
```

That rewrites 48 occurrences across 19 files, including all 24 proxy lines in
`frontend/_redirects`. Python and the workflows need nothing — they read
`config/backend-origin.txt` directly.

Then **push to main**. Until Netlify deploys the new `_redirects`, the site is
still proxying to the old host, and the homepage will keep looking fine while
every real page 404s.

The tool is not Render-specific. It records every address the site has used in
`config/backend-origin.txt` and searches for all of them, so it works the same
moving to a custom domain, to another provider, or back again.

## 6. Turn the old service off

Only after `https://krashimitra.in/bhav` returns 200. Then suspend or delete
the old service, so it stops burning free-tier hours on the old account.

---

## Verify, in one pass

```bash
for p in / /bhav /naksha /sawal /ganna /sitemap.xml /llms.txt /ads.txt; do
  printf "%-14s " "$p"
  curl -s -o /dev/null -w "%{http_code}\n" -m 45 "https://krashimitra.in$p"
done
```

All 200. A green `/` alone proves nothing — it is served by Netlify and stays
green through a completely dead backend. That is how both previous renames went
unnoticed.

---

## Why any of this happens

Render reassigns the subdomain whenever the service is recreated:

```
krashi-mitra-v1.onrender.com       dead
krashi-mitra-v1-oxdc.onrender.com  dead
krashi-mitra-v1-muup.onrender.com  current
```

Each rename was an outage. The first one also left `.github/workflows/monitor.yml`
pinned to the dead host, where it alerted "site DOWN" and exited before ever
reaching the mandi-freshness check it exists for — so a stalled price feed went
unnoticed for days.

**The permanent fix is DNS.** Point `api.krashimitra.in` at Render with a CNAME,
run `set_backend_origin.py https://api.krashimitra.in` once, and the subdomain
can change as often as Render likes without anything in this repo moving. Until
that record exists, this runbook is the procedure.

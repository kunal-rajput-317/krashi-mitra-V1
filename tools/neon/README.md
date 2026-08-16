# Neon account migration — runbook

Moves KrashiMitra's user data between Neon projects. Three scripts, ~10 minutes,
no downtime: the live site keeps serving from the old DB until the final step.

Needs only Python + `psycopg2` (both already in `requirements.txt`).
**There is no `pg_dump` on this machine** — `C:\Program Files\PostgreSQL\18`
has a `data` dir but no `bin`. Do not plan around it.

---

## The commands

```powershell
# 1. Dump the current DB (read-only; source comes from .env DATABASE_URL)
python tools/neon/neon_dump.py

# 2. Build schema + triggers on the NEW account
python tools/neon/neon_schema.py 'postgresql://USER:PASS@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'

# 3. Load, dry first
python tools/neon/neon_load.py 'postgresql://...same...' --dry-run
python tools/neon/neon_load.py 'postgresql://...same...' --yes

# 4. Cut over: Render dashboard -> DATABASE_URL -> redeploy
# 5. Optional: put the new URL in local .env so dev matches prod
```

### PowerShell gotchas

- **Single-quote the URL.** The `&` in `?sslmode=require&channel_binding=require`
  is a reserved operator; unquoted, PowerShell aborts. Single not double —
  double quotes expand `$`, and Neon passwords can contain one.
- **Drop the leading `psql`.** Neon's copy button hands you
  `psql 'postgresql://...'`. That first word is the program, not the string.
- **Don't type the angle brackets.** `<conn>` is a placeholder marker.

All three mistakes are caught with a readable message rather than a stack trace.

---

## Which `DATABASE_URL`

It lives in two places and they are not interchangeable:

| Where | Used by | Changing it |
|---|---|---|
| local `.env` | these scripts, local dev | invisible to users |
| Render dashboard env var | the live site | **this is the cutover** |

Steps 1–3 pass the target as an *argument* and touch neither. Only step 4
changes what farmers hit. If the load fails, the site never noticed.

---

## What moves, and what doesn't

**Carried (22 tables)** — `users`, `user_profiles`, `chat_history`,
`crop_calendar`, `push_subscriptions`, `mandi_alerts`, `bazar_posts`,
`bazar_likes`, `bazar_comments`, `bazar_follows`, `orders`, `carts`,
`crop_appeals`, `admin_tasks`, `buyers`, `dealer_products`,
`dealer_placements`, `lead_clicks`, `mandi_price_monthly`,
`mandi_season_slices`, `kcc_qa`, `kcc_crop_builds`.

**Left behind on purpose** — `weather_cache`, `weather_history`,
`mandi_prices`, `mandi_last_seen`, `mandi_price_history`, `sync_log`.
The schedulers refill these within a day, and they are the bulk of the
storage. Leaving them is how the new account starts near-empty instead of
inheriting a near-full 0.5 GB branch. Measured Aug 2026: source DB 169 MB,
payload **~1 MB gzipped / 40k rows**.

⚠️ `mandi_price_monthly` + `mandi_season_slices` **must** be carried despite
looking derived. They accumulate slowly off the data.gov archive via a lazy
queue, not a scheduled feed; dropping them guts /bhav's
"पिछले N साल का रुझान" panel for weeks.

---

## Why the scripts do what they do

- **`-pooler` is rewritten to the direct host.** The pooler is PgBouncer in
  transaction mode and won't hold a `COPY` stream open reliably.
- **Load order is parents-first.** `backend/database/db.py` declares ~16 FKs
  with `ondelete CASCADE / SET NULL`. `pg_restore --disable-triggers` is not
  an option: it needs superuser, and Neon roles aren't.
- **`session_replication_role = replica`** during load, so the `users`
  triggers (`trg_ensure_user_profile`, `trg_sync_users_user_id`,
  `trg_profile_requires_verified_user`, `trg_block_unverify_with_profile`)
  don't fabricate colliding profile rows or reject unverified users mid-load.
  Falls back to per-table `DISABLE TRIGGER USER` if the role can't set it.
- **Column names, not positions.** `create_all()` may emit a different
  physical order on the new DB; a positional `COPY` would shear the data.
  The manifest records column order, and drift is reported by `--dry-run`.
- **`neon_schema.py` imports `backend.main` but never fires the startup
  event**, so `create_all()` + `init_db()` run without waking the weather,
  mandi, GSC and mill schedulers. Booting the real app at the new account
  would start all four fetching immediately, burning fresh CU on day one.
- **Sequences are restored last** via `setval()`, so nothing inserted during
  the load bumps them afterwards.

---

## Guards

`neon_schema.py` refuses to run if the target endpoint matches the one `.env`
is live on — step 3 truncates whatever it is pointed at, and that is the one
mistake here that destroys data. It also warns if the target is outside
`ap-southeast-1`: Render is `region: singapore` (`render.yaml`), and a
cross-region DB adds ~200 ms+ to every query — with `pool_pre_ping=True`,
even checking out a pooled connection pays it. Neon cannot move a project
after creation, so the fix is always "recreate it in the right region".

`neon_load.py` refuses to run without `--yes`, and rolls back entirely on any
error. It finishes by re-counting every table against the manifest.

---

## After cutover

1. Confirm the site is healthy — `/health/checks` should be green, especially
   `db_write`.
2. **Rotate the old account's role password** if the string was ever pasted
   into a screenshot, chat, or terminal history.
3. Delete `tools/neon/dump/` — it holds real PII (emails, phones, base64
   avatars). It is gitignored, but it should not linger.

---

## The thing this runbook cannot fix

A free Neon project whose compute never suspends exhausts its 100 CU-hrs in
**16.7 days** (100 ÷ the 0.25 CU floor = 400 hours), regardless of traffic.
Running this migration buys about two weeks and then you run it again.

What actually changes the arithmetic: pay for Launch, or make the compute
genuinely suspend — `NullPool` instead of the default `QueuePool` (which has
no idle reaper, so up to 10 connections stay open forever and Neon's
scale-to-zero never fires), cap autoscale below 2 CU, and serve crawlers from
edge cache so Googlebot never reaches Postgres.

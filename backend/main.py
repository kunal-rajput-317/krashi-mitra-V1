# ============================================================
# Krishi Mitra — Backend API
# Framework: FastAPI | AI: Ollama (qwen:14b)
# Database: PostgreSQL | ORM: SQLAlchemy
# ============================================================
# Modularization status:
#   ✅ weather    → routes/weather.py    + services/weather_service.py
#   ✅ mandi      → routes/mandi.py      + services/mandi_service.py
#   ✅ fertilizer → routes/fertilizer.py + services/fertilizer_service.py
#   ✅ chatbot    → routes/chatbot.py    + services/chatbot_service.py  (async)
#   ✅ auth       → routes/auth.py
#   ✅ profile    → routes/profile.py
#   ✅ search     → routes/search.py     + services/search_service.py
#   ⚠️  chat.py   → REMOVED (duplicated /ask from chatbot.py, caused route conflict)
# ============================================================

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

load_dotenv()

# Quieter HuggingFace loads (skip telemetry round-trips on model init)
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Configure logging BEFORE importing any router: modules that call
# logging.getLogger() at import time must inherit our handler, not the root
# default that prints unformatted WARNING+ only.
from backend.utils.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

from backend.routes import cart  # ensure CartItem model registered before create_all
from backend.utils.security import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    assert_secrets_configured,
)

# Fail fast in production if JWT_SECRET / ADMIN_PASS are unset or still the
# public repo defaults. Raises here, before any router is mounted, so a
# misconfigured deploy never serves a request with a forgeable token.
assert_secrets_configured()

BASE_DIR = Path(__file__).resolve().parents[1]
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG    = os.getenv("DEBUG", "true").lower() == "true"

from backend.database.db import MandiPrice, get_db, init_db

from backend.database.db import engine, Base

# ── Routers ──────────────────────────────────────────────────
from backend.routes.weather    import router as weather_router
from backend.routes.mandi      import router as mandi_router
from backend.routes.fertilizer import router as fertilizer_router
from backend.routes.chatbot    import router as chatbot_router
from backend.routes.auth       import router as auth_router
from backend.routes.profile    import router as profile_router
from backend.routes.search     import router as search_router   # NEW
from backend.routes.cart       import router as cart_router     # CART
from backend.routes.order      import router as order_router    # ORDER

from backend.services.weather_scheduler import start_scheduler  # WEATHER CACHE
from backend.services.mandi_scheduler   import start_scheduler as start_mandi_scheduler  # MANDI CACHE
from backend.services.gsc_scheduler     import start_scheduler as start_gsc_scheduler  # GSC RECRAWL SWEEP
from backend.services.ganna_mill_scheduler import start_scheduler as start_mill_scheduler  # SUGAR-MILL REGISTER

app = FastAPI(
    title="KrashiMitra API",
    description="Hindi-first Agriculture Intelligence Platform for Indian Farmers",
    version="0.1.0",
)

# ── Response compression ─────────────────────────────────────────────
# Added FIRST => innermost, so it sees a route's response as one whole body
# message and can set a real Content-Length. Sitting it outside either
# BaseHTTPMiddleware below would mean compressing an already-streaming
# response, which drops Content-Length and forces chunked transfer on every
# page Netlify's CDN caches.
#
# Why this exists at all: Render suspended the workspace on 16 Aug 2026 for
# blowing the 5 GB/month bandwidth cap, and nothing here had ever compressed
# a response. Hindi is the worst case for that — Devanagari is 3 bytes per
# character in UTF-8, and _doc() inlines a 43 KB CSS blob into every
# server-rendered page. A measured article page is 106,601 bytes raw against
# 18,971 gzipped: a 5.6x multiplier applied to the whole /bhav + /naksha +
# /ganna + /sawal + /product tree, all of which Netlify proxies to Render.
#
# Level 6 rather than the library default of 9: on a free instance CPU is the
# scarce resource, and 9 buys a couple of percent for several times the work.
# Images and PDFs off the static mounts get compressed too for no real gain,
# which is a few wasted milliseconds on paths the production domain serves
# from Netlify anyway — not worth a content-type allowlist to dodge.
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

# ── CORS ─────────────────────────────────────────────────────────────
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse

from backend.origin import backend_origin

raw_origins = os.getenv(
    "CORS_ORIGINS",
    ",".join([
        "https://krashimitra.in",
        "https://www.krashimitra.in",
        # Never hardcoded: Render reassigns this subdomain when the service is
        # recreated, and a stale value here would reject the browser's calls
        # from the app's own domain. See config/backend-origin.txt.
        backend_origin(),
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]),
).split(",")

cors_origins = []
for origin in raw_origins:
    origin = origin.strip()
    if not origin:
        continue
    # Extract only scheme://netloc to ignore trailing slashes and paths
    try:
        parsed = urlparse(origin)
        if parsed.scheme and parsed.netloc:
            cors_origins.append(f"{parsed.scheme}://{parsed.netloc}")
        else:
            cors_origins.append(origin)
    except Exception:
        cors_origins.append(origin)

# In local development (not running on Render) also accept file:// pages
# (Origin header is the literal "null") and any LAN-IP host, so the frontend
# opened straight from disk or over the local network can reach the API.
# api-config.js treats the same hosts as "local" — localhost / 127.0.0.1 /
# 192.168.* / 10.* / 172.16–31.* — so keep both sides in sync.
IS_PROD = bool(os.getenv("RENDER"))
if not IS_PROD:
    cors_origins.append("null")  # file:// pages send Origin: null

# Remove duplicates while preserving order
cors_origins = list(dict.fromkeys(cors_origins))

# Accept any port for local dev (Live Server hops between 5500/5501/… when a
# port is busy). In dev this also covers LAN IPs so a phone on the same Wi-Fi
# can hit the API; in production only localhost is allowed via regex and the
# real origins come from the explicit allow_origins list above.
if IS_PROD:
    # Anchored: without ^...$ this would also be a prefix of hostile origins
    # like http://localhost.attacker.com (Starlette fullmatch()es today, but
    # don't leave the pattern depending on that).
    local_origin_regex = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
else:
    local_origin_regex = (
        r"^https?://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=local_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)

# Added last => outermost. The request id must be set before anything else
# runs, so every log line from CORS handling inward carries it.
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the full traceback, return the house-format error envelope.

    Starlette's default turns an unhandled exception into a bare 500 with the
    traceback on stderr in a shape nothing else here uses. Farmers get the
    Hindi message; we get a request-id-tagged traceback to grep for. The
    exception detail is deliberately NOT echoed to the client — it leaks
    table names and file paths.
    """
    log.exception(
        "unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "सर्वर में कुछ गड़बड़ हुई। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
            "data": {},
        },
    )


async def _warm_up_models():
    """
    Pre-load the sentence-transformer embedding model used by the semantic
    cache and RAG retriever. Without this, the FIRST /ask request pays the
    full cold-load cost (model download/load + first encode), which can
    exceed the 50s pipeline timeout — so the request dies before ever
    reaching Gemini. Runs in a background thread so boot isn't blocked.
    """
    def _load():
        from backend.config import get_setting
        if get_setting("cache_semantic_enabled", True):
            try:
                from cache.cache_engine import _get_model
                _get_model()  # loads cache embedding model
            except Exception as e:
                log.warning(f"⚠️ Cache model warm-up failed (non-fatal): {e}")
        else:
            log.info("[Cache] semantic disabled via CACHE_SEMANTIC_ENABLED=false — "
                  "skipping model warm-up (fuzzy text match only)")
        if not get_setting("rag_enabled", True):
            log.info("[RAG] disabled via RAG_ENABLED=false — skipping warm-up")
            return
        try:
            from rag.indexer import get_collection
            get_collection()  # loads ChromaDB (reuses cache's embedding model)
        except Exception as e:
            log.warning(f"⚠️ RAG model warm-up failed (non-fatal): {e}")

    await asyncio.to_thread(_load)
    log.info("🔥 Embedding models warmed up — first /ask will be fast.")


@app.on_event("startup")
async def startup():
    try:
        Base.metadata.create_all(bind=engine)   # ← create tables (cart, etc.)
        init_db()
        log.info("✅ Krishi Mitra database initialized.")
    except Exception as e:
        log.warning(f"⚠️ DB startup error (non-fatal): {e}")
    # Warm up embedding models in the background so the first question is fast
    asyncio.create_task(_warm_up_models())
    try:
        await start_scheduler()  # WEATHER CACHE — starts scheduler + immediate first fetch
    except Exception as e:
        log.warning(f"⚠️ Scheduler startup error (non-fatal): {e}")
    try:
        await start_mandi_scheduler()  # MANDI — daily fetch + immediate fetch if snapshot empty
    except Exception as e:
        log.warning(f"⚠️ Mandi scheduler startup error (non-fatal): {e}")
    try:
        await start_gsc_scheduler()  # GSC — daily /bhav staleness sweep + recrawl requests
    except Exception as e:
        log.warning(f"⚠️ GSC scheduler startup error (non-fatal): {e}")
    try:
        await start_mill_scheduler()  # /ganna — weekly sugar-mill register refresh
    except Exception as e:
        log.warning(f"⚠️ Mill register scheduler startup error (non-fatal): {e}")
    # MSP hides any crop it can't vouch for (unconfirmed figure, or a marketing
    # season past its valid_until). That silence is correct but invisible, so say
    # it out loud once at boot — otherwise a lapsed season is discovered by a
    # farmer seeing a missing block, not by us.
    try:
        from backend.services import msp as _msp
        _p = _msp.pending()
        if _p["unverified"] or _p["expired"]:
            log.info(f"ℹ️ MSP block hidden for — unverified: {_p['unverified'] or '—'}; "
                  f"season expired: {_p['expired'] or '—'} "
                  f"(fix in backend/data/msp_rates.json)")
    except Exception as e:
        log.warning(f"⚠️ MSP config check skipped (non-fatal): {e}")

# @app.post("/ask")
# async def ask(data: dict):
#     # Your logic here
#     return {"source": "manual", "answer": "Hello world", "cached": False}

# Register all routers
app.include_router(weather_router)
app.include_router(mandi_router)
app.include_router(fertilizer_router)
app.include_router(chatbot_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(search_router)   # NEW
app.include_router(cart_router)     # CART
app.include_router(order_router)    # ORDER
# NOTE: chat.py router deliberately NOT registered — chatbot.py has the full
# pipeline (Cache→RAG→Gemini→Ollama). chat.py was an older simplified version
# that duplicated POST /ask and caused routing conflicts.

from backend.routes import admin as admin_route
app.include_router(admin_route.router)

from backend.routes import share as share_route
app.include_router(share_route.router)  # OG link previews for shared mandi links

from backend.routes import bhav as bhav_route
app.include_router(bhav_route.router)   # SEO price pages (/bhav/*) + /bhav/sitemap.xml

from backend.routes import bazar as bazar_route
app.include_router(bazar_route.router)  # KRASHI BAZAR — social crop marketplace

from backend.routes import crop_calendar as crop_calendar_route
app.include_router(crop_calendar_route.router)  # मेरी फसल — crop calendar (stage timeline + tasks)

from backend.routes import alerts as alerts_route
app.include_router(alerts_route.router)  # 🔔 mandi bhav price alerts (web push)

from backend.routes import appeal as appeal_route
app.include_router(appeal_route.router)  # बेचना/खरीदना है — sell/buy appeals raised on /bhav pages

from backend.routes import dukanlisting as dukanlisting_route
app.include_router(dukanlisting_route.router)   # अपनी दुकान लिस्ट करें — login-gated, paid dealer subscriptions (/dukanlisting)

from backend.routes import pay as pay_route
app.include_router(pay_route.router)     # /pay — UPI listing-fee page sent to a dealer over WhatsApp (noindex)

from backend.routes import product as product_route
app.include_router(product_route.router)  # SEO shop-product pages (/product/*) + /product/sitemap.xml

# Must follow product_route: krashi_dukan imports its card/hero CSS so the two
# catalogues render identically. A different business from both /product (our
# own catalogue) and /dukanlisting (/bhav ad slots) — see the module header.
from backend.routes import krashi_dukan as krashi_dukan_route
app.include_router(krashi_dukan_route.router)  # कृषि दुकान — local shop directory (/krashi_dukan/*)

from backend.routes import admin_dukan as admin_dukan_route
app.include_router(admin_dukan_route.router)   # /admin/dukan/* — shops, catalogue, prices, UPI collect

from backend.routes import articles as articles_route
app.include_router(articles_route.router)  # /articles/meta — live published/updated dates from article JSON-LD

from backend.routes import credits as credits_route
app.include_router(credits_route.router)  # /articles/credits — Commons photo attribution the licences require (noindex)

from backend.routes import naksha as naksha_route
app.include_router(naksha_route.router)  # /naksha, /naksha/{state}[/jile] + /map — state district maps

from backend.routes import sawal as sawal_route
app.include_router(sawal_route.router)  # /sawal — real Kisan Call Centre Q&A, per crop

from backend.routes import ganna as ganna_route
app.include_router(ganna_route.router)  # /ganna — cane SAP/FRP per state + /ganna/sitemap.xml

from backend.routes import sitemap as sitemap_route
app.include_router(sitemap_route.router)  # /sitemap.xml — generated from the pages/articles on disk

from backend.routes import llms as llms_route
app.include_router(llms_route.router)   # /llms.txt — AI-agent site guide, generated like the sitemap

from backend.routes import health as health_route
app.include_router(health_route.router)  # /health (page + liveness), /health/checks, /health/data

# ── Run locally ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=DEBUG,
    )



# ── Frontend mount ──────────────────────────────────────────────────
# Commented out root JSON route so it serves index.html instead
# @app.get("/")
# async def root():
#     return {
#         "app": "KrashiMitra",
#         "status": "API is running! 🌾",
#         "version": "0.1.0",
#         "message": "किसान का डिजिटल साथी",
#     }
#
# /health, /health/checks and /health/data now live in routes/health.py —
# see the header there for why /health stays database-free for the keep-alive
# ping while the same URL serves a full status page to a browser.

# Add this AFTER all app.include_router() lines, at the bottom
app.mount("/admin", StaticFiles(directory=BASE_DIR / "admin", html=True), name="admin")

# Bazar post photos/videos (uploads/bazar/*) — dir is created by routes/bazar.py
app.mount("/uploads", StaticFiles(directory=BASE_DIR / "uploads"), name="uploads")

# Serve the entire frontend directly at root
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
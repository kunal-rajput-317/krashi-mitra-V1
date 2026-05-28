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

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

load_dotenv()

from backend.routes import cart  # ensure CartItem model registered before create_all

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

app = FastAPI(
    title="KrashiMitra API",
    description="Hindi-first Agriculture Intelligence Platform for Indian Farmers",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import urlparse

raw_origins = os.getenv(
    "CORS_ORIGINS",
    ",".join([
        "https://krashimitra.in",
        "https://www.krashimitra.in",
        "https://krashi-mitra-v1.onrender.com",
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

# Remove duplicates while preserving order
cors_origins = list(dict.fromkeys(cors_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        Base.metadata.create_all(bind=engine)   # ← create tables (cart, etc.)
        init_db()
        print("✅ Krishi Mitra database initialized.")
    except Exception as e:
        print(f"⚠️ DB startup error (non-fatal): {e}")
    try:
        await start_scheduler()  # WEATHER CACHE — starts scheduler + immediate first fetch
    except Exception as e:
        print(f"⚠️ Scheduler startup error (non-fatal): {e}")

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

# ── Run locally ──────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=DEBUG,
    )



# ── Health check ─────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "app": "KrashiMitra",
        "status": "API is running! 🌾",
        "version": "0.1.0",
        "message": "किसान का डिजिटल साथी",
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

# Add this AFTER all app.include_router() lines, at the bottom
app.mount("/admin", StaticFiles(directory=BASE_DIR / "admin", html=True), name="admin")
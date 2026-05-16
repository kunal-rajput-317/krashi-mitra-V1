# ============================================================
# Krishi Mitra — Backend API
# Framework: FastAPI | AI: Ollama (qwen:14b)
# Database: PostgreSQL | ORM: SQLAlchemy
# ============================================================
# Modularization status:
#   ✅ weather    → routes/weather.py    + services/weather_service.py
#   ✅ mandi      → routes/mandi.py      + services/mandi_service.py
#   ✅ fertilizer → routes/fertilizer.py + services/fertilizer_service.py
#   ✅ chatbot    → routes/chatbot.py    + services/chatbot_service.py
#   ✅ auth       → routes/auth.py
#   ✅ profile    → routes/profile.py
#   ✅ search     → routes/search.py     + services/search_service.py  ← NEW
# ============================================================

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.routes import chat, weather, mandi
import os
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG    = os.getenv("DEBUG", "true").lower() == "true"

from dotenv import load_dotenv
load_dotenv()

from backend.database.db import MandiPrice, get_db, init_db

# ── Routers ──────────────────────────────────────────────────
from backend.routes.weather    import router as weather_router
from backend.routes.mandi      import router as mandi_router
from backend.routes.fertilizer import router as fertilizer_router
from backend.routes.chatbot    import router as chatbot_router
from backend.routes.auth       import router as auth_router
from backend.routes.profile    import router as profile_router
from backend.routes.search     import router as search_router   # NEW

from backend.services.weather_scheduler import start_scheduler  # WEATHER CACHE

app = FastAPI(
    title="KrashiMitra API",
    description="Hindi-first Agriculture Intelligence Platform for Indian Farmers",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────
# Allow your local frontend to call the API
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,

    allow_origins=["https://krashi-mitra-v1.onrender.com"], 
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=["*"],
)



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
app.include_router(chat.router)
app.include_router(weather.router)
app.include_router(mandi.router)

from backend.routes import admin as admin_route
app.include_router(admin_route.router)

# Initialize database tables on startup
@app.on_event("startup")
async def startup():
    init_db()
    print("✅ Krishi Mitra database initialized.")
    await start_scheduler()  # WEATHER CACHE — starts scheduler + immediate first fetch

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

from fastapi.staticfiles import StaticFiles

# Add this AFTER all app.include_router() lines, at the bottom
app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")

from fastapi.staticfiles import StaticFiles
app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")
# ============================================================
# backend/database/db.py
# KrashiMitra — Database Configuration
# Database: PostgreSQL | ORM: SQLAlchemy
# ============================================================
# CHANGED IN THIS STEP:
#   + Added WeatherCache model for weather caching system
#   All existing models (User, UserProfile, ChatHistory,
#   MandiPrice) are preserved exactly — zero changes to them.
# ============================================================

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

BASE_DIR = os.getcwd()
env_path = os.path.join(BASE_DIR, ".env")
load_dotenv(env_path)

# ── Database Connection ──────────────────────────────────────
DB_USER     = os.getenv("DB_USER", "neondb_owner")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST     = os.getenv("DB_HOST", "postgresql://neondb_owner:npg_6BEHp8TGhFxU@ep-gentle-flower-ap90gedq-pooler.c-7.us-east-1.aws.neon.tech/krashi_mitra_database?sslmode=require&channel_binding=require")
DB_PORT     = os.getenv("DB_PORT", "5432")
DB_NAME     = os.getenv("DB_NAME", "krashi_mitra_database")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

print(f"🗄️  Connecting to: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


# ── WEATHER CACHE MODEL (NEW) ────────────────────────────────

class WeatherCache(Base):
    """
    Weather cache table — one row per district/city combo.
    Populated by APScheduler every 8 hours.
    User requests read ONLY from this table — no direct OWM calls.

    UP Coverage:
      75 districts mapped to their best OWM city string.
      Scheduler upserts all rows every 8 hours.
      Budget: 75 districts × 3 runs/day = 225 calls/day  (well within 1000/day free limit)
    """
    __tablename__ = "weather_cache"

    id                = Column(Integer,  primary_key=True, index=True)

    # Location identifiers
    district          = Column(String,   nullable=False, unique=True, index=True)
    city              = Column(String,   nullable=False)          # OWM query string e.g. "Meerut,IN"
    state             = Column(String,   default="Uttar Pradesh", nullable=False)

    # Core weather fields (matches DB_SCHEMA.md weather_data columns)
    temperature       = Column(Float,    nullable=True)           # °C
    feels_like        = Column(Float,    nullable=True)           # °C
    humidity          = Column(Integer,  nullable=True)           # %
    wind_speed        = Column(Float,    nullable=True)           # m/s from OWM
    rainfall          = Column(Float,    default=0.0, nullable=True)  # mm last 1h
    weather_condition = Column(String,   nullable=True)           # e.g. "Haze", "Clear"
    icon_url          = Column(String,   nullable=True)           # OWM icon URL

    # Farming intelligence
    farming_tip       = Column(Text,     nullable=True)           # Hindi-aware tip

    # Cache metadata
    fetched_at        = Column(DateTime, nullable=True)           # last successful OWM fetch
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_stale          = Column(Boolean,  default=False)           # True if fetch failed last run


# ── DISTRICT → OWM CITY MAP (ALL 75 UP DISTRICTS) ──────────
# Used by both weather_service.py and weather_scheduler.py
# Centralised here so both modules import from one place.

UP_DISTRICT_CITY_MAP = {
    # Division: Agra
    "Agra":          "Agra,IN",
    "Firozabad":     "Firozabad,IN",
    "Mainpuri":      "Mainpuri,IN",
    "Mathura":       "Mathura,IN",

    # Division: Aligarh
    "Aligarh":       "Aligarh,IN",
    "Etah":          "Etah,IN",
    "Hathras":       "Hathras,IN",
    "Kasganj":       "Kasganj,IN",

    # Division: Allahabad (Prayagraj)
    "Prayagraj":     "Allahabad,IN",
    "Fatehpur":      "Fatehpur,IN",
    "Kaushambi":     "Kaushambi,IN",
    "Pratapgarh":    "Pratapgarh,IN",

    # Division: Ayodhya
    "Ayodhya":       "Faizabad,IN",
    "Ambedkar Nagar":"Akbarpur,IN",
    "Amethi":        "Amethi,IN",
    "Barabanki":     "Barabanki,IN",
    "Sultanpur":     "Sultanpur,IN",

    # Division: Azamgarh
    "Azamgarh":      "Azamgarh,IN",
    "Ballia":        "Ballia,IN",
    "Mau":           "Mau,IN",

    # Division: Bareilly
    "Bareilly":      "Bareilly,IN",
    "Badaun":        "Badaun,IN",
    "Pilibhit":      "Pilibhit,IN",
    "Shahjahanpur":  "Shahjahanpur,IN",

    # Division: Basti
    "Basti":         "Basti,IN",
    "Sant Kabir Nagar": "Khalilabad,IN",
    "Siddharthnagar":"Siddharthnagar,IN",

    # Division: Chitrakoot
    "Banda":         "Banda,IN",
    "Chitrakoot":    "Karwi,IN",
    "Hamirpur":      "Hamirpur,IN",
    "Mahoba":        "Mahoba,IN",

    # Division: Devipatan
    "Bahraich":      "Bahraich,IN",
    "Balrampur":     "Balrampur,IN",
    "Gonda":         "Gonda,IN",
    "Shravasti":     "Bhinga,IN",

    # Division: Gorakhpur
    "Gorakhpur":     "Gorakhpur,IN",
    "Deoria":        "Deoria,IN",
    "Kushinagar":    "Kushinagar,IN",
    "Maharajganj":   "Maharajganj,IN",

    # Division: Jhansi
    "Jhansi":        "Jhansi,IN",
    "Jalaun":        "Orai,IN",
    "Lalitpur":      "Lalitpur,IN",

    # Division: Kanpur
    "Kanpur Nagar":  "Kanpur,IN",
    "Kanpur Dehat":  "Akbarpur,IN",
    "Etawah":        "Etawah,IN",
    "Farrukhabad":   "Fatehgarh,IN",
    "Auraiya":       "Auraiya,IN",
    "Kannauj":       "Kannauj,IN",

    # Division: Lucknow
    "Lucknow":       "Lucknow,IN",
    "Hardoi":        "Hardoi,IN",
    "Lakhimpur Kheri":"Lakhimpur,IN",
    "Raebareli":     "Raebareli,IN",
    "Sitapur":       "Sitapur,IN",
    "Unnao":         "Unnao,IN",

    # Division: Meerut
    "Meerut":        "Meerut,IN",
    "Baghpat":       "Baghpat,IN",
    "Bulandshahr":   "Bulandshahr,IN",
    "Ghaziabad":     "Ghaziabad,IN",
    "Gautam Buddha Nagar": "Noida,IN",
    "Hapur":         "Hapur,IN",

    # Division: Mirzapur
    "Mirzapur":      "Mirzapur,IN",
    "Bhadohi":       "Bhadohi,IN",
    "Sonbhadra":     "Robertsganj,IN",

    # Division: Moradabad
    "Moradabad":     "Moradabad,IN",
    "Amroha":        "Amroha,IN",
    "Bijnor":        "Bijnor,IN",
    "Rampur":        "Rampur,IN",
    "Sambhal":       "Sambhal,IN",

    # Division: Saharanpur
    "Saharanpur":    "Saharanpur,IN",
    "Muzaffarnagar": "Muzaffarnagar,IN",
    "Shamli":        "Shamli,IN",

    # Division: Varanasi
    "Varanasi":      "Varanasi,IN",
    "Chandauli":     "Chandauli,IN",
    "Jaunpur":       "Jaunpur,IN",
    "Ghazipur":      "Ghazipur,IN",
}
# Total: 75 districts
# API budget: 75 × 3 fetches/day = 225 calls/day ✅ (< 1000 free limit)


# ── AUTH MODEL (EXISTING — UNCHANGED) ───────────────────────

class User(Base):
    """
    Auth users table — matches DB_SCHEMA.md exactly.
    Separate from UserProfile (which handles farmer profile data).
    """
    __tablename__ = "users"

    id                 = Column(Integer,  primary_key=True, index=True)
    name               = Column(String,   nullable=False)
    email              = Column(String,   unique=True, nullable=False, index=True)
    hashed_password    = Column(String,   nullable=False)
    is_verified        = Column(Boolean,  default=False, nullable=False)
    otp                = Column(String,   nullable=True)
    otp_expiry         = Column(DateTime, nullable=True)
    preferred_language = Column(String,   default="hindi", nullable=True)
    village            = Column(String,   nullable=True)
    district           = Column(String,   nullable=True)
    primary_crop       = Column(String,   default="Wheat", nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


# ── EXISTING MODELS (UNCHANGED) ──────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id           = Column(Integer,  primary_key=True, index=True)
    user_id      = Column(Integer,  nullable=True, index=True)   # FK → users.id
    name         = Column(String,   nullable=False)
    phone_number = Column(String,   nullable=True)
    village      = Column(String,   nullable=True)
    district     = Column(String,   nullable=True)
    state        = Column(String,   nullable=True)
    primary_crop = Column(String,   default="Wheat")
    crops_grown  = Column(String,   nullable=True)               # comma-separated
    farm_size    = Column(String,   nullable=True)
    language     = Column(String,   default="hindi")
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow)


class ChatHistory(Base):
    __tablename__ = "chat_history"
    id         = Column(Integer,  primary_key=True, index=True)
    user_id    = Column(Integer,  nullable=True)
    crop       = Column(String,   nullable=True)
    district   = Column(String,   nullable=True)
    role       = Column(String,   nullable=False)
    message    = Column(Text,     nullable=False)
    language   = Column(String,   default="english")
    created_at = Column(DateTime, default=datetime.utcnow)


class MandiPrice(Base):
    __tablename__ = "mandi_prices"
    id           = Column(Integer,  primary_key=True, index=True)
    commodity    = Column(String,   nullable=False)
    district     = Column(String,   nullable=True)
    market       = Column(String,   nullable=True)
    variety      = Column(String,   nullable=True)
    min_price    = Column(String,   nullable=True)
    max_price    = Column(String,   nullable=True)
    modal_price  = Column(String,   nullable=True)
    arrival_date = Column(String,   nullable=True)
    fetched_at   = Column(DateTime, default=datetime.utcnow)


# ── DB Helpers ───────────────────────────────────────────────

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"⚠️  Database error: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
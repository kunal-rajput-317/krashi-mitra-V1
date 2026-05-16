# ============================================================
# backend/database/db.py
# KrashiMitra — Database Configuration
# ============================================================

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# ── Database Connection ──────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set!")

# Fix postgres:// → postgresql:// (Neon/Heroku style)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Ensure SSL for Neon
if "sslmode" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

print(f"✅ DB connecting to: {DATABASE_URL[:50]}...")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


# ── WEATHER CACHE MODEL ──────────────────────────────────────

class WeatherCache(Base):
    __tablename__ = "weather_cache"

    id                = Column(Integer,  primary_key=True, index=True)
    district          = Column(String,   nullable=False, unique=True, index=True)
    city              = Column(String,   nullable=False)
    state             = Column(String,   default="Uttar Pradesh", nullable=False)
    temperature       = Column(Float,    nullable=True)
    feels_like        = Column(Float,    nullable=True)
    humidity          = Column(Integer,  nullable=True)
    wind_speed        = Column(Float,    nullable=True)
    rainfall          = Column(Float,    default=0.0, nullable=True)
    weather_condition = Column(String,   nullable=True)
    icon_url          = Column(String,   nullable=True)
    farming_tip       = Column(Text,     nullable=True)
    fetched_at        = Column(DateTime, nullable=True)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_stale          = Column(Boolean,  default=False)


# ── DISTRICT → OWM CITY MAP (ALL 75 UP DISTRICTS) ───────────

UP_DISTRICT_CITY_MAP = {
    "Agra":          "Agra,IN",
    "Firozabad":     "Firozabad,IN",
    "Mainpuri":      "Mainpuri,IN",
    "Mathura":       "Mathura,IN",
    "Aligarh":       "Aligarh,IN",
    "Etah":          "Etah,IN",
    "Hathras":       "Hathras,IN",
    "Kasganj":       "Kasganj,IN",
    "Prayagraj":     "Allahabad,IN",
    "Fatehpur":      "Fatehpur,IN",
    "Kaushambi":     "Kaushambi,IN",
    "Pratapgarh":    "Pratapgarh,IN",
    "Ayodhya":       "Faizabad,IN",
    "Ambedkar Nagar":"Akbarpur,IN",
    "Amethi":        "Amethi,IN",
    "Barabanki":     "Barabanki,IN",
    "Sultanpur":     "Sultanpur,IN",
    "Azamgarh":      "Azamgarh,IN",
    "Ballia":        "Ballia,IN",
    "Mau":           "Mau,IN",
    "Bareilly":      "Bareilly,IN",
    "Badaun":        "Badaun,IN",
    "Pilibhit":      "Pilibhit,IN",
    "Shahjahanpur":  "Shahjahanpur,IN",
    "Basti":         "Basti,IN",
    "Sant Kabir Nagar": "Khalilabad,IN",
    "Siddharthnagar":"Siddharthnagar,IN",
    "Banda":         "Banda,IN",
    "Chitrakoot":    "Karwi,IN",
    "Hamirpur":      "Hamirpur,IN",
    "Mahoba":        "Mahoba,IN",
    "Bahraich":      "Bahraich,IN",
    "Balrampur":     "Balrampur,IN",
    "Gonda":         "Gonda,IN",
    "Shravasti":     "Bhinga,IN",
    "Gorakhpur":     "Gorakhpur,IN",
    "Deoria":        "Deoria,IN",
    "Kushinagar":    "Kushinagar,IN",
    "Maharajganj":   "Maharajganj,IN",
    "Jhansi":        "Jhansi,IN",
    "Jalaun":        "Orai,IN",
    "Lalitpur":      "Lalitpur,IN",
    "Kanpur Nagar":  "Kanpur,IN",
    "Kanpur Dehat":  "Akbarpur,IN",
    "Etawah":        "Etawah,IN",
    "Farrukhabad":   "Fatehgarh,IN",
    "Auraiya":       "Auraiya,IN",
    "Kannauj":       "Kannauj,IN",
    "Lucknow":       "Lucknow,IN",
    "Hardoi":        "Hardoi,IN",
    "Lakhimpur Kheri":"Lakhimpur,IN",
    "Raebareli":     "Raebareli,IN",
    "Sitapur":       "Sitapur,IN",
    "Unnao":         "Unnao,IN",
    "Meerut":        "Meerut,IN",
    "Baghpat":       "Baghpat,IN",
    "Bulandshahr":   "Bulandshahr,IN",
    "Ghaziabad":     "Ghaziabad,IN",
    "Gautam Buddha Nagar": "Noida,IN",
    "Hapur":         "Hapur,IN",
    "Mirzapur":      "Mirzapur,IN",
    "Bhadohi":       "Bhadohi,IN",
    "Sonbhadra":     "Robertsganj,IN",
    "Moradabad":     "Moradabad,IN",
    "Amroha":        "Amroha,IN",
    "Bijnor":        "Bijnor,IN",
    "Rampur":        "Rampur,IN",
    "Sambhal":       "Sambhal,IN",
    "Saharanpur":    "Saharanpur,IN",
    "Muzaffarnagar": "Muzaffarnagar,IN",
    "Shamli":        "Shamli,IN",
    "Varanasi":      "Varanasi,IN",
    "Chandauli":     "Chandauli,IN",
    "Jaunpur":       "Jaunpur,IN",
    "Ghazipur":      "Ghazipur,IN",
}


# ── AUTH MODEL ───────────────────────────────────────────────

class User(Base):
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
    primary_crop       = Column(String,   default="Sugarcane", nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


# ── OTHER MODELS ─────────────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id           = Column(Integer,  primary_key=True, index=True)
    user_id      = Column(Integer,  nullable=True, index=True)
    name         = Column(String,   nullable=False)
    phone_number = Column(String,   nullable=True)
    village      = Column(String,   nullable=True)
    district     = Column(String,   nullable=True)
    state        = Column(String,   nullable=True)
    primary_crop = Column(String,   default="Sugarcane")
    crops_grown  = Column(String,   nullable=True)
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
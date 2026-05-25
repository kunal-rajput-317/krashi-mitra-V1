# ============================================================
# backend/database/db.py
# KrashiMitra — Database Configuration
# ============================================================

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, text
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

# Ensure SSL for Neon/Postgres URLs only
if DATABASE_URL.startswith("postgresql") and "sslmode" not in DATABASE_URL:
    separator = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL += f"{separator}sslmode=require"

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

def _ensure_postgres_columns():
    """Add columns that older Neon tables may be missing."""
    if engine.dialect.name != "postgresql":
        return

    schema_patches = {
        "users": [
            ("hashed_password", "VARCHAR"),
            ("is_verified", "BOOLEAN DEFAULT FALSE"),
            ("otp", "VARCHAR"),
            ("otp_expiry", "TIMESTAMP"),
            ("preferred_language", "VARCHAR DEFAULT 'hindi'"),
            ("village", "VARCHAR"),
            ("district", "VARCHAR"),
            ("primary_crop", "VARCHAR DEFAULT 'Sugarcane'"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ],
        "user_profiles": [
            ("user_id", "INTEGER"),
            ("phone_number", "VARCHAR"),
            ("village", "VARCHAR"),
            ("district", "VARCHAR"),
            ("state", "VARCHAR"),
            ("primary_crop", "VARCHAR DEFAULT 'Sugarcane'"),
            ("crops_grown", "VARCHAR"),
            ("farm_size", "VARCHAR"),
            ("language", "VARCHAR DEFAULT 'hindi'"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ],
        "weather_cache": [
            ("city", "VARCHAR"),
            ("state", "VARCHAR DEFAULT 'Uttar Pradesh'"),
            ("temperature", "FLOAT"),
            ("feels_like", "FLOAT"),
            ("humidity", "INTEGER"),
            ("wind_speed", "FLOAT"),
            ("rainfall", "FLOAT DEFAULT 0"),
            ("weather_condition", "TEXT"),
            ("icon_url", "VARCHAR"),
            ("farming_tip", "TEXT"),
            ("fetched_at", "TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("is_stale", "BOOLEAN DEFAULT FALSE"),
        ],
        "chat_history": [
            ("user_id", "INTEGER"),
            ("crop", "VARCHAR"),
            ("district", "VARCHAR"),
            ("language", "VARCHAR DEFAULT 'english'"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ],
        "mandi_prices": [
            ("commodity", "VARCHAR"),
            ("district", "VARCHAR"),
            ("market", "VARCHAR"),
            ("variety", "VARCHAR"),
            ("min_price", "VARCHAR"),
            ("max_price", "VARCHAR"),
            ("modal_price", "VARCHAR"),
            ("arrival_date", "VARCHAR"),
            ("fetched_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ],
        "carts": [
            ("id", "INTEGER"),
            ("user_id", "INTEGER"),
            ("product_id", "INTEGER"),
            ("quantity", "INTEGER DEFAULT 1"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("session_id", "VARCHAR"),
        ],
    }

    with engine.begin() as conn:
        for table_name, columns in schema_patches.items():
            for column_name, column_type in columns:
                conn.execute(text(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN IF NOT EXISTS "{column_name}" {column_type}'
                ))

        conn.execute(text("""
            CREATE SEQUENCE IF NOT EXISTS carts_id_seq OWNED BY carts.id;
            ALTER TABLE carts ALTER COLUMN id SET DEFAULT nextval('carts_id_seq');
            UPDATE carts SET id = nextval('carts_id_seq') WHERE id IS NULL;
            ALTER TABLE carts ALTER COLUMN id SET NOT NULL;
        """))
        conn.execute(text("""
            DO $$
            DECLARE
                pk_name text;
                pk_cols text[];
            BEGIN
                SELECT c.conname, array_agg(a.attname ORDER BY u.ordinality)
                INTO pk_name, pk_cols
                FROM pg_constraint c
                JOIN unnest(c.conkey) WITH ORDINALITY AS u(attnum, ordinality) ON true
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid
                 AND a.attnum = u.attnum
                WHERE c.conrelid = 'carts'::regclass
                  AND c.contype = 'p'
                GROUP BY c.conname;

                IF pk_name IS NOT NULL AND pk_cols <> ARRAY['id'] THEN
                    EXECUTE format('ALTER TABLE carts DROP CONSTRAINT %I', pk_name);
                    pk_name := NULL;
                END IF;

                IF pk_name IS NULL THEN
                    ALTER TABLE carts ADD CONSTRAINT carts_pkey PRIMARY KEY (id);
                END IF;
            END $$;
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS carts_user_product_uidx
            ON carts(user_id, product_id)
            WHERE user_id IS NOT NULL;
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS carts_session_product_uidx
            ON carts(session_id, product_id)
            WHERE session_id IS NOT NULL AND user_id IS NULL;
        """))


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        _ensure_postgres_columns()
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"⚠️  Database error: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================
# backend/database/db.py
# KrashiMitra — Database Configuration
# ============================================================

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Text, Boolean, Float, text
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


# ── WEATHER HISTORY MODEL ────────────────────────────────────

class WeatherHistory(Base):
    """One row per fetch per district — retains last 7 days, auto-purged."""
    __tablename__ = "weather_history"

    id                = Column(Integer,  primary_key=True, index=True)
    district          = Column(String,   nullable=False, index=True)
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
    fetched_at        = Column(DateTime, nullable=False, index=True)


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
    auth_provider      = Column(String,   default="email", nullable=True)  # "email" | "google"
    google_id          = Column(String,   nullable=True, index=True)        # Google's permanent sub
    village            = Column(String,   nullable=True)
    district           = Column(String,   nullable=True)
    primary_crop       = Column(String,   default="Sugarcane", nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


# ── OTHER MODELS ─────────────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    # Core
    id                   = Column(Integer,  primary_key=True, index=True)
    user_id              = Column(Integer,  nullable=True, index=True)

    # Personal
    name                 = Column(String,   nullable=False)
    phone_number         = Column(String,   nullable=True)
    whatsapp_number      = Column(String,   nullable=True)
    dob                  = Column(String,   nullable=True)   # stored as string YYYY-MM-DD
    gender               = Column(String,   nullable=True)
    education            = Column(String,   nullable=True)
    farming_experience   = Column(String,   nullable=True)
    family_size          = Column(Integer,  nullable=True)

    # Location
    state                = Column(String,   nullable=True)
    district             = Column(String,   nullable=True)
    tehsil               = Column(String,   nullable=True)
    village              = Column(String,   nullable=True)
    pin_code             = Column(String,   nullable=True)
    nearest_mandi        = Column(String,   nullable=True)

    # Farm
    farm_size            = Column(String,   nullable=True)
    farm_size_unit       = Column(String,   default="acres")
    land_ownership       = Column(String,   nullable=True)
    soil_type            = Column(String,   nullable=True)
    irrigation_type      = Column(String,   nullable=True)
    khasra_number        = Column(String,   nullable=True)

    # Equipment (checkboxes)
    eq_tractor           = Column(Boolean,  default=False)
    eq_pump              = Column(Boolean,  default=False)
    eq_thresher          = Column(Boolean,  default=False)
    eq_sprayer           = Column(Boolean,  default=False)
    eq_harvester         = Column(Boolean,  default=False)
    eq_none              = Column(Boolean,  default=False)

    # Crops
    primary_crop         = Column(String,   default="Sugarcane")
    crops_grown          = Column(String,   nullable=True)
    farming_season       = Column(String,   nullable=True)
    farming_type         = Column(String,   nullable=True)
    yield_per_acre       = Column(String,   nullable=True)
    crop_problems        = Column(Text,     nullable=True)

    # Schemes & Finance
    pm_kisan_registered  = Column(Boolean,  default=False)
    has_kcc              = Column(Boolean,  default=False)
    aadhaar_linked       = Column(Boolean,  default=False)
    fasal_bima           = Column(Boolean,  default=False)
    bank_name            = Column(String,   nullable=True)
    annual_income        = Column(String,   nullable=True)

    # Preferences
    language             = Column(String,   default="hindi")
    advisory_type        = Column(String,   nullable=True)
    special_needs        = Column(Text,     nullable=True)

    # Notifications
    notif_weather        = Column(Boolean,  default=False)
    notif_mandi          = Column(Boolean,  default=False)
    notif_scheme         = Column(Boolean,  default=False)
    notif_pest           = Column(Boolean,  default=False)
    notif_tips           = Column(Boolean,  default=False)
    notif_none           = Column(Boolean,  default=False)

    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow)


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
    """Latest snapshot — rebuilt every fetch. One row per market/commodity/variety."""
    __tablename__ = "mandi_prices"
    id               = Column(Integer,  primary_key=True, index=True)
    state            = Column(String,   nullable=True, index=True)
    commodity        = Column(String,   nullable=False, index=True)
    district         = Column(String,   nullable=True, index=True)
    market           = Column(String,   nullable=True)
    variety          = Column(String,   nullable=True)
    grade            = Column(String,   nullable=True)
    min_price        = Column(String,   nullable=True)
    max_price        = Column(String,   nullable=True)
    modal_price      = Column(String,   nullable=True)
    prev_modal_price = Column(String,   nullable=True)   # last recorded modal before this date
    change_pct       = Column(Float,    nullable=True)   # % change vs prev_modal_price
    spark            = Column(String,   nullable=True)   # comma-joined last ~8 modal prices (chronological)
    arrival_date     = Column(String,   nullable=True)
    fetched_at       = Column(DateTime, default=datetime.utcnow)


class MandiPriceHistory(Base):
    """Append-only daily history. Never auto-purged — full trend retained."""
    __tablename__ = "mandi_price_history"
    id           = Column(Integer,  primary_key=True, index=True)
    state        = Column(String,   nullable=True, index=True)
    district     = Column(String,   nullable=True, index=True)
    market       = Column(String,   nullable=True)
    commodity    = Column(String,   nullable=False, index=True)
    variety      = Column(String,   nullable=True)
    grade        = Column(String,   nullable=True)
    min_price    = Column(String,   nullable=True)
    max_price    = Column(String,   nullable=True)
    modal_price  = Column(String,   nullable=True)
    arrival_date = Column(String,   nullable=True)          # original DD/MM/YYYY from API
    arrival_dt   = Column(Date,     nullable=True, index=True)  # parsed for ordering
    group_key    = Column(String,   nullable=True, index=True)  # md5(state|district|market|commodity|variety|grade)
    row_key      = Column(String,   nullable=True, unique=True, index=True)  # group_key + arrival_date — dedup
    fetched_at   = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"extend_existing": True}

    id            = Column(Integer,  primary_key=True, autoincrement=True)
    tracking_code = Column(String,   nullable=False, unique=True, index=True)
    user_id       = Column(Integer,  nullable=True, index=True)   # links to users.id (NULL for guests)
    user_email    = Column(String,   nullable=True)                # stored for easy lookup
    user_name     = Column(String,   nullable=True)                # stored for easy lookup
    session_id    = Column(String,   nullable=True, index=True)   # guest identifier
    is_guest      = Column(Boolean,  default=True)
    product_name  = Column(String,   nullable=False)
    product_id    = Column(Integer,  nullable=True)
    quantity      = Column(Integer,  default=1)
    unit_price    = Column(Float,    nullable=False)
    total         = Column(Float,    nullable=False)
    phone         = Column(String,   nullable=False)
    source        = Column(String,   default="shop")   # "shop" or "mandi"
    status        = Column(String,   default="Pending")  # Pending / Confirmed / Delivered
    created_at    = Column(DateTime, default=datetime.utcnow)


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
            ("auth_provider", "VARCHAR DEFAULT 'email'"),
            ("google_id",     "VARCHAR"),
            ("village", "VARCHAR"),
            ("district", "VARCHAR"),
            ("primary_crop", "VARCHAR DEFAULT 'Sugarcane'"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ],
        "user_profiles": [
            ("user_id",              "INTEGER"),
            # Personal
            ("phone_number",         "VARCHAR"),
            ("whatsapp_number",      "VARCHAR"),
            ("dob",                  "VARCHAR"),
            ("gender",               "VARCHAR"),
            ("education",            "VARCHAR"),
            ("farming_experience",   "VARCHAR"),
            ("family_size",          "INTEGER"),
            # Location
            ("state",                "VARCHAR"),
            ("district",             "VARCHAR"),
            ("tehsil",               "VARCHAR"),
            ("village",              "VARCHAR"),
            ("pin_code",             "VARCHAR"),
            ("nearest_mandi",        "VARCHAR"),
            # Farm
            ("farm_size",            "VARCHAR"),
            ("farm_size_unit",       "VARCHAR DEFAULT 'acres'"),
            ("land_ownership",       "VARCHAR"),
            ("soil_type",            "VARCHAR"),
            ("irrigation_type",      "VARCHAR"),
            ("khasra_number",        "VARCHAR"),
            # Equipment
            ("eq_tractor",           "BOOLEAN DEFAULT FALSE"),
            ("eq_pump",              "BOOLEAN DEFAULT FALSE"),
            ("eq_thresher",          "BOOLEAN DEFAULT FALSE"),
            ("eq_sprayer",           "BOOLEAN DEFAULT FALSE"),
            ("eq_harvester",         "BOOLEAN DEFAULT FALSE"),
            ("eq_none",              "BOOLEAN DEFAULT FALSE"),
            # Crops
            ("primary_crop",         "VARCHAR DEFAULT 'Sugarcane'"),
            ("crops_grown",          "VARCHAR"),
            ("farming_season",       "VARCHAR"),
            ("farming_type",         "VARCHAR"),
            ("yield_per_acre",       "VARCHAR"),
            ("crop_problems",        "TEXT"),
            # Schemes
            ("pm_kisan_registered",  "BOOLEAN DEFAULT FALSE"),
            ("has_kcc",              "BOOLEAN DEFAULT FALSE"),
            ("aadhaar_linked",       "BOOLEAN DEFAULT FALSE"),
            ("fasal_bima",           "BOOLEAN DEFAULT FALSE"),
            ("bank_name",            "VARCHAR"),
            ("annual_income",        "VARCHAR"),
            # Preferences
            ("language",             "VARCHAR DEFAULT 'hindi'"),
            ("advisory_type",        "VARCHAR"),
            ("special_needs",        "TEXT"),
            # Notifications
            ("notif_weather",        "BOOLEAN DEFAULT FALSE"),
            ("notif_mandi",          "BOOLEAN DEFAULT FALSE"),
            ("notif_scheme",         "BOOLEAN DEFAULT FALSE"),
            ("notif_pest",           "BOOLEAN DEFAULT FALSE"),
            ("notif_tips",           "BOOLEAN DEFAULT FALSE"),
            ("notif_none",           "BOOLEAN DEFAULT FALSE"),
            ("created_at",           "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at",           "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
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
            ("state", "VARCHAR"),
            ("commodity", "VARCHAR"),
            ("district", "VARCHAR"),
            ("market", "VARCHAR"),
            ("variety", "VARCHAR"),
            ("grade", "VARCHAR"),
            ("min_price", "VARCHAR"),
            ("max_price", "VARCHAR"),
            ("modal_price", "VARCHAR"),
            ("prev_modal_price", "VARCHAR"),
            ("change_pct", "FLOAT"),
            ("spark", "VARCHAR"),
            ("arrival_date", "VARCHAR"),
            ("fetched_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ],
        "mandi_price_history": [
            ("state", "VARCHAR"),
            ("district", "VARCHAR"),
            ("market", "VARCHAR"),
            ("commodity", "VARCHAR"),
            ("variety", "VARCHAR"),
            ("grade", "VARCHAR"),
            ("min_price", "VARCHAR"),
            ("max_price", "VARCHAR"),
            ("modal_price", "VARCHAR"),
            ("arrival_date", "VARCHAR"),
            ("arrival_dt", "DATE"),
            ("group_key", "VARCHAR"),
            ("row_key", "VARCHAR"),
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
        "orders": [
            ("tracking_code", "VARCHAR NOT NULL"),
            ("user_id", "INTEGER"),
            ("user_email", "VARCHAR"),
            ("user_name", "VARCHAR"),
            ("session_id", "VARCHAR"),
            ("is_guest", "BOOLEAN DEFAULT TRUE"),
            ("product_name", "VARCHAR NOT NULL"),
            ("product_id", "INTEGER"),
            ("quantity", "INTEGER DEFAULT 1"),
            ("unit_price", "FLOAT"),
            ("total", "FLOAT"),
            ("phone", "VARCHAR"),
            ("source", "VARCHAR DEFAULT 'shop'"),
            ("status", "VARCHAR DEFAULT 'Pending'"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
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
        # Mandi history: dedup one row per group per arrival_date, fast group lookups
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS mandi_history_row_key_uidx
            ON mandi_price_history(row_key)
            WHERE row_key IS NOT NULL;
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS mandi_history_group_dt_idx
            ON mandi_price_history(group_key, arrival_dt DESC);
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

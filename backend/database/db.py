# ============================================================
# backend/database/db.py
# KrashiMitra — Database Configuration
# ============================================================

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Text, Boolean, Float, text, UniqueConstraint, ForeignKey, Index
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

# Log host only — never the credentials (they were leaking into Render logs)
_safe_host = DATABASE_URL.split("@")[-1].split("?")[0] if "@" in DATABASE_URL else "local"
print(f"[DB] connecting to: ...@{_safe_host}")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

engine       = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,           # concurrent connections (default was 5 — too few for 14k-page crawl traffic)
    max_overflow=15,        # burst headroom
    pool_timeout=20,        # seconds to wait for a free slot before erroring (default 30)
    pool_recycle=300,       # recycle connections every 5 min — Neon's pooler can drop idle ones
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


# ── Read-only database detection ─────────────────────────────
# Neon flips a compute to read-only when the project trips a plan limit. Reads
# keep working perfectly, so the site looks healthy — /bhav, /mandi, articles
# all serve fine — while every write fails with SQLSTATE 25006. Handlers that
# turn this into a generic 500 make it indistinguishable from an application
# bug: the schema, sequences and triggers all inspect clean and the hunt goes
# nowhere. Name it explicitly so it is one glance in the logs instead.
_READ_ONLY_SQLSTATE = "25006"   # read_only_sql_transaction


def is_read_only_error(exc: BaseException) -> bool:
    """True when a write failed because the database refused writes.

    Checks the SQLSTATE off the wrapped DBAPI error (SQLAlchemy stores it on
    `.orig`), falling back to the message so a driver that does not surface
    pgcode still matches.
    """
    orig = getattr(exc, "orig", None) or exc
    if getattr(orig, "pgcode", None) == _READ_ONLY_SQLSTATE:
        return True
    return "read-only transaction" in str(exc).lower()


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


# ── DISTRICT → LAT/LON (district HQ) ─────────────────────────
# Weather is fetched by coordinate, NOT by city name. OWM's name
# geocoding (q=Gorakhpur,IN) is ambiguous across states and silently
# returned the wrong town for Gorakhpur (matched Haryana), Pratapgarh
# (Rajasthan), Kaushambi (Delhi NCR) and Kanpur Dehat (Ambedkar Nagar's
# Akbarpur) — and had no entry at all for Siddharthnagar.
# Coordinates always resolve, so every district gets real data.
UP_DISTRICT_COORDS = {
    "Agra":            (27.18, 78.02),
    "Firozabad":       (27.15, 78.42),
    "Mainpuri":        (27.23, 79.02),
    "Mathura":         (27.50, 77.68),
    "Aligarh":         (27.88, 78.08),
    "Etah":            (27.63, 78.67),
    "Hathras":         (27.60, 78.05),
    "Kasganj":         (27.82, 78.65),
    "Prayagraj":       (25.45, 81.85),
    "Fatehpur":        (25.93, 80.80),
    "Kaushambi":       (25.53, 81.38),   # Manjhanpur (HQ) — was matching Delhi NCR
    "Pratapgarh":      (25.90, 81.95),   # Bela (HQ) — was matching Rajasthan
    "Ayodhya":         (26.78, 82.13),
    "Ambedkar Nagar":  (26.42, 82.55),   # Akbarpur (HQ)
    "Amethi":          (26.15, 81.82),
    "Barabanki":       (26.93, 81.19),
    "Sultanpur":       (26.27, 82.07),
    "Azamgarh":        (26.06, 83.19),
    "Ballia":          (25.76, 84.15),
    "Mau":             (25.95, 83.55),
    "Bareilly":        (28.35, 79.42),
    "Badaun":          (28.05, 79.12),
    "Pilibhit":        (28.63, 79.80),
    "Shahjahanpur":    (27.88, 79.92),
    "Basti":           (26.80, 82.72),
    "Sant Kabir Nagar":(26.77, 83.07),   # Khalilabad (HQ)
    "Siddharthnagar":  (27.28, 83.09),   # Naugarh (HQ) — OWM has no city by this name
    "Banda":           (25.48, 80.33),
    "Chitrakoot":      (25.22, 80.92),   # Karwi (HQ)
    "Hamirpur":        (25.95, 80.15),
    "Mahoba":          (25.28, 79.87),
    "Bahraich":        (27.58, 81.60),
    "Balrampur":       (27.43, 82.18),
    "Gonda":           (27.13, 81.93),
    "Shravasti":       (27.72, 81.93),   # Bhinga (HQ)
    "Gorakhpur":       (26.76, 83.37),   # was matching Gorakhpur, Haryana
    "Deoria":          (26.50, 83.79),
    "Kushinagar":      (26.74, 83.92),
    "Maharajganj":     (27.13, 83.57),
    "Jhansi":          (25.43, 78.58),
    "Jalaun":          (25.98, 79.47),   # Orai (HQ)
    "Lalitpur":        (24.68, 78.42),
    "Kanpur Nagar":    (26.47, 80.35),
    "Kanpur Dehat":    (26.43, 79.98),   # Akbarpur/Mati (HQ) — was matching Ambedkar Nagar
    "Etawah":          (26.78, 79.02),
    "Farrukhabad":     (27.37, 79.63),   # Fatehgarh (HQ)
    "Auraiya":         (26.47, 79.52),
    "Kannauj":         (27.05, 79.92),
    "Lucknow":         (26.85, 80.92),
    "Hardoi":          (27.42, 80.12),
    "Lakhimpur Kheri": (27.95, 80.77),
    "Raebareli":       (26.22, 81.23),
    "Sitapur":         (27.57, 80.68),
    "Unnao":           (26.53, 80.50),
    "Meerut":          (28.98, 77.70),
    "Baghpat":         (28.95, 77.22),
    "Bulandshahr":     (28.40, 77.85),
    "Ghaziabad":       (28.67, 77.43),
    "Gautam Buddha Nagar": (28.58, 77.33),
    "Hapur":           (28.72, 77.78),
    "Mirzapur":        (25.15, 82.58),
    "Bhadohi":         (25.42, 82.57),
    "Sonbhadra":       (24.70, 83.07),   # Robertsganj (HQ)
    "Moradabad":       (28.83, 78.78),
    "Amroha":          (28.92, 78.47),
    "Bijnor":          (29.37, 78.13),
    "Rampur":          (28.82, 79.03),
    "Sambhal":         (28.58, 78.55),
    "Saharanpur":      (29.97, 77.55),
    "Muzaffarnagar":   (29.47, 77.68),
    "Shamli":          (29.45, 77.32),
    "Varanasi":        (25.33, 83.00),
    "Chandauli":       (25.27, 83.27),
    "Jaunpur":         (25.73, 82.68),
    "Ghazipur":        (25.58, 83.57),
}


# ── AUTH MODEL ───────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id                 = Column(Integer,  primary_key=True, index=True)
    # Mirrors `id` — kept as its own column (not just an alias) so other
    # tables/tools can key off "user_id" the same way they do on every other
    # table in this schema. Kept in sync automatically by a DB trigger, see
    # _ensure_postgres_columns() — never set this by hand.
    #
    # NULL until the account is verified: an unverified row is a signup
    # attempt that cannot log in, so it holds no account number. The trigger
    # fills it in the moment is_verified flips true.
    user_id            = Column(Integer,  unique=True, index=True)
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
    primary_crop       = Column(String,   nullable=True)  # NULL until the user actually picks a crop
    # avatar_url lives ONLY on user_profiles — the users mirror was dropped
    # (see the DROP COLUMN migration in _ensure_postgres_columns)
    # Blue-tick for Krashi Bazar sellers — toggled manually by admin in DB
    seller_verified    = Column(Boolean,  default=False, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


# ── OTHER MODELS ─────────────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    # Core
    id                   = Column(Integer,  primary_key=True, index=True)
    # Owned by the account: deleting the user deletes the profile (see _FOREIGN_KEYS)
    user_id              = Column(Integer,
                                  ForeignKey("users.id", ondelete="CASCADE",
                                             name="fk_user_profiles_user_id"),
                                  nullable=True, index=True)

    # Personal
    name                 = Column(String,   nullable=False)
    phone_number         = Column(String,   nullable=True)
    whatsapp_number      = Column(String,   nullable=True)
    dob                  = Column(Date,     nullable=True)   # live column is DATE; input "YYYY-MM-DD"
    gender               = Column(String,   nullable=True)
    education            = Column(String,   nullable=True)
    occupation           = Column(String,   nullable=True)   # व्यवसाय — who the customer is (farmer/trader/dealer/…)
    farming_experience   = Column(String,   nullable=True)
    family_size          = Column(Integer,  nullable=True)
    avatar_url           = Column(String,   nullable=True)

    # Location (manually entered address)
    state                = Column(String,   nullable=True)
    district             = Column(String,   nullable=True)
    tehsil               = Column(String,   nullable=True)
    village              = Column(String,   nullable=True)
    pin_code             = Column(String,   nullable=True)
    nearest_mandi        = Column(String,   nullable=True)

    # Auto-detected device location (browser Geolocation API → reverse-geocoded).
    # Kept SEPARATE from the address fields above: this is "where the phone is
    # right now", not "where the farm is registered".
    geo_lat              = Column(Float,    nullable=True)
    geo_lon              = Column(Float,    nullable=True)
    geo_location         = Column(String,   nullable=True)   # readable "जिला, राज्य"
    geo_updated_at       = Column(DateTime, nullable=True)   # last time the device shared it

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
    primary_crop         = Column(String,   nullable=True)  # NULL until the user actually picks a crop
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
    # A log worth keeping — deleting the account detaches the rows, not deletes
    # them. NULL also means "anonymous visitor", which this table always allowed.
    user_id    = Column(Integer,
                        ForeignKey("users.id", ondelete="SET NULL",
                                   name="fk_chat_history_user_id"),
                        nullable=True)
    crop       = Column(String,   nullable=True)
    district   = Column(String,   nullable=True)
    role       = Column(String,   nullable=False)
    message    = Column(Text,     nullable=False)
    language   = Column(String,   default="english")
    created_at = Column(DateTime, default=datetime.utcnow)


class MandiPrice(Base):
    """Latest snapshot — MERGED every fetch (upsert per market identity).
    Markets that haven't reported today keep their last known price until
    they report again (aged out after ~7 days unrefreshed)."""
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


class MandiLastSeen(Base):
    """The last price we ever saw for each (mandi × crop) — one row, forever.

    Exists so that trimming mandi_price_history is safe. Two things used to
    read the whole history table and would silently degrade as retention got
    shorter:

    1. **The page index** (routes/bhav._get_index) — every crop×state×district
       we have ever had data for, plus the date it last moved. That set decides
       which /bhav URLs exist and what <lastmod> the sitemap claims. Built from
       a trimmed history, districts that went quiet would drop out and URLs the
       sitemap advertises would start 404-ing — the exact regression fixed on
       18 Jul 2026.
    2. **The stale-district rescue** (routes/bhav._rows_for_district) — a
       district that stops reporting still shows its last known prices instead
       of an empty page.

    Neither needs *history*; both need only the latest row per combination.
    That is ~31k rows and, unlike history, it does not grow with time — only
    when a genuinely new mandi/crop/variety appears. So retention can now be
    set by what the 15-day chart needs, not by what SEO needs.

    Keyed by group_key (the same md5 the snapshot and history use), so a row
    here is shaped exactly like a snapshot row and renders through the same
    _row_to_dict path. Deliberately NO index=True on the primary key: that is
    what produced the duplicate id indexes on the older mandi tables.
    """
    __tablename__ = "mandi_last_seen"
    id           = Column(Integer,  primary_key=True)
    group_key    = Column(String,   nullable=False, unique=True)  # md5(state|district|market|commodity|variety|grade)
    state        = Column(String,   nullable=True)
    district     = Column(String,   nullable=True)
    market       = Column(String,   nullable=True)
    commodity    = Column(String,   nullable=False)
    variety      = Column(String,   nullable=True)
    grade        = Column(String,   nullable=True)
    min_price    = Column(String,   nullable=True)
    max_price    = Column(String,   nullable=True)
    modal_price  = Column(String,   nullable=True)
    arrival_date = Column(String,   nullable=True)   # original DD/MM/YYYY
    arrival_dt   = Column(Date,     nullable=True)   # parsed — "when this page last moved"
    updated_at   = Column(DateTime, default=datetime.utcnow)

    # One composite index serves both readers (index build + district rescue).
    __table_args__ = (
        Index("mandi_last_seen_csd_idx", "commodity", "state", "district"),
    )


class MandiPriceHistory(Base):
    """Append-only daily history, deduped by row_key. Trimmed after each
    fetch to the last MANDI_HISTORY_DAYS days (default 15) — powers prev-price
    deltas, sparklines and the trend chart, and nothing else. Anything that
    needs "has this page ever had data" reads MandiLastSeen instead."""
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


class MandiPriceMonthly(Base):
    """Multi-year monthly SUMMARY per (state, district, commodity) — the
    seasonality / "पिछले साल इसी समय" layer.

    Deliberately stores only the aggregate, never the raw daily rows. There
    are ~10k (district × crop) pairs nationwide; keeping their raw history
    would be ~150M rows, which is exactly why MandiPriceHistory is capped at
    MANDI_HISTORY_DAYS. One row per month per pair is ~60 rows/pair for 5
    years — the whole country fits in tens of MB.

    Built from data.gov's never-wiped archive resource by
    backend/services/mandi_season_service.py. Old months never change, so
    rows are written once and simply kept.
    """
    __tablename__ = "mandi_price_monthly"
    id           = Column(Integer,  primary_key=True, index=True)
    state        = Column(String,   nullable=True)
    district     = Column(String,   nullable=True)
    commodity    = Column(String,   nullable=False)
    ym           = Column(String,   nullable=False)          # "2025-03"
    year         = Column(Integer,  nullable=True)
    # Deliberately unindexed: every read is "WHERE slice_key = :k ORDER BY ym"
    # and the seasonal shape is pivoted in Python. On a table this narrow an
    # extra index costs about as much as the data it indexes.
    month        = Column(Integer,  nullable=True)
    median_modal = Column(Integer,  nullable=True)           # ₹/quintal
    min_modal    = Column(Integer,  nullable=True)
    max_modal    = Column(Integer,  nullable=True)
    n_rows       = Column(Integer,  nullable=True)           # daily rows behind the median
    slice_key    = Column(String,   nullable=True, index=True)  # md5(state|district|commodity)
    row_key      = Column(String,   nullable=True, unique=True, index=True)  # slice_key|ym — dedup
    built_at     = Column(DateTime, default=datetime.utcnow)


class MandiSeasonSlice(Base):
    """Work log for the seasonality backfill: one row per (state, district,
    commodity) pair we have been asked for.

    A /bhav page view enqueues its own pair and renders without the block;
    the scheduler drains the queue afterwards. That keeps data.gov calls out
    of the request path entirely — user traffic can never burn the API quota
    the daily price fetch depends on.
    """
    __tablename__ = "mandi_season_slices"
    id           = Column(Integer,  primary_key=True, index=True)
    slice_key    = Column(String,   nullable=False, unique=True, index=True)
    state        = Column(String,   nullable=True)
    district     = Column(String,   nullable=True)
    commodity    = Column(String,   nullable=True)
    status       = Column(String,   default="queued", index=True)  # queued|done|empty|error
    months       = Column(Integer,  default=0)      # months of summary stored
    rows_seen    = Column(Integer,  default=0)      # archive rows aggregated
    hits         = Column(Integer,  default=1)      # times a page asked for it
    attempts     = Column(Integer,  default=0)
    note         = Column(String,   nullable=True)
    requested_at = Column(DateTime, default=datetime.utcnow)
    built_at     = Column(DateTime, nullable=True)


# ── किसान कॉल सेंटर सवाल-जवाब (KCC) ──────────────────────────

class KccQA(Base):
    """Curated question/answer pairs from the Government of India's Kisan Call
    Centre transcripts (data.gov resource cef25fe2-…, ~48M rows).

    ONLY vetted rows land here — see backend/services/kcc_service.py. The
    source is genuinely messy: ~50% of it is throwaway weather chatter, the
    questions are staff-typed English/Hinglish shorthand, and about 2% of
    answers give advice for a DIFFERENT crop than the one the row is filed
    under (paddy answers under wheat, etc.). Since these answers carry
    pesticide names and doses, publishing them unfiltered could put wrong-crop
    spray advice in front of a farmer. The service therefore keeps only
    answers that name their own crop in Hindi, and this table is the
    already-safe subset.
    """
    __tablename__ = "kcc_qa"
    id         = Column(Integer,  primary_key=True, index=True)
    crop_key   = Column(String,   nullable=False, index=True)   # our slug: "wheat"
    crop       = Column(String,   nullable=True)                # KCC's own label
    topic      = Column(String,   nullable=True)                # normalised QueryType
    question   = Column(Text,     nullable=True)                # original (English/Hinglish)
    answer     = Column(Text,     nullable=False)               # Hindi, crop-verified
    district   = Column(String,   nullable=True)
    state      = Column(String,   nullable=True)
    year       = Column(Integer,  nullable=True)
    month      = Column(Integer,  nullable=True)
    ans_key    = Column(String,   nullable=True, unique=True, index=True)  # dedup hash
    built_at   = Column(DateTime, default=datetime.utcnow)


class KccCropBuild(Base):
    """Per-crop build log for the KCC harvest, so a crop with no usable rows
    is not re-fetched on every scheduler pass."""
    __tablename__ = "kcc_crop_builds"
    id         = Column(Integer,  primary_key=True, index=True)
    crop_key   = Column(String,   nullable=False, unique=True, index=True)
    status     = Column(String,   default="queued", index=True)  # queued|done|empty|error
    n_qa       = Column(Integer,  default=0)      # rows kept
    n_seen     = Column(Integer,  default=0)      # rows examined
    attempts   = Column(Integer,  default=0)
    note       = Column(String,   nullable=True)
    built_at   = Column(DateTime, nullable=True)


# ── CROP CALENDAR (मेरी फसल) ─────────────────────────────────

class UserCrop(Base):
    """A crop a farmer is growing this season — crop_key references
    backend/data/crop_stages.json; the timeline itself is computed
    from sowing_date, never stored."""
    __tablename__ = "crop_calendar"

    id          = Column(Integer,  primary_key=True, index=True)
    user_id     = Column(Integer,
                         ForeignKey("users.id", ondelete="CASCADE",
                                    name="fk_crop_calendar_user_id"),
                         nullable=False, index=True)             # users.id
    crop_key    = Column(String,   nullable=False)               # "wheat" | "paddy" | ...
    sowing_date = Column(Date,     nullable=False)               # day-0 (sowing/transplanting)
    area        = Column(String,   nullable=True)                # free text, e.g. "2"
    area_unit   = Column(String,   default="acres")
    status      = Column(String,   default="active", index=True) # active | done
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow)


# ── PRICE ALERTS (Web Push) ──────────────────────────────────

class PushSubscription(Base):
    """One browser/device Web Push endpoint. A row is the *device*; the account
    it belongs to is user_id, which is set the moment a signed-in visitor
    subscribes (and back-filled by /auth/claim-guest for endpoints created
    before the login gate existed). A user with three phones has three rows —
    that is how an alert reaches every device they own."""
    __tablename__ = "push_subscriptions"

    id         = Column(Integer,  primary_key=True, index=True)
    endpoint   = Column(Text,     nullable=False, unique=True, index=True)
    p256dh     = Column(String,   nullable=False)              # client public key
    auth       = Column(String,   nullable=False)              # client auth secret
    # The browser endpoint outlives the account — deleting the user unlinks the
    # device (back to anonymous) rather than throwing the subscription away.
    user_id    = Column(Integer,
                        ForeignKey("users.id", ondelete="SET NULL",
                                   name="fk_push_subscriptions_user_id"),
                        nullable=True, index=True)             # users.id, when logged in
    user_agent = Column(String,   nullable=True)
    active     = Column(Boolean,  default=True, index=True)    # false once push service 404/410s
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class MandiAlert(Base):
    """A "notify me about this mandi bhav" subscription.

    Turning the bell on now requires a login, so a new row belongs to an
    *account* (user_id) and is delivered to every active device that account
    owns — a farmer who clears his browser or buys a new phone keeps his alert.
    subscription_id records the device the alert was created from; it stays the
    delivery target only for legacy rows created before the gate, which have
    user_id NULL and are still honoured so nobody silently loses an alert they
    opted into.

    Evaluated after each mandi fetch run; last_notified_on + last_price dedupe
    so the same price is never pushed twice."""
    __tablename__ = "mandi_alerts"

    id               = Column(Integer,  primary_key=True, index=True)
    subscription_id  = Column(Integer,
                              ForeignKey("push_subscriptions.id", ondelete="CASCADE",
                                         name="fk_mandi_alerts_subscription_id"),
                              nullable=False, index=True)  # push_subscriptions.id
    # CASCADE, not SET NULL: a NULL user_id means "legacy device-only alert" and
    # keeps firing forever, so a deleted account must take its alerts with it.
    user_id          = Column(Integer,
                              ForeignKey("users.id", ondelete="CASCADE",
                                         name="fk_mandi_alerts_user_id"),
                              nullable=True,  index=True)  # users.id; NULL = legacy device-only alert
    # Farmer's display name, copied from user_profiles.name so the raw table is
    # readable in a DB GUI without joining. A convenience copy, NOT the source of
    # truth — it is rewritten on every subscribe/claim, but a profile rename in
    # between leaves it stale. For a guaranteed-current name use GET /admin/alerts,
    # which joins user_profiles live.
    user_name        = Column(String,   nullable=True)
    commodity        = Column(String,   nullable=False, index=True)
    state            = Column(String,   nullable=True,  index=True)
    district         = Column(String,   nullable=True,  index=True)
    active           = Column(Boolean,  default=True, index=True)
    last_notified_on = Column(Date,     nullable=True)   # dedupe key: one push per new price
    last_price       = Column(String,   nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("subscription_id", "commodity", "state", "district",
                         name="uq_mandi_alert_target"),
    )


# ── DATA SYNC LOG ────────────────────────────────────────────

class SyncLog(Base):
    """
    One row per data-sync run (mandi / weather). An audit trail of *when*
    external data was last fetched, whether it succeeded, and how much came
    in — surfaced in the admin panel so a silently-stale feed is obvious.
    """
    __tablename__ = "sync_log"

    id          = Column(Integer,  primary_key=True, index=True)
    source      = Column(String,   nullable=False, index=True)   # "mandi" | "weather"
    status      = Column(String,   nullable=False)               # "success" | "partial" | "failed"
    rows        = Column(Integer,  default=0)                     # rows fetched / districts updated
    detail      = Column(String,   nullable=True)                # short human-readable summary
    duration_ms = Column(Integer,  nullable=True)                # wall-clock run time
    started_at  = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, default=datetime.utcnow, index=True)


# ── KRASHI BAZAR (social crop marketplace) ──────────────────

class BazarPost(Base):
    """A sell/buy listing in the Krashi Bazar feed (image/video optional)."""
    __tablename__ = "bazar_posts"

    id             = Column(Integer,  primary_key=True, index=True)
    user_id        = Column(Integer,
                            ForeignKey("users.id", ondelete="CASCADE",
                                       name="fk_bazar_posts_user_id"),
                            nullable=False, index=True)             # users.id
    post_type      = Column(String,   default="sell", nullable=False)  # "sell" | "buy"
    crop           = Column(String,   nullable=True, index=True)
    text           = Column(Text,     nullable=True)
    media_url      = Column(String,   nullable=True)   # /uploads/bazar/<file>
    media_type     = Column(String,   nullable=True)   # "image" | "video"
    price          = Column(Float,    nullable=True)   # asking price
    old_price      = Column(Float,    nullable=True)   # struck-through previous price
    quantity       = Column(Float,    nullable=True)
    unit           = Column(String,   default="क्विंटल")
    location       = Column(String,   nullable=True)   # denormalized "village, district"
    # ── Structured place/crop, added 2026-07-28 so /bhav can serve a district
    # slice of this feed at /bhav/{crop}/{state}/{district}/kharidar.
    # `location` cannot do that job: it is one free-text "village, district"
    # string, so filtering on it means a substring match that (a) mis-hits when a
    # village name contains a district name and (b) merges the four district
    # names that exist in two states each — bilaspur, hamirpur, pratapgarh,
    # balrampur — the exact collision the /bhav URL scheme was restructured to
    # fix. crop_slug is the /bhav slug ("wheat"), not the typed `crop` ("गेहूं"),
    # so the join is exact instead of an ilike on whatever the farmer wrote.
    state          = Column(String,   nullable=True, index=True)
    district       = Column(String,   nullable=True, index=True)
    crop_slug      = Column(String,   nullable=True, index=True)
    source         = Column(String,   nullable=True)   # "bazar" | "bhav" — which surface posted it
    status         = Column(String,   default="active", index=True)  # active | sold | closed
    likes_count    = Column(Integer,  default=0)
    comments_count = Column(Integer,  default=0)
    created_at     = Column(DateTime, default=datetime.utcnow, index=True)


class BazarLike(Base):
    __tablename__ = "bazar_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="bazar_like_uidx"),)

    id         = Column(Integer,  primary_key=True, index=True)
    post_id    = Column(Integer,
                        ForeignKey("bazar_posts.id", ondelete="CASCADE",
                                   name="fk_bazar_likes_post_id"),
                        nullable=False, index=True)
    user_id    = Column(Integer,
                        ForeignKey("users.id", ondelete="CASCADE",
                                   name="fk_bazar_likes_user_id"),
                        nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BazarComment(Base):
    """Comments and price offers ('kind' distinguishes them) on a post."""
    __tablename__ = "bazar_comments"

    id           = Column(Integer,  primary_key=True, index=True)
    post_id      = Column(Integer,
                          ForeignKey("bazar_posts.id", ondelete="CASCADE",
                                     name="fk_bazar_comments_post_id"),
                          nullable=False, index=True)
    user_id      = Column(Integer,
                          ForeignKey("users.id", ondelete="CASCADE",
                                     name="fk_bazar_comments_user_id"),
                          nullable=False, index=True)
    kind         = Column(String,   default="comment")  # "comment" | "offer"
    text         = Column(Text,     nullable=True)
    offer_amount = Column(Float,    nullable=True)      # set when kind == "offer"
    created_at   = Column(DateTime, default=datetime.utcnow)


class BazarFollow(Base):
    __tablename__ = "bazar_follows"
    __table_args__ = (UniqueConstraint("follower_id", "following_id", name="bazar_follow_uidx"),)

    id           = Column(Integer,  primary_key=True, index=True)
    follower_id  = Column(Integer,
                          ForeignKey("users.id", ondelete="CASCADE",
                                     name="fk_bazar_follows_follower_id"),
                          nullable=False, index=True)
    following_id = Column(Integer,
                          ForeignKey("users.id", ondelete="CASCADE",
                                     name="fk_bazar_follows_following_id"),
                          nullable=False, index=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"extend_existing": True}

    id            = Column(Integer,  primary_key=True, autoincrement=True)
    tracking_code = Column(String,   nullable=False, unique=True, index=True)
    # SET NULL, never CASCADE — a real transaction stays in the books even if the
    # account goes away; user_email/user_name below keep the row readable.
    user_id       = Column(Integer,
                           ForeignKey("users.id", ondelete="SET NULL",
                                      name="fk_orders_user_id"),
                           nullable=True, index=True)   # links to users.id (NULL for guests)
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
    source        = Column(String,   default="shop")   # "shop" / "mandi" / "prebook"
    status        = Column(String,   default="Pending")  # Pending / Booked / Quoted / Purchased / Delivered
    created_at    = Column(DateTime, default=datetime.utcnow)

    # ── Pre-book (RFQ) fields ─────────────────────────────────
    # Farmer pre-books → owner sources a local dealer → sends a quote back (seen via the 🔔 bell)
    pincode       = Column(String,   nullable=True)   # farmer delivery pincode (demand map + dealer match)
    customer_name = Column(String,   nullable=True)   # name from the pre-book form
    quote_total   = Column(Float,    nullable=True)   # full quoted price incl. delivery + our commission
    delivery_info = Column(String,   nullable=True)   # dealer + delivery details sent to the farmer
    dealer_name   = Column(String,   nullable=True)   # local dealer fulfilling the order
    quote_note    = Column(String,   nullable=True)   # optional free-text note in the quote
    quoted_at     = Column(DateTime, nullable=True)   # when the quote was sent (drives the 🔔 badge)


# ── CROP APPEAL (बेचना/खरीदना है — intent captured on /bhav) ──

class CropAppeal(Base):
    """A "मुझे यह फसल बेचनी/खरीदनी है" appeal raised from a /bhav district page.

    The price pages answer *what is the rate* and then dead-end. This row is the
    farmer's (or trader's) next sentence — "I have 40 quintals of wheat in Hardoi,
    who will buy it?" — captured at the exact moment the intent exists.

    Login-gated (decided 2026-07-28; the first cut was open). An appeal is only
    worth acting on if we can get back to whoever raised it, and the reply lands
    in KrashiBook, which needs an account to exist. So every new row carries a
    user_id; routes/appeal.py enforces it with a 401, not just the UI.

    name + description are the required pair. Everything else is context copied
    off the page the appeal was raised from (crop, state, district), so a row is
    actionable on its own without reconstructing where it came from.

    phone is optional on purpose: making it mandatory would cost more appeals
    than the missing numbers are worth at this stage. For a signed-in farmer the
    client pre-fills it from his profile, so the common case still carries one.
    """
    __tablename__ = "crop_appeals"

    id          = Column(Integer,  primary_key=True, index=True)
    kind        = Column(String,   nullable=False, index=True)   # "sell" (बेचना है) | "buy" (खरीदना है)
    # The required pair.
    name        = Column(String,   nullable=False)
    description = Column(String,   nullable=False)               # pre-written in the panel, farmer edits
    phone       = Column(String,   nullable=True)                # optional; how the buyer/seller is reached
    # SET NULL, not CASCADE — same reasoning as Order: a lead we may have already
    # acted on stays in the books even if the account is deleted. `name` and
    # `phone` are stored on the row, so it stays readable without the account.
    user_id     = Column(Integer,
                         ForeignKey("users.id", ondelete="SET NULL",
                                    name="fk_crop_appeals_user_id"),
                         nullable=True, index=True)              # NULL only after the account is deleted
    # Context, copied from the page. Indexed on the two axes the buyer/dealer
    # directory will query by: "who wants to sell wheat in Hardoi".
    commodity   = Column(String,   nullable=False, index=True)
    state       = Column(String,   nullable=True)
    district    = Column(String,   nullable=True,  index=True)
    quantity    = Column(String,   nullable=True)                # free text ("40 क्विंटल") — farmers don't think in one unit
    page_url    = Column(String,   nullable=True)                # exact page the appeal came from
    status      = Column(String,   default="new", index=True)    # new / contacted / matched / closed
    created_at  = Column(DateTime, default=datetime.utcnow, index=True)


class AdminTask(Base):
    """One line of the owner's 31-Aug-2026 checklist (admin panel → Farmer Locator).

    Two kinds of row live here, told apart by `custom`:

    * **seeded** — the curated checklist in `data/deadline_checklist.json`. The
      JSON owns the wording, section, order and notes; this table owns nothing
      but `done`/`done_at`. So a row exists only once the task has been touched,
      and rewording a task in the JSON can never lose a tick, because the tick
      is keyed on the stable `slug`, not on the text.
    * **custom** — tasks the owner adds from the panel. These have no JSON
      counterpart, so the row carries its own title/section and is the only
      copy; deleting it is the only way it disappears.

    That asymmetry is the whole design: the file is the plan, the table is the
    progress, and neither can clobber the other.

    Writes here are the first thing to fail if the Neon compute flips read-only
    — see is_read_only_error(); routes/admin.py surfaces that as its own message
    rather than a generic 500, because "my checkbox won't tick" is otherwise an
    impossible symptom to diagnose.
    """
    __tablename__ = "admin_tasks"

    id         = Column(Integer,  primary_key=True, index=True)
    slug       = Column(String,   nullable=False, unique=True, index=True)  # JSON task id, or "mine-<n>" for custom
    done       = Column(Boolean,  default=False, nullable=False)
    done_at    = Column(DateTime, nullable=True)
    # Only meaningful for custom rows — seeded rows read these from the JSON.
    custom     = Column(Boolean,  default=False, nullable=False, index=True)
    title      = Column(String,   nullable=True)
    section    = Column(String,   nullable=True)   # section key the task belongs to
    note       = Column(String,   nullable=True)
    sort       = Column(Integer,  default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── DB Helpers ───────────────────────────────────────────────

_TABLE_RENAMES = [
    ("user_crops", "crop_calendar"),
]


def _ensure_table_renames():
    """Pick up table renames on an existing Neon DB without losing data.

    Must run before create_all(): if the old name still exists and the new
    one doesn't, RENAME *is* the migration — it carries over every row,
    index and constraint. No-op on every startup after the first, and a
    no-op on a brand-new DB (create_all() just creates the new name).
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for old, new in _TABLE_RENAMES:
            old_exists = conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{old}"}).scalar()
            new_exists = conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{new}"}).scalar()
            if old_exists and not new_exists:
                conn.execute(text(f'ALTER TABLE "{old}" RENAME TO "{new}"'))
                print(f"🔤 renamed table {old} → {new}")
            elif old_exists and new_exists:
                # A reload can race this: create_all() sees the model's new
                # __tablename__ and creates it fresh before this function ever
                # runs, leaving the old table stranded alongside it. Only safe
                # to clean up automatically when the leftover is empty — a
                # non-empty one needs a human to decide how to merge it.
                old_count = conn.execute(text(f'SELECT count(*) FROM "{old}"')).scalar()
                if old_count == 0:
                    conn.execute(text(f'DROP TABLE "{old}"'))
                    print(f"🧹 dropped empty leftover table {old} (already renamed to {new})")
                else:
                    print(f"⚠️  both {old} and {new} exist and {old} has {old_count} row(s) — needs manual merge")


def _ensure_postgres_columns():
    """Add columns that older Neon tables may be missing."""
    if engine.dialect.name != "postgresql":
        return

    schema_patches = {
        "users": [
            ("user_id", "INTEGER"),
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
            # avatar_url intentionally omitted — profile pic lives only on
            # user_profiles now; the old users.avatar_url column is dropped below
            ("seller_verified", "BOOLEAN DEFAULT FALSE"),
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
            ("occupation",           "VARCHAR"),
            ("farming_experience",   "VARCHAR"),
            ("family_size",          "INTEGER"),
            ("avatar_url",           "VARCHAR"),
            # Location
            ("state",                "VARCHAR"),
            ("district",             "VARCHAR"),
            ("tehsil",               "VARCHAR"),
            ("village",              "VARCHAR"),
            ("pin_code",             "VARCHAR"),
            ("nearest_mandi",        "VARCHAR"),
            # Auto-detected device location (see UserProfile model)
            ("geo_lat",              "FLOAT"),
            ("geo_lon",              "FLOAT"),
            ("geo_location",         "VARCHAR"),
            ("geo_updated_at",       "TIMESTAMP"),
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
        "crop_calendar": [
            ("user_id", "INTEGER"),
            ("crop_key", "VARCHAR"),
            ("sowing_date", "DATE"),
            ("area", "VARCHAR"),
            ("area_unit", "VARCHAR DEFAULT 'acres'"),
            ("status", "VARCHAR DEFAULT 'active'"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ],
        "sync_log": [
            ("source", "VARCHAR"),
            ("status", "VARCHAR"),
            ("rows", "INTEGER DEFAULT 0"),
            ("detail", "VARCHAR"),
            ("duration_ms", "INTEGER"),
            ("started_at", "TIMESTAMP"),
            ("finished_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
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
            ("pincode", "VARCHAR"),
            ("customer_name", "VARCHAR"),
            ("quote_total", "FLOAT"),
            ("delivery_info", "VARCHAR"),
            ("dealer_name", "VARCHAR"),
            ("quote_note", "VARCHAR"),
            ("quoted_at", "TIMESTAMP"),
        ],
        # 🔔 mandi alerts moved from device-scoped to account-scoped when the
        # login gate went in — existing rows keep user_id NULL and are still
        # delivered to their original device.
        "push_subscriptions": [
            ("user_id", "INTEGER"),
        ],
        "mandi_alerts": [
            ("user_id", "INTEGER"),
            ("user_name", "VARCHAR"),
        ],
        # Structured place/crop so /bhav can serve a district slice of the Bazar
        # feed. Nullable on purpose: every row written before 2026-07-28 has only
        # the free-text `location`, and backfilling it would mean guessing which
        # comma-separated part was the district.
        "bazar_posts": [
            ("state", "VARCHAR"),
            ("district", "VARCHAR"),
            ("crop_slug", "VARCHAR"),
            ("source", "VARCHAR"),
        ],
    }

    with engine.begin() as conn:
        for table_name, columns in schema_patches.items():
            for column_name, column_type in columns:
                conn.execute(text(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD COLUMN IF NOT EXISTS "{column_name}" {column_type}'
                ))

        # ADD COLUMN brings no index with it, and the kharidar page filters on
        # all three at once on a server-rendered request — one composite index
        # rather than three single-column ones, in the order the query narrows.
        conn.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_bazar_posts_place '
            'ON bazar_posts (crop_slug, state, district, status)'
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
        # ── bhav page performance: covering indexes for the two heaviest queries ──
        # _rows_for() filters by commodity+state+district with lower(); this
        # composite expression index turns a full table scan into an index lookup.
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS mandi_prices_csd_lower_idx
            ON mandi_prices(lower(commodity), lower(state), lower(district));
        """))
        # _get_index() does GROUP BY (commodity, state, district) + max(arrival_dt)
        # on the history table. Without a covering index, Postgres has to scan the
        # entire 30-day table (hundreds of thousands of rows) on cold start.
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS mandi_history_csd_dt_idx
            ON mandi_price_history(commodity, state, district, arrival_dt DESC);
        """))

        # 🔔 alerts are now looked up by account, not just by device — both on
        # subscribe (find this user's existing alert for the crop) and on the
        # push pass (fan an alert out to every device the account owns).
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS mandi_alerts_user_idx
            ON mandi_alerts(user_id) WHERE user_id IS NOT NULL;
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS push_subs_user_active_idx
            ON push_subscriptions(user_id) WHERE user_id IS NOT NULL;
        """))

        # ── users.user_id mirrors users.id, but only once verified ───
        # Requested as a standalone column (not just `id` reused) so every
        # table in this schema can be keyed off "user_id" consistently. Kept
        # in sync automatically — no manual backfill/re-run ever needed.
        #
        # An unverified row is a signup attempt, not an account: it cannot log
        # in (auth.py rejects is_verified = false), so it gets no account
        # number and user_id stays NULL until verification flips it true.
        # That is why UPDATE OF lists is_verified as well as id — verification
        # lands long after the INSERT, and the number has to appear then.
        # Any number of unverified rows can coexist under users_user_id_uidx:
        # Postgres treats NULLs as distinct in a unique index.
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION sync_users_user_id() RETURNS trigger AS $$
            BEGIN
                NEW.user_id := CASE WHEN NEW.is_verified THEN NEW.id ELSE NULL END;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(text("DROP TRIGGER IF EXISTS trg_sync_users_user_id ON users;"))
        conn.execute(text("""
            CREATE TRIGGER trg_sync_users_user_id
                BEFORE INSERT OR UPDATE OF id, is_verified ON users
                FOR EACH ROW
                EXECUTE FUNCTION sync_users_user_id();
        """))
        # Re-align rows that predate this rule, plus any row whose is_verified
        # was flipped by hand in the DB GUI while the trigger still ignored it.
        conn.execute(text("""
            UPDATE users
               SET user_id = CASE WHEN is_verified THEN id ELSE NULL END
             WHERE user_id IS DISTINCT FROM CASE WHEN is_verified THEN id ELSE NULL END;
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_uidx ON users(user_id);
        """))

        # ── users ↔ user_profiles 1:1 guarantee ──────────────────
        # The app-level _ensure_profile() (auth.py) only runs on the OTP-verify
        # and Google-login flows. Flipping is_verified = TRUE by hand in the DB
        # GUI — or any future code path — bypassed it, leaving verified users
        # with no user_profiles row. This DB trigger closes that gap: a profile
        # is created automatically no matter HOW is_verified becomes true.
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION ensure_user_profile() RETURNS trigger AS $$
            BEGIN
                INSERT INTO user_profiles (user_id, name, language)
                SELECT NEW.id, NEW.name, COALESCE(NEW.preferred_language, 'hindi')
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_profiles WHERE user_id = NEW.id
                );
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        conn.execute(text("DROP TRIGGER IF EXISTS trg_ensure_user_profile ON users;"))
        conn.execute(text("""
            CREATE TRIGGER trg_ensure_user_profile
                AFTER INSERT OR UPDATE OF is_verified ON users
                FOR EACH ROW
                WHEN (NEW.is_verified)
                EXECUTE FUNCTION ensure_user_profile();
        """))
        # One-time backfill for accounts that were verified before this trigger
        # existed (e.g. users 5, 6, 7, 13 verified manually in the GUI).
        conn.execute(text("""
            INSERT INTO user_profiles (user_id, name, language)
            SELECT u.id, u.name, COALESCE(u.preferred_language, 'hindi')
            FROM users u
            LEFT JOIN user_profiles p ON p.user_id = u.id
            WHERE u.is_verified AND p.id IS NULL;
        """))

        # ── Profile pic lives ONLY on user_profiles ──────────────
        # users.avatar_url was a duplicated mirror (double storage). Preserve
        # any avatar that somehow exists only on users, then drop the column.
        # Self-guarding: the branch only runs while the column still exists, so
        # it's a safe no-op on every startup after the first.
        conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'avatar_url'
                ) THEN
                    UPDATE user_profiles p
                    SET avatar_url = u.avatar_url
                    FROM users u
                    WHERE p.user_id = u.id
                      AND (p.avatar_url IS NULL OR p.avatar_url = '')
                      AND u.avatar_url IS NOT NULL AND u.avatar_url <> '';

                    ALTER TABLE users DROP COLUMN avatar_url;
                END IF;
            END $$;
        """))


def _ensure_users_column_order():
    """Physically move users.user_id to sit right after users.id.

    Postgres has no ALTER TABLE ... position-column form — the only way to
    actually reorder a column on disk is to rebuild the table: drop every FK
    pointing at users, recreate users with the new column order, copy the
    rows back, reinstall its own indexes/triggers, then let
    _ensure_foreign_keys() (called right after this in init_db()) reinstall
    the FKs it already knows how to build.

    Self-guarding: skipped once user_id is already column 2, so this is a
    no-op on every startup after the first — and a no-op on a brand-new DB,
    where create_all() already emits the model's declared order.
    """
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        pos = conn.execute(text("""
            SELECT ordinal_position FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'user_id'
        """)).scalar()
        if pos is None or pos == 2:
            return  # column not created yet, or already in place

        fks = conn.execute(text("""
            SELECT conname, conrelid::regclass::text
            FROM pg_constraint
            WHERE confrelid = 'users'::regclass AND contype = 'f'
        """)).fetchall()
        for conname, child in fks:
            conn.execute(text(f'ALTER TABLE "{child}" DROP CONSTRAINT "{conname}"'))

        conn.execute(text("ALTER TABLE users RENAME TO users_old"))
        conn.execute(text("""
            CREATE TABLE users (
                id                  INTEGER PRIMARY KEY DEFAULT nextval('users_id_seq'),
                user_id             INTEGER,
                name                VARCHAR NOT NULL,
                email               VARCHAR NOT NULL,
                hashed_password     VARCHAR NOT NULL,
                is_verified         BOOLEAN NOT NULL,
                otp                 VARCHAR,
                otp_expiry          TIMESTAMP,
                preferred_language  VARCHAR,
                auth_provider       VARCHAR,
                google_id           VARCHAR,
                village             VARCHAR,
                district            VARCHAR,
                primary_crop        VARCHAR,
                seller_verified     BOOLEAN,
                created_at          TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO users (id, user_id, name, email, hashed_password, is_verified,
                                otp, otp_expiry, preferred_language, auth_provider,
                                google_id, village, district, primary_crop,
                                seller_verified, created_at)
            SELECT id, user_id, name, email, hashed_password, is_verified,
                   otp, otp_expiry, preferred_language, auth_provider,
                   google_id, village, district, primary_crop,
                   seller_verified, created_at
            FROM users_old
        """))
        # Reassign the sequence to the new id column BEFORE dropping
        # users_old — it's still OWNED BY the old column, and an owned
        # sequence is dropped along with its owner, which would otherwise
        # rip out the new table's DEFAULT too.
        conn.execute(text("ALTER SEQUENCE users_id_seq OWNED BY users.id"))
        # users_old still holds the OLD copies of these index names (a table
        # RENAME does not rename its indexes) — drop it so the names are
        # free for the new table to reclaim.
        conn.execute(text("DROP TABLE users_old"))
        # users_old also held the OLD "users_pkey" constraint name, so
        # CREATE TABLE above had to auto-suffix the new one (e.g.
        # "users_pkey1") — now that the name is free, reclaim it.
        conn.execute(text("""
            DO $$
            DECLARE pk text;
            BEGIN
                SELECT conname INTO pk FROM pg_constraint
                WHERE conrelid = 'users'::regclass AND contype = 'p';
                IF pk <> 'users_pkey' THEN
                    EXECUTE format('ALTER TABLE users RENAME CONSTRAINT %I TO users_pkey', pk);
                END IF;
            END $$;
        """))
        conn.execute(text("CREATE INDEX ix_users_google_id ON users(google_id)"))
        conn.execute(text("CREATE INDEX ix_users_id ON users(id)"))
        conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users(email)"))
        conn.execute(text("CREATE UNIQUE INDEX users_user_id_uidx ON users(user_id)"))
        conn.execute(text("""
            CREATE TRIGGER trg_sync_users_user_id
                BEFORE INSERT OR UPDATE OF id ON users
                FOR EACH ROW
                EXECUTE FUNCTION sync_users_user_id()
        """))
        conn.execute(text("""
            CREATE TRIGGER trg_ensure_user_profile
                AFTER INSERT OR UPDATE OF is_verified ON users
                FOR EACH ROW
                WHEN (NEW.is_verified)
                EXECUTE FUNCTION ensure_user_profile()
        """))
        print("🔀 rebuilt users table with user_id as column 2")


# ── REFERENTIAL INTEGRITY ────────────────────────────────────
# (child_table, child_column, parent_table, parent_column, ON DELETE rule)
#
# Every one of these columns is documented as "users.id" / "push_subscriptions.id"
# in the models above, but until now not one of them was actually declared as a
# foreign key — the schema had zero. Postgres therefore never checked that the id
# resolved, and never cleaned up when the parent row went away, so deleting an
# account by hand in the Neon GUI left its profile, crops, alerts, cart and posts
# behind pointing at an id that no longer exists. (That is how user_profiles ended
# up with a "Gate Probe" row for a users.id 2 that isn't there.) Worse, the debris
# is *claimable*: reset or roll back the users id sequence and the next signup
# silently inherits the previous owner's profile, alerts and order history.
#
# CASCADE where the row is meaningless without its owner; SET NULL where the row
# is a record worth keeping (orders, chat log) or a device that outlives the
# account (push endpoint). Deliberately NOT deleting orders — a real transaction
# stays in the books, just detached; user_email/user_name on the row keep it
# readable.
#
# Order matters: a parent is cleaned before the children that hang off it, so a
# bazar_post removed with its owner takes its likes and comments with it.
_FOREIGN_KEYS = [
    ("user_profiles",      "user_id",         "users",              "id", "CASCADE"),
    ("crop_calendar",      "user_id",         "users",              "id", "CASCADE"),
    ("carts",              "user_id",         "users",              "id", "CASCADE"),
    ("chat_history",       "user_id",         "users",              "id", "SET NULL"),
    ("orders",             "user_id",         "users",              "id", "SET NULL"),
    ("push_subscriptions", "user_id",         "users",              "id", "SET NULL"),
    ("mandi_alerts",       "user_id",         "users",              "id", "CASCADE"),
    ("mandi_alerts",       "subscription_id", "push_subscriptions", "id", "CASCADE"),
    ("bazar_posts",        "user_id",         "users",              "id", "CASCADE"),
    ("bazar_likes",        "user_id",         "users",              "id", "CASCADE"),
    ("bazar_likes",        "post_id",         "bazar_posts",        "id", "CASCADE"),
    ("bazar_comments",     "user_id",         "users",              "id", "CASCADE"),
    ("bazar_comments",     "post_id",         "bazar_posts",        "id", "CASCADE"),
    ("bazar_follows",      "follower_id",     "users",              "id", "CASCADE"),
    ("bazar_follows",      "following_id",    "users",              "id", "CASCADE"),
]


def _has_column(conn, table: str, column: str) -> bool:
    return bool(conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
    """), {"t": table, "c": column}).scalar())


def _ensure_foreign_keys():
    """Install the FKs in _FOREIGN_KEYS, sweeping pre-existing orphans first.

    ADD CONSTRAINT refuses to run while a single violating row exists, so each
    pass applies its own ON DELETE rule by hand to rows that are already
    orphaned — exactly what Postgres would have done had the constraint been
    there — and only then installs it.

    Idempotent and self-guarding: missing tables/columns are skipped, so are
    constraints already present, which makes this a no-op on every startup after
    the first. Each FK runs in its own transaction so one unexpected failure
    can't roll back the others.
    """
    if engine.dialect.name != "postgresql":
        return

    for child, col, parent, pcol, on_delete in _FOREIGN_KEYS:
        name = f"fk_{child}_{col}"
        try:
            with engine.begin() as conn:
                if not (_has_column(conn, child, col) and _has_column(conn, parent, pcol)):
                    continue
                # Matched by (child column → parent table), not by name: on a
                # brand-new DB create_all() has already emitted the constraint
                # from the model, and Postgres would happily accept a second,
                # identical one under a different name.
                exists = conn.execute(text("""
                    SELECT 1
                    FROM pg_constraint c
                    JOIN pg_attribute a
                      ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                    WHERE c.contype  = 'f'
                      AND c.conrelid  = to_regclass('public.' || :child)
                      AND c.confrelid = to_regclass('public.' || :parent)
                      AND array_length(c.conkey, 1) = 1
                      AND a.attname   = :col
                """), {"child": child, "parent": parent, "col": col}).scalar()
                if exists:
                    continue

                orphan_filter = (
                    f'WHERE c."{col}" IS NOT NULL '
                    f'AND NOT EXISTS (SELECT 1 FROM "{parent}" p WHERE p."{pcol}" = c."{col}")'
                )
                if on_delete == "CASCADE":
                    swept = conn.execute(text(
                        f'DELETE FROM "{child}" AS c {orphan_filter}'
                    )).rowcount
                    action = "deleted"
                else:
                    swept = conn.execute(text(
                        f'UPDATE "{child}" AS c SET "{col}" = NULL {orphan_filter}'
                    )).rowcount
                    action = "detached"
                if swept:
                    print(f"🧹 {child}.{col}: {action} {swept} orphan row(s) "
                          f"pointing at a missing {parent}.{pcol}")

                conn.execute(text(
                    f'ALTER TABLE "{child}" ADD CONSTRAINT "{name}" '
                    f'FOREIGN KEY ("{col}") REFERENCES "{parent}"("{pcol}") '
                    f'ON DELETE {on_delete}'
                ))
                print(f"🔗 {name} → {parent}.{pcol} ON DELETE {on_delete}")
        except Exception as e:
            print(f"⚠️  Foreign key {name} skipped: {e}")


# Indexes that cost storage and buy nothing. Each is either an exact duplicate
# of another index on the same column, or measured at near-zero scans against
# hundreds of thousands on its twin (checked 2026-07-29 via pg_stat_user_indexes).
# On the Free plan they were 64% of mandi_price_history's size — 65MB of index
# on 36MB of data — and every one of them also multiplies write-time change
# history, which is what the 512MB branch cap actually measures.
#
#   mandi_history_row_key_uidx      13MB, 3 scans      — UNIQUE dup of ix_..._row_key
#   mandi_history_group_dt_idx      13MB, 3 scans      — superseded by csd_dt
#   ix_mandi_price_history_id      3.9MB, 5 scans      — dup of the primary key
#   ix_mandi_price_history_district 1.6MB, 3 scans     — covered by csd_dt
#   ix_mandi_price_history_state   1.2MB, 5 scans      — covered by csd_dt
#   ix_mandi_prices_id             4.7MB, 277 scans    — dup of the primary key
#   ix_mandi_prices_state          1.2MB, 4 scans      — covered by csd_lower
#
# NOTE row_key: the ON CONFLICT dedup needs a unique index on row_key, so the
# UNIQUE one is what we keep — ix_mandi_price_history_row_key (non-unique) is
# the redundant twin, even though the planner had been picking it. A unique
# index answers the same lookups.
_DEAD_INDEXES = [
    "ix_mandi_price_history_row_key",
    "mandi_history_group_dt_idx",
    "ix_mandi_price_history_id",
    "ix_mandi_price_history_district",
    "ix_mandi_price_history_state",
    "ix_mandi_prices_id",
    "ix_mandi_prices_state",
]


def _drop_dead_indexes():
    """Drop the redundant mandi indexes. Idempotent — IF EXISTS, so this is a
    no-op on every startup after the first and on a fresh database."""
    if engine.dialect.name != "postgresql":
        return
    dropped = []
    for name in _DEAD_INDEXES:
        try:
            with engine.begin() as conn:
                exists = conn.execute(text("SELECT to_regclass(:n)"),
                                      {"n": f"public.{name}"}).scalar()
                if not exists:
                    continue
                # CONCURRENTLY would need autocommit; these are small enough
                # that a plain DROP is a sub-second exclusive lock.
                conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                dropped.append(name)
        except Exception as e:
            print(f"⚠️  could not drop index {name}: {e}")
    if dropped:
        print(f"🗑️  dropped {len(dropped)} redundant mandi index(es): {', '.join(dropped)}")


def _backfill_last_seen():
    """Seed mandi_last_seen from the history still on disk.

    Runs once (skipped as soon as the table has rows) and must happen BEFORE
    the first trim at the new retention, or pages whose only record is an old
    history row would lose it. DISTINCT ON keeps the newest row per group_key.

    Only mandi_price_history is read: it is the superset (every fetched row is
    appended to it, and the snapshot is built from the same rows), and it is
    the only one of the two that carries group_key — mandi_prices does not.
    """
    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.begin() as conn:
            if not conn.execute(text("SELECT to_regclass('public.mandi_price_history')")).scalar():
                return
            if conn.execute(text("SELECT 1 FROM mandi_last_seen LIMIT 1")).scalar():
                return                      # already seeded
            res = conn.execute(text("""
                INSERT INTO mandi_last_seen
                    (group_key, state, district, market, commodity, variety,
                     grade, min_price, max_price, modal_price, arrival_date,
                     arrival_dt, updated_at)
                SELECT DISTINCT ON (group_key)
                    group_key, state, district, market, commodity, variety,
                    grade, min_price, max_price, modal_price, arrival_date,
                    arrival_dt, now()
                FROM mandi_price_history
                WHERE group_key IS NOT NULL AND commodity IS NOT NULL
                ORDER BY group_key, arrival_dt DESC NULLS LAST
                ON CONFLICT (group_key) DO NOTHING
            """))
            if res.rowcount:
                print(f"🌱 mandi_last_seen seeded with {res.rowcount:,} rows")
    except Exception as e:
        print(f"⚠️  mandi_last_seen backfill skipped: {e}")


def init_db():
    try:
        _ensure_table_renames()
        Base.metadata.create_all(bind=engine)
        _ensure_postgres_columns()
        _ensure_users_column_order()
        _ensure_foreign_keys()
        _backfill_last_seen()
        _drop_dead_indexes()
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"⚠️  Database error: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

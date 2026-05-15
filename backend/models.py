from pydantic import BaseModel
from typing import Optional

# --- /ask route ---
class AskRequest(BaseModel):
    q: str                          # question text
    crop: Optional[str] = "general" # selected crop
    language: Optional[str] = "hi"  # "hi" or "en"
    district: Optional[str] = ""    # "Meerut district" or "Kairana village, Meerut district"

class AskResponse(BaseModel):
    answer: str
    source: str = "ai"              # "cache" | "rag" | "ai" | "fallback"
    cached: bool = False

# --- /weather route ---
class WeatherResponse(BaseModel):
    city: str
    state: str
    temp_c: float
    feels_like: float
    condition: str                  # "साफ धूप", "बादल", "बारिश" etc.
    humidity: int
    wind_kmh: float
    advisory: str                   # farming advice based on weather
    updated_at: str

# --- /mandi route ---
class MandiPrice(BaseModel):
    crop: str
    price_per_quintal: float
    market: str
    trend: str                      # "up" | "down" | "stable"
    updated_at: str

class MandiResponse(BaseModel):
    prices: list[MandiPrice]
    district: str

# --- /reset route ---
class ResetResponse(BaseModel):
    status: str = "ok"
    message: str = "Chat reset"
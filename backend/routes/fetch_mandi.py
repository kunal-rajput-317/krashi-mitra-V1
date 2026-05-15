# ============================================================
# Krashi_mitra — Mandi Price Fetcher
# Run manually: python fetch_mandi.py
# Fetches from data.gov.in and stores in PostgreSQL
# ============================================================

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from backend.database.db import MandiPrice, SessionLocal, init_db
from datetime import datetime
import os

load_dotenv()

api_key = os.getenv("DATA_GOV_API_KEY", "")

# List of commodities to fetch
COMMODITIES = ["Wheat", "Rice", "Sugarcane", "Potato", "Onion", "Mustard"]

# Working Agmarknet endpoints to try
ENDPOINTS = [
    "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070",
    "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24",
]

def fetch_and_store():
    init_db()
    db: Session = SessionLocal()

    for commodity in COMMODITIES:
        print(f"\n🌾 Fetching: {commodity}")
        records = []

        for endpoint in ENDPOINTS:
            try:
                params = {
                    "api-key": api_key,
                    "format":  "json",
                    "limit":   100,
                    "filters[state]":     "Uttar Pradesh",
                    "filters[commodity]": commodity,
                }
                res = requests.get(endpoint, params=params, timeout=180) # I have switched timeout from 15 to 60 .
                print(f"   Endpoint status: {res.status_code}")

                if res.status_code == 200 and res.text.strip():
                    data    = res.json()
                    records = data.get("records", [])
                    if records:
                        print(f"   ✅ Got {len(records)} records!")
                        break
                    else:
                        print(f"   ⚠️ Empty records. Raw: {res.text[:200]}")
            except Exception as e:
                print(f"   ❌ Error: {e}")

        if not records:
            # Store dummy data so frontend always has something
            print(f"   📝 Storing sample data for {commodity}")
            sample = get_sample_data(commodity)
            for row in sample:
                db.add(MandiPrice(**row))
            db.commit()
            continue

        # Delete old records for this commodity
        db.query(MandiPrice).filter(MandiPrice.commodity == commodity).delete()

        # Store new records
        for r in records:
            db.add(MandiPrice(
                commodity    = r.get("commodity", commodity),
                district     = r.get("district", ""),
                market       = r.get("market", ""),
                variety      = r.get("variety", ""),
                min_price    = str(r.get("min_price", "")),
                max_price    = str(r.get("max_price", "")),
                modal_price  = str(r.get("modal_price", "")),
                arrival_date = r.get("arrival_date", ""),
                fetched_at   = datetime.utcnow()
            ))
        db.commit()
        print(f"   💾 Saved {len(records)} records to DB.")

    db.close()
    print("\n✅ All done!")

# Sample data fallback if API fails
def get_sample_data(commodity):
    prices = {
        "Wheat":     [("Lucknow", "2150", "2300", "2200"),
                      ("Agra",    "2100", "2280", "2180"),
                      ("Kanpur",  "2120", "2290", "2210")],
        "Rice":      [("Lucknow", "1800", "2100", "1950"),
                      ("Varanasi","1750", "2050", "1900"),
                      ("Bareilly","1820", "2080", "1960")],
        "Sugarcane": [("Lucknow", "290",  "320",  "305"),
                      ("Meerut",  "285",  "315",  "300"),
                      ("Gorakhpur","295", "325",  "310")],
        "Potato":    [("Agra",    "800",  "1200", "1000"),
                      ("Lucknow", "750",  "1150", "950")],
        "Onion":     [("Lucknow", "1200", "1800", "1500"),
                      ("Agra",    "1100", "1700", "1400")],
        "Mustard":   [("Agra",    "5200", "5600", "5400"),
                      ("Mathura", "5100", "5500", "5300")],
    }
    rows = []
    for district, min_p, max_p, modal_p in prices.get(commodity, []):
        rows.append({
            "commodity":    commodity,
            "district":     district,
            "market":       f"{district} Mandi",
            "variety":      "Local",
            "min_price":    min_p,
            "max_price":    max_p,
            "modal_price":  modal_p,
            "arrival_date": datetime.now().strftime("%Y-%m-%d"),
            "fetched_at":   datetime.utcnow()
        })
    return rows

if __name__ == "__main__":
    fetch_and_store()
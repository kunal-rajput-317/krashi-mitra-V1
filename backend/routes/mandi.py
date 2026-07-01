# ============================================================
# routes/mandi.py
# Krishi Mitra — Mandi Price Router
# Thin FastAPI layer. All logic lives in services/mandi_service.py
# ============================================================

from fastapi import APIRouter
from backend.services.mandi_service import (
    get_mandi_prices,
    get_states,
    get_districts,
    get_commodities,
    get_price_history,
)

router = APIRouter()


@router.get("/shop/mandi")
def mandi_prices(commodity: str = "", district: str = "", state: str = ""):
    return get_mandi_prices(commodity, district, state)


@router.get("/shop/mandi/history")
def mandi_history(commodity: str = "", market: str = "", district: str = "",
                  state: str = "", variety: str = "", days: int = 60):
    return get_price_history(commodity, market, district, state, variety, days)


@router.get("/shop/states")
def states():
    return get_states()


@router.get("/shop/districts")
def districts(state: str = ""):
    return get_districts(state)


@router.get("/shop/commodities")
def commodities(state: str = ""):
    return get_commodities(state)
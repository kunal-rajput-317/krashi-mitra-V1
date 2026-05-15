# ============================================================
# routes/fertilizer.py
# Krishi Mitra — Fertilizer Router
# Thin FastAPI layer. All logic lives in services/fertilizer_service.py
# ============================================================

from fastapi import APIRouter
from backend.services.fertilizer_service import get_all_fertilizers

router = APIRouter()


@router.get("/shop/fertilizers")
def fertilizers():
    return get_all_fertilizers()
# ============================================================
# services/fertilizer_service.py
# Krishi Mitra — Fertilizer Service
# Reads from fertilizers.json loaded once at module import.
# No FastAPI dependency here.
# ============================================================

import json
import os

_json_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "fertilizers.json"
)
with open(_json_path, "r") as f:
    fertilizer_data = json.load(f)


def get_all_fertilizers() -> dict:
    return {"fertilizers": fertilizer_data}
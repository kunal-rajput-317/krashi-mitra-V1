"""Render-compatible ASGI entrypoint.

Render is configured to run ``uvicorn main:app`` from the repository root,
while the FastAPI application lives in ``backend.main``.
"""

from backend.main import app


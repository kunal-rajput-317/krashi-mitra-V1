# ============================================================
# KrashiMitra — International Hub & Country Portals Router
# ============================================================

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter(tags=["international"])

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
INTL_DIR = FRONTEND_DIR / "international"


@router.get("/international", response_class=HTMLResponse)
@router.get("/international/", response_class=HTMLResponse)
def international_hub():
    file_path = INTL_DIR / "index.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


@router.get("/us", response_class=HTMLResponse)
@router.get("/international/us", response_class=HTMLResponse)
def portal_us():
    file_path = INTL_DIR / "us.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


@router.get("/uk", response_class=HTMLResponse)
@router.get("/international/uk", response_class=HTMLResponse)
def portal_uk():
    file_path = INTL_DIR / "uk.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


@router.get("/np", response_class=HTMLResponse)
@router.get("/international/np", response_class=HTMLResponse)
def portal_np():
    file_path = INTL_DIR / "np.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


@router.get("/bd", response_class=HTMLResponse)
@router.get("/international/bd", response_class=HTMLResponse)
def portal_bd():
    file_path = INTL_DIR / "bd.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


@router.get("/id", response_class=HTMLResponse)
@router.get("/international/id", response_class=HTMLResponse)
def portal_id():
    file_path = INTL_DIR / "id.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


@router.get("/ng", response_class=HTMLResponse)
@router.get("/international/ng", response_class=HTMLResponse)
def portal_ng():
    file_path = INTL_DIR / "ng.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))


@router.get("/lk", response_class=HTMLResponse)
@router.get("/international/lk", response_class=HTMLResponse)
def portal_lk():
    file_path = INTL_DIR / "lk.html"
    return HTMLResponse(content=file_path.read_text(encoding="utf-8"))

# ============================================================
# routes/admin_articles.py
# Admin API for लेख — /admin/articles/*
#
# The panel's half of services/article_publish.py: write an article, see the
# page it produces, ship it. Nothing here renders or stores anything itself —
# it is auth, validation surface and error wording.
#
# TWO THINGS THIS ROUTER TAKES SERIOUSLY:
#
# 1. A FAILED PUBLISH LEAVES NOTHING BEHIND. save() writes the page, runs the
#    builder's validator, and rolls the file back if the page did not pass and
#    the author did not force it. The panel therefore never has to ask "did
#    half of it go live?" — the answer is always no.
#
# 2. NEON GOES READ-ONLY WITHOUT WARNING. Reads keep working, so the panel
#    looks perfectly healthy while every write 500s. An author who has just
#    typed 2,000 words of Hindi deserves to be told that nothing was saved and
#    that the text is still in the box, not a stack trace. Same guard, same
#    wording as admin_dukan.py.
# ============================================================

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.routes.admin import admin_db, require_admin
from backend.services import article_publish as ap

router = APIRouter(prefix="/admin/articles", tags=["admin-articles"])

# A hero photo off a phone camera is a few MB; anything past this is either a
# mistake or a RAW file, and the 512 MB dyno cannot afford to find out which.
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _write(fn, *args, **kwargs):
    """Run a write, and name the two failures that are not bugs."""
    from backend.database.db import is_read_only_error
    try:
        return fn(*args, **kwargs)
    except ap.PublishError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        if is_read_only_error(e):
            raise HTTPException(
                503,
                "Database is read-only (Neon plan limit) — कुछ भी सेव नहीं हुआ। "
                "लेख इसी बॉक्स में है, DB लिखने लायक होते ही फिर से Publish करें।")
        raise HTTPException(500, str(e))


@router.get("")
def list_articles(_: str = Depends(require_admin), db: Session = Depends(admin_db)):
    """Panel-published articles, plus the counts that put them in context."""
    rows = ap.listing(db)
    return {
        "success": True,
        "articles": rows,
        "cats": {k: {"label": v["label"], "emoji": v["emoji"]}
                 for k, v in ap.CATS.items()},
        # How many articles came from git. The panel shows it so "3 published"
        # is read against 98 committed ones rather than as the whole site.
        "committed": len(ap.committed_slugs()),
        "missing_on_disk": [r["slug"] for r in rows if not r["on_disk"]],
    }


@router.get("/{slug}")
def get_article(slug: str, _: str = Depends(require_admin),
                db: Session = Depends(admin_db)):
    """The payload as submitted, so editing is editing and not retyping."""
    row = ap.get(db, slug.lower())
    if row is None:
        raise HTTPException(404, f"{slug}: कोई पैनल-लेख नहीं")
    return {
        "success": True,
        "slug": row.slug,
        "status": row.status,
        "payload": json.loads(row.payload) if row.payload else None,
        "problems": json.loads(row.problems) if row.problems else [],
        "has_image": bool(row.image_mime),
        "url": f"https://krashimitra.in/articles/{row.slug}",
    }


@router.post("/preview", response_class=HTMLResponse)
def preview(payload: dict = Body(...), _: str = Depends(require_admin)):
    """The real page, rendered, stored nowhere.

    Served as HTML so the panel can drop it straight into an iframe at 390px —
    which is the width 98% of this site's traffic actually reads at, and the
    only width at which a broken layout is visible.
    """
    try:
        return HTMLResponse(ap.render_html(payload))
    except ap.PublishError as e:
        raise HTTPException(400, str(e))


@router.post("/check")
def check(payload: dict = Body(...), _: str = Depends(require_admin)):
    """What the builder would object to, without publishing anything.

    The probe is written to a temp directory under the article's own filename,
    never into frontend/articles/: the validator resolves ../assets against the
    frontend root and everything else off the stem, so the checks are the real
    ones — and a crash between write and cleanup cannot leave a half-page in
    the directory that sitemap.py enumerates.
    """
    try:
        a = ap.expand(payload)
        html = ap.render_html(payload)
    except ap.PublishError as e:
        raise HTTPException(400, str(e))

    with tempfile.TemporaryDirectory(prefix="km-article-") as tmp:
        path = Path(tmp) / f"{a['slug']}.html"
        path.write_text(html, encoding="utf-8")
        # The validator asserts every /articles/ link on the page has a file
        # behind it, and the page's own canonical is one of those links. Before
        # publishing there is no file yet — that complaint is the check working
        # correctly on a page that does not exist, so it is dropped here and
        # nowhere else. save() validates the real file, where it applies.
        self_link = f"internal link has no file: /articles/{a['slug']}"
        problems = [p for p in ap._builder().validate(path) if p != self_link]

    return {"success": True, "slug": a["slug"], "words": a["word_count"],
            "read_time": a["read_time"], "problems": problems}


@router.post("")
def publish(payload: dict = Body(...), force: bool = False,
            _: str = Depends(require_admin), db: Session = Depends(admin_db)):
    """Publish or update. `force` ships a page the validator complained about."""
    result = _write(ap.save, db, payload, force=force)
    if not result["ok"]:
        # 422, not 400: the payload is well-formed, the page it makes is not.
        raise HTTPException(422, {"problems": result["problems"],
                                  "slug": result["slug"]})
    return {"success": True, **result}


@router.post("/{slug}/image")
async def upload_image(slug: str, file: UploadFile = File(...),
                       _: str = Depends(require_admin),
                       db: Session = Depends(admin_db)):
    """The hero photo — one upload feeding the figure, og:image, the schema
    image and the hub card."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "खाली फ़ाइल")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"इमेज {len(raw) // 1024 // 1024} MB की है — "
                                 f"{MAX_IMAGE_BYTES // 1024 // 1024} MB तक ही")
    return {"success": True, **_write(ap.attach_image, db, slug.lower(), raw)}


@router.delete("/{slug}")
def unpublish(slug: str, _: str = Depends(require_admin),
              db: Session = Depends(admin_db)):
    """Take it down — row, page, images and hub card."""
    return {"success": True, **_write(ap.delete, db, slug.lower())}


@router.post("/restore")
def restore(_: str = Depends(require_admin), db: Session = Depends(admin_db)):
    """Re-lay every live article on disk.

    The same pass that runs at boot. Exposed because the one failure mode this
    feature has is "the file is gone and the row is fine", and it should be one
    button rather than a redeploy.
    """
    return {"success": True, **ap.restore_all(db)}

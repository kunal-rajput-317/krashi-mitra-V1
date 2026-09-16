"""Replies, comment likes, and being able to take a comment back down.

The thread under a listing is where a sale actually gets negotiated, and until
now it was write-only: you could add a comment and nothing else. A wrong price,
a phone number typed in public, or abuse under your own crop had no remedy.

What is pinned here:

  * a reply attaches to a comment, and replying to a reply does NOT nest deeper
    — two levels is all a 390px screen can show;
  * an offer is a number against the listing, never a nested reply, or the
    seller stops seeing it;
  * the post's owner can clear anything off his own listing, everyone else only
    their own words, and nobody can touch a third party's;
  * deleting a parent takes its replies with it and the post's counter stays
    honest — it may never drift below zero.
"""

from datetime import datetime

import pytest


SELLER = "bazar-thread-seller@example.com"
BUYER = "bazar-thread-buyer@example.com"
OTHER = "bazar-thread-other@example.com"


def _make_user(db_session, email, name):
    from sqlalchemy import func

    from backend.database.db import User, UserProfile
    from backend.utils.auth_utils import create_access_token

    user = User(name=name, email=email, hashed_password="x",
                is_verified=True, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    n = (db_session.query(func.max(UserProfile.id)).scalar() or 0) + 1
    user.user_id = n
    db_session.commit()
    db_session.add(UserProfile(id=n, user_id=n, name=name, phone_number="9876500777",
                               state="Uttar Pradesh", district="Hardoi", village="Rampur"))
    db_session.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


@pytest.fixture()
def cast(db_session):
    """A seller who owns the listing, a buyer, and an unrelated third party."""
    from backend.database.db import (BazarComment, BazarCommentLike, BazarPost,
                                     User, UserProfile)

    emails = [SELLER, BUYER, OTHER]

    def _wipe():
        rows = db_session.query(User).filter(User.email.in_(emails)).all()
        ids = [u.id for u in rows]
        accts = [u.user_id for u in rows if u.user_id is not None]
        if ids:
            posts = [p.id for p in db_session.query(BazarPost.id)
                     .filter(BazarPost.users_id.in_(ids)).all()]
            cids = []
            if posts:
                cids = [c.id for c in db_session.query(BazarComment.id)
                        .filter(BazarComment.post_id.in_(posts)).all()]
            if cids:
                db_session.query(BazarCommentLike).filter(
                    BazarCommentLike.comment_id.in_(cids)).delete(synchronize_session=False)
            db_session.query(BazarComment).filter(
                BazarComment.users_id.in_(ids)).delete(synchronize_session=False)
            db_session.query(BazarPost).filter(
                BazarPost.users_id.in_(ids)).delete(synchronize_session=False)
            if accts:
                db_session.query(UserProfile).filter(
                    UserProfile.user_id.in_(accts)).delete(synchronize_session=False)
            db_session.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
            db_session.commit()

    _wipe()
    seller, sh = _make_user(db_session, SELLER, "Thread Seller")
    buyer,  bh = _make_user(db_session, BUYER,  "Thread Buyer")
    other,  oh = _make_user(db_session, OTHER,  "Thread Other")

    post = BazarPost(users_id=seller.id, post_type="sell", crop="गेहूं",
                     price=2400, unit="क्विंटल", comments_count=0)
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    yield {"post": post.id, "seller": sh, "buyer": bh, "other": oh,
           "seller_id": seller.id, "buyer_id": buyer.id}
    _wipe()


def _comment(client, cast, headers, text, parent_id=None):
    r = client.post(f"/bazar/posts/{cast['post']}/comments", headers=headers,
                    json={"text": text, "kind": "comment", "parent_id": parent_id})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _thread(client, cast, headers=None):
    r = client.get(f"/bazar/posts/{cast['post']}/comments", headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()["data"]["comments"]


# ── Replies ──────────────────────────────────────────────────

def test_a_reply_nests_under_its_parent(client, cast):
    top = _comment(client, cast, cast["buyer"], "भाव क्या है?")
    _comment(client, cast, cast["seller"], "2400 है।", parent_id=top["id"])

    thread = _thread(client, cast)
    assert len(thread) == 1, "a reply must not appear as a second top-level comment"
    assert len(thread[0]["replies"]) == 1
    assert thread[0]["replies"][0]["text"] == "2400 है।"


def test_replying_to_a_reply_does_not_nest_deeper(client, cast):
    """Two levels is all a 390px screen can show; a third would run off it."""
    top = _comment(client, cast, cast["buyer"], "भाव क्या है?")
    mid = _comment(client, cast, cast["seller"], "2400 है।", parent_id=top["id"])
    deep = _comment(client, cast, cast["buyer"], "ठीक है।", parent_id=mid["id"])

    assert deep["parent_id"] == top["id"], "a reply to a reply must join its parent"
    thread = _thread(client, cast)
    assert len(thread) == 1
    assert len(thread[0]["replies"]) == 2


def test_an_offer_cannot_be_hidden_inside_a_thread(client, cast):
    top = _comment(client, cast, cast["buyer"], "भाव क्या है?")
    r = client.post(f"/bazar/posts/{cast['post']}/comments", headers=cast["buyer"],
                    json={"kind": "offer", "offer_amount": 2300, "parent_id": top["id"]})
    assert r.status_code == 400, "an offer nested under a comment stops being visible"


def test_a_reply_cannot_cross_posts(client, cast, db_session):
    from backend.database.db import BazarPost

    other_post = BazarPost(users_id=cast["seller_id"], post_type="sell", crop="धान")
    db_session.add(other_post)
    db_session.commit()
    db_session.refresh(other_post)
    try:
        top = _comment(client, cast, cast["buyer"], "भाव क्या है?")
        r = client.post(f"/bazar/posts/{other_post.id}/comments", headers=cast["buyer"],
                        json={"text": "x", "parent_id": top["id"]})
        assert r.status_code == 404
    finally:
        db_session.delete(other_post)
        db_session.commit()


# ── Deleting ─────────────────────────────────────────────────

def test_the_author_can_delete_their_own_comment(client, cast):
    c = _comment(client, cast, cast["buyer"], "गलत नंबर लिख दिया")
    r = client.delete(f"/bazar/posts/{cast['post']}/comments/{c['id']}", headers=cast["buyer"])
    assert r.status_code == 200, r.text
    assert _thread(client, cast) == []


def test_the_post_owner_can_clear_anything_off_his_listing(client, cast):
    """He must not have to wait for us to take abuse off his own crop."""
    c = _comment(client, cast, cast["buyer"], "कुछ गलत")
    r = client.delete(f"/bazar/posts/{cast['post']}/comments/{c['id']}", headers=cast["seller"])
    assert r.status_code == 200, r.text
    assert _thread(client, cast) == []


def test_a_stranger_cannot_delete_someone_elses_comment(client, cast):
    c = _comment(client, cast, cast["buyer"], "मेरा सवाल")
    r = client.delete(f"/bazar/posts/{cast['post']}/comments/{c['id']}", headers=cast["other"])
    assert r.status_code == 403
    assert len(_thread(client, cast)) == 1


def test_deleting_a_parent_takes_its_replies_with_it(client, cast, db_session):
    from backend.database.db import BazarPost

    top = _comment(client, cast, cast["buyer"], "सवाल")
    _comment(client, cast, cast["seller"], "जवाब 1", parent_id=top["id"])
    _comment(client, cast, cast["other"], "जवाब 2", parent_id=top["id"])

    r = client.delete(f"/bazar/posts/{cast['post']}/comments/{top['id']}", headers=cast["buyer"])
    assert r.status_code == 200, r.text
    assert len(r.json()["data"]["deleted"]) == 3
    assert _thread(client, cast) == []

    db_session.expire_all()
    post = db_session.query(BazarPost).filter(BazarPost.id == cast["post"]).first()
    assert post.comments_count == 0


def test_the_counter_never_goes_negative(client, cast, db_session):
    """These counters predate the column and some live rows drifted."""
    from backend.database.db import BazarPost

    c = _comment(client, cast, cast["buyer"], "एक")
    post = db_session.query(BazarPost).filter(BazarPost.id == cast["post"]).first()
    post.comments_count = 0          # simulate the drift
    db_session.commit()

    r = client.delete(f"/bazar/posts/{cast['post']}/comments/{c['id']}", headers=cast["buyer"])
    assert r.status_code == 200
    assert r.json()["data"]["comments_count"] == 0


# ── Comment likes ────────────────────────────────────────────

def test_a_comment_like_toggles(client, cast):
    c = _comment(client, cast, cast["buyer"], "अच्छा भाव")

    on = client.post(f"/bazar/comments/{c['id']}/like", headers=cast["seller"])
    assert on.status_code == 200, on.text
    assert on.json()["data"] == {"liked": True, "likes_count": 1}

    off = client.post(f"/bazar/comments/{c['id']}/like", headers=cast["seller"])
    assert off.json()["data"] == {"liked": False, "likes_count": 0}


def test_one_like_per_person_however_many_taps(client, cast):
    c = _comment(client, cast, cast["buyer"], "अच्छा भाव")
    client.post(f"/bazar/comments/{c['id']}/like", headers=cast["seller"])
    client.post(f"/bazar/comments/{c['id']}/like", headers=cast["other"])
    r = client.post(f"/bazar/comments/{c['id']}/like", headers=cast["other"])   # untoggle
    assert r.json()["data"]["likes_count"] == 1


def test_a_drifted_like_counter_heals_on_the_next_tap(client, cast, db_session):
    """Counted from the rows, not incremented, so it cannot drift forever."""
    from backend.database.db import BazarComment

    c = _comment(client, cast, cast["buyer"], "अच्छा भाव")
    row = db_session.query(BazarComment).filter(BazarComment.id == c["id"]).first()
    row.likes_count = 97
    db_session.commit()

    r = client.post(f"/bazar/comments/{c['id']}/like", headers=cast["seller"])
    assert r.json()["data"]["likes_count"] == 1


def test_the_thread_tells_the_viewer_what_they_may_do(client, cast):
    """can_delete and liked_by_me are per-viewer; the card renders off them."""
    c = _comment(client, cast, cast["buyer"], "सवाल")
    client.post(f"/bazar/comments/{c['id']}/like", headers=cast["buyer"])

    as_buyer = _thread(client, cast, cast["buyer"])[0]
    assert as_buyer["liked_by_me"] is True
    assert as_buyer["can_delete"] is True

    as_owner = _thread(client, cast, cast["seller"])[0]
    assert as_owner["liked_by_me"] is False
    assert as_owner["can_delete"] is True      # his listing

    as_other = _thread(client, cast, cast["other"])[0]
    assert as_other["can_delete"] is False

    as_guest = _thread(client, cast)[0]
    assert as_guest["can_delete"] is False and as_guest["liked_by_me"] is False


# ── The page itself ──────────────────────────────────────────

def _page():
    import io
    from pathlib import Path
    return io.open(Path(__file__).resolve().parents[1] / "frontend" / "krashi_bajar.html",
                   encoding="utf-8").read()


def test_the_thread_paints_before_it_waits_on_anything():
    """The complaint was that Like and Comment felt dead.

    Both used to await the member gate, then the POST, then — for comments — a
    full refetch of the thread, before a single pixel moved. Everything the
    farmer can see now happens first and the network reconciles afterwards.
    """
    import re

    html = _page()
    for fn in ("sendComment", "toggleCommentLike"):
        body = html[html.index(f"async function {fn}("):]
        body = body[:body.index("\n}\n")]
        # Strip // comments: the prose explaining the old behaviour says
        # "awaited", and matching prose instead of code is a false failure.
        code = re.sub(r"//[^\n]*", "", body)
        first_paint = min(
            (code.index(m) for m in ("renderComments()", "paint();") if m in code),
            default=-1,
        )
        assert first_paint > -1, f"{fn} never paints"
        assert "await" not in code[:first_paint], (
            f"{fn} awaits something before it paints — that is the lag being fixed"
        )


def test_a_failed_comment_gives_the_farmer_his_words_back():
    """Optimism is only safe if the rollback is complete. He typed it on a
    phone keyboard in a field; losing it is worse than a slow button."""
    html = _page()
    body = html[html.index("async function sendComment("):]
    body = body[:body.index("\n}\n")]
    assert body.count("input.value = text;") == 2, (
        "both the gate refusal and the network failure must restore the text"
    )


def test_the_decorative_emoji_are_gone():
    """Asked for directly: the stickers had become visual noise.

    The sidebar drawer's link icons are deliberately excluded — that markup is
    shared with every other page on the site.
    """
    html = _page()
    lines = [l for l in html.split("\n") if "sidebar-drawer" not in l]
    body = "\n".join(lines)
    for glyph in ["🚀", "💰", "📦", "✏️", "📍", "🎉", "📋", "👋", "➕", "🔒", "📷", "🌾", "🛒"]:
        assert glyph not in body, f"{glyph} is back on the page"


def test_the_loader_is_a_spinner_not_a_sticker():
    html = _page()
    assert "bz-spin" in html
    assert "bz-grow-cycle" not in html, "the sprouting-wheat emoji animation is back"


def test_the_thread_actions_are_icons_that_still_say_what_they_do():
    """Like / Reply / Delete are icons, not Hindi words.

    As text they put a second line of prose directly under the comment's own
    text and read as more comment rather than as controls. The words must not
    simply vanish though — a screen reader and a long press still need them,
    in whichever language the page is set to.
    """
    import re

    html = _page()
    acts = html[html.index('<div class="bz-comment-acts">'):]
    acts = acts[:acts.index("</div>`")]

    for icon in ("IC_THUMB_FILLED", "IC_THUMB_OUTLINE", "IC_REPLY", "IC_TRASH"):
        assert icon in acts, f"{icon} missing from the comment actions"
    # Every button carries both, and neither is hard-coded to one language.
    assert acts.count("aria-label=") == 3
    assert acts.count("title=") == 3
    for key in ("tr.like", "tr.reply", "tr.delete_c"):
        assert key in acts, f"{key} is no longer the label source"
    # No bare Hindi label left as the button's visible content.
    assert "escapeHtml(tr.like)}<" not in acts

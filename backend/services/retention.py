# ============================================================
# services/retention.py — personal data that has outlived its purpose
#
# LEGAL_RULES §4 says collect only what a feature needs; the DPDP Act adds
# that it is erased once the purpose is served. Two tables kept rows forever:
#
#   chat_history — AI chat questions and answers. Nothing reads an old row
#     back (the model never sees history, see routes/chatbot.py step 4), and
#     a question can carry whatever a farmer typed. Deleted after CHAT_DAYS.
#
#   orders — name, email, phone, pincode on every order and pre-book, even
#     the ones that never became a sale. After ORDER_CONTACT_DAYS the contact
#     fields are blanked; product, quantity, price and status stay, so the
#     order still counts in the books. The money itself is in `payments`,
#     which keeps 8 years for tax law and is NOT touched here.
#
# Run daily by services/mandi_scheduler.py. Both are single bulk statements.
# ============================================================
from datetime import datetime, timedelta

from backend.database.db import ChatHistory, Order

CHAT_DAYS          = 90
ORDER_CONTACT_DAYS = 730   # 2 years


def purge_old_chats(db, now=None) -> int:
    cutoff = (now or datetime.utcnow()) - timedelta(days=CHAT_DAYS)
    n = db.query(ChatHistory).filter(ChatHistory.created_at < cutoff) \
          .delete(synchronize_session=False)
    db.commit()
    return n


def anonymise_old_orders(db, now=None) -> int:
    cutoff = (now or datetime.utcnow()) - timedelta(days=ORDER_CONTACT_DAYS)
    n = db.query(Order).filter(Order.created_at < cutoff, Order.phone != "") \
          .update({
              Order.user_email:    None,
              Order.user_name:     None,
              Order.customer_name: None,
              Order.phone:         "",      # NOT NULL column
              Order.pincode:       None,
              Order.delivery_info: None,
              Order.session_id:    None,
          }, synchronize_session=False)
    db.commit()
    return n


def sweep(db, now=None) -> dict:
    return {"chats_deleted":     purge_old_chats(db, now),
            "orders_anonymised": anonymise_old_orders(db, now)}

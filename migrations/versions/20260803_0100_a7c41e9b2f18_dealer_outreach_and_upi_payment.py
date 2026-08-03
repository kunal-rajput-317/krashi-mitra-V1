"""dealer outreach + UPI payment tracking on buyers

Turns the `buyers` row into the call-tracking row as well. The alternative was a
separate sheet or table holding a second copy of every name, number and district
— two records that drift apart, and disagree on the day it matters, mid-call.

`called_at` / `call_result` / `call_count` answer the question
data/deadline_checklist.json §8.4 says decides a failed 31-Aug test: did the
market say no, or were the calls never made? `status` alone cannot tell those
apart — a dealer never rung and one rung and refused both read as "not live".

`paid_*` are written only by services/dealers.py::record_payment, from the admin
panel, by a human who saw the credit in a bank app. A upi:// deep link hands off
to the payer's own app and reports nothing back (services/upi.py), so there is
no callback that could set these and nothing automated may ever try — an
auto-ticked "paid" is a fabricated receipt.

All nullable: rows written before today were genuinely never called, and NULL
says that honestly where a 0 or false would claim a call happened.

NOTE: same caveat as the buyers-table revision — production has not been stamped
with the baseline yet, and db.py::init_db() patches columns via
_ensure_postgres_columns() on every boot, so in practice these columns arrive
that way rather than from this migration. This revision exists so the migration
history stays a truthful description of the schema for whenever the stamp
happens.

Revision ID: a7c41e9b2f18
Revises: f3d92e4d4a78
Create Date: 2026-08-03 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c41e9b2f18'
down_revision: Union[str, None] = 'f3d92e4d4a78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buyers', sa.Column('called_at', sa.DateTime(), nullable=True))
    op.add_column('buyers', sa.Column('call_result', sa.String(), nullable=True))
    op.add_column('buyers', sa.Column('call_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('buyers', sa.Column('paid_at', sa.DateTime(), nullable=True))
    op.add_column('buyers', sa.Column('paid_amount', sa.Integer(), nullable=True))
    op.add_column('buyers', sa.Column('payment_ref', sa.String(), nullable=True))
    op.add_column('buyers', sa.Column('paid_until', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('buyers', 'paid_until')
    op.drop_column('buyers', 'payment_ref')
    op.drop_column('buyers', 'paid_amount')
    op.drop_column('buyers', 'paid_at')
    op.drop_column('buyers', 'call_count')
    op.drop_column('buyers', 'call_result')
    op.drop_column('buyers', 'called_at')

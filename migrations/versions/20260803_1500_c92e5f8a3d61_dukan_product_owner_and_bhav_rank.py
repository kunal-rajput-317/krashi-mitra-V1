"""dukan/product: owner_user_id + bhav_rank on buyers

Backs the paid, login-gated /dukan/product flow that replaces the old anonymous
/dukan/signup. Two columns:

`owner_user_id` ties a district-row back to the dealer's own account (a real
users.id, set once from the authenticated token in routes/dukan.py, never from
client input). Rows sharing an owner_user_id are one dealer's account — one
subscription payment (services/dealers.py::record_payment) renews every row
that shares it, and services/buyers.py::for_bhav_panel groups them by state.

`bhav_rank` (1/2/3 or NULL) is which of the ≤3 Tier-3 bhav-panel slots a row
holds for its state — admin-only, set through dealers.py::set_bhav_rank(),
which clears any other row in the same state already holding that rank so two
paying dealers never collide on one slot.

NOTE: same caveat as the two prior buyers-table revisions — production has not
been stamped with the baseline yet, and db.py::init_db() patches columns via
_ensure_postgres_columns() on every boot, so in practice these columns arrive
that way rather than from this migration. This revision exists so the
migration history stays a truthful description of the schema for whenever the
stamp happens.

Revision ID: c92e5f8a3d61
Revises: a7c41e9b2f18
Create Date: 2026-08-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c92e5f8a3d61'
down_revision: Union[str, None] = 'a7c41e9b2f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buyers', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.add_column('buyers', sa.Column('bhav_rank', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_buyers_owner_user_id'), 'buyers', ['owner_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_buyers_owner_user_id'), table_name='buyers')
    op.drop_column('buyers', 'bhav_rank')
    op.drop_column('buyers', 'owner_user_id')

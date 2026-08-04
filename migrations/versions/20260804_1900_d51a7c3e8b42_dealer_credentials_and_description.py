"""dealer credentials + public description on buyers

Five columns, two purposes.

CREDENTIALS (gstin, license_no, email, address) are admin-only — services/
dealers.py::listing() hands them to the panel and services/buyers.py::as_dict()
deliberately does not carry them, so no farmer-facing page can render one by
accident. They exist to make `verified` mean something checkable rather than
"we rang a number once": a khad-beej dealer is legally required to hold a
fertilizer/seed licence, which is the strongest thing we can verify about him,
and the blue tick is a claim we make to a farmer about a stranger.

DESCRIPTION is the opposite — the dealer's own public words about what he deals
in, written by him on /dukan/product and rendered on the kharidar card.

It exists because `note` could not do both jobs. `note` is the private call log
(dealers.py::log_call appends "[04 Aug] wants a discount" to it after every
call) AND it was the field the public card rendered — so internal remarks about
a dealer's haggling were being published to farmers under his own name. This
column takes over the public role and `note` never leaves the admin panel again.

All nullable and unvalidated: a trader reading a GST number off a certificate
over a bad phone line is not a form-validation problem, and rejecting the row
would lose the listing rather than improve the data.

NOTE: same caveat as the prior buyers revisions — production has not been
stamped with the baseline yet, and db.py::init_db() patches columns via
_ensure_postgres_columns() on every boot, so in practice these arrive that way
rather than from this migration. This revision keeps the migration history a
truthful description of the schema for whenever the stamp happens.

Revision ID: d51a7c3e8b42
Revises: c92e5f8a3d61
Create Date: 2026-08-04 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd51a7c3e8b42'
down_revision: Union[str, None] = 'c92e5f8a3d61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('buyers', sa.Column('gstin', sa.String(), nullable=True))
    op.add_column('buyers', sa.Column('license_no', sa.String(), nullable=True))
    op.add_column('buyers', sa.Column('email', sa.String(), nullable=True))
    op.add_column('buyers', sa.Column('address', sa.String(), nullable=True))
    op.add_column('buyers', sa.Column('description', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('buyers', 'description')
    op.drop_column('buyers', 'address')
    op.drop_column('buyers', 'email')
    op.drop_column('buyers', 'license_no')
    op.drop_column('buyers', 'gstin')

"""dealer_placements — which /bhav page a paying dealer is shown on, and where

Eligibility and placement were the same column, and they are not the same
thing. `buyers.bhav_rank` held one rank for a whole state: giving a wheat
dealer rank 1 took rank 1 from a rice dealer who could never have appeared on
the same page, and it could not express "district page only" at all.

That second case is a product, not a detail — the two things being sold are:

    /bhav/{crop}/{state}/{district}   ₹199/month, +₹50 per extra district
    /bhav/{crop}/{state}              ₹999/month, +₹999 per extra state

One row per (page, rank) is the only shape that can hold both at once.

`district_slug` is '' for a state page rather than NULL, because Postgres
treats NULLs as distinct in a UNIQUE constraint — a nullable column would let
two dealers both hold rank 1 on the same state page, which is the exact
collision uq_placement_slot exists to prevent.

`price` is a snapshot of what was agreed, not a lookup: list prices move and a
dealer already on the wall keeps the number he said yes to.

NOTE: production has not been stamped with the baseline yet and db.py::init_db()
calls Base.metadata.create_all() on every boot, so in practice this table is
created by that rather than by this migration. The revision exists so the
history stays a truthful description of the schema.

Revision ID: a3f71c4d8e92
Revises: f84c2d5e9b13
Create Date: 2026-08-05 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f71c4d8e92'
down_revision: Union[str, None] = 'f84c2d5e9b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dealer_placements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('buyer_slug', sa.String(), nullable=False),
        sa.Column('crop_slug', sa.String(), nullable=False),
        sa.Column('state_slug', sa.String(), nullable=False),
        sa.Column('district_slug', sa.String(), server_default='', nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('crop_slug', 'state_slug', 'district_slug', 'rank',
                            name='uq_placement_slot'),
        sa.UniqueConstraint('crop_slug', 'state_slug', 'district_slug', 'buyer_slug',
                            name='uq_placement_one_per_dealer'),
    )
    op.create_index(op.f('ix_dealer_placements_id'), 'dealer_placements', ['id'])
    op.create_index(op.f('ix_dealer_placements_buyer_slug'), 'dealer_placements', ['buyer_slug'])
    op.create_index('ix_placement_page', 'dealer_placements',
                    ['crop_slug', 'state_slug', 'district_slug'])


def downgrade() -> None:
    op.drop_index('ix_placement_page', table_name='dealer_placements')
    op.drop_index(op.f('ix_dealer_placements_buyer_slug'), table_name='dealer_placements')
    op.drop_index(op.f('ix_dealer_placements_id'), table_name='dealer_placements')
    op.drop_table('dealer_placements')

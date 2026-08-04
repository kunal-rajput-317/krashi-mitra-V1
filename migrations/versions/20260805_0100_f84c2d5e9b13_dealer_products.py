"""dealer_products — the catalogue behind /dukan/product

A `buyers` row answers "who buys here and how do I reach him". This table
answers "what is he selling, and at what price" — which is what a farmer is
scanning a listing for, and the reason a dealer pays to be on the page.

Field-for-field the shape backend/routes/product.py::_hub_card() already
renders (name_hi / name_en / price / mrp / unit_hi), so a dealer's card and a
KrashiMitra catalogue card are the same object to a farmer's eye: one design
language and one discount calculation rather than a second visual vocabulary.
`mrp` is nullable — a trader quoting a loose rate has nothing to strike through
and gets no "% off" pill.

Keyed on `owner_user_id` where there is one, so a dealer paying for three
districts types his catalogue once and it shows in all three; `buyer_slug` is
the fallback for admin-typed rows that have no account behind them.

The image lives on the product, not the dealer — it is a picture of a 5kg seed
bag, not of a firm. Base64 WebP in Postgres for the reason routes/profile.py
learned with avatars (Render wipes uploads/ on restart), and deferred() in the
model so the blob never loads on a /bhav render.

NOTE: production has not been stamped with the baseline yet and db.py::init_db()
calls Base.metadata.create_all() on every boot, so in practice this table is
created by that rather than by this migration. The revision exists so the
history stays a truthful description of the schema.

Revision ID: f84c2d5e9b13
Revises: d51a7c3e8b42
Create Date: 2026-08-05 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f84c2d5e9b13'
down_revision: Union[str, None] = 'd51a7c3e8b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dealer_products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('buyer_slug', sa.String(), nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('name_hi', sa.String(), nullable=False),
        sa.Column('name_en', sa.String(), nullable=True),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('mrp', sa.Integer(), nullable=True),
        sa.Column('unit_hi', sa.String(), nullable=True),
        sa.Column('badge', sa.String(), nullable=True),
        sa.Column('image_data', sa.Text(), nullable=True),
        sa.Column('image_mime', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dealer_products_id'), 'dealer_products', ['id'])
    op.create_index(op.f('ix_dealer_products_buyer_slug'), 'dealer_products', ['buyer_slug'])
    op.create_index(op.f('ix_dealer_products_owner_user_id'), 'dealer_products', ['owner_user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_dealer_products_owner_user_id'), table_name='dealer_products')
    op.drop_index(op.f('ix_dealer_products_buyer_slug'), table_name='dealer_products')
    op.drop_index(op.f('ix_dealer_products_id'), table_name='dealer_products')
    op.drop_table('dealer_products')

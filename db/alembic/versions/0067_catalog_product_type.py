"""Catalog items keep the old system's product type

The old system's catalog types are finer than the six catalog tables (Glass, Supplies, Paint, Edging,
Laminate Benchtop, Contractor Manufacturing...). Each catalog row gets a free-text `product_type`
(nullable; the tab still comes from the table the row is in), so the type survives the move and can be
shown and filtered on the Catalog screen. Downgrade drops the column.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-15
"""
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

_TABLES = ("board_materials", "hardware_materials", "custom_made", "benchtop_materials", "appliances",
           "equipment_hire")


def upgrade():
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ADD COLUMN product_type varchar(64);")


def downgrade():
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS product_type;")

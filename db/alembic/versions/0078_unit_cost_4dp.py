"""Catalog `unit_cost` keeps four decimals

The API accepted `unit_cost` up to 15 digits with 4 decimals, but every catalog column was
`numeric(12,2)` (`0007`, `0069`, `0070`, `0074`): a value over 10 whole digits was a 500 and a value
with more than 2 decimals was silently rounded to cents. User decision (2026-10-20): widen the
columns to `numeric(14,4)` on all nine catalog tables (10 whole digits, as before; the API limit is
now `max_digits=14, decimal_places=4`). Order lines take the price into `po_line_items.unit_price`
(`numeric(15,4)`) and their `line_total` is `round(quantity * unit_price, 2)`, so nothing downstream
needed widening. No view, index or constraint refers to these columns.

Downgrade narrows back to `numeric(12,2)` and **rounds** each value to cents (half away from zero,
Postgres' own rounding): a unit cost of 1.2345 becomes 1.23. Both types hold 10 whole digits, but a value
in 9999999999.995 .. 9999999999.9999 would round up to 11 digits and fail the whole downgrade, so it is
capped at 9999999999.99 instead.

Revision ID: 0078
Revises: 0077
Create Date: 2026-10-20
"""
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

_TABLES = (
    "board_materials", "hardware_materials", "custom_made", "benchtop_materials", "appliances",
    "equipment_hire", "edging_materials", "glass_materials", "timber_materials",
)


def upgrade():
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ALTER COLUMN unit_cost TYPE numeric(14,4);")


def downgrade():
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} ALTER COLUMN unit_cost TYPE numeric(12,2) USING LEAST(round(unit_cost, 2), 9999999999.99);")

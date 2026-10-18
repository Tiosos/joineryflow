"""Order types: the 13 the old system's list has and the new one lacked

The customer's screenshot of the old Order Type list has 18 types. Five already exist here (Acoustic
panel, Board, Benchtop, Contractor, Hardware); these 13 are new lookup rows in `order_category`, with
the old list's wording as the label. They sort after the joinery types. The older types the old list
does not have (IT, Office, Metal, Cushion, ...) are kept. Downgrade archives the rows rather than
deleting them: an order may use one.

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-15
"""
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

_TYPES = [
    ("ContractorInstall", "Contractor Install", 200), ("CorianClad", "Corian Clad", 210),
    ("Delivery", "Delivery", 220), ("Edging", "Edging", 230), ("Extra", "Extra", 240),
    ("Equipment", "Equipment", 250), ("Glass", "Glass", 260), ("Laminate", "Laminate", 270),
    ("Maintenance", "Maintenance", 280), ("StoneClad", "Stone Clad", 290),
    ("SolidSurface", "Solid Surface", 300), ("Supplies", "Supplies", 310), ("Wages", "Wages", 320),
]


def upgrade():
    values = ", ".join(f"('{k}', '{label}', {order})" for k, label, order in _TYPES)
    op.execute(f"""
    INSERT INTO order_category (category_key, label, sort_order) VALUES {values}
    ON CONFLICT (category_key) DO UPDATE SET archived_at = NULL;
    """)


def downgrade():
    keys = ", ".join(f"'{k}'" for k, _, _ in _TYPES)
    op.execute(f"UPDATE order_category SET archived_at = now() WHERE category_key IN ({keys});")

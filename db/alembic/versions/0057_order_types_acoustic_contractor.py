"""Orderbook order types: Acoustic panel and Contractor-manufacturing

The old Orderbook groups orders under a type heading and has a detail layout per type. Benchtop
already exists (`0031`); the other two the customer's screens show are new lookup rows in
`order_category`: `Acoustic` (board size, colour, substrate, finish...) and `Contractor`
(a free description). Their type-specific fields live in `purchase_orders.attributes` (Q503), so
nothing else changes. Downgrade archives the rows rather than deleting them: an order may use one.

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-10
"""
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    INSERT INTO order_category (category_key, label, sort_order) VALUES
        ('Acoustic',   'Acoustic panel',            105),
        ('Contractor', 'Contractor-manufacturing',  125)
    ON CONFLICT (category_key) DO UPDATE SET archived_at = NULL;
    """)


def downgrade():
    op.execute("""
    UPDATE order_category SET archived_at = now()
     WHERE category_key IN ('Acoustic', 'Contractor');
    """)

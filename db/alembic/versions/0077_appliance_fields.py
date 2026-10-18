"""Appliances get a UM, a product website and one picture

`appliances` stays its own table (PK `material_id`). The old order screen for an appliance (a dishwasher,
order type HARDWARE) has only product code, product website, description, image, unit of measure and cost,
so the three missing fields are added as for Hardware (`0072`), Custom (`0073`) and Equipment Hire (`0076`).
All nullable. Downgrade drops the columns.

Revision ID: 0077
Revises: 0076
Create Date: 2026-10-18
"""
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE appliances
            ADD COLUMN um              varchar(32),
            ADD COLUMN product_website varchar(255),
            ADD COLUMN image_blob      bigint REFERENCES file_blob(file_blob_id);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE appliances
            DROP COLUMN IF EXISTS um, DROP COLUMN IF EXISTS product_website, DROP COLUMN IF EXISTS image_blob;
    """)

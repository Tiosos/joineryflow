"""Custom items get a UM, a product website and one picture

`custom_made` keeps serving Contractor Manufacturing (and Delivery) items; the old CONTRACTOR-MANUFACTURING
order screen has no fields of its own beyond description, unit of measure, product website and product
image, so those three are added as for Hardware (`0072`). All nullable. Downgrade drops the columns.

Revision ID: 0073
Revises: 0072
Create Date: 2026-10-16
"""
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE custom_made
            ADD COLUMN um              varchar(32),
            ADD COLUMN product_website varchar(255),
            ADD COLUMN image_blob      bigint REFERENCES file_blob(file_blob_id);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE custom_made
            DROP COLUMN IF EXISTS um, DROP COLUMN IF EXISTS product_website, DROP COLUMN IF EXISTS image_blob;
    """)

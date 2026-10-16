"""Hardware items get a UM, a product website and one picture

`hardware_materials` keeps serving the Hardware type (and, until their own turns, Supplies and Paint), as
`board_materials` does for Board (`0068`). The old HARDWARE order screen has almost no hardware-specific
fields: description, unit of measure, product website and product image. `brand` and `hardware_type`
already existed (`0001`) and are now shown and edited. Adds `um`, `product_website` and `image_blob`
(all nullable). Downgrade drops the columns.

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-16
"""
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE hardware_materials
            ADD COLUMN um              varchar(32),
            ADD COLUMN product_website varchar(255),
            ADD COLUMN image_blob      bigint REFERENCES file_blob(file_blob_id);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE hardware_materials
            DROP COLUMN IF EXISTS um, DROP COLUMN IF EXISTS product_website, DROP COLUMN IF EXISTS image_blob;
    """)

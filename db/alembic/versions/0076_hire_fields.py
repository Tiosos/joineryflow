"""Equipment Hire gets a UM, a product website and one picture

`equipment_hire` stays its own table (PK `hire_id`, needs `project_id`). The old PLANT HIRE order screen
has only product code, product website, description, image, unit of measure (ea) and cost, so the three
missing fields are added as for Hardware (`0072`) and Custom (`0073`). All nullable. Downgrade drops the columns.

Revision ID: 0076
Revises: 0075
Create Date: 2026-10-16
"""
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE equipment_hire
            ADD COLUMN um              varchar(32),
            ADD COLUMN product_website varchar(255),
            ADD COLUMN image_blob      bigint REFERENCES file_blob(file_blob_id);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE equipment_hire
            DROP COLUMN IF EXISTS um, DROP COLUMN IF EXISTS product_website, DROP COLUMN IF EXISTS image_blob;
    """)

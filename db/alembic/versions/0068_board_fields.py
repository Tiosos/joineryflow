"""Board catalog items get the old Orders screen's board fields

Colour, Substrate, Finish, Sided, Grain (free text, not the `grain_locked` switch), Rating and HMR,
plus a Product website and one Product image (`image_blob`, in the shared file store). All nullable, so
existing rows are untouched. Downgrade drops the columns.

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-16
"""
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE board_materials
            ADD COLUMN colour          varchar(128),
            ADD COLUMN substrate       varchar(128),
            ADD COLUMN finish          varchar(128),
            ADD COLUMN sided           varchar(64),
            ADD COLUMN grain           varchar(64),
            ADD COLUMN rating          varchar(64),
            ADD COLUMN hmr             varchar(64),
            ADD COLUMN product_website varchar(255),
            ADD COLUMN image_blob      bigint REFERENCES file_blob(file_blob_id);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE board_materials
            DROP COLUMN IF EXISTS colour, DROP COLUMN IF EXISTS substrate, DROP COLUMN IF EXISTS finish,
            DROP COLUMN IF EXISTS sided, DROP COLUMN IF EXISTS grain, DROP COLUMN IF EXISTS rating,
            DROP COLUMN IF EXISTS hmr, DROP COLUMN IF EXISTS product_website, DROP COLUMN IF EXISTS image_blob;
    """)

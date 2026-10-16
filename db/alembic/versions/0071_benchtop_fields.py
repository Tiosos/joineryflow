"""Laminate Benchtop items get the old Orders screen's benchtop fields

`benchtop_materials` keeps serving the Laminate Benchtop type (and TG Solid; Solid Timber moved out in
`0074`), as `board_materials` does for Board (`0068`). It gains colour, underside, edge details,
laminate supplier, laminate code, finish, UM, product website, the bench size (length and width in mm; the
existing `thickness_mm` is the bench thickness), pieces, joins, cable entry, shaped and one picture
(`image_blob`). All nullable except `shaped`, so existing rows are untouched. Downgrade drops the columns.

Revision ID: 0071
Revises: 0070
Create Date: 2026-10-16
"""
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE benchtop_materials
            ADD COLUMN colour            varchar(128),
            ADD COLUMN underside         varchar(128),
            ADD COLUMN edge_details      varchar(128),
            ADD COLUMN laminate_supplier varchar(128),
            ADD COLUMN laminate_code     varchar(64),
            ADD COLUMN finish            varchar(128),
            ADD COLUMN um                varchar(32),
            ADD COLUMN product_website   varchar(255),
            ADD COLUMN bench_length_mm   numeric(8,2),
            ADD COLUMN bench_width_mm    numeric(8,2),
            ADD COLUMN pieces            integer,
            ADD COLUMN joins             integer,
            ADD COLUMN cable_entry       integer,
            ADD COLUMN shaped            boolean NOT NULL DEFAULT false,
            ADD COLUMN image_blob        bigint REFERENCES file_blob(file_blob_id);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE benchtop_materials
            DROP COLUMN IF EXISTS colour, DROP COLUMN IF EXISTS underside, DROP COLUMN IF EXISTS edge_details,
            DROP COLUMN IF EXISTS laminate_supplier, DROP COLUMN IF EXISTS laminate_code,
            DROP COLUMN IF EXISTS finish, DROP COLUMN IF EXISTS um, DROP COLUMN IF EXISTS product_website,
            DROP COLUMN IF EXISTS bench_length_mm, DROP COLUMN IF EXISTS bench_width_mm,
            DROP COLUMN IF EXISTS pieces, DROP COLUMN IF EXISTS joins, DROP COLUMN IF EXISTS cable_entry,
            DROP COLUMN IF EXISTS shaped, DROP COLUMN IF EXISTS image_blob;
    """)

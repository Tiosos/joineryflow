"""Board gets a UM (Laminate stays a tab over board_materials)

The old LAMINATE order screen has Board's fields (sheet size L x W x Thk, colour, finish, product website,
description, image) plus a unit of measure. Laminate gets no table of its own: its rows stay in
`board_materials` behind the Laminate tab (settled with the user, Oct 2026). Only `um` was missing.
Adds `um` (nullable). Downgrade drops the column.

Revision ID: 0075
Revises: 0074
Create Date: 2026-10-16
"""
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE board_materials ADD COLUMN um varchar(32);")


def downgrade():
    op.execute("ALTER TABLE board_materials DROP COLUMN IF EXISTS um;")

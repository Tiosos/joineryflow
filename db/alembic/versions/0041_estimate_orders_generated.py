"""estimate_revision.orders_generated_at + estimate_line.included_at_convert
— PO generation from a won quote

Adds a nullable `orders_generated_at` timestamptz to `estimate_revision`.
Guards `POST /revisions/{rid}/generate-orders` to run at most once per
revision — the revision is already locked by the time it's WON, so its line
breakdown is frozen and there is no legitimate reason to regenerate orders
from it.

Also adds `estimate_line.included_at_convert boolean NOT NULL DEFAULT false`,
set by `convert_to_project()` for exactly the lines a PM selected at Convert
time (Q490's `include_line_ids`). Without it, `generate_orders()` /
`order_preview()` had no way to tell which lines actually became Joinery
Items, so their default (no `include_line_ids` given) fell back to every
line in the revision — including ones the PM deliberately excluded from the
project, generating a purchase order for materials no item in the project
needs. Post-convert, the default now reads this column instead.

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-28
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE estimate_revision
      ADD COLUMN IF NOT EXISTS orders_generated_at timestamptz;

    ALTER TABLE estimate_line
      ADD COLUMN IF NOT EXISTS included_at_convert boolean NOT NULL DEFAULT false;
    """)


def downgrade():
    op.execute("""
    ALTER TABLE estimate_line DROP COLUMN IF EXISTS included_at_convert;
    ALTER TABLE estimate_revision DROP COLUMN IF EXISTS orders_generated_at;
    """)

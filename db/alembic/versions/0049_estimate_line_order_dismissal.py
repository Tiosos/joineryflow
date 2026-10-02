"""estimate_line order dismissal — mark a quote line "ordered by hand"

A line the Generate Orders run holds back (a material with no supplier) keeps the quote's
"N lines not yet ordered" bar and the Generate Orders button until a supplier is linked.
That is the right signal while the line is still to be ordered, but there was no way out for
a line the PM ordered outside the system: nothing in the tree could say "this one is done".

`orders_generated_at` cannot carry it — that column means "a Generate Orders run made POs
for this line", and `0048`'s backfill and the `estimate.generate_orders` audit rows read it as
exactly that. So a dismissal gets its own columns: when, by whom, and why. The reason is
required (nothing in the system proves the order happened, so the note is the only trail).
A dismissal is reversible: clearing the three columns makes the line orderable again, which
cannot double-order anything because the system never ordered it.

A line is either covered by a run or dismissed, never both — a CHECK, not a convention.

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-02
"""
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE estimate_line
      ADD COLUMN IF NOT EXISTS orders_dismissed_at     timestamptz,
      ADD COLUMN IF NOT EXISTS orders_dismissed_by     bigint REFERENCES app_user(id) ON DELETE SET NULL,
      ADD COLUMN IF NOT EXISTS orders_dismissed_reason text;

    -- The three travel together: a dismissal has a time and a reason, or none of them.
    -- (`by` is nullable on its own so that deleting the user does not break the row.)
    ALTER TABLE estimate_line
      ADD CONSTRAINT ck_estimate_line_dismissal_complete
      CHECK ((orders_dismissed_at IS NULL) = (orders_dismissed_reason IS NULL)),
      ADD CONSTRAINT ck_estimate_line_dismissal_reason_len
      CHECK (orders_dismissed_reason IS NULL
             OR char_length(btrim(orders_dismissed_reason)) BETWEEN 1 AND 500),
      ADD CONSTRAINT ck_estimate_line_covered_xor_dismissed
      CHECK (orders_dismissed_at IS NULL OR orders_generated_at IS NULL);
    """)


def downgrade():
    op.execute("""
    ALTER TABLE estimate_line
      DROP CONSTRAINT IF EXISTS ck_estimate_line_covered_xor_dismissed,
      DROP CONSTRAINT IF EXISTS ck_estimate_line_dismissal_reason_len,
      DROP CONSTRAINT IF EXISTS ck_estimate_line_dismissal_complete,
      DROP COLUMN IF EXISTS orders_dismissed_reason,
      DROP COLUMN IF EXISTS orders_dismissed_by,
      DROP COLUMN IF EXISTS orders_dismissed_at;
    """)

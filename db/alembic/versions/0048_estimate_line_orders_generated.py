"""estimate_line.orders_generated_at — generate the rest of a won quote's orders later

`0041` guarded `POST /revisions/{rid}/generate-orders` with one flag on the
revision, so it could run once. That is fine while every run covers every line,
but it makes a *partial* run a one-way trap: tick two of five lines and the other
three could never be generated afterwards, only ordered by hand.

This moves the guard down to the line. `estimate_line.orders_generated_at` is set,
once, on every line a run covered, and a run refuses a line that already has it
(`409 LINES_ALREADY_GENERATED`). `estimate_revision.orders_generated_at` stays
but means "the most recent run", not "a run happened"; nothing reads it as a guard.

Backfill: a revision that already ran covered the lines named in its
`estimate.generate_orders` audit row (`payload.included_line_ids`); where there is
no audit row (a row written some other way) it covered the lines included at
Convert, which is what a run with no `include_line_ids` selects. Each such line
takes the revision's timestamp.

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-02
"""
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE estimate_line
      ADD COLUMN IF NOT EXISTS orders_generated_at timestamptz;

    UPDATE estimate_line l
       SET orders_generated_at = r.orders_generated_at
      FROM estimate_revision r
     WHERE l.revision_id = r.revision_id
       AND r.orders_generated_at IS NOT NULL
       AND l.orders_generated_at IS NULL
       AND (
            l.line_id IN (
                SELECT x::bigint
                  FROM audit_log a,
                       jsonb_array_elements_text(a.payload -> 'included_line_ids') x
                 WHERE a.event = 'estimate.generate_orders'
                   AND a.target = r.revision_id::text
            )
            OR (
                l.included_at_convert
                AND NOT EXISTS (
                    SELECT 1 FROM audit_log a
                     WHERE a.event = 'estimate.generate_orders'
                       AND a.target = r.revision_id::text
                )
            )
       );
    """)


def downgrade():
    op.execute("""
    ALTER TABLE estimate_line DROP COLUMN IF EXISTS orders_generated_at;
    """)

"""per-material order coverage — one row per (quote line, material) already ordered or dismissed

Until now coverage was per quote LINE (`estimate_line.orders_generated_at`, `0048`;
`orders_dismissed_*`, `0049`), so a line was ordered whole or held back whole: a line with a
board that has a supplier and a hinge that has none could order neither. This table tracks the
state of each material on a line instead.

A row exists only for a material that has been **ordered by a Generate Orders run**
(`orders_generated_at`) or **marked ordered by hand** (`orders_dismissed_*`, with a required
reason); no row means the material is still pending. The same CHECKs as on the line apply: the
dismissal columns travel together, the reason is 1-500 characters, and a material is never both
ordered and dismissed.

`estimate_line.orders_generated_at` / `orders_dismissed_*` are kept and are now **derived**: for a
line that references catalog materials they are written from this table whenever it changes (set
when no material is pending). They stay the source of truth for a line that references none (a
labour-only line has nothing to order).

Back-fill (the line's state is copied to each of its materials, the user's choice): a line already
covered gets every distinct material it references marked generated with the line's timestamp; a
dismissed line gets every one dismissed with the line's time, user and reason.

The downgrade drops the table; the line columns keep the line-level state, so a per-material
distinction made after this migration is lost.

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-03
"""
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE estimate_line_material_order (
      line_id                 bigint NOT NULL REFERENCES estimate_line(line_id) ON DELETE CASCADE,
      material_type           text   NOT NULL,
      material_id             bigint NOT NULL,
      orders_generated_at     timestamptz,
      orders_dismissed_at     timestamptz,
      orders_dismissed_by     bigint REFERENCES app_user(id) ON DELETE SET NULL,
      orders_dismissed_reason text,
      PRIMARY KEY (line_id, material_type, material_id),
      CONSTRAINT ck_elmo_exactly_one_state
        CHECK ((orders_generated_at IS NULL) <> (orders_dismissed_at IS NULL)),
      CONSTRAINT ck_elmo_dismissal_complete
        CHECK ((orders_dismissed_at IS NULL) = (orders_dismissed_reason IS NULL)),
      CONSTRAINT ck_elmo_dismissal_reason_len
        CHECK (orders_dismissed_reason IS NULL
               OR char_length(btrim(orders_dismissed_reason)) BETWEEN 1 AND 500)
    );

    WITH m AS (
      SELECT line_id, material_type, material_id
        FROM estimate_line_part WHERE material_id IS NOT NULL
      UNION
      SELECT line_id, material_type, material_id
        FROM estimate_line_hardware WHERE material_id IS NOT NULL
    )
    INSERT INTO estimate_line_material_order
           (line_id, material_type, material_id, orders_generated_at)
    SELECT l.line_id, m.material_type, m.material_id, l.orders_generated_at
      FROM estimate_line l JOIN m USING (line_id)
     WHERE l.orders_generated_at IS NOT NULL;

    WITH m AS (
      SELECT line_id, material_type, material_id
        FROM estimate_line_part WHERE material_id IS NOT NULL
      UNION
      SELECT line_id, material_type, material_id
        FROM estimate_line_hardware WHERE material_id IS NOT NULL
    )
    INSERT INTO estimate_line_material_order
           (line_id, material_type, material_id,
            orders_dismissed_at, orders_dismissed_by, orders_dismissed_reason)
    SELECT l.line_id, m.material_type, m.material_id,
           l.orders_dismissed_at, l.orders_dismissed_by, l.orders_dismissed_reason
      FROM estimate_line l JOIN m USING (line_id)
     WHERE l.orders_dismissed_at IS NOT NULL;
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS estimate_line_material_order;")

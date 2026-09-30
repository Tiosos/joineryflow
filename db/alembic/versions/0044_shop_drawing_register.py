"""shop drawing register fields (Tg Register redesign)

Additive only. The four revision statuses, the workflow and every existing
column are untouched; a drawing gains the register columns the redesigned
Shop Dwgs page shows:

  drawing_no    per-project register number, ``{project_code}-{seq:03d}``
                (allocated from ``workspace_counter`` name ``sd:{project_id}``,
                never MAX+1). Nullable on purpose: the seed and many test
                fixtures INSERT drawings with raw SQL, and the API allocates
                the number on create. UNIQUE per project (NULLs are distinct).
  type          IFA | IFC (issued for approval / issued for construction)
  level, joinery_id, zone, room_no   free text. ``joinery_id`` is text, not an
                FK: drawings are still not linked to items.
  assigned_to   FK app_user, workspace-validated by the API
  due_date, submitted_at   dates (submitted = sent to the builder)

Existing drawings are numbered in drawing_id order per project and each
project's counter is advanced past them.

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-30
"""
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    ALTER TABLE shop_drawing
      ADD COLUMN drawing_no   text,
      ADD COLUMN type         text NOT NULL DEFAULT 'IFA'
                              CHECK (type IN ('IFA', 'IFC')),
      ADD COLUMN level        text,
      ADD COLUMN joinery_id   text,
      ADD COLUMN zone         text,
      ADD COLUMN room_no      text,
      ADD COLUMN assigned_to  bigint REFERENCES app_user(id),
      ADD COLUMN due_date     date,
      ADD COLUMN submitted_at date;

    CREATE UNIQUE INDEX uniq_shop_drawing_no
      ON shop_drawing (project_id, drawing_no);
    CREATE INDEX idx_shop_drawing_assigned
      ON shop_drawing (assigned_to) WHERE assigned_to IS NOT NULL;

    -- Number what already exists, per project, oldest first.
    UPDATE shop_drawing d SET drawing_no = n.code
      FROM (SELECT d2.drawing_id,
                   p.project_code || '-' ||
                   lpad((row_number() OVER (PARTITION BY d2.project_id
                                            ORDER BY d2.drawing_id))::text, 3, '0') AS code
              FROM shop_drawing d2 JOIN projects p ON p.project_id = d2.project_id) n
     WHERE d.drawing_id = n.drawing_id;

    -- Advance each project's counter past the numbers just handed out.
    INSERT INTO workspace_counter (workspace_id, name, next_value)
    SELECT p.workspace_id, 'sd:' || d.project_id, COUNT(*) + 1
      FROM shop_drawing d JOIN projects p ON p.project_id = d.project_id
     GROUP BY p.workspace_id, d.project_id
    ON CONFLICT (workspace_id, name) DO UPDATE SET next_value = EXCLUDED.next_value;
    """)


def downgrade():
    op.execute(r"""
    DELETE FROM workspace_counter WHERE name LIKE 'sd:%';
    DROP INDEX IF EXISTS idx_shop_drawing_assigned;
    DROP INDEX IF EXISTS uniq_shop_drawing_no;
    ALTER TABLE shop_drawing
      DROP COLUMN submitted_at, DROP COLUMN due_date, DROP COLUMN assigned_to,
      DROP COLUMN room_no, DROP COLUMN zone, DROP COLUMN joinery_id,
      DROP COLUMN level, DROP COLUMN type, DROP COLUMN drawing_no;
    """)

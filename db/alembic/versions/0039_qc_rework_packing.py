"""QC module, Rework, Packing stage (Plan V1 §26-28, Q515-519)

Adds:
- `qc_defect` — a QC finding against a Joinery Item, optionally tagged with
  the stage_key whose work is being checked (§26: "QC checks the work just
  completed"). Two states only (open/resolved) — resolving is the qc:approve
  action, raising/editing is qc:write.
- `qc_checklist_item` — a per-item QC checklist line (Q515's "checklists";
  §2's "QC checklist" is duplicable configuration, but item duplication
  itself is not built anywhere in this tree yet, so there is nothing to wire
  that into today).
- `rework` — one entity with a `kind` CHECK ('internal','full') rather than
  two entity types (Q516). Records cause/scope/cost/responsibility per
  plan_v1.md's own list of what must be captured. Never reopens a completed
  stage (Q517) — it is a parallel record, not a workflow transition.
- `stages` gains a PACKING row (sort_order 85, between MADE=80 and DEL=90) —
  the first addition to the 10-stage list since Q459 (Q519). Widens the
  `worker_assignment` / `stage_completion_log` CHECKs from 0020 so Packing
  is assignable through Shop Floor like the five stages before it.
- Backfills `group_module_grant` for the new `qc` RBAC module (the 12th,
  Q515) across every existing workspace's 7 system groups — the 0037
  backfill was a one-time snapshot of MATRIX at that migration's authoring
  time, so a module added after it does not reach existing memberships
  without an explicit grant insert here (`rbac_engine.seed_system_groups`
  covers a workspace created after this migration).

`qc_defect` / `qc_checklist_item` / `rework` are Joinery-Items-only (the
`item_documents` precedent) and workspace-isolated through
`items -> projects.workspace_id`, so no direct `workspace_id` column.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-27
"""
from alembic import op


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS qc_defect (
        defect_id     BIGSERIAL PRIMARY KEY,
        item_id       BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
        stage_key     VARCHAR(16) REFERENCES stages(stage_key),
        description   TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
        resolved_note TEXT,
        resolved_by   BIGINT REFERENCES app_user(id),
        resolved_at   TIMESTAMPTZ,
        created_by    BIGINT NOT NULL REFERENCES app_user(id),
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_qc_defect_item ON qc_defect (item_id);
    CREATE INDEX IF NOT EXISTS idx_qc_defect_open ON qc_defect (item_id) WHERE status = 'open';

    CREATE TABLE IF NOT EXISTS qc_checklist_item (
        checklist_item_id BIGSERIAL PRIMARY KEY,
        item_id           BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
        label             TEXT NOT NULL,
        is_checked        BOOLEAN NOT NULL DEFAULT false,
        checked_by        BIGINT REFERENCES app_user(id),
        checked_at        TIMESTAMPTZ,
        sort_order        SMALLINT NOT NULL DEFAULT 0,
        created_by        BIGINT NOT NULL REFERENCES app_user(id),
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_qc_checklist_item_item ON qc_checklist_item (item_id, sort_order);

    CREATE TABLE IF NOT EXISTS rework (
        rework_id      BIGSERIAL PRIMARY KEY,
        item_id        BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
        kind           TEXT NOT NULL CHECK (kind IN ('internal', 'full')),
        cause          TEXT NOT NULL,
        scope          TEXT NOT NULL,
        responsibility TEXT,
        cost           NUMERIC(12, 2),
        status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
        closed_note    TEXT,
        closed_by      BIGINT REFERENCES app_user(id),
        closed_at      TIMESTAMPTZ,
        created_by     BIGINT NOT NULL REFERENCES app_user(id),
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_rework_item ON rework (item_id);
    CREATE INDEX IF NOT EXISTS idx_rework_open ON rework (item_id) WHERE status = 'open';

    -- Packing: the first new lifecycle stage since the original 10 (Q519).
    INSERT INTO stages (stage_key, label, sort_order)
    VALUES ('PACKING', 'Packed', 85)
    ON CONFLICT (stage_key) DO NOTHING;

    ALTER TABLE worker_assignment
        DROP CONSTRAINT IF EXISTS worker_assignment_stage_key_check;
    ALTER TABLE worker_assignment
        ADD CONSTRAINT worker_assignment_stage_key_check
        CHECK (stage_key IN ('DOWN', 'CNC', 'EDGED', 'PAINTED', 'MADE', 'PACKING'));

    ALTER TABLE stage_completion_log
        DROP CONSTRAINT IF EXISTS stage_completion_log_stage_key_check;
    ALTER TABLE stage_completion_log
        ADD CONSTRAINT stage_completion_log_stage_key_check
        CHECK (stage_key IN ('DOWN', 'CNC', 'EDGED', 'PAINTED', 'MADE', 'PACKING'));

    -- Grants for the new qc module, added only to the existing system
    -- groups' rows (the 0037 backfill already created the groups
    -- themselves; this does not touch any other module's grants).
    INSERT INTO group_module_grant (group_id, module, action)
    SELECT g.group_id, m.module, m.action
    FROM permission_group g
    JOIN (VALUES
        ('admin', 'qc', 'read'),
        ('admin', 'qc', 'write'),
        ('admin', 'qc', 'approve'),
        ('admin', 'qc', 'comment'),
        ('manager', 'qc', 'read'),
        ('manager', 'qc', 'write'),
        ('manager', 'qc', 'approve'),
        ('manager', 'qc', 'comment'),
        ('editor', 'qc', 'read'),
        ('editor', 'qc', 'write'),
        ('editor', 'qc', 'comment'),
        ('drafter', 'qc', 'read'),
        ('drafter', 'qc', 'comment'),
        ('estimator', 'qc', 'read'),
        ('purchase_officer', 'qc', 'read'),
        ('viewer', 'qc', 'read')
    ) AS m(role, module, action) ON m.role = g.name
    WHERE g.is_system = true
    ON CONFLICT DO NOTHING;
    """)


def downgrade():
    op.execute("""
    DELETE FROM group_module_grant WHERE module = 'qc';

    ALTER TABLE stage_completion_log
        DROP CONSTRAINT IF EXISTS stage_completion_log_stage_key_check;
    ALTER TABLE stage_completion_log
        ADD CONSTRAINT stage_completion_log_stage_key_check
        CHECK (stage_key IN ('DOWN', 'CNC', 'EDGED', 'PAINTED', 'MADE'));

    ALTER TABLE worker_assignment
        DROP CONSTRAINT IF EXISTS worker_assignment_stage_key_check;
    ALTER TABLE worker_assignment
        ADD CONSTRAINT worker_assignment_stage_key_check
        CHECK (stage_key IN ('DOWN', 'CNC', 'EDGED', 'PAINTED', 'MADE'));

    -- A PACKING row already referenced by worker_assignment/stage_completion_log
    -- (now impossible per the CHECK above) or item_stages would block this;
    -- in practice downgrade only runs against a database this migration's
    -- own upgrade() created, so no row exists yet.
    DELETE FROM stages WHERE stage_key = 'PACKING';

    DROP TABLE IF EXISTS rework;
    DROP TABLE IF EXISTS qc_checklist_item;
    DROP TABLE IF EXISTS qc_defect;
    """)

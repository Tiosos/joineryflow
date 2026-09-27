"""tender lifecycle + contract value + variations (Plan V1 §5-6, §16-17, Q487-494/548-549)

Adds:
- Widens `estimate_revision.status` from the 6-value quoting-only enum to
  the 12-stage tender lifecycle of Plan V1 §5 (11 sequential stages +
  WON/LOST/WITHDRAWN as the 3 possible resolutions of the 12th, terminal
  position). Existing rows are migrated onto it (Q435 data-preserving):
  draft -> QUOTE_PREPARED, sent -> SUBMITTED, accepted -> WON,
  rejected -> LOST, expired -> LOST (Q548), withdrawn -> WITHDRAWN.
  `draft` is deliberately landed at QUOTE_PREPARED rather than the pipeline
  start: an in-flight quote already did the opportunity/review/pricing work
  the new early stages describe, and restarting it at stage 1 would make it
  walk stages that, in substance, already happened.
- Replaces the partial unique index `uniq_estimate_draft` (status='draft')
  with `uniq_estimate_unlocked` (`locked_at IS NULL`) — the same invariant
  ("at most one revision per estimate not yet sent to the client") expressed
  against `locked_at`, which generalises across all 10 pre-Submitted stages
  instead of naming just one of them.
- `project_contract` (one row per project, immutable once set — §17) +
  `project_contract_variation` (append-only; current value is
  original_value + SUM(amount_delta), computed on read, never stored, so
  there is nowhere for it to drift out of sync — Q491).

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-27
"""
from alembic import op


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    -- Drop the old (6-value) constraint first so the remap below can write
    -- the new stage names before the new (14-value) constraint exists to
    -- reject them.
    ALTER TABLE estimate_revision DROP CONSTRAINT IF EXISTS estimate_revision_status_check;

    UPDATE estimate_revision SET status = CASE status
        WHEN 'draft'     THEN 'QUOTE_PREPARED'
        WHEN 'sent'      THEN 'SUBMITTED'
        WHEN 'accepted'  THEN 'WON'
        WHEN 'rejected'  THEN 'LOST'
        WHEN 'expired'   THEN 'LOST'
        WHEN 'withdrawn' THEN 'WITHDRAWN'
    END
    WHERE status IN ('draft','sent','accepted','rejected','expired','withdrawn');

    -- A row that reached SUBMITTED or a terminal state should already carry
    -- locked_at (transition_revision sets it when target='sent') — but any
    -- row written outside that path (raw SQL, a fixture) may not. The new
    -- unique index below is keyed on locked_at IS NULL, so an un-backfilled
    -- locked row here would collide with a genuinely-unlocked sibling
    -- revision on the same estimate. Best available timestamp, falling back
    -- to created_at so this can never fail to produce one.
    UPDATE estimate_revision
       SET locked_at = COALESCE(locked_at, sent_at, accepted_at, rejected_at, created_at)
     WHERE status IN ('SUBMITTED', 'WON', 'LOST', 'WITHDRAWN')
       AND locked_at IS NULL;

    ALTER TABLE estimate_revision ADD CONSTRAINT estimate_revision_status_check
        CHECK (status IN (
            'OPPORTUNITY', 'INITIAL_REVIEW', 'GO_NO_GO', 'INFO_REQUESTED',
            'DOCS_RECEIVED', 'ESTIMATING', 'SUPPLIER_PRICING', 'INTERNAL_REVIEW',
            'QUOTE_PREPARED', 'MGMT_APPROVAL', 'SUBMITTED',
            'WON', 'LOST', 'WITHDRAWN'
        ));

    DROP INDEX IF EXISTS uniq_estimate_draft;
    CREATE UNIQUE INDEX uniq_estimate_unlocked
        ON estimate_revision (estimate_id)
        WHERE locked_at IS NULL;

    CREATE TABLE IF NOT EXISTS project_contract (
        project_id     BIGINT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
        original_value NUMERIC(14,2) NOT NULL,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by     BIGINT REFERENCES app_user(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS project_contract_variation (
        variation_id  BIGSERIAL PRIMARY KEY,
        project_id    BIGINT NOT NULL REFERENCES project_contract(project_id) ON DELETE CASCADE,
        description   TEXT NOT NULL,
        amount_delta  NUMERIC(14,2) NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by    BIGINT REFERENCES app_user(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_contract_variation_project
        ON project_contract_variation (project_id, created_at);
    """)


def downgrade():
    op.execute("""
    DROP TABLE IF EXISTS project_contract_variation;
    DROP TABLE IF EXISTS project_contract;

    DROP INDEX IF EXISTS uniq_estimate_unlocked;

    -- Drop the 14-value constraint before writing the old 6-value names back,
    -- for the same reason upgrade() drops the 6-value one first.
    ALTER TABLE estimate_revision DROP CONSTRAINT IF EXISTS estimate_revision_status_check;

    UPDATE estimate_revision SET status = CASE
        WHEN status IN ('OPPORTUNITY','INITIAL_REVIEW','GO_NO_GO','INFO_REQUESTED',
                         'DOCS_RECEIVED','ESTIMATING','SUPPLIER_PRICING',
                         'INTERNAL_REVIEW','QUOTE_PREPARED') THEN 'draft'
        WHEN status IN ('MGMT_APPROVAL','SUBMITTED') THEN 'sent'
        WHEN status = 'WON' THEN 'accepted'
        WHEN status = 'LOST' THEN 'rejected'
        WHEN status = 'WITHDRAWN' THEN 'withdrawn'
    END;

    ALTER TABLE estimate_revision ADD CONSTRAINT estimate_revision_status_check
        CHECK (status IN ('draft','sent','accepted','rejected','expired','withdrawn'));

    CREATE UNIQUE INDEX uniq_estimate_draft
        ON estimate_revision (estimate_id)
        WHERE status = 'draft';
    """)

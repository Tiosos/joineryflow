"""Approval states for contract variations (Q608).

A variation is a Draft until a manager or admin approves or rejects it; only Approved variations count
toward the contract's current value. Every variation that exists today was decided when it was saved,
so it becomes Approved, decided by whoever added it at that moment. `status` has no default afterwards:
a writer that forgets it fails instead of silently counting (or not counting) money.

Revision ID: 0086
Revises: 0085
"""
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE project_contract_variation
            ADD COLUMN status        text NOT NULL DEFAULT 'Approved'
                CONSTRAINT ck_variation_status CHECK (status IN ('Draft', 'Approved', 'Rejected')),
            ADD COLUMN decided_by    bigint REFERENCES app_user(id) ON DELETE SET NULL,
            ADD COLUMN decided_at    timestamptz,
            ADD COLUMN decision_note text;

        UPDATE project_contract_variation SET decided_by = created_by, decided_at = created_at;

        ALTER TABLE project_contract_variation ALTER COLUMN status DROP DEFAULT;

        ALTER TABLE project_contract_variation
            ADD CONSTRAINT ck_variation_decision CHECK (
                (status = 'Draft'    AND decided_at IS NULL AND decision_note IS NULL)
             OR (status = 'Approved' AND decided_at IS NOT NULL)
             OR (status = 'Rejected' AND decided_at IS NOT NULL AND btrim(coalesce(decision_note, '')) <> '')
            );
    """)


def downgrade():
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM project_contract_variation WHERE status <> 'Approved') THEN
                RAISE EXCEPTION '0086 downgrade refused: Draft or Rejected variations exist (they would start counting toward contract values)';
            END IF;
        END $$;
        ALTER TABLE project_contract_variation
            DROP CONSTRAINT ck_variation_decision,
            DROP COLUMN decision_note,
            DROP COLUMN decided_at,
            DROP COLUMN decided_by,
            DROP COLUMN status;
    """)

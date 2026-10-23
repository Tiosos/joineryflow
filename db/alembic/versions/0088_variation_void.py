"""Void for contract variations (Q610).

A manager or admin voids an Approved variation with a reason: the row, its amount and its approval stay,
but it stops counting toward the contract's current value. `Voided` is a fourth status, with its own
who / when / why columns so the original decision is kept.

Revision ID: 0088
Revises: 0087
"""
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE project_contract_variation
            DROP CONSTRAINT ck_variation_status,
            DROP CONSTRAINT ck_variation_decision,
            ADD COLUMN voided_by   bigint REFERENCES app_user(id) ON DELETE SET NULL,
            ADD COLUMN voided_at   timestamptz,
            ADD COLUMN void_reason text;

        ALTER TABLE project_contract_variation
            ADD CONSTRAINT ck_variation_status CHECK (status IN ('Draft', 'Approved', 'Rejected', 'Voided')),
            ADD CONSTRAINT ck_variation_decision CHECK (
                (status = 'Draft'    AND decided_at IS NULL AND decision_note IS NULL)
             OR (status = 'Approved' AND decided_at IS NOT NULL)
             OR (status = 'Rejected' AND decided_at IS NOT NULL AND btrim(coalesce(decision_note, '')) <> '')
             OR (status = 'Voided'   AND decided_at IS NOT NULL)
            ),
            ADD CONSTRAINT ck_variation_void CHECK (
                CASE WHEN status = 'Voided'
                     THEN voided_at IS NOT NULL AND btrim(coalesce(void_reason, '')) <> ''
                     ELSE voided_by IS NULL AND voided_at IS NULL AND void_reason IS NULL END
            );
    """)


def downgrade():
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM project_contract_variation WHERE status = 'Voided') THEN
                RAISE EXCEPTION '0088 downgrade refused: voided variations exist (they would start counting again or lose their status)';
            END IF;
        END $$;
        ALTER TABLE project_contract_variation
            DROP CONSTRAINT ck_variation_void,
            DROP CONSTRAINT ck_variation_decision,
            DROP CONSTRAINT ck_variation_status,
            DROP COLUMN void_reason,
            DROP COLUMN voided_at,
            DROP COLUMN voided_by;
        ALTER TABLE project_contract_variation
            ADD CONSTRAINT ck_variation_status CHECK (status IN ('Draft', 'Approved', 'Rejected')),
            ADD CONSTRAINT ck_variation_decision CHECK (
                (status = 'Draft'    AND decided_at IS NULL AND decision_note IS NULL)
             OR (status = 'Approved' AND decided_at IS NOT NULL)
             OR (status = 'Rejected' AND decided_at IS NOT NULL AND btrim(coalesce(decision_note, '')) <> '')
            );
    """)

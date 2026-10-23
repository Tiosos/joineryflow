"""More fields on a contract variation (Q611, Q612).

A per-project variation number, a reason, who asked and when, a cost impact beside the selling-price
impact, and a time impact in working days. `amount_delta` stays as it is and is now the selling-price
impact (Q612): the contract's current value is still the original value plus the approved ones.
Existing variations are numbered by creation order within their project; their other new fields are empty
(`requested_on` too: nobody recorded when it was asked). `number` has no default, so a writer that forgets
it fails instead of colliding.

Revision ID: 0089
Revises: 0088
"""
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE project_contract_variation
            ADD COLUMN number           integer,
            ADD COLUMN reason           text,
            ADD COLUMN requester        varchar(255),
            ADD COLUMN requested_on     date,
            ADD COLUMN cost_impact      numeric(14,2),
            ADD COLUMN time_impact_days integer;

        UPDATE project_contract_variation v
           SET number = n.rn
          FROM (SELECT variation_id,
                       row_number() OVER (PARTITION BY project_id ORDER BY created_at, variation_id) AS rn
                  FROM project_contract_variation) n
         WHERE n.variation_id = v.variation_id;

        ALTER TABLE project_contract_variation
            ALTER COLUMN number SET NOT NULL,
            ADD CONSTRAINT uq_variation_number UNIQUE (project_id, number),
            ADD CONSTRAINT ck_variation_number CHECK (number >= 1),
            ADD CONSTRAINT ck_variation_time_impact CHECK (time_impact_days BETWEEN -36500 AND 36500);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE project_contract_variation
            DROP CONSTRAINT ck_variation_time_impact,
            DROP CONSTRAINT ck_variation_number,
            DROP CONSTRAINT uq_variation_number,
            DROP COLUMN time_impact_days,
            DROP COLUMN cost_impact,
            DROP COLUMN requested_on,
            DROP COLUMN requester,
            DROP COLUMN reason,
            DROP COLUMN number;
    """)

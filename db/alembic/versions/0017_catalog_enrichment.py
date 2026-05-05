"""catalog enrichment + cv_material_mapping — sub-project #7a

Adds:
- synonyms text[] + default_supplier + default_lead_time_days +
  archived_at + archived_by on all 6 catalog tables.
- GIN index on synonyms; partial active-row index (workspace_id) WHERE archived_at IS NULL.
- cv_material_mapping (workspace, cv_code) UNIQUE register.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-05
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


CATALOG_TABLES = (
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
)


def upgrade():
    for tbl in CATALOG_TABLES:
        op.execute(f"""
        ALTER TABLE {tbl}
          ADD COLUMN synonyms               text[]      NOT NULL DEFAULT '{{}}',
          ADD COLUMN default_supplier       varchar(128),
          ADD COLUMN default_lead_time_days int,
          ADD COLUMN archived_at            timestamptz,
          ADD COLUMN archived_by            bigint REFERENCES app_user(id);
        """)
        op.execute(f"CREATE INDEX idx_{tbl}_synonyms ON {tbl} USING gin (synonyms);")
        op.execute(
            f"CREATE INDEX idx_{tbl}_active ON {tbl} (workspace_id) "
            f"WHERE archived_at IS NULL;"
        )

    op.execute(r"""
    CREATE TABLE cv_material_mapping (
      cv_material_mapping_id bigserial    PRIMARY KEY,
      workspace_id           bigint       NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
      cv_code                varchar(255) NOT NULL,
      target_material_table  text         NOT NULL CHECK (target_material_table IN
        ('board_materials','hardware_materials','custom_made',
         'benchtop_materials','appliances','equipment_hire')),
      target_material_id     bigint       NOT NULL,
      notes                  text,
      created_by             bigint       NOT NULL REFERENCES app_user(id),
      created_at             timestamptz  NOT NULL DEFAULT now(),
      updated_at             timestamptz  NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, cv_code)
    );
    CREATE INDEX idx_cv_material_mapping_target
      ON cv_material_mapping (target_material_table, target_material_id);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; recover via 0001-0016 only")

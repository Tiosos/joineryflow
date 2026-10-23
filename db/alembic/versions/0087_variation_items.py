"""Optional links from a contract variation to Joinery Items (Q609).

A variation with no rows here is a project-level variation. The link table only says which items a
variation touches; it changes no money. Rows go with their variation or item (cascade); a soft-deleted
item is hidden by the readers, not unlinked, so a restore brings the link back.

Revision ID: 0087
Revises: 0086
"""
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE project_contract_variation_item (
            variation_id bigint NOT NULL REFERENCES project_contract_variation(variation_id) ON DELETE CASCADE,
            item_id      bigint NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
            PRIMARY KEY (variation_id, item_id)
        );
        CREATE INDEX ix_variation_item_item ON project_contract_variation_item(item_id);
    """)


def downgrade():
    op.execute("DROP TABLE project_contract_variation_item")

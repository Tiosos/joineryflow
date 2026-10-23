"""A project's folder link (Q640).

One plain link per project to wherever its files live (a SharePoint folder today), shown on the
project page and in Tracking's Info pop-up. Nullable: no project has one yet. The API accepts a
web link only; the CHECK states the same so a link that is not one never reaches the page.

Revision ID: 0084
Revises: 0083
"""
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
        ALTER TABLE projects
        ADD COLUMN project_folder_url text
        CONSTRAINT ck_projects_folder_url
        CHECK (project_folder_url IS NULL
               OR (length(project_folder_url) <= 2048 AND project_folder_url ~* '^https?://[^\s/]'));
    """)


def downgrade():
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM projects WHERE project_folder_url IS NOT NULL) THEN
                RAISE EXCEPTION '0084 downgrade refused: project folder links exist';
            END IF;
        END $$;
        ALTER TABLE projects DROP COLUMN project_folder_url;
    """)

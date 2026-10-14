"""Keep the last rendered quote PDF per revision

Rendering a quote with WeasyPrint takes about 6 s for 300 lines and 12 s for 800 (a straight line, all
page layout). The PDF is a pure function of the HTML the template produces, so the cache is keyed on
the SHA-256 of that HTML: a changed line, status, customer or date gives a different key and a fresh
render; the same content gives the stored bytes. One row per revision, the newest content only.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-14
"""
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quote_pdf_cache (
            revision_id  bigint PRIMARY KEY REFERENCES estimate_revision(revision_id) ON DELETE CASCADE,
            html_sha256  text    NOT NULL,
            pdf          bytea   NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE quote_pdf_cache")

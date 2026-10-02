"""po_attachments.file_blob_id: legacy PO attachments move to the shared file store

The legacy ``/procurement/orders/{id}/attachments`` route wrote each upload to
``./uploads/<po>/…`` — a path relative to the api process's working directory,
so inside the container's own layer rather than the mounted ``uploads`` volume,
and nothing could read it back. New uploads now go through the same
``FileStore`` / ``file_blob`` subsystem every other upload uses (sha256-deduped,
workspace-scoped, on the volume) and the row points at the blob.

The column is nullable and ``file_path`` stays: rows written before this
migration keep their path and are served from it for as long as the file still
exists (it often will not — that is the bug). Nothing is backfilled; reading the
filesystem inside a migration would be fragile and untestable.

No ``ON DELETE`` action: a ``file_blob`` row is never deleted anywhere in this
app (no orphan GC), so removing an attachment deletes the row and leaves the blob.

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-02
"""
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE po_attachments ADD COLUMN file_blob_id bigint REFERENCES file_blob(file_blob_id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE po_attachments DROP COLUMN file_blob_id")

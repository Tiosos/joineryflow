"""The two steps of storing an upload that two requests can race on.

Identical bytes uploaded at the same moment both miss the dedup SELECT, both write the same key,
and both INSERT; the loser hits UNIQUE (workspace_id, sha256). It must adopt the winner's row and
must not delete the bytes (same key) the winner committed.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from .store import FileStore


def insert_blob_or_existing(
    db: Session, *, workspace_id: int, sha256: str, mime: str, byte_size: int,
    original_filename: str, storage_key: str, uploaded_by: int,
) -> tuple[int, bool]:
    """`(file_blob_id, created)`. `created` is False when a concurrent request committed the same
    (workspace, sha256) first: that row is returned and nothing is inserted."""
    row = db.execute(
        text(
            """
            INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename,
                                  storage_key, uploaded_by)
            VALUES (:w, :s, :m, :sz, :n, :k, :u)
            ON CONFLICT (workspace_id, sha256) DO NOTHING
            RETURNING file_blob_id
            """
        ),
        {"w": workspace_id, "s": sha256, "m": mime, "sz": byte_size, "n": original_filename,
         "k": storage_key, "u": uploaded_by},
    ).first()
    if row is not None:
        return int(row[0]), True
    existing = db.execute(
        text("SELECT file_blob_id FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
        {"w": workspace_id, "s": sha256},
    ).scalar_one()
    return int(existing), False


def discard_bytes_if_unreferenced(db: Session, store: FileStore, storage_key: str) -> None:
    """After a failed upload: delete the bytes this request wrote, unless a `file_blob` row (the
    winner of a race, or an earlier upload of the same file) points at that key."""
    if db.execute(text("SELECT 1 FROM file_blob WHERE storage_key = :k LIMIT 1"), {"k": storage_key}).first() is None:
        store.delete(storage_key)

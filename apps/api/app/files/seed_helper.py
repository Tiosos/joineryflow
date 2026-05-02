"""Direct (no-HTTP) helper used by seed scripts.

Mirrors the dedup + storage path logic of the upload route, but skips
multipart parsing and audit (seed runs are bulk + idempotent).
"""
import hashlib
import io
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from .store import get_default_store
from .validators import sniff_mime


def put_seed_file(
    db: Session, *, workspace_id: int, workspace_slug: str, app_user_id: int, path: str | Path
) -> int:
    p = Path(path)
    payload = p.read_bytes()
    mime = sniff_mime(payload[:16])
    if mime is None:
        raise ValueError(f"unknown file type for {p}")
    sha = hashlib.sha256(payload).hexdigest()

    existing = db.execute(
        text("SELECT file_blob_id FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
        {"w": workspace_id, "s": sha},
    ).first()
    if existing:
        return existing[0]

    store = get_default_store()
    storage_key = store.put(workspace_slug, sha, io.BytesIO(payload))
    new_id = db.execute(
        text(
            """
            INSERT INTO file_blob(workspace_id, sha256, mime, byte_size,
                                  original_filename, storage_key, uploaded_by)
            VALUES (:w, :s, :m, :sz, :n, :k, :u) RETURNING file_blob_id
            """
        ),
        {"w": workspace_id, "s": sha, "m": mime, "sz": len(payload),
         "n": p.name, "k": storage_key, "u": app_user_id},
    ).scalar()
    return new_id

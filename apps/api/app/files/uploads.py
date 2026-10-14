"""Reading an upload into the shared file store, for routes that attach a file to their own row.

Same contract as `POST /files` and the order attachments: 25 MB cap, content sniffed and agreeing
with the extension, sha256-deduped per workspace (`files/blobs.py` for the race). `allowed` narrows
the mime types a given box takes. The caller commits, and on failure rolls back and calls
`discard(...)` so bytes this request wrote are not left behind.
"""
import hashlib
import io
import urllib.parse
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.sessions import AuthUser
from .blobs import discard_bytes_if_unreferenced, insert_blob_or_existing
from .store import FileStore
from .validators import MAX_BYTE_SIZE, sniff_mime, validate_extension_matches

PDF = frozenset({"application/pdf"})
IMAGE = frozenset({"image/png", "image/jpeg"})
PDF_OR_IMAGE = PDF | IMAGE


@dataclass
class Stored:
    blob_id: int
    file_name: str
    size: int
    written_key: str | None  # set only when this request wrote bytes


async def store_upload(
    db: Session, store: FileStore, *, user: AuthUser, file: UploadFile, allowed: frozenset[str] | None = None,
) -> Stored:
    name = (file.filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_BYTE_SIZE:
            raise HTTPException(413, f"file size exceeds {MAX_BYTE_SIZE} bytes")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(400, "empty file")
    payload = b"".join(chunks)
    mime = sniff_mime(payload[:16], name)
    if mime is None:
        raise HTTPException(415, "unsupported file type (magic-byte sniff failed)")
    if not validate_extension_matches(name, mime):
        raise HTTPException(415, f"filename extension does not match content type {mime}")
    if allowed is not None and mime not in allowed:
        raise HTTPException(415, "this box does not take that file type")
    return store_bytes(db, store, user=user, payload=payload, name=name, mime=mime)


def store_bytes(
    db: Session, store: FileStore, *, user: AuthUser, payload: bytes, name: str, mime: str,
) -> Stored:
    """Put already-validated bytes in the store (also used for a PDF the server rendered)."""
    sha = hashlib.sha256(payload).hexdigest()
    blob_id = db.execute(
        text("SELECT file_blob_id FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
        {"w": user.workspace_id, "s": sha},
    ).scalar()
    key: str | None = None
    if blob_id is None:
        slug = db.execute(text("SELECT slug FROM workspace WHERE id = :w"), {"w": user.workspace_id}).scalar_one()
        key = store.put(slug, sha, io.BytesIO(payload))
        blob_id, created = insert_blob_or_existing(
            db, workspace_id=user.workspace_id, sha256=sha, mime=mime, byte_size=len(payload),
            original_filename=name, storage_key=key, uploaded_by=user.id,
        )
        if created:
            write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="file_blob.create",
                        target=str(blob_id), payload={"sha256": sha, "byte_size": len(payload), "mime": mime,
                                                      "original_filename": name})
    return Stored(int(blob_id), name, len(payload), key)


def discard(db: Session, store: FileStore, stored: Stored | None) -> None:
    if stored is not None and stored.written_key is not None:
        discard_bytes_if_unreferenced(db, store, stored.written_key)


def stream_blob(db: Session, store: FileStore, *, workspace_id: int, blob_id: int) -> StreamingResponse:
    """Serve a stored file; 404 when it is another workspace's or its bytes are gone."""
    row = db.execute(
        text("SELECT original_filename, mime, byte_size, storage_key FROM file_blob"
             " WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": blob_id, "w": workspace_id},
    ).mappings().first()
    if not row or not store.exists(row["storage_key"]):
        raise HTTPException(404, "file not found")
    raw = row["original_filename"] or "file"
    ascii_name = raw.encode("ascii", errors="replace").decode("ascii").replace('"', "_")
    return StreamingResponse(
        store.get(row["storage_key"]),
        media_type=row["mime"],
        headers={
            "Content-Length": str(row["byte_size"]),
            "Content-Disposition": f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(raw, safe='')}",
            "Cache-Control": "private, max-age=300",
        },
    )

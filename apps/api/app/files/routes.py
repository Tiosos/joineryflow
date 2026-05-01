"""POST /files (upload) + GET /files/{id} (stream).

Upload contract:
  multipart/form-data with one `file` field.
  Returns 201 + FileBlobOut. dedup-aware: identical bytes in the same
  workspace return the existing file_blob_id with deduped=true.

The download route is implemented in Task 6.
"""
import hashlib
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .schemas import FileBlobOut
from .store import FileStore, get_default_store
from .validators import MAX_BYTE_SIZE, sniff_mime, validate_extension_matches

router = APIRouter(prefix="/files", tags=["files"])


def _get_store() -> FileStore:
    return get_default_store()


def _workspace_slug(db: Session, workspace_id: int) -> str:
    row = db.execute(
        text("SELECT slug FROM workspace WHERE id = :w"),
        {"w": workspace_id},
    ).first()
    if not row:
        raise HTTPException(status_code=500, detail="workspace missing for current user")
    return row[0]


@router.post("", response_model=FileBlobOut, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    # Read into memory once. We need the full bytes for sha256 + size enforcement
    # + magic-byte sniff. 25 MB cap is enforced by counting bytes as we read.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTE_SIZE:
            raise HTTPException(status_code=413, detail=f"file size exceeds {MAX_BYTE_SIZE} bytes")
        chunks.append(chunk)
    payload = b"".join(chunks)
    if total == 0:
        raise HTTPException(status_code=400, detail="empty file")

    sniffed = sniff_mime(payload[:16])
    if sniffed is None:
        raise HTTPException(status_code=415, detail="unsupported file type (magic-byte sniff failed)")
    if not validate_extension_matches(file.filename or "", sniffed):
        raise HTTPException(status_code=415, detail=f"filename extension does not match content type {sniffed}")

    sha = hashlib.sha256(payload).hexdigest()

    # Dedup check.
    existing = db.execute(
        text("SELECT file_blob_id FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
        {"w": user.workspace_id, "s": sha},
    ).first()
    if existing:
        write_audit(
            db,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event="file_blob.dedup",
            target=str(existing[0]),
            payload={"sha256": sha, "byte_size": total, "original_filename": file.filename},
        )
        db.commit()
        return FileBlobOut(
            file_blob_id=existing[0],
            sha256=sha,
            mime=sniffed,
            byte_size=total,
            original_filename=file.filename or "",
            deduped=True,
        )

    # Persist bytes, then DB row. If DB insert fails, delete the disk file.
    slug = _workspace_slug(db, user.workspace_id)
    storage_key = store.put(slug, sha, io.BytesIO(payload))
    try:
        new_id = db.execute(
            text(
                """
                INSERT INTO file_blob(workspace_id, sha256, mime, byte_size,
                                      original_filename, storage_key, uploaded_by)
                VALUES (:w, :s, :m, :sz, :n, :k, :u)
                RETURNING file_blob_id
                """
            ),
            {
                "w": user.workspace_id, "s": sha, "m": sniffed, "sz": total,
                "n": file.filename or "", "k": storage_key, "u": user.id,
            },
        ).scalar()
        write_audit(
            db,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event="file_blob.create",
            target=str(new_id),
            payload={"sha256": sha, "byte_size": total, "mime": sniffed,
                     "original_filename": file.filename},
        )
        db.commit()
    except Exception:
        store.delete(storage_key)
        db.rollback()
        raise

    return FileBlobOut(
        file_blob_id=new_id,
        sha256=sha,
        mime=sniffed,
        byte_size=total,
        original_filename=file.filename or "",
        deduped=False,
    )


@router.get("/{file_blob_id}")
def download_file(
    file_blob_id: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    row = db.execute(
        text(
            """
            SELECT file_blob_id, workspace_id, mime, byte_size,
                   original_filename, storage_key
              FROM file_blob
             WHERE file_blob_id = :id
            """
        ),
        {"id": file_blob_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    if row["workspace_id"] != user.workspace_id:
        # Don't leak existence across workspaces.
        raise HTTPException(status_code=404, detail="file not found")

    fh = store.get(row["storage_key"])
    safe_name = (row["original_filename"] or "file").replace('"', "_")
    headers = {
        "Content-Length": str(row["byte_size"]),
        "Content-Disposition": f'inline; filename="{safe_name}"',
        "Cache-Control": "private, max-age=300",
    }
    return StreamingResponse(fh, media_type=row["mime"], headers=headers)

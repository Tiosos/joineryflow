"""Order attachments: the FILE and PDF boxes of the order pop-up.

`po_attachments` rows bound to the shared file store (`file_blob`, migration 0047). The legacy
`/procurement/*` upload route is retired; these routes are gated by `orderbook` (the Orderbook's
people do not hold `shop_dwgs:write`, which `POST /files` needs). Same upload contract as
`POST /files`: 25 MB, content sniffed and agreeing with the extension, sha256 dedup per workspace.
The PDF box takes PDF only. A Cancelled / Delivered order is read-only (its files can be
downloaded, not changed), like its other fields.
"""
import hashlib
import io
import urllib.parse
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..files.blobs import discard_bytes_if_unreferenced, insert_blob_or_existing
from ..files.store import FileStore, get_default_store
from ..files.validators import MAX_BYTE_SIZE, sniff_mime, validate_extension_matches
from . import queries as q

router = APIRouter(tags=["order-attachments"])

AttachmentKind = Literal["File", "PDF"]


class AttachmentOut(BaseModel):
    attachment_id: int
    po_id: int
    attachment_type: str
    file_name: str
    file_size_bytes: int | None
    uploaded_by_name: str | None
    uploaded_at: str | None


class AttachmentListOut(BaseModel):
    attachments: list[AttachmentOut]


def _get_store() -> FileStore:
    return get_default_store()


_COLS = """a.attachment_id, a.po_id, a.attachment_type, a.file_name, a.file_size_bytes,
           u.full_name AS uploaded_by_name, a.uploaded_at::text AS uploaded_at"""


def _order_exists(db: Session, po_id: int, workspace_id: int) -> bool:
    return db.execute(
        text(f"SELECT 1 FROM purchase_orders po WHERE po.po_id = :o AND {q._ORDER_WORKSPACE}"),
        {"o": po_id, "w": workspace_id},
    ).first() is not None


def _list(db: Session, po_id: int) -> list[dict]:
    rows = db.execute(
        text(f"SELECT {_COLS} FROM po_attachments a LEFT JOIN app_user u ON u.id = a.uploaded_by"
             " WHERE a.po_id = :o AND a.file_blob_id IS NOT NULL ORDER BY a.attachment_id"),
        {"o": po_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _locked(e: q.OrderLocked) -> HTTPException:
    return HTTPException(409, {"code": "ORDER_LOCKED", "status": e.status})


@router.get("/orders/{po_id}/attachments", response_model=AttachmentListOut)
def list_attachments(
    po_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    if not _order_exists(db, po_id, user.workspace_id):
        raise HTTPException(404, "order not found")
    return {"attachments": _list(db, po_id)}


@router.post("/orders/{po_id}/attachments", response_model=AttachmentListOut, status_code=201)
async def upload_attachment(
    po_id: int,
    file: UploadFile = File(...),
    attachment_type: AttachmentKind = Form("File"),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    if not _order_exists(db, po_id, user.workspace_id):
        raise HTTPException(404, "order not found")
    name = (file.filename or "attachment").replace("\\", "/").rsplit("/", 1)[-1]
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
    if attachment_type == "PDF" and mime != "application/pdf":
        raise HTTPException(415, "the PDF box takes a PDF")

    try:
        if not q._lock_order_for_update(db, po_id=po_id, workspace_id=user.workspace_id):
            raise HTTPException(404, "order not found")
    except q.OrderLocked as e:
        db.rollback()
        raise _locked(e) from e

    sha = hashlib.sha256(payload).hexdigest()
    blob_id = db.execute(
        text("SELECT file_blob_id FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
        {"w": user.workspace_id, "s": sha},
    ).scalar()
    storage_key: str | None = None  # set only when this request wrote bytes
    try:
        if blob_id is None:
            slug = db.execute(text("SELECT slug FROM workspace WHERE id = :w"), {"w": user.workspace_id}).scalar_one()
            storage_key = store.put(slug, sha, io.BytesIO(payload))
            blob_id, created = insert_blob_or_existing(
                db, workspace_id=user.workspace_id, sha256=sha, mime=mime, byte_size=size,
                original_filename=name, storage_key=storage_key, uploaded_by=user.id,
            )
            if created:
                write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="file_blob.create",
                            target=str(blob_id), payload={"sha256": sha, "byte_size": size, "mime": mime,
                                                          "original_filename": name})
        aid = db.execute(
            text("INSERT INTO po_attachments (po_id, attachment_type, file_name, file_size_bytes, file_blob_id,"
                 " uploaded_by) VALUES (:o, :t, :n, :sz, :b, :u) RETURNING attachment_id"),
            {"o": po_id, "t": attachment_type, "n": name, "sz": size, "b": blob_id, "u": user.id},
        ).scalar()
        write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="order.attachment.add",
                    target=f"order:{po_id}", payload={"attachment_id": aid, "type": attachment_type, "file_name": name})
        db.commit()
    except Exception:
        db.rollback()
        if storage_key is not None:
            discard_bytes_if_unreferenced(db, store, storage_key)
        raise
    return {"attachments": _list(db, po_id)}


@router.get("/orders/{po_id}/attachments/{attachment_id}/download")
def download_attachment(
    po_id: int,
    attachment_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    if not _order_exists(db, po_id, user.workspace_id):
        raise HTTPException(404, "attachment not found")
    row = db.execute(
        text("SELECT a.file_name, b.mime, b.byte_size, b.storage_key FROM po_attachments a"
             " JOIN file_blob b ON b.file_blob_id = a.file_blob_id AND b.workspace_id = :w"
             " WHERE a.attachment_id = :a AND a.po_id = :o"),
        {"a": attachment_id, "o": po_id, "w": user.workspace_id},
    ).mappings().first()
    if not row or not store.exists(row["storage_key"]):
        raise HTTPException(404, "attachment not found")
    raw = row["file_name"] or "file"
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


@router.delete("/orders/{po_id}/attachments/{attachment_id}", response_model=AttachmentListOut)
def delete_attachment(
    po_id: int,
    attachment_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    try:
        if not q._lock_order_for_update(db, po_id=po_id, workspace_id=user.workspace_id):
            raise HTTPException(404, "attachment not found")
    except q.OrderLocked as e:
        db.rollback()
        raise _locked(e) from e
    found = db.execute(
        text("DELETE FROM po_attachments WHERE attachment_id = :a AND po_id = :o RETURNING file_name"),
        {"a": attachment_id, "o": po_id},
    ).first()
    if not found:
        db.rollback()
        raise HTTPException(404, "attachment not found")
    write_audit(db, workspace_id=user.workspace_id, actor_id=user.id, event="order.attachment.remove",
                target=f"order:{po_id}", payload={"attachment_id": attachment_id, "file_name": found[0]})
    db.commit()
    return {"attachments": _list(db, po_id)}

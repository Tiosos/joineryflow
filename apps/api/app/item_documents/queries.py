"""Item Document Register query layer.

Routes own the transaction boundary (db.commit). Queries flush only.
Every mutation writes audit_log and item_edit_log in the caller's transaction.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log
from ..row_types import joinery_items_only

# Like the named attachment slots, the register belongs to Joinery Items only.
_JOINERY_ITEM = joinery_items_only("i")

ALLOWED_MIMES = ("application/pdf", "image/png", "image/jpeg")

_DOC_COLS = """
    d.document_id, d.item_id, d.file_blob_id, d.label, d.sort_order,
    d.uploaded_by, u.full_name AS uploaded_by_name, d.uploaded_at,
    fb.original_filename, fb.byte_size, fb.mime AS mime_type
"""

_DOC_JOINS = """
    JOIN file_blob fb ON fb.file_blob_id = d.file_blob_id
    LEFT JOIN app_user u ON u.id = d.uploaded_by
"""


class NotFound(Exception):
    pass


class UnsupportedMime(Exception):
    pass


def _item_in_workspace(db: Session, *, item_id: int, workspace_id: int) -> bool:
    return db.execute(
        text(
            f"""
            SELECT 1 FROM items i
              JOIN projects p ON p.project_id = i.project_id
             WHERE i.item_id = :i AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).first() is not None


def _document(db: Session, *, document_id: int, workspace_id: int) -> dict:
    row = db.execute(
        text(
            f"""
            SELECT {_DOC_COLS}
              FROM item_document d
              {_DOC_JOINS}
              JOIN items i ON i.item_id = d.item_id
              JOIN projects p ON p.project_id = i.project_id
             WHERE d.document_id = :d AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"d": document_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        raise NotFound("document not found")
    return dict(row)


def _log(db: Session, *, workspace_id: int, actor_id: int, item_id: int,
         event: str, payload: dict, field: str,
         old: str | None, new: str | None) -> None:
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event=event,
                target=str(item_id), payload=payload)
    write_edit_log(db, item_id=item_id, actor_id=actor_id, field=field,
                   old_value=old, new_value=new)


def list_documents(db: Session, *, item_id: int, workspace_id: int) -> list[dict]:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    rows = db.execute(
        text(
            f"""
            SELECT {_DOC_COLS}
              FROM item_document d
              {_DOC_JOINS}
             WHERE d.item_id = :i
             ORDER BY d.sort_order, d.uploaded_at, d.document_id
            """
        ),
        {"i": item_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def bind_document(
    db: Session,
    *,
    item_id: int,
    file_blob_id: int,
    label: str | None,
    sort_order: int,
    workspace_id: int,
    actor_id: int,
) -> dict:
    if not _item_in_workspace(db, item_id=item_id, workspace_id=workspace_id):
        raise NotFound("item not found")
    blob = db.execute(
        text("SELECT mime, original_filename FROM file_blob"
             " WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": file_blob_id, "w": workspace_id},
    ).first()
    if blob is None:
        raise NotFound("file_blob not found")
    if blob[0] not in ALLOWED_MIMES:
        raise UnsupportedMime("document register accepts PDF, PNG or JPEG only")

    did = db.execute(
        text(
            """
            INSERT INTO item_document(item_id, file_blob_id, label, sort_order, uploaded_by)
            VALUES (:i, :b, :l, :s, :u)
            RETURNING document_id
            """
        ),
        {"i": item_id, "b": file_blob_id, "l": label, "s": sort_order, "u": actor_id},
    ).scalar()
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=item_id,
         event="item.document.bind",
         payload={"document_id": did, "file_blob_id": file_blob_id},
         field="_document_bind", old=None, new=label or blob[1])
    db.flush()
    return _document(db, document_id=did, workspace_id=workspace_id)


def patch_document(
    db: Session,
    *,
    document_id: int,
    changes: dict,
    workspace_id: int,
    actor_id: int,
) -> dict:
    current = _document(db, document_id=document_id, workspace_id=workspace_id)
    diff = {k: v for k, v in changes.items() if current[k] != v}
    if not diff:
        return current

    sets = ", ".join(f"{k} = :{k}" for k in diff)
    db.execute(
        text(f"UPDATE item_document SET {sets} WHERE document_id = :d"),
        {**diff, "d": document_id},
    )
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id,
                event="item.document.update", target=str(current["item_id"]),
                payload={"document_id": document_id,
                         "before": {k: current[k] for k in diff},
                         "after": diff})
    for k, v in diff.items():
        write_edit_log(db, item_id=current["item_id"], actor_id=actor_id,
                       field=f"document.{document_id}.{k}",
                       old_value=None if current[k] is None else str(current[k]),
                       new_value=None if v is None else str(v))
    db.flush()
    return _document(db, document_id=document_id, workspace_id=workspace_id)


def unbind_document(
    db: Session, *, document_id: int, workspace_id: int, actor_id: int
) -> None:
    """Removes the register row. The file_blob itself stays (no orphan GC)."""
    current = _document(db, document_id=document_id, workspace_id=workspace_id)
    db.execute(text("DELETE FROM item_document WHERE document_id = :d"),
               {"d": document_id})
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=current["item_id"],
         event="item.document.unbind",
         payload={"document_id": document_id, "file_blob_id": current["file_blob_id"]},
         field="_document_unbind",
         old=current["label"] or current["original_filename"], new=None)
    db.flush()

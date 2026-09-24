"""Item attachments query layer.

Routes own the transaction boundary (db.commit). Queries flush only.
The PDF-only mime gate and the workspace-match check on file_blob run here so
both routes and seed helpers go through the same enforcement path.
"""
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..row_types import joinery_items_only

# The three attachment slots (CV drawing / floor plan / site measure) are
# cutlist documents. A related part has no cutlist (Plan V1 Q417).
_JOINERY_ITEM = joinery_items_only("i")

AttachmentKind = Literal["cv_drawing", "floor_plan", "site_measure"]
ALL_KINDS: tuple[AttachmentKind, ...] = ("cv_drawing", "floor_plan", "site_measure")


def bind_attachment(
    db: Session,
    *,
    item_id: int,
    kind: AttachmentKind,
    file_blob_id: int,
    workspace_id: int,
    actor_id: int,
) -> dict:
    """UPSERT a slot. Validates blob is PDF + workspace-match. Writes audit."""
    owns = db.execute(
        text(
            f"""
            SELECT 1 FROM items i
              JOIN projects p ON p.project_id = i.project_id
             WHERE i.item_id = :i AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).first()
    if not owns:
        raise ValueError("item not found in this workspace")

    blob = db.execute(
        text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": file_blob_id, "w": workspace_id},
    ).first()
    if not blob:
        raise ValueError("file_blob not found in this workspace")
    if blob[0] != "application/pdf":
        raise ValueError("item attachments must be application/pdf")

    prior = db.execute(
        text("SELECT file_blob_id FROM item_attachment WHERE item_id = :i AND kind = :k"),
        {"i": item_id, "k": kind},
    ).scalar()

    db.execute(
        text(
            """
            INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
            VALUES (:i, :k, :b, :u)
            ON CONFLICT (item_id, kind) DO UPDATE
              SET file_blob_id = EXCLUDED.file_blob_id,
                  uploaded_by  = EXCLUDED.uploaded_by,
                  uploaded_at  = now()
            """
        ),
        {"i": item_id, "k": kind, "b": file_blob_id, "u": actor_id},
    )

    audit_payload = {"file_blob_id": file_blob_id}
    if prior is not None and prior != file_blob_id:
        audit_payload["replaced_file_blob_id"] = prior

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="item_attachment.bind", target=f"{item_id}:{kind}",
        payload=audit_payload,
    )
    db.flush()
    return {"item_id": item_id, "kind": kind, "file_blob_id": file_blob_id}


def clear_attachment(
    db: Session,
    *,
    item_id: int,
    kind: AttachmentKind,
    workspace_id: int,
    actor_id: int,
) -> bool:
    """Remove a slot. Returns True if removed, False if not present OR cross-workspace."""
    row = db.execute(
        text(
            f"""
            DELETE FROM item_attachment
             WHERE item_id = :i AND kind = :k
               AND item_id IN (
                 SELECT i.item_id
                   FROM items i
                   JOIN projects p ON p.project_id = i.project_id
                  WHERE p.workspace_id = :w
                    AND {_JOINERY_ITEM}
               )
             RETURNING file_blob_id
            """
        ),
        {"i": item_id, "k": kind, "w": workspace_id},
    ).first()
    if not row:
        return False
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="item_attachment.clear", target=f"{item_id}:{kind}",
        payload={"file_blob_id": row[0]},
    )
    db.flush()
    return True


def get_bundle(db: Session, *, item_id: int, workspace_id: int) -> dict | None:
    """Return all 3 slots in canonical order, populated or null.

    Returns None if the item doesn't exist or belongs to a different workspace
    (so the route can return 404 — don't leak existence).
    """
    # Workspace ownership check first
    owns = db.execute(
        text(
            f"""
            SELECT 1
              FROM items i
              JOIN projects p ON p.project_id = i.project_id
             WHERE i.item_id = :i AND p.workspace_id = :w
               AND {_JOINERY_ITEM}
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).first()
    if not owns:
        return None

    rows = db.execute(
        text(
            """
            SELECT ia.kind, ia.file_blob_id, ia.uploaded_by, ia.uploaded_at,
                   fb.original_filename, fb.byte_size,
                   u.full_name AS uploaded_by_name
              FROM item_attachment ia
              JOIN file_blob fb ON fb.file_blob_id = ia.file_blob_id
              LEFT JOIN app_user u ON u.id = ia.uploaded_by
             WHERE ia.item_id = :i
            """
        ),
        {"i": item_id},
    ).mappings().all()
    by_kind = {r["kind"]: dict(r) for r in rows}

    slots: list[dict] = []
    for kind in ALL_KINDS:
        if kind in by_kind:
            slots.append(by_kind[kind])
        else:
            slots.append({
                "kind": kind, "file_blob_id": None, "original_filename": None,
                "byte_size": None, "uploaded_by": None, "uploaded_by_name": None,
                "uploaded_at": None,
            })
    return {"item_id": item_id, "slots": slots}

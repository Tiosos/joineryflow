"""Samples query layer.

Routes own the transaction boundary (db.commit). Queries flush only.
Workspace isolation enforced via projects.workspace_id direct join (post-hardening).
The PNG/JPEG-only photo gate runs in routes.py (analogous to #5b's PDF-only gate).
"""
from datetime import datetime
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from .schemas import CreateSampleIn, PatchSampleIn

Subtab = Literal["board", "archive"]


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def list_samples(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    subtab: Subtab,
    q: str | None = None,
    status_filter: str | None = None,
    supplier: str | None = None,
) -> dict:
    """Return list + total + counts. Returns None if project not in workspace."""
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None  # type: ignore[return-value]

    if subtab == "board":
        subtab_where = "s.archived_at IS NULL AND s.status IN ('pending', 'approved')"
    elif subtab == "archive":
        subtab_where = "(s.archived_at IS NOT NULL OR s.status = 'rejected')"
    else:
        raise ValueError(f"unknown subtab: {subtab}")

    extra_where: list[str] = []
    params: dict = {"p": project_id, "w": workspace_id}
    if q:
        extra_where.append("s.title ILIKE :q")
        params["q"] = f"%{q}%"
    if status_filter and status_filter in ("pending", "approved", "rejected"):
        extra_where.append("s.status = :sf")
        params["sf"] = status_filter
    if supplier:
        extra_where.append("s.supplier = :sup")
        params["sup"] = supplier
    extra = (" AND " + " AND ".join(extra_where)) if extra_where else ""

    sql = f"""
        SELECT s.sample_id, s.project_id, p.project_code, s.title, s.room,
               s.hex_swatch, s.supplier, s.status, s.review_note,
               s.reviewed_by, ur.full_name AS reviewed_by_name, s.reviewed_at,
               s.photo_file_blob_id, fb.original_filename AS photo_filename,
               s.archived_at, s.archived_by,
               s.created_by, uc.full_name AS created_by_name,
               s.created_at, s.updated_at
          FROM sample s
          JOIN projects p ON p.project_id = s.project_id
          LEFT JOIN app_user ur ON ur.id = s.reviewed_by
          LEFT JOIN app_user uc ON uc.id = s.created_by
          LEFT JOIN file_blob fb ON fb.file_blob_id = s.photo_file_blob_id
         WHERE s.project_id = :p
           AND p.workspace_id = :w
           AND {subtab_where}
           {extra}
         ORDER BY s.sample_id DESC
    """
    rows = db.execute(text(sql), params).mappings().all()

    counts_row = db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE status='pending'  AND archived_at IS NULL) AS pending,
          COUNT(*) FILTER (WHERE status='approved' AND archived_at IS NULL) AS approved,
          COUNT(*) FILTER (WHERE status='rejected' OR  archived_at IS NOT NULL) AS rejected_or_archived,
          COUNT(*) AS total
          FROM sample
         WHERE project_id = :p
    """), {"p": project_id}).mappings().first()

    return {
        "samples": [dict(r) for r in rows],
        "total": counts_row["total"] if counts_row else 0,
        "counts": {
            "pending": counts_row["pending"] if counts_row else 0,
            "approved": counts_row["approved"] if counts_row else 0,
            "rejected": counts_row["rejected_or_archived"] if counts_row else 0,
        },
    }


def get_sample(db: Session, *, sample_id: int, workspace_id: int) -> dict | None:
    row = db.execute(text("""
        SELECT s.sample_id, s.project_id, p.project_code, s.title, s.room,
               s.hex_swatch, s.supplier, s.status, s.review_note,
               s.reviewed_by, ur.full_name AS reviewed_by_name, s.reviewed_at,
               s.photo_file_blob_id, fb.original_filename AS photo_filename,
               s.archived_at, s.archived_by,
               s.created_by, uc.full_name AS created_by_name,
               s.created_at, s.updated_at
          FROM sample s
          JOIN projects p ON p.project_id = s.project_id
          LEFT JOIN app_user ur ON ur.id = s.reviewed_by
          LEFT JOIN app_user uc ON uc.id = s.created_by
          LEFT JOIN file_blob fb ON fb.file_blob_id = s.photo_file_blob_id
         WHERE s.sample_id = :s
           AND p.workspace_id = :w
    """), {"s": sample_id, "w": workspace_id}).mappings().first()
    return dict(row) if row else None


def create_sample(
    db: Session, *, project_id: int, workspace_id: int, payload: CreateSampleIn, actor_id: int
) -> int:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        raise ValueError("project not found in workspace")

    if payload.photo_file_blob_id is not None:
        blob = db.execute(
            text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
            {"b": payload.photo_file_blob_id, "w": workspace_id},
        ).first()
        if not blob:
            raise ValueError("photo file_blob not found in this workspace")
        if blob[0] not in ("image/png", "image/jpeg"):
            raise ValueError("sample photos must be PNG or JPEG")

    new_id = db.execute(text("""
        INSERT INTO sample(project_id, title, room, hex_swatch, supplier,
                           photo_file_blob_id, created_by)
        VALUES (:p, :t, :r, :h, :sup, :ph, :u) RETURNING sample_id
    """), {
        "p": project_id, "t": payload.title, "r": payload.room,
        "h": payload.hex_swatch, "sup": payload.supplier,
        "ph": payload.photo_file_blob_id, "u": actor_id,
    }).scalar()

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="sample.create", target=str(new_id),
        payload={
            "title": payload.title, "room": payload.room,
            "hex_swatch": payload.hex_swatch, "supplier": payload.supplier,
            "status": "pending",
            **({"photo_file_blob_id": payload.photo_file_blob_id} if payload.photo_file_blob_id else {}),
        },
    )
    db.flush()
    return new_id


def patch_sample(
    db: Session, *, sample_id: int, workspace_id: int, payload: PatchSampleIn, actor_id: int
) -> dict | None:
    """Edit fields. Caller-rule (creator OR manager+) is enforced in the route handler."""
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return get_sample(db, sample_id=sample_id, workspace_id=workspace_id)

    cur = get_sample(db, sample_id=sample_id, workspace_id=workspace_id)
    if not cur:
        return None

    set_clauses = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "s": sample_id}
    db.execute(text(f"UPDATE sample SET {set_clauses}, updated_at = now() WHERE sample_id = :s"), params)
    for k, v in fields.items():
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="sample.update", target=str(sample_id),
            payload={"field": k, "value": v},
        )
    db.flush()
    return get_sample(db, sample_id=sample_id, workspace_id=workspace_id)


def transition_status(
    db: Session, *, sample_id: int, workspace_id: int, action: Literal["approve", "reject"],
    actor_id: int, review_note: str | None = None,
) -> dict | None:
    """Apply a workflow transition. Returns updated sample or None if not found.

    Caller-rule (not creator) enforced in route handler.
    """
    cur = get_sample(db, sample_id=sample_id, workspace_id=workspace_id)
    if not cur:
        return None
    if cur["status"] != "pending":
        raise ValueError(f"cannot {action} from {cur['status']}")

    if action == "approve":
        new_status = "approved"
    elif action == "reject":
        if not review_note:
            raise ValueError("review_note required for reject")
        new_status = "rejected"
    else:
        raise ValueError(f"unknown action: {action}")

    db.execute(text("""
        UPDATE sample
           SET status = :s,
               reviewed_by = :u,
               reviewed_at = now(),
               review_note = :n,
               updated_at = now()
         WHERE sample_id = :sid
    """), {"s": new_status, "u": actor_id, "n": review_note, "sid": sample_id})

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event=f"sample.{action}", target=str(sample_id),
        payload={"reviewed_by": actor_id, **({"review_note": review_note} if review_note else {})},
    )
    db.flush()
    return get_sample(db, sample_id=sample_id, workspace_id=workspace_id)


def archive_sample(
    db: Session, *, sample_id: int, workspace_id: int, actor_id: int
) -> bool:
    """Set archived_at + archived_by. Caller-rule enforced in route handler.

    Returns False if sample not in workspace OR already archived.
    """
    cur = get_sample(db, sample_id=sample_id, workspace_id=workspace_id)
    if not cur:
        return False
    if cur["archived_at"] is not None:
        return False  # already archived

    status_at_archive = cur["status"]
    db.execute(text("""
        UPDATE sample SET archived_at = now(), archived_by = :u, updated_at = now()
         WHERE sample_id = :s
    """), {"u": actor_id, "s": sample_id})

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="sample.archive", target=str(sample_id),
        payload={"archived_by": actor_id, "status_at_archive": status_at_archive},
    )
    db.flush()
    return True


def bind_photo(
    db: Session, *, sample_id: int, workspace_id: int, file_blob_id: int, actor_id: int
) -> bool:
    """Bind/replace photo. Validates PNG/JPEG mime + workspace match.

    Returns False if sample not in workspace.
    """
    cur = get_sample(db, sample_id=sample_id, workspace_id=workspace_id)
    if not cur:
        return False

    blob = db.execute(
        text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": file_blob_id, "w": workspace_id},
    ).first()
    if not blob:
        raise ValueError("photo file_blob not found in this workspace")
    if blob[0] not in ("image/png", "image/jpeg"):
        raise ValueError("sample photos must be PNG or JPEG")

    prior = cur["photo_file_blob_id"]
    db.execute(text("""
        UPDATE sample SET photo_file_blob_id = :b, updated_at = now() WHERE sample_id = :s
    """), {"b": file_blob_id, "s": sample_id})

    payload = {"file_blob_id": file_blob_id}
    if prior is not None and prior != file_blob_id:
        payload["replaced_file_blob_id"] = prior

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="sample.upload_photo", target=str(sample_id),
        payload=payload,
    )
    db.flush()
    return True


def clear_photo(
    db: Session, *, sample_id: int, workspace_id: int, actor_id: int
) -> bool:
    """Clear photo. Returns False if sample not in workspace OR no photo bound."""
    cur = get_sample(db, sample_id=sample_id, workspace_id=workspace_id)
    if not cur:
        return False
    if cur["photo_file_blob_id"] is None:
        return False

    prior = cur["photo_file_blob_id"]
    db.execute(text("""
        UPDATE sample SET photo_file_blob_id = NULL, updated_at = now() WHERE sample_id = :s
    """), {"s": sample_id})

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="sample.clear_photo", target=str(sample_id),
        payload={"file_blob_id": prior},
    )
    db.flush()
    return True


def list_ledger(
    db: Session, *, project_id: int, workspace_id: int, limit: int = 50, offset: int = 0
) -> dict | None:
    """Return audit_log rows for entity='sample' on this project's samples.

    Returns None if project not in workspace (so route can 404).
    """
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None

    rows = db.execute(text("""
        SELECT a.id, a.actor_id, u.full_name AS actor_name, a.event,
               a.target AS sample_id, a.payload, a.created_at
          FROM audit_log a
          LEFT JOIN app_user u ON u.id = a.actor_id
         WHERE a.workspace_id = :w
           AND a.event LIKE 'sample.%'
           AND a.target ~ '^[0-9]+$'
           AND CAST(a.target AS bigint) IN (
             SELECT s.sample_id FROM sample s
              WHERE s.project_id = :p
           )
         ORDER BY a.created_at DESC, a.id DESC
         LIMIT :lim OFFSET :off
    """), {"w": workspace_id, "p": project_id, "lim": limit, "off": offset}).mappings().all()

    total = db.execute(text("""
        SELECT COUNT(*) FROM audit_log a
         WHERE a.workspace_id = :w
           AND a.event LIKE 'sample.%'
           AND a.target ~ '^[0-9]+$'
           AND CAST(a.target AS bigint) IN (
             SELECT s.sample_id FROM sample s WHERE s.project_id = :p
           )
    """), {"w": workspace_id, "p": project_id}).scalar()

    return {
        "entries": [
            {
                "id": r["id"], "actor_id": r["actor_id"], "actor_name": r["actor_name"],
                "event": r["event"], "sample_id": int(r["sample_id"]),
                "payload": r["payload"] or {}, "created_at": r["created_at"],
            }
            for r in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }

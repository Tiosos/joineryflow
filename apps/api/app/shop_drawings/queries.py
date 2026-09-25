"""SQL query functions for shop_drawings.

NO db.commit() here — routes own the transaction boundary.
Workspace-scoping clause: drawings are project-scoped; we filter via the
direct projects.workspace_id FK (added in migration 0014). Never reach
through pm_id -> app_user, which read TRUE in every workspace whenever a
project lacked a PM.
"""
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from .schemas import CreateDrawingIn, PatchDrawingIn

Subtab = Literal["current", "in_review", "archive"]


_LATEST_REV_CTE = """
    latest AS (
        SELECT DISTINCT ON (drawing_id)
               drawing_id, revision_id, rev_no, status,
               file_blob_id, uploaded_by, uploaded_at,
               reviewed_by, reviewed_at
          FROM shop_drawing_revision
         ORDER BY drawing_id, rev_no DESC
    )
"""

# /files also stores .skp / .cvj for attachment slots; the viewer renders only these.
DRAWING_MIMES = ("application/pdf", "image/png", "image/jpeg")


def _ensure_project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    """Returns True iff the project exists and belongs to this workspace."""
    row = db.execute(
        text(
            """
            SELECT 1 FROM projects p
             WHERE p.project_id = :p AND p.workspace_id = :w
            """
        ),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def list_drawings_by_subtab(
    db: Session,
    *,
    project_id: int,
    subtab: Subtab,
    room: str | None = None,
    reviewer_id: int | None = None,
    q: str | None = None,
) -> list[dict]:
    """List drawings for a project filtered by subtab + optional facets.

    Note on `reviewer_id`: filters on the **latest** revision's reviewer (via
    the _LATEST_REV_CTE), not the approved revision's reviewer. For the
    `archive` subtab this means a reviewer filter excludes archived drawings
    whose latest revision is unreviewed (e.g. archived-while-pending). The
    UI uses this filter primarily on Current/In-review subtabs.
    """
    extra_where: list[str] = []
    params: dict = {"p": project_id}
    if room:
        extra_where.append("d.room = :room")
        params["room"] = room
    if reviewer_id is not None:
        extra_where.append("l.reviewed_by = :rev")
        params["rev"] = reviewer_id
    if q:
        extra_where.append("d.title ILIKE :q")
        params["q"] = f"%{q}%"
    extra = (" AND " + " AND ".join(extra_where)) if extra_where else ""

    if subtab == "current":
        subtab_where = "d.archived_at IS NULL AND d.current_revision_id IS NOT NULL"
    elif subtab == "in_review":
        subtab_where = "d.archived_at IS NULL AND l.status IN ('draft','pending')"
    elif subtab == "archive":
        subtab_where = "d.archived_at IS NOT NULL"
    else:
        raise ValueError(f"unknown subtab: {subtab}")

    sql = f"""
        WITH {_LATEST_REV_CTE}
        SELECT d.drawing_id,
               d.project_id,
               p.project_code,
               d.title,
               d.room,
               d.archived_at,
               d.current_revision_id,
               l.rev_no       AS latest_rev_no,
               l.status       AS latest_status,
               l.uploaded_at  AS latest_uploaded_at,
               up.full_name   AS latest_uploaded_by_name,
               l.reviewed_at  AS latest_reviewed_at,
               rv.full_name   AS latest_reviewed_by_name,
               l.file_blob_id AS latest_file_blob_id
          FROM shop_drawing d
          JOIN projects p ON p.project_id = d.project_id
          JOIN latest l   ON l.drawing_id = d.drawing_id
          LEFT JOIN app_user up ON up.id = l.uploaded_by
          LEFT JOIN app_user rv ON rv.id = l.reviewed_by
         WHERE d.project_id = :p
           AND {subtab_where}
           {extra}
         ORDER BY d.drawing_id DESC
    """
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def list_summary(db: Session, *, project_id: int, workspace_id: int) -> dict:
    """Header counts: total non-archived, distinct rooms, awaiting review.

    Workspace-scoped via projects.workspace_id, so safe to call independently
    of an outer _ensure_project_in_workspace check.
    """
    row = db.execute(
        text(
            f"""
            WITH {_LATEST_REV_CTE}
            SELECT
              COUNT(*) FILTER (WHERE d.archived_at IS NULL)               AS total,
              COUNT(DISTINCT d.room) FILTER (WHERE d.archived_at IS NULL) AS distinct_rooms,
              COUNT(*) FILTER (WHERE d.archived_at IS NULL AND l.status = 'pending') AS awaiting_review
              FROM shop_drawing d
              JOIN latest l ON l.drawing_id = d.drawing_id
              JOIN projects p ON p.project_id = d.project_id
             WHERE d.project_id = :p AND p.workspace_id = :w
            """
        ),
        {"p": project_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else {"total": 0, "distinct_rooms": 0, "awaiting_review": 0}


def get_drawing_with_revisions(db: Session, *, drawing_id: int, workspace_id: int) -> dict | None:
    drawing = db.execute(
        text(
            """
            SELECT d.drawing_id, d.project_id, p.project_code, d.title, d.room,
                   d.current_revision_id, d.archived_at, d.archived_by,
                   d.created_by, d.created_at
              FROM shop_drawing d
              JOIN projects p ON p.project_id = d.project_id
             WHERE d.drawing_id = :d AND p.workspace_id = :w
            """
        ),
        {"d": drawing_id, "w": workspace_id},
    ).mappings().first()
    if not drawing:
        return None

    revs = db.execute(
        text(
            """
            SELECT r.revision_id, r.rev_no, r.status, r.file_blob_id,
                   fb.mime AS file_mime,
                   r.uploaded_by, up.full_name AS uploaded_by_name, r.uploaded_at,
                   r.reviewed_by, rv.full_name AS reviewed_by_name, r.reviewed_at,
                   r.review_note
              FROM shop_drawing_revision r
              JOIN file_blob fb ON fb.file_blob_id = r.file_blob_id
              LEFT JOIN app_user up ON up.id = r.uploaded_by
              LEFT JOIN app_user rv ON rv.id = r.reviewed_by
             WHERE r.drawing_id = :d
             ORDER BY r.rev_no DESC
            """
        ),
        {"d": drawing_id},
    ).mappings().all()
    return dict(drawing) | {"revisions": [dict(r) for r in revs]}


def create_drawing(
    db: Session, *, workspace_id: int, project_id: int, payload: CreateDrawingIn, actor_id: int
) -> int:
    if not _ensure_project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        raise ValueError("project not found in workspace")
    # Confirm the file_blob belongs to this workspace (cross-workspace blob is rejected).
    blob = db.execute(
        text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": payload.file_blob_id, "w": workspace_id},
    ).first()
    if not blob:
        raise ValueError("file_blob_id not found in this workspace")
    if blob[0] not in DRAWING_MIMES:
        raise ValueError("shop drawings accept PDF, PNG or JPEG only")

    drawing_id = db.execute(
        text(
            """
            INSERT INTO shop_drawing(project_id, title, room, created_by)
            VALUES (:p, :t, :r, :u) RETURNING drawing_id
            """
        ),
        {"p": project_id, "t": payload.title, "r": payload.room, "u": actor_id},
    ).scalar()

    initial_status = "pending" if payload.submit_immediately else "draft"
    rev_id = db.execute(
        text(
            """
            INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
            VALUES (:d, 1, :b, :s, :u) RETURNING revision_id
            """
        ),
        {"d": drawing_id, "b": payload.file_blob_id, "s": initial_status, "u": actor_id},
    ).scalar()

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="shop_drawing.create", target=str(drawing_id),
        payload={"title": payload.title, "room": payload.room,
                 "rev_no": 1, "status": initial_status, "revision_id": rev_id},
    )
    db.flush()
    return drawing_id


def patch_drawing(
    db: Session, *, drawing_id: int, workspace_id: int, payload: PatchDrawingIn,
    actor_id: int, actor_role: str,
) -> dict | None:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)

    drawing = get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)
    if not drawing:
        return None

    # Spec §6.2: only the creator OR manager/admin can edit title/room.
    if drawing["created_by"] != actor_id and actor_role not in ("manager", "admin"):
        raise PermissionError("only the drawing's creator or a manager/admin may edit title/room")

    set_clauses = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "d": drawing_id}
    db.execute(text(f"UPDATE shop_drawing SET {set_clauses} WHERE drawing_id = :d"), params)
    for k, v in fields.items():
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="shop_drawing.update", target=str(drawing_id),
            payload={"field": k, "value": v},
        )
    db.flush()
    return get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)


def archive_drawing(
    db: Session, *, drawing_id: int, workspace_id: int, actor_id: int
) -> bool:
    drawing = get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)
    if not drawing:
        return False
    if drawing["archived_at"] is not None:
        raise ValueError("drawing is already archived")
    db.execute(
        text("UPDATE shop_drawing SET archived_at = now(), archived_by = :u WHERE drawing_id = :d"),
        {"u": actor_id, "d": drawing_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="shop_drawing.archive", target=str(drawing_id), payload={},
    )
    db.flush()
    return True


def add_revision(
    db: Session, *, drawing_id: int, workspace_id: int, file_blob_id: int, actor_id: int
) -> int:
    drawing = get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)
    if not drawing:
        raise ValueError("drawing not found")
    blob = db.execute(
        text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": file_blob_id, "w": workspace_id},
    ).first()
    if not blob:
        raise ValueError("file_blob_id not found in this workspace")
    if blob[0] not in DRAWING_MIMES:
        raise ValueError("shop drawings accept PDF, PNG or JPEG only")

    next_rev = db.execute(
        text("SELECT COALESCE(MAX(rev_no), 0) + 1 FROM shop_drawing_revision WHERE drawing_id = :d"),
        {"d": drawing_id},
    ).scalar()
    rev_id = db.execute(
        text(
            """
            INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
            VALUES (:d, :n, :b, 'draft', :u) RETURNING revision_id
            """
        ),
        {"d": drawing_id, "n": next_rev, "b": file_blob_id, "u": actor_id},
    ).scalar()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="shop_drawing.revision.upload", target=str(drawing_id),
        payload={"revision_id": rev_id, "rev_no": next_rev},
    )
    db.flush()
    return rev_id


def transition_revision(
    db: Session, *, drawing_id: int, revision_id: int, workspace_id: int,
    actor_id: int, action: Literal["submit", "withdraw", "approve", "reject"],
    review_note: str | None = None,
) -> dict | None:
    """Apply a state transition. Returns the updated revision row or None if not found."""
    rev = db.execute(
        text(
            """
            SELECT r.revision_id, r.drawing_id, r.status, r.uploaded_by, r.rev_no
              FROM shop_drawing_revision r
              JOIN shop_drawing d ON d.drawing_id = r.drawing_id
              JOIN projects p ON p.project_id = d.project_id
             WHERE r.revision_id = :r AND r.drawing_id = :d
               AND p.workspace_id = :w
            """
        ),
        {"r": revision_id, "d": drawing_id, "w": workspace_id},
    ).mappings().first()
    if not rev:
        return None

    cur = rev["status"]
    if action == "submit":
        if cur != "draft":
            raise ValueError(f"cannot submit from {cur}")
        new_status, set_review = "pending", False
    elif action == "withdraw":
        if cur != "pending":
            raise ValueError(f"cannot withdraw from {cur}")
        new_status, set_review = "draft", False
    elif action == "approve":
        if cur != "pending":
            raise ValueError(f"cannot approve from {cur}")
        new_status, set_review = "approved", True
    elif action == "reject":
        if cur != "pending":
            raise ValueError(f"cannot reject from {cur}")
        if not review_note:
            raise ValueError("review_note is required for reject")
        new_status, set_review = "rejected", True
    else:
        raise ValueError(f"unknown action: {action}")

    if set_review:
        db.execute(
            text(
                """
                UPDATE shop_drawing_revision
                   SET status = :s, reviewed_by = :u, reviewed_at = now(), review_note = :n
                 WHERE revision_id = :r
                """
            ),
            {"s": new_status, "u": actor_id, "n": review_note, "r": revision_id},
        )
    else:
        db.execute(
            text("UPDATE shop_drawing_revision SET status = :s WHERE revision_id = :r"),
            {"s": new_status, "r": revision_id},
        )

    if action == "approve":
        db.execute(
            text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
            {"r": revision_id, "d": drawing_id},
        )

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event=f"shop_drawing.revision.{action}", target=str(drawing_id),
        payload={"revision_id": revision_id, "rev_no": rev["rev_no"],
                 "status_before": cur, "status_after": new_status,
                 "review_note": review_note},
    )
    db.flush()
    return {"revision_id": revision_id, "status": new_status}

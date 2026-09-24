"""SQL helpers for project_lift_access (1 row per project)."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from .schemas import UpsertLiftAccessIn


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def _blob_in_workspace(db: Session, *, file_blob_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text(
            "SELECT 1 FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"
        ),
        {"b": file_blob_id, "w": workspace_id},
    ).first()
    return row is not None


def get_lift_access(
    db: Session, *, project_id: int, workspace_id: int
) -> dict | None:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None
    row = db.execute(
        text(
            """
            SELECT project_id, notes, sketch_file_blob_id, updated_at, updated_by
              FROM project_lift_access
             WHERE project_id = :pid
            """
        ),
        {"pid": project_id},
    ).mappings().first()
    if row is None:
        return {
            "project_id": project_id,
            "notes": None,
            "sketch_file_blob_id": None,
            "updated_at": None,
            "updated_by": None,
        }
    return dict(row)


def upsert_lift_access(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    payload: UpsertLiftAccessIn,
    actor_id: int,
) -> str | dict:
    """Returns 'NOT_FOUND', 'CROSS_WORKSPACE_BLOB', or the new row dict."""
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return "NOT_FOUND"
    if payload.sketch_file_blob_id is not None and not _blob_in_workspace(
        db, file_blob_id=payload.sketch_file_blob_id, workspace_id=workspace_id
    ):
        return "CROSS_WORKSPACE_BLOB"

    db.execute(
        text(
            """
            INSERT INTO project_lift_access(project_id, notes, sketch_file_blob_id,
                                            updated_by, updated_at)
            VALUES (:pid, :notes, :sb, :ub, now())
            ON CONFLICT (project_id) DO UPDATE
              SET notes               = EXCLUDED.notes,
                  sketch_file_blob_id = EXCLUDED.sketch_file_blob_id,
                  updated_by          = EXCLUDED.updated_by,
                  updated_at          = now()
            """
        ),
        {
            "pid":   project_id,
            "notes": payload.notes,
            "sb":    payload.sketch_file_blob_id,
            "ub":    actor_id,
        },
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="project.lift_access.update",
        target=str(project_id),
        payload={
            "notes_set": payload.notes is not None,
            "sketch_set": payload.sketch_file_blob_id is not None,
        },
    )
    db.flush()
    return get_lift_access(db, project_id=project_id, workspace_id=workspace_id)


def delete_lift_access(
    db: Session, *, project_id: int, workspace_id: int, actor_id: int
) -> bool:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return False
    result = db.execute(
        text("DELETE FROM project_lift_access WHERE project_id = :pid"),
        {"pid": project_id},
    )
    if result.rowcount == 0:
        return False
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="project.lift_access.update",
        target=str(project_id),
        payload={"cleared": True},
    )
    db.flush()
    return True

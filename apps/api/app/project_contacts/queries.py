"""SQL helpers for project_contact CRUD.  Workspace-isolated through projects."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from .schemas import CreateContactIn, PatchContactIn


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def list_contacts(db: Session, *, project_id: int, workspace_id: int) -> list[dict] | None:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None
    rows = db.execute(
        text(
            """
            SELECT contact_id, project_id, kind, position, name, email, mobile,
                   notes, sort_order, created_at, created_by
              FROM project_contact
             WHERE project_id = :pid
             ORDER BY kind, sort_order, contact_id
            """
        ),
        {"pid": project_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_contact(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    payload: CreateContactIn,
    actor_id: int,
) -> dict | None:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None
    row = db.execute(
        text(
            """
            INSERT INTO project_contact(project_id, kind, position, name, email,
                                        mobile, notes, sort_order, created_by)
            VALUES (:pid, :kind, :pos, :name, :email, :mobile, :notes, :so, :cb)
            RETURNING contact_id, project_id, kind, position, name, email, mobile,
                      notes, sort_order, created_at, created_by
            """
        ),
        {
            "pid":    project_id,
            "kind":   payload.kind,
            "pos":    payload.position,
            "name":   payload.name,
            "email":  payload.email,
            "mobile": payload.mobile,
            "notes":  payload.notes,
            "so":     payload.sort_order,
            "cb":     actor_id,
        },
    ).mappings().first()
    out = dict(row)
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="project.contact.create",
        target=str(project_id),
        payload={"contact_id": out["contact_id"], "kind": out["kind"], "name": out["name"]},
    )
    db.flush()
    return out


def _get_contact_scoped(
    db: Session, *, contact_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT c.contact_id, c.project_id, c.kind, c.position, c.name, c.email,
                   c.mobile, c.notes, c.sort_order, c.created_at, c.created_by
              FROM project_contact c
              JOIN projects p ON p.project_id = c.project_id
             WHERE c.contact_id = :cid AND p.workspace_id = :w
            """
        ),
        {"cid": contact_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def patch_contact(
    db: Session,
    *,
    contact_id: int,
    workspace_id: int,
    payload: PatchContactIn,
    actor_id: int,
) -> dict | None:
    current = _get_contact_scoped(db, contact_id=contact_id, workspace_id=workspace_id)
    if current is None:
        return None

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return current

    set_clauses = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "cid": contact_id}
    db.execute(
        text(f"UPDATE project_contact SET {set_clauses} WHERE contact_id = :cid"),
        params,
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="project.contact.update",
        target=str(current["project_id"]),
        payload={"contact_id": contact_id, "fields": list(fields.keys())},
    )
    db.flush()
    return _get_contact_scoped(db, contact_id=contact_id, workspace_id=workspace_id)


def delete_contact(
    db: Session, *, contact_id: int, workspace_id: int, actor_id: int
) -> bool:
    current = _get_contact_scoped(db, contact_id=contact_id, workspace_id=workspace_id)
    if current is None:
        return False
    db.execute(
        text("DELETE FROM project_contact WHERE contact_id = :cid"),
        {"cid": contact_id},
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="project.contact.delete",
        target=str(current["project_id"]),
        payload={"contact_id": contact_id},
    )
    db.flush()
    return True

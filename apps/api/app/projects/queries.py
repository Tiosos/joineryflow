"""SQL query functions for the projects module.

Column name mapping (legacy FileMaker schema vs spec):
  projects.project_id         -> aliased as id
  projects.installation_start -> aliased as install_start
  projects.total_value        -> exists as numeric(15,2)
  projects.workspace_id       -> direct FK to workspace(id), added in 0014.
                                 Use this for isolation; never join through
                                 pm_id -> app_user, which read TRUE in every
                                 workspace for unowned projects.

NO db.commit() here — routes own the transaction boundary.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..row_types import joinery_items_only
from .schemas import CreateProjectIn, PatchProjectIn


def _assert_user_in_workspace(db: Session, *, user_id: int, workspace_id: int) -> None:
    """Raise ValueError if user_id does not belong to workspace_id."""
    row = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :u AND workspace_id = :w"),
        {"u": user_id, "w": workspace_id},
    ).first()
    if not row:
        raise ValueError("pm_id does not belong to this workspace")

# ── Workspace-scoping clause ──────────────────────────────────────────────────
# Direct projects.workspace_id FK (migration 0014). Never reach through pm_id
# for isolation — that path is TRUE in every workspace when pm_id IS NULL.
_WORKSPACE_FILTER = "p.workspace_id = :wid"

_SELECT_COLS = """
    p.project_id                          AS id,
    p.project_code,
    p.name,
    p.pm_id,
    u.full_name                           AS pm_name,
    p.status,
    p.installation_start                  AS install_start,
    p.total_value,
    p.created_at,
    -- Q408's Project Details tiles (C5). All three are real columns the
    -- serializer simply never carried; the mock's hours tables are NOT here,
    -- because those come from TGPAY and nothing in this schema records hours
    -- (Q571).
    p.created_by,
    p.tg_solid,
    p.total_line_items,
    COALESCE(ic.cnt, 0)                   AS item_count,
    (f.user_id IS NOT NULL)               AS is_favourite,
    -- Project Detail 2.0 (#11) — additive surface
    p.builder,
    p.classification,
    p.site_street,
    p.site_suburb,
    p.site_postcode,
    p.site_state,
    p.tg_project_manager,
    p.tg_coordinator,
    p.tg_solid,
    p.carell_pid,
    p.total_line_items,
    p.closed_at,
    p.closed_by,
    cb.full_name                          AS closed_by_name
"""

_FROM_JOINS = f"""
    FROM projects p
    LEFT JOIN app_user u
        ON u.id = p.pm_id
    LEFT JOIN app_user cb
        ON cb.id = p.closed_by
    LEFT JOIN project_favourites f
        ON f.project_id = p.project_id AND f.user_id = :uid
    LEFT JOIN (
        SELECT project_id, COUNT(*) AS cnt
        FROM items
        WHERE {joinery_items_only("items")}
        GROUP BY project_id
    ) ic ON ic.project_id = p.project_id
"""


def _hydrate_project(db: Session, *, project_id: int) -> tuple[list[dict], dict | None, dict]:
    """Fetch contacts, lift access, and labour hours for one project."""
    contacts = db.execute(
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

    lift = db.execute(
        text(
            """
            SELECT project_id, notes, sketch_file_blob_id, updated_at, updated_by
              FROM project_lift_access
             WHERE project_id = :pid
            """
        ),
        {"pid": project_id},
    ).mappings().first()

    labour = db.execute(
        text(
            """
            SELECT site_install, assembly, administration
              FROM project_labour_hours_view
             WHERE project_id = :pid
            """
        ),
        {"pid": project_id},
    ).mappings().first()

    return (
        [dict(c) for c in contacts],
        dict(lift) if lift else None,
        dict(labour) if labour else {"site_install": 0, "assembly": 0, "administration": 0},
    )


def list_projects(
    db: Session,
    *,
    workspace_id: int,
    current_user_id: int,
    fav_only: bool | None = None,
) -> list[dict]:
    fav_clause = "AND f.user_id IS NOT NULL" if fav_only else ""
    rows = db.execute(
        text(
            f"""
            SELECT {_SELECT_COLS}
            {_FROM_JOINS}
            WHERE {_WORKSPACE_FILTER}
            {fav_clause}
            ORDER BY p.project_id
            """
        ),
        {"wid": workspace_id, "uid": current_user_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_project(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    current_user_id: int,
) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT {_SELECT_COLS}
            {_FROM_JOINS}
            WHERE p.project_id = :pid AND {_WORKSPACE_FILTER}
            """
        ),
        {"pid": project_id, "wid": workspace_id, "uid": current_user_id},
    ).mappings().first()
    if row is None:
        return None
    out = dict(row)
    contacts, lift, labour = _hydrate_project(db, project_id=project_id)
    out["contacts"] = contacts
    out["lift_access"] = lift
    out["labour_hours"] = labour
    return out


def close_out_project(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    actor_id: int,
) -> str:
    """Set closed_at + closed_by + status='Closed'.

    Returns 'OK', 'NOT_FOUND', or 'ALREADY_CLOSED'.
    """
    row = db.execute(
        text(
            "SELECT closed_at FROM projects WHERE project_id = :pid AND workspace_id = :wid"
        ),
        {"pid": project_id, "wid": workspace_id},
    ).mappings().first()
    if row is None:
        return "NOT_FOUND"
    if row["closed_at"] is not None:
        return "ALREADY_CLOSED"

    db.execute(
        text(
            """
            UPDATE projects
               SET closed_at = now(),
                   closed_by = :uid,
                   status    = 'Closed'
             WHERE project_id = :pid AND workspace_id = :wid
            """
        ),
        {"pid": project_id, "wid": workspace_id, "uid": actor_id},
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="project.close_out",
        target=str(project_id),
        payload={},
    )
    db.flush()
    return "OK"


def create_project(
    db: Session,
    *,
    workspace_id: int,
    payload: CreateProjectIn,
    actor_id: int,
) -> int:
    if payload.pm_id is not None:
        _assert_user_in_workspace(db, user_id=payload.pm_id, workspace_id=workspace_id)

    row = db.execute(
        text(
            """
            INSERT INTO projects(project_code, name, pm_id, installation_start, workspace_id)
            VALUES (:code, :name, :pm_id, :install_start, :wid)
            RETURNING project_id
            """
        ),
        {
            "code": payload.project_code,
            "name": payload.name,
            "pm_id": payload.pm_id,
            "install_start": payload.install_start,
            "wid": workspace_id,
        },
    ).mappings().first()
    new_id = row["project_id"]
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="project.create",
        target=str(new_id),
        payload=payload.model_dump(mode="json"),
    )
    db.flush()
    return new_id


# Patchable column names (whitelist) mapped to their actual DB column names.
_PATCH_COL_MAP = {
    "name": "name",
    "pm_id": "pm_id",
    "install_start": "installation_start",
    "status": "status",
    # Project Detail 2.0 (#11) — additive
    "builder": "builder",
    "classification": "classification",
    "site_street": "site_street",
    "site_suburb": "site_suburb",
    "site_postcode": "site_postcode",
    "site_state": "site_state",
    "tg_project_manager": "tg_project_manager",
    "tg_coordinator": "tg_coordinator",
    "tg_solid": "tg_solid",
    "carell_pid": "carell_pid",
    "total_value": "total_value",
    "total_line_items": "total_line_items",
}


def add_favourite(db: Session, *, project_id: int, user_id: int) -> None:
    db.execute(
        text("""
            INSERT INTO project_favourites(project_id, user_id)
            VALUES (:p, :u) ON CONFLICT DO NOTHING
        """),
        {"p": project_id, "u": user_id},
    )
    db.flush()


def remove_favourite(db: Session, *, project_id: int, user_id: int) -> None:
    db.execute(
        text("""
            DELETE FROM project_favourites WHERE project_id = :p AND user_id = :u
        """),
        {"p": project_id, "u": user_id},
    )
    db.flush()


def patch_project(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    payload: PatchProjectIn,
    actor_id: int,
) -> dict | None:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return get_project(
            db,
            project_id=project_id,
            workspace_id=workspace_id,
            current_user_id=actor_id,
        )

    # CRITICAL #2: validate pm_id belongs to this workspace before any write.
    if "pm_id" in fields and fields["pm_id"] is not None:
        _assert_user_in_workspace(db, user_id=fields["pm_id"], workspace_id=workspace_id)

    # Closing goes only through close_out_project, so closed_at/by are always
    # stamped; moving status anywhere else re-opens and clears the stamp.
    if "status" in fields and fields["status"] == "Closed":
        # Another workspace's project must still read as 404, not as this 422.
        if db.execute(
            text("SELECT 1 FROM projects WHERE project_id = :pid AND workspace_id = :wid"),
            {"pid": project_id, "wid": workspace_id},
        ).first() is None:
            return None
        raise ValueError("use POST /projects/{id}/close-out to close a project")

    set_clauses = ", ".join(
        f"{_PATCH_COL_MAP[k]} = :{k}" for k in fields if k in _PATCH_COL_MAP
    )
    if "status" in fields:
        set_clauses += ", closed_at = NULL, closed_by = NULL"
    # CRITICAL #1: scope the UPDATE to this workspace via the direct FK.
    # If 0 rows affected the project either doesn't exist or belongs to another workspace.
    params = {**fields, "pid": project_id, "wid": workspace_id}
    result = db.execute(
        text(
            f"""
            UPDATE projects
               SET {set_clauses}
             WHERE project_id = :pid
               AND workspace_id = :wid
            """
        ),
        params,
    )
    if result.rowcount == 0:
        return None

    # One audit row per changed field.
    for field_name, new_val in fields.items():
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor_id,
            event=f"project.patch.{field_name}",
            target=str(project_id),
            payload={"field": field_name, "value": str(new_val)},
        )

    db.flush()
    return get_project(
        db,
        project_id=project_id,
        workspace_id=workspace_id,
        current_user_id=actor_id,
    )

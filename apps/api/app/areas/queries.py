"""Area + Room query layer.

Routes own the transaction boundary; queries flush only, matching `cutlists/`
and `items/`. Workspace isolation goes through `projects.workspace_id`.

`0026` created these tables and backfilled them from the items that existed
when it ran. Nothing has written to them since — C6 is the first code to read
or create a row, which is why a database seeded *after* the migration has none.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..row_types import joinery_items_only
from .schemas import CreateAreaIn, CreateRoomIn

_JOINERY_I = joinery_items_only("i")


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first() is not None


def list_areas(db: Session, *, project_id: int, workspace_id: int) -> dict | None:
    """Areas with their rooms nested, each carrying how many items sit on it.

    The counts are what make an empty area safe to show: a selector needs the
    area to exist before any item can point at it.
    """
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None

    areas = db.execute(
        text(
            f"""
            SELECT a.area_id, a.project_id, a.name, a.sort_order, a.created_at,
                   (SELECT COUNT(*) FROM items i
                     WHERE i.area_id = a.area_id AND {_JOINERY_I}) AS item_count
              FROM area a
             WHERE a.project_id = :p
          ORDER BY a.sort_order, a.name
            """
        ),
        {"p": project_id},
    ).mappings().all()

    rooms = db.execute(
        text(
            f"""
            SELECT r.room_id, r.area_id, r.rm_no, r.rm_desc, r.sort_order,
                   (SELECT COUNT(*) FROM items i
                     WHERE i.room_id = r.room_id AND {_JOINERY_I}) AS item_count
              FROM room r
              JOIN area a ON a.area_id = r.area_id
             WHERE a.project_id = :p
          ORDER BY r.sort_order, r.rm_no
            """
        ),
        {"p": project_id},
    ).mappings().all()

    by_area: dict[int, list[dict]] = {}
    for r in rooms:
        by_area.setdefault(r["area_id"], []).append(dict(r))

    return {
        "project_id": project_id,
        "areas": [
            {**dict(a), "rooms": by_area.get(a["area_id"], [])} for a in areas
        ],
    }


def create_area(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    payload: CreateAreaIn,
    actor_id: int,
) -> tuple[str, dict | None]:
    """('OK', area) | ('NOT_FOUND', None) | ('DUPLICATE', existing).

    `uq_area_project_name` already forbids a second area of the same name in a
    project; returning the existing row rather than a raw constraint violation
    lets the selector just select it.
    """
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return "NOT_FOUND", None

    existing = db.execute(
        text("SELECT area_id FROM area WHERE project_id = :p AND name = :n"),
        {"p": project_id, "n": payload.name},
    ).mappings().first()
    if existing is not None:
        return "DUPLICATE", dict(existing)

    area_id = db.execute(
        text(
            """
            INSERT INTO area (project_id, name, sort_order)
            VALUES (:p, :n, :s)
            RETURNING area_id
            """
        ),
        {"p": project_id, "n": payload.name, "s": payload.sort_order},
    ).scalar()
    db.flush()
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="area.create",
        target=str(area_id),
        payload={"project_id": project_id, "name": payload.name},
    )
    return "OK", {"area_id": area_id}


def create_room(
    db: Session,
    *,
    area_id: int,
    workspace_id: int,
    payload: CreateRoomIn,
    actor_id: int,
) -> tuple[str, dict | None]:
    """('OK', room) | ('NOT_FOUND', None) | ('DUPLICATE', existing).

    A room belongs to an area, never straight to a project (Q552), so the area
    is the scope for both the lookup and `uq_room_area_no`.
    """
    area = db.execute(
        text(
            """
            SELECT a.area_id, a.project_id
              FROM area a
              JOIN projects p ON p.project_id = a.project_id
             WHERE a.area_id = :a AND p.workspace_id = :w
            """
        ),
        {"a": area_id, "w": workspace_id},
    ).mappings().first()
    if area is None:
        return "NOT_FOUND", None

    existing = db.execute(
        text("SELECT room_id FROM room WHERE area_id = :a AND rm_no = :n"),
        {"a": area_id, "n": payload.rm_no},
    ).mappings().first()
    if existing is not None:
        return "DUPLICATE", dict(existing)

    room_id = db.execute(
        text(
            """
            INSERT INTO room (area_id, rm_no, rm_desc, sort_order)
            VALUES (:a, :n, :d, :s)
            RETURNING room_id
            """
        ),
        {"a": area_id, "n": payload.rm_no, "d": payload.rm_desc, "s": payload.sort_order},
    ).scalar()
    db.flush()
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="room.create",
        target=str(room_id),
        payload={"area_id": area_id, "rm_no": payload.rm_no, "rm_desc": payload.rm_desc},
    )
    return "OK", {"room_id": room_id, "area_id": area_id}

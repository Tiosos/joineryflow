"""SQL helpers for the in-app notification inbox.

A notification is addressed to one user, so every query is keyed on
`recipient_id` (and `workspace_id`): you can only ever see or mark your own.
Notifications whose comment was deleted are hidden and not counted — an unread
badge that points at nothing would be a lie. The route additionally hides what
the recipient can no longer read (see `notifications/routes.py`).
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

_VISIBLE = """
    FROM notification n
    JOIN comment c ON c.comment_id = n.comment_id AND c.deleted_at IS NULL
    WHERE n.recipient_id = :u AND n.workspace_id = :w
"""


def _url(
    object_type: str, object_id: int, project_id: int | None,
    parent_id: int | None = None,
) -> str | None:
    """`parent_id` is the module's item / the revision's drawing."""
    if object_type == "item":
        return f"/items/{object_id}?tab=comments"
    if object_type == "module" and parent_id is not None:
        # The item editor's Cutlist tab opens the module named in the query.
        return f"/items/{parent_id}?tab=cutlist&module={object_id}"
    if object_type == "revision" and parent_id is not None and project_id is not None:
        # `comments=1` opens the drawer's comment panel on arrival.
        return (f"/shop-dwgs?project={project_id}&drawing={parent_id}"
                f"&rev={object_id}&comments=1")
    if object_type == "project":
        return f"/projects/{object_id}"
    # Area and Room threads live on the project page's Areas & Rooms card, which
    # opens the thread named in the query string.
    if object_type in ("area", "room") and project_id is not None:
        return f"/projects/{project_id}?{object_type}={object_id}"
    return None


def list_notifications(
    db: Session, *, user_id: int, workspace_id: int, unread_only: bool,
    limit: int, offset: int, types: list[str],
) -> dict:
    """`types` are the object types the recipient can currently read; the caller
    works them out, this only filters."""
    rows = db.execute(
        text(
            f"""
            SELECT n.notification_id, n.kind, n.created_at, n.read_at, n.actor_id,
                   ua.full_name AS actor_name, c.comment_id,
                   left(c.body, 140) AS excerpt, c.object_type,
                   COALESCE(c.project_id, c.area_id, c.room_id, c.item_id,
                            c.module_id, c.revision_id) AS object_id,
                   COALESCE(c.project_id, a.project_id, ra.project_id, i.project_id,
                            mi.project_id, sd.project_id) AS project_id,
                   COALESCE(mo.item_id, sr.drawing_id) AS parent_id,
                   CASE c.object_type
                        WHEN 'project' THEN p.project_code
                        WHEN 'area'    THEN a.name
                        -- the area is named too: "R01" alone is ambiguous when
                        -- several areas each have an R01
                        WHEN 'room'    THEN r.rm_no || COALESCE(' ' || r.rm_desc, '')
                                            || ' (' || ra.name || ')'
                        WHEN 'module'  THEN mo.module_no || COALESCE(' ' || mo.name, '')
                                            || ' (#' || mi.num::text || ')'
                        WHEN 'revision' THEN sd.title || ' · v' || sr.rev_no::text
                        ELSE '#' || i.num::text || COALESCE(' ' || i.description, '')
                   END AS object_label
              FROM notification n
              JOIN comment c ON c.comment_id = n.comment_id AND c.deleted_at IS NULL
              LEFT JOIN app_user ua ON ua.id = n.actor_id
              LEFT JOIN projects p ON p.project_id = c.project_id
              LEFT JOIN area a     ON a.area_id    = c.area_id
              LEFT JOIN room r     ON r.room_id    = c.room_id
              LEFT JOIN area ra    ON ra.area_id   = r.area_id
              LEFT JOIN items i    ON i.item_id    = c.item_id
              LEFT JOIN modules mo ON mo.module_id = c.module_id
              LEFT JOIN items mi   ON mi.item_id   = mo.item_id
              LEFT JOIN shop_drawing_revision sr ON sr.revision_id = c.revision_id
              LEFT JOIN shop_drawing sd ON sd.drawing_id = sr.drawing_id
             WHERE n.recipient_id = :u AND n.workspace_id = :w
               AND c.object_type = ANY(:types)
               AND (i.item_id IS NULL OR NOT i.deleted)
               AND (mi.item_id IS NULL OR NOT mi.deleted)
               {"AND n.read_at IS NULL" if unread_only else ""}
             ORDER BY n.created_at DESC, n.notification_id DESC
             LIMIT :lim OFFSET :off
            """
        ),
        {"u": user_id, "w": workspace_id, "lim": limit, "off": offset, "types": types},
    ).mappings().all()
    notifications = []
    for r in rows:
        row = dict(r)
        project_id = row.pop("project_id")  # only needed to build the link
        parent_id = row.pop("parent_id")
        notifications.append({
            **row,
            "url": _url(row["object_type"], row["object_id"], project_id, parent_id),
        })
    return {
        "notifications": notifications,
        "unread_count": unread_count(
            db, user_id=user_id, workspace_id=workspace_id, types=types
        ),
    }


def unread_count(
    db: Session, *, user_id: int, workspace_id: int, types: list[str]
) -> int:
    return db.execute(
        text(f"SELECT count(*) {_VISIBLE} AND n.read_at IS NULL"
             " AND c.object_type = ANY(:types)"),
        {"u": user_id, "w": workspace_id, "types": types},
    ).scalar_one()


def mark_read(db: Session, *, notification_id: int, user_id: int, workspace_id: int) -> str:
    """"OK" when it just became read, "ALREADY_READ" when it already was,
    "NOT_FOUND" when it is not this user's."""
    row = db.execute(
        text(
            """
            UPDATE notification SET read_at = now()
             WHERE notification_id = :n AND recipient_id = :u AND workspace_id = :w
               AND read_at IS NULL
            RETURNING 1
            """
        ),
        {"n": notification_id, "u": user_id, "w": workspace_id},
    ).first()
    if row:
        return "OK"
    mine = db.execute(
        text("SELECT 1 FROM notification WHERE notification_id = :n"
             " AND recipient_id = :u AND workspace_id = :w"),
        {"n": notification_id, "u": user_id, "w": workspace_id},
    ).first()
    return "ALREADY_READ" if mine else "NOT_FOUND"


def mark_all_read(db: Session, *, user_id: int, workspace_id: int) -> int:
    return db.execute(
        text(
            """
            UPDATE notification SET read_at = now()
             WHERE recipient_id = :u AND workspace_id = :w AND read_at IS NULL
            """
        ),
        {"u": user_id, "w": workspace_id},
    ).rowcount

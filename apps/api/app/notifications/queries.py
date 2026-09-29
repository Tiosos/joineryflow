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


def _url(object_type: str, object_id: int, project_id: int | None) -> str | None:
    if object_type == "item":
        return f"/items/{object_id}?tab=comments"
    if object_type == "project":
        return f"/projects/{object_id}"
    # Area and Room threads live on the project page's Areas & Rooms card, which
    # opens the thread named in the query string.
    if object_type in ("area", "room") and project_id is not None:
        return f"/projects/{project_id}?{object_type}={object_id}"
    return None


def list_notifications(
    db: Session, *, user_id: int, workspace_id: int, unread_only: bool,
    limit: int, offset: int, include_items: bool = True,
) -> dict:
    rows = db.execute(
        text(
            f"""
            SELECT n.notification_id, n.kind, n.created_at, n.read_at, n.actor_id,
                   ua.full_name AS actor_name, c.comment_id,
                   left(c.body, 140) AS excerpt, c.object_type,
                   COALESCE(c.project_id, c.area_id, c.room_id, c.item_id) AS object_id,
                   COALESCE(c.project_id, a.project_id, ra.project_id, i.project_id)
                       AS project_id,
                   CASE c.object_type
                        WHEN 'project' THEN p.project_code
                        WHEN 'area'    THEN a.name
                        WHEN 'room'    THEN r.rm_no
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
             WHERE n.recipient_id = :u AND n.workspace_id = :w
               {"AND n.read_at IS NULL" if unread_only else ""}
               {"" if include_items else "AND c.item_id IS NULL"}
             ORDER BY n.created_at DESC, n.notification_id DESC
             LIMIT :lim OFFSET :off
            """
        ),
        {"u": user_id, "w": workspace_id, "lim": limit, "off": offset},
    ).mappings().all()
    return {
        "notifications": [
            {**{k: v for k, v in dict(r).items() if k != "project_id"},
             "url": _url(r["object_type"], r["object_id"], r["project_id"])}
            for r in rows
        ],
        "unread_count": unread_count(
            db, user_id=user_id, workspace_id=workspace_id, include_items=include_items
        ),
    }


def unread_count(
    db: Session, *, user_id: int, workspace_id: int, include_items: bool = True
) -> int:
    return db.execute(
        text(f"SELECT count(*) {_VISIBLE} AND n.read_at IS NULL"
             + ("" if include_items else " AND c.item_id IS NULL")),
        {"u": user_id, "w": workspace_id},
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

"""SQL helpers for comments (migrations 0042 + 0043, Plan V1 §29).

One thread entity over Project / Area / Room / Joinery Item / Module /
Shop-drawing revision. The object is one of six real FK columns
(`_OBJECT_COL`); replies inherit their parent's object and are one level deep
(a DB rule, see the migration).

Every mutation writes `audit_log`; a comment on an item or on one of its modules
also writes `item_edit_log` in the same transaction, per the PM Workbench
invariant (a shop-drawing revision belongs to no item, so it writes none).
Workspace isolation: `comment.workspace_id` is set from the resolved object and
every read/write filters on it, so another workspace's id is a 404.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac_engine import has_permission_db
from ..auth.sessions import AuthUser
from ..edit_log import write_edit_log
from ..row_types import joinery_items_only

# Fixed map — the only place a column name is interpolated into SQL.
_OBJECT_COL = {
    "project": "project_id", "area": "area_id", "room": "room_id", "item": "item_id",
    "module": "module_id", "revision": "revision_id",
}

# Project, Area, Room and Item are Tracking's own hierarchy (areas/rooms already
# gate on it), so `tracking` governs their threads. A Module belongs to the item
# editor's Cutlist tab (`list`) and a shop-drawing revision to `shop_dwgs`; each
# thread is governed by the module its object lives under, not by `tracking`,
# so a group that cannot open a drawing cannot read the discussion about it.
MODULE = "tracking"

# The module whose `comment` grant posts, edits and deletes in a thread.
COMMENT_MODULE = {
    "project": MODULE, "area": MODULE, "room": MODULE, "item": MODULE,
    "module": "list", "revision": "shop_dwgs",
}

# Every module whose `read` grant is needed to open what the thread links to. An
# item's thread also needs `list:read`, because its notification links to the
# item editor and `GET /items/{id}` is gated on `list` — the Dynamic RBAC engine
# lets an admin grant one without the other, and a link the recipient cannot open
# is the failure `BAD_MENTION` exists to prevent. Every default role holds both.
# A module's link opens the same editor (`list`); a revision's opens the
# shop-drawings drawer (`shop_dwgs`).
READ_MODULES = {
    "project": (MODULE,), "area": (MODULE,), "room": (MODULE,),
    "item": (MODULE, "list"), "module": ("list",), "revision": ("shop_dwgs",),
}

_EXCERPT = 200

_COMMENT_COLS = """
    c.comment_id, c.workspace_id, c.object_type,
    COALESCE(c.project_id, c.area_id, c.room_id, c.item_id, c.module_id, c.revision_id)
        AS object_id,
    c.parent_comment_id, c.author_id, ua.full_name AS author_name,
    c.body, c.created_at, c.edited_at, c.deleted_at
"""
_COMMENT_JOIN = "LEFT JOIN app_user ua ON ua.id = c.author_id"


def _object_in_workspace(
    db: Session, *, object_type: str, object_id: int, workspace_id: int,
    lock: bool = False,
) -> bool:
    """Does the object exist in this workspace? With `lock`, also takes a
    `FOR KEY SHARE` lock on its row so a concurrent hard delete waits for this
    transaction instead of turning the comment INSERT into a raw FK violation."""
    sql = {
        "project": "SELECT 1 FROM projects p WHERE p.project_id = :id AND p.workspace_id = :w",
        "area": """SELECT 1 FROM area a JOIN projects p ON p.project_id = a.project_id
                    WHERE a.area_id = :id AND p.workspace_id = :w""",
        "room": """SELECT 1 FROM room r JOIN area a ON a.area_id = r.area_id
                     JOIN projects p ON p.project_id = a.project_id
                    WHERE r.room_id = :id AND p.workspace_id = :w""",
        # Joinery Items only — a related part gets 404, the item_documents / qc
        # precedent (§29 says "Joinery Item").
        "item": f"""SELECT 1 FROM items i JOIN projects p ON p.project_id = i.project_id
                     WHERE i.item_id = :id AND p.workspace_id = :w
                       AND {joinery_items_only("i")}""",
        # A module's item must be a Joinery Item too: the thread's link opens it.
        "module": f"""SELECT 1 FROM modules m JOIN items i ON i.item_id = m.item_id
                       JOIN projects p ON p.project_id = i.project_id
                      WHERE m.module_id = :id AND p.workspace_id = :w
                        AND {joinery_items_only("i")}""",
        "revision": """SELECT 1 FROM shop_drawing_revision v
                         JOIN shop_drawing d ON d.drawing_id = v.drawing_id
                         JOIN projects p ON p.project_id = d.project_id
                        WHERE v.revision_id = :id AND p.workspace_id = :w""",
    }[object_type]
    if lock:
        sql += " FOR KEY SHARE OF " + {
            "project": "p", "area": "a", "room": "r", "item": "i",
            "module": "m", "revision": "v",
        }[object_type]
    return db.execute(text(sql), {"id": object_id, "w": workspace_id}).first() is not None


def object_type_of(db: Session, *, comment_id: int, workspace_id: int) -> str | None:
    """The object type a comment belongs to, or None if it is not in this
    workspace. The routes need it *before* the permission check: which module
    gates a comment depends on what it is a comment on."""
    return db.execute(
        text("SELECT object_type FROM comment WHERE comment_id = :c AND workspace_id = :w"),
        {"c": comment_id, "w": workspace_id},
    ).scalar()


def _row(
    db: Session, *, comment_id: int, workspace_id: int, for_update: bool = False
) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT {_COMMENT_COLS}
              FROM comment c {_COMMENT_JOIN}
             WHERE c.comment_id = :cid AND c.workspace_id = :w
            {"FOR UPDATE OF c" if for_update else ""}
            """
        ),
        {"cid": comment_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def _mentions_for(db: Session, comment_ids: list[int]) -> dict[int, list[dict]]:
    if not comment_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT m.comment_id, m.user_id, u.full_name
              FROM comment_mention m JOIN app_user u ON u.id = m.user_id
             WHERE m.comment_id = ANY(:ids)
             ORDER BY u.full_name
            """
        ),
        {"ids": comment_ids},
    ).mappings().all()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["comment_id"], []).append(
            {"user_id": r["user_id"], "full_name": r["full_name"]}
        )
    return out


def _shape(row: dict, mentions: list[dict]) -> dict:
    """API shape. A deleted comment's body and mentions are blanked — it stays
    only as a placeholder in front of replies that survive it."""
    gone = row["deleted_at"] is not None
    return {
        "comment_id": row["comment_id"],
        "object_type": row["object_type"],
        "object_id": row["object_id"],
        "parent_comment_id": row["parent_comment_id"],
        "author_id": row["author_id"],
        "author_name": row["author_name"],
        "body": "" if gone else row["body"],
        "created_at": row["created_at"],
        "edited_at": row["edited_at"],
        "deleted": gone,
        "mentions": [] if gone else mentions,
        "replies": [],
    }


def _load_one(db: Session, *, comment_id: int, workspace_id: int) -> dict:
    row = _row(db, comment_id=comment_id, workspace_id=workspace_id)
    assert row is not None
    return _shape(row, _mentions_for(db, [comment_id]).get(comment_id, []))


def list_comments(
    db: Session, *, object_type: str, object_id: int, workspace_id: int
) -> list[dict] | None:
    """Top-level comments oldest-first, each with its replies oldest-first.

    A deleted top-level comment is kept (as a blanked placeholder) only while a
    surviving reply hangs off it; a deleted reply simply disappears."""
    if not _object_in_workspace(
        db, object_type=object_type, object_id=object_id, workspace_id=workspace_id
    ):
        return None
    col = _OBJECT_COL[object_type]
    rows = db.execute(
        text(
            f"""
            SELECT {_COMMENT_COLS}
              FROM comment c {_COMMENT_JOIN}
             WHERE c.{col} = :oid AND c.workspace_id = :w
             ORDER BY c.created_at, c.comment_id
            """
        ),
        {"oid": object_id, "w": workspace_id},
    ).mappings().all()
    mentions = _mentions_for(db, [r["comment_id"] for r in rows])
    tops: dict[int, dict] = {}
    order: list[int] = []
    for r in rows:
        r = dict(r)
        if r["parent_comment_id"] is None:
            tops[r["comment_id"]] = _shape(r, mentions.get(r["comment_id"], []))
            order.append(r["comment_id"])
    for r in rows:
        r = dict(r)
        parent = tops.get(r["parent_comment_id"]) if r["parent_comment_id"] else None
        if parent is not None and r["deleted_at"] is None:
            parent["replies"].append(_shape(r, mentions.get(r["comment_id"], [])))
    return [
        tops[i] for i in order if not tops[i]["deleted"] or tops[i]["replies"]
    ]


def _readers(
    db: Session, *, workspace_id: int, user_ids: list[int], object_type: str
) -> set[int]:
    """Of `user_ids`, those who are active in this workspace and can currently
    read what this object's thread links to (`READ_MODULES`). Checked against
    the Dynamic RBAC engine, workspace-wide."""
    if not user_ids:
        return set()
    rows = db.execute(
        text(
            """
            SELECT id, workspace_id, email, full_name, auth_role
              FROM app_user
             WHERE workspace_id = :w AND is_active = true AND id = ANY(:ids)
            """
        ),
        {"w": workspace_id, "ids": user_ids},
    ).mappings().all()
    return {
        r["id"]
        for r in rows
        if all(
            has_permission_db(
                db,
                AuthUser(id=r["id"], workspace_id=r["workspace_id"], email=r["email"],
                         full_name=r["full_name"], auth_role=r["auth_role"]),
                module, "read",
            )
            for module in READ_MODULES[object_type]
        )
    }


def counts_for_project(
    db: Session, *, project_id: int, workspace_id: int
) -> dict | None:
    """Live comment counts per area and per room of one project, for the
    Areas & Rooms card. Deleted comments are not counted (a deleted top-level
    comment is only a placeholder). None if the project is not in this
    workspace."""
    if not _object_in_workspace(
        db, object_type="project", object_id=project_id, workspace_id=workspace_id
    ):
        return None
    rows = db.execute(
        text(
            """
            SELECT c.area_id, c.room_id, count(*) AS n
              FROM comment c
              LEFT JOIN area a  ON a.area_id = c.area_id
              LEFT JOIN room r  ON r.room_id = c.room_id
              LEFT JOIN area ra ON ra.area_id = r.area_id
             WHERE c.workspace_id = :w AND c.deleted_at IS NULL
               AND (c.area_id IS NOT NULL OR c.room_id IS NOT NULL)
               AND COALESCE(a.project_id, ra.project_id) = :p
             GROUP BY c.area_id, c.room_id
            """
        ),
        {"w": workspace_id, "p": project_id},
    ).mappings().all()
    return {
        "areas": {r["area_id"]: r["n"] for r in rows if r["area_id"] is not None},
        "rooms": {r["room_id"]: r["n"] for r in rows if r["room_id"] is not None},
    }


def _bad_mentions(
    db: Session, *, workspace_id: int, user_ids: list[int], object_type: str
) -> list[int]:
    """Ids that cannot be mentioned: not an active user of this workspace, or a
    user who cannot read this thread's object (a notification linking them to a
    record they cannot open is worse than refusing the mention)."""
    ok = _readers(db, workspace_id=workspace_id, user_ids=user_ids, object_type=object_type)
    return sorted(set(user_ids) - ok)


def _notify(
    db: Session, *, workspace_id: int, actor_id: int, comment_id: int,
    recipients: dict[int, str],
) -> None:
    """One row per (recipient, kind); the unique constraint makes a repeat a
    no-op, so re-mentioning someone on edit never pings them twice."""
    for uid, kind in recipients.items():
        if uid == actor_id:
            continue
        db.execute(
            text(
                """
                INSERT INTO notification(workspace_id, recipient_id, actor_id, kind, comment_id)
                VALUES (:w, :r, :a, :k, :c)
                ON CONFLICT (recipient_id, comment_id, kind) DO NOTHING
                """
            ),
            {"w": workspace_id, "r": uid, "a": actor_id, "k": kind, "c": comment_id},
        )


def _log_item(
    db: Session, row: dict, *, actor_id: int, field: str,
    old: str | None, new: str | None,
) -> None:
    """`row` needs `object_type` and `object_id`. An item's thread logs against
    the item, a module's against the module's item; nothing else has one."""
    if row["object_type"] == "item":
        item_id = row["object_id"]
    elif row["object_type"] == "module":
        item_id = db.execute(
            text("SELECT item_id FROM modules WHERE module_id = :m"),
            {"m": row["object_id"]},
        ).scalar()
    else:
        return
    if item_id is not None:
        write_edit_log(db, item_id=item_id, actor_id=actor_id,
                       field=field, old_value=old, new_value=new)


def create_comment(
    db: Session, *, actor: AuthUser, object_type: str | None, object_id: int | None,
    parent_id: int | None, body: str, mentioned_user_ids: list[int],
) -> tuple[str, object]:
    """Returns (code, payload): ("OK", comment) or an error code.

    Codes: NOT_FOUND, PARENT_DELETED, REPLY_TO_REPLY, BAD_MENTION (payload =
    the offending user ids)."""
    ws = actor.workspace_id
    body = body.strip()
    parent = None
    if parent_id is not None:
        # Locked so a delete racing this reply serialises against it.
        parent = _row(db, comment_id=parent_id, workspace_id=ws, for_update=True)
        if parent is None:
            return "NOT_FOUND", None
        if parent["deleted_at"] is not None:
            return "PARENT_DELETED", None
        if parent["parent_comment_id"] is not None:
            return "REPLY_TO_REPLY", None
        object_type, object_id = parent["object_type"], parent["object_id"]
    elif not _object_in_workspace(
        db, object_type=object_type, object_id=object_id, workspace_id=ws, lock=True
    ):
        return "NOT_FOUND", None

    ids = sorted(set(mentioned_user_ids))
    bad = _bad_mentions(db, workspace_id=ws, user_ids=ids, object_type=object_type)
    if bad:
        return "BAD_MENTION", bad

    col = _OBJECT_COL[object_type]
    cid = db.execute(
        text(
            f"""
            INSERT INTO comment(workspace_id, {col}, parent_comment_id, author_id, body)
            VALUES (:w, :oid, :p, :a, :b) RETURNING comment_id
            """
        ),
        {"w": ws, "oid": object_id, "p": parent_id, "a": actor.id, "b": body},
    ).scalar_one()
    for uid in ids:
        db.execute(
            text("INSERT INTO comment_mention(comment_id, user_id) VALUES (:c, :u)"),
            {"c": cid, "u": uid},
        )

    recipients = {uid: "mention" for uid in ids}
    if parent and parent["author_id"] and parent["author_id"] not in recipients:
        # A reply is never refused over its recipient, but it is only *sent* to a
        # parent author who can still open the thread.
        if parent["author_id"] in _readers(
            db, workspace_id=ws, user_ids=[parent["author_id"]], object_type=object_type
        ):
            recipients[parent["author_id"]] = "reply"
    _notify(db, workspace_id=ws, actor_id=actor.id, comment_id=cid, recipients=recipients)

    write_audit(
        db, workspace_id=ws, actor_id=actor.id, event="comment.create",
        target=f"{object_type}:{object_id}",
        payload={"comment_id": cid, "parent_comment_id": parent_id, "mentions": ids},
    )
    _log_item(db, {"object_type": object_type, "object_id": object_id},
              actor_id=actor.id, field="_comment_create", old=None,
              new=f"comment {cid}: {body[:_EXCERPT]}")
    return "OK", _load_one(db, comment_id=cid, workspace_id=ws)


def edit_comment(
    db: Session, *, actor: AuthUser, comment_id: int, body: str,
    mentioned_user_ids: list[int] | None,
) -> tuple[str, object]:
    """Author only. Codes: NOT_FOUND, COMMENT_DELETED, NOT_AUTHOR, BAD_MENTION.

    A mention added by the edit is notified; one removed keeps the
    notification already sent (they *were* told)."""
    ws = actor.workspace_id
    row = _row(db, comment_id=comment_id, workspace_id=ws, for_update=True)
    if row is None:
        return "NOT_FOUND", None
    if row["deleted_at"] is not None:
        return "COMMENT_DELETED", None
    if row["author_id"] != actor.id:
        return "NOT_AUTHOR", None

    old_ids = {
        r for r in db.execute(
            text("SELECT user_id FROM comment_mention WHERE comment_id = :c"),
            {"c": comment_id},
        ).scalars()
    }
    new_ids: list[int] | None = None
    if mentioned_user_ids is not None:
        new_ids = sorted(set(mentioned_user_ids))
        # Only *newly added* mentions are checked: one already on the comment
        # must not block an unrelated edit just because that person has since
        # lost access (the UI resends every `@Name` still in the text).
        bad = _bad_mentions(
            db, workspace_id=ws, object_type=row["object_type"],
            user_ids=[u for u in new_ids if u not in old_ids],
        )
        if bad:
            return "BAD_MENTION", bad

    body = body.strip()
    if body == row["body"] and (new_ids is None or set(new_ids) == old_ids):
        return "OK", _load_one(db, comment_id=comment_id, workspace_id=ws)  # no-op

    db.execute(
        text("UPDATE comment SET body = :b, edited_at = now() WHERE comment_id = :c"),
        {"b": body, "c": comment_id},
    )
    if new_ids is not None:
        for uid in old_ids - set(new_ids):
            db.execute(
                text("DELETE FROM comment_mention WHERE comment_id = :c AND user_id = :u"),
                {"c": comment_id, "u": uid},
            )
        added = [u for u in new_ids if u not in old_ids]
        for uid in added:
            db.execute(
                text("INSERT INTO comment_mention(comment_id, user_id) VALUES (:c, :u)"),
                {"c": comment_id, "u": uid},
            )
        _notify(db, workspace_id=ws, actor_id=actor.id, comment_id=comment_id,
                recipients={u: "mention" for u in added})

    write_audit(
        db, workspace_id=ws, actor_id=actor.id, event="comment.edit",
        target=f"{row['object_type']}:{row['object_id']}",
        payload={"comment_id": comment_id,
                 "mentions": new_ids if new_ids is not None else sorted(old_ids)},
    )
    _log_item(db, row, actor_id=actor.id, field=f"comment.{comment_id}",
              old=row["body"][:_EXCERPT], new=body[:_EXCERPT])
    return "OK", _load_one(db, comment_id=comment_id, workspace_id=ws)


def delete_comment(
    db: Session, *, actor: AuthUser, comment_id: int
) -> str:
    """Soft delete — the row stays for the audit trail and to anchor surviving
    replies. The author, or a manager / admin, may delete. Codes: OK,
    NOT_FOUND, ALREADY_DELETED, FORBIDDEN."""
    ws = actor.workspace_id
    row = _row(db, comment_id=comment_id, workspace_id=ws, for_update=True)
    if row is None:
        return "NOT_FOUND"
    if row["deleted_at"] is not None:
        return "ALREADY_DELETED"
    if row["author_id"] != actor.id and actor.auth_role not in ("manager", "admin"):
        return "FORBIDDEN"
    db.execute(
        text("UPDATE comment SET deleted_at = now(), deleted_by = :u WHERE comment_id = :c"),
        {"u": actor.id, "c": comment_id},
    )
    write_audit(
        db, workspace_id=ws, actor_id=actor.id, event="comment.delete",
        target=f"{row['object_type']}:{row['object_id']}",
        payload={"comment_id": comment_id, "author_id": row["author_id"]},
    )
    _log_item(db, row, actor_id=actor.id, field="_comment_delete",
              old=row["body"][:_EXCERPT], new=None)
    return "OK"

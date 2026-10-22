"""SQL for tasks (migration 0080, Plan V1 §10, Q524).

Who may do what (spec `docs/archive/2026-10-21-tasks.md` §4):

* **Read** a task with a target needs `read` on the target's module (`tracking` for a
  project or item, `list` for a cutlist). A task with no target is read by its creator,
  its assignee, and managers / admins.
* **Create / edit** needs `comment` on that module; a task with no target is free to
  create for yourself, and giving it to someone else needs `comment` on `tracking`.
* **Change status** (incl. reopening): creator, assignee, manager, admin.
* The assignee must be able to read the target (`ASSIGNEE_CANNOT_READ_TARGET`), so a
  record's name is never shown to someone who could not open it.

A task whose item or cutlist was soft-deleted (`0052`) drops out of every read, like the
item does. Queries return `(code, value)`; the routes map the codes to HTTP.
"""
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac_engine import has_permission_db
from ..auth.sessions import AuthUser
from ..concurrency import bump_field_versions, check_field_conflicts, conflict_safe_value
from ..edit_log import write_edit_log
from ..row_types import live_joinery_items
from ..sql_columns import require_columns
from ..workspace_scope import project_in_workspace
from .schemas import CreateTaskIn, PatchTaskIn

_JOINERY_I = live_joinery_items("i")

# The only columns a PATCH may write: `require_columns` is called with the keys below.
_PATCHABLE = frozenset({
    "title", "description", "assignee_id", "due_date",
    "project_id", "item_id", "cutlist_id",
})
_TARGET_COLS = ("project_id", "item_id", "cutlist_id")
_KIND_COL = {"project": "project_id", "item": "item_id", "cutlist": "cutlist_id"}
_PRIVILEGED_ROLES = ("manager", "admin")

# The tasks the caller may see: `:w` (workspace), `:u` (the caller), `:priv`, `:rt`, `:rl` (from
# `scope`). Used by every read here and by the notification inbox, which must hide a task thread
# from a recipient who can no longer see the task.
_FROM_VISIBLE = f"""
    FROM task t
    LEFT JOIN app_user au ON au.id = t.assignee_id
    LEFT JOIN app_user cu ON cu.id = t.created_by
    LEFT JOIN projects p ON p.project_id = t.project_id
    LEFT JOIN items i ON i.item_id = t.item_id AND {_JOINERY_I}
    LEFT JOIN cutlist c ON c.cutlist_id = t.cutlist_id AND NOT c.deleted
    WHERE t.workspace_id = :w
      AND (t.item_id IS NULL OR i.item_id IS NOT NULL)
      AND (t.cutlist_id IS NULL OR c.cutlist_id IS NOT NULL)
      AND (
            (t.project_id IS NULL AND t.item_id IS NULL AND t.cutlist_id IS NULL
               AND (:priv OR t.created_by = :u OR t.assignee_id = :u))
         OR (:rt AND (t.project_id IS NOT NULL OR t.item_id IS NOT NULL))
         OR (:rl AND t.cutlist_id IS NOT NULL)
      )
"""
FROM_VISIBLE = _FROM_VISIBLE

_SELECT = f"""
    SELECT t.task_id, t.title, t.description, t.status, t.assignee_id,
           au.full_name AS assignee_name, t.created_by, cu.full_name AS created_by_name,
           t.due_date, t.source, t.project_id, t.item_id, t.cutlist_id,
           CASE WHEN t.project_id IS NOT NULL THEN 'project'
                WHEN t.item_id    IS NOT NULL THEN 'item'
                WHEN t.cutlist_id IS NOT NULL THEN 'cutlist' END AS target_type,
           CASE WHEN t.project_id IS NOT NULL THEN p.project_code
                WHEN t.item_id    IS NOT NULL THEN COALESCE(NULLIF(i.code, ''), CAST(i.num AS text))
                WHEN t.cutlist_id IS NOT NULL THEN CAST(c.cutlist_no AS text)
                                                   || COALESCE(' ' || c.name, '') END AS target_label,
           t.completed_at, t.cancelled_at, t.field_versions, t.created_at, t.updated_at,
           (SELECT count(*) FROM comment cm
             WHERE cm.task_id = t.task_id AND cm.deleted_at IS NULL) AS comment_count
    {_FROM_VISIBLE}
"""


def _is_privileged(actor: AuthUser) -> bool:
    return actor.auth_role in _PRIVILEGED_ROLES


def scope(db: Session, actor: AuthUser) -> dict:
    """Bind values for the visibility predicate in `_SELECT`."""
    return {
        "w": actor.workspace_id, "u": actor.id, "priv": _is_privileged(actor),
        "rt": has_permission_db(db, actor, "tracking", "read"),
        "rl": has_permission_db(db, actor, "list", "read"),
    }


def _module(target_type: str | None) -> str:
    return "list" if target_type == "cutlist" else "tracking"


def _target_of(row: dict) -> tuple[str | None, int | None]:
    for col, kind in (("project_id", "project"), ("item_id", "item"), ("cutlist_id", "cutlist")):
        if row.get(col) is not None:
            return kind, row[col]
    return None, None


def target_exists(db: Session, *, workspace_id: int, target_type: str | None,
                    target_id: int | None) -> bool:
    """Does the target exist, live, in this workspace? A related part, a deleted item or
    cutlist, and another workspace's row all answer as missing."""
    if target_type is None:
        return True
    if target_type == "project":
        return project_in_workspace(db, project_id=target_id, workspace_id=workspace_id)
    if target_type == "item":
        sql = (f"SELECT 1 FROM items i JOIN projects p ON p.project_id = i.project_id"
               f" WHERE i.item_id = :t AND p.workspace_id = :w AND {_JOINERY_I}")
    else:
        sql = ("SELECT 1 FROM cutlist c JOIN projects p ON p.project_id = c.project_id"
               " WHERE c.cutlist_id = :t AND p.workspace_id = :w AND NOT c.deleted")
    return db.execute(text(sql), {"t": target_id, "w": workspace_id}).first() is not None


def _user(db: Session, *, user_id: int, workspace_id: int) -> AuthUser | None:
    r = db.execute(
        text("SELECT id, workspace_id, email, full_name, auth_role FROM app_user"
             " WHERE id = :u AND workspace_id = :w"),
        {"u": user_id, "w": workspace_id},
    ).mappings().first()
    return AuthUser(**dict(r)) if r else None


def _assignee_check(db: Session, *, workspace_id: int, assignee_id: int | None,
                    target_type: str | None) -> str:
    """"OK", "ASSIGNEE_NOT_FOUND" or "ASSIGNEE_CANNOT_READ_TARGET"."""
    if assignee_id is None:
        return "OK"
    assignee = _user(db, user_id=assignee_id, workspace_id=workspace_id)
    if assignee is None:
        return "ASSIGNEE_NOT_FOUND"
    if target_type is not None and not has_permission_db(db, assignee, _module(target_type), "read"):
        return "ASSIGNEE_CANNOT_READ_TARGET"
    return "OK"


def _may_comment(db: Session, actor: AuthUser, *, target_type: str | None,
                 assignee_id: int | None) -> bool:
    """`comment` on the target's module; with no target, free for yourself and
    `comment` on `tracking` to give it to someone else."""
    if target_type is None and assignee_id in (None, actor.id):
        return True
    return has_permission_db(db, actor, _module(target_type), "comment")


def _log_item(db: Session, row: dict, *, actor_id: int, field: str,
              old: str | None, new: str | None) -> None:
    if row.get("item_id") is not None:
        write_edit_log(db, item_id=row["item_id"], actor_id=actor_id, field=field,
                       old_value=old, new_value=new)


def can_comment(db: Session, actor: AuthUser, task: dict) -> bool:
    """May `actor` post in this task's thread (comments, migration 0082)? A task on a project, item
    or cutlist: `comment` on the module its target follows. A task with no target has no module,
    and a person who can see it (its creator, assignee, a manager or admin) is its whole audience,
    so seeing it is enough, as making one for yourself needs no grant either."""
    target = task["target_type"]
    return target is None or has_permission_db(db, actor, _module(target), "comment")


def _with_can_comment(db: Session, actor: AuthUser, rows: list[dict]) -> list[dict]:
    """Adds `can_comment` to each row, asking the permission engine once per module."""
    granted = {m: has_permission_db(db, actor, m, "comment") for m in ("tracking", "list")}
    for r in rows:
        r["can_comment"] = r["target_type"] is None or granted[_module(r["target_type"])]
    return rows


def get_task(db: Session, *, actor: AuthUser, task_id: int, for_update: bool = False) -> dict | None:
    if for_update:
        locked = db.execute(text("SELECT task_id FROM task WHERE task_id=:t AND workspace_id=:w FOR UPDATE"),
                            {"t": task_id, "w": actor.workspace_id}).first()
        if locked is None:
            return None
        # Read visibility and all mutable business fields in a NEW statement
        # after waiting; a version-only refresh leaves ownership/status stale.
    r = db.execute(text(_SELECT + " AND t.task_id = :t"),
                   {**scope(db, actor), "t": task_id}).mappings().first()
    return _with_can_comment(db, actor, [dict(r)])[0] if r else None


def list_tasks(
    db: Session, *, actor: AuthUser, assignee_id: int | None, status: str | None,
    project_id: int | None, item_id: int | None, cutlist_id: int | None,
    due_before, limit: int, offset: int,
) -> dict:
    where, params = "", {**scope(db, actor)}
    if assignee_id is not None:
        where += " AND t.assignee_id = :f_assignee"
        params["f_assignee"] = assignee_id
    if status == "active":                      # open + in_progress: what is still to do
        where += " AND t.status IN ('open', 'in_progress')"
    elif status is not None:
        where += " AND t.status = :f_status"
        params["f_status"] = status
    if project_id is not None:
        where += " AND COALESCE(t.project_id, i.project_id, c.project_id) = :f_project"
        params["f_project"] = project_id
    if item_id is not None:
        where += " AND t.item_id = :f_item"
        params["f_item"] = item_id
    if cutlist_id is not None:
        where += " AND t.cutlist_id = :f_cutlist"
        params["f_cutlist"] = cutlist_id
    if due_before is not None:
        where += " AND t.due_date < :f_due"
        params["f_due"] = due_before
    total = db.execute(
        text(f"SELECT count(*) FROM ({_SELECT}{where}) q"), params
    ).scalar_one()
    rows = db.execute(
        text(_SELECT + where + """
             ORDER BY (t.status IN ('done', 'cancelled')), t.due_date NULLS LAST, t.task_id DESC
             LIMIT :limit OFFSET :offset"""),
        {**params, "limit": limit, "offset": offset},
    ).mappings().all()
    return {"items": _with_can_comment(db, actor, [dict(r) for r in rows]), "total": total}


def create_task(db: Session, *, actor: AuthUser, payload: CreateTaskIn) -> tuple[str, dict | None]:
    ws = actor.workspace_id
    target_type, target_id = _target_of(payload.model_dump())
    if not target_exists(db, workspace_id=ws, target_type=target_type, target_id=target_id):
        return "NOT_FOUND", None
    if not _may_comment(db, actor, target_type=target_type, assignee_id=payload.assignee_id):
        return "FORBIDDEN", None
    code = _assignee_check(db, workspace_id=ws, assignee_id=payload.assignee_id,
                           target_type=target_type)
    if code != "OK":
        return code, None
    task_id = db.execute(
        text("""
            INSERT INTO task(workspace_id, title, description, assignee_id, created_by,
                             due_date, project_id, item_id, cutlist_id)
            VALUES (:w, :title, :d, :a, :u, :due, :p, :i, :c) RETURNING task_id
        """),
        {"w": ws, "title": payload.title, "d": payload.description,
         "a": payload.assignee_id, "u": actor.id, "due": payload.due_date,
         "p": payload.project_id, "i": payload.item_id, "c": payload.cutlist_id},
    ).scalar_one()
    write_audit(db, workspace_id=ws, actor_id=actor.id, event="task.create",
                target=f"task:{task_id}",
                payload={"title": payload.title, "assignee_id": payload.assignee_id,
                         "target": [target_type, target_id]})
    _log_item(db, payload.model_dump(), actor_id=actor.id, field="_task_create",
              old=None, new=f"task {task_id}: {payload.title}")
    return "OK", get_task(db, actor=actor, task_id=task_id)


def patch_task(db: Session, *, actor: AuthUser, task_id: int,
               payload: PatchTaskIn) -> tuple[str, object]:
    ws = actor.workspace_id
    current = get_task(db, actor=actor, task_id=task_id, for_update=True)
    if current is None:
        return "NOT_FOUND", None
    if not (_is_privileged(actor) or actor.id in (current["created_by"], current["assignee_id"])):
        return "FORBIDDEN", None
    if current["status"] in ("done", "cancelled"):
        return "TASK_CLOSED", None

    fields = payload.model_fields_set - {"expected_versions"}
    if not fields:
        return "OK", current

    # The resulting state, field by field.
    new = {k: getattr(payload, k) for k in fields if k in _PATCHABLE and k not in _TARGET_COLS}
    old_type, old_id = _target_of(current)
    new_type_, new_id = old_type, old_id
    if fields & set(_TARGET_COLS):
        new_type_, new_id = _target_of(payload.model_dump())
        for kind, col in _KIND_COL.items():
            new[col] = new_id if kind == new_type_ else None
    assignee = new["assignee_id"] if "assignee_id" in new else current["assignee_id"]

    # Editing needs `comment` on the target the task has and on the one it is moving to.
    if not _may_comment(db, actor, target_type=old_type, assignee_id=actor.id):
        return "FORBIDDEN", None
    if (new_type_, new_id) != (old_type, old_id):
        if not target_exists(db, workspace_id=ws, target_type=new_type_, target_id=new_id):
            return "NOT_FOUND", None
        if not _may_comment(db, actor, target_type=new_type_, assignee_id=actor.id):
            return "FORBIDDEN", None
    if "assignee_id" in new and assignee not in (None, current["assignee_id"]):
        if not _may_comment(db, actor, target_type=new_type_, assignee_id=assignee):
            return "FORBIDDEN", None
    if "assignee_id" in new or fields & set(_TARGET_COLS):
        code = _assignee_check(db, workspace_id=ws, assignee_id=assignee, target_type=new_type_)
        if code != "OK":
            return code, None

    locked = current["field_versions"]
    conflicts = check_field_conflicts(locked, payload.expected_versions)
    if conflicts:
        for field, info in conflicts.items():
            info["current_value"] = conflict_safe_value(current.get(field))
        return "FIELD_CONFLICT", conflicts

    changed = {k: v for k, v in new.items() if current.get(k) != v}
    if not changed:
        return "OK", current
    require_columns(changed, _PATCHABLE)
    sets = ", ".join(f"{k} = :{k}" for k in changed)
    db.execute(
        text(f"UPDATE task SET {sets}, field_versions = CAST(:fv AS jsonb), updated_at = now()"
             " WHERE task_id = :t"),
        {**changed, "fv": json.dumps(bump_field_versions(locked, list(changed))), "t": task_id},
    )
    write_audit(db, workspace_id=ws, actor_id=actor.id, event="task.update",
                target=f"task:{task_id}", payload={"changed": sorted(changed)})
    for item_id in {current.get("item_id"), changed.get("item_id")} - {None}:
        _log_item(db, {"item_id": item_id}, actor_id=actor.id, field="_task_update",
                  old=None, new=f"task {task_id}: {', '.join(sorted(changed))}")
    return "OK", get_task(db, actor=actor, task_id=task_id)


def set_status(db: Session, *, actor: AuthUser, task_id: int, status: str) -> tuple[str, dict | None]:
    ws = actor.workspace_id
    current = get_task(db, actor=actor, task_id=task_id, for_update=True)
    if current is None:
        return "NOT_FOUND", None
    if not (_is_privileged(actor) or actor.id in (current["created_by"], current["assignee_id"])):
        return "FORBIDDEN", None
    if current["status"] == status:
        return "OK", current
    locked = current["field_versions"]
    db.execute(
        text("""
            UPDATE task SET status = CAST(:s AS varchar),
                   completed_at = CASE WHEN CAST(:s AS varchar) = 'done' THEN now() END,
                   completed_by = CASE WHEN CAST(:s AS varchar) = 'done' THEN CAST(:u AS bigint) END,
                   cancelled_at = CASE WHEN CAST(:s AS varchar) = 'cancelled' THEN now() END,
                   cancelled_by = CASE WHEN CAST(:s AS varchar) = 'cancelled' THEN CAST(:u AS bigint) END,
                   field_versions = CAST(:fv AS jsonb), updated_at = now()
            WHERE task_id = :t
        """),
        {"s": status, "u": actor.id, "t": task_id,
         "fv": json.dumps(bump_field_versions(locked, ["status"]))},
    )
    write_audit(db, workspace_id=ws, actor_id=actor.id, event="task.status",
                target=f"task:{task_id}", payload={"from": current["status"], "to": status})
    _log_item(db, current, actor_id=actor.id, field="_task_status",
              old=current["status"], new=f"task {task_id}: {status}")
    return "OK", get_task(db, actor=actor, task_id=task_id)

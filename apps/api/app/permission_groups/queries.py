"""SQL helpers for the RBAC-engine admin API (Q466-473).

Workspace-isolated throughout: `permission_group.workspace_id` is a direct
column (Q555's pattern — groups are referenced directly with no join path),
`user_group_membership` reaches it through its group.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.permissions import _ALL_MODULES
from .schemas import CreateGroupIn, CreateMembershipIn, GrantIn

_ACTIONS = ("read", "write", "approve", "comment")


def _validate_grants(grants: list[GrantIn]) -> str | None:
    """Returns an error message, or None if every grant is a legal
    (module, action) pair."""
    for g in grants:
        if g.module not in _ALL_MODULES:
            return f"unknown module: {g.module}"
        if g.action not in _ACTIONS:
            return f"unknown action: {g.action}"
    return None


def _group_grants(db: Session, group_id: int) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT module, action FROM group_module_grant "
            "WHERE group_id = :g ORDER BY module, action"
        ),
        {"g": group_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_groups(db: Session, *, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT group_id, name, is_system FROM permission_group "
            "WHERE workspace_id = :w ORDER BY is_system DESC, name"
        ),
        {"w": workspace_id},
    ).mappings().all()
    return [
        {**dict(r), "grants": _group_grants(db, r["group_id"])} for r in rows
    ]


def _get_group_scoped(db: Session, *, group_id: int, workspace_id: int) -> dict | None:
    row = db.execute(
        text(
            "SELECT group_id, name, is_system FROM permission_group "
            "WHERE group_id = :g AND workspace_id = :w"
        ),
        {"g": group_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    return {**dict(row), "grants": _group_grants(db, group_id)}


def create_group(
    db: Session, *, workspace_id: int, payload: CreateGroupIn, actor_id: int
) -> tuple[str, dict]:
    existing = db.execute(
        text(
            "SELECT group_id FROM permission_group "
            "WHERE workspace_id = :w AND name = :n"
        ),
        {"w": workspace_id, "n": payload.name},
    ).scalar()
    if existing is not None:
        return "DUPLICATE", _get_group_scoped(db, group_id=existing, workspace_id=workspace_id)
    row = db.execute(
        text(
            """
            INSERT INTO permission_group (workspace_id, name, is_system)
            VALUES (:w, :n, false)
            RETURNING group_id, name, is_system
            """
        ),
        {"w": workspace_id, "n": payload.name},
    ).mappings().first()
    out = {**dict(row), "grants": []}
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="permission_group.create",
        target=str(out["group_id"]),
        payload={"name": payload.name},
    )
    db.flush()
    return "OK", out


def set_grants(
    db: Session, *, group_id: int, workspace_id: int, grants: list[GrantIn], actor_id: int
) -> tuple[str, dict | None]:
    group = _get_group_scoped(db, group_id=group_id, workspace_id=workspace_id)
    if group is None:
        return "NOT_FOUND", None
    err = _validate_grants(grants)
    if err is not None:
        return "BAD_GRANT", {"error": err}
    db.execute(text("DELETE FROM group_module_grant WHERE group_id = :g"), {"g": group_id})
    seen: set[tuple[str, str]] = set()
    for g in grants:
        key = (g.module, g.action)
        if key in seen:
            continue
        seen.add(key)
        db.execute(
            text(
                "INSERT INTO group_module_grant (group_id, module, action) "
                "VALUES (:g, :m, :a)"
            ),
            {"g": group_id, "m": g.module, "a": g.action},
        )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="permission_group.set_grants",
        target=str(group_id),
        payload={"grants": [[g.module, g.action] for g in grants]},
    )
    db.flush()
    return "OK", _get_group_scoped(db, group_id=group_id, workspace_id=workspace_id)


def delete_group(
    db: Session, *, group_id: int, workspace_id: int, actor_id: int
) -> tuple[str, dict | None]:
    group = _get_group_scoped(db, group_id=group_id, workspace_id=workspace_id)
    if group is None:
        return "NOT_FOUND", None
    if group["is_system"]:
        return "SYSTEM_GROUP", None
    member_count = db.execute(
        text("SELECT count(*) FROM user_group_membership WHERE group_id = :g"),
        {"g": group_id},
    ).scalar()
    if member_count:
        return "HAS_MEMBERS", {"member_count": member_count}
    db.execute(text("DELETE FROM permission_group WHERE group_id = :g"), {"g": group_id})
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="permission_group.delete",
        target=str(group_id),
        payload={"name": group["name"]},
    )
    db.flush()
    return "OK", None


def _membership_row_out(db: Session, membership_id: int) -> dict:
    row = db.execute(
        text(
            """
            SELECT m.membership_id, m.user_id, u.full_name AS user_full_name,
                   m.group_id, g.name AS group_name,
                   m.project_id, p.project_code
              FROM user_group_membership m
              JOIN app_user u ON u.id = m.user_id
              JOIN permission_group g ON g.group_id = m.group_id
              LEFT JOIN projects p ON p.project_id = m.project_id
             WHERE m.membership_id = :mid
            """
        ),
        {"mid": membership_id},
    ).mappings().first()
    return dict(row)


def list_memberships(
    db: Session, *, group_id: int, workspace_id: int
) -> list[dict] | None:
    group = _get_group_scoped(db, group_id=group_id, workspace_id=workspace_id)
    if group is None:
        return None
    rows = db.execute(
        text(
            """
            SELECT m.membership_id, m.user_id, u.full_name AS user_full_name,
                   m.group_id, g.name AS group_name,
                   m.project_id, p.project_code
              FROM user_group_membership m
              JOIN app_user u ON u.id = m.user_id
              JOIN permission_group g ON g.group_id = m.group_id
              LEFT JOIN projects p ON p.project_id = m.project_id
             WHERE m.group_id = :g
             ORDER BY u.full_name, m.project_id
            """
        ),
        {"g": group_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_user_memberships(
    db: Session, *, user_id: int, workspace_id: int
) -> list[dict] | None:
    exists = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :u AND workspace_id = :w"),
        {"u": user_id, "w": workspace_id},
    ).first()
    if exists is None:
        return None
    rows = db.execute(
        text(
            """
            SELECT m.membership_id, m.user_id, u.full_name AS user_full_name,
                   m.group_id, g.name AS group_name,
                   m.project_id, p.project_code
              FROM user_group_membership m
              JOIN app_user u ON u.id = m.user_id
              JOIN permission_group g ON g.group_id = m.group_id
              LEFT JOIN projects p ON p.project_id = m.project_id
             WHERE m.user_id = :u AND g.workspace_id = :w
             ORDER BY g.name, m.project_id
            """
        ),
        {"u": user_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_membership(
    db: Session,
    *,
    group_id: int,
    workspace_id: int,
    payload: CreateMembershipIn,
    actor_id: int,
) -> tuple[str, dict | None]:
    group = _get_group_scoped(db, group_id=group_id, workspace_id=workspace_id)
    if group is None:
        return "GROUP_NOT_FOUND", None
    user_ok = db.execute(
        text("SELECT 1 FROM app_user WHERE id = :u AND workspace_id = :w"),
        {"u": payload.user_id, "w": workspace_id},
    ).first()
    if user_ok is None:
        return "UNKNOWN_USER", None
    if payload.project_id is not None:
        proj_ok = db.execute(
            text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
            {"p": payload.project_id, "w": workspace_id},
        ).first()
        if proj_ok is None:
            return "UNKNOWN_PROJECT", None
    existing = db.execute(
        text(
            """
            SELECT membership_id FROM user_group_membership
             WHERE user_id = :u AND group_id = :g
               AND COALESCE(project_id, 0) = COALESCE(:p, 0)
            """
        ),
        {"u": payload.user_id, "g": group_id, "p": payload.project_id},
    ).scalar()
    if existing is not None:
        return "DUPLICATE", _membership_row_out(db, existing)
    mid = db.execute(
        text(
            """
            INSERT INTO user_group_membership (user_id, group_id, project_id, created_by)
            VALUES (:u, :g, :p, :cb)
            RETURNING membership_id
            """
        ),
        {"u": payload.user_id, "g": group_id, "p": payload.project_id, "cb": actor_id},
    ).scalar()
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="permission_group.membership.create",
        target=str(group_id),
        payload={"user_id": payload.user_id, "project_id": payload.project_id},
    )
    db.flush()
    return "OK", _membership_row_out(db, mid)


def delete_membership(
    db: Session, *, membership_id: int, workspace_id: int, actor_id: int
) -> bool:
    row = db.execute(
        text(
            """
            SELECT m.membership_id, m.group_id, m.user_id, m.project_id
              FROM user_group_membership m
              JOIN permission_group g ON g.group_id = m.group_id
             WHERE m.membership_id = :mid AND g.workspace_id = :w
            """
        ),
        {"mid": membership_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return False
    db.execute(
        text("DELETE FROM user_group_membership WHERE membership_id = :mid"),
        {"mid": membership_id},
    )
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="permission_group.membership.delete",
        target=str(row["group_id"]),
        payload={"user_id": row["user_id"], "project_id": row["project_id"]},
    )
    db.flush()
    return True

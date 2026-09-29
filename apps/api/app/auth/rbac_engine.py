"""DB-backed permission resolution (Plan V1 §3.4, Q466-473).

`effective_actions` is the live source of truth `require_permission` (in
`app.auth.rbac`) consults: the union of `group_module_grant` rows across every
`user_group_membership` the user holds that applies to the target scope —
a membership with `project_id IS NULL` applies workspace-wide, one with a
`project_id` set applies only there. Most-permissive-wins across a user's
groups, per Q466/Q469.

`permissions.MATRIX` is *not* dead: it is the fallback for a user who holds
zero group memberships at all (a row inserted outside migration 0037's
backfill — e.g. by a test's raw SQL `INSERT INTO app_user`, or a workspace
created after this migration ran, which has no seeded system groups to join
against). A user who has at least one membership is fully DB-governed, even
if that membership grants nothing for the module/project asked about — an
empty result for such a user is a real "no", not a signal to fall back.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from .permissions import MATRIX, _ALL_MODULES, permissions_for  # noqa: F401 (re-exported for callers/tests)
from .sessions import AuthUser


def _has_any_membership(db: Session, user_id: int) -> bool:
    return (
        db.execute(
            text("SELECT 1 FROM user_group_membership WHERE user_id = :u LIMIT 1"),
            {"u": user_id},
        ).first()
        is not None
    )


def effective_actions(
    db: Session, user: AuthUser, module: str, project_id: int | None = None
) -> set[str]:
    """The set of actions `user` may perform on `module`, optionally scoped
    to `project_id`.

    `project_id=None` checks workspace-wide grants only — the scope every
    existing call site uses today, and what migration 0037's backfill
    reproduces exactly for every pre-existing user. Passing a real
    `project_id` additionally pulls in grants from memberships scoped to
    that one project.
    """
    rows = db.execute(
        text(
            """
            SELECT DISTINCT g.action
            FROM user_group_membership m
            JOIN group_module_grant g ON g.group_id = m.group_id
            WHERE m.user_id = :uid
              AND g.module = :module
              AND (m.project_id IS NULL OR m.project_id = :pid)
            """
        ),
        {"uid": user.id, "module": module, "pid": project_id},
    ).scalars().all()
    if rows:
        return set(rows)
    if _has_any_membership(db, user.id):
        return set()
    return set(MATRIX.get(user.auth_role, {}).get(module, set()))


def effective_permissions(db: Session, user: AuthUser) -> dict[str, list[str]]:
    """`effective_actions(db, user, m)` for every module, as `{module: sorted
    actions}` — the shape `/auth/me` serves. Workspace-wide grants only: the
    map carries no project, so a project-scoped membership is not represented
    here (the API still honours it wherever a route passes `project_param`).

    One grants query instead of twelve `effective_actions` calls, because
    `/auth/me` runs on every page load. The fallback rule is the same as
    `effective_actions`'s and `test_effective_permissions_agrees_with_effective_actions`
    pins the two together: a module with grants uses them; otherwise a user
    holding any membership gets nothing for it, and a user holding none gets
    the `MATRIX` row.
    """
    rows = db.execute(
        text(
            """
            SELECT g.module, g.action
            FROM user_group_membership m
            JOIN group_module_grant g ON g.group_id = m.group_id
            WHERE m.user_id = :uid AND m.project_id IS NULL
            """
        ),
        {"uid": user.id},
    ).all()
    granted: dict[str, set[str]] = {}
    for module, action in rows:
        granted.setdefault(module, set()).add(action)
    if any(m not in granted for m in _ALL_MODULES) and not _has_any_membership(db, user.id):
        fallback = permissions_for(user.auth_role)
        return {m: sorted(granted[m]) if m in granted else fallback[m] for m in _ALL_MODULES}
    return {m: sorted(granted.get(m, ())) for m in _ALL_MODULES}


def has_permission_db(
    db: Session, user: AuthUser, module: str, action: str, project_id: int | None = None
) -> bool:
    return action in effective_actions(db, user, module, project_id)


def seed_system_groups(db: Session, *, workspace_id: int) -> None:
    """(Re)create the 7 system groups + grants for one workspace, mirroring
    `MATRIX` exactly. Idempotent (safe to call more than once).

    Migration 0037 ran the same seeding as raw SQL, once, for every workspace
    that already existed at the time — a frozen historical snapshot of
    `MATRIX` as it read then. This function is the live equivalent: a
    workspace created after that migration (there is no "create workspace"
    route in v1, so today that means test fixtures only) has no system
    groups until something calls this. Not wired to any automatic trigger,
    deliberately — see CLAUDE.md's Dynamic RBAC engine section.
    """
    for role, per_module in MATRIX.items():
        gid = db.execute(
            text(
                """
                INSERT INTO permission_group (workspace_id, name, is_system)
                VALUES (:w, :n, true)
                ON CONFLICT (workspace_id, name) DO UPDATE SET is_system = true
                RETURNING group_id
                """
            ),
            {"w": workspace_id, "n": role},
        ).scalar()
        for module in _ALL_MODULES:
            for action in per_module.get(module, set()):
                db.execute(
                    text(
                        "INSERT INTO group_module_grant (group_id, module, action) "
                        "VALUES (:g, :m, :a) ON CONFLICT DO NOTHING"
                    ),
                    {"g": gid, "m": module, "a": action},
                )


def swap_default_group_membership(
    db: Session, *, workspace_id: int, user_id: int, old_role: str, new_role: str
) -> None:
    """Move a user's workspace-wide system-group membership from `old_role`'s
    group to `new_role`'s (Q468). `PATCH /users/{uid}` can still change
    `auth_role`; without this, the stale membership would keep granting the
    old role's actions under this engine even after the column changes.

    A no-op where either role has no matching system group in this workspace
    (falls back to `permissions.py`, as always).
    """
    db.execute(
        text(
            """
            DELETE FROM user_group_membership m
            USING permission_group g
            WHERE m.group_id = g.group_id
              AND g.workspace_id = :w AND g.is_system AND g.name = :old
              AND m.user_id = :u AND m.project_id IS NULL
            """
        ),
        {"w": workspace_id, "old": old_role, "u": user_id},
    )
    db.execute(
        text(
            """
            INSERT INTO user_group_membership (user_id, group_id, project_id)
            SELECT :u, g.group_id, NULL
            FROM permission_group g
            WHERE g.workspace_id = :w AND g.is_system AND g.name = :new
            ON CONFLICT (user_id, group_id, COALESCE(project_id, 0)) DO NOTHING
            """
        ),
        {"u": user_id, "w": workspace_id, "new": new_role},
    )

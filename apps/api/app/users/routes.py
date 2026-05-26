from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import current_user, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .schemas import (
    MyStatusPatch,
    TeamMemberOut,
    TeamOut,
    UserOut,
    UserPatch,
    UserShopWorkerPatch,
)

router = APIRouter(prefix="/users", tags=["users"])
me_router = APIRouter(prefix="/me", tags=["me"])
team_router = APIRouter(prefix="/workspace", tags=["workspace"])

_VALID_ROLES = {"admin", "manager", "editor", "drafter", "estimator", "purchase_officer", "viewer"}
_PATCHABLE = ("full_name", "auth_role", "jtbd_role", "is_active")


@router.get("", response_model=list[UserOut])
def list_users(
    user: AuthUser = Depends(require_permission("it_management", "read")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT id, email, full_name, auth_role, jtbd_role,
                   is_active, is_shop_worker
            FROM app_user WHERE workspace_id = :w ORDER BY full_name
            """
        ),
        {"w": user.workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/{uid}", response_model=UserOut)
def patch_user(
    uid: int,
    body: UserPatch,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "no fields")
    # Whitelist guard - keys are static so this is safe to interpolate.
    bad = set(fields) - set(_PATCHABLE)
    if bad:
        raise HTTPException(400, f"unknown fields: {sorted(bad)}")
    if "auth_role" in fields and fields["auth_role"] not in _VALID_ROLES:
        raise HTTPException(400, "bad auth_role")
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "i": uid, "w": user.workspace_id}
    row = db.execute(
        text(
            f"""
            UPDATE app_user SET {sets}
            WHERE id = :i AND workspace_id = :w
            RETURNING id, email, full_name, auth_role, jtbd_role, is_active
            """
        ),
        params,
    ).mappings().first()
    if not row:
        raise HTTPException(404)
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="user.update",
        target=str(uid),
        payload=fields,
    )
    db.commit()
    row_dict = dict(row)
    # Re-read to include is_shop_worker (UPDATE RETURNING above doesn't
    # surface it). Cheap second SELECT.
    extra = db.execute(
        text(
            "SELECT is_shop_worker FROM app_user "
            "WHERE id = :i AND workspace_id = :w"
        ),
        {"i": uid, "w": user.workspace_id},
    ).first()
    row_dict["is_shop_worker"] = bool(extra[0]) if extra else False
    return row_dict


@team_router.get("/team", response_model=TeamOut)
def get_workspace_team(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    """List all workspace members with their current work_status + location.
    Any authenticated user can read. is_self=true on the row matching the caller.
    """
    rows = db.execute(
        text(
            """
            SELECT id, full_name, auth_role, jtbd_role,
                   work_status, location_label
              FROM app_user
             WHERE workspace_id = :w AND is_active = true
             ORDER BY full_name
            """
        ),
        {"w": user.workspace_id},
    ).mappings().all()
    members = [
        TeamMemberOut(
            id=r["id"],
            full_name=r["full_name"],
            auth_role=r["auth_role"],
            jtbd_role=r["jtbd_role"],
            work_status=r["work_status"],
            location_label=r["location_label"],
            is_self=(r["id"] == user.id),
        )
        for r in rows
    ]
    return TeamOut(members=members)


@me_router.patch("/status", response_model=TeamMemberOut)
def patch_my_status(
    body: MyStatusPatch,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Update caller's own work_status + location_label. Authenticated-only
    (no module gate — every user can publish their own status)."""
    row = db.execute(
        text(
            """
            UPDATE app_user
               SET work_status    = :ws,
                   location_label = :loc
             WHERE id = :i AND workspace_id = :w
             RETURNING id, full_name, auth_role, jtbd_role,
                       work_status, location_label
            """
        ),
        {
            "ws": body.work_status,
            "loc": body.location_label,
            "i": user.id,
            "w": user.workspace_id,
        },
    ).mappings().first()
    if not row:
        raise HTTPException(404, "user not found")
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="user.status",
        target=str(user.id),
        payload={
            "work_status": body.work_status,
            "location_label": body.location_label,
        },
    )
    db.commit()
    return TeamMemberOut(
        id=row["id"],
        full_name=row["full_name"],
        auth_role=row["auth_role"],
        jtbd_role=row["jtbd_role"],
        work_status=row["work_status"],
        location_label=row["location_label"],
        is_self=True,
    )


@router.patch("/{uid}/shop-worker", response_model=UserOut)
def patch_user_shop_worker(
    uid: int,
    body: UserShopWorkerPatch,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    """Admin-only toggle of `is_shop_worker`. Powers the /it
    WorkerRosterPanel."""
    row = db.execute(
        text(
            """
            UPDATE app_user
            SET is_shop_worker = :flag
            WHERE id = :i AND workspace_id = :w
            RETURNING id, email, full_name, auth_role, jtbd_role,
                      is_active, is_shop_worker
            """
        ),
        {"flag": body.is_shop_worker, "i": uid, "w": user.workspace_id},
    ).mappings().first()
    if not row:
        raise HTTPException(404, "user not found")
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="it.worker_toggle",
        target=str(uid),
        payload={
            "user_id": uid,
            "is_shop_worker": body.is_shop_worker,
            "by_admin_id": user.id,
        },
    )
    db.commit()
    return dict(row)

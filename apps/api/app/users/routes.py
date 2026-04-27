from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .schemas import UserOut, UserPatch

router = APIRouter(prefix="/users", tags=["users"])

_VALID_ROLES = {"admin", "manager", "editor", "drafter", "purchase_officer", "viewer"}
_PATCHABLE = ("full_name", "auth_role", "jtbd_role", "is_active")


@router.get("", response_model=list[UserOut])
def list_users(
    user: AuthUser = Depends(require_permission("it_management", "read")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """
            SELECT id, email, full_name, auth_role, jtbd_role, is_active
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
    return dict(row)

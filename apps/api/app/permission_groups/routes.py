"""Admin CRUD for the RBAC-engine's groups, grants and memberships (Q466-473).

Gated `it_management`, matching the existing admin-only pattern (worker
roster toggle, `/it/labour-rates`). Read is admin+manager (matrix already
gives manager `it_management:read`); write is admin-only.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import CreateGroupIn, CreateMembershipIn, GroupOut, MembershipOut, SetGrantsIn

router = APIRouter(prefix="/permission-groups", tags=["permission_groups"])


@router.get("", response_model=list[GroupOut])
def list_groups_route(
    user: AuthUser = Depends(require_permission("it_management", "read")),
    db: Session = Depends(get_db),
):
    return q.list_groups(db, workspace_id=user.workspace_id)


@router.post("", response_model=GroupOut, status_code=201)
def create_group_route(
    body: CreateGroupIn,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    outcome, group = q.create_group(db, workspace_id=user.workspace_id, payload=body, actor_id=user.id)
    if outcome == "DUPLICATE":
        raise HTTPException(
            status_code=409,
            detail={"code": "GROUP_EXISTS", "group_id": group["group_id"]},
        )
    db.commit()
    return group


@router.put("/{gid}/grants", response_model=GroupOut)
def set_grants_route(
    gid: int,
    body: SetGrantsIn,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    outcome, result = q.set_grants(
        db, group_id=gid, workspace_id=user.workspace_id, grants=body.grants, actor_id=user.id
    )
    if outcome == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="group not found")
    if outcome == "BAD_GRANT":
        raise HTTPException(status_code=422, detail=result["error"])
    db.commit()
    return result


@router.delete("/{gid}", status_code=204)
def delete_group_route(
    gid: int,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    outcome, result = q.delete_group(db, group_id=gid, workspace_id=user.workspace_id, actor_id=user.id)
    if outcome == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="group not found")
    if outcome == "SYSTEM_GROUP":
        raise HTTPException(status_code=409, detail={"code": "SYSTEM_GROUP"})
    if outcome == "HAS_MEMBERS":
        raise HTTPException(status_code=409, detail={"code": "GROUP_HAS_MEMBERS", **result})
    db.commit()
    return Response(status_code=204)


@router.get("/{gid}/memberships", response_model=list[MembershipOut])
def list_memberships_route(
    gid: int,
    user: AuthUser = Depends(require_permission("it_management", "read")),
    db: Session = Depends(get_db),
):
    rows = q.list_memberships(db, group_id=gid, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="group not found")
    return rows


@router.post("/{gid}/memberships", response_model=MembershipOut, status_code=201)
def create_membership_route(
    gid: int,
    body: CreateMembershipIn,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    outcome, result = q.create_membership(
        db, group_id=gid, workspace_id=user.workspace_id, payload=body, actor_id=user.id
    )
    if outcome == "GROUP_NOT_FOUND":
        raise HTTPException(status_code=404, detail="group not found")
    if outcome == "UNKNOWN_USER":
        raise HTTPException(status_code=422, detail={"code": "UNKNOWN_USER"})
    if outcome == "UNKNOWN_PROJECT":
        raise HTTPException(status_code=422, detail={"code": "UNKNOWN_PROJECT"})
    if outcome == "DUPLICATE":
        raise HTTPException(
            status_code=409,
            detail={"code": "MEMBERSHIP_EXISTS", "membership_id": result["membership_id"]},
        )
    db.commit()
    return result


@router.delete("/memberships/{mid}", status_code=204)
def delete_membership_route(
    mid: int,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
):
    ok = q.delete_membership(db, membership_id=mid, workspace_id=user.workspace_id, actor_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="membership not found")
    db.commit()
    return Response(status_code=204)


@router.get("/users/{uid}/memberships", response_model=list[MembershipOut])
def list_user_memberships_route(
    uid: int,
    user: AuthUser = Depends(require_permission("it_management", "read")),
    db: Session = Depends(get_db),
):
    rows = q.list_user_memberships(db, user_id=uid, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="user not found")
    return rows

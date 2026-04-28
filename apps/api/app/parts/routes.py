"""FastAPI routes for modules + parts CRUD.

6 endpoints:
  POST   /items/{id}/modules          -> create module
  PATCH  /modules/{mid}               -> patch module
  DELETE /modules/{mid}               -> delete module
  POST   /modules/{mid}/parts         -> create part
  PATCH  /parts/{pid}                 -> patch part
  DELETE /parts/{pid}                 -> delete part

All mutations gated by require_drafter() (drafter, manager, admin only).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import current_user, require_drafter
from ..auth.sessions import AuthUser
from ..db import get_db
from ..items.schemas import ModuleOut, PartOut
from .queries import (
    create_module,
    create_part,
    delete_module,
    delete_part,
    get_module,
    get_part,
    patch_module,
    patch_part,
)
from .schemas import CreateModuleIn, CreatePartIn, PatchModuleIn, PatchPartIn

router = APIRouter(prefix="", tags=["parts"])


# ── Module endpoints ───────────────────────────────────────────────────────────


@router.post(
    "/items/{id}/modules",
    response_model=ModuleOut,
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def post_module(
    id: int,
    payload: CreateModuleIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ModuleOut:
    mid = create_module(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if mid is None:
        raise HTTPException(status_code=404, detail="item not found")
    db.commit()
    result = get_module(db, module_id=mid, workspace_id=user.workspace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


@router.patch(
    "/modules/{mid}",
    response_model=ModuleOut,
    dependencies=[Depends(require_drafter())],
)
def patch_module_route(
    mid: int,
    payload: PatchModuleIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ModuleOut:
    result = patch_module(
        db,
        module_id=mid,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="module not found")
    db.commit()
    return result


@router.delete(
    "/modules/{mid}",
    status_code=204,
    dependencies=[Depends(require_drafter())],
)
def delete_module_route(
    mid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    result = delete_module(
        db,
        module_id=mid,
        workspace_id=user.workspace_id,
        actor_id=user.id,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="module not found")
    db.commit()


# ── Part endpoints ─────────────────────────────────────────────────────────────


@router.post(
    "/modules/{mid}/parts",
    response_model=PartOut,
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def post_part(
    mid: int,
    payload: CreatePartIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> PartOut:
    pid = create_part(
        db,
        module_id=mid,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if pid is None:
        raise HTTPException(status_code=404, detail="module not found")
    db.commit()
    result = get_part(db, part_id=pid, workspace_id=user.workspace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="module not found")
    return result


@router.patch(
    "/parts/{pid}",
    response_model=PartOut,
    dependencies=[Depends(require_drafter())],
)
def patch_part_route(
    pid: int,
    payload: PatchPartIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> PartOut:
    result = patch_part(
        db,
        part_id=pid,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="part not found")
    db.commit()
    return result


@router.delete(
    "/parts/{pid}",
    status_code=204,
    dependencies=[Depends(require_drafter())],
)
def delete_part_route(
    pid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    result = delete_part(
        db,
        part_id=pid,
        workspace_id=user.workspace_id,
        actor_id=user.id,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="part not found")
    db.commit()

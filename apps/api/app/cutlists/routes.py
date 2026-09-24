"""Cutlist routes — CRUD plus link / unlink.

RBAC gate is `("list", action)`. Plan V1 **Q474** settled that Cutlist *is* the
existing `List` tab rather than a seventh primary tab, and the RBAC module name
already reflects that — `("list","read")` has gated `cutlist.pdf` since #5b. So
no matrix row is added here (Q432).

Reads need `("list","read")`; every mutation needs `("list","write")`, which is
drafter+ since drafter holds PM-parity on `list`.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CreateCutlistIn,
    CutlistDetailOut,
    CutlistListOut,
    CutlistOut,
    LinkItemIn,
    PatchCutlistIn,
)

router = APIRouter(tags=["cutlists"])


@router.get("/projects/{pid}/cutlists", response_model=CutlistListOut)
def list_cutlists_route(
    pid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    result = q.list_cutlists(db, project_id=pid, workspace_id=user.workspace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    return result


@router.get("/cutlists/{cid}", response_model=CutlistDetailOut)
def get_cutlist_route(
    cid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    result = q.get_cutlist(db, cutlist_id=cid, workspace_id=user.workspace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="cutlist not found")
    return result


@router.post("/projects/{pid}/cutlists", response_model=CutlistOut, status_code=201)
def create_cutlist_route(
    pid: int,
    payload: CreateCutlistIn,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    result = q.create_cutlist(
        db, project_id=pid, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="project not found")
    db.commit()
    return result


@router.patch("/cutlists/{cid}", response_model=CutlistOut)
def patch_cutlist_route(
    cid: int,
    payload: PatchCutlistIn,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    result = q.patch_cutlist(
        db, cutlist_id=cid, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="cutlist not found")
    db.commit()
    return result


@router.delete("/cutlists/{cid}", status_code=204)
def delete_cutlist_route(
    cid: int,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    code = q.delete_cutlist(
        db, cutlist_id=cid, workspace_id=user.workspace_id, actor_id=user.id
    )
    if code == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="cutlist not found")
    if code == "HAS_ITEMS":
        raise HTTPException(
            status_code=409,
            detail={"code": "HAS_ITEMS",
                    "message": "unlink every item before deleting this cutlist"},
        )
    db.commit()
    return None


@router.post("/cutlists/{cid}/items", response_model=CutlistOut)
def link_item_route(
    cid: int,
    payload: LinkItemIn,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    code, detail = q.link_item(
        db, cutlist_id=cid, item_id=payload.item_id,
        workspace_id=user.workspace_id, actor_id=user.id,
    )
    if code == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="cutlist or item not found")
    if code == "RELATED_PART":
        raise HTTPException(
            status_code=409,
            detail={"code": "RELATED_PART",
                    "message": "a related part cannot hold a cutlist number"},
        )
    if code == "WRONG_PROJECT":
        raise HTTPException(
            status_code=409,
            detail={"code": "WRONG_PROJECT",
                    "message": "a cutlist belongs to one project", **(detail or {})},
        )
    if code == "ITEM_HAS_CUTLIST":
        # Q411: surface the cutlist already held, so the UI can offer to move
        # the item rather than making the user go and find it.
        raise HTTPException(
            status_code=409,
            detail={"code": "ITEM_HAS_CUTLIST",
                    "message": "this item is already on a cutlist",
                    **(detail or {})},
        )
    db.commit()
    return detail


@router.delete("/cutlists/{cid}/items/{iid}", status_code=204)
def unlink_item_route(
    cid: int,
    iid: int,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    code = q.unlink_item(
        db, cutlist_id=cid, item_id=iid,
        workspace_id=user.workspace_id, actor_id=user.id,
    )
    if code == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="cutlist or item not found")
    if code == "NOT_LINKED":
        raise HTTPException(
            status_code=409,
            detail={"code": "NOT_LINKED",
                    "message": "this item is not on this cutlist"},
        )
    db.commit()
    return None

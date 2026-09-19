"""Related-part routes (Plan V1 Q416-Q424, Q447-Q453).

**Q423** says the Drafter or the Project Manager may create these. That is
exactly what the existing `require_drafter()` gate already allows
(`drafter`, `manager`, `admin`), so mutations pair it with
`("tracking", "write")` — the same combination every item mutation uses,
since a related part is a Tracking row.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CreateRelatedPartIn,
    PatchRelatedPartIn,
    RelatedPartListOut,
    RelatedPartOut,
    RelatedPartTypeOut,
    ReparentIn,
)

router = APIRouter(tags=["related-parts"])

_PARENT_ERRORS = {
    "PARENT_NOT_FOUND": (404, "parent item not found"),
    "PARENT_IS_RELATED_PART": (
        409, "a related part cannot be a parent — one level only",
    ),
    "UNKNOWN_TYPE": (422, "unknown related-part type"),
    "CROSS_PROJECT": (409, "a related part cannot move to another project"),
    "SAME_PARENT": (409, "already beneath that item"),
}


def _raise(code: str) -> None:
    status, message = _PARENT_ERRORS[code]
    raise HTTPException(status, {"code": code, "message": message})


@router.get("/related-part-types", response_model=list[RelatedPartTypeOut])
def list_types_route(
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    """Q448 — configurable, seeded with metal / benchtop / cushion."""
    return q.list_types(db)


@router.get("/items/{parent_id}/related-parts", response_model=RelatedPartListOut)
def list_route(
    parent_id: int,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    rows = q.list_for_parent(db, parent_item_id=parent_id, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(404, "parent item not found")
    return {"parent_item_id": parent_id, "related_parts": rows}


@router.get("/related-parts/{rid}", response_model=RelatedPartOut)
def get_route(
    rid: int,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    part = q.get_related_part(db, item_id=rid, workspace_id=user.workspace_id)
    if part is None:
        raise HTTPException(404, "related part not found")
    return part


@router.post(
    "/items/{parent_id}/related-parts",
    response_model=RelatedPartOut,
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def create_route(
    parent_id: int,
    payload: CreateRelatedPartIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    code, part = q.create_related_part(
        db, parent_item_id=parent_id, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if code != "OK":
        _raise(code)
    db.commit()
    return part


@router.patch(
    "/related-parts/{rid}",
    response_model=RelatedPartOut,
    dependencies=[Depends(require_drafter())],
)
def patch_route(
    rid: int,
    payload: PatchRelatedPartIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    code, part = q.patch_related_part(
        db, item_id=rid, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if code == "NOT_FOUND":
        raise HTTPException(404, "related part not found")
    if code != "OK":
        _raise(code)
    db.commit()
    return part


@router.post(
    "/related-parts/{rid}/reparent",
    response_model=RelatedPartOut,
    dependencies=[Depends(require_drafter())],
)
def reparent_route(
    rid: int,
    payload: ReparentIn,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    """Q452 — moves the part, its Group ID, and its orders' CUTLIST NO."""
    code, part = q.reparent(
        db, item_id=rid, new_parent_item_id=payload.new_parent_item_id,
        workspace_id=user.workspace_id, actor_id=user.id,
    )
    if code == "NOT_FOUND":
        raise HTTPException(404, "related part not found")
    if code != "OK":
        _raise(code)
    db.commit()
    return part


@router.delete(
    "/related-parts/{rid}",
    status_code=204,
    dependencies=[Depends(require_drafter())],
)
def delete_route(
    rid: int,
    user: AuthUser = Depends(require_permission("tracking", "write")),
    db: Session = Depends(get_db),
):
    code = q.delete_related_part(
        db, item_id=rid, workspace_id=user.workspace_id, actor_id=user.id
    )
    if code == "NOT_FOUND":
        raise HTTPException(404, "related part not found")
    db.commit()
    return None

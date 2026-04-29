"""HTTP routes for /catalogs/{type_} (Procurement Workbench v1, Task 11).

CRUD across the 6 material catalog tables:
  board, hardware, custom_made, benchtop, appliance, hire

RBAC: read = (orderbook, read); writes = (orderbook, write). All mutating
endpoints write a workspace-level audit row keyed on
`target=catalog.<type_>:<mid>`.
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.audit import write_audit
from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from .queries import (
    REGISTRY,
    create_catalog_row,
    delete_catalog_row,
    get_catalog_row,
    list_catalog,
    patch_catalog_row,
)

router = APIRouter(prefix="", tags=["procurement-v1"])

VALID_TYPES = tuple(REGISTRY.keys())


def _validate_type(type_: str) -> None:
    if type_ not in VALID_TYPES:
        raise HTTPException(404, f"Unknown catalog type: {type_}")


@router.get("/catalogs/{type_}")
def list_(
    type_: str,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    return {"type": type_, "rows": list_catalog(db, type_=type_)}


@router.post("/catalogs/{type_}", status_code=201)
def create(
    type_: str,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    try:
        mid = create_catalog_row(db, type_=type_, fields=payload)
    except ValueError as e:
        raise HTTPException(422, str(e))
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="catalog.create",
        target=f"catalog.{type_}:{mid}",
    )
    db.commit()
    out = get_catalog_row(db, type_=type_, mid=mid)
    if out is None:
        raise HTTPException(500, "Created row not visible")
    return out


@router.get("/catalogs/{type_}/{mid}")
def get_one(
    type_: str,
    mid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    row = get_catalog_row(db, type_=type_, mid=mid)
    if row is None:
        raise HTTPException(404, "Catalog row not found")
    return row


@router.patch("/catalogs/{type_}/{mid}")
def patch_one(
    type_: str,
    mid: int,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    if get_catalog_row(db, type_=type_, mid=mid) is None:
        raise HTTPException(404, "Catalog row not found")
    patch_catalog_row(db, type_=type_, mid=mid, fields=payload)
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="catalog.update",
        target=f"catalog.{type_}:{mid}",
    )
    db.commit()
    return get_catalog_row(db, type_=type_, mid=mid)


@router.delete("/catalogs/{type_}/{mid}", status_code=204)
def delete_one(
    type_: str,
    mid: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    if get_catalog_row(db, type_=type_, mid=mid) is None:
        raise HTTPException(404, "Catalog row not found")
    delete_catalog_row(db, type_=type_, mid=mid)
    write_audit(
        db,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event="catalog.delete",
        target=f"catalog.{type_}:{mid}",
    )
    db.commit()
    return None

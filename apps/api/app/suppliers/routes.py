"""Supplier routes — the single v1 surface over `vendors`.

Gated `("orderbook", action)`, matching orders (B6): a supplier exists to be
ordered from. **Q565** retired the legacy `/procurement/vendors*` endpoints in
favour of these, so there is one surface over the table rather than two — the
same convergence #7a made for `/catalogs/*`.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CreateSupplierIn,
    LinkMaterialIn,
    PatchSupplierIn,
    SupplierListOut,
    SupplierOut,
)

router = APIRouter(tags=["suppliers"])

_ERRORS = {
    "UNKNOWN_CATEGORY": (422, "unknown category — see /order-categories"),
    "UNKNOWN_TABLE": (422, "not one of the six catalog tables"),
    "UNKNOWN_FIELD": (422, "field must be supplier_id or default_supplier_id"),
    "MATERIAL_NOT_FOUND": (404, "material not found in this workspace"),
}


def _raise(code: str) -> None:
    status, message = _ERRORS[code]
    raise HTTPException(status, {"code": code, "message": message})


@router.get("/suppliers", response_model=SupplierListOut)
def list_route(
    q_search: str | None = Query(None, alias="q"),
    category: str | None = None,
    status: str | None = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"suppliers": q.list_suppliers(
        db, workspace_id=user.workspace_id,
        q=q_search, category=category, status=status,
    )}


@router.get("/suppliers/{vendor_id}", response_model=SupplierOut)
def get_route(
    vendor_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    supplier = q.get_supplier(db, vendor_id=vendor_id, workspace_id=user.workspace_id)
    if supplier is None:
        raise HTTPException(404, "supplier not found")
    return supplier


@router.get("/suppliers/{vendor_id}/materials")
def linked_materials_route(
    vendor_id: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    """Every catalog row pointing here, across all six tables."""
    rows = q.linked_materials(db, vendor_id=vendor_id, workspace_id=user.workspace_id)
    if rows is None:
        raise HTTPException(404, "supplier not found")
    return {"vendor_id": vendor_id, "materials": rows}


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_route(
    payload: CreateSupplierIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, supplier = q.create_supplier(
        db, workspace_id=user.workspace_id, payload=payload, actor_id=user.id
    )
    if code != "OK":
        _raise(code)
    db.commit()
    return supplier


@router.patch("/suppliers/{vendor_id}", response_model=SupplierOut)
def patch_route(
    vendor_id: int,
    payload: PatchSupplierIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    code, supplier = q.patch_supplier(
        db, vendor_id=vendor_id, workspace_id=user.workspace_id,
        payload=payload, actor_id=user.id,
    )
    if code == "NOT_FOUND":
        raise HTTPException(404, "supplier not found")
    if code != "OK":
        _raise(code)
    db.commit()
    return supplier


@router.post("/suppliers/{vendor_id}/materials", status_code=204)
def link_material_route(
    vendor_id: int,
    payload: LinkMaterialIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    """Q506 — repoint a catalog row's supplier at this vendor.

    The free-text `supplier` / `default_supplier` column is left as it is
    (Q435): the repoint is additive, so an unmatched name stays readable.
    """
    code = q.link_material(
        db, vendor_id=vendor_id, workspace_id=user.workspace_id,
        material_table=payload.material_table, material_id=payload.material_id,
        field=payload.field, actor_id=user.id,
    )
    if code == "NOT_FOUND":
        raise HTTPException(404, "supplier not found")
    if code != "OK":
        _raise(code)
    db.commit()
    return None

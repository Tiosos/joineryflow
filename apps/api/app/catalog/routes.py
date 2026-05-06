"""Catalog HTTP routes — sub-project #7a.

Layout:
1) /catalog/cv-mappings   (literal — must be declared first)
2) /catalog/{slug}        (parameterised — 6 material types via URL_TO_TYPE)
3) /catalog/{slug}/bulk   (literal sub-path)
4) /catalog/{slug}/{mid}/archive

All gated by ("catalog", action). Workspace isolation via
`AuthUser.workspace_id`. Mutations write `audit_log`.
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    BulkImportIn,
    BulkImportOut,
    BulkRowError,
    CreateApplianceIn,
    CreateBenchtopIn,
    CreateBoardIn,
    CreateCustomMadeIn,
    CreateCvMappingIn,
    CreateEquipmentHireIn,
    CreateHardwareIn,
    PatchApplianceIn,
    PatchBenchtopIn,
    PatchBoardIn,
    PatchCustomMadeIn,
    PatchCvMappingIn,
    PatchEquipmentHireIn,
    PatchHardwareIn,
)

router = APIRouter(tags=["catalog"])

URL_TO_TYPE: dict[str, str] = {
    "board-materials":     "board",
    "hardware-materials":  "hardware",
    "custom-made":         "custom_made",
    "benchtop-materials":  "benchtop",
    "appliances":          "appliance",
    "equipment-hire":      "hire",
}


def _resolve_type(slug: str) -> str:
    if slug not in URL_TO_TYPE:
        raise HTTPException(404, f"Unknown catalog slug: {slug}")
    return URL_TO_TYPE[slug]


# ============================================================
# CV mappings (declared FIRST so the literal path wins routing)
# ============================================================

@router.get("/catalog/cv-mappings")
def list_cv_mappings_route(
    q_search: str | None = Query(None, alias="q"),
    user: AuthUser = Depends(require_permission("catalog", "read")),
    db: Session = Depends(get_db),
):
    return q.list_cv_mappings(db, workspace_id=user.workspace_id, q=q_search)


@router.post("/catalog/cv-mappings", status_code=201)
def create_cv_mapping_route(
    body: CreateCvMappingIn,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    try:
        mid = q.create_cv_mapping(
            db, payload=body.model_dump(), actor_id=user.id, workspace_id=user.workspace_id,
        )
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"cv_code already mapped: {e.orig}")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cv_material_mapping.create",
        target=f"cv_material_mapping:{mid}",
        payload={"cv_code": body.cv_code, "target_material_table": body.target_material_table},
    )
    db.commit()
    return q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id)


@router.patch("/catalog/cv-mappings/{mid}")
def patch_cv_mapping_route(
    mid: int,
    body: PatchCvMappingIn,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    if q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Mapping not found")
    fields = body.model_dump(exclude_none=True)
    try:
        q.patch_cv_mapping(db, mid=mid, fields=fields, workspace_id=user.workspace_id)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"cv_code already mapped: {e.orig}")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cv_material_mapping.update",
        target=f"cv_material_mapping:{mid}", payload=fields,
    )
    db.commit()
    return q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id)


@router.delete("/catalog/cv-mappings/{mid}", status_code=204)
def delete_cv_mapping_route(
    mid: int,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    if q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Mapping not found")
    q.delete_cv_mapping(db, mid=mid, workspace_id=user.workspace_id)
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cv_material_mapping.delete",
        target=f"cv_material_mapping:{mid}",
    )
    db.commit()
    return None


# ============================================================
# Generic 6-table sub-routers
# ============================================================

@router.get("/catalog/{slug}")
def list_catalog_route(
    slug: str,
    q_search: str | None = Query(None, alias="q"),
    supplier: str | None = None,
    archived: bool = False,
    user: AuthUser = Depends(require_permission("catalog", "read")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    rows = q.list_catalog(
        db, type_=type_, workspace_id=user.workspace_id,
        q=q_search, supplier=supplier, archived=archived,
    )
    return {"type": type_, "rows": rows}


@router.post("/catalog/{slug}/bulk", response_model=BulkImportOut)
def bulk_import_route(
    slug: str,
    body: BulkImportIn,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    """All-or-nothing: validate every row first; insert only if all clean."""
    type_ = _resolve_type(slug)
    schema_cls = {
        "board": CreateBoardIn, "hardware": CreateHardwareIn,
        "custom_made": CreateCustomMadeIn, "benchtop": CreateBenchtopIn,
        "appliance": CreateApplianceIn, "hire": CreateEquipmentHireIn,
    }[type_]

    errors: list[BulkRowError] = []
    validated_rows: list[dict] = []
    for i, raw in enumerate(body.rows):
        try:
            v = schema_cls.model_validate(raw).model_dump()
        except Exception as e:
            errors.append(BulkRowError(row_index=i, error=str(e)))
            continue
        validated_rows.append(v)

    if errors:
        return BulkImportOut(created=0, errors=errors)

    created = 0
    for i, v in enumerate(validated_rows):
        try:
            q.create_catalog_row(
                db, type_=type_, fields=v, workspace_id=user.workspace_id
            )
            created += 1
        except IntegrityError as e:
            db.rollback()
            return BulkImportOut(
                created=0,
                errors=[BulkRowError(row_index=i, error=f"unique constraint: {e.orig}")],
            )

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.csv_import", target=f"catalog.{type_}:bulk",
        payload={"created": created},
    )
    db.commit()
    return BulkImportOut(created=created, errors=[])


@router.get("/catalog/{slug}/{mid}")
def get_catalog_row_route(
    slug: str, mid: int,
    user: AuthUser = Depends(require_permission("catalog", "read")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    row = q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(404, "Catalog row not found")
    return row


@router.post("/catalog/{slug}", status_code=201)
def create_catalog_row_route(
    slug: str,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    schema_cls = {
        "board": CreateBoardIn, "hardware": CreateHardwareIn,
        "custom_made": CreateCustomMadeIn, "benchtop": CreateBenchtopIn,
        "appliance": CreateApplianceIn, "hire": CreateEquipmentHireIn,
    }[type_]
    try:
        validated = schema_cls.model_validate(payload).model_dump()
    except Exception as e:
        raise HTTPException(422, str(e))
    try:
        mid = q.create_catalog_row(
            db, type_=type_, fields=validated, workspace_id=user.workspace_id
        )
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"unique constraint: {e.orig}")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.create", target=f"catalog.{type_}:{mid}",
    )
    db.commit()
    return q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)


@router.patch("/catalog/{slug}/{mid}")
def patch_catalog_row_route(
    slug: str, mid: int,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    if q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Catalog row not found")
    schema_cls = {
        "board": PatchBoardIn, "hardware": PatchHardwareIn,
        "custom_made": PatchCustomMadeIn, "benchtop": PatchBenchtopIn,
        "appliance": PatchApplianceIn, "hire": PatchEquipmentHireIn,
    }[type_]
    try:
        validated = schema_cls.model_validate(payload).model_dump(exclude_none=True)
    except Exception as e:
        raise HTTPException(422, str(e))
    q.patch_catalog_row(
        db, type_=type_, mid=mid, fields=validated, workspace_id=user.workspace_id,
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.update", target=f"catalog.{type_}:{mid}",
        payload=validated,
    )
    db.commit()
    return q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)


@router.post("/catalog/{slug}/{mid}/archive")
def archive_catalog_row_route(
    slug: str, mid: int,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    rid = q.archive_catalog_row(
        db, type_=type_, mid=mid, actor_id=user.id, workspace_id=user.workspace_id,
    )
    if rid is None:
        if q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id) is None:
            raise HTTPException(404, "Catalog row not found")
        raise HTTPException(409, "already archived")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.archive", target=f"catalog.{type_}:{mid}",
    )
    db.commit()
    return q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)

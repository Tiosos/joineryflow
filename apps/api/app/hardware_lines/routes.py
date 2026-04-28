from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import current_user, require_drafter, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..items.schemas import HardwareLineOut
from ..projects.queries import get_project
from .queries import (
    _ALLOWED_SOURCE_TABLES,
    add_to_catalog,
    create_hardware_line,
    delete_hardware_line,
    get_hardware_line,
    list_catalog,
    list_source_catalog,
    patch_hardware_line,
    remove_from_catalog,
)
from .schemas import (
    AddCatalogIn,
    CreateHardwareLineIn,
    HardwareCatalogOut,
    PatchHardwareLineIn,
)

router = APIRouter(prefix="", tags=["hardware_lines"])


@router.get("/projects/{pid}/hardware_catalog", response_model=HardwareCatalogOut)
def get_catalog(
    pid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    if get_project(db, project_id=pid, workspace_id=user.workspace_id,
                   current_user_id=user.id) is None:
        raise HTTPException(404, "project not found")
    rows = list_catalog(db, workspace_id=user.workspace_id, project_id=pid)
    return {"project_id": pid, "rows": rows}


@router.post(
    "/projects/{pid}/hardware_catalog",
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def post_catalog(
    pid: int,
    payload: AddCatalogIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    cid = add_to_catalog(
        db,
        project_id=pid,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if cid is None:
        raise HTTPException(404, "project or source row not found")
    db.commit()
    return {"catalog_id": cid}


@router.delete(
    "/projects/{pid}/hardware_catalog/{cid}",
    status_code=204,
    dependencies=[Depends(require_drafter())],
)
def delete_catalog(
    pid: int,
    cid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    result = remove_from_catalog(
        db,
        catalog_id=cid,
        workspace_id=user.workspace_id,
        actor_id=user.id,
    )
    if result == "IN_USE":
        raise HTTPException(409, "catalog row referenced by item_hardware_lines")
    if result == "NOT_FOUND":
        raise HTTPException(404, "catalog row not found")
    db.commit()


@router.post(
    "/items/{id}/hardware_lines",
    response_model=HardwareLineOut,
    status_code=201,
    dependencies=[Depends(require_drafter())],
)
def post_hardware_line(
    id: int,
    payload: CreateHardwareLineIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    lid = create_hardware_line(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if lid is None:
        raise HTTPException(404, "item or catalog not found or catalog not in same project")
    db.commit()
    row = get_hardware_line(db, line_id=lid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(500, "line created but could not be retrieved")
    return row


@router.patch(
    "/hardware_lines/{lid}",
    response_model=HardwareLineOut,
    dependencies=[Depends(require_drafter())],
)
def patch_hardware_line_route(
    lid: int,
    payload: PatchHardwareLineIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = patch_hardware_line(
        db,
        line_id=lid,
        workspace_id=user.workspace_id,
        payload=payload,
        actor_id=user.id,
    )
    if row is None:
        raise HTTPException(404, "hardware line not found")
    db.commit()
    return row


@router.delete(
    "/hardware_lines/{lid}",
    status_code=204,
    dependencies=[Depends(require_drafter())],
)
def delete_hardware_line_route(
    lid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    result = delete_hardware_line(
        db,
        line_id=lid,
        workspace_id=user.workspace_id,
        actor_id=user.id,
    )
    if result == "NOT_FOUND":
        raise HTTPException(404, "hardware line not found")
    db.commit()


@router.get("/source_catalog/{table}")
def list_source_catalog_route(
    table: str,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    if table not in _ALLOWED_SOURCE_TABLES:
        raise HTTPException(400, "unknown source table")
    rows = list_source_catalog(db, table=table, workspace_id=user.workspace_id)
    return {"table": table, "rows": rows}

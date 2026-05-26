"""HTTP routes for the estimating module — sub-project #9a.

All routes gated by `("estimating", action)` via require_permission. The
`approve` action gates lock-and-send + Convert-to-Project. Labour rates
sit under `it_management` (admin-only).
"""
from __future__ import annotations

import json
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import pdf as pdf_engine
from . import queries as q
from .schemas import (
    AddHardwareIn,
    AddPartIn,
    ConvertResultOut,
    CreateCustomerIn,
    CreateEstimateIn,
    CreateLineIn,
    CustomerOut,
    EstimateDetailOut,
    EstimateListOut,
    EstimateSummaryOut,
    ExpireIn,
    LabourRateOut,
    LineHardwareOut,
    LineOut,
    LinePartOut,
    PatchCustomerIn,
    PatchEstimateIn,
    PatchHardwareIn,
    PatchLabourRatesIn,
    PatchLineIn,
    PatchPartIn,
    PatchRevisionIn,
    RejectIn,
    ReorderLinesIn,
    RevisionDetailOut,
    UpsertLabourIn,
    WithdrawIn,
)


router = APIRouter(tags=["estimating"])


def _decode_value_error(exc: ValueError) -> dict:
    msg = str(exc)
    if msg.startswith("{"):
        try:
            return json.loads(msg)
        except json.JSONDecodeError:
            pass
    return {"code": msg}


def _find_line(detail: dict, line_id: int) -> LineOut:
    for l in detail["lines"]:
        if int(l["line_id"]) == int(line_id):
            return LineOut(**l)
    raise HTTPException(500, "line not found in revision detail")


# ============================================================================
# Customer CRUD
# ============================================================================

@router.get("/customers")
def list_customers_route(
    q_text: str | None = Query(default=None, alias="q"),
    include_archived: bool = Query(default=False),
    user: AuthUser = Depends(require_permission("estimating", "read")),
    db: Session = Depends(get_db),
) -> list[CustomerOut]:
    rows = q.list_customers(
        db, workspace_id=user.workspace_id, q=q_text,
        include_archived=include_archived,
    )
    return [CustomerOut(**r) for r in rows]


@router.get("/customers/{cid}")
def get_customer_route(
    cid: int,
    user: AuthUser = Depends(require_permission("estimating", "read")),
    db: Session = Depends(get_db),
) -> CustomerOut:
    row = q.get_customer(db, customer_id=cid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(404, "customer not found")
    return CustomerOut(**row)


@router.post("/customers", status_code=201)
def create_customer_route(
    body: CreateCustomerIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> CustomerOut:
    try:
        cid = q.create_customer(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            payload=body.model_dump(),
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, {"code": "DUPLICATE_NAME"})
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="customer.create", target=str(cid),
        payload={"name": body.name},
    )
    db.commit()
    row = q.get_customer(db, customer_id=cid, workspace_id=user.workspace_id)
    return CustomerOut(**row)


@router.patch("/customers/{cid}")
def patch_customer_route(
    cid: int,
    body: PatchCustomerIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> CustomerOut:
    fields = body.model_dump(exclude_unset=True)
    try:
        row = q.patch_customer(
            db, customer_id=cid, workspace_id=user.workspace_id,
            actor_id=user.id, fields=fields,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, {"code": "DUPLICATE_NAME"})
    if row is None:
        raise HTTPException(404, "customer not found")
    db.commit()
    return CustomerOut(**row)


@router.post("/customers/{cid}/archive")
def archive_customer_route(
    cid: int,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> CustomerOut:
    try:
        row = q.archive_customer(
            db, customer_id=cid, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if row is None:
        raise HTTPException(404, "customer not found")
    db.commit()
    return CustomerOut(**row)


# ============================================================================
# Estimate header + list
# ============================================================================

@router.get("/estimates")
def list_estimates_route(
    subtab: str = Query(default="active"),
    customer_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    q_text: str | None = Query(default=None, alias="q"),
    user: AuthUser = Depends(require_permission("estimating", "read")),
    db: Session = Depends(get_db),
) -> EstimateListOut:
    rows = q.list_estimates(
        db, workspace_id=user.workspace_id,
        customer_id=customer_id, status=status, q=q_text, subtab=subtab,
    )
    return EstimateListOut(estimates=[EstimateSummaryOut(**r) for r in rows])


@router.get("/estimates/{eid}")
def get_estimate_route(
    eid: int,
    user: AuthUser = Depends(require_permission("estimating", "read")),
    db: Session = Depends(get_db),
) -> EstimateDetailOut:
    row = q.estimate_detail(
        db, estimate_id=eid, workspace_id=user.workspace_id
    )
    if row is None:
        raise HTTPException(404, "estimate not found")
    return EstimateDetailOut(
        estimate_id=row["estimate_id"],
        estimate_no=row["estimate_no"],
        title=row["title"],
        site_address=row.get("site_address"),
        customer=CustomerOut(**row["customer"]),
        current_revision_id=row.get("current_revision_id"),
        revisions=[RevisionDetailOut(**r) for r in row["revisions"]],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/estimates", status_code=201)
def create_estimate_route(
    body: CreateEstimateIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> EstimateDetailOut:
    try:
        eid = q.create_estimate(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            payload=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, {"code": "DUPLICATE_ESTIMATE_NO"})
    db.commit()
    detail = q.estimate_detail(
        db, estimate_id=eid, workspace_id=user.workspace_id
    )
    return EstimateDetailOut(
        estimate_id=detail["estimate_id"],
        estimate_no=detail["estimate_no"],
        title=detail["title"],
        site_address=detail.get("site_address"),
        customer=CustomerOut(**detail["customer"]),
        current_revision_id=detail.get("current_revision_id"),
        revisions=[RevisionDetailOut(**r) for r in detail["revisions"]],
        created_at=detail["created_at"],
        updated_at=detail["updated_at"],
    )


@router.patch("/estimates/{eid}")
def patch_estimate_route(
    eid: int,
    body: PatchEstimateIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> EstimateSummaryOut:
    fields = body.model_dump(exclude_unset=True)
    try:
        row = q.patch_estimate(
            db, estimate_id=eid, workspace_id=user.workspace_id,
            actor_id=user.id, fields=fields,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if row is None:
        raise HTTPException(404, "estimate not found")
    db.commit()
    return EstimateSummaryOut(**row)


# ============================================================================
# Revision lifecycle
# ============================================================================

@router.post("/estimates/{eid}/revise", status_code=201)
def revise_route(
    eid: int,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    try:
        rid = q.revise_estimate(
            db, estimate_id=eid, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except ValueError as exc:
        decoded = _decode_value_error(exc)
        if decoded.get("code") == "NOT_FOUND":
            raise HTTPException(404, decoded)
        raise HTTPException(409, decoded)
    db.commit()
    detail = q.revision_detail(
        db, revision_id=rid, workspace_id=user.workspace_id
    )
    return RevisionDetailOut(**detail)


@router.get("/estimates/{eid}/revisions/{rid}")
def get_revision_route(
    eid: int, rid: int,
    user: AuthUser = Depends(require_permission("estimating", "read")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    detail = q.revision_detail(
        db, revision_id=rid, workspace_id=user.workspace_id
    )
    if detail is None or detail.get("estimate_id") != eid:
        raise HTTPException(404, "revision not found")
    return RevisionDetailOut(**detail)


@router.patch("/revisions/{rid}")
def patch_revision_route(
    rid: int,
    body: PatchRevisionIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    fields = body.model_dump(exclude_unset=True)
    try:
        row = q.patch_revision(
            db, revision_id=rid, workspace_id=user.workspace_id,
            actor_id=user.id, fields=fields,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if row is None:
        raise HTTPException(404, "revision not found")
    db.commit()
    detail = q.revision_detail(
        db, revision_id=rid, workspace_id=user.workspace_id
    )
    return RevisionDetailOut(**detail)


def _transition_route(
    rid: int, user: AuthUser, db: Session,
    target: str, lost_reason: str | None,
) -> RevisionDetailOut:
    try:
        q.transition_revision(
            db, revision_id=rid, workspace_id=user.workspace_id,
            actor_id=user.id, target=target, lost_reason=lost_reason,
        )
    except ValueError as exc:
        decoded = _decode_value_error(exc)
        if decoded.get("code") == "NOT_FOUND":
            raise HTTPException(404, decoded)
        raise HTTPException(409, decoded)
    db.commit()
    detail = q.revision_detail(
        db, revision_id=rid, workspace_id=user.workspace_id
    )
    if detail is None:
        raise HTTPException(404, "revision not found after transition")
    return RevisionDetailOut(**detail)


@router.post("/revisions/{rid}/send")
def send_revision_route(
    rid: int,
    user: AuthUser = Depends(require_permission("estimating", "approve")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    return _transition_route(rid, user, db, target="sent", lost_reason=None)


@router.post("/revisions/{rid}/accept")
def accept_revision_route(
    rid: int,
    user: AuthUser = Depends(require_permission("estimating", "approve")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    return _transition_route(rid, user, db, target="accepted", lost_reason=None)


@router.post("/revisions/{rid}/reject")
def reject_revision_route(
    rid: int,
    body: RejectIn,
    user: AuthUser = Depends(require_permission("estimating", "approve")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    return _transition_route(rid, user, db, target="rejected",
                             lost_reason=body.lost_reason)


@router.post("/revisions/{rid}/expire")
def expire_revision_route(
    rid: int,
    body: ExpireIn,
    user: AuthUser = Depends(require_permission("estimating", "approve")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    return _transition_route(rid, user, db, target="expired",
                             lost_reason=body.lost_reason)


@router.post("/revisions/{rid}/withdraw")
def withdraw_revision_route(
    rid: int,
    body: WithdrawIn,
    user: AuthUser = Depends(require_permission("estimating", "approve")),
    db: Session = Depends(get_db),
) -> RevisionDetailOut:
    return _transition_route(rid, user, db, target="withdrawn",
                             lost_reason=body.lost_reason)


# ============================================================================
# Convert-to-Project
# ============================================================================

@router.post("/revisions/{rid}/convert")
def convert_revision_route(
    rid: int,
    user: AuthUser = Depends(require_permission("estimating", "approve")),
    db: Session = Depends(get_db),
) -> ConvertResultOut:
    try:
        result = q.convert_to_project(
            db, revision_id=rid, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except ValueError as exc:
        decoded = _decode_value_error(exc)
        if decoded.get("code") == "NOT_FOUND":
            raise HTTPException(404, decoded)
        raise HTTPException(409, decoded)
    db.commit()
    return ConvertResultOut(**result)


# ============================================================================
# Lines + breakdown — draft-only
# ============================================================================

@router.post("/revisions/{rid}/lines", status_code=201)
def create_line_route(
    rid: int,
    body: CreateLineIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> LineOut:
    try:
        lid = q.create_line(
            db, revision_id=rid, workspace_id=user.workspace_id,
            actor_id=user.id, payload=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    db.commit()
    detail = q.revision_detail(
        db, revision_id=rid, workspace_id=user.workspace_id
    )
    return _find_line(detail, lid)


@router.patch("/lines/{lid}")
def patch_line_route(
    lid: int,
    body: PatchLineIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> LineOut:
    payload = body.model_dump(exclude_unset=True)
    clear_override = payload.pop("clear_unit_sell_override", False)
    try:
        row = q.patch_line(
            db, line_id=lid, workspace_id=user.workspace_id,
            actor_id=user.id, fields=payload,
            clear_unit_sell_override=bool(clear_override),
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if row is None:
        raise HTTPException(404, "line not found")
    db.commit()
    detail = q.revision_detail(
        db, revision_id=row["revision_id"], workspace_id=user.workspace_id
    )
    return _find_line(detail, lid)


@router.delete("/lines/{lid}", status_code=200)
def delete_line_route(
    lid: int,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ok = q.delete_line(
            db, line_id=lid, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if not ok:
        raise HTTPException(404, "line not found")
    db.commit()
    return {"ok": True}


@router.post("/revisions/{rid}/lines/reorder")
def reorder_lines_route(
    rid: int,
    body: ReorderLinesIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        q.reorder_lines(
            db, revision_id=rid, workspace_id=user.workspace_id,
            actor_id=user.id, ordered_line_ids=body.ordered_line_ids,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    db.commit()
    return {"ok": True}


@router.post("/lines/{lid}/parts", status_code=201)
def add_part_route(
    lid: int,
    body: AddPartIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> LinePartOut:
    try:
        pid = q.add_part(
            db, line_id=lid, workspace_id=user.workspace_id,
            actor_id=user.id, payload=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    db.commit()
    line = q._line_in_workspace(
        db, line_id=lid, workspace_id=user.workspace_id
    )
    detail = q.revision_detail(
        db, revision_id=line["revision_id"], workspace_id=user.workspace_id
    )
    line_out = _find_line(detail, lid)
    for p in line_out.parts:
        if p.part_id == pid:
            return p
    raise HTTPException(500, "part inserted but not visible")


@router.delete("/estimate-parts/{pid}")
def remove_part_route(
    pid: int,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ok = q.remove_part(
            db, part_id=pid, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if not ok:
        raise HTTPException(404, "part not found")
    db.commit()
    return {"ok": True}


@router.patch("/estimate-parts/{pid}")
def patch_part_route(
    pid: int,
    body: PatchPartIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> LinePartOut:
    fields = body.model_dump(exclude_unset=True)
    try:
        row = q.patch_part(
            db, part_id=pid, workspace_id=user.workspace_id,
            actor_id=user.id, fields=fields,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if row is None:
        raise HTTPException(404, "part not found")
    db.commit()
    detail = q.revision_detail(
        db, revision_id=int(row["revision_id"]),
        workspace_id=user.workspace_id,
    )
    line_out = _find_line(detail, int(row["line_id"]))
    for p in line_out.parts:
        if p.part_id == pid:
            return p
    raise HTTPException(500, "part updated but not visible")


@router.post("/lines/{lid}/hardware", status_code=201)
def add_hardware_route(
    lid: int,
    body: AddHardwareIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> LineHardwareOut:
    try:
        hid = q.add_hardware(
            db, line_id=lid, workspace_id=user.workspace_id,
            actor_id=user.id, payload=body.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    db.commit()
    line = q._line_in_workspace(
        db, line_id=lid, workspace_id=user.workspace_id
    )
    detail = q.revision_detail(
        db, revision_id=line["revision_id"], workspace_id=user.workspace_id
    )
    line_out = _find_line(detail, lid)
    for h in line_out.hardware:
        if h.hw_id == hid:
            return h
    raise HTTPException(500, "hardware inserted but not visible")


@router.delete("/hardware/{hid}")
def remove_hardware_route(
    hid: int,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ok = q.remove_hardware(
            db, hw_id=hid, workspace_id=user.workspace_id,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if not ok:
        raise HTTPException(404, "hardware not found")
    db.commit()
    return {"ok": True}


@router.patch("/hardware/{hid}")
def patch_hardware_route(
    hid: int,
    body: PatchHardwareIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> LineHardwareOut:
    fields = body.model_dump(exclude_unset=True)
    try:
        row = q.patch_hardware(
            db, hw_id=hid, workspace_id=user.workspace_id,
            actor_id=user.id, fields=fields,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    if row is None:
        raise HTTPException(404, "hardware not found")
    db.commit()
    detail = q.revision_detail(
        db, revision_id=int(row["revision_id"]),
        workspace_id=user.workspace_id,
    )
    line_out = _find_line(detail, int(row["line_id"]))
    for h in line_out.hardware:
        if h.hw_id == hid:
            return h
    raise HTTPException(500, "hardware updated but not visible")


@router.post("/lines/{lid}/labour")
def upsert_labour_route(
    lid: int,
    body: UpsertLabourIn,
    user: AuthUser = Depends(require_permission("estimating", "write")),
    db: Session = Depends(get_db),
) -> LineOut:
    try:
        q.upsert_labour(
            db, line_id=lid, workspace_id=user.workspace_id,
            actor_id=user.id, stage_key=body.stage_key, hours=body.hours,
        )
    except ValueError as exc:
        raise HTTPException(409, _decode_value_error(exc))
    db.commit()
    line = q._line_in_workspace(
        db, line_id=lid, workspace_id=user.workspace_id
    )
    if line is None:
        raise HTTPException(404, "line not found")
    detail = q.revision_detail(
        db, revision_id=line["revision_id"], workspace_id=user.workspace_id
    )
    return _find_line(detail, lid)


# ============================================================================
# Workspace labour rates (admin-only)
# ============================================================================

@router.get("/it/labour-rates")
def get_labour_rates_route(
    user: AuthUser = Depends(require_permission("it_management", "read")),
    db: Session = Depends(get_db),
) -> list[LabourRateOut]:
    rows = q.list_labour_rates(db, workspace_id=user.workspace_id)
    return [LabourRateOut(**r) for r in rows]


@router.patch("/it/labour-rates")
def patch_labour_rates_route(
    body: PatchLabourRatesIn,
    user: AuthUser = Depends(require_permission("it_management", "write")),
    db: Session = Depends(get_db),
) -> list[LabourRateOut]:
    try:
        rows = q.patch_labour_rates(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            rates=[r.model_dump() for r in body.rates],
        )
    except ValueError as exc:
        raise HTTPException(422, _decode_value_error(exc))
    db.commit()
    return [LabourRateOut(**r) for r in rows]


# ============================================================================
# Quote PDF
# ============================================================================

@router.get("/revisions/{rid}/quote.pdf")
def quote_pdf_route(
    rid: int,
    user: AuthUser = Depends(require_permission("estimating", "read")),
    db: Session = Depends(get_db),
) -> Response:
    detail = q.revision_detail(
        db, revision_id=rid, workspace_id=user.workspace_id
    )
    if detail is None:
        raise HTTPException(404, "revision not found")
    is_draft = detail["status"] == "draft"
    estimate = q.estimate_detail(
        db, estimate_id=detail["estimate_id"], workspace_id=user.workspace_id
    )
    pdf_bytes = pdf_engine.render_quote_pdf(
        estimate=estimate, revision=detail, is_draft=is_draft,
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="estimate.print", target=str(rid),
        payload={"byte_size": len(pdf_bytes)},
    )
    db.commit()
    raw_name = f"{estimate['estimate_no']}-r{detail['rev_no']}.pdf"
    ascii_fallback = raw_name.encode("ascii", errors="replace").decode("ascii").replace('"', "_")
    encoded_name = urllib.parse.quote(raw_name, safe="")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'inline; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{encoded_name}"
            ),
            "Cache-Control": "no-store",
            "Content-Length": str(len(pdf_bytes)),
        },
    )

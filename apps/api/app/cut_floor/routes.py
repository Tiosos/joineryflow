"""cut_floor HTTP routes — sub-project #7c.

Two surfaces:
  CutPlan: /projects/{pid}/cut-plans, /cut-plans/{plan_id},
           /items/{iid}/cut-plan
  CutSchedule: /cut-schedules (?date=...&project_id=&status=),
               /cut-schedules/{sid},  /cut-schedules/reorder

All gated by ("cut_floor", action). Workspace isolation via
`cut_plan.workspace_id`; `assigned_to` is separately validated against
`app_user.workspace_id` (see queries.user_in_workspace) since it is a plain
FK with no workspace check of its own. Audit on every mutation.
"""
from __future__ import annotations

from datetime import date as date_t

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import inventory_queries as inv
from . import optimiser as opt
from . import queries as q
from .schemas import (
    BoardInventoryIn,
    BoardInventoryOut,
    BoardInventoryPatchIn,
    CutPlanIn,
    CutPlanOut,
    CutPlanSummary,
    CutScheduleIn,
    CutSchedulePatchIn,
    CutScheduleOut,
    CutSheetIn,
    ItemCutPlanOut,
    OptimiseIn,
    OptimiseOut,
    OptimiseSummary,
    PartSlotIn,
    ReorderIn,
)


router = APIRouter(tags=["cut_floor"])


# ============================================================================
# CutPlan
# ============================================================================

@router.post("/projects/{pid}/cut-plans", status_code=201)
def create_cut_plan_route(
    pid: int,
    body: CutPlanIn,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> CutPlanOut:
    if not q.project_in_workspace(db, project_id=pid, workspace_id=user.workspace_id):
        raise HTTPException(404, "project not found")

    plan_id = q.insert_cut_plan(
        db,
        workspace_id=user.workspace_id,
        project_id=pid,
        name=body.name,
        notes=body.notes,
        actor_id=user.id,
    )

    sheets_summary = []
    for sheet in body.sheets:
        sheet_id = q.insert_cut_sheet(
            db,
            cut_plan_id=plan_id,
            sheet_no=sheet.sheet_no,
            material_sku=sheet.material_sku,
        )
        slot_count = 0
        for slot in sheet.slots:
            q.insert_part_slot(
                db,
                cut_sheet_id=sheet_id,
                x=slot.x, y=slot.y, w=slot.w, h=slot.h,
                label=slot.label, part_id=slot.part_id,
            )
            slot_count += 1
        sheets_summary.append({"sheet_no": sheet.sheet_no, "slots": slot_count})

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cut_plan.create", target=str(plan_id),
        payload={
            "plan_id": plan_id,
            "project_id": pid,
            "name": body.name,
            "sheets": sheets_summary,
        },
    )

    out = q.get_cut_plan(db, workspace_id=user.workspace_id, plan_id=plan_id)
    db.commit()
    return CutPlanOut(**out)


@router.get("/projects/{pid}/cut-plans")
def list_cut_plans_route(
    pid: int,
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> list[CutPlanSummary]:
    if not q.project_in_workspace(db, project_id=pid, workspace_id=user.workspace_id):
        raise HTTPException(404, "project not found")
    rows = q.list_cut_plans_for_project(
        db, workspace_id=user.workspace_id, project_id=pid
    )
    return [CutPlanSummary(**r) for r in rows]


@router.get("/cut-plans/{plan_id}")
def get_cut_plan_route(
    plan_id: int,
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> CutPlanOut:
    plan = q.get_cut_plan(db, workspace_id=user.workspace_id, plan_id=plan_id)
    if plan is None:
        raise HTTPException(404, "cut plan not found")
    return CutPlanOut(**plan)


@router.get("/items/{iid}/cut-plan")
def get_item_cut_plan_route(
    iid: int,
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> ItemCutPlanOut:
    proj_id = q.item_project(db, item_id=iid, workspace_id=user.workspace_id)
    if proj_id is None:
        raise HTTPException(404, "item not found")
    payload = q.get_latest_plan_for_item(
        db, workspace_id=user.workspace_id, item_id=iid
    )
    return ItemCutPlanOut(**payload)


@router.delete("/cut-plans/{plan_id}", status_code=204)
def delete_cut_plan_route(
    plan_id: int,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
):
    if not q.plan_in_workspace(
        db, workspace_id=user.workspace_id, plan_id=plan_id
    ):
        raise HTTPException(404, "cut plan not found")
    if q.has_active_schedules(db, plan_id=plan_id):
        raise HTTPException(
            409,
            {"code": "PLAN_HAS_SCHEDULES",
             "message": "cancel or remove schedules referencing this plan first"},
        )
    deleted = q.delete_cut_plan(
        db, workspace_id=user.workspace_id, plan_id=plan_id
    )
    if not deleted:
        raise HTTPException(404, "cut plan not found")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cut_plan.delete", target=str(plan_id),
        payload={"plan_id": plan_id},
    )
    db.commit()


# ============================================================================
# Optimiser (sub-project #9)
# ============================================================================

@router.post("/projects/{pid}/optimise")
def optimise_project_route(
    pid: int,
    body: OptimiseIn,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> OptimiseOut:
    """Pure-function nest proposal — **no DB writes, no audit**. Packs parts
    across one or more sheets and returns a `CutPlanIn`-shaped `proposal` the
    user reviews then forwards to POST /projects/{pid}/cut-plans (which owns
    persistence + the `cut_plan.create` audit)."""
    if not q.project_in_workspace(
        db, project_id=pid, workspace_id=user.workspace_id
    ):
        raise HTTPException(404, "project not found")

    # Sheet size: explicit dimensions win; otherwise fall back to the largest
    # in-stock sheet for this SKU (board_inventory, 0025). Reading stock never
    # reserves or decrements it — /optimise stays a pure function.
    sheet_len = body.sheet_len_mm
    sheet_wid = body.sheet_wid_mm
    dims_from_stock = False
    if sheet_len is None or sheet_wid is None:
        stock = inv.best_stock_for_sku(
            db, workspace_id=user.workspace_id, sku=body.material_sku
        )
        if stock is None:
            raise HTTPException(
                422,
                {
                    "code": "NO_SHEET_SIZE",
                    "message": (
                        "no sheet stock on hand for this SKU — record stock "
                        "or supply sheet_len_mm and sheet_wid_mm"
                    ),
                    "material_sku": body.material_sku,
                },
            )
        sheet_len = float(stock["len_mm"])
        sheet_wid = float(stock["wid_mm"])
        dims_from_stock = True

    rows = q.candidate_parts_for_optimise(
        db,
        workspace_id=user.workspace_id,
        project_id=pid,
        item_ids=body.include_only_item_ids,
    )

    # Expand each part row into `qty` unit rectangles; grain-locked board
    # materials forbid rotation. `uid` lets the multi-sheet packer track each
    # instance as it overflows to the next sheet.
    parts: list[opt.PackPart] = []
    uid = 0
    for r in rows:
        qty = int(r["qty"] or 1)
        label = r["part_name"] or f"part {r['part_id']}"
        for _ in range(max(qty, 1)):
            parts.append(
                opt.PackPart(
                    w=float(r["len_mm"]),
                    h=float(r["wid_mm"]),
                    label=label,
                    part_id=r["part_id"],
                    allow_rotation=not r["grain_locked"],
                    uid=uid,
                )
            )
            uid += 1

    packed = opt.pack_sheets(
        parts,
        sheet_len=sheet_len,
        sheet_wid=sheet_wid,
        kerf=body.kerf_mm,
        strategy=body.strategy,
        max_sheets=body.max_sheets,
    )

    proposal = CutPlanIn(
        name=body.name,
        notes=f"optimiser · {body.strategy} · {body.material_sku}",
        sheets=[
            CutSheetIn(
                sheet_no=i + 1,
                material_sku=body.material_sku,
                slots=[
                    PartSlotIn(
                        x=s.x, y=s.y, w=s.w, h=s.h,
                        label=s.label, part_id=s.part_id,
                    )
                    for s in sheet.placed
                ],
            )
            for i, sheet in enumerate(packed.sheets)
        ],
    )
    placed_count = sum(len(sheet.placed) for sheet in packed.sheets)
    sheet_utils = [sheet.utilization_pct for sheet in packed.sheets]
    overall = round(sum(sheet_utils) / len(sheet_utils), 4) if sheet_utils else 0.0

    # Stock context. A SKU with no recorded stock reports `None` (unknown)
    # rather than 0, so the UI never claims a shortfall it can't substantiate.
    on_hand = inv.total_sheets_for_size(
        db, workspace_id=user.workspace_id, sku=body.material_sku,
        len_mm=sheet_len, wid_mm=sheet_wid,
    )
    has_stock_record = dims_from_stock or on_hand > 0
    sheets_available = on_hand if has_stock_record else None
    shortfall = (
        max(0, len(packed.sheets) - on_hand) if has_stock_record else 0
    )

    summary = OptimiseSummary(
        total_parts=len(parts),
        placed=placed_count,
        skipped=len(packed.skipped),
        skipped_reasons=[
            {"label": s.label, "reason": s.reason, "part_id": s.part_id}
            for s in packed.skipped
        ],
        sheets_used=len(packed.sheets),
        utilization_pct=overall,
        sheet_utilization=sheet_utils,
        sheet_len_mm=sheet_len,
        sheet_wid_mm=sheet_wid,
        sheet_dims_from_stock=dims_from_stock,
        sheets_available=sheets_available,
        sheet_shortfall=shortfall,
    )
    return OptimiseOut(proposal=proposal, summary=summary)


# ============================================================================
# Board inventory (sheet stock on hand — migration 0025)
# ============================================================================

@router.get("/board-inventory")
def list_board_inventory_route(
    material_sku: str | None = Query(None),
    in_stock_only: bool = Query(False),
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> list[BoardInventoryOut]:
    rows = inv.list_inventory(
        db,
        workspace_id=user.workspace_id,
        material_sku=material_sku,
        in_stock_only=in_stock_only,
    )
    return [BoardInventoryOut(**r) for r in rows]


@router.post("/board-inventory", status_code=201)
def upsert_board_inventory_route(
    body: BoardInventoryIn,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> BoardInventoryOut:
    """Record stock for a (material, sheet size). Upserts: posting the same
    size again sets the quantity rather than creating a duplicate row."""
    material_id = inv.material_by_sku(
        db, workspace_id=user.workspace_id, sku=body.material_sku
    )
    if material_id is None:
        raise HTTPException(
            404,
            {"code": "UNKNOWN_MATERIAL", "material_sku": body.material_sku},
        )
    inventory_id = inv.upsert_inventory(
        db,
        workspace_id=user.workspace_id,
        material_id=material_id,
        len_mm=body.len_mm,
        wid_mm=body.wid_mm,
        qty_on_hand=body.qty_on_hand,
        location=body.location,
        notes=body.notes,
        actor_id=user.id,
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="board_inventory.upsert", target=str(inventory_id),
        payload={
            "inventory_id": inventory_id,
            "material_sku": body.material_sku,
            "len_mm": body.len_mm,
            "wid_mm": body.wid_mm,
            "qty_on_hand": body.qty_on_hand,
        },
    )
    row = inv.get_inventory(
        db, workspace_id=user.workspace_id, inventory_id=inventory_id
    )
    db.commit()
    return BoardInventoryOut(**row)


@router.patch("/board-inventory/{inventory_id}")
def patch_board_inventory_route(
    inventory_id: int,
    body: BoardInventoryPatchIn,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> BoardInventoryOut:
    if inv.get_inventory(
        db, workspace_id=user.workspace_id, inventory_id=inventory_id
    ) is None:
        raise HTTPException(404, "inventory row not found")
    fields = body.model_dump(exclude_unset=True)
    inv.patch_inventory(
        db, workspace_id=user.workspace_id,
        inventory_id=inventory_id, fields=fields,
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="board_inventory.update", target=str(inventory_id),
        payload={"inventory_id": inventory_id, "changes": list(fields.keys())},
    )
    row = inv.get_inventory(
        db, workspace_id=user.workspace_id, inventory_id=inventory_id
    )
    db.commit()
    return BoardInventoryOut(**row)


@router.delete("/board-inventory/{inventory_id}", status_code=204)
def delete_board_inventory_route(
    inventory_id: int,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
):
    if not inv.delete_inventory(
        db, workspace_id=user.workspace_id, inventory_id=inventory_id
    ):
        raise HTTPException(404, "inventory row not found")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="board_inventory.delete", target=str(inventory_id),
        payload={"inventory_id": inventory_id},
    )
    db.commit()


# ============================================================================
# CutSchedule
# ============================================================================

@router.get("/cut-schedules")
def list_cut_schedules_route(
    date: date_t | None = Query(None),
    project_id: int | None = Query(None),
    status: str | None = Query(None),
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> list[CutScheduleOut]:
    rows = q.list_cut_schedules(
        db,
        workspace_id=user.workspace_id,
        day=date,
        project_id=project_id,
        status=status,
    )
    return [CutScheduleOut(**r) for r in rows]


@router.get("/cut-schedules/{sid}")
def get_cut_schedule_route(
    sid: int,
    user: AuthUser = Depends(require_permission("cut_floor", "read")),
    db: Session = Depends(get_db),
) -> CutScheduleOut:
    row = q.get_cut_schedule(
        db, workspace_id=user.workspace_id, schedule_id=sid
    )
    if row is None:
        raise HTTPException(404, "cut schedule not found")
    return CutScheduleOut(**row)


@router.post("/cut-schedules", status_code=201)
def create_cut_schedule_route(
    body: CutScheduleIn,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> CutScheduleOut:
    if not q.plan_in_workspace(
        db, workspace_id=user.workspace_id, plan_id=body.cut_plan_id
    ):
        raise HTTPException(404, "cut plan not found")
    if body.assigned_to is not None and not q.user_in_workspace(
        db, user_id=body.assigned_to, workspace_id=user.workspace_id
    ):
        raise HTTPException(
            422, "assigned_to must reference a user in the same workspace"
        )
    sid = q.insert_cut_schedule(
        db,
        workspace_id=user.workspace_id,
        cut_plan_id=body.cut_plan_id,
        scheduled_for=body.scheduled_for,
        assigned_to=body.assigned_to,
        actor_id=user.id,
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cut_schedule.create", target=str(sid),
        payload={
            "schedule_id": sid,
            "cut_plan_id": body.cut_plan_id,
            "scheduled_for": body.scheduled_for.isoformat(),
            "assigned_to": body.assigned_to,
        },
    )
    row = q.get_cut_schedule(
        db, workspace_id=user.workspace_id, schedule_id=sid
    )
    db.commit()
    return CutScheduleOut(**row)


@router.patch("/cut-schedules/{sid}")
def patch_cut_schedule_route(
    sid: int,
    body: CutSchedulePatchIn,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> CutScheduleOut:
    current = q.get_cut_schedule(
        db, workspace_id=user.workspace_id, schedule_id=sid
    )
    if current is None:
        raise HTTPException(404, "cut schedule not found")

    payload = body.model_dump(exclude_unset=True)
    fields: dict = {}
    status_changed = False

    if "status" in payload:
        new_status = payload["status"]
        if not q.is_legal_transition(current["status"], new_status):
            raise HTTPException(
                409,
                {"code": "BAD_TRANSITION",
                 "from": current["status"], "to": new_status},
            )
        if new_status != current["status"]:
            status_changed = True
            fields["status"] = new_status
    if "scheduled_for" in payload:
        fields["scheduled_for"] = payload["scheduled_for"]
    if "assigned_to" in payload:
        assigned_to = payload["assigned_to"]
        if assigned_to is not None and not q.user_in_workspace(
            db, user_id=assigned_to, workspace_id=user.workspace_id
        ):
            raise HTTPException(
                422, "assigned_to must reference a user in the same workspace"
            )
        fields["assigned_to"] = assigned_to
    if "priority" in payload:
        fields["priority"] = payload["priority"]

    if not fields:
        return CutScheduleOut(**current)

    q.update_cut_schedule(db, schedule_id=sid, fields=fields)

    if status_changed:
        write_audit(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            event="cut_schedule.status_change", target=str(sid),
            payload={
                "schedule_id": sid,
                "from": current["status"],
                "to": fields["status"],
            },
        )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cut_schedule.update", target=str(sid),
        payload={"schedule_id": sid, "changes": list(fields.keys())},
    )
    row = q.get_cut_schedule(
        db, workspace_id=user.workspace_id, schedule_id=sid
    )
    db.commit()
    return CutScheduleOut(**row)


@router.post("/cut-schedules/reorder")
def reorder_cut_schedules_route(
    body: ReorderIn,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> list[CutScheduleOut]:
    try:
        applied = q.reorder_cut_schedules(
            db,
            workspace_id=user.workspace_id,
            day=body.scheduled_for,
            ordered_ids=body.ordered_ids,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cut_schedule.reorder", target=str(body.scheduled_for),
        payload={
            "scheduled_for": body.scheduled_for.isoformat(),
            "ordered_ids": applied,
        },
    )

    rows = q.list_cut_schedules(
        db,
        workspace_id=user.workspace_id,
        day=body.scheduled_for,
        project_id=None,
        status=None,
    )
    db.commit()
    return [CutScheduleOut(**r) for r in rows]


@router.delete("/cut-schedules/{sid}", status_code=200)
def cancel_cut_schedule_route(
    sid: int,
    user: AuthUser = Depends(require_permission("cut_floor", "write")),
    db: Session = Depends(get_db),
) -> CutScheduleOut:
    current = q.get_cut_schedule(
        db, workspace_id=user.workspace_id, schedule_id=sid
    )
    if current is None:
        raise HTTPException(404, "cut schedule not found")
    if current["status"] == "cancelled":
        raise HTTPException(
            409,
            {"code": "ALREADY_CANCELLED", "schedule_id": sid},
        )
    if current["status"] == "done":
        raise HTTPException(
            409,
            {"code": "BAD_TRANSITION", "from": "done", "to": "cancelled"},
        )
    q.update_cut_schedule(
        db, schedule_id=sid, fields={"status": "cancelled"},
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cut_schedule.cancel", target=str(sid),
        payload={"schedule_id": sid, "from": current["status"]},
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cut_schedule.status_change", target=str(sid),
        payload={"schedule_id": sid, "from": current["status"], "to": "cancelled"},
    )
    row = q.get_cut_schedule(
        db, workspace_id=user.workspace_id, schedule_id=sid
    )
    db.commit()
    return CutScheduleOut(**row)

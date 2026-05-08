"""cut_floor HTTP routes — sub-project #7c.

Two surfaces:
  CutPlan: /projects/{pid}/cut-plans, /cut-plans/{plan_id},
           /items/{iid}/cut-plan
  CutSchedule: /cut-schedules (?date=...&project_id=&status=),
               /cut-schedules/{sid},  /cut-schedules/reorder

All gated by ("cut_floor", action). Workspace isolation via
`cut_plan.workspace_id`. Audit on every mutation.
"""
from __future__ import annotations

from datetime import date as date_t

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CutPlanIn,
    CutPlanOut,
    CutPlanSummary,
    CutScheduleIn,
    CutSchedulePatchIn,
    CutScheduleOut,
    ItemCutPlanOut,
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
        fields["assigned_to"] = payload["assigned_to"]
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

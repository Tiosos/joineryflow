"""shop_floor HTTP routes — sub-project #8.

10 endpoints:
  GET    /projects/{pid}/shop-floor/board
  GET    /projects/{pid}/shop-floor/workers
  GET    /workers/{wid}/queue
  GET    /workers/{wid}/recent-completions
  POST   /projects/{pid}/items/{iid}/assignments
  PATCH  /assignments/{aid}
  DELETE /assignments/{aid}
  POST   /assignments/{aid}/start
  POST   /assignments/{aid}/complete
  POST   /completions/{log_id}/undo

All gated by ("shop_floor", action). Workspace isolation via the
items -> projects.workspace_id chain.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .lifecycle import is_within_undo_window
from .schemas import (
    AssignIn,
    AssignmentOut,
    BoardCard,
    BoardOut,
    CompleteIn,
    CompleteOut,
    PatchAssignmentIn,
    RecentCompletionOut,
    StationCard,
    StationOut,
    UndoOut,
    WorkerOut,
)


router = APIRouter(tags=["shop_floor"])

SHOP_FLOOR_STAGES = ("DOWN", "CNC", "EDGED", "PAINTED", "MADE")


def _is_admin_or_manager(role: str) -> bool:
    return role in ("admin", "manager", "editor")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# Board + worker registry
# ============================================================================

@router.get("/projects/{pid}/shop-floor/board")
def get_board_route(
    pid: int,
    user: AuthUser = Depends(require_permission("shop_floor", "read")),
    db: Session = Depends(get_db),
) -> BoardOut:
    proj = q.project_in_workspace(db, project_id=pid, workspace_id=user.workspace_id)
    if proj is None:
        raise HTTPException(404, "project not found")

    rows = q.board_cards(db, workspace_id=user.workspace_id, project_id=pid)

    columns: dict[str, list[BoardCard]] = {s: [] for s in SHOP_FLOOR_STAGES}
    for r in rows:
        assignment = None
        if r.get("assignment_id") is not None:
            assignment = AssignmentOut(
                assignment_id=r["assignment_id"],
                cutlist_id=r["cutlist_id"],
                cutlist_no=r["cutlist_no"],
                cutlist_name=r.get("cutlist_name"),
                item_count=int(r.get("item_count") or 0),
                stage_key=r["next_stage_key"],
                worker_id=r["worker_id"],
                worker_name=r.get("worker_name"),
                status=r["status"],
                note=r.get("note"),
                assigned_by=r["assigned_by"],
                assigned_at=r["assigned_at"],
                started_at=r.get("started_at"),
                ended_at=r.get("ended_at"),
                cancelled_at=r.get("cancelled_at"),
            )
        card = BoardCard(
            item_id=r["item_id"],
            item_number=r["item_number"],
            cutlist_id=r.get("cutlist_id"),
            code=r.get("code"),
            description=r.get("description"),
            painting_req=bool(r["painting_req"]),
            paint_after_assembly=bool(r["paint_after_assembly"]),
            next_stage_key=r["next_stage_key"],
            assignment=assignment,
        )
        columns[r["next_stage_key"]].append(card)

    return BoardOut(
        project_id=proj["project_id"],
        project_code=proj["project_code"],
        columns=columns,
    )


@router.get("/projects/{pid}/shop-floor/workers")
def list_workers_route(
    pid: int,
    user: AuthUser = Depends(require_permission("shop_floor", "read")),
    db: Session = Depends(get_db),
) -> list[WorkerOut]:
    if q.project_in_workspace(db, project_id=pid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "project not found")
    rows = q.list_project_workers(
        db, workspace_id=user.workspace_id, project_id=pid
    )
    return [WorkerOut(**r) for r in rows]


# ============================================================================
# Worker queue + recent completions (kiosk reads)
# ============================================================================

@router.get("/workers/{wid}/queue")
def worker_queue_route(
    wid: int,
    user: AuthUser = Depends(require_permission("shop_floor", "read")),
    db: Session = Depends(get_db),
) -> StationOut:
    worker = q.get_workspace_user(
        db, workspace_id=user.workspace_id, user_id=wid
    )
    if worker is None or not worker["is_shop_worker"]:
        raise HTTPException(404, "worker not found")
    rows = q.worker_queue(db, workspace_id=user.workspace_id, worker_id=wid)
    cards = [StationCard(**r) for r in rows]
    return StationOut(
        worker_id=wid,
        worker_name=worker["full_name"],
        cards=cards,
    )


@router.get("/workers/{wid}/recent-completions")
def recent_completions_route(
    wid: int,
    user: AuthUser = Depends(require_permission("shop_floor", "read")),
    db: Session = Depends(get_db),
) -> list[RecentCompletionOut]:
    worker = q.get_workspace_user(
        db, workspace_id=user.workspace_id, user_id=wid
    )
    if worker is None or not worker["is_shop_worker"]:
        raise HTTPException(404, "worker not found")
    rows = q.recent_completions_for_worker(
        db, workspace_id=user.workspace_id, worker_id=wid, minutes=5
    )
    return [RecentCompletionOut(**r) for r in rows]


# ============================================================================
# Assignment CRUD
# ============================================================================

@router.post("/projects/{pid}/items/{iid}/assignments", status_code=201)
def create_assignment_route(
    pid: int,
    iid: int,
    body: AssignIn,
    user: AuthUser = Depends(require_permission("shop_floor", "write")),
    db: Session = Depends(get_db),
) -> AssignmentOut:
    if q.project_in_workspace(db, project_id=pid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "project not found")
    item = q.item_for_workspace(
        db, item_id=iid, workspace_id=user.workspace_id
    )
    if item is None or item["project_id"] != pid:
        raise HTTPException(404, "item not found in project")
    if not q.is_workspace_worker(
        db, workspace_id=user.workspace_id, worker_id=body.worker_id
    ):
        raise HTTPException(
            422,
            {"code": "NOT_A_SHOP_WORKER", "worker_id": body.worker_id},
        )
    # Q412: the production workflow belongs to the CUTLIST, so this assigns
    # every item that shares it — not item `iid` alone. The route stays
    # item-scoped because that is how the board addresses a card; `0030`
    # re-keyed what it writes.
    if item.get("cutlist_id") is None:
        raise HTTPException(
            409,
            {"code": "ITEM_HAS_NO_CUTLIST", "item_id": iid,
             "message": "link this item to a cutlist before assigning work"},
        )
    cid = item["cutlist_id"]
    try:
        aid = q.insert_assignment(
            db,
            cutlist_id=cid,
            stage_key=body.stage_key,
            worker_id=body.worker_id,
            note=body.note,
            assigned_by=user.id,
        )
    except IntegrityError:
        db.rollback()
        existing = q.get_active_assignment(
            db, cutlist_id=cid, stage_key=body.stage_key
        )
        if existing is not None:
            raise HTTPException(
                409,
                {
                    "code": "ACTIVE_ASSIGNMENT_EXISTS",
                    "assignment_id": existing["assignment_id"],
                    "worker_id": existing["worker_id"],
                    "worker_name": existing.get("worker_name"),
                    "status": existing["status"],
                },
            )
        raise HTTPException(409, {"code": "ACTIVE_ASSIGNMENT_EXISTS"})

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="shop_floor.assign", target=str(aid),
        payload={
            "assignment_id": aid,
            "item_id": iid,
            "stage_key": body.stage_key,
            "worker_id": body.worker_id,
            "assigned_by": user.id,
        },
    )
    db.commit()
    row = q.get_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    return AssignmentOut(**row)


@router.patch("/assignments/{aid}")
def patch_assignment_route(
    aid: int,
    body: PatchAssignmentIn,
    user: AuthUser = Depends(require_permission("shop_floor", "write")),
    db: Session = Depends(get_db),
) -> AssignmentOut:
    current = q.get_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    if current is None:
        raise HTTPException(404, "assignment not found")
    if current["status"] in ("done", "cancelled"):
        raise HTTPException(
            409,
            {"code": "ASSIGNMENT_TERMINAL", "status": current["status"]},
        )

    payload = body.model_dump(exclude_unset=True)
    fields: dict = {}
    audit_event = None
    audit_payload: dict = {"assignment_id": aid, "item_id": current["item_id"],
                           "stage_key": current["stage_key"]}

    if "worker_id" in payload and payload["worker_id"] is not None:
        new_worker = payload["worker_id"]
        if not q.is_workspace_worker(
            db, workspace_id=user.workspace_id, worker_id=new_worker
        ):
            raise HTTPException(
                422,
                {"code": "NOT_A_SHOP_WORKER", "worker_id": new_worker},
            )
        if new_worker != current["worker_id"]:
            fields["worker_id"] = new_worker
            fields["status"] = "assigned"
            fields["started_at"] = None
            audit_event = "shop_floor.reassign"
            audit_payload.update({
                "old_worker_id": current["worker_id"],
                "new_worker_id": new_worker,
                "started_at_cleared": True,
            })

    if "note" in payload:
        fields["note"] = payload["note"]
        if audit_event is None:
            audit_event = "shop_floor.assign_note_update"
            audit_payload["note"] = payload["note"]

    if not fields:
        return AssignmentOut(**current)

    q.update_assignment(db, assignment_id=aid, fields=fields)
    if audit_event:
        write_audit(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            event=audit_event, target=str(aid), payload=audit_payload,
        )
    db.commit()
    row = q.get_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    return AssignmentOut(**row)


@router.delete("/assignments/{aid}", status_code=200)
def cancel_assignment_route(
    aid: int,
    user: AuthUser = Depends(require_permission("shop_floor", "write")),
    db: Session = Depends(get_db),
) -> AssignmentOut:
    current = q.get_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    if current is None:
        raise HTTPException(404, "assignment not found")
    if current["status"] == "cancelled":
        raise HTTPException(409, {"code": "ALREADY_CANCELLED"})
    if current["status"] == "done":
        raise HTTPException(
            409,
            {"code": "ASSIGNMENT_TERMINAL", "status": "done"},
        )
    q.update_assignment(
        db, assignment_id=aid,
        fields={
            "status": "cancelled",
            "cancelled_at": _now(),
            "cancelled_by": user.id,
        },
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="shop_floor.unassign", target=str(aid),
        payload={
            "assignment_id": aid,
            "item_id": current["item_id"],
            "stage_key": current["stage_key"],
            "cancelled_by": user.id,
            "from_status": current["status"],
        },
    )
    db.commit()
    row = q.get_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    return AssignmentOut(**row)


# ============================================================================
# Worker actions: start + complete + undo
# ============================================================================

@router.post("/assignments/{aid}/start")
def start_assignment_route(
    aid: int,
    user: AuthUser = Depends(require_permission("shop_floor", "write")),
    db: Session = Depends(get_db),
) -> AssignmentOut:
    current = q.get_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    if current is None:
        raise HTTPException(404, "assignment not found")
    if current["status"] in ("done", "cancelled"):
        raise HTTPException(
            409,
            {"code": "ASSIGNMENT_TERMINAL", "status": current["status"]},
        )
    if user.id != current["worker_id"] and not _is_admin_or_manager(user.auth_role):
        raise HTTPException(403, {"code": "NOT_THE_WORKER"})

    if current["status"] != "in_progress":
        q.update_assignment(
            db, assignment_id=aid,
            fields={"status": "in_progress", "started_at": _now()},
        )
        write_audit(
            db, workspace_id=user.workspace_id, actor_id=user.id,
            event="shop_floor.stage_start", target=str(aid),
            payload={"assignment_id": aid, "worker_id": current["worker_id"]},
        )
    db.commit()
    row = q.get_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    return AssignmentOut(**row)


@router.post("/assignments/{aid}/complete")
def complete_assignment_route(
    aid: int,
    body: CompleteIn,
    user: AuthUser = Depends(require_permission("shop_floor", "write")),
    db: Session = Depends(get_db),
) -> CompleteOut:
    locked = q.lock_assignment(
        db, assignment_id=aid, workspace_id=user.workspace_id
    )
    if locked is None:
        raise HTTPException(404, "assignment not found")
    if locked["status"] in ("done", "cancelled"):
        raise HTTPException(
            409,
            {"code": "ASSIGNMENT_TERMINAL", "status": locked["status"]},
        )
    # The status machine is assigned -> in_progress -> done; completing a
    # never-started assignment would skip in_progress and leave started_at
    # NULL on a done row. The kiosk always Starts before Mark-done.
    if locked["status"] != "in_progress":
        raise HTTPException(
            409,
            {"code": "NOT_IN_PROGRESS", "status": locked["status"]},
        )
    if user.id != locked["worker_id"] and not _is_admin_or_manager(user.auth_role):
        raise HTTPException(403, {"code": "NOT_THE_WORKER"})

    # Q562: every item on the cutlist must be ready, because they all advance
    # together. An item whose own order skips this stage is not consulted.
    missing = q.cutlist_prior_stages_done(
        db, cutlist_id=locked["cutlist_id"], stage_key=locked["stage_key"],
    )
    if missing:
        raise HTTPException(
            409,
            {"code": "STAGE_OUT_OF_ORDER", "missing": missing},
        )

    log_id = q.insert_completion_log(
        db,
        cutlist_id=locked["cutlist_id"],
        stage_key=locked["stage_key"],
        assignment_id=aid,
        worker_id=locked["worker_id"],
        note=body.note,
    )
    # Q439: one completion, N item_stages rows — the projection the Tracking
    # strip reads per row without joining the cutlist (Q441).
    fanned = q.fan_out_stage_done(
        db, cutlist_id=locked["cutlist_id"], stage_key=locked["stage_key"]
    )
    q.update_assignment(
        db, assignment_id=aid,
        fields={"status": "done", "ended_at": _now()},
    )

    # `next_open_stage` is per item; with a shared cutlist the kiosk shows the
    # first linked item's next stage. They only diverge where the items'
    # painting flags differ (Q562).
    cl_items = q.cutlist_items(db, cutlist_id=locked["cutlist_id"])
    next_stage = (
        q.next_open_stage(
            db,
            item_id=cl_items[0]["item_id"],
            painting_req=bool(cl_items[0]["painting_req"]),
            paint_after_assembly=bool(cl_items[0]["paint_after_assembly"]),
        )
        if cl_items
        else None
    )

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="shop_floor.stage_complete", target=str(aid),
        payload={
            "assignment_id": aid,
            "log_id": log_id,
            "cutlist_id": locked["cutlist_id"],
            "cutlist_no": locked["cutlist_no"],
            "fanned_out_to_item_ids": fanned,
            "stage_key": locked["stage_key"],
            "worker_id": locked["worker_id"],
            "note": body.note,
            "lifecycle_advanced": next_stage is not None,
            "next_stage_key": next_stage,
        },
    )
    db.commit()
    return CompleteOut(
        log_id=log_id,
        assignment_id=aid,
        lifecycle_advanced=next_stage is not None,
        next_stage_key=next_stage,
    )


@router.post("/completions/{log_id}/undo")
def undo_completion_route(
    log_id: int,
    user: AuthUser = Depends(require_permission("shop_floor", "write")),
    db: Session = Depends(get_db),
) -> UndoOut:
    log = q.get_completion_log(
        db, log_id=log_id, workspace_id=user.workspace_id
    )
    if log is None:
        raise HTTPException(404, "completion log not found")
    if log["undone_at"] is not None:
        raise HTTPException(409, {"code": "ALREADY_UNDONE"})

    is_worker = user.id == log["worker_id"]
    is_supervisor = _is_admin_or_manager(user.auth_role)
    if not (is_worker or is_supervisor):
        raise HTTPException(403, {"code": "NOT_AUTHORIZED_TO_UNDO"})
    if is_worker and not is_supervisor:
        if not is_within_undo_window(log["completed_at"]):
            raise HTTPException(
                409,
                {"code": "UNDO_WINDOW_EXPIRED"},
            )

    # Undoing a stage whose successor is already done would produce the
    # out-of-order lifecycle (earlier stage open, later stage done) that
    # /complete's prior-stages check forbids. Make the later stage be undone
    # first.
    blockers = q.cutlist_later_stages_done(
        db, cutlist_id=log["cutlist_id"], stage_key=log["stage_key"],
    )
    if blockers:
        raise HTTPException(
            409,
            {"code": "LATER_STAGE_DONE", "blocking": blockers},
        )

    q.mark_completion_undone(db, log_id=log_id, undone_by=user.id)
    # Q446: the undo reverses the whole cutlist, not one item. Q539's late
    # joiner is a no-op for free — it has no row for this stage to clear.
    cleared = q.fan_in_stage_undone(
        db, cutlist_id=log["cutlist_id"], stage_key=log["stage_key"]
    )
    if log["assignment_id"] is not None:
        q.update_assignment(
            db, assignment_id=log["assignment_id"],
            fields={"status": "in_progress", "ended_at": None},
        )

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="shop_floor.stage_undo", target=str(log_id),
        payload={
            "log_id": log_id,
            "cutlist_id": log["cutlist_id"],
            "cutlist_no": log["cutlist_no"],
            "cleared_item_ids": cleared,
            "stage_key": log["stage_key"],
            "undone_by": user.id,
            "original_worker_id": log["worker_id"],
            "original_completed_at": log["completed_at"].isoformat()
                if hasattr(log["completed_at"], "isoformat") else None,
            "via": "worker" if is_worker else "supervisor",
        },
    )
    db.commit()
    return UndoOut(
        log_id=log_id,
        assignment_id=log["assignment_id"] or 0,
        cutlist_id=log["cutlist_id"],
        cutlist_no=log["cutlist_no"],
        stage_key=log["stage_key"],
    )

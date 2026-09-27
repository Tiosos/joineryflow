"""Derived actual-cost rollup for a project (Plan V1 §16, Q493/Q549).

Pure read, nothing stored — the same "derive, don't capture twice" stance
as #9's `/optimise` (Q501). Two sources, both already recorded elsewhere:

- **Materials**: `procurement_batches.qty_received * cost_per_unit`, summed
  per project over batches with `cancelled_at IS NULL` — a soft-cancelled
  batch (#4's `DELETE /batches/{bid}`) never happened, cost-wise, matching
  the same filter `procurement_v1` already applies elsewhere. This is
  project-level only (Q492 caps granularity at Project + Item, and there is
  no per-item allocation path for BOARD/CUSTOM/BENCHTOP batches today — only
  HARDWARE batches reach an item, through `batch_allocations ->
  item_hardware_lines`, which #12's Material Summary already treats as a
  project-level-only gap for the same reason).
- **Labour**: each `stage_completion_log` row's duration
  (`completed_at - worker_assignment.started_at`) priced at
  `workspace_labour_rate`. Completions belong to a **cutlist** (migration
  `0030`), shared by every item on it, so a completion's cost is apportioned
  across the cutlist's items by each item's share of total part area (Q549) —
  falling back to an equal split when no item on the cutlist has any
  measurable part area yet.

A completion with no `assignment_id` (nullable — pre-`0030` provenance rows,
per `stage_completion_log`'s own comment) has no `started_at` to compute a
duration from and is excluded, not zero-costed; there is nothing to derive
it from.
"""
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def _materials_actual(db: Session, *, project_id: int) -> Decimal:
    val = db.execute(
        text(
            """
            SELECT COALESCE(SUM(qty_received * COALESCE(cost_per_unit, 0)), 0)
              FROM procurement_batches
             WHERE project_id = :p AND cancelled_at IS NULL
            """
        ),
        {"p": project_id},
    ).scalar()
    return Decimal(str(val or 0))


def _labour_completions(db: Session, *, project_id: int, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT scl.log_id, scl.cutlist_id, scl.stage_key,
                   EXTRACT(EPOCH FROM (scl.completed_at - wa.started_at)) / 3600.0 AS hours,
                   COALESCE(r.hourly_rate, 0) AS hourly_rate
              FROM stage_completion_log scl
              JOIN worker_assignment wa ON wa.assignment_id = scl.assignment_id
              JOIN cutlist cl ON cl.cutlist_id = scl.cutlist_id
              LEFT JOIN workspace_labour_rate r
                ON r.workspace_id = :w AND r.stage_key = scl.stage_key
             WHERE cl.project_id = :p AND scl.undone_at IS NULL
            """
        ),
        {"p": project_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _item_areas_by_cutlist(db: Session, *, cutlist_ids: set[int]) -> dict[int, dict[int, Decimal]]:
    if not cutlist_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT i.item_id, i.cutlist_id,
                   COALESCE(SUM(p.len_mm::numeric * p.wid_mm * p.qty), 0) AS area
              FROM items i
              LEFT JOIN modules m ON m.item_id = i.item_id
              LEFT JOIN parts p ON p.module_id = m.module_id
             WHERE i.cutlist_id = ANY(:ids)
             GROUP BY i.item_id, i.cutlist_id
            """
        ),
        {"ids": list(cutlist_ids)},
    ).mappings().all()
    out: dict[int, dict[int, Decimal]] = {}
    for r in rows:
        out.setdefault(int(r["cutlist_id"]), {})[int(r["item_id"])] = Decimal(str(r["area"]))
    return out


def actual_costs_for_project(
    db: Session, *, project_id: int, workspace_id: int
) -> dict | None:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None

    materials_actual = _materials_actual(db, project_id=project_id)
    completions = _labour_completions(db, project_id=project_id, workspace_id=workspace_id)
    cutlist_ids = {int(c["cutlist_id"]) for c in completions}
    areas = _item_areas_by_cutlist(db, cutlist_ids=cutlist_ids)

    labour_actual = Decimal("0")
    labour_by_item: dict[int, Decimal] = {}
    for c in completions:
        hours = Decimal(str(c["hours"] or 0))
        cost = hours * Decimal(str(c["hourly_rate"] or 0))
        labour_actual += cost
        cutlist_items = areas.get(int(c["cutlist_id"]), {})
        if not cutlist_items:
            continue
        total_area = sum(cutlist_items.values(), Decimal("0"))
        n = len(cutlist_items)
        for item_id, area in cutlist_items.items():
            share = (area / total_area) if total_area > 0 else (Decimal("1") / n)
            labour_by_item[item_id] = labour_by_item.get(item_id, Decimal("0")) + cost * share

    labour_actual = labour_actual.quantize(Decimal("0.01"))
    return {
        "project_id": project_id,
        "materials_actual": materials_actual.quantize(Decimal("0.01")),
        "labour_actual": labour_actual,
        "total_actual": (materials_actual + labour_actual).quantize(Decimal("0.01")),
        "labour_by_item": {
            k: v.quantize(Decimal("0.01")) for k, v in labour_by_item.items()
        },
    }

"""SQL queries for cut_floor (sub-project #7c).

Routes own the transaction boundary; queries flush only.

Workspace isolation: every read + write filters by `cut_plan.workspace_id`
(or by joining through it). cut_schedule and cut_sheet/part_slot have no
workspace_id column — they always go through cut_plan.
"""
from __future__ import annotations

from datetime import date as date_t
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from ..row_types import joinery_items_only

# A related part has no modules, parts or cut plan (Plan V1 Q447), so it can
# neither be nested nor looked up here.
_JOINERY_ITEM = joinery_items_only("i")


# ---- Status transition matrix (per spec §6) --------------------------------

ALLOWED_STATUS_TRANSITIONS: set[tuple[str, str]] = {
    ("planned", "running"),
    ("planned", "cancelled"),
    ("running", "done"),
    ("running", "cancelled"),
}


def is_legal_transition(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True  # no-op
    return (from_status, to_status) in ALLOWED_STATUS_TRANSITIONS


# ---- Project / item lookup -------------------------------------------------

def project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    return db.execute(
        text(
            "SELECT 1 FROM projects "
            "WHERE project_id = :pid AND workspace_id = :w"
        ),
        {"pid": project_id, "w": workspace_id},
    ).first() is not None


def item_project(db: Session, *, item_id: int, workspace_id: int) -> int | None:
    row = db.execute(
        text(
            f"""
            SELECT i.project_id
            FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :iid AND p.workspace_id = :w
              AND {_JOINERY_ITEM}
            """
        ),
        {"iid": item_id, "w": workspace_id},
    ).first()
    return row[0] if row else None


# ---- Optimiser: candidate parts (sub-project #9) ---------------------------

def candidate_parts_for_optimise(
    db: Session,
    *,
    workspace_id: int,
    project_id: int,
    item_ids: list[int] | None = None,
) -> list[dict]:
    """Parts eligible for packing: every part in the project with real
    dimensions, joined to its board material's `grain_locked` flag (parts
    with no board material default to rotatable). Optionally narrowed to
    `item_ids`. Workspace isolation is enforced by the caller's
    project_in_workspace() check plus the project join here.

    `item_ids` distinguishes "not filtering" from "filtering to nothing":
      * `None`  -> no filter, every part in the project.
      * `[]`    -> an explicit empty selection, so no parts. Treating this as
        "no filter" would silently pack the whole project — the opposite of
        what an empty selection means.
    """
    if item_ids is not None and len(item_ids) == 0:
        return []
    conds = [
        "pr.workspace_id = :w",
        "i.project_id = :pid",
        "p.len_mm IS NOT NULL AND p.wid_mm IS NOT NULL",
        "p.len_mm > 0 AND p.wid_mm > 0",
    ]
    params: dict[str, Any] = {"w": workspace_id, "pid": project_id}
    if item_ids:
        conds.append("i.item_id = ANY(:item_ids)")
        params["item_ids"] = item_ids
    where = " AND ".join(conds)
    rows = db.execute(
        text(
            f"""
            SELECT p.part_id, p.part_name, p.qty, p.len_mm, p.wid_mm,
                   COALESCE(bm.grain_locked, false) AS grain_locked
            FROM parts p
            JOIN modules m  ON m.module_id = p.module_id
            JOIN items i    ON i.item_id = m.item_id AND {_JOINERY_ITEM}
            JOIN projects pr ON pr.project_id = i.project_id
            LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id
            WHERE {where}
            ORDER BY p.part_id
            """
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


# ---- CutPlan: insert -------------------------------------------------------

def insert_cut_plan(
    db: Session,
    *,
    workspace_id: int,
    project_id: int,
    name: str,
    notes: str | None,
    actor_id: int,
) -> int:
    """INSERT a cut_plan row. Returns plan id (column is `id`)."""
    return db.execute(
        text(
            """
            INSERT INTO cut_plan(workspace_id, project_id, name, notes, created_by)
            VALUES (:w, :pid, :name, :notes, :a)
            RETURNING id
            """
        ),
        {
            "w": workspace_id,
            "pid": project_id,
            "name": name,
            "notes": notes,
            "a": actor_id,
        },
    ).scalar()


def insert_cut_sheet(
    db: Session,
    *,
    cut_plan_id: int,
    sheet_no: int,
    material_sku: str,
) -> int:
    return db.execute(
        text(
            """
            INSERT INTO cut_sheet(cut_plan_id, sheet_no, material_sku)
            VALUES (:cpid, :sno, :sku)
            RETURNING id
            """
        ),
        {"cpid": cut_plan_id, "sno": sheet_no, "sku": material_sku},
    ).scalar()


def insert_part_slot(
    db: Session,
    *,
    cut_sheet_id: int,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str | None,
    part_id: int | None,
) -> int:
    return db.execute(
        text(
            """
            INSERT INTO part_slot(cut_sheet_id, x, y, w, h, label, part_id)
            VALUES (:cs, :x, :y, :w, :h, :lbl, :pid)
            RETURNING id
            """
        ),
        {
            "cs": cut_sheet_id,
            "x": x, "y": y, "w": w, "h": h,
            "lbl": label, "pid": part_id,
        },
    ).scalar()


# ---- CutPlan: read ---------------------------------------------------------

def list_cut_plans_for_project(
    db: Session, *, workspace_id: int, project_id: int
) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT cp.id, cp.name, cp.project_id, cp.notes,
                   cp.created_by, cp.created_at,
                   COUNT(DISTINCT cs.id) AS sheet_count,
                   COUNT(ps.id)          AS slot_count
            FROM cut_plan cp
            LEFT JOIN cut_sheet cs ON cs.cut_plan_id = cp.id
            LEFT JOIN part_slot ps ON ps.cut_sheet_id = cs.id
            WHERE cp.workspace_id = :w AND cp.project_id = :pid
            GROUP BY cp.id
            ORDER BY cp.id DESC
            """
        ),
        {"w": workspace_id, "pid": project_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_cut_plan(
    db: Session, *, workspace_id: int, plan_id: int
) -> dict | None:
    """Return the plan row + nested sheets and slots."""
    plan_row = db.execute(
        text(
            """
            SELECT id, name, project_id, notes, created_by, created_at
            FROM cut_plan
            WHERE id = :pid AND workspace_id = :w
            """
        ),
        {"pid": plan_id, "w": workspace_id},
    ).mappings().first()
    if plan_row is None:
        return None

    sheets = db.execute(
        text(
            """
            SELECT id, sheet_no, material_sku
            FROM cut_sheet
            WHERE cut_plan_id = :pid
            ORDER BY sheet_no
            """
        ),
        {"pid": plan_id},
    ).mappings().all()

    sheet_ids = [s["id"] for s in sheets]
    slot_rows: list[dict] = []
    if sheet_ids:
        slot_rows = [
            dict(r) for r in db.execute(
                text(
                    """
                    SELECT id, cut_sheet_id, x, y, w, h, label, part_id
                    FROM part_slot
                    WHERE cut_sheet_id = ANY(:sheet_ids)
                    ORDER BY id
                    """
                ),
                {"sheet_ids": sheet_ids},
            ).mappings().all()
        ]

    by_sheet: dict[int, list[dict]] = {sid: [] for sid in sheet_ids}
    for r in slot_rows:
        by_sheet[r["cut_sheet_id"]].append({
            "id": r["id"],
            "x": float(r["x"]), "y": float(r["y"]),
            "w": float(r["w"]), "h": float(r["h"]),
            "label": r["label"],
            "part_id": r["part_id"],
            "is_foreign": False,
        })

    return {
        "id": plan_row["id"],
        "name": plan_row["name"],
        "project_id": plan_row["project_id"],
        "notes": plan_row["notes"],
        "created_by": plan_row["created_by"],
        "created_at": plan_row["created_at"],
        "sheets": [
            {
                "id": s["id"],
                "sheet_no": s["sheet_no"],
                "material_sku": s["material_sku"],
                "slots": by_sheet.get(s["id"], []),
            }
            for s in sheets
        ],
    }


def get_latest_plan_for_item(
    db: Session, *, workspace_id: int, item_id: int
) -> dict:
    """Return ItemCutPlanOut shape — most-recent plan for the item's project,
    filtered to sheets containing slots from this item, with foreign-slot flag.
    """
    project_id = item_project(db, item_id=item_id, workspace_id=workspace_id)
    if project_id is None:
        return {"plan": None, "sheets": []}

    plan_row = db.execute(
        text(
            """
            SELECT id, name, project_id, notes, created_by, created_at
            FROM cut_plan
            WHERE workspace_id = :w AND project_id = :pid
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"w": workspace_id, "pid": project_id},
    ).mappings().first()
    if plan_row is None:
        return {"plan": None, "sheets": []}

    plan_id = plan_row["id"]

    item_part_ids = [r[0] for r in db.execute(
        text(
            """
            SELECT p.part_id
            FROM parts p
            JOIN modules m ON m.module_id = p.module_id
            WHERE m.item_id = :iid
            """
        ),
        {"iid": item_id},
    ).all()]
    item_part_ids_set = set(item_part_ids)

    if not item_part_ids:
        return {
            "plan": {
                **dict(plan_row),
                "sheet_count": 0,
                "slot_count": 0,
            },
            "sheets": [],
        }

    relevant_sheets = db.execute(
        text(
            """
            SELECT DISTINCT cs.id, cs.sheet_no, cs.material_sku
            FROM cut_sheet cs
            JOIN part_slot ps ON ps.cut_sheet_id = cs.id
            WHERE cs.cut_plan_id = :plan_id
              AND ps.part_id = ANY(:pids)
            ORDER BY cs.sheet_no
            """
        ),
        {"plan_id": plan_id, "pids": item_part_ids},
    ).mappings().all()

    sheet_ids = [s["id"] for s in relevant_sheets]
    slot_rows: list[dict] = []
    if sheet_ids:
        slot_rows = [
            dict(r) for r in db.execute(
                text(
                    """
                    SELECT ps.id, ps.cut_sheet_id, ps.x, ps.y, ps.w, ps.h,
                           ps.label, ps.part_id, p.part_name
                    FROM part_slot ps
                    LEFT JOIN parts p ON p.part_id = ps.part_id
                    WHERE ps.cut_sheet_id = ANY(:sheet_ids)
                    ORDER BY ps.id
                    """
                ),
                {"sheet_ids": sheet_ids},
            ).mappings().all()
        ]

    by_sheet: dict[int, list[dict]] = {sid: [] for sid in sheet_ids}
    total_slots = 0
    for r in slot_rows:
        is_foreign = (
            r["part_id"] is None or r["part_id"] not in item_part_ids_set
        )
        label = r["label"] or r["part_name"] or f"slot {r['id']}"
        by_sheet[r["cut_sheet_id"]].append({
            "id": r["id"],
            "x": float(r["x"]), "y": float(r["y"]),
            "w": float(r["w"]), "h": float(r["h"]),
            "label": label,
            "part_id": r["part_id"],
            "is_foreign": is_foreign,
        })
        total_slots += 1

    return {
        "plan": {
            "id": plan_row["id"],
            "name": plan_row["name"],
            "project_id": plan_row["project_id"],
            "notes": plan_row["notes"],
            "created_by": plan_row["created_by"],
            "created_at": plan_row["created_at"],
            "sheet_count": len(relevant_sheets),
            "slot_count": total_slots,
        },
        "sheets": [
            {
                "id": s["id"],
                "sheet_no": s["sheet_no"],
                "material_sku": s["material_sku"],
                "slots": by_sheet.get(s["id"], []),
            }
            for s in relevant_sheets
        ],
    }


# ---- CutPlan: delete -------------------------------------------------------

def has_active_schedules(db: Session, *, plan_id: int) -> bool:
    """`done` and `cancelled` schedules don't block plan deletion — only
    live (planned/running) work does. Cascading delete will sweep the
    historical rows along with the plan."""
    return db.execute(
        text(
            """
            SELECT 1 FROM cut_schedule
            WHERE cut_plan_id = :pid
              AND status IN ('planned', 'running')
            LIMIT 1
            """
        ),
        {"pid": plan_id},
    ).first() is not None


def delete_cut_plan(
    db: Session, *, workspace_id: int, plan_id: int
) -> bool:
    res = db.execute(
        text(
            """
            DELETE FROM cut_plan
            WHERE id = :pid AND workspace_id = :w
            """
        ),
        {"pid": plan_id, "w": workspace_id},
    )
    db.flush()
    return (res.rowcount or 0) > 0


# ---- CutSchedule: read -----------------------------------------------------

_SCHEDULE_SELECT = """
    SELECT cs.id, cs.cut_plan_id, cs.scheduled_for, cs.status,
           cs.priority, cs.assigned_to, cs.created_by, cs.created_at,
           cs.updated_at,
           cp.name        AS cut_plan_name,
           cp.project_id  AS project_id,
           u.full_name    AS assigned_to_full_name
    FROM cut_schedule cs
    JOIN cut_plan cp ON cp.id = cs.cut_plan_id
    LEFT JOIN app_user u ON u.id = cs.assigned_to
"""


def list_cut_schedules(
    db: Session,
    *,
    workspace_id: int,
    day: date_t | None,
    project_id: int | None,
    status: str | None,
) -> list[dict]:
    conds = ["cp.workspace_id = :w"]
    params: dict[str, Any] = {"w": workspace_id}
    if day is not None:
        conds.append("cs.scheduled_for = :d")
        params["d"] = day
    if project_id is not None:
        conds.append("cp.project_id = :pid")
        params["pid"] = project_id
    if status is not None:
        conds.append("cs.status = :st")
        params["st"] = status
    where = " AND ".join(conds)
    rows = db.execute(
        text(
            _SCHEDULE_SELECT
            + f" WHERE {where} "
            + " ORDER BY cs.scheduled_for NULLS LAST, cs.priority ASC, cs.id ASC"
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def get_cut_schedule(
    db: Session, *, workspace_id: int, schedule_id: int
) -> dict | None:
    row = db.execute(
        text(
            _SCHEDULE_SELECT
            + " WHERE cs.id = :sid AND cp.workspace_id = :w"
        ),
        {"sid": schedule_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


# ---- CutSchedule: write ----------------------------------------------------

def plan_in_workspace(
    db: Session, *, workspace_id: int, plan_id: int
) -> bool:
    return db.execute(
        text(
            "SELECT 1 FROM cut_plan WHERE id = :pid AND workspace_id = :w"
        ),
        {"pid": plan_id, "w": workspace_id},
    ).first() is not None


def insert_cut_schedule(
    db: Session,
    *,
    workspace_id: int,
    cut_plan_id: int,
    scheduled_for: date_t,
    assigned_to: int | None,
    actor_id: int,
) -> int:
    """Auto-priority = MAX(priority) + 100 for the same date in this workspace, else 100.

    Caller must already hold a row lock on the target cut_plan via
    plan_in_workspace(). Within READ COMMITTED, concurrent INSERTs on the
    same date may briefly produce equal priorities — the reorder route
    is the canonical normaliser.
    """
    next_priority = db.execute(
        text(
            """
            SELECT COALESCE(MAX(cs.priority), 0) + 100
            FROM cut_schedule cs
            JOIN cut_plan cp ON cp.id = cs.cut_plan_id
            WHERE cs.scheduled_for = :d AND cp.workspace_id = :w
            """
        ),
        {"d": scheduled_for, "w": workspace_id},
    ).scalar() or 100
    sid = db.execute(
        text(
            """
            INSERT INTO cut_schedule(
                cut_plan_id, scheduled_for, status, priority,
                assigned_to, created_by
            )
            VALUES (:cpid, :d, 'planned', :pri, :ato, :a)
            RETURNING id
            """
        ),
        {
            "cpid": cut_plan_id,
            "d": scheduled_for,
            "pri": int(next_priority),
            "ato": assigned_to,
            "a": actor_id,
        },
    ).scalar()
    db.flush()
    return sid


# Whitelist of columns that route handlers may update on cut_schedule.
# Keep this in sync with CutSchedulePatchIn in schemas.py. Used by
# update_cut_schedule() to defend against future callers passing
# unsanitised keys into the dynamic SET clause.
_PATCHABLE_COLUMNS: frozenset[str] = frozenset({
    "scheduled_for", "assigned_to", "status", "priority",
})


def update_cut_schedule(
    db: Session,
    *,
    schedule_id: int,
    fields: dict[str, Any],
) -> None:
    """Apply a partial update. Caller already validated transitions."""
    if not fields:
        return
    bad = set(fields) - _PATCHABLE_COLUMNS
    if bad:
        raise ValueError(f"disallowed cut_schedule columns: {sorted(bad)}")
    set_parts: list[str] = []
    params: dict[str, Any] = {"sid": schedule_id}
    for k, v in fields.items():
        set_parts.append(f"{k} = :{k}")
        params[k] = v
    set_parts.append("updated_at = now()")
    db.execute(
        text(
            f"UPDATE cut_schedule SET {', '.join(set_parts)} WHERE id = :sid"
        ),
        params,
    )
    db.flush()


def reorder_cut_schedules(
    db: Session,
    *,
    workspace_id: int,
    day: date_t,
    ordered_ids: list[int],
) -> list[int]:
    """Validate every id is in workspace + on the given day, then write
    dense priorities 100, 200, 300, ... Returns the validated id list in
    the order applied. Raises ValueError when any id is invalid."""
    if not ordered_ids:
        return []
    rows = db.execute(
        text(
            """
            SELECT cs.id
            FROM cut_schedule cs
            JOIN cut_plan cp ON cp.id = cs.cut_plan_id
            WHERE cs.id = ANY(:ids)
              AND cs.scheduled_for = :d
              AND cp.workspace_id = :w
            """
        ),
        {"ids": ordered_ids, "d": day, "w": workspace_id},
    ).all()
    valid_ids = {r[0] for r in rows}
    missing = [i for i in ordered_ids if i not in valid_ids]
    if missing:
        raise ValueError(f"unknown or out-of-scope schedule ids: {missing}")

    for idx, sid in enumerate(ordered_ids):
        db.execute(
            text(
                """
                UPDATE cut_schedule
                SET priority = :p, updated_at = now()
                WHERE id = :sid
                """
            ),
            {"p": (idx + 1) * 100, "sid": sid},
        )
    db.flush()
    return list(ordered_ids)

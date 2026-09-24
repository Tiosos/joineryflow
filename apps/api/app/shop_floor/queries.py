"""SQL queries for shop_floor (sub-project #8).

Routes own the transaction boundary; queries flush only.

Workspace isolation: every query joins through `projects.workspace_id`
or `items.project_id -> projects.workspace_id`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..row_types import joinery_items_only
from .lifecycle import later_stages, prior_stages, shop_floor_order

# Shop Floor is production-only: a related part has no workflow stages at all
# (Plan V1 Q419), so it must never reach a board, a queue or an assignment.
# Applied to the enumerations and to the assign/complete guard. The three
# by-assignment-id / by-log-id lookups are deliberately left unfiltered — they
# are reachable only through a row the guard already refused to create, and B3
# re-keys those two tables to (cutlist_id, stage_key) anyway.
_JOINERY_ITEM = joinery_items_only("i")


# ============================================================================
# Worker registry helpers
# ============================================================================

def is_workspace_worker(
    db: Session, *, workspace_id: int, worker_id: int
) -> bool:
    """True iff worker exists in workspace and has is_shop_worker=true."""
    return db.execute(
        text(
            """
            SELECT 1 FROM app_user
            WHERE id = :wid AND workspace_id = :w
              AND is_shop_worker = true AND is_active = true
            """
        ),
        {"wid": worker_id, "w": workspace_id},
    ).first() is not None


def get_workspace_user(
    db: Session, *, workspace_id: int, user_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT id, email, full_name, auth_role, jtbd_role,
                   is_active, is_shop_worker
            FROM app_user
            WHERE id = :uid AND workspace_id = :w
            """
        ),
        {"uid": user_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def list_project_workers(
    db: Session, *, workspace_id: int, project_id: int
) -> list[dict]:
    """List all is_shop_worker users in the workspace. Project arg is
    accepted for forward-compat (per-project rosters in v3)."""
    rows = db.execute(
        text(
            """
            SELECT id, email, full_name, is_shop_worker
            FROM app_user
            WHERE workspace_id = :w AND is_shop_worker = true
              AND is_active = true
            ORDER BY full_name
            """
        ),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_workspace_users(db: Session, *, workspace_id: int) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT id, email, full_name, auth_role, is_shop_worker, is_active
            FROM app_user
            WHERE workspace_id = :w
            ORDER BY full_name
            """
        ),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def update_worker_flag(
    db: Session, *, workspace_id: int, user_id: int, is_shop_worker: bool
) -> dict | None:
    """Flip the is_shop_worker bit. Returns the updated row, or None if
    the user isn't in this workspace."""
    row = db.execute(
        text(
            """
            UPDATE app_user
            SET is_shop_worker = :flag
            WHERE id = :uid AND workspace_id = :w
            RETURNING id, email, full_name, auth_role, is_shop_worker, is_active
            """
        ),
        {"flag": is_shop_worker, "uid": user_id, "w": workspace_id},
    ).mappings().first()
    db.flush()
    return dict(row) if row else None


def active_assignments_for_worker(
    db: Session, *, workspace_id: int, worker_id: int
) -> list[dict]:
    """Active (assigned/in_progress) assignments a worker still holds, scoped
    to the workspace. Used to block deactivating or un-flagging a worker who
    would otherwise leave orphaned rows on the Foreman board that the
    uniq_active_assignment index then blocks anyone else from taking over."""
    rows = db.execute(
        text(
            f"""
            SELECT wa.assignment_id, wa.cutlist_id, c.cutlist_no,
                   wa.stage_key, wa.status
            FROM worker_assignment wa
            JOIN cutlist c  ON c.cutlist_id = wa.cutlist_id
            JOIN projects p ON p.project_id = c.project_id
            WHERE wa.worker_id = :wid
              AND p.workspace_id = :w
              AND wa.status IN ('assigned', 'in_progress')
            ORDER BY wa.assignment_id
            """
        ),
        {"wid": worker_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


# ============================================================================
# Project / item lookup
# ============================================================================

def project_in_workspace(
    db: Session, *, project_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT project_id, project_code
            FROM projects
            WHERE project_id = :pid AND workspace_id = :w
            """
        ),
        {"pid": project_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def item_for_workspace(
    db: Session, *, item_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            f"""
            SELECT i.item_id, i.project_id, i.cutlist_id, i.painting_req,
                   i.paint_after_assembly, i.deleted, p.project_code
            FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :iid AND p.workspace_id = :w
              AND {_JOINERY_ITEM}
            """
        ),
        {"iid": item_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


# ============================================================================
# Cutlist resolution — Shop Floor keys on the cutlist (Q412, migration 0030)
# ============================================================================

def cutlist_items(db: Session, *, cutlist_id: int) -> list[dict]:
    """Every Joinery Item on a cutlist, with the two flags that set its order.

    This is the unit Shop Floor now works in: one assignment, one completion,
    N items. Related parts are excluded — they have no workflow at all (Q419).
    """
    rows = db.execute(
        text(
            f"""
            SELECT i.item_id, i.num, i.painting_req, i.paint_after_assembly
            FROM items i
            WHERE i.cutlist_id = :cid
              AND {_JOINERY_ITEM}
              AND i.deleted = false
            ORDER BY COALESCE(i.num, CAST(i.item_id AS integer))
            """
        ),
        {"cid": cutlist_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def cutlist_for_workspace(
    db: Session, *, cutlist_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT c.cutlist_id, c.cutlist_no, c.project_id, p.project_code
            FROM cutlist c
            JOIN projects p ON p.project_id = c.project_id
            WHERE c.cutlist_id = :cid AND p.workspace_id = :w
            """
        ),
        {"cid": cutlist_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def cutlist_prior_stages_done(
    db: Session, *, cutlist_id: int, stage_key: str
) -> list[str]:
    """Priors still outstanding across **every** item on the cutlist (Q562).

    `painting_req` and `paint_after_assembly` are per item, so one cutlist can
    carry several different stage orders at once. The cutlist's stage is only
    reachable when it is reachable for all of them, so this unions each item's
    own missing priors. An item whose order excludes PAINTED never contributes
    PAINTED to the result.
    """
    missing: list[str] = []
    for item in cutlist_items(db, cutlist_id=cutlist_id):
        if stage_key not in shop_floor_order(bool(item["paint_after_assembly"])):
            continue
        for s in prior_stages_done(
            db,
            item_id=item["item_id"],
            stage_key=stage_key,
            painting_req=bool(item["painting_req"]),
            paint_after_assembly=bool(item["paint_after_assembly"]),
        ):
            if s not in missing:
                missing.append(s)
    return missing


def fan_out_stage_done(
    db: Session, *, cutlist_id: int, stage_key: str
) -> list[int]:
    """Q439 — write the completion onto every linked item. Returns the ids hit.

    **Selective, not blanket** (Q562): an item whose own order does not contain
    this stage is skipped, so a `painting_req = false` item never receives a
    PAINTED date just because a sibling on the same cutlist needed painting.
    """
    touched: list[int] = []
    for item in cutlist_items(db, cutlist_id=cutlist_id):
        if stage_key not in shop_floor_order(bool(item["paint_after_assembly"])):
            continue
        if stage_key == "PAINTED" and not item["painting_req"]:
            continue
        upsert_item_stage_done(db, item_id=item["item_id"], stage_key=stage_key)
        touched.append(item["item_id"])
    return touched


def fan_in_stage_undone(
    db: Session, *, cutlist_id: int, stage_key: str
) -> list[int]:
    """Q446 — undo reverses the whole cutlist, not one item.

    Q539's late joiner is a no-op here for free: it has no `item_stages` row
    for the stage, so clearing its `done_date` changes nothing.
    """
    touched: list[int] = []
    for item in cutlist_items(db, cutlist_id=cutlist_id):
        clear_item_stage_done(db, item_id=item["item_id"], stage_key=stage_key)
        touched.append(item["item_id"])
    return touched


# ============================================================================
# Stage ordering — done-date introspection
# ============================================================================

def prior_stages_done(
    db: Session,
    *,
    item_id: int,
    stage_key: str,
    painting_req: bool,
    paint_after_assembly: bool,
) -> list[str]:
    """Return the list of priors that are NOT done yet. Empty list -> ok.

    Still per item: Q562 keeps both flags on `items`, and
    `cutlist_prior_stages_done` above unions this across a cutlist.
    """
    priors = prior_stages(
        stage_key,
        painting_req=painting_req,
        paint_after_assembly=paint_after_assembly,
    )
    if not priors:
        return []
    rows = db.execute(
        text(
            """
            SELECT stage_key, done_date
            FROM item_stages
            WHERE item_id = :iid AND stage_key = ANY(:priors)
            """
        ),
        {"iid": item_id, "priors": list(priors)},
    ).mappings().all()
    have: dict[str, Any] = {r["stage_key"]: r["done_date"] for r in rows}
    missing: list[str] = []
    for s in priors:
        if have.get(s) is None:
            missing.append(s)
    return missing


def later_stages_done(
    db: Session,
    *,
    item_id: int,
    stage_key: str,
    painting_req: bool,
    paint_after_assembly: bool,
) -> list[str]:
    """Return the stages AFTER `stage_key` that are already done. Empty -> the
    stage can be undone without leaving a completed successor stranded."""
    after = later_stages(
        stage_key,
        painting_req=painting_req,
        paint_after_assembly=paint_after_assembly,
    )
    if not after:
        return []
    rows = db.execute(
        text(
            """
            SELECT stage_key
            FROM item_stages
            WHERE item_id = :iid AND stage_key = ANY(:keys)
              AND done_date IS NOT NULL
            """
        ),
        {"iid": item_id, "keys": list(after)},
    ).mappings().all()
    done = {r["stage_key"] for r in rows}
    return [s for s in after if s in done]


def cutlist_later_stages_done(
    db: Session, *, cutlist_id: int, stage_key: str
) -> list[str]:
    """Stages after `stage_key` already done on ANY item of the cutlist.

    The undo guard's cutlist form (Q446): undoing a stage whose successor is
    done anywhere on the cutlist would leave the shared workflow out of order.
    """
    blockers: list[str] = []
    for item in cutlist_items(db, cutlist_id=cutlist_id):
        if stage_key not in shop_floor_order(bool(item["paint_after_assembly"])):
            continue
        for s in later_stages_done(
            db,
            item_id=item["item_id"],
            stage_key=stage_key,
            painting_req=bool(item["painting_req"]),
            paint_after_assembly=bool(item["paint_after_assembly"]),
        ):
            if s not in blockers:
                blockers.append(s)
    return blockers


def next_open_stage(
    db: Session,
    *,
    item_id: int,
    painting_req: bool,
    paint_after_assembly: bool,
) -> str | None:
    """Return the first shop-floor stage with done_date IS NULL, in
    the per-item ordering."""
    order = shop_floor_order(paint_after_assembly)
    rows = db.execute(
        text(
            """
            SELECT stage_key, done_date
            FROM item_stages
            WHERE item_id = :iid AND stage_key = ANY(:keys)
            """
        ),
        {"iid": item_id, "keys": list(order)},
    ).mappings().all()
    done: dict[str, Any] = {r["stage_key"]: r["done_date"] for r in rows}
    for s in order:
        if s == "PAINTED" and not painting_req:
            continue
        if done.get(s) is None:
            return s
    return None


# ============================================================================
# Assignment CRUD
# ============================================================================

# `0030` dropped worker_assignment.item_id — an assignment belongs to the
# cutlist. Callers that used to show an item number now show the cutlist
# number plus how many items ride on it.
_ASSIGNMENT_SELECT = """
    SELECT wa.assignment_id, wa.cutlist_id, wa.stage_key, wa.worker_id,
           wa.status, wa.note, wa.assigned_by, wa.assigned_at,
           wa.started_at, wa.ended_at, wa.cancelled_at,
           u.full_name AS worker_name,
           c.cutlist_no,
           c.name AS cutlist_name,
           (SELECT COUNT(*) FROM items li
             WHERE li.cutlist_id = wa.cutlist_id
               AND li.row_type = 'joinery_item'
               AND li.deleted = false) AS item_count
    FROM worker_assignment wa
    LEFT JOIN app_user u ON u.id = wa.worker_id
    JOIN cutlist c ON c.cutlist_id = wa.cutlist_id
"""

# The workspace path for an assignment now runs through its cutlist.
_ASSIGNMENT_WORKSPACE_JOIN = """
    JOIN projects p ON p.project_id = c.project_id
"""


def get_assignment(
    db: Session, *, assignment_id: int, workspace_id: int
) -> dict | None:
    """Return an assignment row scoped to workspace."""
    row = db.execute(
        text(
            _ASSIGNMENT_SELECT
            + """
            JOIN projects p ON p.project_id = c.project_id
            WHERE wa.assignment_id = :aid AND p.workspace_id = :w
            """
        ),
        {"aid": assignment_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def get_active_assignment(
    db: Session, *, cutlist_id: int, stage_key: str
) -> dict | None:
    """Return the live (assigned/in_progress) row for the (cutlist, stage)
    if any. Used to surface assignment_id on a 409."""
    row = db.execute(
        text(
            _ASSIGNMENT_SELECT
            + """
            WHERE wa.cutlist_id = :cid AND wa.stage_key = :sk
              AND wa.status IN ('assigned', 'in_progress')
            """
        ),
        {"cid": cutlist_id, "sk": stage_key},
    ).mappings().first()
    return dict(row) if row else None


def insert_assignment(
    db: Session,
    *,
    cutlist_id: int,
    stage_key: str,
    worker_id: int,
    note: str | None,
    assigned_by: int,
) -> int:
    """One assignment per (cutlist, stage) — 0030 re-keyed this off the item.

    The partial unique index `uniq_active_assignment` raises IntegrityError
    when an active assignment already exists for the pair; the route catches
    it and surfaces the holder.
    """
    sid = db.execute(
        text(
            """
            INSERT INTO worker_assignment(
                cutlist_id, stage_key, worker_id, status, note, assigned_by
            )
            VALUES (:cid, :sk, :wid, 'assigned', :note, :ab)
            RETURNING assignment_id
            """
        ),
        {
            "cid": cutlist_id, "sk": stage_key, "wid": worker_id,
            "note": note, "ab": assigned_by,
        },
    ).scalar()
    db.flush()
    return sid


# Whitelist guarding update_assignment dynamic SET clause.
_PATCHABLE_COLUMNS: frozenset[str] = frozenset({
    "worker_id", "note", "status", "started_at", "ended_at",
    "cancelled_at", "cancelled_by",
})


def update_assignment(
    db: Session, *, assignment_id: int, fields: dict[str, Any],
) -> None:
    if not fields:
        return
    bad = set(fields) - _PATCHABLE_COLUMNS
    if bad:
        raise ValueError(f"disallowed assignment columns: {sorted(bad)}")
    set_parts = [f"{k} = :{k}" for k in fields]
    set_parts.append("updated_at = now()")
    params: dict[str, Any] = {**fields, "aid": assignment_id}
    db.execute(
        text(
            f"UPDATE worker_assignment SET {', '.join(set_parts)} "
            f"WHERE assignment_id = :aid"
        ),
        params,
    )
    db.flush()


def lock_assignment(
    db: Session, *, assignment_id: int, workspace_id: int
) -> dict | None:
    """SELECT … FOR UPDATE on the assignment + return its full row.
    Used by mark-done and undo to serialize concurrent attempts."""
    row = db.execute(
        text(
            """
            SELECT wa.assignment_id, wa.cutlist_id, c.cutlist_no,
                   wa.stage_key, wa.worker_id,
                   wa.status, wa.note, wa.started_at
            FROM worker_assignment wa
            JOIN cutlist c  ON c.cutlist_id = wa.cutlist_id
            JOIN projects p ON p.project_id = c.project_id
            WHERE wa.assignment_id = :aid AND p.workspace_id = :w
            FOR UPDATE OF wa
            """
        ),
        {"aid": assignment_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


# ============================================================================
# Board + station + recent completions
# ============================================================================

def board_cards(
    db: Session, *, workspace_id: int, project_id: int
) -> list[dict]:
    """Return one row per item with its next open shop-floor stage and
    (optional) active assignment.

    Honours per-item paint_after_assembly: when true, MADE comes before
    PAINTED in the priority CASE.
    """
    rows = db.execute(
        text(
            f"""
            WITH item_pool AS (
                SELECT
                    i.item_id, i.num AS item_number, i.code, i.description,
                    i.painting_req, i.paint_after_assembly, i.project_id,
                    i.cutlist_id,
                    (
                        -- Candidates are the full canonical stage list, not
                        -- just item_stages rows that happen to exist: the
                        -- LEFT JOIN makes a MISSING row read as open
                        -- (s.done_date IS NULL), matching next_open_stage().
                        -- Without this, items created via create_item (zero
                        -- stage rows) or seeded (REQ..CNC only) drop off the
                        -- board once their existing rows are done.
                        SELECT so.stage_key
                        FROM (VALUES
                            ('DOWN'), ('CNC'), ('EDGED'), ('PAINTED'), ('MADE')
                        ) AS so(stage_key)
                        LEFT JOIN item_stages s
                               ON s.item_id = i.item_id
                              AND s.stage_key = so.stage_key
                        WHERE s.done_date IS NULL
                          AND (so.stage_key <> 'PAINTED' OR i.painting_req)
                        ORDER BY (
                            CASE
                                WHEN i.paint_after_assembly THEN
                                    CASE so.stage_key
                                        WHEN 'DOWN' THEN 1 WHEN 'CNC' THEN 2
                                        WHEN 'EDGED' THEN 3 WHEN 'MADE' THEN 4
                                        WHEN 'PAINTED' THEN 5
                                    END
                                ELSE
                                    CASE so.stage_key
                                        WHEN 'DOWN' THEN 1 WHEN 'CNC' THEN 2
                                        WHEN 'EDGED' THEN 3 WHEN 'PAINTED' THEN 4
                                        WHEN 'MADE' THEN 5
                                    END
                            END
                        )
                        LIMIT 1
                    ) AS next_stage_key
                FROM items i
                JOIN projects p ON p.project_id = i.project_id
                WHERE p.project_id = :pid
                  AND p.workspace_id = :w
                  AND {_JOINERY_ITEM}
                  AND i.deleted = false
            )
            SELECT ip.item_id, ip.item_number, ip.code, ip.description,
                   ip.painting_req, ip.paint_after_assembly,
                   ip.cutlist_id, ip.next_stage_key,
                   wa.assignment_id, wa.worker_id, wa.status,
                   wa.note, wa.assigned_by, wa.assigned_at,
                   wa.started_at, wa.ended_at, wa.cancelled_at,
                   u.full_name AS worker_name,
                   c.cutlist_no, c.name AS cutlist_name,
                   (SELECT COUNT(*) FROM items li
                     WHERE li.cutlist_id = ip.cutlist_id
                       AND li.row_type = 'joinery_item'
                       AND li.deleted = false) AS item_count
            FROM item_pool ip
            LEFT JOIN worker_assignment wa
              ON wa.cutlist_id = ip.cutlist_id
             AND wa.stage_key = ip.next_stage_key
             AND wa.status IN ('assigned', 'in_progress')
            LEFT JOIN cutlist c ON c.cutlist_id = ip.cutlist_id
            LEFT JOIN app_user u ON u.id = wa.worker_id
            WHERE ip.next_stage_key IS NOT NULL
            ORDER BY ip.next_stage_key, ip.item_number
            """
        ),
        {"pid": project_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def worker_queue(
    db: Session, *, workspace_id: int, worker_id: int
) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT wa.assignment_id, wa.cutlist_id, c.cutlist_no,
                   c.name AS cutlist_name, p.project_code,
                   (SELECT COUNT(*) FROM items li
                     WHERE li.cutlist_id = wa.cutlist_id
                       AND li.row_type = 'joinery_item'
                       AND li.deleted = false) AS item_count,
                   wa.stage_key, wa.status, wa.note,
                   wa.assigned_at, wa.started_at
            FROM worker_assignment wa
            JOIN cutlist c  ON c.cutlist_id = wa.cutlist_id
            JOIN projects p ON p.project_id = c.project_id
            WHERE wa.worker_id = :wid AND p.workspace_id = :w
              AND wa.status IN ('assigned', 'in_progress')
            ORDER BY CASE wa.status
                       WHEN 'in_progress' THEN 0 ELSE 1 END,
                     wa.assigned_at
            """
        ),
        {"wid": worker_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def recent_completions_for_worker(
    db: Session, *, workspace_id: int, worker_id: int, minutes: int = 5
) -> list[dict]:
    rows = db.execute(
        text(
            f"""
            SELECT scl.log_id, scl.cutlist_id, c.cutlist_no,
                   scl.stage_key, scl.completed_at, scl.note
            FROM stage_completion_log scl
            JOIN cutlist c  ON c.cutlist_id = scl.cutlist_id
            JOIN projects p ON p.project_id = c.project_id
            WHERE scl.worker_id = :wid
              AND p.workspace_id = :w
              AND scl.undone_at IS NULL
              AND scl.completed_at > now() - interval '{int(minutes)} minutes'
            ORDER BY scl.completed_at DESC
            """
        ),
        {"wid": worker_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


# ============================================================================
# Mark-done transaction primitives
# ============================================================================

def insert_completion_log(
    db: Session,
    *,
    cutlist_id: int,
    stage_key: str,
    assignment_id: int,
    worker_id: int,
    note: str | None,
) -> int:
    """One log row per (cutlist, stage) completion — Q412 says the completion
    belongs to the cutlist, and every linked item shares its time.

    `item_id` is left NULL: since `0030` it holds provenance for pre-re-key
    rows only (see that migration's docstring).
    """
    log_id = db.execute(
        text(
            """
            INSERT INTO stage_completion_log(
                cutlist_id, stage_key, assignment_id, worker_id, note
            )
            VALUES (:cid, :sk, :aid, :wid, :note)
            RETURNING log_id
            """
        ),
        {"cid": cutlist_id, "sk": stage_key, "aid": assignment_id,
         "wid": worker_id, "note": note},
    ).scalar()
    db.flush()
    return log_id


def upsert_item_stage_done(
    db: Session, *, item_id: int, stage_key: str
) -> None:
    """Mark item_stages.done_date = today for (item, stage). Inserts the
    row if it doesn't exist (some items may not have been pre-seeded
    for a given stage)."""
    db.execute(
        text(
            """
            INSERT INTO item_stages(item_id, stage_key, done_date)
            VALUES (:iid, :sk, CURRENT_DATE)
            ON CONFLICT (item_id, stage_key)
            DO UPDATE SET done_date = CURRENT_DATE
            """
        ),
        {"iid": item_id, "sk": stage_key},
    )
    db.flush()


def clear_item_stage_done(
    db: Session, *, item_id: int, stage_key: str
) -> None:
    db.execute(
        text(
            """
            UPDATE item_stages SET done_date = NULL
            WHERE item_id = :iid AND stage_key = :sk
            """
        ),
        {"iid": item_id, "sk": stage_key},
    )
    db.flush()


def get_completion_log(
    db: Session, *, log_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT scl.log_id, scl.cutlist_id, c.cutlist_no, scl.stage_key,
                   scl.assignment_id, scl.worker_id, scl.completed_at,
                   scl.note, scl.undone_at, scl.undone_by
            FROM stage_completion_log scl
            JOIN cutlist c  ON c.cutlist_id = scl.cutlist_id
            JOIN projects p ON p.project_id = c.project_id
            WHERE scl.log_id = :lid AND p.workspace_id = :w
            """
        ),
        {"lid": log_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def mark_completion_undone(
    db: Session, *, log_id: int, undone_by: int
) -> None:
    db.execute(
        text(
            """
            UPDATE stage_completion_log
            SET undone_at = now(), undone_by = :ub
            WHERE log_id = :lid
            """
        ),
        {"ub": undone_by, "lid": log_id},
    )
    db.flush()

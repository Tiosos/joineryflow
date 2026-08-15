"""SQL queries for shop_floor (sub-project #8).

Routes own the transaction boundary; queries flush only.

Workspace isolation: every query joins through `projects.workspace_id`
or `items.project_id -> projects.workspace_id`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .lifecycle import later_stages, prior_stages, shop_floor_order


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
            """
            SELECT i.item_id, i.project_id, i.painting_req,
                   i.paint_after_assembly, i.deleted, p.project_code
            FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :iid AND p.workspace_id = :w
            """
        ),
        {"iid": item_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


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
    """Return the list of priors that are NOT done yet. Empty list -> ok."""
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

_ASSIGNMENT_SELECT = """
    SELECT wa.assignment_id, wa.item_id, wa.stage_key, wa.worker_id,
           wa.status, wa.note, wa.assigned_by, wa.assigned_at,
           wa.started_at, wa.ended_at, wa.cancelled_at,
           u.full_name AS worker_name
    FROM worker_assignment wa
    LEFT JOIN app_user u ON u.id = wa.worker_id
"""


def get_assignment(
    db: Session, *, assignment_id: int, workspace_id: int
) -> dict | None:
    """Return an assignment row scoped to workspace."""
    row = db.execute(
        text(
            _ASSIGNMENT_SELECT
            + """
            JOIN items i ON i.item_id = wa.item_id
            JOIN projects p ON p.project_id = i.project_id
            WHERE wa.assignment_id = :aid AND p.workspace_id = :w
            """
        ),
        {"aid": assignment_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def get_active_assignment(
    db: Session, *, item_id: int, stage_key: str
) -> dict | None:
    """Return the live (assigned/in_progress) row for the (item, stage)
    if any. Used to surface assignment_id on a 409."""
    row = db.execute(
        text(
            _ASSIGNMENT_SELECT
            + """
            WHERE wa.item_id = :iid AND wa.stage_key = :sk
              AND wa.status IN ('assigned', 'in_progress')
            """
        ),
        {"iid": item_id, "sk": stage_key},
    ).mappings().first()
    return dict(row) if row else None


def insert_assignment(
    db: Session,
    *,
    item_id: int,
    stage_key: str,
    worker_id: int,
    note: str | None,
    assigned_by: int,
) -> int:
    sid = db.execute(
        text(
            """
            INSERT INTO worker_assignment(
                item_id, stage_key, worker_id, status, note, assigned_by
            )
            VALUES (:iid, :sk, :wid, 'assigned', :note, :ab)
            RETURNING assignment_id
            """
        ),
        {
            "iid": item_id, "sk": stage_key, "wid": worker_id,
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
            SELECT wa.assignment_id, wa.item_id, wa.stage_key, wa.worker_id,
                   wa.status, wa.note, wa.started_at,
                   i.painting_req, i.paint_after_assembly
            FROM worker_assignment wa
            JOIN items i ON i.item_id = wa.item_id
            JOIN projects p ON p.project_id = i.project_id
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
            """
            WITH item_pool AS (
                SELECT
                    i.item_id, i.num AS item_number, i.code, i.description,
                    i.painting_req, i.paint_after_assembly, i.project_id,
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
                  AND i.deleted = false
            )
            SELECT ip.item_id, ip.item_number, ip.code, ip.description,
                   ip.painting_req, ip.paint_after_assembly,
                   ip.next_stage_key,
                   wa.assignment_id, wa.worker_id, wa.status,
                   wa.note, wa.assigned_by, wa.assigned_at,
                   wa.started_at, wa.ended_at, wa.cancelled_at,
                   u.full_name AS worker_name
            FROM item_pool ip
            LEFT JOIN worker_assignment wa
              ON wa.item_id = ip.item_id
             AND wa.stage_key = ip.next_stage_key
             AND wa.status IN ('assigned', 'in_progress')
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
            """
            SELECT wa.assignment_id, wa.item_id, i.num AS item_number,
                   i.code, i.description, i.rm_no AS room_no,
                   i.rm_desc AS room_desc, p.project_code,
                   wa.stage_key, wa.status, wa.note,
                   wa.assigned_at, wa.started_at
            FROM worker_assignment wa
            JOIN items i    ON i.item_id    = wa.item_id
            JOIN projects p ON p.project_id = i.project_id
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
            SELECT scl.log_id, scl.item_id, i.num AS item_number,
                   scl.stage_key, scl.completed_at, scl.note
            FROM stage_completion_log scl
            JOIN items i    ON i.item_id    = scl.item_id
            JOIN projects p ON p.project_id = i.project_id
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
    item_id: int,
    stage_key: str,
    assignment_id: int,
    worker_id: int,
    note: str | None,
) -> int:
    log_id = db.execute(
        text(
            """
            INSERT INTO stage_completion_log(
                item_id, stage_key, assignment_id, worker_id, note
            )
            VALUES (:iid, :sk, :aid, :wid, :note)
            RETURNING log_id
            """
        ),
        {"iid": item_id, "sk": stage_key, "aid": assignment_id,
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
            SELECT scl.log_id, scl.item_id, scl.stage_key,
                   scl.assignment_id, scl.worker_id, scl.completed_at,
                   scl.note, scl.undone_at, scl.undone_by,
                   i.painting_req, i.paint_after_assembly
            FROM stage_completion_log scl
            JOIN items i    ON i.item_id    = scl.item_id
            JOIN projects p ON p.project_id = i.project_id
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

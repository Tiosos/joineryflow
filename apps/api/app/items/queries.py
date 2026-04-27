"""SQL query functions for the items module.

Column name mapping (legacy FileMaker schema vs spec):
  items.item_id   -> aliased as id
  items.num       -> aliased as item_number
  items.rm_no     -> aliased as room_no
  items.rm_desc   -> aliased as room_desc
  items.zone      -> str (varchar 16 in DB, not int)
  item_hardware_lines.line_id -> used in JOINs (not .id)
  batch_allocations.item_hardware_line_id -> FK to item_hardware_lines.line_id

Workspace scoping: items have no workspace_id column. Isolation goes via
  items.project_id -> projects.pm_id -> app_user.workspace_id
mirroring the _WORKSPACE_FILTER pattern in projects/queries.py.

Strategy: Two queries rather than one giant GROUP BY + window function:
  Query 1: items with cutlist_owner_name + ready/blocked counts (correlated subqueries).
  Query 2: all item_stages rows for this project, merged in Python into stages dicts.
This avoids GROUP BY fan-out complications with the jsonb_object_agg approach
when combined with the availability correlated subqueries.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

# Workspace isolation clause (items -> projects -> pm_id -> app_user.workspace_id).
_WORKSPACE_FILTER = """
    EXISTS (
        SELECT 1 FROM projects p2
        JOIN app_user au ON au.id = p2.pm_id
        WHERE p2.project_id = i.project_id
          AND au.workspace_id = :wid
    )
"""

_ITEM_COLS = """
    i.item_id                                       AS id,
    i.num                                           AS item_number,
    i.status,
    i.stage,
    i.zone,
    i.level,
    i.rm_no                                         AS room_no,
    i.rm_desc                                       AS room_desc,
    i.code,
    i.description,
    i.qty,
    i.cutlist_owner_id,
    u.full_name                                     AS cutlist_owner_name,
    i.item_locked,
    (
        SELECT COUNT(DISTINCT hl.line_id)
        FROM item_hardware_lines hl
        JOIN batch_allocations ba ON ba.item_hardware_line_id = hl.line_id
        WHERE hl.item_id = i.item_id
    )                                               AS ready,
    (
        SELECT COUNT(*)
        FROM item_hardware_lines hl
        WHERE hl.item_id = i.item_id
          AND NOT EXISTS (
              SELECT 1 FROM batch_allocations ba
              WHERE ba.item_hardware_line_id = hl.line_id
          )
    )                                               AS blocked
"""


def list_items_for_project(
    db: Session,
    *,
    workspace_id: int,
    project_id: int,
    status: str | None = None,
    stage_key: str | None = None,
    q: str | None = None,
) -> list[dict]:
    """Return tracking grid rows for a project, scoped to the caller's workspace.

    Filters:
      status    - exact match on items.status
      stage_key - items currently AT that lifecycle stage (due_date set, done_date NULL)
      q         - ILIKE substring on description or code
    """
    params: dict = {
        "pid": project_id,
        "wid": workspace_id,
        "status": status,
        "stage_key": stage_key,
        "q": q,
    }

    # Query 1: items with availability rollup
    item_rows = db.execute(
        text(
            f"""
            SELECT {_ITEM_COLS}
            FROM items i
            LEFT JOIN app_user u ON u.id = i.cutlist_owner_id
            WHERE i.project_id = :pid
              AND {_WORKSPACE_FILTER}
              AND (CAST(:status AS text) IS NULL OR i.status = :status)
              AND (
                  CAST(:stage_key AS text) IS NULL
                  OR EXISTS (
                      SELECT 1 FROM item_stages s
                      WHERE s.item_id = i.item_id
                        AND s.stage_key = :stage_key
                        AND s.due_date IS NOT NULL
                        AND s.done_date IS NULL
                  )
              )
              AND (
                  CAST(:q AS text) IS NULL
                  OR i.description ILIKE '%' || :q || '%'
                  OR i.code ILIKE '%' || :q || '%'
              )
            ORDER BY COALESCE(i.num, CAST(i.item_id AS integer))
            """
        ),
        params,
    ).mappings().all()

    if not item_rows:
        return []

    item_ids = [r["id"] for r in item_rows]

    # Query 2: fetch all item_stages rows for these items in one shot
    stage_rows = db.execute(
        text(
            """
            SELECT item_id, stage_key, due_date, done_date
            FROM item_stages
            WHERE item_id = ANY(:ids)
            """
        ),
        {"ids": item_ids},
    ).mappings().all()

    # Build stages dict per item_id
    stages_by_item: dict[int, dict] = {iid: {} for iid in item_ids}
    for sr in stage_rows:
        iid = sr["item_id"]
        stages_by_item[iid][sr["stage_key"]] = {
            "due_date": sr["due_date"],
            "done_date": sr["done_date"],
        }

    # Assemble final result list
    results = []
    for r in item_rows:
        item_id = r["id"]
        results.append(
            {
                "id": item_id,
                "item_number": r["item_number"],
                "status": r["status"],
                "stage": r["stage"],
                "zone": r["zone"],
                "level": r["level"],
                "room_no": r["room_no"],
                "room_desc": r["room_desc"],
                "code": r["code"],
                "description": r["description"],
                "qty": r["qty"],
                "cutlist_owner_id": r["cutlist_owner_id"],
                "cutlist_owner_name": r["cutlist_owner_name"],
                "item_locked": bool(r["item_locked"]),
                "stages": stages_by_item.get(item_id, {}),
                "availability": {
                    "ready": int(r["ready"]),
                    "blocked": int(r["blocked"]),
                },
            }
        )

    return results

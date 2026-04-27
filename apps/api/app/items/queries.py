"""SQL query functions for the items module.

Column name mapping (legacy FileMaker schema vs spec):
  items.item_id   -> aliased as id
  items.num       -> aliased as item_number
  items.rm_no     -> aliased as room_no
  items.rm_desc   -> aliased as room_desc
  items.zone      -> str (varchar 16 in DB, not int)
  items.painting_req -> painting_required (aliased)
  items.solid_surface_req -> solid_surface_required (aliased)
  item_hardware_lines.line_id -> used in JOINs (not .id)
  batch_allocations.item_hardware_line_id -> FK to item_hardware_lines.line_id
  project_hardware_catalog.material_type -> catalog_source_table (aliased)
  project_hardware_catalog.material_id -> source_id used in CTE join

Workspace scoping: items have no workspace_id column. Isolation goes via
  items.project_id -> projects.pm_id -> app_user.workspace_id
mirroring the _WORKSPACE_FILTER pattern in projects/queries.py.

Strategy: Two queries rather than one giant GROUP BY + window function:
  Query 1: items with cutlist_owner_name + ready/blocked counts (correlated subqueries).
  Query 2: all item_stages rows for this project, merged in Python into stages dicts.
This avoids GROUP BY fan-out complications with the jsonb_object_agg approach
when combined with the availability correlated subqueries.
"""
from datetime import datetime, timezone

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


def get_item_detail(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    current_user_id: int,
) -> dict | None:
    """Return the full drafter payload for a single item.

    Five small queries instead of one mega-JOIN. The multi-query approach keeps
    each SQL statement simple, avoids GROUP BY fan-out when combining nested
    collections, and mirrors the two-query pattern already established in
    list_items_for_project. Each query is indexed (item_id, workspace FK chain).

    Returns None if the item doesn't exist or belongs to a different workspace.

    Schema drift notes:
    - project_hardware_catalog uses material_type/material_id, not source_table/source_id.
      The 6 catalog tables all use material_id as PK, except equipment_hire which uses hire_id.
    - The 6 catalog tables don't have a uniform "name" column; they use "description".
    - equipment_hire PK column is hire_id, not material_id.
    - parts has no is_rev_c column; hardcoded False.
    - items.painting_req / solid_surface_req aliased to painting_required / solid_surface_required.
    """
    # ── Query 1: Item row + cutlist_owner_name, workspace-scoped ───────────────
    row = db.execute(
        text(
            f"""
            SELECT
                i.item_id                   AS id,
                i.project_id,
                i.num                       AS item_number,
                i.status,
                i.stage,
                i.zone,
                i.level,
                i.rm_no                     AS room_no,
                i.rm_desc                   AS room_desc,
                i.code,
                i.description,
                i.qty,
                i.cutlist_owner_id,
                u.full_name                 AS cutlist_owner_name,
                i.item_locked,
                i.estimator_notes,
                i.painting_req              AS painting_required,
                i.solid_surface_req         AS solid_surface_required,
                i.group_id
            FROM items i
            LEFT JOIN app_user u ON u.id = i.cutlist_owner_id
            WHERE i.item_id = :iid
              AND {_WORKSPACE_FILTER}
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).mappings().first()

    if row is None:
        return None

    row = dict(row)

    # ── Query 2: item_stages pivot ─────────────────────────────────────────────
    stage_rows = db.execute(
        text(
            """
            SELECT stage_key, due_date, done_date
            FROM item_stages
            WHERE item_id = :iid
            """
        ),
        {"iid": item_id},
    ).mappings().all()

    stages: dict = {}
    for sr in stage_rows:
        stages[sr["stage_key"]] = {
            "due_date": sr["due_date"],
            "done_date": sr["done_date"],
        }

    # ── Query 3: Modules + parts ───────────────────────────────────────────────
    # Parts join board_materials for the human-readable board description.
    mod_part_rows = db.execute(
        text(
            """
            SELECT
                m.module_id     AS module_id,
                m.name          AS module_name,
                p.part_id,
                p.qty,
                p.part_name,
                p.len_mm,
                p.wid_mm,
                bm.description  AS board_material,
                p.edge,
                p.colour,
                p.paint_instruction,
                p.comment
            FROM modules m
            LEFT JOIN parts p ON p.module_id = m.module_id
            LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id
            WHERE m.item_id = :iid
            ORDER BY m.module_id, p.part_id
            """
        ),
        {"iid": item_id},
    ).mappings().all()

    # Group parts into modules in Python
    modules_map: dict[int, dict] = {}
    for mp in mod_part_rows:
        mid = mp["module_id"]
        if mid not in modules_map:
            modules_map[mid] = {
                "id": mid,
                "name": mp["module_name"],
                "parts": [],
            }
        # part_id is None when module has no parts (LEFT JOIN)
        if mp["part_id"] is not None:
            modules_map[mid]["parts"].append(
                {
                    "id": mp["part_id"],
                    "module_id": mid,
                    "qty": mp["qty"],
                    "part_name": mp["part_name"],
                    "len_mm": mp["len_mm"],
                    "wid_mm": mp["wid_mm"],
                    "board_material": mp["board_material"],
                    "edge": mp["edge"],
                    "colour": mp["colour"],
                    "paint_instruction": mp["paint_instruction"],
                    "comment": mp["comment"],
                    # parts table has no is_rev_c column — hardcoded False
                    "is_rev_c": False,
                }
            )
    modules = list(modules_map.values())

    # ── Query 4: Hardware lines + catalog resolution ───────────────────────────
    # project_hardware_catalog uses material_type (BOARD/HARDWARE/CUSTOM/etc.)
    # and material_id. The 6 source tables all use material_id as PK, except
    # equipment_hire which uses hire_id. Each table uses "description" (not "name").
    hw_rows = db.execute(
        text(
            """
            WITH src AS (
                SELECT 'BOARD'     AS t, material_id AS sid, description, supplier
                FROM board_materials
                UNION ALL
                SELECT 'HARDWARE', material_id, description, supplier
                FROM hardware_materials
                UNION ALL
                SELECT 'CUSTOM', material_id, description, NULL::text
                FROM custom_made
                UNION ALL
                SELECT 'BENCHTOP', material_id, description, supplier
                FROM benchtop_materials
                UNION ALL
                SELECT 'APPLIANCE', material_id, description, supplier
                FROM appliances
                UNION ALL
                SELECT 'HIRE', hire_id, description, supplier
                FROM equipment_hire
            )
            SELECT
                hl.line_id              AS id,
                hl.catalog_id,
                src.description         AS catalog_description,
                src.supplier            AS catalog_supplier,
                phc.material_type       AS catalog_source_table,
                hl.qty,
                hl.note
            FROM item_hardware_lines hl
            LEFT JOIN project_hardware_catalog phc ON phc.catalog_id = hl.catalog_id
            LEFT JOIN src
                   ON src.t = phc.material_type AND src.sid = phc.material_id
            WHERE hl.item_id = :iid
            ORDER BY hl.line_id
            """
        ),
        {"iid": item_id},
    ).mappings().all()

    hardware_lines = [
        {
            "id": hw["id"],
            "catalog_id": hw["catalog_id"],
            "catalog_description": hw["catalog_description"],
            "catalog_supplier": hw["catalog_supplier"],
            "catalog_source_table": hw["catalog_source_table"],
            "qty": hw["qty"],
            "note": hw["note"],
        }
        for hw in hw_rows
    ]

    # ── Query 5: Last 50 edit log rows ─────────────────────────────────────────
    log_rows = db.execute(
        text(
            """
            SELECT el.log_id, el.actor_id, u.full_name AS actor_name,
                   el.field, el.old_value, el.new_value, el.ts
            FROM item_edit_log el
            LEFT JOIN app_user u ON u.id = el.actor_id
            WHERE el.item_id = :iid
            ORDER BY el.ts DESC
            LIMIT 50
            """
        ),
        {"iid": item_id},
    ).mappings().all()

    edit_log = [
        {
            "log_id": lr["log_id"],
            "actor_id": lr["actor_id"],
            "actor_name": lr["actor_name"],
            "field": lr["field"],
            "old_value": lr["old_value"],
            "new_value": lr["new_value"],
            "ts": lr["ts"],
        }
        for lr in log_rows
    ]

    # ── lock_warning: computed in Python ──────────────────────────────────────
    lock_warning = None
    owner_id = row["cutlist_owner_id"]
    if row["item_locked"] and owner_id is not None and owner_id != current_user_id:
        # Resolve owner's display name
        owner_row = db.execute(
            text("SELECT full_name FROM app_user WHERE id = :oid"),
            {"oid": owner_id},
        ).mappings().first()
        owner_name = owner_row["full_name"] if owner_row else "Unknown"

        # Last edit timestamp from edit_log
        last_ts_row = db.execute(
            text("SELECT MAX(ts) AS last_ts FROM item_edit_log WHERE item_id = :iid"),
            {"iid": item_id},
        ).mappings().first()
        last_ts = last_ts_row["last_ts"] if last_ts_row else None

        now = datetime.now(tz=timezone.utc)
        if last_ts is not None:
            # Ensure last_ts is timezone-aware for subtraction
            if last_ts.tzinfo is None:
                last_ts = last_ts.replace(tzinfo=timezone.utc)
            minutes_ago = int((now - last_ts).total_seconds() // 60)
        else:
            minutes_ago = 0

        lock_warning = {
            "owner_id": owner_id,
            "owner_name": owner_name,
            "last_edit_minutes_ago": minutes_ago,
        }

    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "item_number": row["item_number"],
        "status": row["status"],
        "stage": row["stage"],
        "zone": row["zone"],
        "level": row["level"],
        "room_no": row["room_no"],
        "room_desc": row["room_desc"],
        "code": row["code"],
        "description": row["description"],
        "qty": row["qty"],
        "cutlist_owner_id": owner_id,
        "item_locked": bool(row["item_locked"]),
        "estimator_notes": row["estimator_notes"],
        "painting_required": row["painting_required"],
        "solid_surface_required": row["solid_surface_required"],
        "group_id": row["group_id"],
        "stages": stages,
        "modules": modules,
        "hardware_lines": hardware_lines,
        "edit_log": edit_log,
        "lock_warning": lock_warning,
    }

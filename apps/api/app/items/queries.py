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
import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.sessions import AuthUser
from ..edit_log import write_edit_log, write_edit_log_many
from ..row_types import joinery_items_only
from .schemas import CreateItemIn, PatchItemIn, PatchLifecycleIn

# The drafter editor and the availability drawer are cutlist surfaces: neither
# means anything for a related part (Q417/Q447), so both 404 on its id.  The
# Tracking LIST is deliberately different — it returns related parts inline,
# nested under their parent (Q420/Q422) — and so carries no filter.
_JOINERY_I = joinery_items_only("i")

# Workspace isolation clause (items -> projects.workspace_id direct FK, since 0014).
_WORKSPACE_FILTER = """
    EXISTS (
        SELECT 1 FROM projects p2
        WHERE p2.project_id = i.project_id
          AND p2.workspace_id = :wid
    )
"""

_ITEM_COLS = """
    i.item_id                                       AS id,
    i.num                                           AS item_number,
    i.row_type,
    i.parent_item_id,
    i.related_part_type_key,
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
    -- Q417 + Q567: the leftmost Tracking reference is the cutlist number for a
    -- Joinery Item and the ISSUED supplier-order number for a related part.
    -- "Issued" is `date_ordered IS NOT NULL` -- the column that records the day
    -- the order went to the supplier -- because no order status means issued
    -- (0002's CHECK has Draft/Pending/Approved/... and no Issued).  A part may
    -- carry several orders, so the most recent issued one wins.
    ord.po_number                                   AS issued_order_no,
    ord.po_id                                       AS issued_order_po_id,
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
            LEFT JOIN items parent ON parent.item_id = i.parent_item_id
            LEFT JOIN LATERAL (
                SELECT po.po_id, po.po_number
                  FROM purchase_orders po
                 WHERE po.item_id = i.item_id
                   AND po.date_ordered IS NOT NULL
                 ORDER BY po.date_ordered DESC, po.po_id DESC
                 LIMIT 1
            ) ord ON true
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
            -- Q420: a related part sorts with its PARENT, directly beneath it —
            -- not at its own number's position.  Q541 draws Item IDs and cutlist
            -- numbers from one shared sequence, so a child's `num` is nowhere
            -- near its parent's and ordering by `num` alone would scatter them.
            ORDER BY COALESCE(parent.num, i.num, CAST(i.item_id AS integer)),
                     CASE WHEN i.row_type = 'related_part' THEN 1 ELSE 0 END,
                     COALESCE(i.num, CAST(i.item_id AS integer))
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
                # Q558: the list carries both row kinds; the web nests on these.
                "row_type": r["row_type"],
                "parent_item_id": r["parent_item_id"],
                "related_part_type_key": r["related_part_type_key"],
                "issued_order_no": r["issued_order_no"],
                "issued_order_po_id": r["issued_order_po_id"],
                "stages": stages_by_item.get(item_id, {}),
                "availability": {
                    "ready": int(r["ready"]),
                    "blocked": int(r["blocked"]),
                },
            }
        )

    return results


def get_item_availability(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
) -> dict | None:
    """Return per-hardware-line availability roll-up for an item.

    Status semantics (derived from procurement_batches.received_date):
      - 'ready'   : at least one linked procurement_batch has received_date IS NOT NULL.
      - 'ordered' : at least one batch_allocation exists but no batch has been received yet.
      - 'none'    : no batch_allocation rows for this line.

    Schema drift vs. spec:
      - batch_allocations has no received_at column; received state is
        procurement_batches.received_date IS NOT NULL.
      - procurement_batches.expected_arrival -> eta_date.
      - procurement_batches.id -> batch_id.

    For lines with multiple batches, returns the batch with the latest eta_date
    (NULLS LAST) as the representative batch_id and eta.

    Returns None if the item does not exist or belongs to a different workspace.
    """
    # Workspace visibility check: same EXISTS chain as _WORKSPACE_FILTER.
    #
    # Joinery Items only.  Availability is computed from hardware lines joined
    # to procurement batches; a related part has no hardware lines (Q447) and
    # is procured through its own supplier order (Q424).  Serving it an empty
    # drawer would read identically to "nothing outstanding", so it 404s.
    exists_row = db.execute(
        text(
            f"""
            SELECT 1
            FROM items i
            WHERE i.item_id = :iid
              AND {_WORKSPACE_FILTER}
              AND {joinery_items_only("i")}
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).first()

    if exists_row is None:
        return None

    # Aggregate per hardware line.
    #
    # Procurement Workbench v1: enrich each line with per-line procurement
    # metadata. The base CTE preserves the original status/eta/batch_id semantics
    # (PM Workbench contract). Additional joins/LATERAL subqueries surface:
    #   - seq, catalog_id, qty_needed       from item_hardware_lines
    #   - material_type, material_id        from project_hardware_catalog
    #   - qty_on_order / qty_received       summed from procurement_batches
    #                                       (project + material scoped, open=not received/cancelled)
    #   - earliest_eta                      MIN(eta_date) over open batches
    #   - qty_allocated_to_line             SUM(qty_allocated) for this specific line
    line_rows = db.execute(
        text(
            f"""
            WITH lines AS (
                SELECT hl.line_id, hl.item_id, hl.seq, hl.qty AS qty_needed,
                       hl.catalog_id
                FROM item_hardware_lines hl
                WHERE hl.item_id = :iid
            ),
            base AS (
                SELECT
                    l.line_id,
                    CASE
                        WHEN COUNT(pb.batch_id) FILTER (
                            WHERE pb.received_date IS NOT NULL
                        ) > 0 THEN 'ready'
                        WHEN COUNT(ba.allocation_id) > 0 THEN 'ordered'
                        ELSE 'none'
                    END                                                 AS status,
                    MAX(pb.eta_date)                                    AS eta,
                    (
                        ARRAY_AGG(
                            pb.batch_id
                            ORDER BY pb.eta_date DESC NULLS LAST
                        )
                    )[1]                                                AS batch_id
                FROM lines l
                LEFT JOIN batch_allocations ba
                       ON ba.item_hardware_line_id = l.line_id
                LEFT JOIN procurement_batches pb
                       ON pb.batch_id = ba.batch_id
                GROUP BY l.line_id
            )
            SELECT
                l.line_id,
                l.seq,
                l.catalog_id,
                l.qty_needed,
                phc.material_type,
                phc.material_id,
                b.status,
                b.eta,
                b.batch_id,
                COALESCE(mat.qty_received, 0)                           AS qty_received,
                COALESCE(mat.qty_on_order, 0)                           AS qty_on_order,
                mat.earliest_eta                                        AS earliest_eta,
                COALESCE(alloc.qty_allocated_to_line, 0)                AS qty_allocated_to_line
            FROM lines l
            JOIN base b USING (line_id)
            JOIN items i ON i.item_id = l.item_id AND {_JOINERY_I}
            LEFT JOIN project_hardware_catalog phc
                   ON phc.catalog_id = l.catalog_id
            LEFT JOIN LATERAL (
                SELECT
                    SUM(pb2.qty_received)                               AS qty_received,
                    SUM(pb2.qty_ordered)
                      FILTER (WHERE pb2.received_date IS NULL
                              AND pb2.cancelled_at IS NULL)             AS qty_on_order,
                    MIN(pb2.eta_date)
                      FILTER (WHERE pb2.received_date IS NULL
                              AND pb2.cancelled_at IS NULL)             AS earliest_eta
                FROM procurement_batches pb2
                WHERE pb2.project_id    = i.project_id
                  AND pb2.material_type = phc.material_type
                  AND pb2.material_id   = phc.material_id
            ) mat ON TRUE
            LEFT JOIN LATERAL (
                SELECT SUM(ba2.qty_allocated)                           AS qty_allocated_to_line
                FROM batch_allocations ba2
                WHERE ba2.item_hardware_line_id = l.line_id
            ) alloc ON TRUE
            ORDER BY l.line_id
            """
        ),
        {"iid": item_id},
    ).mappings().all()

    lines = [
        {
            "line_id": r["line_id"],
            "status": r["status"],
            "eta": r["eta"],
            "batch_id": r["batch_id"],
            "seq": r["seq"],
            "catalog_id": r["catalog_id"],
            "material_type": r["material_type"],
            "material_id": r["material_id"],
            "qty_needed": r["qty_needed"],
            "qty_received": r["qty_received"],
            "qty_on_order": r["qty_on_order"],
            "qty_allocated_to_line": r["qty_allocated_to_line"],
            "earliest_eta": r["earliest_eta"],
        }
        for r in line_rows
    ]

    return {"item_id": item_id, "lines": lines}


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
              AND {_JOINERY_I}
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


# ── Write helpers (T15) ────────────────────────────────────────────────────────


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    """Return True if the project belongs to workspace_id (direct FK, since 0014)."""
    row = db.execute(
        text(
            """
            SELECT 1 FROM projects p
            WHERE p.project_id = :pid AND p.workspace_id = :wid
            """
        ),
        {"pid": project_id, "wid": workspace_id},
    ).first()
    return row is not None


def _item_row(db: Session, *, item_id: int, workspace_id: int) -> dict | None:
    """Fetch bare item columns for mutation helpers.  Returns None if 404.

    Deliberately **not** filtered to Joinery Items: the related-part routes
    (Q450 own status, Q452 reparent) reach their rows through this helper.
    It returns `row_type` so each caller can decide — see `patch_lifecycle`
    and `claim_or_release_lock`, which refuse related parts.
    """
    row = db.execute(
        text(
            f"""
            SELECT
                i.item_id,
                i.row_type,
                i.project_id,
                i.description,
                i.qty,
                i.stage,
                i.code,
                i.level,
                i.rm_no,
                i.rm_desc,
                i.zone,
                i.estimator_notes,
                i.painting_req,
                i.solid_surface_req,
                i.item_locked,
                i.cutlist_owner_id
            FROM items i
            WHERE i.item_id = :iid
              AND {_WORKSPACE_FILTER}
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row is not None else None


def create_item(
    db: Session,
    *,
    workspace_id: int,
    project_id: int,
    payload: CreateItemIn,
    actor_id: int,
) -> int | None:
    """INSERT a new item.  Returns new item_id, or None if project not in workspace.

    `items.num` has a global UNIQUE constraint (legacy FK artefact) and is
    allocated from **`joinery_number_seq`** (migration `0027`), the single
    company-wide counter Q541 requires: Item IDs, cutlist numbers and related
    parts all draw from it, so a six-digit number never means two things.

    This replaced `nextval('items_item_id_seq') + 100000`, which borrowed the
    PK sequence and therefore burned two values per insert (the explicit
    nextval here, plus the column DEFAULT for `item_id`).
    """
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None

    iid = db.execute(
        text(
            """
            INSERT INTO items(
                num, project_id, status,
                description, qty, stage, code, level,
                rm_no, rm_desc, zone, item_locked
            )
            VALUES (
                nextval('joinery_number_seq'),
                :pid, 'CLEAR',
                :desc, :qty, :stage, :code, :level,
                :room_no, :room_desc, :zone, false
            )
            RETURNING item_id
            """
        ),
        {
            "pid": project_id,
            "desc": payload.description,
            "qty": payload.qty,
            "stage": payload.stage,
            "code": payload.code,
            "level": payload.level,
            "room_no": payload.room_no,
            "room_desc": payload.room_desc,
            "zone": payload.zone,
        },
    ).scalar()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.create",
        target=str(iid),
        payload={"project_id": project_id, "description": payload.description},
    )
    write_edit_log(
        db,
        item_id=iid,
        actor_id=actor_id,
        field="_create",
        old_value=None,
        new_value=str(payload.model_dump(exclude_none=True)),
    )
    return iid


# Field map: PatchItemIn attribute -> (DB column, old_value_key_in_row)
_PATCH_FIELD_MAP: list[tuple[str, str, str]] = [
    ("description",          "description",     "description"),
    ("qty",                  "qty",             "qty"),
    ("stage",                "stage",           "stage"),
    ("code",                 "code",            "code"),
    ("level",                "level",           "level"),
    ("room_no",              "rm_no",           "rm_no"),
    ("room_desc",            "rm_desc",         "rm_desc"),
    ("zone",                 "zone",            "zone"),
    ("estimator_notes",      "estimator_notes", "estimator_notes"),
    ("painting_required",    "painting_req",    "painting_req"),
    ("solid_surface_required","solid_surface_req","solid_surface_req"),
]


def _apply_item_changes(
    db: Session,
    *,
    item_id: int,
    current: dict,
    payload: PatchItemIn,
    author_id: int,
    extra_updates: dict[str, object] | None = None,
) -> list[tuple[str, str | None, str | None]]:
    """Write the fields of `payload` that actually differ from `current`.

    Shared by the owner's own save and by the approval of someone else's
    Controlled-Lock request, so an approved request lands exactly as a direct
    save would.  `author_id` is who gets credited in `item_edit_log` — the
    person whose change it is, which on an approval is the *requester*, not the
    approver (the approver is named in the audit row instead).

    Returns the (field, old, new) tuples it logged.
    """
    updates: dict[str, object] = dict(extra_updates or {})
    changes: list[tuple[str, str | None, str | None]] = []

    for attr, col, row_key in _PATCH_FIELD_MAP:
        new_val = getattr(payload, attr)
        if new_val is None:
            continue
        old_val = current.get(row_key)
        if new_val != old_val:
            updates[col] = new_val
            changes.append((attr, None if old_val is None else str(old_val), str(new_val)))

    if updates:
        set_clauses = ", ".join(f"{col} = :{col}" for col in updates)
        db.execute(
            text(f"UPDATE items SET {set_clauses}, updated_at = now() WHERE item_id = :iid"),
            {"iid": item_id, **updates},
        )
        db.flush()

    if changes:
        write_edit_log_many(db, item_id=item_id, actor_id=author_id, changes=changes)

    return changes


def _changed_fields(payload: PatchItemIn, current: dict) -> dict[str, object]:
    """The submitted fields that would actually change `current`, as a jsonb body."""
    out: dict[str, object] = {}
    for attr, _col, row_key in _PATCH_FIELD_MAP:
        new_val = getattr(payload, attr)
        if new_val is None:
            continue
        if new_val != current.get(row_key):
            out[attr] = new_val
    return out


def patch_item(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    payload: PatchItemIn,
    actor_id: int,
) -> dict | None:
    """Apply a partial update to an item.  None if not found/out-of-workspace.

    Controlled Lock (Q509, replacing the advisory soft-lock of spec §6.4):
    - cutlist_owner_id IS NULL:      first save claims — item_locked=true, owner=actor.
    - item_locked AND owner != actor: the save does **not** apply.  It is held as
      a pending `item_lock_request` for the owner or a manager to decide, and
      the caller gets 409.  Saving again revises your own pending request
      rather than stacking a second one (uniq_pending_lock_request).
    - otherwise:                     applies directly.

    Returns `{"outcome": "applied"}` or `{"outcome": "lock_request", "request": {...}}`.
    Edit log: one row per changed field.
    """
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return None

    owner_id: int | None = current["cutlist_owner_id"]
    is_locked: bool = bool(current["item_locked"])

    if is_locked and owner_id is not None and owner_id != actor_id:
        proposed = _changed_fields(payload, current)
        if not proposed:
            # Nothing would change — no request to raise, and nothing applied.
            return {"outcome": "applied"}
        request = _upsert_lock_request(
            db,
            item_id=item_id,
            workspace_id=workspace_id,
            requester_id=actor_id,
            owner_id=owner_id,
            proposed=proposed,
        )
        return {"outcome": "lock_request", "request": request}

    extra: dict[str, object] = {}
    if owner_id is None:
        # First-save claim
        extra = {"item_locked": True, "cutlist_owner_id": actor_id}

    _apply_item_changes(
        db,
        item_id=item_id,
        current=current,
        payload=payload,
        author_id=actor_id,
        extra_updates=extra,
    )
    return {"outcome": "applied"}


def delete_item(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    actor_id: int,
) -> str:
    """Delete an item.  Returns 'OK', 'NOT_FOUND', or 'IN_USE'.

    IN_USE if any item_hardware_lines for this item are referenced by
    batch_allocations — indicates procurement data would be orphaned.
    Writes audit and edit_log BEFORE the delete so foreign-key cascade
    doesn't remove the log target.
    """
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    # Guard: any hardware lines referenced by batch_allocations?
    in_use = db.execute(
        text(
            """
            SELECT 1 FROM item_hardware_lines hl
            JOIN batch_allocations ba ON ba.item_hardware_line_id = hl.line_id
            WHERE hl.item_id = :iid
            LIMIT 1
            """
        ),
        {"iid": item_id},
    ).first()
    if in_use is not None:
        return "IN_USE"

    # Write audit + edit_log before DELETE (CASCADE would nuke item_edit_log)
    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.delete",
        target=str(item_id),
        payload={"description": current.get("description")},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_delete",
        old_value=str(current.get("description")),
        new_value=None,
    )

    db.execute(text("DELETE FROM items WHERE item_id = :iid"), {"iid": item_id})
    db.flush()
    return "OK"


# ── T16 write helpers ─────────────────────────────────────────────────────────

VALID_STAGE_KEYS = (
    "REQ", "SM", "LISTED", "DOWN", "CNC",
    "EDGED", "PAINTED", "MADE", "DEL", "INST",
)


def patch_item_status(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    status: str,
    note: str | None = None,
    actor_id: int,
) -> bool:
    """Update items.status.  Returns True if updated, False if item not found.

    Writes to item_status_log (the actual table, which records status changes
    with columns: item_id, status, note, changed_by), audit_log, and item_edit_log.
    """
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return False

    prev_status = db.execute(
        text("SELECT status FROM items WHERE item_id = :iid"),
        {"iid": item_id},
    ).scalar()

    db.execute(
        text(
            "UPDATE items SET status = :s, updated_at = now() WHERE item_id = :iid"
        ),
        {"s": status, "iid": item_id},
    )
    db.flush()

    # item_status_log records status changes: (item_id, status, note, changed_by)
    db.execute(
        text(
            """
            INSERT INTO item_status_log(item_id, status, note, changed_by)
            VALUES (:iid, :s, :n, :cb)
            """
        ),
        {"iid": item_id, "s": status, "n": note or "", "cb": str(actor_id)},
    )
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="item.status",
        target=str(item_id),
        payload={"old": prev_status, "new": status, "note": note},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="item.status",
        old_value=prev_status,
        new_value=status,
    )
    return True


def patch_lifecycle(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    stage_key: str,
    payload: PatchLifecycleIn,
    actor_id: int,
) -> str:
    """UPSERT item_stages row for (item_id, stage_key).

    Returns 'OK', 'NOT_FOUND', or 'INVALID_STAGE_KEY'.

    Writes audit_log and item_edit_log per changed field.
    Does NOT write to item_status_log — that table is for status changes,
    not lifecycle date changes (schema drift from spec).
    """
    if stage_key not in VALID_STAGE_KEYS:
        return "INVALID_STAGE_KEY"

    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    # Q419: a related part shows no workflow stages at all, so it has no
    # lifecycle to patch.  NOT_FOUND rather than a new sentinel — the stage
    # genuinely does not exist for this row.
    if current["row_type"] != "joinery_item":
        return "NOT_FOUND"

    # Fetch current stage row (if any) to capture old values for edit_log
    existing = db.execute(
        text(
            """
            SELECT due_date, done_date
            FROM item_stages
            WHERE item_id = :iid AND stage_key = :sk
            """
        ),
        {"iid": item_id, "sk": stage_key},
    ).mappings().first()

    old_due = existing["due_date"] if existing else None
    old_done = existing["done_date"] if existing else None

    # UPSERT: composite PK (item_id, stage_key) guarantees uniqueness
    db.execute(
        text(
            """
            INSERT INTO item_stages(item_id, stage_key, due_date, done_date)
            VALUES (:iid, :sk, :due, :done)
            ON CONFLICT (item_id, stage_key)
            DO UPDATE SET
                due_date  = COALESCE(EXCLUDED.due_date,  item_stages.due_date),
                done_date = COALESCE(EXCLUDED.done_date, item_stages.done_date)
            """
        ),
        {
            "iid": item_id,
            "sk": stage_key,
            "due": payload.due_date,
            "done": payload.done_date,
        },
    )
    db.flush()

    # Audit and edit_log per changed field
    audit_payload: dict = {}
    changes: list[tuple[str, str | None, str | None]] = []

    if payload.due_date is not None and payload.due_date != old_due:
        field_name = f"lifecycle.{stage_key}.due_date"
        audit_payload["due_date"] = str(payload.due_date)
        changes.append((field_name, str(old_due) if old_due else None, str(payload.due_date)))

    if payload.done_date is not None and payload.done_date != old_done:
        field_name = f"lifecycle.{stage_key}.done_date"
        audit_payload["done_date"] = str(payload.done_date)
        changes.append((field_name, str(old_done) if old_done else None, str(payload.done_date)))

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event=f"item.lifecycle.{stage_key}",
        target=str(item_id),
        payload=audit_payload,
    )

    if changes:
        write_edit_log_many(db, item_id=item_id, actor_id=actor_id, changes=changes)

    return "OK"


def claim_or_release_lock(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    actor: AuthUser,
    action: str,
    owner_id: int | None = None,
) -> str:
    """Manage soft-lock state.  action ∈ {'claim', 'release', 'transfer'}.

    Returns 'OK', 'NOT_FOUND', or 'FORBIDDEN'.

    claim   (POST /items/{id}/lock, no body):
        Always takes lock for actor.
    release (DELETE /items/{id}/lock):
        Clears item_locked; cutlist_owner_id is NOT cleared (sticky claim).
    transfer (POST /items/{id}/lock with {owner_id: N}):
        Requires actor == current owner OR auth_role in {manager, admin}.
        Verifies new owner_id is in caller's workspace.
    """
    current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"

    # The soft-lock guards cutlist ownership, and a related part has no
    # cutlist (Q417), so it can neither be claimed nor assigned.
    if current["row_type"] != "joinery_item":
        return "NOT_FOUND"

    prior_owner: int | None = current["cutlist_owner_id"]

    if action == "claim":
        db.execute(
            text(
                """
                UPDATE items
                   SET item_locked = true,
                       cutlist_owner_id = :actor_id,
                       updated_at = now()
                 WHERE item_id = :iid
                """
            ),
            {"actor_id": actor.id, "iid": item_id},
        )
        db.flush()
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor.id,
            event="item.lock",
            target=str(item_id),
            payload={},
        )

    elif action == "release":
        db.execute(
            text(
                """
                UPDATE items
                   SET item_locked = false,
                       updated_at = now()
                 WHERE item_id = :iid
                """
            ),
            {"iid": item_id},
        )
        db.flush()
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor.id,
            event="item.unlock",
            target=str(item_id),
            payload={},
        )

    elif action == "transfer":
        # Permission: must be current owner OR manager/admin
        if prior_owner != actor.id and actor.auth_role not in ("manager", "admin"):
            return "FORBIDDEN"

        # Validate new owner is in caller's workspace
        new_owner_row = db.execute(
            text("SELECT 1 FROM app_user WHERE id = :uid AND workspace_id = :wid"),
            {"uid": owner_id, "wid": workspace_id},
        ).first()
        if new_owner_row is None:
            return "FORBIDDEN"

        db.execute(
            text(
                """
                UPDATE items
                   SET cutlist_owner_id = :new_owner,
                       item_locked = true,
                       updated_at = now()
                 WHERE item_id = :iid
                """
            ),
            {"new_owner": owner_id, "iid": item_id},
        )
        db.flush()
        write_audit(
            db,
            workspace_id=workspace_id,
            actor_id=actor.id,
            event="item.lock_transfer",
            target=str(item_id),
            payload={"from": prior_owner, "to": owner_id},
        )

    return "OK"


# ── Controlled Lock: requests (B7 / Q509) ─────────────────────────────────────

_LOCK_REQUEST_COLS = """
    r.request_id,
    r.item_id,
    r.requested_by,
    ru.full_name                    AS requested_by_name,
    r.requested_changes,
    r.status,
    r.created_at,
    r.updated_at,
    r.decided_by,
    du.full_name                    AS decided_by_name,
    r.decided_at,
    r.decision_note
"""


def _lock_request_row(db: Session, *, request_id: int, workspace_id: int) -> dict | None:
    """One request, scoped to the caller's workspace through its item's project."""
    row = db.execute(
        text(
            f"""
            SELECT {_LOCK_REQUEST_COLS}, i.cutlist_owner_id
              FROM item_lock_request r
              JOIN items i    ON i.item_id = r.item_id
              JOIN projects p ON p.project_id = i.project_id
              JOIN app_user ru ON ru.id = r.requested_by
         LEFT JOIN app_user du ON du.id = r.decided_by
             WHERE r.request_id = :rid
               AND p.workspace_id = :wid
            """
        ),
        {"rid": request_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def _upsert_lock_request(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    requester_id: int,
    owner_id: int,
    proposed: dict,
) -> dict:
    """Record (or revise) the requester's pending request on this item.

    `uniq_pending_lock_request` makes this an upsert: a second save by the same
    person replaces their own undecided proposal, so the owner always decides
    on the latest version rather than a queue of stale ones.
    """
    rid = db.execute(
        text(
            """
            INSERT INTO item_lock_request (item_id, requested_by, requested_changes)
            VALUES (:iid, :uid, CAST(:changes AS jsonb))
            ON CONFLICT (item_id, requested_by) WHERE status = 'pending'
            DO UPDATE SET requested_changes = EXCLUDED.requested_changes,
                          updated_at = now()
            RETURNING request_id
            """
        ),
        {"iid": item_id, "uid": requester_id, "changes": json.dumps(proposed)},
    ).scalar()
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=requester_id,
        event="item.lock_request.create",
        target=str(item_id),
        payload={
            "request_id": rid,
            "owner_id": owner_id,
            "fields": sorted(proposed),
        },
    )
    return _lock_request_row(db, request_id=rid, workspace_id=workspace_id) or {}


def list_lock_requests(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    status: str | None = None,
) -> list[dict] | None:
    """Requests on an item, newest first.  None if the item is out of workspace."""
    if _item_row(db, item_id=item_id, workspace_id=workspace_id) is None:
        return None
    rows = db.execute(
        text(
            f"""
            SELECT {_LOCK_REQUEST_COLS}
              FROM item_lock_request r
              JOIN app_user ru ON ru.id = r.requested_by
         LEFT JOIN app_user du ON du.id = r.decided_by
             WHERE r.item_id = :iid
               AND (CAST(:status AS varchar) IS NULL OR r.status = :status)
          ORDER BY r.request_id DESC
            """
        ),
        {"iid": item_id, "status": status},
    ).mappings().all()
    return [dict(r) for r in rows]


def decide_lock_request(
    db: Session,
    *,
    request_id: int,
    workspace_id: int,
    actor: AuthUser,
    decision: str,
    note: str | None,
) -> str | dict:
    """Approve or reject a pending request.  decision ∈ {'approved', 'rejected'}.

    Returns 'NOT_FOUND', 'FORBIDDEN', 'ALREADY_DECIDED', or the decided row.

    Who may decide: the current lock owner, or a manager/admin — the same rule
    `claim_or_release_lock` already applies to transferring the lock, since
    both amount to overriding the owner.

    Approval replays the stored body through the ordinary save path, so fields
    the owner has since changed to the requested value are simply no-ops and
    the edit log still credits the requester.
    """
    row = _lock_request_row(db, request_id=request_id, workspace_id=workspace_id)
    if row is None:
        return "NOT_FOUND"
    if row["status"] != "pending":
        return "ALREADY_DECIDED"
    if row["cutlist_owner_id"] != actor.id and actor.auth_role not in ("manager", "admin"):
        return "FORBIDDEN"

    item_id = row["item_id"]
    applied: list[str] = []

    if decision == "approved":
        current = _item_row(db, item_id=item_id, workspace_id=workspace_id)
        if current is None:          # item deleted between request and decision
            return "NOT_FOUND"
        changes = _apply_item_changes(
            db,
            item_id=item_id,
            current=current,
            payload=PatchItemIn(**row["requested_changes"]),
            author_id=row["requested_by"],
        )
        applied = [field for field, _old, _new in changes]

    db.execute(
        text(
            """
            UPDATE item_lock_request
               SET status = :status,
                   decided_by = :actor,
                   decided_at = now(),
                   decision_note = :note,
                   updated_at = now()
             WHERE request_id = :rid
            """
        ),
        {"status": decision, "actor": actor.id, "note": note, "rid": request_id},
    )
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor.id,
        event=f"item.lock_request.{'approve' if decision == 'approved' else 'reject'}",
        target=str(item_id),
        payload={
            "request_id": request_id,
            "requested_by": row["requested_by"],
            "fields": sorted(row["requested_changes"]),
            "applied_fields": applied,
            "note": note,
        },
    )
    return _lock_request_row(db, request_id=request_id, workspace_id=workspace_id) or {}

"""Item reads: the Tracking list, the availability drawer and the item detail.

Part of the items queries facade (see `queries.py`)."""

from datetime import datetime
from datetime import timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from ._q_base import _JOINERY_I, _WORKSPACE_FILTER


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
    (i.hard_locked_at IS NOT NULL)                   AS hard_locked,
    -- Q438 + Q568: the CUTLIST column is the *cutlist's* number, which several
    -- items share, not the item's own `num`.  Q540 made the two equal for every
    -- migrated item, which is why reading `num` looked right until a cutlist was
    -- actually shared.  NULL while an item has no cutlist, which Q440 permits
    -- indefinitely.
    i.cutlist_id,
    cl.cutlist_no,
    -- Q417 + Q567: the leftmost Tracking reference is the cutlist number for a
    -- Joinery Item and the ISSUED supplier-order number for a related part.
    -- "Issued" is `date_ordered IS NOT NULL` -- the column that records the day
    -- the order went to the supplier -- because no order status means issued
    -- (0002's CHECK has Draft/Pending/Approved/... and no Issued).  A part may
    -- carry several orders, so the most recent issued one wins.
    ord.po_number                                   AS issued_order_no,
    ord.po_id                                       AS issued_order_po_id,
    -- Q425: Tracking's O/BOOK sub-tab shows this row's order state, which is a
    -- different question from Q417's reference column above.  It takes the
    -- latest order in ANY state, because a freshly raised Draft is exactly what
    -- the sub-tab exists to surface; `issued_order_no` stays issued-only.
    obook.po_id                                     AS order_po_id,
    obook.po_number                                 AS order_no,
    obook.status                                    AS order_status,
    obook.vendor_name                               AS order_supplier,
    obook.due_date                                  AS order_due_date,
    -- Tracking 2.0 enrichment (#10)
    i.jid_code,
    i.jid_color,
    i.var_boq,
    i.contractor_id,
    c.full_name                                     AS contractor_name,
    f.code                                          AS factory_code,
    i.tg_solid                                      AS tg_solid,
    i.total_amount,
    i.site_measure_notes,
    i.floor_plan,
    i.rls,
    i.joiery_details,
    i.painting_req                                  AS painting_required,
    i.solid_surface_req                             AS solid_surface_required,
    i.cutlist_printed,
    i.group_id,
    i.item_code,
    i.assembler,
    i.lister,
    (
        SELECT ia.file_blob_id
        FROM item_attachment ia
        WHERE ia.item_id = i.item_id AND ia.kind = 'site_measure'
    )                                               AS site_measure_attachment_id,
    (
        SELECT COUNT(*) FROM item_hardware_lines hl
        WHERE hl.item_id = i.item_id
    )                                               AS hardware_line_count,
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
    availability: str | None = None,
    deleted: bool = False,
) -> list[dict]:
    """Return tracking grid rows for a project, scoped to the caller's workspace.

    `deleted=True` lists the soft-deleted rows instead of the live ones (Tracking's
    Deleted chip); it is the only reader of them besides `restore_item`.

    Filters:
      status    - exact match on items.status
      stage_key - items currently AT that lifecycle stage (due_date set, done_date NULL)
      q         - ILIKE substring on description or code
      availability - 'blocked' for items with ≥1 unallocated hardware line
                     (powers the TO BE ORDERED subtab); anything else ignored.
    """
    params: dict = {
        "pid": project_id,
        "wid": workspace_id,
        "status": status,
        "stage_key": stage_key,
        "q": q,
        "blocked_only": 1 if availability == "blocked" else 0,
        "deleted": deleted,
    }

    # Query 1: items with availability rollup + contractor join
    item_rows = db.execute(
        text(
            f"""
            SELECT {_ITEM_COLS}
            FROM items i
            LEFT JOIN app_user u ON u.id = i.cutlist_owner_id
            LEFT JOIN items parent ON parent.item_id = i.parent_item_id
            LEFT JOIN cutlist cl ON cl.cutlist_id = i.cutlist_id
            LEFT JOIN LATERAL (
                SELECT po.po_id, po.po_number
                  FROM purchase_orders po
                 WHERE po.item_id = i.item_id
                   AND po.date_ordered IS NOT NULL
                 ORDER BY po.date_ordered DESC, po.po_id DESC
                 LIMIT 1
            ) ord ON true
            LEFT JOIN LATERAL (
                SELECT po.po_id, po.po_number, po.status, po.due_date,
                       v.name AS vendor_name
                  FROM purchase_orders po
                  LEFT JOIN vendors v ON v.vendor_id = po.vendor_id
                 WHERE po.item_id = i.item_id
                 ORDER BY po.po_id DESC
                 LIMIT 1
            ) obook ON true
            LEFT JOIN app_user c ON c.id = i.contractor_id
            LEFT JOIN factory f ON f.factory_id = i.factory_id
            WHERE i.project_id = :pid
              AND {_WORKSPACE_FILTER}
              AND i.deleted = :deleted
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
              AND (
                  :blocked_only = 0
                  OR EXISTS (
                      SELECT 1 FROM item_hardware_lines hl
                      WHERE hl.item_id = i.item_id
                        AND NOT EXISTS (
                            SELECT 1 FROM batch_allocations ba
                            WHERE ba.item_hardware_line_id = hl.line_id
                        )
                  )
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
                "hard_locked": bool(r["hard_locked"]),
                # Q558: the list carries both row kinds; the web nests on these.
                "row_type": r["row_type"],
                "parent_item_id": r["parent_item_id"],
                "related_part_type_key": r["related_part_type_key"],
                "cutlist_id": r["cutlist_id"],
                "cutlist_no": r["cutlist_no"],
                "issued_order_no": r["issued_order_no"],
                "issued_order_po_id": r["issued_order_po_id"],
                "order_po_id": r["order_po_id"],
                "order_no": r["order_no"],
                "order_status": r["order_status"],
                "order_supplier": r["order_supplier"],
                "order_due_date": r["order_due_date"],
                "stages": stages_by_item.get(item_id, {}),
                "availability": {
                    "ready": int(r["ready"]),
                    "blocked": int(r["blocked"]),
                },
                # Tracking 2.0 enrichment
                "jid_code": r["jid_code"],
                "jid_color": r["jid_color"],
                "var_boq": r["var_boq"] or "BOQ",
                "contractor_id": r["contractor_id"],
                "contractor_name": r["contractor_name"],
                "factory_code": r["factory_code"],
                "tg_solid": bool(r["tg_solid"]),
                "total_amount": r["total_amount"],
                "site_measure_notes": r["site_measure_notes"],
                "site_measure_attachment_id": r["site_measure_attachment_id"],
                "floor_plan": r["floor_plan"],
                "rls": r["rls"],
                "joiery_details": r["joiery_details"],
                "painting_required": r["painting_required"],
                "solid_surface_required": r["solid_surface_required"],
                "cutlist_printed": r["cutlist_printed"],
                "group_id": r["group_id"],
                "item_code": r["item_code"],
                "assembler": r["assembler"],
                "lister": r["lister"],
                "hardware_line_count": int(r["hardware_line_count"] or 0),
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
              AND {_JOINERY_I}
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
                i.group_id,
                i.area_id,
                i.room_id,
                i.jid_code,
                i.jid_color,
                i.var_boq,
                i.contractor_id,
                c.full_name                 AS contractor_name,
                i.total_amount,
                i.site_measure_notes,
                i.floor_plan,
                i.rls,
                i.joiery_details,
                i.cutlist_printed,
                i.hard_locked_at,
                i.hard_locked_by,
                hl.full_name                AS hard_locked_by_name,
                i.field_versions,
                i.duplicated_from_item_id,
                src.num                     AS duplicated_from_item_number
            FROM items i
            LEFT JOIN app_user u ON u.id = i.cutlist_owner_id
            LEFT JOIN app_user c ON c.id = i.contractor_id
            LEFT JOIN app_user hl ON hl.id = i.hard_locked_by
            LEFT JOIN items src ON src.item_id = i.duplicated_from_item_id
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
                (SELECT count(*) FROM comment c
                  WHERE c.module_id = m.module_id
                    AND c.deleted_at IS NULL) AS comment_count,
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
                "comment_count": mp["comment_count"],
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
        "area_id": row["area_id"],
        "room_id": row["room_id"],
        "jid_code": row["jid_code"],
        "jid_color": row["jid_color"],
        "var_boq": row["var_boq"] or "BOQ",
        "contractor_id": row["contractor_id"],
        "contractor_name": row["contractor_name"],
        "total_amount": row["total_amount"],
        "site_measure_notes": row["site_measure_notes"],
        "floor_plan": row["floor_plan"],
        "rls": row["rls"],
        "joiery_details": row["joiery_details"],
        "cutlist_printed": row["cutlist_printed"],
        "stages": stages,
        "modules": modules,
        "hardware_lines": hardware_lines,
        "edit_log": edit_log,
        "lock_warning": lock_warning,
        "hard_locked_at": row["hard_locked_at"],
        "hard_locked_by": row["hard_locked_by"],
        "hard_locked_by_name": row["hard_locked_by_name"],
        "field_versions": row["field_versions"] or {},
        "duplicated_from_item_id": row["duplicated_from_item_id"],
        "duplicated_from_item_number": row["duplicated_from_item_number"],
    }

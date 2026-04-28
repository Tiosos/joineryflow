"""SQL query functions for the hardware_lines module.

Schema notes:
- project_hardware_catalog has no workspace_id column.
  Workspace scoping goes via project_id -> projects.pm_id -> app_user.workspace_id,
  mirroring the pattern in apps/api/app/items/queries.py.
- project_hardware_catalog has no qty column. qty is returned as 1.0 (catalog-level
  default; per-line qty lives on item_hardware_lines, not the catalog itself).
- equipment_hire PK is hire_id (not material_id); handled in the UNION ALL CTE.
- custom_made has vendor (not supplier); exposed as NULL for consistency.
- board_materials has both a legacy supplier column and the new unit_cost column.

Schema drift (T18):
- project_hardware_catalog_log has NO catalog_id column. Log rows store
  (project_id, material_type, material_id) directly — retrieved from catalog row.
- project_hardware_catalog_log.changed_by is bigint FK to app_user (not varchar).
- Log action CHECK: 'ADD' | 'REMOVE' | 'REACTIVATE' (uppercase).
- equipment_hire has its own project_id but workspace scoping is via workspace_id column.
  source row is validated by workspace_id match, not by project_id chain.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log, write_edit_log_many
from .schemas import AddCatalogIn, CreateHardwareLineIn, PatchHardwareLineIn

# Maps source_table name -> (material_type DB value, pk column name)
_SOURCE_TABLE_MAP: dict[str, tuple[str, str]] = {
    "board_materials":    ("BOARD",     "material_id"),
    "hardware_materials": ("HARDWARE",  "material_id"),
    "custom_made":        ("CUSTOM",    "material_id"),
    "benchtop_materials": ("BENCHTOP",  "material_id"),
    "appliances":         ("APPLIANCE", "material_id"),
    "equipment_hire":     ("HIRE",      "hire_id"),
}

# Maps material_type -> source_table name (reverse of above)
_MTYPE_TO_TABLE: dict[str, str] = {v[0]: k for k, v in _SOURCE_TABLE_MAP.items()}

# Workspace isolation: project_hardware_catalog -> projects -> pm_id -> app_user.workspace_id
_WORKSPACE_FILTER = """
    EXISTS (
        SELECT 1
        FROM projects p
        JOIN app_user au ON au.id = p.pm_id
        WHERE p.project_id = phc.project_id
          AND au.workspace_id = :wid
    )
"""


def list_catalog(
    db: Session,
    *,
    workspace_id: int,
    project_id: int,
) -> list[dict]:
    """List rows in a project's hardware catalog with source-table descriptors.

    Resolves project_hardware_catalog.material_type + material_id through a
    6-way UNION ALL CTE across the six source-table primary keys.

    Returns an empty list when the project has no catalog rows.
    """
    rows = db.execute(
        text(
            """
            WITH src AS (
                SELECT
                    'BOARD'         AS mat_type,
                    material_id     AS sid,
                    sku,
                    description,
                    supplier,
                    unit_cost
                FROM board_materials

                UNION ALL

                SELECT
                    'HARDWARE',
                    material_id,
                    sku,
                    description,
                    supplier,
                    unit_cost
                FROM hardware_materials

                UNION ALL

                SELECT
                    'CUSTOM',
                    material_id,
                    sku,
                    description,
                    NULL::text      AS supplier,
                    unit_cost
                FROM custom_made

                UNION ALL

                SELECT
                    'BENCHTOP',
                    material_id,
                    sku,
                    description,
                    supplier,
                    unit_cost
                FROM benchtop_materials

                UNION ALL

                SELECT
                    'APPLIANCE',
                    material_id,
                    sku,
                    description,
                    supplier,
                    unit_cost
                FROM appliances

                UNION ALL

                SELECT
                    'HIRE',
                    hire_id,
                    sku,
                    description,
                    supplier,
                    unit_cost
                FROM equipment_hire
            )
            SELECT
                phc.catalog_id,
                CASE phc.material_type
                    WHEN 'BOARD'     THEN 'board_materials'
                    WHEN 'HARDWARE'  THEN 'hardware_materials'
                    WHEN 'CUSTOM'    THEN 'custom_made'
                    WHEN 'BENCHTOP'  THEN 'benchtop_materials'
                    WHEN 'APPLIANCE' THEN 'appliances'
                    WHEN 'HIRE'      THEN 'equipment_hire'
                END                             AS source_table,
                phc.material_id                 AS source_id,
                src.sku,
                src.description                 AS name,
                src.supplier,
                src.unit_cost,
                1.0::float                      AS qty
            FROM project_hardware_catalog phc
            LEFT JOIN src
                   ON src.mat_type = phc.material_type
                  AND src.sid      = phc.material_id
            WHERE phc.project_id = :pid
              AND phc.is_active IS TRUE
              AND """ + _WORKSPACE_FILTER + """
            ORDER BY phc.material_type, src.description
            """
        ),
        {"pid": project_id, "wid": workspace_id},
    ).mappings().all()

    return [
        {
            "catalog_id": r["catalog_id"],
            "source_table": r["source_table"],
            "source_id": r["source_id"],
            "sku": r["sku"],
            "name": r["name"] or "",
            "supplier": r["supplier"],
            "unit_cost": float(r["unit_cost"]) if r["unit_cost"] is not None else None,
            "qty": r["qty"],
        }
        for r in rows
    ]


# ── T18 mutation helpers ──────────────────────────────────────────────────────


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    """Return True if project is owned by a pm in the given workspace."""
    row = db.execute(
        text(
            """
            SELECT 1 FROM projects p
            JOIN app_user au ON au.id = p.pm_id
            WHERE p.project_id = :pid AND au.workspace_id = :wid
            """
        ),
        {"pid": project_id, "wid": workspace_id},
    ).first()
    return row is not None


def _catalog_row(db: Session, *, catalog_id: int, workspace_id: int) -> dict | None:
    """Return (catalog_id, project_id, material_type, material_id) or None if not visible."""
    row = db.execute(
        text(
            """
            SELECT phc.catalog_id, phc.project_id, phc.material_type, phc.material_id
            FROM project_hardware_catalog phc
            WHERE phc.catalog_id = :cid
              AND EXISTS (
                  SELECT 1 FROM projects p
                  JOIN app_user au ON au.id = p.pm_id
                  WHERE p.project_id = phc.project_id
                    AND au.workspace_id = :wid
              )
            """
        ),
        {"cid": catalog_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def _item_project_in_workspace(
    db: Session, *, item_id: int, workspace_id: int
) -> int | None:
    """Return project_id if item belongs to a workspace project, else None."""
    row = db.execute(
        text(
            """
            SELECT i.project_id
            FROM items i
            WHERE i.item_id = :iid
              AND EXISTS (
                  SELECT 1 FROM projects p
                  JOIN app_user au ON au.id = p.pm_id
                  WHERE p.project_id = i.project_id
                    AND au.workspace_id = :wid
              )
            """
        ),
        {"iid": item_id, "wid": workspace_id},
    ).scalar()
    return row


def _line_item_in_workspace(
    db: Session, *, line_id: int, workspace_id: int
) -> dict | None:
    """Return {line_id, item_id, qty, note, catalog_id} if line is in workspace, else None."""
    row = db.execute(
        text(
            """
            SELECT ihl.line_id, ihl.item_id, ihl.qty, ihl.note, ihl.catalog_id
            FROM item_hardware_lines ihl
            JOIN items i ON i.item_id = ihl.item_id
            WHERE ihl.line_id = :lid
              AND EXISTS (
                  SELECT 1 FROM projects p
                  JOIN app_user au ON au.id = p.pm_id
                  WHERE p.project_id = i.project_id
                    AND au.workspace_id = :wid
              )
            """
        ),
        {"lid": line_id, "wid": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def add_to_catalog(
    db: Session,
    *,
    project_id: int,
    workspace_id: int,
    payload: AddCatalogIn,
    actor_id: int,
) -> int | None:
    """INSERT project_hardware_catalog + log row + audit.

    Returns new catalog_id, or None if project not in workspace or source row
    not found in caller's workspace.

    Log drift note: project_hardware_catalog_log has no catalog_id column;
    log stores (project_id, material_type, material_id) directly.
    """
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None

    material_type, pk_col = _SOURCE_TABLE_MAP[payload.source_table]

    # Validate source row exists in caller's workspace
    src_row = db.execute(
        text(
            f"SELECT {pk_col} FROM {payload.source_table} "
            f"WHERE {pk_col} = :sid AND workspace_id = :wid"
        ),
        {"sid": payload.source_id, "wid": workspace_id},
    ).first()
    if src_row is None:
        return None

    catalog_id = db.execute(
        text(
            """
            INSERT INTO project_hardware_catalog
                (project_id, material_type, material_id, added_by)
            VALUES (:pid, :mtype, :mid, :by)
            RETURNING catalog_id
            """
        ),
        {
            "pid": project_id,
            "mtype": material_type,
            "mid": payload.source_id,
            "by": actor_id,
        },
    ).scalar()
    db.flush()

    # Log row: project_hardware_catalog_log stores (project_id, material_type, material_id)
    db.execute(
        text(
            """
            INSERT INTO project_hardware_catalog_log
                (project_id, material_type, material_id, action, changed_by)
            VALUES (:pid, :mtype, :mid, 'ADD', :by)
            """
        ),
        {"pid": project_id, "mtype": material_type, "mid": payload.source_id, "by": actor_id},
    )
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="hardware_catalog.add",
        target=str(catalog_id),
        payload={
            "project_id": project_id,
            "material_type": material_type,
            "material_id": payload.source_id,
        },
    )
    return catalog_id


def remove_from_catalog(
    db: Session,
    *,
    catalog_id: int,
    workspace_id: int,
    actor_id: int,
) -> str:
    """Returns 'OK', 'NOT_FOUND', or 'IN_USE'.

    IN_USE when any item_hardware_lines row references this catalog entry.
    Log drift note: project_hardware_catalog_log has no catalog_id column;
    log stores (project_id, material_type, material_id) from the catalog row.
    """
    cat = _catalog_row(db, catalog_id=catalog_id, workspace_id=workspace_id)
    if cat is None:
        return "NOT_FOUND"

    in_use = db.execute(
        text(
            "SELECT 1 FROM item_hardware_lines WHERE catalog_id = :cid LIMIT 1"
        ),
        {"cid": catalog_id},
    ).first()
    if in_use:
        return "IN_USE"

    # Write log before delete
    db.execute(
        text(
            """
            INSERT INTO project_hardware_catalog_log
                (project_id, material_type, material_id, action, changed_by)
            VALUES (:pid, :mtype, :mid, 'REMOVE', :by)
            """
        ),
        {
            "pid": cat["project_id"],
            "mtype": cat["material_type"],
            "mid": cat["material_id"],
            "by": actor_id,
        },
    )
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="hardware_catalog.remove",
        target=str(catalog_id),
        payload={
            "project_id": cat["project_id"],
            "material_type": cat["material_type"],
            "material_id": cat["material_id"],
        },
    )

    db.execute(
        text("DELETE FROM project_hardware_catalog WHERE catalog_id = :cid"),
        {"cid": catalog_id},
    )
    db.flush()
    return "OK"


def get_hardware_line(
    db: Session, *, line_id: int, workspace_id: int
) -> dict | None:
    """Return HardwareLineOut-shaped dict for a single line, or None if not visible."""
    row = db.execute(
        text(
            """
            SELECT
                ihl.line_id                 AS id,
                ihl.catalog_id,
                src.description             AS catalog_description,
                src.supplier                AS catalog_supplier,
                phc.material_type           AS catalog_source_table,
                ihl.qty,
                ihl.note
            FROM item_hardware_lines ihl
            JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
            JOIN items i ON i.item_id = ihl.item_id
            LEFT JOIN LATERAL (
                SELECT description, supplier FROM board_materials
                WHERE material_id = phc.material_id AND phc.material_type = 'BOARD'
                UNION ALL
                SELECT description, supplier FROM hardware_materials
                WHERE material_id = phc.material_id AND phc.material_type = 'HARDWARE'
                UNION ALL
                SELECT description, NULL::text FROM custom_made
                WHERE material_id = phc.material_id AND phc.material_type = 'CUSTOM'
                UNION ALL
                SELECT description, supplier FROM benchtop_materials
                WHERE material_id = phc.material_id AND phc.material_type = 'BENCHTOP'
                UNION ALL
                SELECT description, supplier FROM appliances
                WHERE material_id = phc.material_id AND phc.material_type = 'APPLIANCE'
                UNION ALL
                SELECT description, supplier FROM equipment_hire
                WHERE hire_id = phc.material_id AND phc.material_type = 'HIRE'
            ) src ON true
            WHERE ihl.line_id = :lid
              AND EXISTS (
                  SELECT 1 FROM projects p
                  JOIN app_user au ON au.id = p.pm_id
                  WHERE p.project_id = i.project_id
                    AND au.workspace_id = :wid
              )
            """
        ),
        {"lid": line_id, "wid": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    return {
        "id": row["id"],
        "catalog_id": row["catalog_id"],
        "catalog_description": row["catalog_description"],
        "catalog_supplier": row["catalog_supplier"],
        "catalog_source_table": row["catalog_source_table"],
        "qty": row["qty"],
        "note": row["note"],
    }


def create_hardware_line(
    db: Session,
    *,
    item_id: int,
    workspace_id: int,
    payload: CreateHardwareLineIn,
    actor_id: int,
) -> int | None:
    """Returns new line_id, or None if item or catalog_id not visible / catalog not same project."""
    project_id = _item_project_in_workspace(db, item_id=item_id, workspace_id=workspace_id)
    if project_id is None:
        return None

    # Validate catalog_id belongs to the SAME project as the item
    cat = db.execute(
        text(
            """
            SELECT catalog_id FROM project_hardware_catalog
            WHERE catalog_id = :cid AND project_id = :pid AND is_active IS TRUE
            """
        ),
        {"cid": payload.catalog_id, "pid": project_id},
    ).first()
    if cat is None:
        return None

    line_id = db.execute(
        text(
            """
            INSERT INTO item_hardware_lines(item_id, catalog_id, qty, note)
            VALUES (:iid, :cid, :qty, :note)
            RETURNING line_id
            """
        ),
        {
            "iid": item_id,
            "cid": payload.catalog_id,
            "qty": payload.qty,
            "note": payload.note,
        },
    ).scalar()
    db.flush()

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="hardware_line.create",
        target=str(line_id),
        payload={"item_id": item_id, "catalog_id": payload.catalog_id, "qty": payload.qty},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_create_hardware_line",
        old_value=None,
        new_value=str(payload.catalog_id),
    )
    return line_id


def patch_hardware_line(
    db: Session,
    *,
    line_id: int,
    workspace_id: int,
    payload: PatchHardwareLineIn,
    actor_id: int,
) -> dict | None:
    """Apply partial update to a hardware line.

    Returns HardwareLineOut-shaped dict or None if not found.
    Writes one item_edit_log row per changed field.
    """
    info = _line_item_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if info is None:
        return None

    item_id = info["item_id"]
    changes: list[tuple[str, str | None, str | None]] = []
    updates: dict = {}

    if payload.qty is not None and payload.qty != info["qty"]:
        updates["qty"] = payload.qty
        changes.append(("hardware_lines.qty", str(info["qty"]), str(payload.qty)))

    if payload.note is not None and payload.note != info["note"]:
        updates["note"] = payload.note
        changes.append(("hardware_lines.note", info["note"], payload.note))

    if updates:
        set_clauses = ", ".join(f"{col} = :{col}" for col in updates)
        db.execute(
            text(
                f"UPDATE item_hardware_lines SET {set_clauses}, updated_at = now() "
                f"WHERE line_id = :lid"
            ),
            {"lid": line_id, **updates},
        )
        db.flush()

    if changes:
        write_edit_log_many(db, item_id=item_id, actor_id=actor_id, changes=changes)

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="hardware_line.patch",
        target=str(line_id),
        payload={c[0]: c[2] for c in changes},
    )
    return get_hardware_line(db, line_id=line_id, workspace_id=workspace_id)


def delete_hardware_line(
    db: Session,
    *,
    line_id: int,
    workspace_id: int,
    actor_id: int,
) -> str:
    """Returns 'OK' or 'NOT_FOUND'.

    Writes audit + edit_log BEFORE delete. batch_allocations rows are
    handled by ON DELETE CASCADE on the FK.
    """
    info = _line_item_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if info is None:
        return "NOT_FOUND"

    item_id = info["item_id"]

    write_audit(
        db,
        workspace_id=workspace_id,
        actor_id=actor_id,
        event="hardware_line.delete",
        target=str(line_id),
        payload={"item_id": item_id, "catalog_id": info["catalog_id"]},
    )
    write_edit_log(
        db,
        item_id=item_id,
        actor_id=actor_id,
        field="_delete_hardware_line",
        old_value=str(info["catalog_id"]),
        new_value=None,
    )

    db.execute(
        text("DELETE FROM item_hardware_lines WHERE line_id = :lid"),
        {"lid": line_id},
    )
    db.flush()
    return "OK"


_ALLOWED_SOURCE_TABLES = frozenset(_SOURCE_TABLE_MAP.keys())


def list_source_catalog(
    db: Session,
    *,
    table: str,
    workspace_id: int,
) -> list[dict]:
    """List rows from one of the 6 source tables for the caller's workspace.

    table must be in _ALLOWED_SOURCE_TABLES (validated by route layer).
    equipment_hire uses hire_id as PK; all others use material_id.
    """
    pk_col = "hire_id" if table == "equipment_hire" else "material_id"
    # custom_made uses `vendor` instead of `supplier`; expose as NULL for API consistency.
    supplier_expr = "NULL::text AS supplier" if table == "custom_made" else "supplier"
    rows = db.execute(
        text(
            f"""
            SELECT {pk_col} AS source_id, sku, description, {supplier_expr}, unit_cost
            FROM {table}
            WHERE workspace_id = :wid
            ORDER BY description
            """
        ),
        {"wid": workspace_id},
    ).mappings().all()

    return [
        {
            "source_id": r["source_id"],
            "sku": r["sku"],
            "description": r["description"] or "",
            "supplier": r["supplier"],
            "unit_cost": float(r["unit_cost"]) if r["unit_cost"] is not None else None,
        }
        for r in rows
    ]

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
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

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

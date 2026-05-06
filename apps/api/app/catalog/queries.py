"""Catalog CRUD with workspace isolation + audit hooks.

REGISTRY-driven: one dict entry per material type. The five enrichment columns
(synonyms, default_supplier, default_lead_time_days, archived_at, archived_by)
are present on every table per migration 0017. Per-table legacy NOT NULL UNIQUE
columns (code, internal_ref, slab_id, model_number, contract_ref) are honoured
via insert_cols.

Routes own the transaction boundary; queries flush only.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

ENRICHMENT_SELECT = (
    "synonyms, default_supplier, default_lead_time_days, archived_at, archived_by"
)
ENRICHMENT_INSERT = (
    "synonyms", "default_supplier", "default_lead_time_days",
)

REGISTRY: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "board": (
        "board_materials",
        "material_id",
        f"material_id, code, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("code", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "hardware": (
        "hardware_materials",
        "material_id",
        f"material_id, sku, description, workspace_id, {ENRICHMENT_SELECT}",
        ("sku", "description", *ENRICHMENT_INSERT),
    ),
    "custom_made": (
        "custom_made",
        "material_id",
        f"material_id, internal_ref, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("internal_ref", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "benchtop": (
        "benchtop_materials",
        "material_id",
        f"material_id, slab_id, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("slab_id", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "appliance": (
        "appliances",
        "material_id",
        f"material_id, model_number, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("model_number", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "hire": (
        "equipment_hire",
        "hire_id",
        f"hire_id, contract_ref, project_id, description, sku, workspace_id, "
        f"{ENRICHMENT_SELECT}",
        ("contract_ref", "project_id", "description", "sku", *ENRICHMENT_INSERT),
    ),
}


def list_catalog(
    db: Session,
    *,
    type_: str,
    workspace_id: int,
    q: str | None = None,
    supplier: str | None = None,
    archived: bool = False,
) -> list[dict]:
    table, id_col, cols, _ = REGISTRY[type_]
    where = ["workspace_id = :w"]
    params: dict = {"w": workspace_id}
    if not archived:
        where.append("archived_at IS NULL")
    if q:
        where.append("(description ILIKE :q OR sku ILIKE :q)")
        params["q"] = f"%{q}%"
    if supplier:
        where.append("default_supplier = :sup")
        params["sup"] = supplier
    sql = (
        f"SELECT {cols} FROM {table} "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {id_col} DESC"
    )
    return [dict(r) | {"type": type_} for r in db.execute(text(sql), params).mappings()]


def get_catalog_row(
    db: Session, *, type_: str, mid: int, workspace_id: int
) -> dict | None:
    table, id_col, cols, _ = REGISTRY[type_]
    sql = text(
        f"SELECT {cols} FROM {table} "
        f"WHERE {id_col} = :id AND workspace_id = :w"
    )
    r = db.execute(sql, {"id": mid, "w": workspace_id}).mappings().first()
    return (dict(r) | {"type": type_}) if r else None


def create_catalog_row(
    db: Session, *, type_: str, fields: dict[str, Any], workspace_id: int
) -> int:
    table, id_col, _, insert_cols = REGISTRY[type_]
    use = {k: v for k, v in fields.items() if k in insert_cols}
    if not use:
        raise ValueError("no insertable fields supplied")
    use["workspace_id"] = workspace_id
    cols = list(use.keys())
    sql = text(
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)}) "
        f"RETURNING {id_col}"
    )
    return db.execute(sql, use).scalar()


def patch_catalog_row(
    db: Session, *, type_: str, mid: int, fields: dict, workspace_id: int
) -> int | None:
    if not fields:
        return mid
    table, id_col, _, insert_cols = REGISTRY[type_]
    use = {k: v for k, v in fields.items() if k in insert_cols}
    if not use:
        return mid
    sets = ", ".join(f"{c} = :{c}" for c in use.keys())
    sql = text(
        f"UPDATE {table} SET {sets} "
        f"WHERE {id_col} = :id AND workspace_id = :w "
        f"RETURNING {id_col}"
    )
    return db.execute(sql, {**use, "id": mid, "w": workspace_id}).scalar()


def archive_catalog_row(
    db: Session, *, type_: str, mid: int, actor_id: int, workspace_id: int
) -> int | None:
    table, id_col, _, _ = REGISTRY[type_]
    sql = text(
        f"UPDATE {table} SET archived_at = now(), archived_by = :a "
        f"WHERE {id_col} = :id AND workspace_id = :w AND archived_at IS NULL "
        f"RETURNING {id_col}"
    )
    return db.execute(sql, {"a": actor_id, "id": mid, "w": workspace_id}).scalar()


def list_cv_mappings(
    db: Session, *, workspace_id: int, q: str | None = None
) -> dict:
    where = ["m.workspace_id = :w"]
    params: dict = {"w": workspace_id}
    if q:
        where.append("(m.cv_code ILIKE :q OR m.notes ILIKE :q)")
        params["q"] = f"%{q}%"
    rows = db.execute(text(f"""
        SELECT m.cv_material_mapping_id, m.workspace_id, m.cv_code,
               m.target_material_table, m.target_material_id,
               m.notes, m.created_by, m.created_at, m.updated_at,
               CASE m.target_material_table
                 WHEN 'board_materials'    THEN (SELECT description FROM board_materials    WHERE material_id = m.target_material_id)
                 WHEN 'hardware_materials' THEN (SELECT description FROM hardware_materials WHERE material_id = m.target_material_id)
                 WHEN 'custom_made'        THEN (SELECT description FROM custom_made        WHERE material_id = m.target_material_id)
                 WHEN 'benchtop_materials' THEN (SELECT description FROM benchtop_materials WHERE material_id = m.target_material_id)
                 WHEN 'appliances'         THEN (SELECT description FROM appliances         WHERE material_id = m.target_material_id)
                 WHEN 'equipment_hire'     THEN (SELECT description FROM equipment_hire     WHERE hire_id     = m.target_material_id)
               END AS target_description
          FROM cv_material_mapping m
         WHERE {' AND '.join(where)}
         ORDER BY m.cv_material_mapping_id DESC
    """), params).mappings().all()
    return {"rows": [dict(r) for r in rows], "total": len(rows)}


def get_cv_mapping(db: Session, *, mid: int, workspace_id: int) -> dict | None:
    r = db.execute(text("""
        SELECT cv_material_mapping_id, workspace_id, cv_code,
               target_material_table, target_material_id,
               notes, created_by, created_at, updated_at
          FROM cv_material_mapping
         WHERE cv_material_mapping_id = :id AND workspace_id = :w
    """), {"id": mid, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def create_cv_mapping(
    db: Session, *, payload: dict, actor_id: int, workspace_id: int
) -> int:
    sql = text("""
        INSERT INTO cv_material_mapping
          (workspace_id, cv_code, target_material_table, target_material_id,
           notes, created_by)
        VALUES (:w, :code, :tbl, :tid, :notes, :a)
        RETURNING cv_material_mapping_id
    """)
    return db.execute(sql, {
        "w": workspace_id,
        "code": payload["cv_code"],
        "tbl":  payload["target_material_table"],
        "tid":  payload["target_material_id"],
        "notes": payload.get("notes"),
        "a": actor_id,
    }).scalar()


def patch_cv_mapping(
    db: Session, *, mid: int, fields: dict, workspace_id: int
) -> int | None:
    use = {k: v for k, v in fields.items() if k in
           ("cv_code", "target_material_table", "target_material_id", "notes")}
    if not use:
        return mid
    sets_parts = [f"{c} = :{c}" for c in use]
    sets_parts.append("updated_at = now()")
    sql = text(
        f"UPDATE cv_material_mapping SET {', '.join(sets_parts)} "
        f"WHERE cv_material_mapping_id = :id AND workspace_id = :w "
        f"RETURNING cv_material_mapping_id"
    )
    return db.execute(sql, {**use, "id": mid, "w": workspace_id}).scalar()


def delete_cv_mapping(db: Session, *, mid: int, workspace_id: int) -> int | None:
    return db.execute(text(
        "DELETE FROM cv_material_mapping "
        "WHERE cv_material_mapping_id = :id AND workspace_id = :w "
        "RETURNING cv_material_mapping_id"
    ), {"id": mid, "w": workspace_id}).scalar()

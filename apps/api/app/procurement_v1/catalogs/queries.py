"""Catalog CRUD across the 6 material catalog tables.

Each catalog has its own canonical column shape per migrations 0001 + 0007.
A small REGISTRY maps the URL `type_` to `(table, id_col, select_cols, insertable_cols)`.
We accept `dict[str, Any]` payloads and only allow the columns listed in
`insertable_cols` to make it into INSERT/UPDATE statements — Postgres rejects
the rest implicitly. Writes are gated by `(orderbook, write)` and audited.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

# (table, id_col, select_cols_csv, insertable_cols_tuple)
#
# Column names per migrations 0001 (initial 6-table catalog) + 0007 (sku
# hybrid). Each table has `description` (readable name) and `sku` except
# `hardware_materials`, where `sku` is the legacy NOT NULL UNIQUE column.
# `equipment_hire` is project-scoped (`project_id` NOT NULL FK) and uses
# `hire_id` as primary key.
REGISTRY: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "board": (
        "board_materials",
        "material_id",
        "material_id, code, description, sku",
        ("code", "description", "sku"),
    ),
    "hardware": (
        "hardware_materials",
        "material_id",
        "material_id, sku, description",
        ("sku", "description"),
    ),
    "custom_made": (
        "custom_made",
        "material_id",
        "material_id, internal_ref, description, sku",
        ("internal_ref", "description", "sku"),
    ),
    "benchtop": (
        "benchtop_materials",
        "material_id",
        "material_id, slab_id, description, sku",
        ("slab_id", "description", "sku"),
    ),
    "appliance": (
        "appliances",
        "material_id",
        "material_id, model_number, description, sku",
        ("model_number", "description", "sku"),
    ),
    "hire": (
        "equipment_hire",
        "hire_id",
        "hire_id, contract_ref, project_id, description, sku",
        ("contract_ref", "project_id", "description", "sku"),
    ),
}


def list_catalog(db: Session, *, type_: str) -> list[dict]:
    table, _, cols, _ = REGISTRY[type_]
    sql = text(f"SELECT {cols} FROM {table} ORDER BY 1")
    return [dict(r) | {"type": type_} for r in db.execute(sql).mappings()]


def create_catalog_row(db: Session, *, type_: str, fields: dict) -> int:
    table, id_col, _, insert_cols = REGISTRY[type_]
    cols = [c for c in insert_cols if c in fields]
    if not cols:
        raise ValueError("no insertable fields supplied")
    sql = text(
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)}) RETURNING {id_col}"
    )
    return db.execute(sql, fields).scalar()


def get_catalog_row(db: Session, *, type_: str, mid: int) -> dict | None:
    table, id_col, cols, _ = REGISTRY[type_]
    sql = text(f"SELECT {cols} FROM {table} WHERE {id_col} = :id")
    r = db.execute(sql, {"id": mid}).mappings().first()
    return (dict(r) | {"type": type_}) if r else None


def patch_catalog_row(db: Session, *, type_: str, mid: int, fields: dict) -> int | None:
    if not fields:
        return mid
    table, id_col, _, insert_cols = REGISTRY[type_]
    use = {k: v for k, v in fields.items() if k in insert_cols}
    if not use:
        return mid
    sets = ", ".join(f"{c} = :{c}" for c in use.keys())
    sql = text(
        f"UPDATE {table} SET {sets} WHERE {id_col} = :id RETURNING {id_col}"
    )
    return db.execute(sql, {**use, "id": mid}).scalar()


def delete_catalog_row(db: Session, *, type_: str, mid: int) -> int | None:
    table, id_col, _, _ = REGISTRY[type_]
    return db.execute(
        text(f"DELETE FROM {table} WHERE {id_col} = :id RETURNING {id_col}"),
        {"id": mid},
    ).scalar()

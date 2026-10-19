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
    "synonyms, default_supplier, default_lead_time_days, unit_cost, product_type, archived_at, archived_by"
)
ENRICHMENT_INSERT = (
    "synonyms", "default_supplier", "default_lead_time_days", "unit_cost", "product_type",
    # The supplier link (`0029`): settable at create as well as on PATCH.
    "default_supplier_id",
)


def _supplier_link_cols(table: str) -> str:
    """The FK and the linked supplier's name, for a row of `table`.

    The name is scoped to the row's own workspace, so a link written some other
    way across workspaces (the column is a plain FK) can never surface another
    workspace's supplier name.
    """
    return (
        "default_supplier_id, "
        f"(SELECT v.name FROM vendors v WHERE v.vendor_id = {table}.default_supplier_id"
        f" AND v.workspace_id = {table}.workspace_id) AS default_supplier_name"
    )


def supplier_in_workspace(db: Session, *, vendor_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM vendors WHERE vendor_id = :v AND workspace_id = :w"),
        {"v": vendor_id, "w": workspace_id},
    ).first() is not None


def unknown_supplier_detail(supplier_id: int) -> dict:
    """The 422 body for a supplier that is unknown or in another workspace."""
    return {
        "code": "UNKNOWN_SUPPLIER", "supplier_id": supplier_id,
        "message": "supplier not found in this workspace",
    }


def supplier_ids_by_name(db: Session, *, workspace_id: int) -> dict[str, int | None]:
    """Lower-cased supplier name -> vendor_id, for matching a free-text name.

    The same exact, case-insensitive rule the seed and migration `0029` used. A
    name two suppliers share maps to None: ambiguous, so never linked by guess.
    """
    out: dict[str, int | None] = {}
    for vid, name in db.execute(
        text("SELECT vendor_id, name FROM vendors WHERE workspace_id = :w"),
        {"w": workspace_id},
    ).all():
        key = (name or "").strip().lower()
        if not key:
            continue
        out[key] = None if key in out else vid
    return out

# Board's own fields (`0068`): the old Orders screen's board attributes. All plain text.
# The sheet size and thickness (`sheet_len_mm`, `sheet_wid_mm` integers, `thickness_mm` numeric(6,2)) are columns since
# `0001`; they are shown and edited from the catalog now, no migration. All nullable.
BOARD_TEXT_FIELDS = ("colour", "substrate", "finish", "sided", "grain", "rating", "hmr", "um", "product_website")
BOARD_NUMBER_FIELDS = ("sheet_len_mm", "sheet_wid_mm", "thickness_mm")
BOARD_FIELDS_TUPLE = (*BOARD_TEXT_FIELDS, *BOARD_NUMBER_FIELDS)
BOARD_FIELDS = ", ".join(BOARD_FIELDS_TUPLE)
# Edging's own fields (`0069`). `edge_type` is the old screen's "Type" (not `product_type`, the tab).
EDGING_TEXT_FIELDS = ("colour", "edge_type", "um", "product_website")
EDGING_NUMBER_FIELDS = ("roll_length_m", "edge_width_mm", "edge_thickness_mm")
EDGING_FIELDS_TUPLE = (*EDGING_TEXT_FIELDS, *EDGING_NUMBER_FIELDS, "glued")
EDGING_FIELDS = ", ".join(EDGING_FIELDS_TUPLE)
# Glass's own fields (`0070`). Length, width, thickness in mm; glass type and power point are free text.
GLASS_TEXT_FIELDS = ("colour", "edge_finish", "glass_type", "power_point", "um", "product_website")
GLASS_NUMBER_FIELDS = ("length_mm", "width_mm", "thickness_mm")
GLASS_FIELDS_TUPLE = (*GLASS_TEXT_FIELDS, *GLASS_NUMBER_FIELDS, "shaped")
GLASS_FIELDS = ", ".join(GLASS_FIELDS_TUPLE)
# Solid Timber's own fields (`0074`). Colour, finish, grain and rating are free text; sizes in mm.
TIMBER_TEXT_FIELDS = ("colour", "finish", "grain", "rating", "um", "product_website")
TIMBER_NUMBER_FIELDS = ("thickness_mm", "width_mm", "length_mm")
TIMBER_FIELDS_TUPLE = (*TIMBER_TEXT_FIELDS, *TIMBER_NUMBER_FIELDS)
TIMBER_FIELDS = ", ".join(TIMBER_FIELDS_TUPLE)
# Laminate Benchtop's own fields (`0071`, on `benchtop_materials`). `thickness_mm` already existed; the bench
# size is `bench_length_mm` x `bench_width_mm` (the slab_* columns are the supplier's slab).
BENCHTOP_TEXT_FIELDS = ("colour", "underside", "edge_details", "laminate_supplier", "laminate_code", "finish", "um",
                        "product_website")
BENCHTOP_NUMBER_FIELDS = ("bench_length_mm", "bench_width_mm", "thickness_mm")
BENCHTOP_INT_FIELDS = ("pieces", "joins", "cable_entry")
BENCHTOP_FIELDS_TUPLE = (*BENCHTOP_TEXT_FIELDS, *BENCHTOP_NUMBER_FIELDS, *BENCHTOP_INT_FIELDS, "shaped")
BENCHTOP_FIELDS = ", ".join(BENCHTOP_FIELDS_TUPLE)
# Hardware's own fields (`0072`, on `hardware_materials`): `brand` and `hardware_type` were already columns.
HARDWARE_FIELDS_TUPLE = ("brand", "hardware_type", "um", "product_website")
HARDWARE_FIELDS = ", ".join(HARDWARE_FIELDS_TUPLE)
# Custom's own fields (`0073`, on `custom_made`): the same three Hardware got.
CUSTOM_FIELDS_TUPLE = ("um", "product_website")
CUSTOM_FIELDS = ", ".join(CUSTOM_FIELDS_TUPLE)
# Equipment Hire's own fields (`0076`, on `equipment_hire`): the same three again.
HIRE_FIELDS_TUPLE = ("um", "product_website")
HIRE_FIELDS = ", ".join(HIRE_FIELDS_TUPLE)
# Appliance's own fields (`0077`, on `appliances`): the same three again.
APPLIANCE_FIELDS_TUPLE = ("um", "product_website")
APPLIANCE_FIELDS = ", ".join(APPLIANCE_FIELDS_TUPLE)
# Nullable fields a PATCH `null` clears (`glued` is NOT NULL: a null is dropped like any other).
CLEARABLE_TYPE_FIELDS = (*BOARD_TEXT_FIELDS, *BOARD_NUMBER_FIELDS, *EDGING_TEXT_FIELDS, *EDGING_NUMBER_FIELDS,
                         *GLASS_TEXT_FIELDS, *GLASS_NUMBER_FIELDS, *TIMBER_TEXT_FIELDS, *TIMBER_NUMBER_FIELDS,
                         *BENCHTOP_TEXT_FIELDS, *BENCHTOP_NUMBER_FIELDS,
                         *BENCHTOP_INT_FIELDS, *HARDWARE_FIELDS_TUPLE, *CUSTOM_FIELDS_TUPLE,
                         *HIRE_FIELDS_TUPLE, *APPLIANCE_FIELDS_TUPLE)
# Tables that keep one picture per row (`image_blob`).
IMAGE_TABLES = {"board": "board_materials", "edging": "edging_materials", "glass": "glass_materials",
                "timber": "timber_materials", "benchtop": "benchtop_materials", "hardware": "hardware_materials",
                "custom_made": "custom_made", "hire": "equipment_hire", "appliance": "appliances"}

REGISTRY: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "board": (
        "board_materials",
        "material_id",
        f"material_id, code, description, sku, grain_locked, workspace_id, "
        f"{BOARD_FIELDS}, (image_blob IS NOT NULL) AS has_image, {ENRICHMENT_SELECT}",
        ("code", "description", "sku", "grain_locked", *BOARD_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "glass": (
        "glass_materials",
        "material_id",
        f"material_id, sku, description, workspace_id, {GLASS_FIELDS}, (image_blob IS NOT NULL) AS has_image, "
        f"{ENRICHMENT_SELECT}",
        ("sku", "description", *GLASS_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "timber": (
        "timber_materials",
        "material_id",
        f"material_id, sku, description, workspace_id, {TIMBER_FIELDS}, (image_blob IS NOT NULL) AS has_image, "
        f"{ENRICHMENT_SELECT}",
        ("sku", "description", *TIMBER_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "hardware": (
        "hardware_materials",
        "material_id",
        f"material_id, sku, description, workspace_id, {HARDWARE_FIELDS}, (image_blob IS NOT NULL) AS has_image, "
        f"{ENRICHMENT_SELECT}",
        ("sku", "description", *HARDWARE_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "edging": (
        "edging_materials",
        "material_id",
        f"material_id, sku, description, workspace_id, {EDGING_FIELDS}, (image_blob IS NOT NULL) AS has_image, "
        f"{ENRICHMENT_SELECT}",
        ("sku", "description", *EDGING_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "custom_made": (
        "custom_made",
        "material_id",
        f"material_id, internal_ref, description, sku, workspace_id, {CUSTOM_FIELDS}, "
        f"(image_blob IS NOT NULL) AS has_image, {ENRICHMENT_SELECT}",
        ("internal_ref", "description", "sku", *CUSTOM_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "benchtop": (
        "benchtop_materials",
        "material_id",
        f"material_id, slab_id, description, sku, grain_locked, workspace_id, "
        f"{BENCHTOP_FIELDS}, (image_blob IS NOT NULL) AS has_image, {ENRICHMENT_SELECT}",
        ("slab_id", "description", "sku", "grain_locked", *BENCHTOP_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "appliance": (
        "appliances",
        "material_id",
        f"material_id, model_number, description, sku, workspace_id, {APPLIANCE_FIELDS}, "
        f"(image_blob IS NOT NULL) AS has_image, {ENRICHMENT_SELECT}",
        ("model_number", "description", "sku", *APPLIANCE_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
    "hire": (
        "equipment_hire",
        "hire_id",
        f"hire_id, contract_ref, project_id, description, sku, workspace_id, {HIRE_FIELDS}, "
        f"(image_blob IS NOT NULL) AS has_image, {ENRICHMENT_SELECT}",
        ("contract_ref", "project_id", "description", "sku", *HIRE_FIELDS_TUPLE, *ENRICHMENT_INSERT),
    ),
}


# material_type (as stored on batches, take lines, hardware catalog rows) -> catalog table.
MATERIAL_TABLE_BY_TYPE: dict[str, str] = {
    "BOARD": "board_materials", "HARDWARE": "hardware_materials", "CUSTOM": "custom_made",
    "BENCHTOP": "benchtop_materials", "APPLIANCE": "appliances", "HIRE": "equipment_hire",
    "EDGING": "edging_materials", "GLASS": "glass_materials",
    "TIMBER": "timber_materials",
}
_ID_COLUMN_BY_TABLE: dict[str, str] = {table: id_col for table, id_col, *_ in REGISTRY.values()}


class MaterialNotFound(Exception):
    """A request named a catalog row that is not in the caller's workspace.

    A row of another workspace and a row that does not exist are the same answer
    (workspace isolation: cross-workspace is 404, never a hint that the row exists).
    """

    def __init__(self, material_id: int):
        self.detail = {
            "code": "MATERIAL_NOT_FOUND", "material_id": material_id,
            "message": "material not found in this workspace",
        }


def assert_material_in_workspace(
    db: Session, *, table: str, material_id: int, workspace_id: int
) -> None:
    """Raise `MaterialNotFound` unless `material_id` is a row of catalog `table` in this
    workspace. `table` is one of the six catalog tables; anything else is refused."""
    id_col = _ID_COLUMN_BY_TABLE.get(table)
    found = id_col is not None and db.execute(
        text(f"SELECT 1 FROM {table} WHERE {id_col} = :m AND workspace_id = :w"),
        {"m": material_id, "w": workspace_id},
    ).first() is not None
    if not found:
        raise MaterialNotFound(material_id)


def list_catalog(
    db: Session,
    *,
    type_: str,
    workspace_id: int,
    q: str | None = None,
    supplier: str | None = None,
    archived: bool = False,
    product_type: str | None = None,
    untyped: bool = False,
) -> list[dict]:
    table, id_col, cols, _ = REGISTRY[type_]
    where = ["workspace_id = :w"]
    params: dict = {"w": workspace_id}
    if not archived:
        where.append("archived_at IS NULL")
    if untyped:
        where.append("(product_type IS NULL OR btrim(product_type) = '')")
    elif product_type:
        where.append("lower(btrim(product_type)) = lower(btrim(:ptype))")
        params["ptype"] = product_type
    if q:
        where.append("(description ILIKE :q OR sku ILIKE :q OR product_type ILIKE :q)")
        params["q"] = f"%{q}%"
    if supplier:
        where.append("default_supplier = :sup")
        params["sup"] = supplier
    sql = (
        f"SELECT {cols}, {_supplier_link_cols(table)} FROM {table} "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {id_col} DESC"
    )
    return [dict(r) | {"type": type_} for r in db.execute(text(sql), params).mappings()]


def product_type_counts(db: Session, *, workspace_id: int, archived: bool = False) -> dict:
    """The product types in use across the six tables, with how many items each has.

    Types are free text, so 'Glass' and 'glass ' are one type (shown as its most used spelling, else the first alphabetically).
    `untyped` counts the items with no type."""
    spellings: dict[str, dict[str, int]] = {}      # lower-cased type -> {spelling: items}
    untyped = 0
    for table, *_ in REGISTRY.values():
        sql = (
            f"SELECT btrim(product_type) AS t, count(*) FROM {table} WHERE workspace_id = :w"
            + ("" if archived else " AND archived_at IS NULL")
            + " GROUP BY btrim(product_type)"
        )
        for t, n in db.execute(text(sql), {"w": workspace_id}).all():
            if not t:
                untyped += n
            else:
                by_spelling = spellings.setdefault(t.lower(), {})
                by_spelling[t] = by_spelling.get(t, 0) + n
    types = sorted(
        ({"product_type": min(sp, key=lambda t: (-sp[t], t)), "count": sum(sp.values())} for sp in spellings.values()),
        key=lambda x: x["product_type"].lower(),
    )
    return {"types": types, "untyped": untyped}


def get_catalog_row(
    db: Session, *, type_: str, mid: int, workspace_id: int
) -> dict | None:
    table, id_col, cols, _ = REGISTRY[type_]
    sql = text(
        f"SELECT {cols}, {_supplier_link_cols(table)} FROM {table} "
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
                 WHEN 'edging_materials'   THEN (SELECT description FROM edging_materials   WHERE material_id = m.target_material_id)
                 WHEN 'glass_materials'    THEN (SELECT description FROM glass_materials    WHERE material_id = m.target_material_id)
                 WHEN 'timber_materials'   THEN (SELECT description FROM timber_materials   WHERE material_id = m.target_material_id)
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


_SET_IMAGE = {
    "board": "UPDATE board_materials SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
             "RETURNING material_id",
    "edging": "UPDATE edging_materials SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
              "RETURNING material_id",
    "custom_made": "UPDATE custom_made SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
                   "RETURNING material_id",
    "hardware": "UPDATE hardware_materials SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
                "RETURNING material_id",
    "benchtop": "UPDATE benchtop_materials SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
                "RETURNING material_id",
    "glass": "UPDATE glass_materials SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
             "RETURNING material_id",
    "timber": "UPDATE timber_materials SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
              "RETURNING material_id",
    # equipment_hire's primary key is `hire_id`
    "hire": "UPDATE equipment_hire SET image_blob = :b WHERE hire_id = :m AND workspace_id = :w "
            "RETURNING hire_id",
    "appliance": "UPDATE appliances SET image_blob = :b WHERE material_id = :m AND workspace_id = :w "
                 "RETURNING material_id",
}


def set_image(db: Session, *, type_: str, mid: int, workspace_id: int, blob_id: int | None) -> bool:
    """Point a catalog row at its picture (or clear it). False when the row is not this workspace's."""
    return db.execute(
        text(_SET_IMAGE[type_]),
        {"b": blob_id, "m": mid, "w": workspace_id},
    ).scalar() is not None


def image_blob(db: Session, *, type_: str, mid: int, workspace_id: int) -> tuple[bool, int | None]:
    """(the row exists in this workspace, its image blob id)."""
    table = IMAGE_TABLES[type_]
    pk = REGISTRY[type_][1]
    r = db.execute(
        text(f"SELECT image_blob FROM {table} WHERE {pk} = :m AND workspace_id = :w"),
        {"m": mid, "w": workspace_id},
    ).first()
    return (r is not None, r[0] if r else None)

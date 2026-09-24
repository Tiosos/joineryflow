"""Supplier query layer.

`vendors` **is** the supplier entity (Q506 + Q556), and since **Q565** this is
its only surface — the legacy `/procurement/vendors*` endpoints are gone. Two
things that namespace never did, and this one does:

* **workspace isolation** on every read and write. `workspace` appeared zero
  times in `procurement/queries.py`, which stopped being harmless the moment
  `0029` gave `vendors` a `workspace_id`.
* **catalog linkage.** `0029` added `supplier_id` / `default_supplier_id` to
  all six catalog tables **beside** their retained free text (Q435), so a
  supplier can be pointed at a material without losing the name already there.

`equipment_hire` keys on `hire_id`, not `material_id` — the per-table PK map
below exists for that one difference, the same reason `0029` carries a
per-table supplier-column map.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from .schemas import CreateSupplierIn, PatchSupplierIn

# The six catalog tables and the PK each one actually uses.
CATALOG_PK = {
    "board_materials": "material_id",
    "hardware_materials": "material_id",
    "custom_made": "material_id",
    "benchtop_materials": "material_id",
    "appliances": "material_id",
    "equipment_hire": "hire_id",
}
LINK_FIELDS = frozenset({"supplier_id", "default_supplier_id"})

_LINKED_COUNT = " + ".join(
    f"(SELECT COUNT(*) FROM {tbl} WHERE supplier_id = v.vendor_id"
    f" OR default_supplier_id = v.vendor_id)"
    for tbl in CATALOG_PK
)

_SUPPLIER_COLS = f"""
    v.vendor_id, v.name, v.category, v.status,
    v.contact_name, v.contact_email, v.contact_phone, v.address,
    v.rating, v.tax_id, v.payment_terms,
    ({_LINKED_COUNT}) AS linked_material_count,
    v.created_at, v.updated_at
"""

_PATCHABLE = frozenset({
    "name", "category", "status", "contact_name", "contact_email",
    "contact_phone", "address", "rating", "tax_id", "payment_terms",
})


def list_suppliers(
    db: Session, *, workspace_id: int, q: str | None = None,
    category: str | None = None, status: str | None = None,
) -> list[dict]:
    where = ["v.workspace_id = :w"]
    params: dict[str, Any] = {"w": workspace_id}
    if q:
        where.append("v.name ILIKE :q")
        params["q"] = f"%{q}%"
    if category:
        where.append("v.category = :cat")
        params["cat"] = category
    if status:
        where.append("v.status = :st")
        params["st"] = status
    rows = db.execute(
        text(f"SELECT {_SUPPLIER_COLS} FROM vendors v"
             f" WHERE {' AND '.join(where)} ORDER BY v.name"),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def get_supplier(db: Session, *, vendor_id: int, workspace_id: int) -> dict | None:
    row = db.execute(
        text(f"SELECT {_SUPPLIER_COLS} FROM vendors v"
             " WHERE v.vendor_id = :v AND v.workspace_id = :w"),
        {"v": vendor_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def create_supplier(
    db: Session, *, workspace_id: int, payload: CreateSupplierIn, actor_id: int
) -> tuple[str, dict | None]:
    """('OK', supplier) | ('UNKNOWN_CATEGORY', None).

    `workspace_id` is supplied here — the omission that broke the legacy
    insert once `0029` made the column NOT NULL (Q565).
    """
    known = db.execute(
        text("SELECT 1 FROM order_category WHERE category_key = :c"
             " AND archived_at IS NULL"),
        {"c": payload.category},
    ).first()
    if known is None:
        return "UNKNOWN_CATEGORY", None

    vendor_id = db.execute(
        text(
            """
            INSERT INTO vendors (
                workspace_id, name, category, contact_name, contact_email,
                contact_phone, address, tax_id, payment_terms
            )
            VALUES (:w, :name, :cat, :cn, :ce, :cp, :addr, :tax, :terms)
            RETURNING vendor_id
            """
        ),
        {
            "w": workspace_id, "name": payload.name, "cat": payload.category,
            "cn": payload.contact_name,
            "ce": str(payload.contact_email) if payload.contact_email else None,
            "cp": payload.contact_phone, "addr": payload.address,
            "tax": payload.tax_id, "terms": payload.payment_terms,
        },
    ).scalar()
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="supplier.create", target=str(vendor_id),
        payload={"name": payload.name, "category": payload.category},
    )
    return "OK", get_supplier(db, vendor_id=vendor_id, workspace_id=workspace_id)


def patch_supplier(
    db: Session, *, vendor_id: int, workspace_id: int,
    payload: PatchSupplierIn, actor_id: int,
) -> tuple[str, dict | None]:
    """('OK', supplier) | ('NOT_FOUND'|'UNKNOWN_CATEGORY', None)."""
    current = get_supplier(db, vendor_id=vendor_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND", None

    fields = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in _PATCHABLE
    }
    if not fields:
        return "OK", current
    if fields.get("category") is not None:
        known = db.execute(
            text("SELECT 1 FROM order_category WHERE category_key = :c"
                 " AND archived_at IS NULL"),
            {"c": fields["category"]},
        ).first()
        if known is None:
            return "UNKNOWN_CATEGORY", None

    sets, params = [], {"v": vendor_id}
    for n, (col, val) in enumerate(fields.items()):
        sets.append(f"{col} = :p{n}")
        params[f"p{n}"] = str(val) if col == "contact_email" and val else val
    db.execute(
        text(f"UPDATE vendors SET {', '.join(sets)}, updated_at = now()"
             " WHERE vendor_id = :v"),
        params,
    )
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="supplier.update", target=str(vendor_id),
        payload={"fields": sorted(fields)},
    )
    return "OK", get_supplier(db, vendor_id=vendor_id, workspace_id=workspace_id)


def link_material(
    db: Session, *, vendor_id: int, workspace_id: int,
    material_table: str, material_id: int, field: str, actor_id: int,
) -> str:
    """Q506 — point a catalog row's supplier at this vendor.

    Codes: OK | NOT_FOUND | UNKNOWN_TABLE | UNKNOWN_FIELD | MATERIAL_NOT_FOUND
    """
    if material_table not in CATALOG_PK:
        return "UNKNOWN_TABLE"
    if field not in LINK_FIELDS:
        return "UNKNOWN_FIELD"
    if get_supplier(db, vendor_id=vendor_id, workspace_id=workspace_id) is None:
        return "NOT_FOUND"

    pk = CATALOG_PK[material_table]
    updated = db.execute(
        text(
            f"""
            UPDATE {material_table}
               SET {field} = :v
             WHERE {pk} = :m AND workspace_id = :w
            RETURNING {pk}
            """
        ),
        {"v": vendor_id, "m": material_id, "w": workspace_id},
    ).first()
    if updated is None:
        return "MATERIAL_NOT_FOUND"
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="supplier.link_material", target=str(vendor_id),
        payload={"material_table": material_table, "material_id": material_id,
                 "field": field},
    )
    return "OK"


def linked_materials(
    db: Session, *, vendor_id: int, workspace_id: int
) -> list[dict] | None:
    """Every catalog row pointing at this supplier, across the six tables."""
    if get_supplier(db, vendor_id=vendor_id, workspace_id=workspace_id) is None:
        return None
    parts = [
        f"""
        SELECT '{tbl}' AS material_table, {pk} AS material_id, sku, description,
               (supplier_id = :v) AS is_supplier,
               (default_supplier_id = :v) AS is_default_supplier
        FROM {tbl}
        WHERE workspace_id = :w
          AND (supplier_id = :v OR default_supplier_id = :v)
        """
        for tbl, pk in CATALOG_PK.items()
    ]
    rows = db.execute(
        text(" UNION ALL ".join(parts) + " ORDER BY material_table, material_id"),
        {"v": vendor_id, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]

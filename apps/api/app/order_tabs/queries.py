"""The order pop-up's tabs (migration 0064): Delivery log, Stock, Tracking, Cutlists, Product image.

Every read starts from `_order`, which scopes the order to the caller's workspace the way the
Orderbook does (another workspace's order is a missing one). The Delivery log and the product image
write only while the order is not frozen (Cancelled / Delivered), like its other fields.
"""
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..catalog import queries as cq
from ..orders import queries as oq
from ..row_types import live_joinery_items, not_deleted
from ..sql_columns import require_columns

# catalog table -> (the `project_hardware_catalog.material_type` it is stored as, its primary key)
_CATALOG_REGISTRY = {
    "board_materials": ("BOARD", "material_id"),
    "hardware_materials": ("HARDWARE", "material_id"),
    "custom_made": ("CUSTOM", "material_id"),
    "benchtop_materials": ("BENCHTOP", "material_id"),
    "appliances": ("APPLIANCE", "material_id"),
    "equipment_hire": ("HIRE", "hire_id"),
    "edging_materials": ("EDGING", "material_id"),
    "glass_materials": ("GLASS", "material_id"),
    "timber_materials": ("TIMBER", "material_id"),
}


def order_row(db: Session, *, po_id: int, workspace_id: int) -> dict | None:
    row = db.execute(
        text(
            "SELECT po.po_id, po.po_number, po.status, po.description, po.product_code, po.quantity,"
            " po.item_id, po.image_blob, po.project_id FROM purchase_orders po"
            f" WHERE po.po_id = :o AND {oq._ORDER_WORKSPACE}"
        ),
        {"o": po_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


# ── Delivery log ────────────────────────────────────────────────────────────────────────────────

_DELIVERY_COLS = (
    "d.delivery_id, d.qty, d.date_received, d.signed_by, d.notes, (d.docket_blob IS NOT NULL) AS has_docket,"
    " b.mime AS docket_mime, d.created_at"
)


def delivery_log(db: Session, *, po_id: int, workspace_id: int) -> dict | None:
    order = order_row(db, po_id=po_id, workspace_id=workspace_id)
    if order is None:
        return None
    rows = db.execute(
        text(
            f"SELECT {_DELIVERY_COLS} FROM order_delivery d LEFT JOIN file_blob b ON b.file_blob_id = d.docket_blob"
            " WHERE d.po_id = :o ORDER BY d.date_received, d.delivery_id"
        ),
        {"o": po_id},
    ).mappings().all()
    total = sum((r["qty"] for r in rows), Decimal(0))
    qty = order["quantity"]
    return {"quantity": qty, "deliveries": [dict(r) for r in rows], "sum_received": total,
            "remaining": None if qty is None else qty - total}


def _lock(db: Session, po_id: int, workspace_id: int) -> bool:
    """Lock the order for this transaction; raises `OrderLocked` when it is frozen. False when missing."""
    return oq._lock_order_for_update(db, po_id=po_id, workspace_id=workspace_id)


def add_delivery(db: Session, *, po_id: int, workspace_id: int, actor_id: int, payload) -> dict | None:
    if not _lock(db, po_id, workspace_id):
        return None
    new_id = db.execute(
        text(
            "INSERT INTO order_delivery (po_id, qty, date_received, signed_by, notes, created_by)"
            " VALUES (:o, :q, :d, :s, :n, :u) RETURNING delivery_id"
        ),
        {"o": po_id, "q": payload.qty, "d": payload.date_received, "s": payload.signed_by,
         "n": payload.notes, "u": actor_id},
    ).scalar_one()
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="order.delivery.add",
                target=f"order:{po_id}", payload={"delivery_id": new_id, "qty": str(payload.qty)})
    return delivery_log(db, po_id=po_id, workspace_id=workspace_id)


_DELIVERY_PATCHABLE = frozenset({"qty", "date_received", "signed_by", "notes"})


def patch_delivery(
    db: Session, *, po_id: int, delivery_id: int, workspace_id: int, actor_id: int, fields: dict
) -> dict | None:
    if not _lock(db, po_id, workspace_id):
        return None
    if not db.execute(text("SELECT 1 FROM order_delivery WHERE delivery_id = :d AND po_id = :o"),
                      {"d": delivery_id, "o": po_id}).first():
        return None
    if fields:
        require_columns(fields, _DELIVERY_PATCHABLE)
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        db.execute(text(f"UPDATE order_delivery SET {sets}, updated_at = now() WHERE delivery_id = :d"),
                   {**fields, "d": delivery_id})
        write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="order.delivery.update",
                    target=f"order:{po_id}", payload={"delivery_id": delivery_id, "fields": sorted(fields)})
    return delivery_log(db, po_id=po_id, workspace_id=workspace_id)


def delete_delivery(db: Session, *, po_id: int, delivery_id: int, workspace_id: int, actor_id: int) -> dict | None:
    if not _lock(db, po_id, workspace_id):
        return None
    gone = db.execute(text("DELETE FROM order_delivery WHERE delivery_id = :d AND po_id = :o RETURNING delivery_id"),
                      {"d": delivery_id, "o": po_id}).first()
    if not gone:
        return None
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="order.delivery.remove",
                target=f"order:{po_id}", payload={"delivery_id": delivery_id})
    return delivery_log(db, po_id=po_id, workspace_id=workspace_id)


def docket_blob(db: Session, *, po_id: int, delivery_id: int, workspace_id: int) -> int | None:
    if order_row(db, po_id=po_id, workspace_id=workspace_id) is None:
        return None
    return db.execute(text("SELECT docket_blob FROM order_delivery WHERE delivery_id = :d AND po_id = :o"),
                      {"d": delivery_id, "o": po_id}).scalar()


def set_docket(
    db: Session, *, po_id: int, delivery_id: int, workspace_id: int, actor_id: int, blob_id: int | None
) -> dict | None:
    if not _lock(db, po_id, workspace_id):
        return None
    found = db.execute(
        text("UPDATE order_delivery SET docket_blob = :b, updated_at = now() WHERE delivery_id = :d AND po_id = :o"
             " RETURNING delivery_id"),
        {"b": blob_id, "d": delivery_id, "o": po_id},
    ).first()
    if not found:
        return None
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id,
                event="order.delivery.docket" if blob_id is not None else "order.delivery.docket.remove",
                target=f"order:{po_id}", payload={"delivery_id": delivery_id})
    return delivery_log(db, po_id=po_id, workspace_id=workspace_id)


# ── Stock ───────────────────────────────────────────────────────────────────────────────────────

def stock_orders(db: Session, *, po_id: int, workspace_id: int) -> list[dict] | None:
    """Stock-tracked orders (not Cancelled / Rejected) of the same product code as this order."""
    order = order_row(db, po_id=po_id, workspace_id=workspace_id)
    if order is None:
        return None
    code = (order["product_code"] or "").strip()
    if not code:
        return []
    rows = db.execute(
        text(
            "SELECT po.po_id, po.quantity, po.product_code, po.project_name, po.description, po.total_amount,"
            " po.category FROM purchase_orders po"
            f" WHERE po.stock_tracked AND lower(po.product_code) = lower(:c) AND {oq._ORDER_WORKSPACE}"
            " AND po.status NOT IN ('Cancelled', 'Rejected') ORDER BY po.po_id DESC LIMIT 200"
        ),
        {"c": code, "w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


# ── Tracking ────────────────────────────────────────────────────────────────────────────────────

def tracking(db: Session, *, po_id: int, workspace_id: int) -> dict | None:
    order = order_row(db, po_id=po_id, workspace_id=workspace_id)
    if order is None:
        return None
    item = None
    if order["item_id"] is not None:
        row = db.execute(
            text(
                "SELECT i.item_id, i.num AS item_number, i.description, i.qty,"
                " (SELECT s.done_date FROM item_stages s WHERE s.item_id = i.item_id AND s.stage_key = 'MADE')"
                " AS date_made FROM items i JOIN projects p ON p.project_id = i.project_id"
                f" WHERE i.item_id = :i AND p.workspace_id = :w AND {live_joinery_items('i')}"
            ),
            {"i": order["item_id"], "w": workspace_id},
        ).mappings().first()
        item = dict(row) if row else None
    return {"order_number": order["po_number"], "description": order["description"],
            "quantity": order["quantity"], "item": item}


# ── Cutlists ────────────────────────────────────────────────────────────────────────────────────

def cutlists(db: Session, *, po_id: int, workspace_id: int) -> dict | None:
    """Cutlists whose items use this order's product: the catalog row whose SKU is the order's product code,
    found through the item's parts (boards) and hardware lines (every catalog table)."""
    order = order_row(db, po_id=po_id, workspace_id=workspace_id)
    if order is None:
        return None
    code = (order["product_code"] or "").strip()
    found: list[tuple[str, int]] = []
    if code:
        for table, (mtype, pk) in _CATALOG_REGISTRY.items():
            for mid in db.execute(
                text(f"SELECT {pk} FROM {table} WHERE workspace_id = :w AND lower(sku) = lower(:c)"),
                {"w": workspace_id, "c": code},
            ).scalars():
                found.append((mtype, int(mid)))
    if not found:
        return {"product_found": False, "cutlists": []}
    rows: dict[tuple[int, int | None], dict] = {}
    for mtype, mid in found:
        uses = [
            ("SELECT l.item_id FROM item_hardware_lines l JOIN project_hardware_catalog c"
             " ON c.catalog_id = l.catalog_id WHERE c.material_type = :t AND c.material_id = :m"),
        ]
        if mtype == "BOARD":
            uses.append("SELECT mo.item_id FROM modules mo JOIN parts p ON p.module_id = mo.module_id"
                        " WHERE p.board_material_id = :m")
        for use in uses:
            for r in db.execute(
                text(
                    "SELECT cl.cutlist_no, cl.created_at, pr.name AS project_name, i.description AS item_description,"
                    " i.item_id FROM items i JOIN cutlist cl ON cl.cutlist_id = i.cutlist_id"
                    " JOIN projects pr ON pr.project_id = i.project_id"
                    f" WHERE i.item_id IN ({use}) AND pr.workspace_id = :w AND {live_joinery_items('i')}"
                    f" AND {not_deleted('cl')} ORDER BY cl.created_at, cl.cutlist_no LIMIT 500"
                ),
                {"t": mtype, "m": mid, "w": workspace_id},
            ).mappings():
                rows[(r["cutlist_no"], r["item_id"])] = dict(r)
    ordered = sorted(rows.values(), key=lambda r: (r["created_at"], r["cutlist_no"]))
    return {"product_found": True, "cutlists": ordered}


# ── Catalog item (the catalog row whose SKU is the order's product code) ───────────────────────

# Fixed order the matches are listed in (a code can exist in several tables); a test pins it to the REGISTRY keys.
CATALOG_MATCH_ORDER = ("board", "benchtop", "hardware", "edging", "glass", "timber", "custom_made", "appliance", "hire")
# Each type's own fields: the catalog's field tuples, so a field added there shows up here. `um` and
# `product_website` are lifted out of the list (shown on their own); no money, notes or supplier columns.
_CATALOG_TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "board": cq.BOARD_FIELDS_TUPLE, "benchtop": cq.BENCHTOP_FIELDS_TUPLE, "hardware": cq.HARDWARE_FIELDS_TUPLE,
    "edging": cq.EDGING_FIELDS_TUPLE, "glass": cq.GLASS_FIELDS_TUPLE, "timber": cq.TIMBER_FIELDS_TUPLE,
    "custom_made": cq.CUSTOM_FIELDS_TUPLE, "appliance": cq.APPLIANCE_FIELDS_TUPLE, "hire": cq.HIRE_FIELDS_TUPLE,
}
_LIFTED = ("um", "product_website")
_PER_TABLE = 5


def _plain(v):
    return float(v) if isinstance(v, Decimal) else v


def catalog_matches(db: Session, *, po_id: int, workspace_id: int) -> list[dict] | None:
    """The catalog rows (all nine tables) whose SKU is the order's product code, trimmed and case-insensitive,
    live ones first, then by `CATALOG_MATCH_ORDER`, then oldest row first. An Equipment Hire row belongs to a
    project, so it matches only the order's own project (an order with no project matches none).
    None = no such order in this workspace."""
    order = order_row(db, po_id=po_id, workspace_id=workspace_id)
    if order is None:
        return None
    code = (order["product_code"] or "").strip()
    if not code:
        return []
    out: list[dict] = []
    for type_ in CATALOG_MATCH_ORDER:
        table, pk = cq.REGISTRY[type_][0], cq.REGISTRY[type_][1]
        fields = [f for f in _CATALOG_TYPE_FIELDS[type_] if f not in _LIFTED]
        extra, params = "", {"w": workspace_id, "c": code}
        if type_ == "hire":
            if order["project_id"] is None:
                continue
            extra, params["p"] = " AND project_id = :p", order["project_id"]
        rows = db.execute(
            text(
                f"SELECT {pk} AS id, sku, description, product_type, um, product_website,"
                f" (archived_at IS NOT NULL) AS archived, (image_blob IS NOT NULL) AS has_image"
                f"{''.join(', ' + f for f in fields)} FROM {table}"
                f" WHERE workspace_id = :w AND lower(btrim(sku)) = lower(:c){extra}"
                f" ORDER BY (archived_at IS NOT NULL), {pk} LIMIT {_PER_TABLE}"
            ),
            params,
        ).mappings().all()
        for r in rows:
            out.append({
                "type": type_, "id": r["id"], "sku": r["sku"], "description": r["description"],
                "product_type": r["product_type"], "um": r["um"], "product_website": r["product_website"],
                "archived": r["archived"], "has_image": r["has_image"],
                "fields": {f: _plain(r[f]) for f in fields},
            })
    out.sort(key=lambda m: m["archived"])  # stable: live first, the fixed table order kept within each group
    return out


def catalog_match_image(db: Session, *, po_id: int, workspace_id: int, n: int) -> tuple[bool, int | None]:
    """(the order exists here, the picture blob of its n-th catalog match). Only rows that match the order's
    product code can be reached, so the Orderbook never opens a picture of an arbitrary catalog row."""
    matches = catalog_matches(db, po_id=po_id, workspace_id=workspace_id)
    if matches is None:
        return False, None
    if n >= len(matches) or not matches[n]["has_image"]:
        return True, None
    m = matches[n]
    _, blob = cq.image_blob(db, type_=m["type"], mid=m["id"], workspace_id=workspace_id)
    return True, blob


# ── Product image ───────────────────────────────────────────────────────────────────────────────

def set_image(db: Session, *, po_id: int, workspace_id: int, actor_id: int, blob_id: int | None) -> bool:
    if not _lock(db, po_id, workspace_id):
        return False
    db.execute(text("UPDATE purchase_orders SET image_blob = :b, updated_at = now() WHERE po_id = :o"),
               {"b": blob_id, "o": po_id})
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id,
                event="order.image.set" if blob_id is not None else "order.image.remove",
                target=f"order:{po_id}", payload={})
    return True

"""Orders query layer.

Routes own the transaction boundary; queries flush only. Workspace isolation
runs through `projects.workspace_id` when the order has a project, and through
`vendors.workspace_id` otherwise — an order with no project (Q554: office
consumables, a stock buy) is still somebody's.

Four rules from Plan V1 live here:

* **Q428** — the CUTLIST NO. on a related part's order comes from its **parent**
  Joinery Item's cutlist, never from the related part itself (Q417).
* **Q429** — an order may be created before the parent has a cutlist; the field
  stays blank.
* **Q430** — when the parent later gains a cutlist, every linked order with a
  blank number is filled in automatically.
* **Q431** — when the parent's cutlist is **replaced**, every linked order is
  updated to the new number, with the old one preserved in the audit payload.

Q430 and Q431 are the same function, `sync_orders_for_item`, called from the
cutlist link/unlink paths. It is deliberately in this module rather than in
`cutlists/`: the orders own the column being written.
"""
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from .schemas import CreateOrderIn, CreateOrderLineIn, PatchOrderIn

# An order reaches its workspace through its project, or, when it has none,
# through its vendor (Q554/Q555).
_ORDER_WORKSPACE = """
    (
        (po.project_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM projects p2
            WHERE p2.project_id = po.project_id AND p2.workspace_id = :w
        ))
        OR
        (po.project_id IS NULL AND EXISTS (
            SELECT 1 FROM vendors v2
            WHERE v2.vendor_id = po.vendor_id AND v2.workspace_id = :w
        ))
    )
"""

_ORDER_COLS = """
    po.po_id, po.po_number, po.order_number, po.supplier_ref_no,
    po.status, po.priority,
    po.vendor_id, v.name AS vendor_name,
    po.project_id, po.project_name, po.location,
    po.item_id, i.num AS item_number, po.cutlist_no,
    po.category, po.description, po.product_code, po.product_description,
    po.quantity, po.unit_of_measure, po.unit_cost, po.total_amount, po.currency,
    po.required_date, po.date_ordered, po.due_date,
    po.notes, po.internal_comments, po.attributes,
    po.created_at, po.updated_at
"""

_ORDER_FROM = """
    FROM purchase_orders po
    LEFT JOIN vendors v ON v.vendor_id = po.vendor_id
    LEFT JOIN items   i ON i.item_id   = po.item_id
"""

_PATCHABLE = frozenset({
    "vendor_id", "description", "category", "status", "priority",
    "order_number", "supplier_ref_no", "location", "product_code",
    "product_description", "quantity", "unit_of_measure", "unit_cost",
    "total_amount", "required_date", "date_ordered", "due_date",
    "notes", "internal_comments", "attributes",
})


def list_categories(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT category_key, label FROM order_category"
            " WHERE archived_at IS NULL ORDER BY sort_order, category_key"
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def get_order(db: Session, *, po_id: int, workspace_id: int) -> dict | None:
    row = db.execute(
        text(f"SELECT {_ORDER_COLS} {_ORDER_FROM} WHERE po.po_id = :o AND {_ORDER_WORKSPACE}"),
        {"o": po_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    order = dict(row)
    lines = db.execute(
        text(
            """
            SELECT line_id, line_number, item_description, sku, quantity, unit,
                   unit_price, line_total, material_table, material_id, attributes
            FROM po_line_items
            WHERE po_id = :o
            ORDER BY line_number
            """
        ),
        {"o": po_id},
    ).mappings().all()
    order["lines"] = [dict(r) for r in lines]
    return order


def list_orders_for_workspace(
    db: Session,
    *,
    workspace_id: int,
    status: str | None = None,
    supplier: str | None = None,
    q: str | None = None,
) -> list[dict]:
    """Every order in the workspace, newest first — the Orderbook page (Q418).

    Cross-project by design: Orderbook has always been the cross-project queue
    (#4 grouped batches by supplier here), and Q504 keeps orders as the
    commercial layer above those batches rather than replacing them.

    `_ORDER_WORKSPACE` already covers the Q554 case of an order with no project
    at all — it reaches its workspace through its vendor instead — so such an
    order is listed here even though no project page would ever show it.
    """
    where = [_ORDER_WORKSPACE]
    params: dict = {"w": workspace_id}
    if status:
        where.append("po.status = :st")
        params["st"] = status
    if supplier:
        where.append("v.name = :sup")
        params["sup"] = supplier
    if q:
        # Deliberately narrow: the number a user arrives with from Tracking,
        # or a word from the description. Not a full-text search.
        where.append(
            "(po.po_number ILIKE :q OR po.description ILIKE :q"
            " OR po.cutlist_no ILIKE :q OR po.order_number ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    rows = db.execute(
        text(
            f"SELECT {_ORDER_COLS} {_ORDER_FROM} WHERE {' AND '.join(where)}"
            " ORDER BY po.po_id DESC"
        ),
        params,
    ).mappings().all()
    return [dict(r) for r in rows]


def list_orders_for_project(
    db: Session, *, project_id: int, workspace_id: int
) -> list[dict] | None:
    in_ws = db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first()
    if in_ws is None:
        return None
    rows = db.execute(
        text(f"SELECT {_ORDER_COLS} {_ORDER_FROM} WHERE po.project_id = :p ORDER BY po.po_id DESC"),
        {"p": project_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def list_orders_for_item(
    db: Session, *, item_id: int, workspace_id: int
) -> list[dict] | None:
    """Tracking's O/BOOK subtab (Q425) for one row."""
    in_ws = db.execute(
        text(
            """
            SELECT 1 FROM items i
            JOIN projects p ON p.project_id = i.project_id
            WHERE i.item_id = :i AND p.workspace_id = :w
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).first()
    if in_ws is None:
        return None
    rows = db.execute(
        text(f"SELECT {_ORDER_COLS} {_ORDER_FROM} WHERE po.item_id = :i ORDER BY po.po_id DESC"),
        {"i": item_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _prefill_from_item(db: Session, *, item_id: int, workspace_id: int) -> dict | None:
    """Q427/Q428 — PROJECT, LOCATION and CUTLIST NO. for an order on this row.

    For a **related part** the cutlist number comes from its parent, because a
    related part never holds one (Q417). For a Joinery Item it is its own.
    Either may be NULL, which Q429 explicitly allows.
    """
    row = db.execute(
        text(
            """
            SELECT i.item_id, i.project_id, i.row_type, i.parent_item_id,
                   p.name AS project_name,
                   i.stage AS location,
                   COALESCE(own.cutlist_no, parent_cl.cutlist_no) AS cutlist_no
            FROM items i
            JOIN projects p ON p.project_id = i.project_id
            LEFT JOIN cutlist own       ON own.cutlist_id = i.cutlist_id
            LEFT JOIN items   parent    ON parent.item_id = i.parent_item_id
            LEFT JOIN cutlist parent_cl ON parent_cl.cutlist_id = parent.cutlist_id
            WHERE i.item_id = :i AND p.workspace_id = :w
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def create_order(
    db: Session,
    *,
    workspace_id: int,
    payload: CreateOrderIn,
    actor_id: int,
) -> tuple[str, dict | None]:
    """('OK', order) | ('ITEM_NOT_FOUND', None) | ('VENDOR_NOT_FOUND', None)."""
    vendor = db.execute(
        text("SELECT 1 FROM vendors WHERE vendor_id = :v AND workspace_id = :w"),
        {"v": payload.vendor_id, "w": workspace_id},
    ).first()
    if vendor is None:
        return "VENDOR_NOT_FOUND", None

    project_id = payload.project_id
    project_name = payload.project_name
    location = payload.location
    cutlist_no: str | None = None

    if payload.item_id is not None:
        item = _prefill_from_item(
            db, item_id=payload.item_id, workspace_id=workspace_id
        )
        if item is None:
            return "ITEM_NOT_FOUND", None
        # Q427: carried over, not asked for. An explicit value still wins.
        project_id = project_id or item["project_id"]
        project_name = project_name or item["project_name"]
        location = location or item["location"]
        # Q428/Q429: the parent's number, or blank if there is none yet.
        cutlist_no = str(item["cutlist_no"]) if item["cutlist_no"] is not None else None

    po_id = db.execute(
        text(
            """
            INSERT INTO purchase_orders (
                po_number, vendor_id, requester_id, description, category,
                item_id, project_id, project_name, location, cutlist_no,
                order_number, supplier_ref_no, priority,
                product_code, product_description,
                quantity, unit_of_measure, unit_cost, total_amount,
                required_date, notes, internal_comments, attributes
            )
            VALUES (
                'PO-' || EXTRACT(year FROM now())::int || '-' ||
                    lpad(nextval('po_number_seq')::text, 4, '0'),
                :vendor, :actor, :descr, :cat,
                :item, :proj, :proj_name, :loc, :cutlist,
                :order_no, :supp_ref, :prio,
                :pcode, :pdescr,
                :qty, :uom, :ucost, :total,
                :req_date, :notes, :internal, CAST(:attrs AS jsonb)
            )
            RETURNING po_id
            """
        ),
        {
            "vendor": payload.vendor_id, "actor": actor_id,
            "descr": payload.description, "cat": payload.category,
            "item": payload.item_id, "proj": project_id,
            "proj_name": project_name, "loc": location, "cutlist": cutlist_no,
            "order_no": payload.order_number, "supp_ref": payload.supplier_ref_no,
            "prio": payload.priority, "pcode": payload.product_code,
            "pdescr": payload.product_description, "qty": payload.quantity,
            "uom": payload.unit_of_measure, "ucost": payload.unit_cost,
            "total": payload.total_amount, "req_date": payload.required_date,
            "notes": payload.notes, "internal": payload.internal_comments,
            "attrs": json.dumps(payload.attributes or {}),
        },
    ).scalar()
    db.flush()

    order = get_order(db, po_id=po_id, workspace_id=workspace_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.create", target=str(po_id),
        payload={
            "po_number": order["po_number"],
            "vendor_id": payload.vendor_id,
            "item_id": payload.item_id,
            "cutlist_no": cutlist_no,
            "prefilled_from_item": payload.item_id is not None,
        },
    )
    return "OK", order


def patch_order(
    db: Session, *, po_id: int, workspace_id: int, payload: PatchOrderIn, actor_id: int
) -> dict | None:
    current = get_order(db, po_id=po_id, workspace_id=workspace_id)
    if current is None:
        return None

    fields: dict[str, Any] = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in _PATCHABLE
    }
    if not fields:
        return current

    sets, params = [], {"o": po_id}
    for i, (col, val) in enumerate(fields.items()):
        key = f"v{i}"
        if col == "attributes":
            sets.append(f"{col} = CAST(:{key} AS jsonb)")
            params[key] = json.dumps(val or {})
        else:
            sets.append(f"{col} = :{key}")
            params[key] = val
    db.execute(
        text(f"UPDATE purchase_orders SET {', '.join(sets)}, updated_at = now()"
             " WHERE po_id = :o"),
        params,
    )
    db.flush()

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.update", target=str(po_id),
        payload={"fields": sorted(fields), "po_number": current["po_number"]},
    )
    return get_order(db, po_id=po_id, workspace_id=workspace_id)


def cancel_order(
    db: Session, *, po_id: int, workspace_id: int, actor_id: int
) -> str:
    """Soft-cancel, matching #4's batch rule. 'OK' | 'NOT_FOUND' | 'ALREADY_CANCELLED'."""
    current = get_order(db, po_id=po_id, workspace_id=workspace_id)
    if current is None:
        return "NOT_FOUND"
    if current["status"] == "Cancelled":
        return "ALREADY_CANCELLED"
    db.execute(
        text("UPDATE purchase_orders SET status = 'Cancelled', updated_at = now()"
             " WHERE po_id = :o"),
        {"o": po_id},
    )
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.cancel", target=str(po_id),
        payload={"po_number": current["po_number"], "from_status": current["status"]},
    )
    return "OK"


def add_line(
    db: Session, *, po_id: int, workspace_id: int,
    payload: CreateOrderLineIn, actor_id: int,
) -> dict | None:
    if get_order(db, po_id=po_id, workspace_id=workspace_id) is None:
        return None
    next_no = db.execute(
        text("SELECT COALESCE(MAX(line_number), 0) + 1 FROM po_line_items WHERE po_id = :o"),
        {"o": po_id},
    ).scalar()
    db.execute(
        text(
            """
            INSERT INTO po_line_items (
                po_id, line_number, item_description, sku, quantity, unit,
                unit_price, material_table, material_id, attributes
            )
            VALUES (:o, :n, :d, :sku, :q, :u, :p, :mt, :mid, CAST(:a AS jsonb))
            """
        ),
        {"o": po_id, "n": next_no, "d": payload.item_description,
         "sku": payload.sku, "q": payload.quantity, "u": payload.unit,
         "p": payload.unit_price, "mt": payload.material_table,
         "mid": payload.material_id,
         "a": json.dumps(payload.attributes or {})},
    )
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.line_add", target=str(po_id),
        payload={"line_number": next_no, "description": payload.item_description},
    )
    return get_order(db, po_id=po_id, workspace_id=workspace_id)


def sync_orders_for_item(
    db: Session, *, item_id: int, workspace_id: int, actor_id: int
) -> list[dict]:
    """Q430 + Q431 — keep every order's CUTLIST NO. in step with the item.

    Called after an item's cutlist changes. Covers both the *item's own* orders
    and those of its **related parts**, because Q428 sources a related part's
    order reference from this parent.

    Q430 (fill a blank one) and Q431 (follow a replacement) are the same UPDATE:
    set the order's `cutlist_no` to whatever the reference item now has. Each
    changed order gets its own audit row carrying the previous value, which is
    what Q431's "previous reference remains traceable" requires.

    Returns the orders it changed.
    """
    rows = db.execute(
        text(
            """
            WITH reference AS (
                -- the item itself, plus every related part hanging off it
                SELECT i.item_id AS target_item_id,
                       c.cutlist_no::text AS want
                FROM items i
                LEFT JOIN cutlist c ON c.cutlist_id = i.cutlist_id
                WHERE i.item_id = :i
                UNION ALL
                SELECT rp.item_id, c.cutlist_no::text
                FROM items rp
                JOIN items parent ON parent.item_id = rp.parent_item_id
                LEFT JOIN cutlist c ON c.cutlist_id = parent.cutlist_id
                WHERE rp.parent_item_id = :i
            ),
            -- Capture the PREVIOUS value before the UPDATE: Q431 requires the
            -- old reference to stay traceable, and UPDATE ... RETURNING can
            -- only give the new one.
            before AS (
                SELECT po.po_id, po.cutlist_no AS old_cutlist_no, r.want
                FROM purchase_orders po
                JOIN reference r ON r.target_item_id = po.item_id
                WHERE po.cutlist_no IS DISTINCT FROM r.want
            ),
            updated AS (
                UPDATE purchase_orders po
                   SET cutlist_no = b.want, updated_at = now()
                  FROM before b
                 WHERE po.po_id = b.po_id
                RETURNING po.po_id, po.po_number, po.item_id, po.cutlist_no
            )
            SELECT u.po_id, u.po_number, u.item_id, u.cutlist_no,
                   b.old_cutlist_no
            FROM updated u
            JOIN before b USING (po_id)
            """
        ),
        {"i": item_id},
    ).mappings().all()
    if not rows:
        return []
    db.flush()

    changed = [dict(r) for r in rows]
    for order in changed:
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="order.cutlist_sync", target=str(order["po_id"]),
            payload={
                "po_number": order["po_number"],
                "item_id": order["item_id"],
                # Q431: the previous reference stays traceable in the audit row.
                "old_cutlist_no": order["old_cutlist_no"],
                "new_cutlist_no": order["cutlist_no"],
                "source_item_id": item_id,
            },
        )
    return changed

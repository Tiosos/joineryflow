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
from ..catalog.queries import assert_material_in_workspace
from ..concurrency import bump_field_versions, check_field_conflicts, conflict_safe_value
from .schemas import (
    FROZEN_STATUSES,
    CreateOrderIn,
    CreateOrderLineIn,
    PatchOrderIn,
    PatchOrderLineIn,
)

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
    po.created_at, po.updated_at, po.field_versions
"""

_ORDER_FROM = """
    FROM purchase_orders po
    LEFT JOIN vendors v ON v.vendor_id = po.vendor_id
    LEFT JOIN items   i ON i.item_id   = po.item_id
"""

# `FROZEN_STATUSES` (Cancelled / Delivered) is defined in schemas.py beside
# `OrderOut.locked`, which reads it; it is imported above so `orders.queries.
# FROZEN_STATUSES` keeps working for the routes, the legacy namespace and tests.


class OrderLocked(Exception):
    """A line mutation was attempted on an order in a frozen status."""

    def __init__(self, status: str):
        super().__init__(status)
        self.status = status


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


def get_order(
    db: Session, *, po_id: int, workspace_id: int, for_update: bool = False
) -> dict | None:
    """`for_update=True` (§L Q511/Q512) locks the `purchase_orders` row for
    the rest of the caller's transaction, so a concurrent PATCH serialises
    instead of racing on the read-then-write field-version check. Only
    `patch_order` passes it; every other caller here is a plain read."""
    row = db.execute(
        text(
            f"SELECT {_ORDER_COLS} {_ORDER_FROM} WHERE po.po_id = :o"
            f" AND {_ORDER_WORKSPACE} {'FOR UPDATE OF po' if for_update else ''}"
        ),
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
            WHERE i.item_id = :i AND p.workspace_id = :w AND NOT i.deleted
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
            WHERE i.item_id = :i AND p.workspace_id = :w AND NOT i.deleted
            """
        ),
        {"i": item_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def _vendor_in_workspace(db: Session, *, vendor_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM vendors WHERE vendor_id = :v AND workspace_id = :w"),
        {"v": vendor_id, "w": workspace_id},
    ).first() is not None


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first() is not None


def _category_exists(db: Session, category_key: str) -> bool:
    """Any row of the `order_category` lookup (0031), archived or not: the FK the
    column carries accepts an archived key, and this only turns what would be a
    raw FK-violation 500 into a clean refusal, it does not add a new rule."""
    return db.execute(
        text("SELECT 1 FROM order_category WHERE category_key = :c"),
        {"c": category_key},
    ).first() is not None


def create_order(
    db: Session,
    *,
    workspace_id: int,
    payload: CreateOrderIn,
    actor_id: int,
) -> tuple[str, dict | None]:
    """('OK', order) | ('ITEM_NOT_FOUND', None) | ('VENDOR_NOT_FOUND', None) |
    ('UNKNOWN_CATEGORY', None) | ('PROJECT_NOT_FOUND', None)."""
    if not _vendor_in_workspace(db, vendor_id=payload.vendor_id, workspace_id=workspace_id):
        return "VENDOR_NOT_FOUND", None
    if not _category_exists(db, payload.category):
        return "UNKNOWN_CATEGORY", None
    # An explicit project must be this workspace's; the item-derived one already is
    # (it is resolved through the item's own workspace join below).
    if payload.project_id is not None and not _project_in_workspace(
        db, project_id=payload.project_id, workspace_id=workspace_id
    ):
        return "PROJECT_NOT_FOUND", None

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
) -> tuple[str, dict | None]:
    """Returns (code, data). Codes: 'OK' | 'NOT_FOUND' | 'FIELD_CONFLICT' (§L
    Q511/Q512 — `data` is the conflicts dict, not the order, in that case) |
    'ORDER_LOCKED' (`data` is {status, blocked_fields} — see `FROZEN_STATUSES`) |
    'VENDOR_NOT_FOUND' (`data` is {vendor_id}: unknown, or another workspace's —
    the same rule `create_order` applies) | 'UNKNOWN_CATEGORY' (`data` is
    {category})."""
    current = get_order(db, po_id=po_id, workspace_id=workspace_id, for_update=True)
    if current is None:
        return "NOT_FOUND", None

    fields: dict[str, Any] = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in _PATCHABLE
    }
    # Once an order has lines, `total_amount` has a second writer —
    # `_recompute_total_amount()`, called from every line mutation — that
    # doesn't (can't: it isn't submitting an "expected" prior value, it's
    # deriving one) go through `check_field_conflicts()`. Two writers for
    # one field defeats §L's guarantee regardless of which one loses, so
    # once lines exist this header PATCH stops being the field's other
    # writer: it's dropped from `fields` like an unrecognized key, the same
    # way `_LINE_PATCHABLE` already drops `line_number`. A header-only order
    # (no lines) is unaffected — `total_amount` stays directly patchable.
    expected_versions = payload.expected_versions
    if current["lines"]:
        fields.pop("total_amount", None)
        # `total_amount`'s version keeps moving via the rollup (above) even
        # though this PATCH no longer writes it — leaving a stale entry for
        # it in `expected_versions` (a batch call naming {status,
        # total_amount} together, the documented "read from a prior GET's
        # field_versions" pattern applied to both) would still raise a
        # spurious FIELD_CONFLICT on a field the write no longer touches,
        # blocking the unrelated field it was never meant to gate. Every
        # *other* unrelated key in `expected_versions` still conflicts by
        # design — `test_cutlist_conflict_on_unrelated_expected_version_key_does_not_500`
        # pins that a bogus key is treated as a real conflict, not silently
        # dropped — so only `total_amount` is carved out here, not a
        # general filter to `fields`.
        if expected_versions and "total_amount" in expected_versions:
            expected_versions = {
                k: v for k, v in expected_versions.items() if k != "total_amount"
            }
    # A frozen order (`FROZEN_STATUSES`) accepts a header PATCH that changes
    # `status` and nothing else — status is the deliberate way back in, so a
    # mistaken cancel/delivery can be reopened (audited and versioned like any
    # header write). Anything else is refused whole, not trimmed: a caller
    # asking for {status, notes} gets a 409 and can send two calls, rather than
    # a 200 that quietly dropped half the request.
    if current["status"] in FROZEN_STATUSES:
        blocked = sorted(set(fields) - {"status"})
        if blocked:
            return "ORDER_LOCKED", {"status": current["status"], "blocked_fields": blocked}
    # References are checked before anything is written or versioned. `vendor_id`
    # went straight into the UPDATE unchecked: another workspace's vendor was
    # accepted, and the response then carried that workspace's supplier name.
    if "vendor_id" in fields and not _vendor_in_workspace(
        db, vendor_id=fields["vendor_id"], workspace_id=workspace_id
    ):
        return "VENDOR_NOT_FOUND", {"vendor_id": fields["vendor_id"]}
    if "category" in fields and not _category_exists(db, fields["category"]):
        return "UNKNOWN_CATEGORY", {"category": fields["category"]}
    if not fields:
        return "OK", current

    conflicts = check_field_conflicts(
        current.get("field_versions"), expected_versions
    )
    if conflicts:
        for field, info in conflicts.items():
            info["current_value"] = conflict_safe_value(current.get(field))
        return "FIELD_CONFLICT", conflicts

    new_versions = bump_field_versions(current.get("field_versions"), list(fields))
    sets, params = [], {"o": po_id, "fv": json.dumps(new_versions)}
    for i, (col, val) in enumerate(fields.items()):
        key = f"v{i}"
        if col == "attributes":
            sets.append(f"{col} = CAST(:{key} AS jsonb)")
            params[key] = json.dumps(val or {})
        else:
            sets.append(f"{col} = :{key}")
            params[key] = val
    db.execute(
        text(f"UPDATE purchase_orders SET {', '.join(sets)},"
             " field_versions = CAST(:fv AS jsonb), updated_at = now()"
             " WHERE po_id = :o"),
        params,
    )
    db.flush()

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.update", target=str(po_id),
        payload={"fields": sorted(fields), "po_number": current["po_number"]},
    )
    return "OK", get_order(db, po_id=po_id, workspace_id=workspace_id)


def cancel_order(
    db: Session, *, po_id: int, workspace_id: int, actor_id: int
) -> str:
    """Soft-cancel, matching #4's batch rule. 'OK' | 'NOT_FOUND' | 'ALREADY_CANCELLED'.

    Cancelling is a status change like any header PATCH of `status`, and it is
    one of the two ways into a frozen state, so it takes the same row lock and
    bumps `field_versions["status"]`: without that, a panel that loaded the
    order before it was cancelled could PATCH `status` back with a still-valid
    `expected_versions` and silently undo the cancel, and two concurrent
    cancels could both pass the ALREADY_CANCELLED check."""
    current = get_order(db, po_id=po_id, workspace_id=workspace_id, for_update=True)
    if current is None:
        return "NOT_FOUND"
    if current["status"] == "Cancelled":
        return "ALREADY_CANCELLED"
    new_versions = bump_field_versions(current.get("field_versions"), ["status"])
    db.execute(
        text("UPDATE purchase_orders SET status = 'Cancelled', updated_at = now(),"
             " field_versions = CAST(:fv AS jsonb) WHERE po_id = :o"),
        {"o": po_id, "fv": json.dumps(new_versions)},
    )
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.cancel", target=str(po_id),
        payload={"po_number": current["po_number"], "from_status": current["status"]},
    )
    return "OK"


def _lock_order_for_update(db: Session, *, po_id: int, workspace_id: int) -> bool:
    """Locks the purchase_orders row for the rest of this transaction, so a
    concurrent add_line() on the same order serializes instead of racing on
    the (po_id, line_number) unique constraint (0002).

    Also the single choke point for "may this order's lines change?": it
    raises `OrderLocked` for a frozen status (`FROZEN_STATUSES`), reading the
    status under the same lock so a concurrent status change can't slip an
    edit past the check. Every line mutation goes through here."""
    row = db.execute(
        text(
            f"SELECT po.status FROM purchase_orders po"
            f" WHERE po.po_id = :o AND {_ORDER_WORKSPACE} FOR UPDATE OF po"
        ),
        {"o": po_id, "w": workspace_id},
    ).first()
    if row is None:
        return False
    if row[0] in FROZEN_STATUSES:
        raise OrderLocked(row[0])
    return True


def _recompute_total_amount(db: Session, *, po_id: int) -> None:
    """`purchase_orders.total_amount` (and the `gst_amount` / `grand_total`
    columns generated from it) predate `po_line_items` and were never wired
    to it — a header-only order (the original per-item Create Order flow)
    still sets `total_amount` directly and never calls this. A PO with real
    lines (every order `generate_orders` creates, and now anything edited
    through this module's line endpoints) should have its Total reflect
    them, so every line mutation keeps it in sync rather than leaving it
    frozen at whatever `create_order` set (typically nothing, i.e. 0.00).
    `quantity` / `unit_cost` are left alone — they're singular fields with
    no coherent value across multiple lines, unlike a summed total.

    Bumps `field_versions["total_amount"]` too — a plain `UPDATE` bypassing
    it would let a stale `PATCH .../orders/{po_id}` (read before this ran,
    `expected_versions: {"total_amount": <old>}`) silently clobber the
    freshly-summed total with no `FIELD_CONFLICT`, defeating §L for this
    one field. Caller already holds the row lock via
    `_lock_order_for_update`, so this read-then-write can't itself race."""
    row = db.execute(
        text(
            "SELECT total_amount, field_versions,"
            " (SELECT COALESCE(SUM(line_total), 0) FROM po_line_items WHERE po_id = :o) AS new_total"
            " FROM purchase_orders WHERE po_id = :o"
        ),
        {"o": po_id},
    ).mappings().one()
    if row["new_total"] == row["total_amount"]:
        return
    new_versions = bump_field_versions(row["field_versions"], ["total_amount"])
    db.execute(
        text(
            "UPDATE purchase_orders SET total_amount = :t,"
            " field_versions = CAST(:fv AS jsonb), updated_at = now() WHERE po_id = :o"
        ),
        {"o": po_id, "t": row["new_total"], "fv": json.dumps(new_versions)},
    )


def add_line(
    db: Session, *, po_id: int, workspace_id: int,
    payload: CreateOrderLineIn, actor_id: int,
) -> dict | None:
    """Appends a line. None = order not found. Raises `OrderLocked` on a frozen
    order (`FROZEN_STATUSES`) — the routes turn that into a 409; a caller
    outside them (`estimating.generate_orders` only ever adds to orders it has
    just created as Draft) must not assume every order accepts lines."""
    if not _lock_order_for_update(db, po_id=po_id, workspace_id=workspace_id):
        return None
    if payload.material_table is not None or payload.material_id is not None:
        assert_material_in_workspace(
            db, table=payload.material_table, material_id=payload.material_id,
            workspace_id=workspace_id,
        )
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
    _recompute_total_amount(db, po_id=po_id)
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.line_add", target=str(po_id),
        payload={"line_number": next_no, "description": payload.item_description},
    )
    return get_order(db, po_id=po_id, workspace_id=workspace_id)


_LINE_PATCHABLE = frozenset({"item_description", "sku", "quantity", "unit", "unit_price"})


def patch_line(
    db: Session, *, po_id: int, line_id: int, workspace_id: int,
    payload: PatchOrderLineIn, actor_id: int,
) -> dict | None:
    """Edits a generated (or manually added) line — quantity/price/sku the
    live-catalog resolution at generation time got wrong, or the PM wants to
    adjust before sending to the supplier. Returns None for NOT_FOUND (no
    such line on this order, in this workspace)."""
    if not _lock_order_for_update(db, po_id=po_id, workspace_id=workspace_id):
        return None
    fields = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if k in _LINE_PATCHABLE
    }
    if not fields:
        exists = db.execute(
            text("SELECT 1 FROM po_line_items WHERE line_id = :l AND po_id = :o"),
            {"l": line_id, "o": po_id},
        ).first()
        if exists is None:
            return None
        return get_order(db, po_id=po_id, workspace_id=workspace_id)
    sets, params = [], {"l": line_id, "o": po_id}
    for i, (col, val) in enumerate(fields.items()):
        key = f"v{i}"
        sets.append(f"{col} = :{key}")
        params[key] = val
    result = db.execute(
        text(f"UPDATE po_line_items SET {', '.join(sets)}"
             " WHERE line_id = :l AND po_id = :o"),
        params,
    )
    if result.rowcount == 0:
        return None
    _recompute_total_amount(db, po_id=po_id)
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.line_update", target=str(po_id),
        payload={"line_id": line_id, "fields": sorted(fields)},
    )
    return get_order(db, po_id=po_id, workspace_id=workspace_id)


def remove_line(
    db: Session, *, po_id: int, line_id: int, workspace_id: int, actor_id: int,
) -> dict | None:
    """Removes one line — e.g. a consolidated material the PM decided not to
    order through this PO after all. Returns None for NOT_FOUND."""
    if not _lock_order_for_update(db, po_id=po_id, workspace_id=workspace_id):
        return None
    result = db.execute(
        text("DELETE FROM po_line_items WHERE line_id = :l AND po_id = :o"),
        {"l": line_id, "o": po_id},
    )
    if result.rowcount == 0:
        return None
    _recompute_total_amount(db, po_id=po_id)
    db.flush()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="order.line_remove", target=str(po_id),
        payload={"line_id": line_id},
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

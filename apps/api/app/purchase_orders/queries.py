"""PO documents (migration 0059): the old PO screen, a header over orders of one supplier.

An *order* (`purchase_orders`, Q553) is one ordered item with its own requester, project, location,
cost, arrival and budget; a *PO document* (`po_document`) groups orders of **one supplier** onto one
numbered sheet that is printed, mailed and invoiced against. The orders stay exactly as they are: this
module only links them (`purchase_orders.po_document_id`), sets their `date_ordered` (an order put on a
PO is ordered), and reads them back as the PO's lines.

Rules (asked first, October 2026): any **open** order (not Delivered, Cancelled or Rejected) of the PO's
supplier that is on no PO yet may be put on one; the PO number is a plain running number; the delivery
charge is an ordinary "Delivery Fee" order of the same supplier (`po_document.delivery_order_id`).
Every function returns `(code, data)`; a code other than `"OK"` means nothing was written.
"""
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..concurrency import bump_field_versions
from ..orders import queries as oq
from ..orders.schemas import CreateOrderIn, PatchOrderIn
from .schemas import CreatePoIn, InvoiceIn, PatchInvoiceIn, PatchPoIn

_OPEN_STATUSES = ("Delivered", "Cancelled", "Rejected")
_OUT_OF_TOTALS = ("Cancelled", "Rejected")

_HEADER_SQL = """
    SELECT pd.po_document_id, pd.po_no, pd.status, pd.vendor_id, v.name AS vendor_name,
           v.address AS vendor_address, pd.reference_no, pd.ordered_by_id,
           ob.full_name AS ordered_by_name, pd.date_ordered, pd.date_required, pd.date_due,
           pd.memo, pd.deliver_to, pd.delivery_order_id, pd.created_at, pd.updated_at
      FROM po_document pd
      JOIN vendors v ON v.vendor_id = pd.vendor_id
      LEFT JOIN app_user ob ON ob.id = pd.ordered_by_id
     WHERE pd.po_document_id = :d AND pd.workspace_id = :w
"""


# ── reads ───────────────────────────────────────────────────────────────────────────────────────

def list_documents(db: Session, *, workspace_id: int, vendor_id: int | None = None) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT pd.po_document_id, pd.po_no, pd.status, pd.vendor_id, v.name AS vendor_name,
                   pd.reference_no, pd.date_ordered, pd.created_at,
                   (SELECT count(*) FROM purchase_orders po
                     WHERE po.po_document_id = pd.po_document_id) AS line_count
              FROM po_document pd JOIN vendors v ON v.vendor_id = pd.vendor_id
             WHERE pd.workspace_id = :w AND (CAST(:v AS bigint) IS NULL OR pd.vendor_id = :v)
             ORDER BY pd.po_document_id DESC
            """
        ),
        {"w": workspace_id, "v": vendor_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_document(db: Session, *, doc_id: int, workspace_id: int, for_update: bool = False) -> dict | None:
    """The PO with its lines, invoices and totals, or None (also for another workspace's)."""
    head = db.execute(
        text(_HEADER_SQL + (" FOR UPDATE OF pd" if for_update else "")),
        {"d": doc_id, "w": workspace_id},
    ).mappings().first()
    if head is None:
        return None
    doc = dict(head)
    invoices = db.execute(
        text(
            """
            SELECT inv.invoice_id, inv.order_id, inv.invoice_number, inv.invoiced_date, inv.qty,
                   inv.total_inc, inv.notes, inv.delivery_doc
              FROM po_invoice inv WHERE inv.po_document_id = :d ORDER BY inv.invoice_id
            """
        ),
        {"d": doc_id},
    ).mappings().all()
    rows = db.execute(
        text(
            """
            SELECT po.po_id AS order_id, po.po_number, po.status, po.description, po.product_code,
                   po.quantity, po.unit_of_measure, po.unit_cost, po.total_amount, po.gst_amount,
                   po.grand_total, ru.full_name AS requester_name, po.project_name, po.location,
                   i.num AS item_number, po.arrived_date,
                   EXISTS (SELECT 1 FROM po_attachments pa WHERE pa.po_id = po.po_id) AS has_attachment,
                   (po.po_id = :dl) AS is_delivery
              FROM purchase_orders po
              LEFT JOIN app_user ru ON ru.id = po.requester_id
              LEFT JOIN items i ON i.item_id = po.item_id
             WHERE po.po_document_id = :d
             ORDER BY (po.po_id = :dl), po.po_id
            """
        ),
        {"d": doc_id, "dl": doc["delivery_order_id"] or 0},
    ).mappings().all()
    by_order: dict[int, list[dict]] = {}
    for inv in invoices:
        by_order.setdefault(inv["order_id"], []).append(dict(inv))
    lines, line_no = [], {}
    total_ex = gst = total_inc = Decimal(0)
    delivery_charge = None
    for n, r in enumerate(rows, start=1):
        line = dict(r)
        line["line_no"] = n
        line_no[line["order_id"]] = n
        # invoiced: any invoice row without a quantity, or invoiced quantities adding up to the order's
        invs = by_order.get(line["order_id"], [])
        qty_total = sum((x["qty"] for x in invs if x["qty"] is not None), Decimal(0))
        line["invoiced"] = bool(invs) and (
            any(x["qty"] is None for x in invs)
            or line["quantity"] is None
            or qty_total >= line["quantity"]
        )
        lines.append(line)
        if line["status"] not in _OUT_OF_TOTALS:
            total_ex += line["total_amount"] or 0
            gst += line["gst_amount"] or 0
            total_inc += line["grand_total"] or 0
        if line["is_delivery"] and line["status"] not in _OUT_OF_TOTALS:
            delivery_charge = line["total_amount"]
    # the invoice table shows each row's item
    by_id = {line["order_id"]: line for line in lines}
    inv_out = []
    for inv in invoices:
        o = by_id.get(inv["order_id"], {})
        inv_out.append({**inv, "line_no": line_no.get(inv["order_id"]),
                        "description": o.get("description"), "product_code": o.get("product_code")})
    doc.update(
        lines=lines, invoices=inv_out, delivery_charge=delivery_charge,
        totals={"total_ex": total_ex, "gst": gst, "total_inc": total_inc},
    )
    return doc


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────

def _lock_orders(db: Session, order_ids: list[int], workspace_id: int) -> list[dict] | None:
    """The named orders (this workspace's), locked, or None if any is missing or another workspace's."""
    rows = db.execute(
        text(
            """
            SELECT po.po_id, po.po_number, po.vendor_id, po.status, po.po_document_id, po.date_ordered,
                   po.required_date, po.field_versions, po.date_ordered_from_po
              FROM purchase_orders po
              JOIN vendors v ON v.vendor_id = po.vendor_id AND v.workspace_id = :w
             WHERE po.po_id = ANY(:ids)
             ORDER BY po.po_id FOR UPDATE OF po
            """
        ),
        {"w": workspace_id, "ids": order_ids},
    ).mappings().all()
    if len(rows) != len(order_ids):
        return None
    return [dict(r) for r in rows]


def _user_in_workspace(db: Session, user_id: int, workspace_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM app_user WHERE id = :u AND workspace_id = :w"),
        {"u": user_id, "w": workspace_id},
    ).first() is not None


def _check_orders(rows: list[dict], vendor_id: int | None) -> tuple[str, dict] | None:
    """The refusal for a set of orders that cannot go on a PO of `vendor_id`, or None."""
    if any(r["po_document_id"] is not None for r in rows):
        return "ORDER_ALREADY_ON_PO", {"order_ids": [r["po_id"] for r in rows if r["po_document_id"] is not None]}
    if any(r["status"] in _OPEN_STATUSES for r in rows):
        return "ORDER_NOT_OPEN", {"order_ids": [r["po_id"] for r in rows if r["status"] in _OPEN_STATUSES]}
    wanted = vendor_id if vendor_id is not None else rows[0]["vendor_id"]
    if any(r["vendor_id"] != wanted for r in rows):
        return "SUPPLIER_MISMATCH", {"order_ids": [r["po_id"] for r in rows if r["vendor_id"] != wanted]}
    return None


def _attach(db: Session, rows: list[dict], doc_id: int, date_ordered: date) -> None:
    """Put the orders on the PO; an order with no Date ordered gets the PO's (it is ordered now), and
    is flagged so that leaving the PO takes that date away again (and only that one)."""
    for r in rows:
        versions = r["field_versions"]
        from_po = r["date_ordered"] is None
        if from_po:
            versions = bump_field_versions(versions, ["date_ordered"])
        db.execute(
            text(
                """
                UPDATE purchase_orders
                   SET po_document_id = :d, date_ordered = COALESCE(date_ordered, :dt),
                       date_ordered_from_po = :fp,
                       field_versions = CAST(:fv AS jsonb), updated_at = now()
                 WHERE po_id = :o
                """
            ),
            {"d": doc_id, "dt": date_ordered, "o": r["po_id"], "fv": _json(versions), "fp": from_po},
        )


def _json(v: Any) -> str:
    import json
    return json.dumps(v or {})


def _detach(db: Session, order_ids: list[int]) -> None:
    """Take orders off the PO. A Date ordered the PO gave an order is taken away again (and versioned,
    so a stale order panel gets a conflict), unless the order is already Cancelled / Delivered: its
    date is then history and stays. The rows are locked first, in id order."""
    rows = db.execute(
        text("SELECT po_id, status, date_ordered_from_po, field_versions FROM purchase_orders"
             " WHERE po_id = ANY(:ids) ORDER BY po_id FOR UPDATE"),
        {"ids": order_ids},
    ).mappings().all()
    for r in rows:
        clear = r["date_ordered_from_po"] and r["status"] not in ("Cancelled", "Delivered")
        versions = bump_field_versions(r["field_versions"], ["date_ordered"]) if clear else r["field_versions"]
        db.execute(
            text(
                """
                UPDATE purchase_orders
                   SET po_document_id = NULL, date_ordered_from_po = false,
                       date_ordered = CASE WHEN :clear THEN NULL ELSE date_ordered END,
                       field_versions = CAST(:fv AS jsonb), updated_at = now()
                 WHERE po_id = :o
                """
            ),
            {"o": r["po_id"], "clear": clear, "fv": _json(versions)},
        )


def _touch(db: Session, doc_id: int) -> None:
    db.execute(text("UPDATE po_document SET updated_at = now() WHERE po_document_id = :d"), {"d": doc_id})


def _open_doc(db: Session, doc_id: int, workspace_id: int) -> tuple[str, dict | None]:
    """The locked header of an Open PO, or the refusal."""
    doc = get_document(db, doc_id=doc_id, workspace_id=workspace_id, for_update=True)
    if doc is None:
        return "NOT_FOUND", None
    if doc["status"] != "Open":
        return "PO_CANCELLED", {"po_no": doc["po_no"]}
    return "OK", doc


# ── writes: the PO ──────────────────────────────────────────────────────────────────────────────

def create_document(
    db: Session, *, workspace_id: int, actor_id: int, payload: CreatePoIn
) -> tuple[str, dict | None]:
    rows = _lock_orders(db, payload.order_ids, workspace_id)
    if rows is None:
        return "ORDER_NOT_FOUND", {"order_ids": payload.order_ids}
    refusal = _check_orders(rows, None)
    if refusal:
        return refusal
    if payload.ordered_by_id is not None and not _user_in_workspace(db, payload.ordered_by_id, workspace_id):
        return "USER_NOT_FOUND", {"user_id": payload.ordered_by_id}
    required = payload.date_required or min(
        (r["required_date"] for r in rows if r["required_date"] is not None), default=None
    )
    deliver_to = payload.deliver_to
    if deliver_to is None:  # the last address used in this workspace
        deliver_to = db.execute(
            text("SELECT deliver_to FROM po_document WHERE workspace_id = :w AND deliver_to IS NOT NULL"
                 " ORDER BY po_document_id DESC LIMIT 1"),
            {"w": workspace_id},
        ).scalar()
    doc_id, po_no, date_ordered = db.execute(
        text(
            """
            INSERT INTO po_document (workspace_id, vendor_id, reference_no, ordered_by_id, date_required,
                                     date_due, memo, deliver_to, created_by)
            VALUES (:w, :v, :ref, :ob, :req, :due, :memo, :to, :u)
            RETURNING po_document_id, po_no, date_ordered
            """
        ),
        {"w": workspace_id, "v": rows[0]["vendor_id"], "ref": payload.reference_no,
         "ob": payload.ordered_by_id or actor_id, "req": required,
         "due": payload.date_due or required, "memo": payload.memo, "to": deliver_to, "u": actor_id},
    ).one()
    _attach(db, rows, doc_id, date_ordered)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.create", target=f"po:{doc_id}",
        payload={"po_no": po_no, "orders": [r["po_number"] for r in rows]},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


_PATCHABLE = ("reference_no", "ordered_by_id", "date_ordered", "date_required", "date_due", "memo", "deliver_to")


def patch_document(
    db: Session, *, doc_id: int, workspace_id: int, actor_id: int, payload: PatchPoIn
) -> tuple[str, dict | None]:
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    fields = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if k in _PATCHABLE}
    if fields.get("ordered_by_id") is not None and not _user_in_workspace(db, fields["ordered_by_id"], workspace_id):
        return "USER_NOT_FOUND", {"user_id": fields["ordered_by_id"]}
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        db.execute(
            text(f"UPDATE po_document SET {sets}, updated_at = now() WHERE po_document_id = :d"),
            {**fields, "d": doc_id},
        )
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id, event="po.update", target=f"po:{doc_id}",
            payload={"po_no": doc["po_no"], "fields": sorted(fields)},
        )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


def add_orders(
    db: Session, *, doc_id: int, workspace_id: int, actor_id: int, order_ids: list[int]
) -> tuple[str, dict | None]:
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    rows = _lock_orders(db, order_ids, workspace_id)
    if rows is None:
        return "ORDER_NOT_FOUND", {"order_ids": order_ids}
    refusal = _check_orders(rows, doc["vendor_id"])
    if refusal:
        return refusal
    _attach(db, rows, doc_id, doc["date_ordered"])
    _touch(db, doc_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.orders.add", target=f"po:{doc_id}",
        payload={"po_no": doc["po_no"], "orders": [r["po_number"] for r in rows]},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


def remove_order(
    db: Session, *, doc_id: int, workspace_id: int, actor_id: int, order_id: int
) -> tuple[str, dict | None]:
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    line = next((x for x in doc["lines"] if x["order_id"] == order_id), None)
    if line is None:
        return "ORDER_NOT_ON_PO", {"order_id": order_id}
    if line["is_delivery"]:
        return "IS_DELIVERY_ORDER", {"order_id": order_id}
    if any(i["order_id"] == order_id for i in doc["invoices"]):
        return "ORDER_HAS_INVOICES", {"order_id": order_id}
    _detach(db, [order_id])
    _touch(db, doc_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.orders.remove", target=f"po:{doc_id}",
        payload={"po_no": doc["po_no"], "orders": [line["po_number"]]},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


def cancel_document(
    db: Session, *, doc_id: int, workspace_id: int, actor_id: int, can_decide: bool
) -> tuple[str, dict | None]:
    """Cancel the PO: its orders come off it (and out of "ordered" if the PO ordered them); the
    Delivery Fee order, which only existed for this PO, is cancelled. `can_decide` is the
    `orderbook:approve` grant: cancelling a decided Delivery Fee order needs it, like any order."""
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    if doc["invoices"]:
        return "PO_HAS_INVOICES", {"po_no": doc["po_no"], "invoices": len(doc["invoices"])}
    delivery_id = doc["delivery_order_id"]
    if delivery_id is not None:
        result = oq.cancel_order(db, po_id=delivery_id, workspace_id=workspace_id,
                                 actor_id=actor_id, can_decide=can_decide)
        if result == "DECISION_FORBIDDEN":
            return "DECISION_FORBIDDEN", {"order_id": delivery_id}
    ids = [x["order_id"] for x in doc["lines"]]
    if ids:
        _detach(db, ids)
    db.execute(
        text("UPDATE po_document SET status = 'Cancelled', delivery_order_id = NULL, updated_at = now()"
             " WHERE po_document_id = :d"),
        {"d": doc_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.cancel", target=f"po:{doc_id}",
        payload={"po_no": doc["po_no"], "orders": [x["po_number"] for x in doc["lines"]]},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


# ── writes: the delivery charge ─────────────────────────────────────────────────────────────────

def set_delivery(
    db: Session, *, doc_id: int, workspace_id: int, actor_id: int, amount: Decimal
) -> tuple[str, dict | None]:
    """Add Delivery: the charge is an ordinary "Delivery Fee" order of this supplier, put on the PO."""
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    old_fee = next((x for x in doc["lines"] if x["is_delivery"]), None)
    if old_fee is not None and old_fee["status"] in _OUT_OF_TOTALS:
        # cancelled in the Orderbook: it is no charge any more, so take it off and make a new one
        _detach(db, [old_fee["order_id"]])
        db.execute(text("UPDATE po_document SET delivery_order_id = NULL WHERE po_document_id = :d"), {"d": doc_id})
        doc["delivery_order_id"] = None
    if doc["delivery_order_id"] is not None:
        code, data = oq.patch_order(
            db, po_id=doc["delivery_order_id"], workspace_id=workspace_id, actor_id=actor_id,
            payload=PatchOrderIn(unit_cost=amount, total_amount=amount),
        )
        if code != "OK":
            return code, data
    else:
        code, order = oq.create_order(
            db, workspace_id=workspace_id, actor_id=actor_id,
            payload=CreateOrderIn(
                vendor_id=doc["vendor_id"], description="Delivery Fee", category="Other",
                quantity=Decimal(1), unit_of_measure="ea", unit_cost=amount, total_amount=amount,
            ),
        )
        if code != "OK":
            return code, order
        rows = _lock_orders(db, [order["po_id"]], workspace_id)
        _attach(db, rows, doc_id, doc["date_ordered"])
        db.execute(
            text("UPDATE po_document SET delivery_order_id = :o WHERE po_document_id = :d"),
            {"o": order["po_id"], "d": doc_id},
        )
    _touch(db, doc_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.delivery.set", target=f"po:{doc_id}",
        payload={"po_no": doc["po_no"], "amount": str(amount)},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


def remove_delivery(
    db: Session, *, doc_id: int, workspace_id: int, actor_id: int, can_decide: bool
) -> tuple[str, dict | None]:
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    delivery_id = doc["delivery_order_id"]
    if delivery_id is None:
        return "NO_DELIVERY", {"po_no": doc["po_no"]}
    if any(i["order_id"] == delivery_id for i in doc["invoices"]):
        return "ORDER_HAS_INVOICES", {"order_id": delivery_id}
    result = oq.cancel_order(db, po_id=delivery_id, workspace_id=workspace_id,
                             actor_id=actor_id, can_decide=can_decide)
    if result == "DECISION_FORBIDDEN":
        return "DECISION_FORBIDDEN", {"order_id": delivery_id}
    _detach(db, [delivery_id])
    db.execute(text("UPDATE po_document SET delivery_order_id = NULL, updated_at = now()"
                    " WHERE po_document_id = :d"), {"d": doc_id})
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.delivery.remove", target=f"po:{doc_id}",
        payload={"po_no": doc["po_no"]},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


# ── writes: invoices ────────────────────────────────────────────────────────────────────────────

def add_invoice(
    db: Session, *, doc_id: int, workspace_id: int, actor_id: int, payload: InvoiceIn
) -> tuple[str, dict | None]:
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    if not any(x["order_id"] == payload.order_id for x in doc["lines"]):
        return "ORDER_NOT_ON_PO", {"order_id": payload.order_id}
    invoice_id = db.execute(
        text(
            """
            INSERT INTO po_invoice (po_document_id, order_id, invoice_number, invoiced_date, qty, total_inc,
                                    notes, delivery_doc, created_by)
            VALUES (:d, :o, :n, :dt, :q, :t, :notes, :dd, :u) RETURNING invoice_id
            """
        ),
        {"d": doc_id, "o": payload.order_id, "n": payload.invoice_number, "dt": payload.invoiced_date,
         "q": payload.qty, "t": payload.total_inc, "notes": payload.notes, "dd": payload.delivery_doc,
         "u": actor_id},
    ).scalar_one()
    _touch(db, doc_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.invoice.add", target=f"po:{doc_id}",
        payload={"po_no": doc["po_no"], "invoice_id": invoice_id, "invoice_number": payload.invoice_number},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


def patch_invoice(
    db: Session, *, doc_id: int, invoice_id: int, workspace_id: int, actor_id: int, payload: PatchInvoiceIn
) -> tuple[str, dict | None]:
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    if not any(i["invoice_id"] == invoice_id for i in doc["invoices"]):
        return "INVOICE_NOT_FOUND", {"invoice_id": invoice_id}
    fields = payload.model_dump(exclude_unset=True)
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        db.execute(text(f"UPDATE po_invoice SET {sets} WHERE invoice_id = :i"), {**fields, "i": invoice_id})
        _touch(db, doc_id)
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id, event="po.invoice.update", target=f"po:{doc_id}",
            payload={"po_no": doc["po_no"], "invoice_id": invoice_id, "fields": sorted(fields)},
        )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


def delete_invoice(
    db: Session, *, doc_id: int, invoice_id: int, workspace_id: int, actor_id: int
) -> tuple[str, dict | None]:
    code, doc = _open_doc(db, doc_id, workspace_id)
    if code != "OK":
        return code, doc
    if not any(i["invoice_id"] == invoice_id for i in doc["invoices"]):
        return "INVOICE_NOT_FOUND", {"invoice_id": invoice_id}
    db.execute(text("DELETE FROM po_invoice WHERE invoice_id = :i"), {"i": invoice_id})
    _touch(db, doc_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id, event="po.invoice.delete", target=f"po:{doc_id}",
        payload={"po_no": doc["po_no"], "invoice_id": invoice_id},
    )
    return "OK", get_document(db, doc_id=doc_id, workspace_id=workspace_id)


def list_staff(db: Session, *, workspace_id: int) -> list[dict]:
    """Active people of the workspace with their email: the PO panel's Ordered by list and Cc ticks.
    Reached only through the Orderbook-gated route, so emails are not on the open team list."""
    rows = db.execute(
        text("SELECT id, full_name, email FROM app_user WHERE workspace_id = :w AND is_active = true"
             " ORDER BY full_name"),
        {"w": workspace_id},
    ).mappings().all()
    return [dict(r) for r in rows]


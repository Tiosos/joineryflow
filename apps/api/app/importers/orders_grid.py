"""Pilot-data importer for FileMaker's orders grid export (E3, second slice).

One workbook, one sheet, one project: a row per ordered item. Run it from the api container (or any venv
with `DATABASE_URL` set):

    python -m app.importers.orders_grid FILE.xlsx --workspace-slug SLUG --actor-email EMAIL \\
        --project-code 2325 [--project-name "..."]           # a dry run: validates, writes nothing
    python -m app.importers.orders_grid ... --commit          # the same, then keeps it

Settled with the user (2026-10-15):

- A row is **one order** (`purchase_orders`). `OrderNumber` is kept as `order_number` on every row that
  has it; **no PO document is built** (65 numbers cover 175 rows, two of them mix suppliers).
- Status: `_Priority = ORDERED` with a `Date_Arrived` is `Delivered`, without one `Approved`;
  `ON HOLD` = `Hold`, `NEXT` = `Next`, `QUOTE` = `Quote`, `URGENT` and a blank = `Pending`. Priority is
  `High` for `URGENT`, otherwise `Medium`. (The 17 rows with `TAG_Active = 0` are the ones with no order
  number and no `Date_Ordered`: requests not yet ordered.)
- `_Cost_Sub` is the **line total, ex GST**: `total_amount` = it, `unit_cost` = it / `QTY`.
- A missing supplier is **created** by its exact name (case-insensitive match first); a row with no
  supplier is skipped and listed. The requester is only a first name (`Bill`), so it is kept in the notes
  (`Requested by: Bill`) and the order is raised by the importing user.

Departures I chose and the report counts (change them by saying so):

- Every order gets category `Other` (the file has none; the Delivery Fee order of a PO uses it too).
- `SumTotla` (stock control, qty received) becomes **one delivery-log row** (`order_delivery`) dated
  `Date_Arrived`, only on a Delivered order and only when it is above zero.
- `Doc_PDF` holds FileMaker container paths, not file bytes: no file is imported (counted).
  `CutlistNumber` is kept as text on the order (`cutlist_no`); no item link is made.
  The staff photo and `_Tag_Select` columns are not imported.
- No cost centre is set, so nothing is committed or spent against a budget.

Re-running is safe: each row gets a key (a hash of its values plus the count of identical rows before it,
kept in `attributes.fm_import`) and a row whose key already exists is skipped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit

REQUIRED_HEADERS = (
    "OrderNumber", "_RequestedByName", "QTY", "_BoardGroup", "Location", "Doc_PDF", "_ProjectName",
    "Supplier", "T07b_ORD_StockControl::SumTotla", "_Cost_Sub", "_PCode", "Date_Required", "Date_Ordered",
    "Date_Due", "Date_Arrived", "TAG_Active", "_Priority", "CutlistNumber",
)

CATEGORY = "Other"
STATUS_NOT_ORDERED = {"ON HOLD": "Hold", "NEXT": "Next", "QUOTE": "Quote", "URGENT": "Pending"}
MAX_LEN = {"order_number": 50, "cutlist_no": 50, "location": 255, "product_code": 100, "project_name": 255}


class ImportErrorReport(Exception):
    """The workbook cannot be imported at all (missing columns, several projects)."""


@dataclass
class OrderPlan:
    row: int                       # sheet row number, header = 1
    key: str
    order_number: str | None
    supplier: str
    description: str
    product_code: str | None
    location: str | None
    cutlist_no: str | None
    quantity: Decimal
    total: Decimal
    unit_cost: Decimal | None
    status: str
    priority: str
    required: dt.date | None
    ordered: dt.date | None
    due: dt.date | None
    arrived: dt.date | None
    received_qty: Decimal | None   # delivery-log row, Delivered orders only
    notes: str | None
    has_file: bool


@dataclass
class Plan:
    project_name: str | None
    orders: list[OrderPlan] = field(default_factory=list)
    suppliers: list[str] = field(default_factory=list)
    anomalies: list[tuple[str, str]] = field(default_factory=list)

    def note(self, kind: str, detail: str) -> None:
        self.anomalies.append((kind, detail))


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _num(v) -> Decimal | None:
    s = _clean(v)
    if s is None:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def _date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    return v if isinstance(v, dt.date) else None


def read_rows(path: str | Path) -> list[dict]:
    import openpyxl    # imported here so the planner can be tested without a workbook

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    it = wb.worksheets[0].iter_rows(values_only=True)
    header = [(_clean(h) or "") for h in next(it)]
    missing = [h for h in REQUIRED_HEADERS if h not in header]
    if missing:
        raise ImportErrorReport(f"the sheet is missing columns: {', '.join(missing)}")
    return [dict(zip(header, r)) for r in it if any(c is not None and str(c).strip() for c in r)]


def _row_key(r: dict, seen: Counter) -> str:
    base = json.dumps({k: str(v) for k, v in sorted(r.items()) if k in REQUIRED_HEADERS}, sort_keys=True)
    digest = hashlib.sha256(base.encode()).hexdigest()[:32]
    seen[digest] += 1
    return f"{digest}-{seen[digest]}"


def build_plan(rows: list[dict]) -> Plan:
    """Validate and normalise the rows; no database. Everything odd is recorded in `plan.anomalies`."""
    names = {n for n in (_clean(r.get("_ProjectName")) for r in rows) if n}
    if len(names) > 1:
        raise ImportErrorReport(f"the sheet holds several projects ({sorted(names)}); import one at a time")
    plan = Plan(project_name=next(iter(names), None))
    seen: Counter = Counter()

    for n, r in enumerate(rows, start=2):
        key = _row_key(r, seen)
        supplier = _clean(r.get("Supplier"))
        if supplier is None:
            plan.note("no_supplier", f"row {n}: no supplier; skipped")
            continue

        def cut(field_name: str, value: str | None) -> str | None:
            limit = MAX_LEN[field_name]
            if value is not None and len(value) > limit:
                plan.note("too_long", f"row {n}: {field_name} is {len(value)} characters; cut to {limit}")
                return value[:limit]
            return value

        order_no = _clean(r.get("OrderNumber"))
        if order_no is not None and order_no.endswith(".0"):
            order_no = order_no[:-2]
        raw_state = (_clean(r.get("_Priority")) or "").upper()
        arrived = _date(r.get("Date_Arrived"))
        if raw_state == "ORDERED":
            status = "Delivered" if arrived else "Approved"
            if order_no is None:
                plan.note("ordered_no_number", f"row {n}: ORDERED but no order number")
        elif raw_state in STATUS_NOT_ORDERED:
            status = STATUS_NOT_ORDERED[raw_state]
        else:
            if raw_state:
                plan.note("unknown_state", f"row {n}: state {raw_state!r} is not one we know; imported as Pending")
            status = "Pending"
        if status != "Delivered" and arrived:
            plan.note("arrived_not_delivered", f"row {n}: has an arrival date but is {status}; date kept")
        priority = "High" if raw_state == "URGENT" else "Medium"

        qty = _num(r.get("QTY"))
        if qty is None or qty <= 0:
            plan.note("bad_qty", f"row {n}: quantity {r.get('QTY')!r}; imported as 1")
            qty = Decimal(1)
        total = _num(r.get("_Cost_Sub"))
        if total is None:
            total = Decimal(0)
        unit = (total / qty).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        total = total.quantize(Decimal("0.01"), ROUND_HALF_UP)
        ordered, due, required = (_date(r.get(c)) for c in ("Date_Ordered", "Date_Due", "Date_Required"))
        if ordered and arrived and arrived < ordered:
            plan.note("date_order", f"row {n}: arrived {arrived} is before ordered {ordered}")

        received = _num(r.get("T07b_ORD_StockControl::SumTotla"))
        received = received if status == "Delivered" and received and received > 0 else None

        description = _clean(r.get("_BoardGroup"))
        if description is None:
            plan.note("no_description", f"row {n}: no description")
            description = "(no description)"
        requester = _clean(r.get("_RequestedByName"))
        cutlist = _clean(r.get("CutlistNumber"))
        if cutlist is not None and cutlist.endswith(".0"):
            cutlist = cutlist[:-2]

        plan.orders.append(OrderPlan(
            row=n, key=key, order_number=cut("order_number", order_no), supplier=supplier,
            description=description, product_code=cut("product_code", _clean(r.get("_PCode"))),
            location=cut("location", _clean(r.get("Location"))), cutlist_no=cut("cutlist_no", cutlist),
            quantity=qty, total=total, unit_cost=unit, status=status, priority=priority,
            required=required, ordered=ordered, due=due, arrived=arrived, received_qty=received,
            notes=f"Requested by: {requester}" if requester else None,
            has_file=_clean(r.get("Doc_PDF")) is not None,
        ))
        if supplier not in plan.suppliers:
            plan.suppliers.append(supplier)
    return plan


@dataclass
class Result:
    project_id: int | None = None
    project_created: bool = False
    vendors_created: int = 0
    orders_created: int = 0
    orders_skipped_existing: int = 0
    deliveries: int = 0


def apply(
    db: Session, plan: Plan, *, workspace_id: int, actor_id: int, project_code: str, project_name: str,
    source_sha256: str,
) -> Result:
    """Write the plan. Flushes, never commits: the caller commits (`--commit`) or rolls back (dry run)."""
    res = Result()
    actor_email = db.execute(text("SELECT email FROM app_user WHERE id = :u AND workspace_id = :w"),
                             {"u": actor_id, "w": workspace_id}).scalar()
    pr = db.execute(text("SELECT project_id, name FROM projects WHERE project_code = :c AND workspace_id = :w"),
                    {"c": project_code, "w": workspace_id}).first()
    if pr is None:
        res.project_id = db.execute(
            text("""INSERT INTO projects(project_code, name, workspace_id, pm_id, created_by)
                    VALUES (:c, :n, :w, :u, :e) RETURNING project_id"""),
            {"c": project_code, "n": project_name, "w": workspace_id, "u": actor_id, "e": actor_email},
        ).scalar()
        res.project_created = True
        name_on_orders = project_name
    else:
        res.project_id, name_on_orders = pr[0], pr[1]

    vendor_ids: dict[str, int] = {}
    for name in plan.suppliers:
        row = db.execute(text("SELECT vendor_id FROM vendors WHERE workspace_id = :w AND lower(name) = lower(:n)"
                              " ORDER BY vendor_id LIMIT 1"), {"w": workspace_id, "n": name}).first()
        if row is None:
            row = db.execute(text("INSERT INTO vendors(workspace_id, name, category) VALUES (:w, :n, :c)"
                                  " RETURNING vendor_id"), {"w": workspace_id, "n": name, "c": CATEGORY}).first()
            res.vendors_created += 1
        vendor_ids[name] = row[0]

    keys = [o.key for o in plan.orders]
    existing = {r[0] for r in db.execute(
        text("SELECT attributes->>'fm_import' FROM purchase_orders WHERE attributes->>'fm_import' = ANY(:k)"
             " AND project_id = :p"), {"k": keys, "p": res.project_id})}

    for o in plan.orders:
        if o.key in existing:
            res.orders_skipped_existing += 1
            continue
        po_id = db.execute(
            text("""
                INSERT INTO purchase_orders (
                    po_number, status, vendor_id, requester_id, description, category, project_id,
                    project_name, location, cutlist_no, order_number, priority, product_code,
                    quantity, unit_cost, total_amount, required_date, date_ordered, due_date, arrived_date,
                    notes, attributes)
                VALUES (
                    'PO-' || EXTRACT(year FROM now())::int || '-' || lpad(nextval('po_number_seq')::text, 4, '0'),
                    :status, :vendor, :actor, :descr, :cat, :proj, :pname, :loc, :cutlist, :order_no, :prio,
                    :pcode, :qty, :ucost, :total, :req, :ord, :due, :arr, :notes,
                    CAST(:attrs AS jsonb))
                RETURNING po_id"""),
            {"status": o.status, "vendor": vendor_ids[o.supplier], "actor": actor_id, "descr": o.description,
             "cat": CATEGORY, "proj": res.project_id, "pname": name_on_orders, "loc": o.location,
             "cutlist": o.cutlist_no, "order_no": o.order_number, "prio": o.priority, "pcode": o.product_code,
             "qty": o.quantity, "ucost": o.unit_cost, "total": o.total, "req": o.required, "ord": o.ordered,
             "due": o.due, "arr": o.arrived, "notes": o.notes, "attrs": json.dumps({"fm_import": o.key})},
        ).scalar()
        res.orders_created += 1
        if o.received_qty is not None:
            db.execute(
                text("""INSERT INTO order_delivery(po_id, qty, date_received, notes, created_by)
                        VALUES (:p, :q, :d, 'Imported from FileMaker (stock control total)', :u)"""),
                {"p": po_id, "q": o.received_qty, "d": o.arrived, "u": actor_id})
            res.deliveries += 1

    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="import.orders_grid",
                target=project_code, payload={
                    "source_sha256": source_sha256, "project_id": res.project_id,
                    "project_created": res.project_created, "orders_created": res.orders_created,
                    "orders_skipped_existing": res.orders_skipped_existing,
                    "vendors_created": res.vendors_created, "deliveries": res.deliveries,
                    "anomalies": len(plan.anomalies)})
    db.flush()
    return res


def report(plan: Plan, res: Result | None, *, committed: bool) -> str:
    out = [f"Orders grid import: {len(plan.orders)} orders for {plan.project_name!r}"
           f" ({'COMMITTED' if committed else 'DRY RUN, nothing was written'})"]
    out.append("  status: " + ", ".join(f"{k} {n}" for k, n in sorted(Counter(o.status for o in plan.orders).items())))
    out.append(f"  suppliers: {len(plan.suppliers)}   order numbers: {len({o.order_number for o in plan.orders if o.order_number})}"
               f"   total ex GST: {sum(o.total for o in plan.orders):,.2f}")
    out.append(f"  Doc_PDF not imported (container paths only, no bytes): {sum(o.has_file for o in plan.orders)} rows")
    if res is not None:
        out.append(f"  would create (or created): project {'new' if res.project_created else 'existing'},"
                   f" {res.vendors_created} suppliers, {res.orders_created} orders,"
                   f" {res.deliveries} delivery-log rows; {res.orders_skipped_existing} orders already existed")
    by_kind = Counter(k for k, _ in plan.anomalies)
    out.append(f"  anomalies: {sum(by_kind.values())} ({', '.join(f'{k} {n}' for k, n in sorted(by_kind.items())) or 'none'})")
    for kind in sorted(by_kind):
        for k, detail in [a for a in plan.anomalies if a[0] == kind][:5]:
            out.append(f"    [{k}] {detail}")
        if by_kind[kind] > 5:
            out.append(f"    [{kind}] ... and {by_kind[kind] - 5} more")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("--workspace-slug", required=True)
    ap.add_argument("--actor-email", required=True, help="the user the import is recorded under (and raises the orders)")
    ap.add_argument("--project-code", required=True)
    ap.add_argument("--project-name", help="used only when the project has to be created (default: the sheet's)")
    ap.add_argument("--commit", action="store_true", help="keep the result (default: a dry run, rolled back)")
    args = ap.parse_args(argv)

    from ..db import SessionLocal           # imported late so `--help` works without DATABASE_URL

    data = Path(args.file).read_bytes()
    plan = build_plan(read_rows(args.file))
    db = SessionLocal()
    try:
        ws = db.execute(text("SELECT id FROM workspace WHERE slug = :s"), {"s": args.workspace_slug}).scalar()
        actor = db.execute(text("SELECT id FROM app_user WHERE email = :e AND workspace_id = :w"),
                           {"e": args.actor_email, "w": ws}).scalar() if ws else None
        if ws is None or actor is None:
            print("unknown workspace or actor", file=sys.stderr)
            return 2
        res = apply(db, plan, workspace_id=ws, actor_id=actor, project_code=args.project_code,
                    project_name=args.project_name or plan.project_name or args.project_code,
                    source_sha256=hashlib.sha256(data).hexdigest())
        (db.commit if args.commit else db.rollback)()
        print(report(plan, res, committed=args.commit))
        return 0
    except ImportErrorReport as e:
        db.rollback()
        print(f"cannot import: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

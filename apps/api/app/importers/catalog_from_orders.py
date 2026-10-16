"""Start the catalog from a FileMaker orders export (E3, third slice), in two steps.

The old system's catalog could not be exported, but every order line names a product (`_PCode`, the
description, the supplier). The orders workbook is the same one `orders_grid` imports.

    python -m app.importers.catalog_from_orders propose ORDERS.xlsx --out review.xlsx
        # no database: one row per product code, with a guessed catalog table and the reason

    (a person corrects the Table column of review.xlsx: board, hardware, custom_made, benchtop,
     appliance, or skip)

    python -m app.importers.catalog_from_orders import review.xlsx --workspace-slug SLUG \\
        --actor-email EMAIL [--commit]                       # a dry run, rolled back, unless --commit

Settled with the user (2026-10-15): the catalog is built from order history; the table per product is
guessed and then reviewed by a person before anything is written; the old Order Type list is a separate
thing (migration 0066).

What it writes is what the catalog itself takes (`catalog.queries.create_catalog_row`): the code, the SKU
(= the code, which is what the order pop-up's Cutlists tab matches on), the description and the supplier
(linked when exactly one supplier has that name), the old system's **product type** (the optional Type column of the sheet: Glass, Supplies, Paint..., kept as text beside the tab) and the **unit cost**: the latest order's line total
divided by its quantity, ex GST, a cost of 0 stored as 0 (settled with the user, 2026-10-15; Generate Orders
and "add from catalog" start an order line's price from it). Equipment hire is never written (a hire row
belongs to a project). A code already in the catalog is left as it is; a code another workspace already
uses is reported (the code columns are unique across workspaces, a `0001` artefact).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..catalog import queries as catalog_queries

ORDER_HEADERS = ("_PCode", "_BoardGroup", "Supplier", "Date_Ordered", "QTY", "_Cost_Sub")
REVIEW_HEADERS = ("Code", "Description", "Supplier", "Unit cost", "Orders", "Type", "Table", "Reason", "Confidence", "Note")
TABLES = ("board", "hardware", "custom_made", "benchtop", "appliance", "hire", "edging", "skip")
# The Catalog screen's tabs are the product types; each type's items live in one of the six tables until
# the types get tables of their own. A person never sees or edits this: Type (column F) is the only input.
TYPE_TABLE = {
    "laminate benchtop": "benchtop", "hardware": "hardware", "glass": "custom_made", "supplies": "hardware",
    "contractor manufacturing": "custom_made", "board": "board", "laminate": "board", "delivery": "custom_made",
    "edging": "edging", "solid timber": "benchtop", "paint": "hardware", "tg solid": "benchtop",
    "appliance": "appliance", "equipment hire": "hire",
}

# catalog type -> (the type's own code column; both it and `sku` get the product code)
CODE_COLUMN = {"board": "code", "hardware": "sku", "custom_made": "internal_ref",
               "benchtop": "slab_id", "appliance": "model_number", "hire": "contract_ref",
               "edging": "sku"}
MAX_CODE = {"board": 32}        # the others take 64 (the schemas' limits)


class ImportErrorReport(Exception):
    """The workbook cannot be used at all (missing columns, an unknown table value)."""


def _clean(v) -> str | None:
    s = None if v is None else str(v).strip()
    return s or None


def _squash(v) -> str:
    return " ".join(str(v or "").split())


def _unit_cost(row: dict) -> Decimal | None:
    """The order line's total divided by its quantity (ex GST); None when either is unusable."""
    try:
        qty, total = Decimal(str(row.get("QTY"))), Decimal(str(row.get("_Cost_Sub")))
    except Exception:
        return None
    return (total / qty).quantize(Decimal("0.0001"), ROUND_HALF_UP) if qty > 0 and total >= 0 else None


# ---- the guess ---------------------------------------------------------------------------------------

_DIMS = re.compile(r"^\s*\d+(\.\d+)?\s*[xX]\s*\d+(\.\d+)?\s*[xX]\s*\d+(\.\d+)?\s*-\s")
_ONE_OFF = re.compile(r"^pcs:\(|as per attached|refer to attached|per attached|shop drawings|size varies|varies\b"
                      r"|pc in dulux|powdercoat|steel frame|steel legs", re.I)
_NOT_PRODUCT = re.compile(r"delivery fee|surcharge", re.I)
_HIRE = re.compile(r"vertical lift|scissor lift|boom lift|\bhire\b|haulotte", re.I)
_APPLIANCE = re.compile(r"dishwasher|dishdrawer|\boven\b|cooktop|rangehood|fridge|microwave", re.I)
_GLASS = re.compile(r"\bfloat\b|toughened|\bglass\b|\bfpar\b", re.I)
_EDGING = re.compile(r"unglued|edging|\bedge\b", re.I)
_SOLID_TOP = re.compile(r"^solid top|solid tasmanian oak|\bdar\b", re.I)
_HARDWARE = re.compile(
    r"hinge|runner|handle|\bpull\b|\bbin\b|\bleg\b|basket|bolt|\bnut\b|washer|anchor|threaded rod|glove|silicone|"
    r"hypersil|paint|dulux|kg of|drill|cutter|\btool\b|end cap|shelf|\bally\b|aluminium|table (base|frame)|tabel|"
    r"folding table|module|power box|pipe|polyester|sds", re.I)
_BRANDS = re.compile(r"hafele|hettich|blum", re.I)


def classify(code: str | None, description: str, supplier: str | None) -> tuple[str, str, str]:
    """(table, reason, confidence) for one product. Only a guess: a person reviews every row."""
    d = _squash(description)
    if not code:
        return "skip", "no product code", "high"
    if _NOT_PRODUCT.search(d) or code.lower().startswith(("tg_deliveryfee", "surcharge")):
        return "skip", "a charge, not a product", "high"
    if _ONE_OFF.search(d):
        return "skip", "made to order for one job", "high"
    if _HIRE.search(d):
        return "skip", "equipment hire belongs to a project; not imported", "high"
    if _APPLIANCE.search(d):
        return "appliance", "an appliance", "high"
    if _GLASS.search(d):
        return "custom_made", "cut-to-size glass", "low"
    if _DIMS.match(d):
        if _EDGING.search(d):
            return "hardware", "edging", "low"
        return "board", "a sheet size, then the material", "high"
    if _SOLID_TOP.search(d):
        return "benchtop", "a solid timber top", "low"
    if _HARDWARE.search(d) or _BRANDS.search(supplier or "") or _BRANDS.search(d):
        return "hardware", "a fitting, fixing or supply", "low"
    return "skip", "could not tell", "low"


# ---- step 1: the proposal ----------------------------------------------------------------------------

@dataclass
class Product:
    code: str | None
    description: str
    supplier: str | None
    unit_cost: Decimal | None
    orders: int
    table: str
    reason: str
    confidence: str
    note: str


def read_orders(path: str | Path) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    it = wb.worksheets[0].iter_rows(values_only=True)
    header = [(_clean(h) or "") for h in next(it)]
    missing = [h for h in ORDER_HEADERS if h not in header]
    if missing:
        raise ImportErrorReport(f"the orders sheet is missing columns: {', '.join(missing)}")
    return [dict(zip(header, r)) for r in it if any(c is not None and str(c).strip() for c in r)]


def propose(rows: list[dict]) -> list[Product]:
    """One product per `_PCode`: the most recently ordered row names it. No database."""
    groups: "OrderedDict[str | None, list[dict]]" = OrderedDict()
    for r in rows:
        groups.setdefault(_clean(r.get("_PCode")), []).append(r)
    out = []
    for code, rs in groups.items():
        newest = max(rs, key=lambda r: str(r.get("Date_Ordered") or ""))
        desc = _squash(newest.get("_BoardGroup"))
        supplier = _clean(newest.get("Supplier"))
        table, reason, confidence = classify(code, desc, supplier)
        others = {_squash(r.get("_BoardGroup")) for r in rs} - {desc}
        note = f"{len(others)} other wording(s) on earlier orders" if others else ""
        if len({_clean(r.get("Supplier")) for r in rs}) > 1:
            note = (note + "; " if note else "") + "ordered from more than one supplier"
        out.append(Product(code, desc[:255], supplier, _unit_cost(newest), len(rs), table, reason, confidence, note))
    same = Counter(p.description.lower() for p in out)
    for p in out:
        if p.table != "skip" and same[p.description.lower()] > 1:
            p.note = (p.note + "; " if p.note else "") + f"same wording under {same[p.description.lower()] - 1} other code(s)"
    return out


def write_review(products: list[Product], out: str | Path) -> None:
    import openpyxl
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Review"
    ws.append(list(REVIEW_HEADERS))
    for p in products:
        ws.append([p.code, p.description, p.supplier, None if p.unit_cost is None else float(p.unit_cost),
                   p.orders, None, p.table, p.reason, p.confidence, p.note])
    dv = DataValidation(type="list", formula1='"' + ",".join(TABLES) + '"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add(f"G2:G{len(products) + 1}")
    for col, width in zip("ABCDEFGHIJ", (22, 70, 28, 11, 8, 18, 14, 44, 11, 40)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    guide = wb.create_sheet("Read me")
    for line in ("Correct the Table column (G), then keep the file for the import step. Type (F) is optional free text: the old system's product type, kept on the catalog item.",
                 "Table is one of: " + ", ".join(TABLES) + ". `skip` leaves the product out of the catalog.",
                 "Unit cost is the latest order's line total divided by its quantity, ex GST; clear a cell to import no price.",
                 "Equipment hire is never imported (it belongs to a project).",
                 "Confidence `low` marks the guesses most worth a look."):
        guide.append([line])
    wb.save(out)


# ---- step 2: the import ------------------------------------------------------------------------------

@dataclass
class ReviewRow:
    row: int
    code: str
    description: str
    supplier: str | None
    table: str
    unit_cost: Decimal | None
    product_type: str | None


def read_review(path: str | Path) -> list[ReviewRow]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Review"] if "Review" in wb.sheetnames else wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [(_clean(h) or "") for h in next(it)]
    missing = [h for h in ("Code", "Description", "Supplier", "Type") if h not in header]
    if missing:
        raise ImportErrorReport(f"the review sheet is missing columns: {', '.join(missing)}")
    out, bad = [], []
    for n, r in enumerate(it, start=2):
        rec = dict(zip(header, r))
        ptype = _clean(rec.get("Type"))
        # A Table column (the old review sheets) wins; otherwise the table follows from the Type.
        table = (_clean(rec.get("Table")) or TYPE_TABLE.get((ptype or "").lower()) or "skip").lower()
        if table not in TABLES:
            bad.append(f"row {n}: {table!r}")
            continue
        code = _clean(rec.get("Code"))
        if code is None:
            continue
        cost = None
        if _clean(rec.get("Unit cost")) is not None:
            try:
                cost = Decimal(str(rec.get("Unit cost"))).quantize(Decimal("0.0001"), ROUND_HALF_UP)
                if cost < 0 or cost >= Decimal(10) ** 11:
                    raise ValueError
            except Exception:
                bad.append(f"row {n}: unit cost {rec.get('Unit cost')!r}")
                continue
        if ptype is not None and len(ptype) > 64:
            bad.append(f"row {n}: type {ptype[:20]!r}... is longer than 64 characters")
            continue
        out.append(ReviewRow(n, code, _squash(rec.get("Description"))[:255], _clean(rec.get("Supplier")), table, cost,
                             ptype))
    if bad:
        raise ImportErrorReport("Table must be one of " + ", ".join(TABLES) + " and Unit cost a number of 0 or more; got "
                                + "; ".join(bad[:10]))
    return out


@dataclass
class Result:
    created: Counter
    existing: int = 0
    skipped: int = 0
    linked: int = 0
    unlinked: int = 0


def apply(db: Session, rows: list[ReviewRow], *, workspace_id: int, actor_id: int, source_sha256: str,
          anomalies: list[tuple[str, str]], hire_project_id: int | None = None) -> Result:
    """Write the reviewed rows. Flushes, never commits: the caller commits (`--commit`) or rolls back."""
    res = Result(created=Counter())
    by_name = catalog_queries.supplier_ids_by_name(db, workspace_id=workspace_id)
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if r.table == "skip":
            res.skipped += 1
            continue
        if (r.table, r.code) in seen:
            anomalies.append(("duplicate_code", f"row {r.row}: {r.code} is on the sheet twice; the first is used"))
            continue
        seen.add((r.table, r.code))
        if len(r.code) > MAX_CODE.get(r.table, 64):
            anomalies.append(("code_too_long", f"row {r.row}: {r.code!r} is too long for {r.table}; skipped"))
            continue
        if not r.description:
            anomalies.append(("no_description", f"row {r.row}: {r.code} has no description; skipped"))
            continue
        if r.table == "hire" and hire_project_id is None:
            anomalies.append(("hire_needs_project", f"row {r.row}: {r.code} is equipment hire, which belongs to a "
                                                    "project; give --project-code. Skipped"))
            continue
        table, _id, _cols, _ins = catalog_queries.REGISTRY[r.table]
        code_col = CODE_COLUMN[r.table]
        hit = db.execute(text(f"SELECT workspace_id FROM {table} WHERE {code_col} = :c OR "
                              "(workspace_id = :w AND sku = :c) LIMIT 1"), {"c": r.code, "w": workspace_id}).first()
        if hit is not None:
            if hit[0] == workspace_id:
                res.existing += 1
            else:
                anomalies.append(("code_used_elsewhere", f"row {r.row}: {r.code} is already used by another "
                                                         f"workspace in {table}; skipped"))
            continue
        fields = {code_col: r.code, "sku": r.code, "description": r.description, "synonyms": [],
                  "default_supplier": (r.supplier or "")[:128] or None, "default_supplier_id": None,
                  "default_lead_time_days": None, "unit_cost": r.unit_cost,
                  "product_type": r.product_type}
        if r.table == "hire":
            fields["project_id"] = hire_project_id
        key = (r.supplier or "").strip().lower()
        if key and by_name.get(key) is not None:
            fields["default_supplier_id"] = by_name[key]
            res.linked += 1
        elif key:
            res.unlinked += 1
        catalog_queries.create_catalog_row(db, type_=r.table, fields=fields, workspace_id=workspace_id)
        res.created[r.table] += 1
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="import.catalog_from_orders",
                target="catalog", payload={"source_sha256": source_sha256, "created": dict(res.created),
                                           "existing": res.existing, "skipped": res.skipped,
                                           "anomalies": len(anomalies)})
    db.flush()
    return res


def report_proposal(products: list[Product]) -> str:
    by = Counter(p.table for p in products)
    low = sum(1 for p in products if p.confidence == "low" and p.table != "skip")
    return (f"Catalog proposal: {len(products)} products from the orders. Guessed tables: "
            + ", ".join(f"{k} {n}" for k, n in sorted(by.items()))
            + f". {low} non-skip guesses are low confidence: look at those first.")


def report_import(res: Result, anomalies: list[tuple[str, str]], *, committed: bool) -> str:
    out = [f"Catalog import ({'COMMITTED' if committed else 'DRY RUN, nothing was written'}):"
           f" created {dict(res.created) or 'nothing'}; {res.existing} already in the catalog;"
           f" {res.skipped} left out (skip); suppliers linked {res.linked}, not linked {res.unlinked}"]
    by_kind = Counter(k for k, _ in anomalies)
    out.append(f"  anomalies: {sum(by_kind.values())} ({', '.join(f'{k} {n}' for k, n in sorted(by_kind.items())) or 'none'})")
    for k, detail in anomalies[:8]:
        out.append(f"    [{k}] {detail}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("propose", help="write the review sheet from the orders export (no database)")
    p1.add_argument("file")
    p1.add_argument("--out", required=True)
    p2 = sub.add_parser("import", help="import a reviewed sheet (a dry run unless --commit)")
    p2.add_argument("file")
    p2.add_argument("--workspace-slug", required=True)
    p2.add_argument("--actor-email", required=True)
    p2.add_argument("--project-code", help="the project equipment-hire rows are attached to (required if the sheet has any)")
    p2.add_argument("--commit", action="store_true", help="keep the result (default: a dry run, rolled back)")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "propose":
            products = propose(read_orders(args.file))
            write_review(products, args.out)
            print(report_proposal(products))
            print(f"Review sheet written to {args.out}")
            return 0
        from ..db import SessionLocal           # imported late so `--help` works without DATABASE_URL

        rows = read_review(args.file)
        data = Path(args.file).read_bytes()
        db = SessionLocal()
        try:
            ws = db.execute(text("SELECT id FROM workspace WHERE slug = :s"), {"s": args.workspace_slug}).scalar()
            actor = db.execute(text("SELECT id FROM app_user WHERE email = :e AND workspace_id = :w"),
                               {"e": args.actor_email, "w": ws}).scalar() if ws else None
            if ws is None or actor is None:
                print("unknown workspace or actor", file=sys.stderr)
                return 2
            anomalies: list[tuple[str, str]] = []
            hire_project = None
            if args.project_code:
                hire_project = db.execute(text("SELECT project_id FROM projects WHERE project_code = :c AND workspace_id = :w"),
                                          {"c": args.project_code, "w": ws}).scalar()
                if hire_project is None:
                    print(f"unknown project code {args.project_code!r}", file=sys.stderr)
                    return 2
            res = apply(db, rows, workspace_id=ws, actor_id=actor, source_sha256=hashlib.sha256(data).hexdigest(),
                        anomalies=anomalies, hire_project_id=hire_project)
            (db.commit if args.commit else db.rollback)()
            print(report_import(res, anomalies, committed=args.commit))
            return 0
        finally:
            db.close()
    except ImportErrorReport as e:
        print(f"cannot import: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

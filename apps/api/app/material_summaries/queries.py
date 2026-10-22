"""Project Material Summary (plan tasks C1–C3; spec §5, §7).

Built from each Joinery Item's *current approved* take. Board lines are
fractional sheets per item and round up **once** here (Q586). `stale`,
`nest_sheets` and the required / on-order / received / outstanding columns are
computed on read and never stored, so they cannot drift from what they describe.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..material_takes.generation import summary_sheets
from ..material_takes.queries import Conflict, NotFound
from ..procurement_v1.materials.queries import _CATALOG_LOOKUP
from ..row_types import live_joinery_items
from ..sql_columns import require_columns

_JOINERY_I = live_joinery_items("i")


def _project(db: Session, project_id: int, workspace_id: int) -> None:
    if db.execute(text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
                  {"p": project_id, "w": workspace_id}).scalar() is None:
        raise NotFound()


def _summary(db: Session, summary_id: int, workspace_id: int, *, lock=False) -> dict:
    r = db.execute(text(f"""
        SELECT s.* FROM material_summary s JOIN projects p ON p.project_id = s.project_id
         WHERE s.summary_id = :s AND p.workspace_id = :w {'FOR UPDATE OF s' if lock else ''}"""),
        {"s": summary_id, "w": workspace_id}).mappings().first()
    if r is None:
        raise NotFound()
    return dict(r)


def _key(line) -> tuple:
    if line["material_type"] == "OTHER":
        return ("OTHER", None, line["description"], line["unit"])
    return (line["material_type"], line["material_id"], None, line["unit"])


def _consolidate(unit: str, qtys: list[Decimal]) -> Decimal:
    return summary_sheets(qtys) if unit == "sheet" else sum(qtys, Decimal(0))


def missing_takes(db: Session, project_id: int) -> list[dict]:
    return [dict(r) for r in db.execute(text(f"""
        SELECT i.item_id, i.num, i.description FROM items i
         WHERE i.project_id = :p AND {_JOINERY_I} AND NOT COALESCE(i.deleted, false)
           AND NOT EXISTS (SELECT 1 FROM material_take t
                            WHERE t.item_id = i.item_id AND t.status = 'approved')
         ORDER BY i.num"""), {"p": project_id}).mappings()]


def build(db: Session, project_id: int, workspace_id: int, actor_id: int) -> int:
    _project(db, project_id, workspace_id)
    rows = db.execute(text(f"""
        SELECT l.*, t.version AS take_version
          FROM material_take t
          JOIN items i ON i.item_id = t.item_id
          JOIN material_take_line l ON l.take_id = t.take_id
         WHERE i.project_id = :p AND {_JOINERY_I} AND t.status = 'approved'
         ORDER BY l.material_type, l.material_id, l.line_id"""), {"p": project_id}).mappings().all()
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault(_key(r), []).append(r)

    sid = db.execute(text("""
        INSERT INTO material_summary(project_id, status, created_by)
        VALUES (:p, 'draft', :a) RETURNING summary_id"""), {"p": project_id, "a": actor_id}).scalar()
    for (mt, mid, _, unit), src in groups.items():
        lid = db.execute(text("""
            INSERT INTO material_summary_line(summary_id, material_type, material_id,
                description, unit, qty_consolidated)
            VALUES (:s, :mt, :mid, :d, :u, :q) RETURNING line_id"""),
            {"s": sid, "mt": mt, "mid": mid, "d": src[0]["description"], "u": unit,
             "q": _consolidate(unit, [r["qty"] for r in src])}).scalar()
        db.execute(text("""
            INSERT INTO material_summary_source(summary_line_id, take_line_id, take_id,
                take_version, qty)
            VALUES (:l, :tl, :t, :v, :q)"""),
            [{"l": lid, "tl": r["line_id"], "t": r["take_id"], "v": r["take_version"],
              "q": r["qty"]} for r in src])
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="material_summary.build",
                target=f"project:{project_id}",
                payload={"summary_id": sid, "lines": len(groups),
                         "missing_takes": len(missing_takes(db, project_id))})
    return sid


def _nest_sheets(db: Session, project_id: int) -> dict[int, int]:
    """Sheets per board material in the project's latest CutPlan (Q582).

    `cut_sheet.material_sku` holds whatever the plan was made with: the
    optimiser writes the catalog SKU, but a plan built from a Cabinet Vision
    nest (the seed's `ALF-001 v1 nest`) carries the CV code (`18-PB`). Resolve
    either to a board material, SKU first, then `cv_material_mapping`."""
    return {r[0]: r[1] for r in db.execute(text("""
        SELECT COALESCE(bm.material_id, cm.target_material_id) AS mid, count(*)
          FROM cut_sheet cs
          JOIN cut_plan cp ON cp.id = cs.cut_plan_id
          LEFT JOIN board_materials bm
                 ON bm.sku = cs.material_sku AND bm.workspace_id = cp.workspace_id
          LEFT JOIN cv_material_mapping cm
                 ON cm.cv_code = cs.material_sku AND cm.workspace_id = cp.workspace_id
                AND cm.target_material_table = 'board_materials'
         WHERE cs.cut_plan_id = (SELECT MAX(id) FROM cut_plan WHERE project_id = :p)
         GROUP BY 1"""), {"p": project_id}) if r[0] is not None}


def _order_figures(db: Session, project_id: int) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    """Ordered, received and raised quantity per product code, from the project's Orderbook orders.

    An order counts as ordered once it is placed with the supplier (`date_ordered`
    set, as a PO does) or Delivered; Cancelled / Rejected never count. Received is
    the Delivery tab's log, and a Delivered order is received in full (the log is a
    record and never changes the status). Matched to a material by product code =
    catalog SKU, trimmed and case-insensitive, like the order pop-up's catalog block.
    Raised is every order not Cancelled / Rejected, placed or not: what a new order
    from the line must not repeat.
    """
    rows = db.execute(text("""
        SELECT lower(btrim(po.product_code)) AS code,
               SUM(po.quantity) FILTER (WHERE placed) AS ordered,
               SUM(CASE WHEN po.status = 'Delivered' THEN po.quantity
                        ELSE COALESCE(d.got, 0) END) FILTER (WHERE placed) AS received,
               SUM(po.quantity) AS raised
          FROM (SELECT po.*, (po.date_ordered IS NOT NULL OR po.status = 'Delivered') AS placed
                  FROM purchase_orders po) po
          LEFT JOIN (SELECT po_id, SUM(qty) AS got FROM order_delivery GROUP BY po_id) d
                 ON d.po_id = po.po_id
         WHERE po.project_id = :p
           AND po.status NOT IN ('Cancelled', 'Rejected')
           AND btrim(COALESCE(po.product_code, '')) <> ''
         GROUP BY 1"""), {"p": project_id}).mappings().all()
    return {r["code"]: (r["ordered"] or Decimal(0), r["received"] or Decimal(0), r["raised"] or Decimal(0))
            for r in rows}


def _line_skus(db: Session, lines: list[dict]) -> dict[tuple[str, int], str]:
    """Lower-cased catalog SKU of every material the lines point at."""
    by_type: dict[str, list[int]] = {}
    for l in lines:
        if l["material_id"] is not None and l["material_type"] in _CATALOG_LOOKUP:
            by_type.setdefault(l["material_type"], []).append(l["material_id"])
    out: dict[tuple[str, int], str] = {}
    for mt, ids in by_type.items():
        table, id_col, _name, sku_col = _CATALOG_LOOKUP[mt]
        for r in db.execute(text(f"SELECT {id_col} AS id, {sku_col} AS sku FROM {table} "
                                 f"WHERE {id_col} = ANY(:ids)"), {"ids": ids}).mappings():
            if r["sku"] and r["sku"].strip():
                out[(mt, r["id"])] = r["sku"].strip().lower()
    return out


def _detail(db: Session, s: dict) -> dict:
    lines = [dict(r) for r in db.execute(text("""
        SELECT l.* FROM material_summary_line l
         WHERE l.summary_id = :s ORDER BY l.material_type, l.description"""),
        {"s": s["summary_id"]}).mappings()]
    sources = db.execute(text("""
        SELECT src.summary_line_id, src.take_version, src.qty, t.item_id, i.num, i.description,
               cur.version AS current_version
          FROM material_summary_source src
          JOIN material_take t ON t.take_id = src.take_id
          JOIN items i ON i.item_id = t.item_id AND NOT i.deleted
          LEFT JOIN material_take cur ON cur.item_id = t.item_id AND cur.status = 'approved'
         WHERE src.summary_line_id = ANY(:ids)
         ORDER BY i.num"""), {"ids": [l["line_id"] for l in lines]}).mappings().all()
    by_line: dict[int, list] = {}
    for r in sources:
        by_line.setdefault(r["summary_line_id"], []).append(dict(r))
    nest = _nest_sheets(db, s["project_id"])
    orders = _order_figures(db, s["project_id"])
    skus = _line_skus(db, lines)
    for l in lines:
        src = by_line.get(l["line_id"], [])
        # Stale (Q500): a source item has since approved another version, or
        # lost its take entirely, or a source row is gone (item hard-deleted).
        l["stale"] = (any(r["current_version"] != r["take_version"] for r in src)
                      or _consolidate(l["unit"], [r["qty"] for r in src]) != l["qty_consolidated"])
        l["sources"] = [{"item_id": r["item_id"], "num": r["num"], "description": r["description"],
                         "take_version": r["take_version"], "qty": r["qty"]} for r in src]
        l["nest_sheets"] = nest.get(l["material_id"]) if l["material_type"] == "BOARD" else None
        # Required is the PM's confirmed figure when set, else what the takes add up to.
        l["qty_required"] = l["qty_confirmed"] if l["qty_confirmed"] is not None else l["qty_consolidated"]
        sku = skus.get((l["material_type"], l["material_id"]))
        if sku is None:      # no catalog SKU to match orders on
            l["qty_on_order"] = l["qty_received"] = l["qty_outstanding"] = l["qty_to_order"] = None
        else:
            l["qty_on_order"], l["qty_received"], raised = orders.get(sku, (Decimal(0),) * 3)
            l["qty_outstanding"] = max(l["qty_required"] - l["qty_received"], Decimal(0))
            l["qty_to_order"] = max(l["qty_required"] - raised, Decimal(0))
    return {**s, "lines": lines, "missing_takes": missing_takes(db, s["project_id"])}


def current(db: Session, project_id: int, workspace_id: int) -> dict | None:
    _project(db, project_id, workspace_id)
    s = db.execute(text("""
        SELECT * FROM material_summary WHERE project_id = :p
         ORDER BY summary_id DESC LIMIT 1"""), {"p": project_id}).mappings().first()
    if s is None:
        return {"summary": None, "missing_takes": missing_takes(db, project_id)}
    d = _detail(db, dict(s))
    return {"summary": d, "missing_takes": d.pop("missing_takes")}


def history(db: Session, project_id: int, workspace_id: int) -> list[dict]:
    _project(db, project_id, workspace_id)
    return [dict(r) for r in db.execute(text("""
        SELECT summary_id, status, confirmed_by, confirmed_at, created_by, created_at
          FROM material_summary WHERE project_id = :p ORDER BY summary_id DESC"""),
        {"p": project_id}).mappings()]


_LINE_COLUMNS = frozenset({"qty_confirmed", "note"})


def patch_line(db: Session, summary_id: int, line_id: int, workspace_id: int, actor_id: int,
               changes: dict) -> None:
    s = _summary(db, summary_id, workspace_id, lock=True)
    if s["status"] != "draft":
        raise Conflict("SUMMARY_CONFIRMED")
    old = db.execute(text("SELECT qty_confirmed, note FROM material_summary_line"
                          " WHERE line_id = :l AND summary_id = :s"),
                     {"l": line_id, "s": summary_id}).mappings().first()
    if old is None:
        raise NotFound()
    require_columns(changes, _LINE_COLUMNS)
    diff = {k: v for k, v in changes.items() if old[k] != v}
    if not diff:
        return
    sets = ", ".join(f"{k} = :{k}" for k in diff)
    db.execute(text(f"UPDATE material_summary_line SET {sets} WHERE line_id = :l"), {**diff, "l": line_id})
    db.execute(text("UPDATE material_summary SET updated_at = now() WHERE summary_id = :s"),
               {"s": summary_id})
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="material_summary.line_edit",
                target=f"project:{s['project_id']}",
                payload={"summary_id": summary_id, "line_id": line_id,
                         "before": {k: None if old[k] is None else str(old[k]) for k in diff},
                         "after": {k: None if v is None else str(v) for k, v in diff.items()}})


def confirm(db: Session, summary_id: int, workspace_id: int, actor_id: int) -> None:
    """Advisory (Q499). Lines the PM left unset take the consolidated figure."""
    s = _summary(db, summary_id, workspace_id, lock=True)
    if s["status"] != "draft":
        raise Conflict("SUMMARY_CONFIRMED")
    db.execute(text("""UPDATE material_summary_line SET qty_confirmed = qty_consolidated
                        WHERE summary_id = :s AND qty_confirmed IS NULL"""), {"s": summary_id})
    db.execute(text("""UPDATE material_summary SET status = 'confirmed', confirmed_by = :a,
                              confirmed_at = now(), updated_at = now() WHERE summary_id = :s"""),
               {"a": actor_id, "s": summary_id})
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="material_summary.confirm",
                target=f"project:{s['project_id']}", payload={"summary_id": summary_id})


# Order category per material type. Solid Timber has no category of its own.
_ORDER_CATEGORY = {"BOARD": "Board", "HARDWARE": "Hardware", "CUSTOM": "Custom", "BENCHTOP": "Benchtop",
                   "APPLIANCE": "Appliance", "HIRE": "Hire", "EDGING": "Edging", "GLASS": "Glass",
                   "TIMBER": "Other"}


def order_line(db: Session, summary_id: int, line_id: int, workspace_id: int, actor_id: int) -> dict:
    """Raise a Pending order for what a summary line still needs (Q585, option 2).

    Quantity is required less every order already raised for the SKU on the project,
    so a second click does not double-order. The order is a normal one: the line's
    catalog SKU as product code, the material's default supplier, no price (an order
    line's price is typed in). Whether the line was confirmed is the summary's to
    show; the order does not record it.
    """
    from ..orders.queries import create_order
    from ..orders.schemas import CreateOrderIn

    s = _summary(db, summary_id, workspace_id)
    if db.execute(text("SELECT MAX(summary_id) FROM material_summary WHERE project_id = :p"),
                  {"p": s["project_id"]}).scalar() != summary_id:
        raise Conflict("SUMMARY_SUPERSEDED")
    line = next((l for l in _detail(db, s)["lines"] if l["line_id"] == line_id), None)
    if line is None:
        raise NotFound()
    if line["material_type"] not in _CATALOG_LOOKUP or line["material_id"] is None:
        raise Conflict("NO_CATALOG_MATERIAL")
    table, id_col, _name, sku_col = _CATALOG_LOOKUP[line["material_type"]]
    m = db.execute(text(f"""SELECT {sku_col} AS sku, description, default_supplier_id, um,
                                   archived_at IS NOT NULL AS archived
                              FROM {table} WHERE {id_col} = :i AND workspace_id = :w"""),
                   {"i": line["material_id"], "w": workspace_id}).mappings().first()
    if m is None:
        raise NotFound()
    if not (m["sku"] or "").strip():
        raise Conflict("NO_SKU")
    if m["default_supplier_id"] is None:
        raise Conflict("NO_SUPPLIER")
    if not line["qty_to_order"]:
        raise Conflict("NOTHING_TO_ORDER")
    code, order = create_order(
        db, workspace_id=workspace_id, actor_id=actor_id,
        payload=CreateOrderIn(
            vendor_id=m["default_supplier_id"], description=m["description"],
            category=_ORDER_CATEGORY[line["material_type"]], project_id=s["project_id"],
            product_code=m["sku"].strip(), quantity=line["qty_to_order"], unit_of_measure=m["um"]))
    if code != "OK":     # the supplier no longer exists in this workspace; the others are fixed above
        raise Conflict("NO_SUPPLIER")
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="material_summary.order_line",
                target=str(line_id), payload={"summary_id": summary_id, "po_id": order["po_id"],
                                              "unconfirmed": line["qty_confirmed"] is None})
    return order

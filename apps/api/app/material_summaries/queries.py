"""Project Material Summary (plan tasks C1–C3; spec §5, §7).

Built from each Joinery Item's *current approved* take. Board lines are
fractional sheets per item and round up **once** here (Q586). `stale`,
`nest_sheets` and the on-order / received columns are computed on read and
never stored, so they cannot drift from what they describe.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..material_takes.generation import summary_sheets
from ..material_takes.queries import Conflict, NotFound
from ..procurement_v1.materials.queries import project_material_rollup
from ..row_types import joinery_items_only

_JOINERY_I = joinery_items_only("i")


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
          JOIN items i ON i.item_id = t.item_id
          LEFT JOIN material_take cur ON cur.item_id = t.item_id AND cur.status = 'approved'
         WHERE src.summary_line_id = ANY(:ids)
         ORDER BY i.num"""), {"ids": [l["line_id"] for l in lines]}).mappings().all()
    by_line: dict[int, list] = {}
    for r in sources:
        by_line.setdefault(r["summary_line_id"], []).append(dict(r))
    nest = _nest_sheets(db, s["project_id"])
    orders = {(r["material_type"], r["material_id"]): r
              for r in project_material_rollup(db, s["project_id"])}
    for l in lines:
        src = by_line.get(l["line_id"], [])
        # Stale (Q500): a source item has since approved another version, or
        # lost its take entirely, or a source row is gone (item hard-deleted).
        l["stale"] = (any(r["current_version"] != r["take_version"] for r in src)
                      or _consolidate(l["unit"], [r["qty"] for r in src]) != l["qty_consolidated"])
        l["sources"] = [{"item_id": r["item_id"], "num": r["num"], "description": r["description"],
                         "take_version": r["take_version"], "qty": r["qty"]} for r in src]
        l["nest_sheets"] = nest.get(l["material_id"]) if l["material_type"] == "BOARD" else None
        o = orders.get((l["material_type"], l["material_id"]))
        l["qty_on_order"] = o["qty_on_order"] if o else None
        l["qty_received"] = o["qty_received"] if o else None
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

"""Material Take persistence (plan tasks B2–B4; spec §3–§6).

Every mutation writes `audit_log` and `item_edit_log` in the caller's
transaction (PM Workbench invariant). Workspace isolation runs through
`items → projects.workspace_id`; a take in another workspace is "not found".
Only a **draft** take changes — an approved one is immutable (Q500).
"""
from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..edit_log import write_edit_log
from .generation import generate_lines, generated_signature

_CENT = Decimal("0.01")


class NotFound(Exception):
    pass


class Conflict(Exception):
    def __init__(self, code: str, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


# --- lookups ----------------------------------------------------------------

def _item(db: Session, item_id: int, workspace_id: int) -> dict:
    r = db.execute(text("""
        SELECT i.item_id, i.row_type FROM items i
          JOIN projects p ON p.project_id = i.project_id
         WHERE i.item_id = :i AND p.workspace_id = :w"""),
        {"i": item_id, "w": workspace_id}).mappings().first()
    if r is None:
        raise NotFound()
    if r["row_type"] == "related_part":
        # Q424: a related part is procured through its own order.
        raise Conflict("RELATED_PART_HAS_NO_TAKE")
    return dict(r)


def _take(db: Session, take_id: int, workspace_id: int, *, lock: bool = False) -> dict:
    r = db.execute(text(f"""
        SELECT t.* FROM material_take t
          JOIN items i ON i.item_id = t.item_id
          JOIN projects p ON p.project_id = i.project_id
         WHERE t.take_id = :t AND p.workspace_id = :w
         {'FOR UPDATE OF t' if lock else ''}"""),
        {"t": take_id, "w": workspace_id}).mappings().first()
    if r is None:
        raise NotFound()
    return dict(r)


def _draft(db: Session, take_id: int, workspace_id: int) -> dict:
    t = _take(db, take_id, workspace_id, lock=True)
    if t["status"] != "draft":
        raise Conflict("TAKE_NOT_DRAFT", status=t["status"])
    return t


def _lines(db: Session, take_id: int) -> list[dict]:
    return [dict(r) for r in db.execute(text(
        "SELECT * FROM material_take_line WHERE take_id = :t ORDER BY line_id"),
        {"t": take_id}).mappings()]


def _with_lines(db: Session, t: dict | None) -> dict | None:
    return None if t is None else {**t, "lines": _lines(db, t["take_id"])}


def _log(db, *, workspace_id, actor_id, item_id, event, field, old=None, new=None, payload=None):
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event=event,
                target=f"item:{item_id}", payload=payload or {})
    write_edit_log(db, item_id=item_id, actor_id=actor_id, field=field,
                   old_value=None if old is None else str(old),
                   new_value=None if new is None else str(new))


def _insert_lines(db: Session, take_id: int, lines: list[dict]) -> None:
    if lines:
        db.execute(text("""
            INSERT INTO material_take_line(take_id, material_type, material_id, description,
                unit, qty_generated, wastage_pct, qty, source, note)
            VALUES (:t, :material_type, :material_id, :description, :unit, :qty_generated,
                    :wastage_pct, :qty, :source, :note)"""),
            [{"t": take_id, **l} for l in lines])


# --- reads ------------------------------------------------------------------

def current(db: Session, item_id: int, workspace_id: int) -> dict:
    _item(db, item_id, workspace_id)
    rows = {r["status"]: dict(r) for r in db.execute(text(
        "SELECT * FROM material_take WHERE item_id = :i AND status IN ('draft','approved')"),
        {"i": item_id}).mappings()}
    approved = _with_lines(db, rows.get("approved"))
    outdated = False
    if approved:
        live = generate_lines(db, item_id, workspace_id)
        outdated = generated_signature(live) != generated_signature(approved["lines"])
    return {"item_id": item_id, "draft": _with_lines(db, rows.get("draft")),
            "approved": approved, "outdated": outdated}


def history(db: Session, item_id: int, workspace_id: int) -> list[dict]:
    _item(db, item_id, workspace_id)
    return [dict(r) for r in db.execute(text("""
        SELECT take_id, version, status, generated_at, approved_by, approved_at,
               created_by, created_at
          FROM material_take WHERE item_id = :i ORDER BY version DESC"""),
        {"i": item_id}).mappings()]


# --- writes -----------------------------------------------------------------

def generate(db: Session, item_id: int, workspace_id: int, actor_id: int) -> int:
    _item(db, item_id, workspace_id)
    existing = db.execute(text(
        "SELECT take_id FROM material_take WHERE item_id = :i AND status = 'draft'"),
        {"i": item_id}).scalar()
    if existing:
        raise Conflict("DRAFT_EXISTS", take_id=existing)
    version = db.execute(text(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM material_take WHERE item_id = :i"),
        {"i": item_id}).scalar()
    tid = db.execute(text("""
        INSERT INTO material_take(item_id, version, status, generated_at, created_by)
        VALUES (:i, :v, 'draft', now(), :a) RETURNING take_id"""),
        {"i": item_id, "v": version, "a": actor_id}).scalar()
    lines = generate_lines(db, item_id, workspace_id)
    _insert_lines(db, tid, lines)
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=item_id,
         event="material_take.generate", field="_material_take_generate", new=f"v{version}",
         payload={"take_id": tid, "version": version, "lines": len(lines)})
    return tid


def regenerate(db: Session, take_id: int, workspace_id: int, actor_id: int) -> None:
    """Replace a draft's generated lines with fresh ones; manual lines stay."""
    t = _draft(db, take_id, workspace_id)
    db.execute(text("DELETE FROM material_take_line WHERE take_id = :t AND source = 'generated'"),
               {"t": take_id})
    lines = generate_lines(db, t["item_id"], workspace_id)
    _insert_lines(db, take_id, lines)
    db.execute(text("UPDATE material_take SET generated_at = now() WHERE take_id = :t"), {"t": take_id})
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=t["item_id"],
         event="material_take.generate", field="_material_take_regenerate",
         new=f"v{t['version']}", payload={"take_id": take_id, "lines": len(lines)})


def add_line(db: Session, take_id: int, workspace_id: int, actor_id: int, line: dict) -> int:
    t = _draft(db, take_id, workspace_id)
    lid = db.execute(text("""
        INSERT INTO material_take_line(take_id, material_type, material_id, description,
            unit, qty_generated, wastage_pct, qty, source, note)
        VALUES (:t, :material_type, :material_id, :description, :unit, NULL,
                :wastage_pct, :qty, 'manual', :note)
        RETURNING line_id"""), {"t": take_id, **line}).scalar()
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=t["item_id"],
         event="material_take.line_add", field="_material_take_line_add",
         new=f"{line['description']} {line['qty']} {line['unit']}",
         payload={"take_id": take_id, "line_id": lid, **{k: str(v) for k, v in line.items()}})
    return lid


def _line(db: Session, take_id: int, line_id: int) -> dict:
    r = db.execute(text("SELECT * FROM material_take_line WHERE line_id = :l AND take_id = :t"),
                   {"l": line_id, "t": take_id}).mappings().first()
    if r is None:
        raise NotFound()
    return dict(r)


def patch_line(db: Session, take_id: int, line_id: int, workspace_id: int, actor_id: int,
               changes: dict) -> None:
    t = _draft(db, take_id, workspace_id)
    old = _line(db, take_id, line_id)
    if old["source"] == "generated":
        # A generated line's material and unit are the generator's answer.
        for k in ("material_type", "material_id", "description", "unit"):
            if k in changes:
                raise Conflict("GENERATED_FIELD_READ_ONLY", field=k)
        # Changing wastage without an explicit qty re-derives qty from it.
        if "wastage_pct" in changes and "qty" not in changes:
            factor = 1 + Decimal(changes["wastage_pct"]) / 100
            changes["qty"] = (Decimal(old["qty_generated"]) * factor).quantize(_CENT, ROUND_CEILING)
    diff = {k: v for k, v in changes.items() if old.get(k) != v}
    if not diff:
        return
    sets = ", ".join(f"{k} = :{k}" for k in diff)
    db.execute(text(f"UPDATE material_take_line SET {sets} WHERE line_id = :l"), {**diff, "l": line_id})
    write_audit(db, workspace_id=workspace_id, actor_id=actor_id, event="material_take.line_edit",
                target=f"item:{t['item_id']}",
                payload={"take_id": take_id, "line_id": line_id,
                         "before": {k: str(old[k]) for k in diff},
                         "after": {k: str(v) for k, v in diff.items()}})
    for k, v in diff.items():
        write_edit_log(db, item_id=t["item_id"], actor_id=actor_id,
                       field=f"material_take.{old['description']}.{k}",
                       old_value=None if old[k] is None else str(old[k]),
                       new_value=None if v is None else str(v))


def delete_line(db: Session, take_id: int, line_id: int, workspace_id: int, actor_id: int) -> None:
    t = _draft(db, take_id, workspace_id)
    old = _line(db, take_id, line_id)
    db.execute(text("DELETE FROM material_take_line WHERE line_id = :l"), {"l": line_id})
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=t["item_id"],
         event="material_take.line_remove", field="_material_take_line_remove",
         old=f"{old['description']} {old['qty']} {old['unit']}",
         payload={"take_id": take_id, "line_id": line_id})


def approve(db: Session, take_id: int, workspace_id: int, actor_id: int) -> None:
    t = _draft(db, take_id, workspace_id)
    superseded = db.execute(text("""
        UPDATE material_take SET status = 'superseded'
         WHERE item_id = :i AND status = 'approved' RETURNING version"""),
        {"i": t["item_id"]}).scalar()
    db.execute(text("""
        UPDATE material_take SET status = 'approved', approved_by = :a, approved_at = now()
         WHERE take_id = :t"""), {"a": actor_id, "t": take_id})
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=t["item_id"],
         event="material_take.approve", field="_material_take_approve",
         old=None if superseded is None else f"v{superseded}", new=f"v{t['version']}",
         payload={"take_id": take_id, "version": t["version"], "superseded_version": superseded})


def review(db: Session, take_id: int, workspace_id: int, actor_id: int,
           outcome: str, note: str | None) -> int | None:
    """§19 impact review on an Outdated approved take. Partial / Full opens
    the next version as a draft, pre-generated from the live lines."""
    t = _take(db, take_id, workspace_id, lock=True)
    if t["status"] != "approved":
        raise Conflict("TAKE_NOT_APPROVED", status=t["status"])
    db.execute(text("""
        INSERT INTO material_take_review(take_id, detected_at, outcome, note, reviewed_by, reviewed_at)
        VALUES (:t, now(), :o, :n, :a, now())"""),
        {"t": take_id, "o": outcome, "n": note, "a": actor_id})
    _log(db, workspace_id=workspace_id, actor_id=actor_id, item_id=t["item_id"],
         event="material_take.review", field="_material_take_review", new=outcome,
         payload={"take_id": take_id, "outcome": outcome, "note": note})
    if outcome == "no_impact":
        return None
    return generate(db, t["item_id"], workspace_id, actor_id)

"""Line CRUD plus parts / hardware / labour add and remove.

Part of the estimating queries facade (see `queries.py`)."""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Any
from ..auth.audit import write_audit
from ._q_catalog import _resolve_hardware_snapshot, _resolve_part_snapshot
from ._q_core import _recompute_line_totals, _recompute_revision_totals, get_revision, lock_revision_for_update


# ============================================================================
# Line CRUD + parts/hardware/labour add/remove
# ============================================================================

def _assert_unlocked(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict:
    cur = get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if cur is None:
        raise ValueError("NOT_FOUND")
    if cur["locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    return cur


def _line_in_workspace(
    db: Session, *, line_id: int, workspace_id: int
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT l.*, r.status AS rev_status, r.locked_at AS rev_locked_at,
                   r.revision_id, e.workspace_id AS _wid
              FROM estimate_line l
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE l.line_id = :lid AND e.workspace_id = :w
            """
        ),
        {"lid": line_id, "w": workspace_id},
    ).mappings().first()
    return dict(row) if row else None


def create_line(
    db: Session, *, revision_id: int, workspace_id: int,
    actor_id: int, payload: dict,
) -> int:
    # Locks the revision row for the rest of this transaction, so a second
    # concurrent create_line() on the same revision blocks here instead of
    # reading the same MAX(seq) and inserting a duplicate (the race the
    # company-wide joinery_number_seq / po_number_seq sequences avoid by
    # allocating inside the INSERT — estimate_line has no such sequence,
    # so locking the parent row is the equivalent here).
    cur = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if cur is None:
        raise ValueError("NOT_FOUND")
    if cur["locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    next_seq = db.execute(
        text(
            """
            SELECT COALESCE(MAX(seq), 0) + 1 FROM estimate_line
             WHERE revision_id = :rid
            """
        ),
        {"rid": revision_id},
    ).scalar()
    lid = db.execute(
        text(
            """
            INSERT INTO estimate_line(
                revision_id, seq, description, qty, unit, notes
            )
            VALUES (:rid, :seq, :d, :q, :u, :n)
            RETURNING line_id
            """
        ),
        {
            "rid": revision_id,
            "seq": int(next_seq),
            "d": payload["description"],
            "q": payload.get("qty", Decimal("1")),
            "u": payload.get("unit", "EA"),
            "n": payload.get("notes"),
        },
    ).scalar()
    _recompute_line_totals(db, line_id=lid)
    _recompute_revision_totals(db, revision_id=revision_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_add", target=str(lid),
        payload={"revision_id": revision_id, "seq": int(next_seq)},
    )
    db.flush()
    return int(lid)


def patch_line(
    db: Session, *, line_id: int, workspace_id: int,
    actor_id: int, fields: dict[str, Any], clear_unit_sell_override: bool,
) -> dict | None:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        return None
    if line["rev_locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")

    columns = {
        "description": "description", "qty": "qty", "unit": "unit",
        "unit_sell_override": "unit_sell_override", "notes": "notes",
    }
    set_clauses = [
        f"{columns[k]} = :{k}" for k in fields if k in columns
    ]
    params = {k: v for k, v in fields.items() if k in columns}
    if clear_unit_sell_override:
        set_clauses.append("unit_sell_override = NULL")
    if not set_clauses:
        return line
    set_clauses.append("updated_at = now()")
    db.execute(
        text(
            f"""
            UPDATE estimate_line
               SET {', '.join(set_clauses)}
             WHERE line_id = :lid
            """
        ),
        {**params, "lid": line_id},
    )
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_edit", target=str(line_id),
        payload={"fields": list(fields.keys()),
                 "clear_unit_sell_override": clear_unit_sell_override},
    )
    return _line_in_workspace(
        db, line_id=line_id, workspace_id=workspace_id
    )


def delete_line(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int
) -> bool:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        return False
    if line["rev_locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    db.execute(
        text("DELETE FROM estimate_line WHERE line_id = :lid"),
        {"lid": line_id},
    )
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_delete", target=str(line_id),
        payload={"revision_id": line["revision_id"]},
    )
    return True


def reorder_lines(
    db: Session, *, revision_id: int, workspace_id: int,
    actor_id: int, ordered_line_ids: list[int],
) -> None:
    _assert_unlocked(db, revision_id=revision_id, workspace_id=workspace_id)
    have = {
        int(r) for r in db.execute(
            text(
                "SELECT line_id FROM estimate_line WHERE revision_id = :rid"
            ),
            {"rid": revision_id},
        ).scalars()
    }
    if set(ordered_line_ids) != have:
        raise ValueError("REORDER_SET_MISMATCH")
    for seq, lid in enumerate(ordered_line_ids, start=1):
        db.execute(
            text(
                """
                UPDATE estimate_line SET seq = :s WHERE line_id = :lid
                """
            ),
            {"s": seq, "lid": lid},
        )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.line_reorder", target=str(revision_id),
        payload={"ordered_line_ids": ordered_line_ids},
    )
    db.flush()


def add_part(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int, payload: dict
) -> int:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        raise ValueError("NOT_FOUND")
    if line["rev_locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    snap = _resolve_part_snapshot(
        db, workspace_id=workspace_id,
        material_type=payload["material_type"],
        material_id=payload["material_id"],
    )
    if snap is None:
        raise ValueError("CATALOG_ROW_NOT_FOUND")
    pid = db.execute(
        text(
            """
            INSERT INTO estimate_line_part(
                line_id, material_type, material_id,
                sku_snapshot, description_snapshot, supplier_snapshot,
                qty, len_mm, wid_mm, cost_per_unit_snapshot,
                paint_instruction, comment
            )
            VALUES (:lid, :mt, :mid, :sku, :desc, :sup, :q, :l, :wmm, :c, :pi, :cm)
            RETURNING part_id
            """
        ),
        {
            "lid": line_id,
            "mt": payload["material_type"],
            "mid": payload["material_id"],
            "sku": snap.get("sku"),
            "desc": snap.get("description"),
            "sup": snap.get("supplier"),
            "q": payload.get("qty", Decimal("1")),
            "l": payload.get("len_mm"),
            "wmm": payload.get("wid_mm"),
            "c": snap.get("cost") or 0,
            "pi": payload.get("paint_instruction", "NONE"),
            "cm": payload.get("comment"),
        },
    ).scalar()
    db.execute(
        text(
            "UPDATE estimate_line SET has_breakdown = true WHERE line_id = :lid"
        ),
        {"lid": line_id},
    )
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.part_add", target=str(pid),
        payload={
            "line_id": line_id,
            "material_type": payload["material_type"],
            "material_id": payload["material_id"],
        },
    )
    db.flush()
    return int(pid)


def remove_part(
    db: Session, *, part_id: int, workspace_id: int, actor_id: int
) -> bool:
    row = db.execute(
        text(
            """
            SELECT p.line_id, l.revision_id, r.locked_at, e.workspace_id AS _wid
              FROM estimate_line_part p
              JOIN estimate_line l ON l.line_id = p.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE p.part_id = :pid AND e.workspace_id = :w
            """
        ),
        {"pid": part_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return False
    if row["locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    db.execute(
        text("DELETE FROM estimate_line_part WHERE part_id = :pid"),
        {"pid": part_id},
    )
    _maybe_clear_has_breakdown(db, line_id=row["line_id"])
    _recompute_line_totals(db, line_id=row["line_id"])
    _recompute_revision_totals(db, revision_id=row["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.part_remove", target=str(part_id),
        payload={"line_id": int(row["line_id"])},
    )
    return True


def patch_part(
    db: Session, *, part_id: int, workspace_id: int, actor_id: int,
    fields: dict[str, Any],
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT p.part_id, p.line_id, l.revision_id, r.locked_at AS rev_locked_at
              FROM estimate_line_part p
              JOIN estimate_line l ON l.line_id = p.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE p.part_id = :pid AND e.workspace_id = :w
            """
        ),
        {"pid": part_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    if row["rev_locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    columns = {
        "qty": "qty", "len_mm": "len_mm", "wid_mm": "wid_mm",
        "paint_instruction": "paint_instruction", "comment": "comment",
    }
    set_clauses = [
        f"{columns[k]} = :{k}" for k in fields if k in columns
    ]
    params = {k: v for k, v in fields.items() if k in columns}
    if not set_clauses:
        return dict(row)
    db.execute(
        text(
            f"""
            UPDATE estimate_line_part
               SET {', '.join(set_clauses)}
             WHERE part_id = :pid
            """
        ),
        {**params, "pid": part_id},
    )
    _recompute_line_totals(db, line_id=int(row["line_id"]))
    _recompute_revision_totals(db, revision_id=int(row["revision_id"]))
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.part_edit", target=str(part_id),
        payload={"line_id": int(row["line_id"]), "fields": list(fields.keys())},
    )
    db.flush()
    return dict(row)


def patch_hardware(
    db: Session, *, hw_id: int, workspace_id: int, actor_id: int,
    fields: dict[str, Any],
) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT h.hw_id, h.line_id, l.revision_id, r.locked_at AS rev_locked_at
              FROM estimate_line_hardware h
              JOIN estimate_line l ON l.line_id = h.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE h.hw_id = :hid AND e.workspace_id = :w
            """
        ),
        {"hid": hw_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return None
    if row["rev_locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    columns = {"qty": "qty", "comment": "comment"}
    set_clauses = [
        f"{columns[k]} = :{k}" for k in fields if k in columns
    ]
    params = {k: v for k, v in fields.items() if k in columns}
    if not set_clauses:
        return dict(row)
    db.execute(
        text(
            f"""
            UPDATE estimate_line_hardware
               SET {', '.join(set_clauses)}
             WHERE hw_id = :hid
            """
        ),
        {**params, "hid": hw_id},
    )
    _recompute_line_totals(db, line_id=int(row["line_id"]))
    _recompute_revision_totals(db, revision_id=int(row["revision_id"]))
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.hardware_edit", target=str(hw_id),
        payload={"line_id": int(row["line_id"]), "fields": list(fields.keys())},
    )
    db.flush()
    return dict(row)


def add_hardware(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int, payload: dict
) -> int:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        raise ValueError("NOT_FOUND")
    if line["rev_locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    snap = _resolve_hardware_snapshot(
        db, workspace_id=workspace_id,
        material_type=payload["material_type"],
        material_id=payload["material_id"],
    )
    if snap is None:
        raise ValueError("CATALOG_ROW_NOT_FOUND")
    hid = db.execute(
        text(
            """
            INSERT INTO estimate_line_hardware(
                line_id, material_type, material_id,
                sku_snapshot, description_snapshot, supplier_snapshot,
                qty, cost_per_unit_snapshot, comment
            )
            VALUES (:lid, :mt, :mid, :sku, :desc, :sup, :q, :c, :cm)
            RETURNING hw_id
            """
        ),
        {
            "lid": line_id,
            "mt": payload["material_type"],
            "mid": payload["material_id"],
            "sku": snap.get("sku"),
            "desc": snap.get("description"),
            "sup": snap.get("supplier"),
            "q": payload.get("qty", Decimal("1")),
            "c": snap.get("cost") or 0,
            "cm": payload.get("comment"),
        },
    ).scalar()
    db.execute(
        text(
            "UPDATE estimate_line SET has_breakdown = true WHERE line_id = :lid"
        ),
        {"lid": line_id},
    )
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.hardware_add", target=str(hid),
        payload={
            "line_id": line_id,
            "material_type": payload["material_type"],
            "material_id": payload["material_id"],
        },
    )
    db.flush()
    return int(hid)


def remove_hardware(
    db: Session, *, hw_id: int, workspace_id: int, actor_id: int
) -> bool:
    row = db.execute(
        text(
            """
            SELECT h.line_id, l.revision_id, r.locked_at, e.workspace_id AS _wid
              FROM estimate_line_hardware h
              JOIN estimate_line l ON l.line_id = h.line_id
              JOIN estimate_revision r ON r.revision_id = l.revision_id
              JOIN estimate e ON e.estimate_id = r.estimate_id
             WHERE h.hw_id = :hid AND e.workspace_id = :w
            """
        ),
        {"hid": hw_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        return False
    if row["locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    db.execute(
        text("DELETE FROM estimate_line_hardware WHERE hw_id = :hid"),
        {"hid": hw_id},
    )
    _maybe_clear_has_breakdown(db, line_id=row["line_id"])
    _recompute_line_totals(db, line_id=row["line_id"])
    _recompute_revision_totals(db, revision_id=row["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.hardware_remove", target=str(hw_id),
        payload={"line_id": int(row["line_id"])},
    )
    return True


def upsert_labour(
    db: Session, *, line_id: int, workspace_id: int, actor_id: int,
    stage_key: str, hours: Decimal,
) -> int:
    line = _line_in_workspace(db, line_id=line_id, workspace_id=workspace_id)
    if line is None:
        raise ValueError("NOT_FOUND")
    if line["rev_locked_at"] is not None:
        raise ValueError("REVISION_LOCKED")
    rate = db.execute(
        text(
            """
            SELECT hourly_rate
              FROM workspace_labour_rate
             WHERE workspace_id = :w AND stage_key = :s
            """
        ),
        {"w": workspace_id, "s": stage_key},
    ).scalar() or Decimal("0")
    if Decimal(str(hours)) == 0:
        db.execute(
            text(
                """
                DELETE FROM estimate_line_labour
                 WHERE line_id = :lid AND stage_key = :s
                """
            ),
            {"lid": line_id, "s": stage_key},
        )
        _recompute_line_totals(db, line_id=line_id)
        _recompute_revision_totals(db, revision_id=line["revision_id"])
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="estimate.labour_clear", target=str(line_id),
            payload={"stage_key": stage_key},
        )
        return 0
    labour_id = db.execute(
        text(
            """
            INSERT INTO estimate_line_labour(
                line_id, stage_key, hours, rate_snapshot
            )
            VALUES (:lid, :s, :h, :r)
            ON CONFLICT (line_id, stage_key) DO UPDATE
              SET hours = EXCLUDED.hours, rate_snapshot = EXCLUDED.rate_snapshot
            RETURNING labour_id
            """
        ),
        {"lid": line_id, "s": stage_key, "h": hours, "r": rate},
    ).scalar()
    _recompute_line_totals(db, line_id=line_id)
    _recompute_revision_totals(db, revision_id=line["revision_id"])
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.labour_set", target=str(labour_id),
        payload={
            "line_id": line_id, "stage_key": stage_key,
            "hours": str(hours), "rate_snapshot": str(rate),
        },
    )
    db.flush()
    return int(labour_id)


def _maybe_clear_has_breakdown(db: Session, *, line_id: int) -> None:
    remaining = db.execute(
        text(
            """
            SELECT
              (SELECT COUNT(*) FROM estimate_line_part WHERE line_id = :lid) +
              (SELECT COUNT(*) FROM estimate_line_hardware WHERE line_id = :lid)
              AS n
            """
        ),
        {"lid": line_id},
    ).scalar()
    if not remaining:
        db.execute(
            text(
                "UPDATE estimate_line SET has_breakdown = false WHERE line_id = :lid"
            ),
            {"lid": line_id},
        )

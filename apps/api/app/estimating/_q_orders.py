"""Generate Orders: PO generation from a won quote.

Part of the estimating queries facade (see `queries.py`)."""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
import json
from ..auth.audit import write_audit
from ..catalog import queries as catalog_q
from ..orders import queries as orders_q
from ..orders.schemas import CreateOrderIn
from ..orders.schemas import CreateOrderLineIn
from ._q_catalog import _CATALOG_BY_TYPE, _ORDER_UNIT_BY_TYPE, _PART_CATALOG_BY_TYPE, _resolve_order_sources_batch
from ._q_core import get_revision, lock_revision_for_update
from ._q_loaders import revision_detail


# ============================================================================
# Generate Orders — PO generation from a won quote
# ============================================================================
#
# Sources from the revision's own line breakdown (estimate_line_part /
# estimate_line_hardware), not the converted project's items: `parts` only
# retains a real material FK for BOARD (Q447's `board_material_id`), so
# CUSTOM/BENCHTOP catalog links survive only as a comment string there —
# reading the revision directly keeps every material_id real. Also not from
# the Material Summary (#12): Q585 confirmed "no create-order-from-line in
# v1" for that surface.

def _material_rows(line: dict):
    """The parts/hardware breakdown rows of one quote line that name a real
    catalog material — the only rows that can become a PO line."""
    for r in line["parts"] + line["hardware"]:
        if r.get("material_id") is not None:
            yield r


def _line_material_keys(line: dict) -> set[tuple[str, int]]:
    """The distinct (material_type, material_id) one quote line references."""
    return {(r["material_type"], int(r["material_id"])) for r in _material_rows(line)}


def _material_state(line: dict, key: tuple[str, int]) -> str:
    """`generated` (a run ordered it), `dismissed` (ordered by hand) or `pending`."""
    row = (line.get("material_orders") or {}).get(key)
    if row is None:
        return "pending"
    return "generated" if row.get("orders_generated_at") is not None else "dismissed"


def _pending_keys(line: dict) -> set[tuple[str, int]]:
    """The materials on one quote line that are still to order."""
    return {k for k in _line_material_keys(line) if _material_state(line, k) == "pending"}


def _collect_order_materials(
    lines: list[dict], include=None,
) -> dict[tuple[str, int], dict]:
    """Consolidates every parts/hardware breakdown row with a real
    material_id across `lines`, summing qty per distinct (material_type,
    material_id) — the same SKU quoted on five different lines becomes one
    PO line for the total quantity, not five. Cut dimensions (len_mm/wid_mm)
    are deliberately dropped: they're cutting information for Production,
    not purchasing information for a PO. `include(line_id, key)`, when given,
    keeps only the (line, material) pairs it accepts."""
    materials: dict[tuple[str, int], dict] = {}
    for line in lines:
        lid = int(line["line_id"])
        for r in _material_rows(line):
            key = (r["material_type"], int(r["material_id"]))
            if include is not None and not include(lid, key):
                continue
            m = materials.setdefault(key, {
                "material_type": r["material_type"],
                "material_id": int(r["material_id"]),
                "qty": Decimal("0"),
                "fallback_sku": r.get("sku_snapshot"),
                "fallback_description": r.get("description_snapshot"),
                "fallback_cost": r.get("cost_per_unit_snapshot"),
            })
            m["qty"] += Decimal(str(r["qty"]))
    return materials


def _load_order_sources(
    db: Session, *, workspace_id: int, keys,
) -> dict[tuple[str, int], dict]:
    """Live catalog source (sku, description, cost, supplier) for each (type, id)."""
    ids_by_type: dict[str, list[int]] = {}
    for mtype, mid in keys:
        ids_by_type.setdefault(mtype, []).append(mid)
    sources: dict[tuple[str, int], dict] = {}
    for mtype, ids in ids_by_type.items():
        batch = _resolve_order_sources_batch(
            db, workspace_id=workspace_id, material_type=mtype, material_ids=ids,
        )
        for mid, src in batch.items():
            sources[(mtype, mid)] = src
    return sources


def _supplier_of(sources: dict, key: tuple[str, int]) -> int | None:
    src = sources.get(key)
    return int(src["supplier_id"]) if src and src["supplier_id"] is not None else None


def _build_order_groups(
    db: Session, *, workspace_id: int, lines: list[dict],
) -> tuple[dict[int, dict], list[dict], set[tuple[int, tuple[str, int]]], set[int], set[int]]:
    """Plans one Generate Orders run over `lines`. Returns (groups keyed by
    supplier_id, unassigned, ordered (line_id, material) pairs, covered line ids,
    held-back line ids).

    **Coverage is per material.** Each material on a line that is still pending is
    ordered when it has a default supplier, and stays pending when it has none (a PO
    needs a vendor — `purchase_orders.vendor_id` is NOT NULL). So a line with a board
    that has a supplier and a hinge that has none orders the board now and keeps the hinge
    to order once a supplier is linked (or to mark ordered by hand). Materials a run or a
    person already settled are never ordered again.

    A line is *covered* by this run when none of its pending materials lacks a supplier
    (nothing left to order on it) — including a line that references no catalog material at
    all (labour only: nothing to order, and it must not stay pending forever). A line is
    *held back* when a pending material has no supplier, i.e. it is only partly ordered, or
    not at all. `unassigned` lists those supplier-less pending materials (of every selected
    line)."""
    pending_by_line = {int(l["line_id"]): _pending_keys(l) for l in lines}
    pending_sums = _collect_order_materials(
        lines, include=lambda lid, key: key in pending_by_line[lid],
    )
    sources = _load_order_sources(db, workspace_id=workspace_id, keys=pending_sums.keys())

    ordered: set[tuple[int, tuple[str, int]]] = set()
    covered_ids: set[int] = set()
    held_ids: set[int] = set()
    for l in lines:
        lid = int(l["line_id"])
        missing = {k for k in pending_by_line[lid] if _supplier_of(sources, k) is None}
        (held_ids if missing else covered_ids).add(lid)
        ordered |= {(lid, k) for k in pending_by_line[lid] - missing}

    def entry_for(key: tuple[str, int], m: dict) -> dict:
        src = sources.get(key)
        return {
            "material_type": m["material_type"],
            "material_id": m["material_id"],
            "sku": src["sku"] if src else m["fallback_sku"],
            "description": src["description"] if src else m["fallback_description"],
            "qty": m["qty"],
            "unit": _ORDER_UNIT_BY_TYPE.get(m["material_type"], "EA"),
            "unit_cost": (
                (src["cost"] if src else m["fallback_cost"]) or Decimal("0")
            ),
            "archived": bool(src["archived"]) if src else False,
        }

    unassigned = [
        entry_for(k, m) for k, m in pending_sums.items()
        if _supplier_of(sources, k) is None
    ]
    groups: dict[int, dict] = {}
    for key, m in _collect_order_materials(
        lines, include=lambda lid, k: (lid, k) in ordered,
    ).items():
        supplier_id = _supplier_of(sources, key)
        group = groups.setdefault(supplier_id, {
            "supplier_id": supplier_id,
            "supplier_name": sources[key]["supplier_name"],
            "lines": [],
            "_type_counts": {},
        })
        group["lines"].append(entry_for(key, m))
        group["_type_counts"][key[0]] = group["_type_counts"].get(key[0], 0) + 1
    for group in groups.values():
        # The PO header's category is the material_type most represented in
        # it — most suppliers specialise, so this is a group's dominant type
        # in practice, not an arbitrary pick. Values match order_category's
        # joinery keys (0031) exactly: "BOARD".capitalize() == "Board", etc.
        dominant = max(group["_type_counts"].items(), key=lambda kv: kv[1])[0]
        group["category"] = dominant.capitalize()
        del group["_type_counts"]
    return groups, unassigned, ordered, covered_ids, held_ids


def _line_pending(l: dict) -> bool:
    """Still to order: no run covered it and nobody marked it ordered by hand."""
    return l.get("orders_generated_at") is None and l.get("orders_dismissed_at") is None


def _order_selection(
    rev: dict, lines: list[dict], include_line_ids: list[int] | None,
) -> tuple[list[dict], list[dict]]:
    """(lines the dialog can show, lines this run covers) — one rule for the
    preview and for `generate_orders`, so they cannot disagree.

    Shown: once converted, the lines included at Convert (a line the PM excluded
    there has no Joinery Item and shouldn't have materials ordered for it); before
    conversion nothing has been decided, so every line is shown as a what-if.
    Covered: with no `include_line_ids`, every shown line no earlier run has
    covered; with ids, exactly those. A line a run covered
    (`estimate_line.orders_generated_at`) is never covered again — that is the
    guard `estimate_revision.orders_generated_at` used to be for the whole quote.
    A line marked **ordered by hand** (`orders_dismissed_at`) is neither selected by default
    nor accepted by id (`LINES_DISMISSED`) until the dismissal is undone.
    Raises `UNKNOWN_LINE_IDS`, `LINES_ALREADY_GENERATED` and `LINES_DISMISSED` as ValueError."""
    shown = (
        [l for l in lines if l.get("included_at_convert")]
        if rev["converted_project_id"] is not None else list(lines)
    )
    if include_line_ids is None:
        return shown, [l for l in shown if _line_pending(l)]
    ids = set(include_line_ids)
    unknown = ids - {int(l["line_id"]) for l in lines}
    if unknown:
        raise ValueError(
            json.dumps({"code": "UNKNOWN_LINE_IDS", "line_ids": sorted(unknown)})
        )
    done = {
        int(l["line_id"]) for l in lines
        if int(l["line_id"]) in ids and l.get("orders_generated_at") is not None
    }
    if done:
        raise ValueError(
            json.dumps({"code": "LINES_ALREADY_GENERATED", "line_ids": sorted(done)})
        )
    dismissed = {
        int(l["line_id"]) for l in lines
        if int(l["line_id"]) in ids and l.get("orders_dismissed_at") is not None
    }
    if dismissed:
        raise ValueError(
            json.dumps({"code": "LINES_DISMISSED", "line_ids": sorted(dismissed)})
        )
    return shown, [l for l in lines if int(l["line_id"]) in ids]


def _line_keys_db(db: Session, line_id: int) -> list[tuple[str, int]]:
    """The distinct catalog materials one quote line references, from the database."""
    rows = db.execute(
        text(
            """
            SELECT material_type, material_id FROM estimate_line_part
             WHERE line_id = :l AND material_id IS NOT NULL
            UNION
            SELECT material_type, material_id FROM estimate_line_hardware
             WHERE line_id = :l AND material_id IS NOT NULL
            """
        ),
        {"l": line_id},
    ).all()
    return sorted((r[0], int(r[1])) for r in rows)


def _refresh_line_state(db: Session, line_id: int) -> None:
    """Re-derive `estimate_line.orders_generated_at` / `orders_dismissed_*` from the line's
    per-material rows (`estimate_line_material_order`), for a line that references catalog
    materials. While any material is pending the line is pending (both NULL). Once none is:
    if any was ordered by a run, the line reads *generated* (at the latest such time); if all
    were ordered by hand, it reads *dismissed* (with the latest dismissal's user and reason).
    A line with no catalog materials is left alone — its columns are written directly."""
    keys = _line_keys_db(db, line_id)
    if not keys:
        return
    rows = db.execute(
        text(
            """
            SELECT orders_generated_at, orders_dismissed_at,
                   orders_dismissed_by, orders_dismissed_reason
              FROM estimate_line_material_order WHERE line_id = :l
            """
        ),
        {"l": line_id},
    ).mappings().all()
    # Rows exist only for keys the line references, but a quote line's materials are
    # frozen once WON, so `len(rows) == len(keys)` means nothing is pending.
    settled = [r for r in rows if (r["orders_generated_at"] or r["orders_dismissed_at"])]
    gens = [r["orders_generated_at"] for r in settled if r["orders_generated_at"]]
    dis = [r for r in settled if r["orders_dismissed_at"]]
    if len(settled) < len(keys):
        values = (None, None, None, None)
    elif gens:
        values = (max(gens), None, None, None)
    else:
        last = max(dis, key=lambda r: r["orders_dismissed_at"])
        values = (
            None, last["orders_dismissed_at"], last["orders_dismissed_by"],
            last["orders_dismissed_reason"],
        )
    db.execute(
        text(
            """
            UPDATE estimate_line
               SET orders_generated_at = :g, orders_dismissed_at = :da,
                   orders_dismissed_by = :db, orders_dismissed_reason = :dr
             WHERE line_id = :l
            """
        ),
        {"g": values[0], "da": values[1], "db": values[2], "dr": values[3], "l": line_id},
    )


# The catalog event name a material type's row writes on an update (`catalog/routes.py`).
_CATALOG_EVENT_TYPE = {
    "BOARD": "board", "HARDWARE": "hardware", "CUSTOM": "custom_made",
    "BENCHTOP": "benchtop", "APPLIANCE": "appliance",
}


def link_material_supplier(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    material_type: str, material_id: int, supplier_id: int,
) -> None:
    """Give a material that has **no** supplier one, from Generate Orders.

    The narrow alternative to handing estimators `catalog:write` (or `orderbook:write`):
    it can only touch a catalog row that this revision's parts / hardware reference, and
    only while that row's `default_supplier_id` is NULL — it never re-points a link. It is
    recorded as the catalog's own `catalog.{type}.update` audit event, with the revision
    that caused it, so the catalog row's history shows it.

    Raises ValueError with a JSON body: NOT_FOUND (revision), MATERIAL_NOT_IN_REVISION,
    MATERIAL_NOT_FOUND, ALREADY_LINKED (carrying the current supplier), UNKNOWN_SUPPLIER.
    """
    if get_revision(db, revision_id=revision_id, workspace_id=workspace_id) is None:
        raise ValueError("NOT_FOUND")
    cfg = _CATALOG_BY_TYPE.get(material_type)
    if cfg is None:
        raise ValueError(json.dumps({"code": "MATERIAL_NOT_IN_REVISION"}))
    table, id_col, *_ = cfg
    child = "estimate_line_part" if material_type in _PART_CATALOG_BY_TYPE else "estimate_line_hardware"
    referenced = db.execute(
        text(
            f"""
            SELECT 1 FROM {child} c
              JOIN estimate_line l ON l.line_id = c.line_id
             WHERE l.revision_id = :rid AND c.material_type = :t AND c.material_id = :m
             LIMIT 1
            """
        ),
        {"rid": revision_id, "t": material_type, "m": material_id},
    ).first()
    if referenced is None:
        raise ValueError(json.dumps({"code": "MATERIAL_NOT_IN_REVISION"}))
    row = db.execute(
        text(
            f"SELECT default_supplier_id FROM {table}"
            f" WHERE {id_col} = :m AND workspace_id = :w FOR UPDATE"
        ),
        {"m": material_id, "w": workspace_id},
    ).first()
    if row is None:
        raise ValueError(json.dumps({"code": "MATERIAL_NOT_FOUND"}))
    if row[0] is not None:
        raise ValueError(json.dumps({"code": "ALREADY_LINKED", "supplier_id": int(row[0])}))
    if not catalog_q.supplier_in_workspace(db, vendor_id=supplier_id, workspace_id=workspace_id):
        raise ValueError(json.dumps(catalog_q.unknown_supplier_detail(supplier_id)))
    db.execute(
        text(f"UPDATE {table} SET default_supplier_id = :s WHERE {id_col} = :m AND workspace_id = :w"),
        {"s": supplier_id, "m": material_id, "w": workspace_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event=f"catalog.{_CATALOG_EVENT_TYPE[material_type]}.update",
        target=f"catalog.{_CATALOG_EVENT_TYPE[material_type]}:{material_id}",
        payload={
            "default_supplier_id": supplier_id,
            "via": "estimate.link_supplier", "revision_id": revision_id,
        },
    )
    db.flush()


def order_preview(
    db: Session, *, revision_id: int, workspace_id: int,
    include_line_ids: list[int] | None = None,
) -> dict | None:
    """The review screen before `generate_orders`: every distinct material
    across the selected lines, grouped by its live default supplier — same shape
    Convert's own `handover_preview` established for Q490. `lines` lists the
    quote lines the PM can tick (those an earlier run covered are listed but
    marked, and never selected); the groups are computed for exactly the lines
    flagged `selected`, which is every line still to order unless
    `include_line_ids` narrows it."""
    rev = get_revision(db, revision_id=revision_id, workspace_id=workspace_id)
    if rev is None:
        return None
    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    shown, selected = _order_selection(rev, detail["lines"], include_line_ids)
    groups, unassigned, _ordered, _covered, held_ids = _build_order_groups(
        db, workspace_id=workspace_id, lines=selected,
    )
    selected_ids = {int(l["line_id"]) for l in selected}
    # Every material the dialog lists, whatever its state, with its live supplier.
    shown_sums = _collect_order_materials(shown)
    sources = _load_order_sources(
        db, workspace_id=workspace_id, keys=shown_sums.keys(),
    )

    def material_entries(l: dict) -> list[dict]:
        out = []
        for key in sorted(_line_material_keys(l)):
            qty = sum(
                (Decimal(str(r["qty"])) for r in _material_rows(l)
                 if (r["material_type"], int(r["material_id"])) == key),
                Decimal("0"),
            )
            row = (l.get("material_orders") or {}).get(key) or {}
            src = sources.get(key)
            fb = shown_sums[key]
            out.append({
                "material_type": key[0], "material_id": key[1],
                "sku": src["sku"] if src else fb["fallback_sku"],
                "description": src["description"] if src else fb["fallback_description"],
                "qty": qty,
                "state": _material_state(l, key),
                "orders_generated_at": row.get("orders_generated_at"),
                "orders_dismissed_at": row.get("orders_dismissed_at"),
                "orders_dismissed_reason": row.get("orders_dismissed_reason"),
                "orders_dismissed_by_name": row.get("orders_dismissed_by_name"),
                "no_supplier": _supplier_of(sources, key) is None,
            })
        return out

    return {
        "revision_id": revision_id,
        "status": rev["status"],
        "converted_project_id": (
            int(rev["converted_project_id"])
            if rev["converted_project_id"] is not None else None
        ),
        "orders_generated_at": rev["orders_generated_at"],
        "lines": [
            {
                "line_id": int(l["line_id"]), "seq": l["seq"],
                "description": l["description"], "qty": l["qty"], "unit": l["unit"],
                "orders_generated_at": l.get("orders_generated_at"),
                "orders_dismissed_at": l.get("orders_dismissed_at"),
                "orders_dismissed_reason": l.get("orders_dismissed_reason"),
                "orders_dismissed_by_name": l.get("orders_dismissed_by_name"),
                "selected": int(l["line_id"]) in selected_ids,
                "held_back": int(l["line_id"]) in held_ids,
                "materials": material_entries(l),
            }
            for l in shown
        ],
        "groups": sorted(
            groups.values(), key=lambda g: g["supplier_name"] or ""
        ),
        "unassigned": unassigned,
    }


def dismiss_order_line(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    line_id: int, reason: str,
) -> None:
    """Mark a quote line **ordered by hand**, so it stops counting as "not yet ordered".

    For a line the PM ordered outside the system: nothing else can clear the quote's
    "N lines not yet ordered" bar for a line Generate Orders holds back. It is recorded in
    its own columns, not `orders_generated_at` (which means "a run made POs for this line").
    Allowed for any line still to order — held back or not — that was handed over at Convert.
    The reason is required (it is the only trail; the system cannot see the order).

    Raises ValueError with a JSON body: NOT_FOUND (revision), NOT_CONVERTED, LINE_NOT_FOUND,
    LINE_NOT_IN_HANDOVER, ALREADY_GENERATED, ALREADY_DISMISSED."""
    rev = lock_revision_for_update(db, revision_id=revision_id, workspace_id=workspace_id)
    if rev is None:
        raise ValueError("NOT_FOUND")
    if rev["converted_project_id"] is None:
        raise ValueError("NOT_CONVERTED")
    row = db.execute(
        text(
            """
            SELECT included_at_convert, orders_generated_at, orders_dismissed_at
              FROM estimate_line
             WHERE line_id = :lid AND revision_id = :rid
               FOR UPDATE
            """
        ),
        {"lid": line_id, "rid": revision_id},
    ).mappings().first()
    if row is None:
        raise ValueError(json.dumps({"code": "LINE_NOT_FOUND"}))
    if not row["included_at_convert"]:
        raise ValueError(json.dumps({"code": "LINE_NOT_IN_HANDOVER"}))
    if row["orders_generated_at"] is not None:
        raise ValueError(json.dumps({"code": "ALREADY_GENERATED"}))
    if row["orders_dismissed_at"] is not None:
        raise ValueError(json.dumps({"code": "ALREADY_DISMISSED"}))
    keys = _line_keys_db(db, line_id)
    if keys:
        # Per-material coverage: the one note covers every material still pending on the
        # line (those a run already ordered, or that were dismissed, are left as they are).
        for mtype, mid in keys:
            db.execute(
                text(
                    """
                    INSERT INTO estimate_line_material_order
                           (line_id, material_type, material_id,
                            orders_dismissed_at, orders_dismissed_by, orders_dismissed_reason)
                    VALUES (:lid, :t, :m, now(), :u, :why)
                    ON CONFLICT (line_id, material_type, material_id) DO NOTHING
                    """
                ),
                {"lid": line_id, "t": mtype, "m": mid, "u": actor_id, "why": reason},
            )
        _refresh_line_state(db, line_id)
    else:
        db.execute(
            text(
                """
                UPDATE estimate_line
                   SET orders_dismissed_at = now(), orders_dismissed_by = :u,
                       orders_dismissed_reason = :why
                 WHERE line_id = :lid
                """
            ),
            {"u": actor_id, "why": reason, "lid": line_id},
        )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.order_dismiss", target=str(revision_id),
        payload={"revision_id": revision_id, "line_id": line_id, "reason": reason},
    )
    db.flush()


def restore_order_line(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int, line_id: int,
) -> None:
    """Undo `dismiss_order_line`: every material of the line that was marked ordered by
    hand is pending again (a material a run ordered is left alone). Safe against ordering
    twice because the system never ordered what was dismissed. The reason being cleared is
    kept in the audit row. Raises NOT_FOUND (revision), LINE_NOT_FOUND, NOT_DISMISSED."""
    rev = lock_revision_for_update(db, revision_id=revision_id, workspace_id=workspace_id)
    if rev is None:
        raise ValueError("NOT_FOUND")
    row = db.execute(
        text(
            """
            SELECT orders_dismissed_at, orders_dismissed_reason
              FROM estimate_line
             WHERE line_id = :lid AND revision_id = :rid
               FOR UPDATE
            """
        ),
        {"lid": line_id, "rid": revision_id},
    ).mappings().first()
    if row is None:
        raise ValueError(json.dumps({"code": "LINE_NOT_FOUND"}))
    previous_reason = row["orders_dismissed_reason"]
    if _line_keys_db(db, line_id):
        removed = db.execute(
            text(
                """
                DELETE FROM estimate_line_material_order
                 WHERE line_id = :lid AND orders_dismissed_at IS NOT NULL
             RETURNING orders_dismissed_reason, orders_dismissed_at
                """
            ),
            {"lid": line_id},
        ).all()
        if not removed:
            raise ValueError(json.dumps({"code": "NOT_DISMISSED"}))
        previous_reason = max(removed, key=lambda r: r[1])[0]
        _refresh_line_state(db, line_id)
    else:
        if row["orders_dismissed_at"] is None:
            raise ValueError(json.dumps({"code": "NOT_DISMISSED"}))
        db.execute(
            text(
                """
                UPDATE estimate_line
                   SET orders_dismissed_at = NULL, orders_dismissed_by = NULL,
                       orders_dismissed_reason = NULL
                 WHERE line_id = :lid
                """
            ),
            {"lid": line_id},
        )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.order_undismiss", target=str(revision_id),
        payload={
            "revision_id": revision_id, "line_id": line_id,
            "previous_reason": previous_reason,
        },
    )
    db.flush()


def _locked_handover_line(
    db: Session, *, revision_id: int, workspace_id: int, line_id: int,
    material_type: str, material_id: int,
) -> None:
    """Shared checks for the per-material verbs: the revision is converted, the line is on it
    and was handed over, and the material is one the line references. Locks the revision.
    Raises NOT_FOUND, NOT_CONVERTED, LINE_NOT_FOUND, LINE_NOT_IN_HANDOVER,
    MATERIAL_NOT_ON_LINE."""
    rev = lock_revision_for_update(db, revision_id=revision_id, workspace_id=workspace_id)
    if rev is None:
        raise ValueError("NOT_FOUND")
    if rev["converted_project_id"] is None:
        raise ValueError("NOT_CONVERTED")
    row = db.execute(
        text(
            "SELECT included_at_convert FROM estimate_line"
            " WHERE line_id = :lid AND revision_id = :rid FOR UPDATE"
        ),
        {"lid": line_id, "rid": revision_id},
    ).mappings().first()
    if row is None:
        raise ValueError(json.dumps({"code": "LINE_NOT_FOUND"}))
    if not row["included_at_convert"]:
        raise ValueError(json.dumps({"code": "LINE_NOT_IN_HANDOVER"}))
    if (material_type, material_id) not in _line_keys_db(db, line_id):
        raise ValueError(json.dumps({"code": "MATERIAL_NOT_ON_LINE"}))


def dismiss_order_material(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    line_id: int, material_type: str, material_id: int, reason: str,
) -> None:
    """Mark **one material** on a quote line ordered by hand (required note). The line is
    done once none of its materials is pending. Raises the per-material checks' codes plus
    ALREADY_GENERATED (a run ordered it) and ALREADY_DISMISSED."""
    _locked_handover_line(
        db, revision_id=revision_id, workspace_id=workspace_id, line_id=line_id,
        material_type=material_type, material_id=material_id,
    )
    existing = db.execute(
        text(
            "SELECT orders_generated_at FROM estimate_line_material_order"
            " WHERE line_id = :l AND material_type = :t AND material_id = :m FOR UPDATE"
        ),
        {"l": line_id, "t": material_type, "m": material_id},
    ).first()
    if existing is not None:
        raise ValueError(json.dumps({
            "code": "ALREADY_GENERATED" if existing[0] is not None else "ALREADY_DISMISSED",
        }))
    db.execute(
        text(
            """
            INSERT INTO estimate_line_material_order
                   (line_id, material_type, material_id,
                    orders_dismissed_at, orders_dismissed_by, orders_dismissed_reason)
            VALUES (:l, :t, :m, now(), :u, :why)
            """
        ),
        {"l": line_id, "t": material_type, "m": material_id, "u": actor_id, "why": reason},
    )
    _refresh_line_state(db, line_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.order_material_dismiss", target=str(revision_id),
        payload={
            "revision_id": revision_id, "line_id": line_id,
            "material_type": material_type, "material_id": material_id, "reason": reason,
        },
    )
    db.flush()


def restore_order_material(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    line_id: int, material_type: str, material_id: int,
) -> None:
    """Undo `dismiss_order_material`: the material is pending again. Raises the per-material
    checks' codes plus NOT_DISMISSED (it is pending, or a run ordered it)."""
    _locked_handover_line(
        db, revision_id=revision_id, workspace_id=workspace_id, line_id=line_id,
        material_type=material_type, material_id=material_id,
    )
    removed = db.execute(
        text(
            """
            DELETE FROM estimate_line_material_order
             WHERE line_id = :l AND material_type = :t AND material_id = :m
               AND orders_dismissed_at IS NOT NULL
         RETURNING orders_dismissed_reason
            """
        ),
        {"l": line_id, "t": material_type, "m": material_id},
    ).first()
    if removed is None:
        raise ValueError(json.dumps({"code": "NOT_DISMISSED"}))
    _refresh_line_state(db, line_id)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.order_material_undismiss", target=str(revision_id),
        payload={
            "revision_id": revision_id, "line_id": line_id,
            "material_type": material_type, "material_id": material_id,
            "previous_reason": removed[0],
        },
    )
    db.flush()


def generate_orders(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    include_line_ids: list[int] | None = None,
) -> dict:
    """Plan V1 §21's "Create PO" (Q505) made real: materialises the
    revision's material breakdown into draft purchase orders, one per
    supplier, reusing the existing orders module end-to-end (`create_order`
    / `add_line`) rather than inventing a parallel order entity — the same
    "purchase_orders + po_line_items ARE the order layer" stance Q502/Q553
    already established for #10.

    Requires the revision already converted (a PO needs a real project to
    attach to — `409 NOT_CONVERTED` otherwise). A run covers the lines in
    `include_line_ids` (default: every line included at Convert that no earlier
    run covered) and marks each `estimate_line.orders_generated_at`, which is
    set once and never cleared — the quote is frozen, so there is no
    legitimate way to order a line twice. So a run can cover part of a quote
    and a later run the rest: `409 LINES_ALREADY_GENERATED` for a line an
    earlier run covered, `409 ORDERS_ALREADY_GENERATED` when no default
    selection is left, `409 NO_LINES_SELECTED` for an empty one. Each run makes
    its own POs, so a supplier used by two runs gets two draft POs.
    `estimate_revision.orders_generated_at` is the time of the most recent run.
    **Coverage is per material** (see `_build_order_groups`): every pending material
    that has a default supplier is ordered; one with none stays pending (returned in
    `unassigned`) and its line in `uncovered_line_ids`, to be ordered by a later run once a
    supplier is linked, or marked ordered by hand. Each ordered (line, material) is recorded
    in `estimate_line_material_order` and never ordered again; a line's own stamp is set once
    nothing on it is pending (or directly, for a line with no catalog material). A run that
    would create no order at all but has supplier-less materials is
    `409 NOTHING_ORDERABLE` and writes nothing."""
    rev = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if rev is None:
        raise ValueError("NOT_FOUND")
    if rev["converted_project_id"] is None:
        raise ValueError("NOT_CONVERTED")

    estimate_no = db.execute(
        text("SELECT estimate_no FROM estimate WHERE estimate_id = :eid"),
        {"eid": rev["estimate_id"]},
    ).scalar()

    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    shown, selected_lines = _order_selection(rev, detail["lines"], include_line_ids)
    if not selected_lines:
        # Every default line already ordered is the old "ran once" answer; an
        # empty explicit selection (or a quote with nothing to order) is not.
        if include_line_ids is None and any(not _line_pending(l) for l in shown):
            raise ValueError("ORDERS_ALREADY_GENERATED")
        raise ValueError("NO_LINES_SELECTED")
    groups, unassigned, ordered, covered_ids, held_ids = _build_order_groups(
        db, workspace_id=workspace_id, lines=selected_lines,
    )
    if not groups and unassigned:
        # Nothing would be ordered. Marking the lines covered here is what used to
        # lock a quote out of ever ordering them once a supplier was linked.
        raise ValueError(
            json.dumps({
                "code": "NOTHING_ORDERABLE",
                "unassigned_count": len(unassigned),
            })
        )
    uncovered_ids = sorted(held_ids)

    po_ids: list[int] = []
    lines_created = 0
    for group in groups.values():
        code, order = orders_q.create_order(
            db, workspace_id=workspace_id,
            payload=CreateOrderIn(
                vendor_id=group["supplier_id"],
                description=(
                    f"Materials for {estimate_no} — "
                    f"{group['supplier_name'] or 'supplier'}"
                ),
                category=group["category"],
                project_id=int(rev["converted_project_id"]),
                attributes={"generated_from_revision_id": revision_id},
            ),
            actor_id=actor_id,
        )
        if code != "OK":
            # Every default_supplier_id write path today keeps the vendor
            # workspace-consistent, so this shouldn't be reachable — but
            # the FK itself carries no workspace check, and failing loudly
            # beats an unhandled TypeError on `order["po_id"]` below.
            raise ValueError(
                json.dumps({"code": code, "supplier_id": group["supplier_id"]})
            )
        po_ids.append(int(order["po_id"]))
        for entry in group["lines"]:
            orders_q.add_line(
                db, po_id=order["po_id"], workspace_id=workspace_id,
                payload=CreateOrderLineIn(
                    item_description=entry["description"] or entry["sku"] or "material",
                    quantity=entry["qty"],
                    unit_price=entry["unit_cost"],
                    sku=entry["sku"],
                    unit=entry["unit"],
                    material_table=_CATALOG_BY_TYPE[entry["material_type"]][0],
                    material_id=entry["material_id"],
                ),
                actor_id=actor_id,
            )
            lines_created += 1

    # What this run ordered can never be ordered again: each (line, material) it made a PO
    # line for is recorded, and the line's own stamp is re-derived (set once no material on
    # it is pending). A line that references no catalog material is stamped directly. A
    # material with no supplier is not recorded, so a later run can still order it. The
    # revision's own timestamp is just "the most recent run".
    for lid, (mtype, mid) in sorted(ordered):
        db.execute(
            text(
                """
                INSERT INTO estimate_line_material_order
                       (line_id, material_type, material_id, orders_generated_at)
                VALUES (:l, :t, :m, now())
                """
            ),
            {"l": lid, "t": mtype, "m": mid},
        )
    no_material_ids = sorted(
        int(l["line_id"]) for l in selected_lines
        if int(l["line_id"]) in covered_ids and not _line_material_keys(l)
    )
    if no_material_ids:
        db.execute(
            text(
                "UPDATE estimate_line SET orders_generated_at = now()"
                " WHERE line_id = ANY(:ids)"
            ),
            {"ids": no_material_ids},
        )
    for lid in sorted({lid for lid, _k in ordered}):
        _refresh_line_state(db, lid)
    db.execute(
        text(
            "UPDATE estimate_revision SET orders_generated_at = now()"
            " WHERE revision_id = :rid"
        ),
        {"rid": revision_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.generate_orders", target=str(revision_id),
        payload={
            "revision_id": revision_id,
            "project_id": int(rev["converted_project_id"]),
            "orders_created": len(po_ids),
            "lines_created": lines_created,
            "po_ids": po_ids,
            "unassigned_count": len(unassigned),
            # The lines this run covered (what migration 0048's backfill reads).
            "included_line_ids": sorted(covered_ids),
            "uncovered_line_ids": uncovered_ids,
            "materials_ordered": [
                {"line_id": lid, "material_type": k[0], "material_id": k[1]}
                for lid, k in sorted(ordered)
            ],
        },
    )
    db.flush()
    return {
        "orders_created": len(po_ids),
        "lines_created": lines_created,
        "po_ids": po_ids,
        "unassigned": unassigned,
        "uncovered_line_ids": uncovered_ids,
    }

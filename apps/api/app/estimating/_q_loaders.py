"""Detail loaders (GET endpoints, PDF, Convert).

Part of the estimating queries facade (see `queries.py`)."""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from ._q_core import get_customer, get_estimate_summary, get_revision


# ============================================================================
# Detail loaders (used by GET endpoints + PDF + Convert)
# ============================================================================

def revision_detail(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict | None:
    rev = get_revision(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if rev is None:
        return None
    lines = db.execute(
        text(
            """
            SELECT l.line_id, l.seq, l.description, l.qty, l.unit, l.has_breakdown,
                   l.material_cost, l.labour_cost, l.total_cost,
                   l.unit_sell_override, l.notes, l.included_at_convert,
                   l.orders_generated_at,
                   l.orders_dismissed_at, l.orders_dismissed_reason,
                   u.full_name AS orders_dismissed_by_name
              FROM estimate_line l
              LEFT JOIN app_user u ON u.id = l.orders_dismissed_by
             WHERE l.revision_id = :rid
             ORDER BY l.seq, l.line_id
            """
        ),
        {"rid": revision_id},
    ).mappings().all()
    line_ids = [int(l["line_id"]) for l in lines]
    parts_by_line: dict[int, list[dict]] = {lid: [] for lid in line_ids}
    hw_by_line: dict[int, list[dict]] = {lid: [] for lid in line_ids}
    lab_by_line: dict[int, list[dict]] = {lid: [] for lid in line_ids}
    if line_ids:
        for r in db.execute(
            text(
                """
                SELECT part_id, line_id, material_type, material_id,
                       sku_snapshot, description_snapshot, supplier_snapshot,
                       qty, len_mm, wid_mm, cost_per_unit_snapshot,
                       cost_extended, paint_instruction, comment
                  FROM estimate_line_part
                 WHERE line_id = ANY(:ids)
                 ORDER BY part_id
                """
            ),
            {"ids": line_ids},
        ).mappings():
            parts_by_line[int(r["line_id"])].append(dict(r))
        for r in db.execute(
            text(
                """
                SELECT hw_id, line_id, material_type, material_id,
                       sku_snapshot, description_snapshot, supplier_snapshot,
                       qty, cost_per_unit_snapshot, cost_extended, comment
                  FROM estimate_line_hardware
                 WHERE line_id = ANY(:ids)
                 ORDER BY hw_id
                """
            ),
            {"ids": line_ids},
        ).mappings():
            hw_by_line[int(r["line_id"])].append(dict(r))
        for r in db.execute(
            text(
                """
                SELECT labour_id, line_id, stage_key, hours,
                       rate_snapshot, cost_extended
                  FROM estimate_line_labour
                 WHERE line_id = ANY(:ids)
                 ORDER BY stage_key
                """
            ),
            {"ids": line_ids},
        ).mappings():
            lab_by_line[int(r["line_id"])].append(dict(r))
    mo_by_line: dict[int, dict[tuple[str, int], dict]] = {lid: {} for lid in line_ids}
    if line_ids:
        for r in db.execute(
            text(
                """
                SELECT m.line_id, m.material_type, m.material_id,
                       m.orders_generated_at, m.orders_dismissed_at,
                       m.orders_dismissed_reason,
                       u.full_name AS orders_dismissed_by_name
                  FROM estimate_line_material_order m
                  LEFT JOIN app_user u ON u.id = m.orders_dismissed_by
                 WHERE m.line_id = ANY(:ids)
                """
            ),
            {"ids": line_ids},
        ).mappings():
            mo_by_line[int(r["line_id"])][
                (r["material_type"], int(r["material_id"]))
            ] = dict(r)

    markup_pct = rev["markup_pct"] or Decimal("0")
    lines_out = []
    for l in lines:
        lid = int(l["line_id"])
        total_cost = Decimal(str(l["total_cost"] or 0))
        if l["unit_sell_override"] is not None:
            unit_sell = Decimal(str(l["unit_sell_override"]))
        else:
            unit_sell = total_cost * (Decimal("1") + Decimal(str(markup_pct)) / Decimal("100"))
        qty = Decimal(str(l["qty"]))
        total_sell = (unit_sell * qty).quantize(Decimal("0.01"))
        lines_out.append(
            {
                **dict(l),
                "unit_sell": unit_sell.quantize(Decimal("0.01")),
                "total_sell": total_sell,
                "parts": parts_by_line[lid],
                "hardware": hw_by_line[lid],
                "labour": lab_by_line[lid],
                # Per-material order state (ordered / ordered by hand); a material
                # with no entry is still pending. Not part of `LineOut`.
                "material_orders": mo_by_line[lid],
            }
        )

    subtotal_sell = Decimal(str(rev["subtotal_sell"] or 0))
    total_inc_gst = Decimal(str(rev["total_inc_gst"] or 0))
    gst_amount = (total_inc_gst - subtotal_sell).quantize(Decimal("0.01"))

    return {
        **rev,
        "subtotal_cost": Decimal(str(rev["subtotal_cost"] or 0)),
        "subtotal_sell": subtotal_sell,
        "total_inc_gst": total_inc_gst,
        "gst_amount": gst_amount,
        "lines": lines_out,
    }


def estimate_detail(
    db: Session, *, estimate_id: int, workspace_id: int
) -> dict | None:
    summary = get_estimate_summary(
        db, estimate_id=estimate_id, workspace_id=workspace_id
    )
    if summary is None:
        return None
    cust = get_customer(
        db, customer_id=summary["customer_id"], workspace_id=workspace_id
    )
    rev_rows = db.execute(
        text(
            """
            SELECT revision_id
              FROM estimate_revision
             WHERE estimate_id = :eid
             ORDER BY rev_no DESC
            """
        ),
        {"eid": estimate_id},
    ).scalars().all()
    revisions = [
        revision_detail(db, revision_id=int(rid), workspace_id=workspace_id)
        for rid in rev_rows
    ]
    return {
        **summary,
        "customer": cust,
        "revisions": revisions,
    }

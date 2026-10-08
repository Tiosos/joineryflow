"""Convert-to-Project.

Part of the estimating queries facade (see `queries.py`)."""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
import json
from ..auth.audit import write_audit
from ..edit_log import write_edit_log
from ._q_catalog import STAGE_KEYS, _resolve_hardware_snapshot, _resolve_part_snapshot
from ._q_core import get_revision, lock_revision_for_update
from ._q_loaders import revision_detail


# ============================================================================
# Convert-to-Project
# ============================================================================

_PHC_TYPE_MAP = {
    "HARDWARE":  "HARDWARE",
    "APPLIANCE": "APPLIANCE",
}


def handover_preview(
    db: Session, *, revision_id: int, workspace_id: int
) -> dict | None:
    """What Q490's PM review screen shows before Convert: the lines that
    would become Joinery Items, and the contract value Convert will set by
    default (the quote's own GST-inclusive total — nothing to re-enter)."""
    rev = get_revision(db, revision_id=revision_id, workspace_id=workspace_id)
    if rev is None:
        return None
    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    return {
        "revision_id": revision_id,
        "status": rev["status"],
        "already_converted_project_id": (
            int(rev["converted_project_id"])
            if rev["converted_project_id"] is not None else None
        ),
        "proposed_contract_value": detail["total_inc_gst"],
        "lines": [
            {
                "line_id": int(l["line_id"]),
                "seq": l["seq"],
                "description": l["description"],
                "qty": l["qty"],
                "has_breakdown": l["has_breakdown"],
                "total_sell": l["total_sell"],
            }
            for l in detail["lines"]
        ],
    }


def convert_to_project(
    db: Session, *, revision_id: int, workspace_id: int, actor_id: int,
    include_line_ids: list[int] | None = None,
    contract_value: Decimal | None = None,
) -> dict:
    """Q490: `include_line_ids` (default: every line) is the PM's selection
    from the handover-preview screen — an excluded line simply becomes no
    Joinery Item, everything else about it (its place in the quote) is
    unaffected. `contract_value` (default: the quote's own GST-inclusive
    total) becomes the immutable `project_contract.original_value` (Q491) —
    it is independent of which lines were included, since a lump-sum line
    left out of the Item list can still be part of what the client is
    paying for."""
    rev = lock_revision_for_update(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    if rev is None:
        raise ValueError("NOT_FOUND")
    if rev["status"] != "WON":
        raise ValueError(
            json.dumps(
                {"code": "BAD_STATUS", "status": rev["status"]}
            )
        )
    if rev["converted_project_id"] is not None:
        raise ValueError(
            json.dumps(
                {"code": "ALREADY_CONVERTED",
                 "project_id": int(rev["converted_project_id"])}
            )
        )

    est = db.execute(
        text(
            """
            SELECT e.estimate_id, e.estimate_no, e.title, e.site_address,
                   e.customer_id, c.name AS customer_name, c.archived_at
              FROM estimate e
              JOIN customer c ON c.customer_id = e.customer_id
             WHERE e.estimate_id = :eid AND e.workspace_id = :w
            """
        ),
        {"eid": rev["estimate_id"], "w": workspace_id},
    ).mappings().first()
    if est is None:
        raise ValueError("ESTIMATE_NOT_FOUND")
    if est["archived_at"] is not None:
        raise ValueError("CUSTOMER_ARCHIVED")

    detail = revision_detail(
        db, revision_id=revision_id, workspace_id=workspace_id
    )
    total_inc_gst = detail["total_inc_gst"]
    all_line_ids = {int(l["line_id"]) for l in detail["lines"]}
    if include_line_ids is None:
        selected_ids = all_line_ids
    else:
        unknown = set(include_line_ids) - all_line_ids
        if unknown:
            raise ValueError(
                json.dumps({"code": "UNKNOWN_LINE_IDS", "line_ids": sorted(unknown)})
            )
        selected_ids = set(include_line_ids)
    detail["lines"] = [l for l in detail["lines"] if int(l["line_id"]) in selected_ids]
    final_contract_value = (
        contract_value if contract_value is not None else total_inc_gst
    )
    # Records which lines actually became Joinery Items — `generate_orders`
    # (below) defaults to this set rather than every line in the revision,
    # so a line the PM excluded here never gets its materials ordered.
    if selected_ids:
        db.execute(
            text(
                "UPDATE estimate_line SET included_at_convert = true"
                " WHERE line_id = ANY(:ids)"
            ),
            {"ids": list(selected_ids)},
        )

    failures: list[dict] = []
    for line in detail["lines"]:
        for p in line["parts"]:
            if p.get("material_id") is None:
                continue
            ok = _resolve_part_snapshot(
                db, workspace_id=workspace_id,
                material_type=p["material_type"],
                material_id=int(p["material_id"]),
            )
            if ok is None:
                failures.append({
                    "line_id": int(line["line_id"]),
                    "material_type": p["material_type"],
                    "material_id": int(p["material_id"]),
                    "kind": "part",
                })
        for h in line["hardware"]:
            if h.get("material_id") is None:
                continue
            ok = _resolve_hardware_snapshot(
                db, workspace_id=workspace_id,
                material_type=h["material_type"],
                material_id=int(h["material_id"]),
            )
            if ok is None:
                failures.append({
                    "line_id": int(line["line_id"]),
                    "material_type": h["material_type"],
                    "material_id": int(h["material_id"]),
                    "kind": "hardware",
                })
    if failures:
        raise ValueError(
            json.dumps({"code": "CATALOG_GONE", "failures": failures})
        )

    project_code = est["estimate_no"]
    project_name = f"{est['title']} [{est['estimate_no']}]"
    new_project_id = db.execute(
        text(
            """
            INSERT INTO projects(
                project_code, name, pm_id, workspace_id,
                customer_id, estimate_revision_id, status, created_by
            )
            VALUES (:code, :name, :pm, :w, :cid, :rid, 'Current', :cb)
            RETURNING project_id
            """
        ),
        {
            "code": project_code,
            "name": project_name,
            "pm": actor_id,
            "w": workspace_id,
            "cid": est["customer_id"],
            "rid": revision_id,
            "cb": str(actor_id),
        },
    ).scalar()

    db.execute(
        text(
            """
            INSERT INTO project_contract(project_id, original_value, created_by)
            VALUES (:p, :v, :a)
            """
        ),
        {"p": int(new_project_id), "v": final_contract_value, "a": actor_id},
    )

    distinct_hw: dict[tuple[str, int], None] = {}
    for line in detail["lines"]:
        for h in line["hardware"]:
            if h.get("material_id") is None:
                continue
            phc_type = _PHC_TYPE_MAP.get(h["material_type"])
            if phc_type is None:
                continue
            distinct_hw[(phc_type, int(h["material_id"]))] = None

    phc_id_by_pair: dict[tuple[str, int], int] = {}
    phc_added = 0
    for (mtype, mid) in distinct_hw:
        cid = db.execute(
            text(
                """
                INSERT INTO project_hardware_catalog(
                    project_id, material_type, material_id, added_by
                )
                VALUES (:p, :mt, :mid, :a)
                RETURNING catalog_id
                """
            ),
            {"p": new_project_id, "mt": mtype, "mid": mid, "a": actor_id},
        ).scalar()
        phc_id_by_pair[(mtype, mid)] = int(cid)
        phc_added += 1

    items_created = 0
    parts_created = 0
    hw_lines_created = 0

    for line in detail["lines"]:
        # `num` comes from the shared `joinery_number_seq` (0027 / Q541).
        #
        # This replaced `SELECT COALESCE(MAX(num), 0) + 1 FROM items`, a
        # read-then-insert with no lock: two conversions running at once both
        # read the same maximum and the loser died on `items_num_key`.
        # Allocating inside the INSERT removes both the race and a round-trip
        # per line.
        item_id = db.execute(
            text(
                """
                INSERT INTO items(
                    num, project_id, description, qty, status
                )
                VALUES (nextval('joinery_number_seq'), :p, :d, :q, 'LIVE')
                RETURNING item_id
                """
            ),
            {
                "p": int(new_project_id),
                "d": line["description"],
                "q": int(Decimal(str(line["qty"])).quantize(Decimal("1"))),
            },
        ).scalar()
        items_created += 1

        for sk in STAGE_KEYS:
            db.execute(
                text(
                    """
                    INSERT INTO item_stages(item_id, stage_key)
                    VALUES (:i, :s)
                    """
                ),
                {"i": item_id, "s": sk},
            )

        write_edit_log(
            db, item_id=int(item_id), actor_id=actor_id,
            field="_create", old_value=None,
            new_value=f"converted from {est['estimate_no']} line {int(line['seq'])}",
        )

        if not line["has_breakdown"]:
            continue

        module_id = db.execute(
            text(
                """
                INSERT INTO modules(item_id, module_no, name)
                VALUES (:i, '1', 'Module 1')
                RETURNING module_id
                """
            ),
            {"i": item_id},
        ).scalar()

        for part_seq, p in enumerate(line["parts"], start=1):
            board_mid = (
                int(p["material_id"])
                if p["material_type"] == "BOARD" and p.get("material_id") is not None
                else None
            )
            comment = p.get("comment")
            if p["material_type"] in ("CUSTOM", "BENCHTOP") and p.get("material_id"):
                tag = f"[material: {p['material_type'].lower()}#{int(p['material_id'])}]"
                comment = f"{tag} {comment or ''}".strip()
            db.execute(
                text(
                    """
                    INSERT INTO parts(
                        module_id, seq, qty, part_name, len_mm, wid_mm,
                        board_material_id, paint_instruction, comment
                    )
                    VALUES (:m, :s, :q, :n, :l, :w, :bmid, :pi, :c)
                    """
                ),
                {
                    "m": int(module_id),
                    # Fixed later. Was hardcoded 1 for every part in a
                    # module — fine while every seed/test fixture had at
                    # most one part per line, but `uq_parts_module_seq`
                    # (module_id, seq) rejects a second part with the same
                    # seq, so any WON quote line with more than one part
                    # failed to convert. Found live-testing PO generation
                    # (#13's `test_generate_orders_creates_one_po_per_
                    # supplier_with_consolidated_lines`-style fixture, a
                    # line with two different BOARD parts).
                    "s": part_seq,
                    "q": int(Decimal(str(p["qty"])).quantize(Decimal("1"))),
                    "n": p.get("description_snapshot") or p.get("sku_snapshot") or "part",
                    "l": p.get("len_mm"),
                    "w": p.get("wid_mm"),
                    "bmid": board_mid,
                    "pi": p.get("paint_instruction", "NONE"),
                    "c": comment,
                },
            )
            parts_created += 1

        for h in line["hardware"]:
            if h.get("material_id") is None:
                continue
            phc_type = _PHC_TYPE_MAP[h["material_type"]]
            phc_id = phc_id_by_pair[(phc_type, int(h["material_id"]))]
            db.execute(
                text(
                    """
                    INSERT INTO item_hardware_lines(
                        item_id, qty, catalog_id, note
                    )
                    VALUES (:i, :q, :c, :n)
                    """
                ),
                {
                    "i": item_id,
                    "q": int(Decimal(str(h["qty"])).quantize(Decimal("1"))),
                    "c": phc_id,
                    "n": h.get("comment"),
                },
            )
            hw_lines_created += 1

    db.execute(
        text(
            """
            UPDATE estimate_revision
               SET converted_project_id = :p
             WHERE revision_id = :rid
            """
        ),
        {"p": int(new_project_id), "rid": revision_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="estimate.convert", target=str(revision_id),
        payload={
            "revision_id": int(revision_id),
            "estimate_id": int(rev["estimate_id"]),
            "project_id": int(new_project_id),
            "items_created": items_created,
            "parts_created": parts_created,
            "hardware_lines_created": hw_lines_created,
            "project_hardware_catalog_added": phc_added,
            "included_line_ids": sorted(selected_ids),
            "excluded_line_ids": sorted(all_line_ids - selected_ids),
            "contract_value": str(final_contract_value),
        },
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="project.create", target=str(new_project_id),
        payload={
            "from_estimate_revision_id": int(revision_id),
            "estimate_no": est["estimate_no"],
            "customer_id": int(est["customer_id"]),
            "name": project_name,
        },
    )
    db.flush()
    return {
        "project_id": int(new_project_id),
        "project_code": project_code,
        "items_created": items_created,
        "parts_created": parts_created,
        "hardware_lines_created": hw_lines_created,
        "project_hardware_catalog_added": phc_added,
        "contract_value": final_contract_value,
    }

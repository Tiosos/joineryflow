"""SQL helpers for project_contract + variations (Q491).

`original_value` is set once, at handover (`estimating.convert_to_project`),
and never overwritten (§17). `current_value` is computed on read as
`original_value + SUM(variation.amount_delta)` over the *Approved* variations
(Q608) — never stored, so there is nowhere for it to drift out of sync with its
own history. A Draft or Rejected variation is listed but never counted.
"""
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..row_types import live_joinery_items


def _project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    row = db.execute(
        text("SELECT 1 FROM projects WHERE project_id = :p AND workspace_id = :w"),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def get_contract(db: Session, *, project_id: int, workspace_id: int) -> dict | None:
    if not _project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        return None
    header = db.execute(
        text(
            "SELECT project_id, original_value, created_at, created_by "
            "FROM project_contract WHERE project_id = :p"
        ),
        {"p": project_id},
    ).mappings().first()
    if header is None:
        return None
    variations = db.execute(
        text(
            """
            SELECT v.variation_id, v.project_id, v.description, v.amount_delta,
                   v.created_at, v.created_by, cu.full_name AS created_by_name,
                   v.status, v.decided_by, du.full_name AS decided_by_name, v.decided_at, v.decision_note,
                   v.voided_by, vu.full_name AS voided_by_name, v.voided_at, v.void_reason,
                   v.number, v.reason, v.requester, v.requested_on, v.cost_impact, v.time_impact_days
              FROM project_contract_variation v
              LEFT JOIN app_user cu ON cu.id = v.created_by
              LEFT JOIN app_user du ON du.id = v.decided_by
              LEFT JOIN app_user vu ON vu.id = v.voided_by
             WHERE v.project_id = :p
             ORDER BY v.created_at, v.variation_id
            """
        ),
        {"p": project_id},
    ).mappings().all()
    linked: dict[int, list[dict]] = {}
    for r in db.execute(
        text(
            f"""
            SELECT l.variation_id, i.item_id, i.num, i.description
              FROM project_contract_variation_item l
              JOIN items i ON i.item_id = l.item_id
             WHERE l.variation_id = ANY(:v) AND {live_joinery_items("i")}
             ORDER BY i.num, i.item_id
            """
        ),
        {"v": [v["variation_id"] for v in variations]},
    ).mappings():
        linked.setdefault(r["variation_id"], []).append(
            {"item_id": r["item_id"], "num": r["num"], "description": r["description"]}
        )
    current_value = Decimal(str(header["original_value"])) + sum(
        (Decimal(str(v["amount_delta"])) for v in variations if v["status"] == "Approved"),
        Decimal("0"),
    )
    return {
        **dict(header),
        "current_value": current_value,
        "variations": [{**dict(v), "items": linked.get(v["variation_id"], [])} for v in variations],
    }


def live_contract_value(db: Session, *, workspace_id: int, pm_id: int | None = None) -> Decimal:
    """Sum of `current_value` (original value + variations, as `get_contract` computes it) over the
    workspace's live (`Current`) projects that have a contract; `pm_id` narrows it to one manager's.
    The dashboard's Value in Progress card (Q634)."""
    return db.execute(
        text(
            """
            SELECT COALESCE(SUM(c.original_value + COALESCE(v.delta, 0)), 0)
              FROM project_contract c
              JOIN projects p ON p.project_id = c.project_id
              LEFT JOIN (SELECT project_id, SUM(amount_delta) AS delta
                           FROM project_contract_variation
                          WHERE status = 'Approved' GROUP BY project_id) v
                     ON v.project_id = c.project_id
             WHERE p.workspace_id = :w
               AND p.status = 'Current'
               AND (CAST(:pm AS bigint) IS NULL OR p.pm_id = :pm)
            """
        ),
        {"w": workspace_id, "pm": pm_id},
    ).scalar()


def _checked_item_ids(db: Session, *, project_id: int, item_ids: list[int]) -> list[int]:
    """The ids, deduplicated, once each is a live Joinery Item of this project. A missing id, another
    project's or workspace's, a related part and a deleted item all answer `404 ITEM_NOT_FOUND`."""
    ids = sorted(set(item_ids))
    if ids:
        found = db.execute(
            text(
                f"SELECT item_id FROM items i WHERE i.project_id = :p AND i.item_id = ANY(:ids)"
                f" AND {live_joinery_items('i')}"
            ),
            {"p": project_id, "ids": ids},
        ).scalars().all()
        if len(found) != len(ids):
            raise HTTPException(status_code=404, detail={"code": "ITEM_NOT_FOUND"})
    return ids


def _set_links(db: Session, *, variation_id: int, item_ids: list[int]) -> None:
    db.execute(text("DELETE FROM project_contract_variation_item WHERE variation_id = :v"), {"v": variation_id})
    if item_ids:
        db.execute(
            text("INSERT INTO project_contract_variation_item(variation_id, item_id)"
                 " SELECT :v, unnest(CAST(:ids AS bigint[]))"),
            {"v": variation_id, "ids": item_ids},
        )


def create_variation(
    db: Session, *, project_id: int, workspace_id: int,
    description: str, amount_delta: Decimal, actor_id: int, auto_approve: bool,
    reason: str, requester: str | None = None, requested_on: date | None = None,
    cost_impact: Decimal | None = None, time_impact_days: int | None = None,
    item_ids: list[int] = (),
) -> dict | None:
    """A manager's or admin's variation is decided by adding it (`auto_approve`, Approved at once);
    anyone else's is a Draft until a manager or admin decides it (Q608)."""
    contract = get_contract(db, project_id=project_id, workspace_id=workspace_id)
    if contract is None:
        return None
    ids = _checked_item_ids(db, project_id=project_id, item_ids=list(item_ids))
    status = "Approved" if auto_approve else "Draft"
    # The contract row is the parent whose lock makes MAX(number) + 1 safe against a concurrent add.
    db.execute(text("SELECT 1 FROM project_contract WHERE project_id = :p FOR UPDATE"), {"p": project_id})
    row = db.execute(
        text(
            """
            INSERT INTO project_contract_variation(
                project_id, number, description, amount_delta, reason, requester, requested_on,
                cost_impact, time_impact_days, created_by, status, decided_by, decided_at
            )
            VALUES (:p,
                    (SELECT COALESCE(MAX(number), 0) + 1 FROM project_contract_variation WHERE project_id = :p),
                    :d, :a, :reason, :requester, COALESCE(CAST(:requested_on AS date), CURRENT_DATE),
                    :cost, :days, :cb, :s,
                    CASE WHEN :s = 'Approved' THEN CAST(:cb AS bigint) END,
                    CASE WHEN :s = 'Approved' THEN now() END)
            RETURNING variation_id, number
            """
        ),
        {"p": project_id, "d": description, "a": amount_delta, "cb": actor_id, "s": status,
         "reason": reason, "requester": requester, "requested_on": requested_on,
         "cost": cost_impact, "days": time_impact_days},
    ).mappings().one()
    _set_links(db, variation_id=row["variation_id"], item_ids=ids)
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="project.contract.variation_add", target=str(project_id),
        payload={"number": row["number"], "description": description, "amount_delta": str(amount_delta),
                 "reason": reason, "requester": requester,
                 "requested_on": None if requested_on is None else str(requested_on),
                 "cost_impact": None if cost_impact is None else str(cost_impact),
                 "time_impact_days": time_impact_days, "status": status, "item_ids": ids},
    )
    db.flush()
    return get_contract(db, project_id=project_id, workspace_id=workspace_id)


def _locked_variation(db: Session, *, project_id: int, variation_id: int, workspace_id: int) -> dict:
    row = db.execute(
        text(
            """
            SELECT v.variation_id, v.status, v.created_by, v.description, v.amount_delta
              FROM project_contract_variation v
              JOIN projects p ON p.project_id = v.project_id
             WHERE v.variation_id = :v AND v.project_id = :p AND p.workspace_id = :w
               FOR UPDATE OF v
            """
        ),
        {"v": variation_id, "p": project_id, "w": workspace_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="variation not found")
    return dict(row)


def patch_variation(
    db: Session, *, project_id: int, variation_id: int, workspace_id: int,
    actor_id: int, actor_is_manager: bool, changes: dict,
) -> dict:
    """Edit a Draft: its creator, a manager or an admin. Anything decided is frozen."""
    row = _locked_variation(db, project_id=project_id, variation_id=variation_id, workspace_id=workspace_id)
    if not actor_is_manager and row["created_by"] != actor_id:
        raise HTTPException(status_code=403, detail={"code": "NOT_YOUR_VARIATION"})
    if row["status"] != "Draft":
        raise HTTPException(status_code=409, detail={"code": "VARIATION_NOT_DRAFT"})
    allowed = {"description", "amount_delta", "reason", "requester", "requested_on", "cost_impact",
               "time_impact_days"}
    item_ids = changes.get("item_ids")
    ids = None if item_ids is None else _checked_item_ids(db, project_id=project_id, item_ids=item_ids)
    changes = {k: v for k, v in changes.items() if k in allowed}
    if ids is not None:
        _set_links(db, variation_id=variation_id, item_ids=ids)
    if changes or ids is not None:
        if changes:
            sets = ", ".join(f"{k} = :{k}" for k in changes)  # names come from the fixed set above
            db.execute(
                text(f"UPDATE project_contract_variation SET {sets} WHERE variation_id = :v"),
                {**changes, "v": variation_id},
            )
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="project.contract.variation_edit", target=str(project_id),
            payload={"variation_id": variation_id,
                     **{k: None if v is None else str(v) for k, v in changes.items()},
                     **({"item_ids": ids} if ids is not None else {})},
        )
    db.flush()
    return get_contract(db, project_id=project_id, workspace_id=workspace_id)


def decide_variation(
    db: Session, *, project_id: int, variation_id: int, workspace_id: int,
    actor_id: int, decision: str, note: str | None,
) -> dict:
    """Approve or reject a Draft (the caller has checked the role). Final: a decided variation is not reopened."""
    row = _locked_variation(db, project_id=project_id, variation_id=variation_id, workspace_id=workspace_id)
    note = (note or "").strip() or None
    status = "Approved" if decision == "approved" else "Rejected"
    if status == "Rejected" and note is None:
        raise HTTPException(status_code=409, detail={"code": "REJECTION_NOTE_REQUIRED"})
    if row["status"] != "Draft":
        raise HTTPException(status_code=409, detail={"code": "VARIATION_ALREADY_DECIDED"})
    db.execute(
        text(
            """
            UPDATE project_contract_variation
               SET status = :s, decided_by = :a, decided_at = now(), decision_note = :n
             WHERE variation_id = :v
            """
        ),
        {"s": status, "a": actor_id, "n": note, "v": variation_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="project.contract.variation_decide", target=str(project_id),
        payload={"variation_id": variation_id, "status": status, "note": note},
    )
    db.flush()
    return get_contract(db, project_id=project_id, workspace_id=workspace_id)


def void_variation(
    db: Session, *, project_id: int, variation_id: int, workspace_id: int, actor_id: int, reason: str | None,
) -> dict:
    """Void an Approved variation (the caller has checked the role): it stays listed with its approval but
    no longer counts. Final, and only an Approved one can be voided (Q610)."""
    row = _locked_variation(db, project_id=project_id, variation_id=variation_id, workspace_id=workspace_id)
    reason = (reason or "").strip() or None
    if reason is None:
        raise HTTPException(status_code=409, detail={"code": "VOID_REASON_REQUIRED"})
    if row["status"] != "Approved":
        raise HTTPException(status_code=409, detail={"code": "VARIATION_NOT_APPROVED"})
    db.execute(
        text(
            """
            UPDATE project_contract_variation
               SET status = 'Voided', voided_by = :a, voided_at = now(), void_reason = :r
             WHERE variation_id = :v
            """
        ),
        {"a": actor_id, "r": reason, "v": variation_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="project.contract.variation_void", target=str(project_id),
        payload={"variation_id": variation_id, "reason": reason},
    )
    db.flush()
    return get_contract(db, project_id=project_id, workspace_id=workspace_id)


def variations_waiting_for_approval(
    db: Session, *, workspace_id: int, limit: int = 20
) -> tuple[int, list[dict]]:
    """(count, newest `limit` rows) of the Draft variations in this workspace: they wait for a manager
    or admin to approve or reject them (Q617). Derived on read, never stored, so a decided one drops
    out by itself and nothing is marked read."""
    where = "v.status = 'Draft' AND p.workspace_id = :w"
    count = db.execute(
        text(
            f"""
            SELECT count(*) FROM project_contract_variation v
              JOIN projects p ON p.project_id = v.project_id WHERE {where}
            """
        ),
        {"w": workspace_id},
    ).scalar_one()
    rows = db.execute(
        text(
            f"""
            SELECT v.variation_id, v.project_id, p.project_code, v.number, v.description,
                   cu.full_name AS created_by_name, v.created_at
              FROM project_contract_variation v
              JOIN projects p ON p.project_id = v.project_id
              LEFT JOIN app_user cu ON cu.id = v.created_by
             WHERE {where}
             ORDER BY v.created_at DESC, v.variation_id DESC
             LIMIT :lim
            """
        ),
        {"w": workspace_id, "lim": limit},
    ).mappings().all()
    return count, [dict(r) for r in rows]

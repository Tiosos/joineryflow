"""SQL helpers for project_contract + variations (Q491).

`original_value` is set once, at handover (`estimating.convert_to_project`),
and never overwritten (§17). `current_value` is computed on read as
`original_value + SUM(variation.amount_delta)` over the *Approved* variations
(Q608) — never stored, so there is nowhere for it to drift out of sync with its
own history. A Draft or Rejected variation is listed but never counted.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit


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
            SELECT variation_id, project_id, description, amount_delta,
                   created_at, created_by, status, decided_by, decided_at, decision_note
              FROM project_contract_variation
             WHERE project_id = :p
             ORDER BY created_at, variation_id
            """
        ),
        {"p": project_id},
    ).mappings().all()
    current_value = Decimal(str(header["original_value"])) + sum(
        (Decimal(str(v["amount_delta"])) for v in variations if v["status"] == "Approved"),
        Decimal("0"),
    )
    return {
        **dict(header),
        "current_value": current_value,
        "variations": [dict(v) for v in variations],
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


def create_variation(
    db: Session, *, project_id: int, workspace_id: int,
    description: str, amount_delta: Decimal, actor_id: int, auto_approve: bool,
) -> dict | None:
    """A manager's or admin's variation is decided by adding it (`auto_approve`, Approved at once);
    anyone else's is a Draft until a manager or admin decides it (Q608)."""
    contract = get_contract(db, project_id=project_id, workspace_id=workspace_id)
    if contract is None:
        return None
    status = "Approved" if auto_approve else "Draft"
    db.execute(
        text(
            """
            INSERT INTO project_contract_variation(
                project_id, description, amount_delta, created_by, status, decided_by, decided_at
            )
            VALUES (:p, :d, :a, :cb, :s,
                    CASE WHEN :s = 'Approved' THEN CAST(:cb AS bigint) END,
                    CASE WHEN :s = 'Approved' THEN now() END)
            """
        ),
        {"p": project_id, "d": description, "a": amount_delta, "cb": actor_id, "s": status},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="project.contract.variation_add", target=str(project_id),
        payload={"description": description, "amount_delta": str(amount_delta), "status": status},
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
    allowed = {"description", "amount_delta"}
    changes = {k: v for k, v in changes.items() if k in allowed}
    if changes:
        sets = ", ".join(f"{k} = :{k}" for k in changes)  # names come from the fixed set above
        db.execute(
            text(f"UPDATE project_contract_variation SET {sets} WHERE variation_id = :v"),
            {**changes, "v": variation_id},
        )
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="project.contract.variation_edit", target=str(project_id),
            payload={"variation_id": variation_id, **{k: str(v) for k, v in changes.items()}},
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

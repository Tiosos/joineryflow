"""SQL helpers for project_contract + variations (Q491).

`original_value` is set once, at handover (`estimating.convert_to_project`),
and never overwritten (§17). `current_value` is computed on read as
`original_value + SUM(variation.amount_delta)` — never stored, so there is
nowhere for it to drift out of sync with its own history.
"""
from decimal import Decimal

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
                   created_at, created_by
              FROM project_contract_variation
             WHERE project_id = :p
             ORDER BY created_at, variation_id
            """
        ),
        {"p": project_id},
    ).mappings().all()
    current_value = Decimal(str(header["original_value"])) + sum(
        (Decimal(str(v["amount_delta"])) for v in variations), Decimal("0")
    )
    return {
        **dict(header),
        "current_value": current_value,
        "variations": [dict(v) for v in variations],
    }


def create_variation(
    db: Session, *, project_id: int, workspace_id: int,
    description: str, amount_delta: Decimal, actor_id: int,
) -> dict | None:
    """Creating the row *is* the decision (§6: "the Project Manager decides
    whether a change becomes a Variation") — there is no separate approval
    step on this table; whoever can write here has already decided."""
    contract = get_contract(db, project_id=project_id, workspace_id=workspace_id)
    if contract is None:
        return None
    db.execute(
        text(
            """
            INSERT INTO project_contract_variation(
                project_id, description, amount_delta, created_by
            )
            VALUES (:p, :d, :a, :cb)
            """
        ),
        {"p": project_id, "d": description, "a": amount_delta, "cb": actor_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="project.contract.variation_add", target=str(project_id),
        payload={"description": description, "amount_delta": str(amount_delta)},
    )
    db.flush()
    return get_contract(db, project_id=project_id, workspace_id=workspace_id)

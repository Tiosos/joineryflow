"""Workspace labour rates.

Part of the estimating queries facade (see `queries.py`)."""
from __future__ import annotations

from datetime import datetime
from datetime import timezone
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..auth.audit import write_audit
from ._q_catalog import STAGE_KEYS


# ============================================================================
# Workspace labour rates
# ============================================================================

def list_labour_rates(db: Session, *, workspace_id: int) -> list[dict]:
    existing = {
        r["stage_key"]: dict(r) for r in db.execute(
            text(
                """
                SELECT stage_key, hourly_rate, effective_from, updated_at
                  FROM workspace_labour_rate
                 WHERE workspace_id = :w
                """
            ),
            {"w": workspace_id},
        ).mappings()
    }
    out = []
    today = datetime.now(timezone.utc).date()
    now_ts = datetime.now(timezone.utc)
    for sk in STAGE_KEYS:
        row = existing.get(sk)
        if row is None:
            out.append(
                {
                    "stage_key": sk,
                    "hourly_rate": Decimal("0"),
                    "effective_from": today,
                    "updated_at": now_ts,
                }
            )
        else:
            out.append(row)
    return out


def patch_labour_rates(
    db: Session, *, workspace_id: int, actor_id: int,
    rates: list[dict],
) -> list[dict]:
    for rate in rates:
        sk = rate["stage_key"]
        if sk not in STAGE_KEYS:
            raise ValueError(f"BAD_STAGE_KEY:{sk}")
        db.execute(
            text(
                """
                INSERT INTO workspace_labour_rate(
                    workspace_id, stage_key, hourly_rate, effective_from,
                    updated_by
                )
                VALUES (:w, :s, :r, CURRENT_DATE, :a)
                ON CONFLICT (workspace_id, stage_key) DO UPDATE
                  SET hourly_rate = EXCLUDED.hourly_rate,
                      effective_from = EXCLUDED.effective_from,
                      updated_at = now(),
                      updated_by = EXCLUDED.updated_by
                """
            ),
            {
                "w": workspace_id, "s": sk,
                "r": rate["hourly_rate"], "a": actor_id,
            },
        )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="it.labour_rate_update", target=None,
        payload={"rates": [
            {"stage_key": r["stage_key"], "hourly_rate": str(r["hourly_rate"])}
            for r in rates
        ]},
    )
    db.flush()
    return list_labour_rates(db, workspace_id=workspace_id)

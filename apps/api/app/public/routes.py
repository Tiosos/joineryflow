"""Public (no-auth) endpoints — safe to call from the login page."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter(prefix="/public", tags=["public"])


class WorkspaceStatsOut(BaseModel):
    projects_live: int
    parts_tracked: int
    suppliers: int


@router.get("/stats", response_model=WorkspaceStatsOut)
def workspace_stats(
    workspace_slug: str = Query(..., alias="workspace_slug"),
    db: Session = Depends(get_db),
) -> WorkspaceStatsOut:
    """Aggregate counts for a workspace — used on the login page brand panel.
    No authentication required; returns only non-sensitive numeric totals.
    Returns zeros if the workspace_slug is not found.
    """
    row = db.execute(
        text(
            """
            WITH ws AS (
                SELECT id FROM workspace WHERE slug = :slug
            ),
            projects_live AS (
                SELECT COUNT(*) AS cnt
                FROM projects p
                JOIN ws ON p.workspace_id = ws.id
            ),
            parts_tracked AS (
                SELECT COUNT(pa.part_id) AS cnt
                FROM parts pa
                JOIN modules mo ON mo.module_id = pa.module_id
                JOIN items   it ON it.item_id   = mo.item_id
                JOIN projects pr ON pr.project_id = it.project_id
                JOIN ws ON pr.workspace_id = ws.id
            ),
            suppliers AS (
                SELECT COUNT(DISTINCT s) AS cnt FROM (
                    SELECT supplier AS s FROM board_materials
                     WHERE workspace_id = (SELECT id FROM ws) AND supplier IS NOT NULL
                    UNION ALL
                    SELECT supplier AS s FROM hardware_materials
                     WHERE workspace_id = (SELECT id FROM ws) AND supplier IS NOT NULL
                    UNION ALL
                    SELECT supplier AS s FROM custom_made
                     WHERE workspace_id = (SELECT id FROM ws) AND supplier IS NOT NULL
                    UNION ALL
                    SELECT supplier AS s FROM benchtop_materials
                     WHERE workspace_id = (SELECT id FROM ws) AND supplier IS NOT NULL
                    UNION ALL
                    SELECT supplier AS s FROM appliances
                     WHERE workspace_id = (SELECT id FROM ws) AND supplier IS NOT NULL
                    UNION ALL
                    SELECT supplier AS s FROM equipment_hire
                     WHERE workspace_id = (SELECT id FROM ws) AND supplier IS NOT NULL
                ) t
            )
            SELECT
                (SELECT cnt FROM projects_live) AS projects_live,
                (SELECT cnt FROM parts_tracked) AS parts_tracked,
                (SELECT cnt  FROM suppliers)     AS suppliers
            """
        ),
        {"slug": workspace_slug},
    ).mappings().first()

    if not row:
        return WorkspaceStatsOut(projects_live=0, parts_tracked=0, suppliers=0)

    return WorkspaceStatsOut(
        projects_live=int(row["projects_live"] or 0),
        parts_tracked=int(row["parts_tracked"] or 0),
        suppliers=int(row["suppliers"] or 0),
    )

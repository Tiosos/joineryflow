"""QC Dashboard (Plan V1 §4.2, Q515): a read-only aggregation over `qc_defect`
and `rework`. Nothing here writes, so there is no audit row and no edit log.

**Scope, settled with the user.** Only items whose *cutlist* has started but not
finished are counted — the QC team's live worklist. A cutlist carries no
finished flag, so both words are derived from Shop Floor (Q412: the production
workflow belongs to the cutlist):

* *started* — an assignment on the cutlist that was actually begun and not
  cancelled, or any completion that has not been undone;
* *finished* — a PACKING completion that has not been undone (PACKING is the
  last Shop Floor stage; DEL / INST are not assignable, Q561).

An item with no cutlist has neither, so it is out of scope. Records outside the
scope are not silently dropped: they are counted, so a defect can never vanish
from QC because nobody has started its cutlist yet.

**Open records only** (user's answer). Resolved defects and closed rework are
history and live on the item's own QC tab.

Every number below reads one `scope` CTE, so they cannot disagree about which
items count.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..row_types import joinery_items_only

_JOINERY_ITEM = joinery_items_only("i")

UNTAGGED = "Untagged"

_SCOPE = f"""
scope AS (
    SELECT i.item_id, i.num, i.item_code, i.description, i.project_id
    FROM items i
    JOIN projects p ON p.project_id = i.project_id
    WHERE p.workspace_id = :w
      AND {_JOINERY_ITEM}
      AND (CAST(:pid AS bigint) IS NULL OR i.project_id = :pid)
      AND i.cutlist_id IS NOT NULL
      AND (
        EXISTS (SELECT 1 FROM worker_assignment wa
                 WHERE wa.cutlist_id = i.cutlist_id
                   AND wa.started_at IS NOT NULL AND wa.cancelled_at IS NULL)
        OR EXISTS (SELECT 1 FROM stage_completion_log l
                    WHERE l.cutlist_id = i.cutlist_id AND l.undone_at IS NULL)
      )
      AND NOT EXISTS (SELECT 1 FROM stage_completion_log l
                       WHERE l.cutlist_id = i.cutlist_id
                         AND l.stage_key = 'PACKING' AND l.undone_at IS NULL)
)
"""

# The date range filters when a record was *raised*: for an open record that is
# the only date it has. Inclusive of both ends.
_RAISED = """
      AND (CAST(:d_from AS date) IS NULL OR {t}.created_at >= CAST(:d_from AS date))
      AND (CAST(:d_to   AS date) IS NULL OR {t}.created_at <  CAST(:d_to   AS date) + 1)
"""


def _f(project_id: int | None, d_from: date | None, d_to: date | None, w: int) -> dict:
    return {"w": w, "pid": project_id, "d_from": d_from, "d_to": d_to}


def dashboard(
    db: Session, *, workspace_id: int, project_id: int | None = None,
    date_from: date | None = None, date_to: date | None = None,
) -> dict:
    p = _f(project_id, date_from, date_to, workspace_id)

    # ---- defects in scope, by project and stage -----------------------------
    defect_rows = db.execute(
        text(f"""
            WITH {_SCOPE}
            SELECT s.project_id, pr.project_code, pr.name AS project_name,
                   d.stage_key, COALESCE(st.label, :untagged) AS stage_label,
                   COALESCE(st.sort_order, 32767) AS stage_order,
                   count(*) AS n, min(d.created_at) AS oldest
            FROM qc_defect d
            JOIN scope s ON s.item_id = d.item_id
            JOIN projects pr ON pr.project_id = s.project_id
            LEFT JOIN stages st ON st.stage_key = d.stage_key
            WHERE d.status = 'open' {_RAISED.format(t="d")}
            GROUP BY s.project_id, pr.project_code, pr.name, d.stage_key,
                     st.label, st.sort_order
            ORDER BY pr.project_code, stage_order
        """),
        {**p, "untagged": UNTAGGED},
    ).mappings().all()

    by_project: dict[int, dict] = {}
    by_stage: dict[str | None, dict] = {}
    for r in defect_rows:
        proj = by_project.setdefault(r["project_id"], {
            "project_id": r["project_id"], "project_code": r["project_code"],
            "project_name": r["project_name"], "open": 0,
            "oldest_open_at": r["oldest"], "by_stage": [],
        })
        proj["open"] += r["n"]
        proj["oldest_open_at"] = min(proj["oldest_open_at"], r["oldest"])
        proj["by_stage"].append({"stage_key": r["stage_key"], "label": r["stage_label"],
                                 "open": r["n"]})
        tot = by_stage.setdefault(r["stage_key"], {
            "stage_key": r["stage_key"], "label": r["stage_label"], "open": 0,
            "_order": r["stage_order"],
        })
        tot["open"] += r["n"]
    stages = sorted(by_stage.values(), key=lambda s: s["_order"])
    for s in stages:
        del s["_order"]

    # ---- rework in scope, by project and kind -------------------------------
    rework_rows = db.execute(
        text(f"""
            WITH {_SCOPE}
            SELECT s.project_id, pr.project_code, pr.name AS project_name,
                   count(*) FILTER (WHERE w.kind = 'internal') AS internal,
                   count(*) FILTER (WHERE w.kind = 'full')     AS "full",
                   COALESCE(sum(w.cost), 0)                    AS cost_total,
                   count(*) FILTER (WHERE w.cost IS NULL)      AS cost_missing,
                   min(w.created_at)                           AS oldest
            FROM rework w
            JOIN scope s ON s.item_id = w.item_id
            JOIN projects pr ON pr.project_id = s.project_id
            WHERE w.status = 'open' {_RAISED.format(t="w")}
            GROUP BY s.project_id, pr.project_code, pr.name
            ORDER BY pr.project_code
        """),
        p,
    ).mappings().all()
    rework_by_project = [{
        "project_id": r["project_id"], "project_code": r["project_code"],
        "project_name": r["project_name"], "internal": r["internal"], "full": r["full"],
        "cost_total": r["cost_total"], "cost_missing": r["cost_missing"],
        "oldest_open_at": r["oldest"],
    } for r in rework_rows]

    # ---- drill-down: the items carrying open records ------------------------
    item_rows = db.execute(
        text(f"""
            WITH {_SCOPE},
            d AS (
                SELECT d.item_id, count(*) AS n, min(d.created_at) AS oldest
                FROM qc_defect d JOIN scope s ON s.item_id = d.item_id
                WHERE d.status = 'open' {_RAISED.format(t="d")}
                GROUP BY d.item_id
            ),
            w AS (
                SELECT w.item_id, count(*) AS n, min(w.created_at) AS oldest
                FROM rework w JOIN scope s ON s.item_id = w.item_id
                WHERE w.status = 'open' {_RAISED.format(t="w")}
                GROUP BY w.item_id
            )
            SELECT s.item_id, s.num, s.item_code, s.description, s.project_id,
                   pr.project_code,
                   COALESCE(d.n, 0) AS open_defects, COALESCE(w.n, 0) AS open_rework,
                   LEAST(d.oldest, w.oldest) AS oldest
            FROM scope s
            JOIN projects pr ON pr.project_id = s.project_id
            LEFT JOIN d ON d.item_id = s.item_id
            LEFT JOIN w ON w.item_id = s.item_id
            WHERE d.n IS NOT NULL OR w.n IS NOT NULL
            ORDER BY oldest, s.num
        """),
        p,
    ).mappings().all()
    items = [{
        "item_id": r["item_id"], "num": r["num"], "item_code": r["item_code"],
        "description": r["description"], "project_id": r["project_id"],
        "project_code": r["project_code"], "open_defects": r["open_defects"],
        "open_rework": r["open_rework"], "oldest_open_at": r["oldest"],
    } for r in item_rows]

    # ---- what the scope leaves out, so nothing disappears silently ----------
    items_in_scope = db.execute(
        text(f"WITH {_SCOPE} SELECT count(*) FROM scope"), p,
    ).scalar()

    def _open_total(table: str, alias: str) -> int:
        return db.execute(
            text(f"""
                SELECT count(*) FROM {table} {alias}
                JOIN items i ON i.item_id = {alias}.item_id
                JOIN projects p ON p.project_id = i.project_id
                WHERE p.workspace_id = :w AND {_JOINERY_ITEM}
                  AND (CAST(:pid AS bigint) IS NULL OR i.project_id = :pid)
                  AND {alias}.status = 'open' {_RAISED.format(t=alias)}
            """),
            p,
        ).scalar()

    defects_open = sum(x["open"] for x in by_project.values())
    rework_open = sum(r["internal"] + r["full"] for r in rework_by_project)
    return {
        "scope": {
            "items_in_scope": items_in_scope,
            "open_defects_out_of_scope": _open_total("qc_defect", "d") - defects_open,
            "open_rework_out_of_scope": _open_total("rework", "w") - rework_open,
        },
        "defects_open": defects_open,
        "defects_by_stage": stages,
        "defects_by_project": list(by_project.values()),
        "rework_open": rework_open,
        "rework_cost_total": sum((r["cost_total"] for r in rework_by_project), Decimal("0")),
        "rework_cost_missing": sum(r["cost_missing"] for r in rework_by_project),
        "rework_by_project": rework_by_project,
        "items": items,
    }

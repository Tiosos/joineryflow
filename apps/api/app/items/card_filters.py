"""One server-side definition of a stage's state, and the item filters built on it (Q591, Q633).

A stage of an item is, in this order:
  * **delayed**: done after its due date;
  * **done**: done on time, or done with no due date;
  * **open**: no due date, or not done and not yet close;
  * **overdue**: not done and due before today;
  * **at_risk**: not done, due today or within the workspace's `at_risk_days`, and an earlier stage of
    the item is not done. "Earlier" is the item's own order: REQ, SM, LISTED, then Shop Floor's order
    for that item (paint before or after assembly, `shop_floor.lifecycle`), then DEL and INST; a PAINTED
    row of an item that does not need painting is not an earlier stage.

A dashboard card counts items and opens the list of the same items, so the count and the list read this
module: `home.queries` counts with it and `GET /tracking/items` lists with it. The Tracking list also
returns each stage's `state` and the item flags `is_overdue` / `is_at_risk` / `is_delayed` from the same
SQL, so the web never re-derives a state from dates.

The SQL is fixed text over the aliases `i` (items), and, inside the stage state, `s` (item_stages),
`it` (items again) and `e` (an earlier item_stages row); it binds `:today` and `:wid` and never takes a
request value.
"""
from ..auth.sessions import AuthUser
from ..shop_floor.lifecycle import SHOP_FLOOR_ORDER_DEFAULT, SHOP_FLOOR_ORDER_PAINT_LAST


def _rank_case(stage_key_sql: str) -> str:
    """SQL rank of a stage key in the item `it`'s own order, built from Shop Floor's orders."""
    def case_for(order: tuple[str, ...]) -> str:
        full = ("REQ", "SM", "LISTED", *order, "DEL", "INST")
        whens = " ".join(f"WHEN '{k}' THEN {n}" for n, k in enumerate(full, start=1))
        return f"CASE {stage_key_sql} {whens} END"
    return (f"CASE WHEN it.paint_after_assembly THEN {case_for(SHOP_FLOOR_ORDER_PAINT_LAST)} "
            f"ELSE {case_for(SHOP_FLOOR_ORDER_DEFAULT)} END")


# `:wid`'s workspace setting (migration 0085).
AT_RISK_DAYS_SQL = "(SELECT w.at_risk_days FROM workspace w WHERE w.id = :wid)"

# The state of the stage row `s` of the item `it`.
STAGE_STATE_SQL = f"""CASE
    WHEN s.done_date IS NOT NULL THEN
        CASE WHEN s.due_date IS NOT NULL AND s.done_date > s.due_date THEN 'delayed' ELSE 'done' END
    WHEN s.due_date IS NULL THEN 'open'
    WHEN s.due_date < :today THEN 'overdue'
    WHEN s.due_date <= :today + {AT_RISK_DAYS_SQL}
         AND EXISTS (SELECT 1 FROM item_stages e
                      WHERE e.item_id = s.item_id AND e.done_date IS NULL
                        AND {_rank_case("e.stage_key")} < {_rank_case("s.stage_key")}
                        AND NOT (e.stage_key = 'PAINTED' AND NOT it.painting_req)) THEN 'at_risk'
    ELSE 'open'
END"""


def _has_stage_in_state(state: str) -> str:
    return (f"EXISTS (SELECT 1 FROM item_stages s JOIN items it ON it.item_id = s.item_id "
            f"WHERE s.item_id = i.item_id AND ({STAGE_STATE_SQL}) = '{state}')")


# Filter key -> predicate on a Joinery Item (`i`).
CARD_FILTERS: dict[str, str] = {
    "overdue": _has_stage_in_state("overdue"),
    "at_risk": _has_stage_in_state("at_risk"),
    # a stage finished late, on a job that is not installed yet (a finished job leaves the list)
    "delayed": f"""{_has_stage_in_state("delayed")}
        AND NOT EXISTS (SELECT 1 FROM item_stages s
                         WHERE s.item_id = i.item_id AND s.stage_key = 'INST' AND s.done_date IS NOT NULL)""",
    # marked down, not yet cut on the CNC
    "in_optimisation": """
        EXISTS (SELECT 1 FROM item_stages s
                 WHERE s.item_id = i.item_id AND s.stage_key = 'DOWN' AND s.done_date IS NOT NULL)
        AND NOT EXISTS (SELECT 1 FROM item_stages s
                 WHERE s.item_id = i.item_id AND s.stage_key = 'CNC' AND s.done_date IS NOT NULL)""",
    # delivered, not yet installed
    "awaiting_install": """
        EXISTS (SELECT 1 FROM item_stages s
                 WHERE s.item_id = i.item_id AND s.stage_key = 'DEL' AND s.done_date IS NOT NULL)
        AND NOT EXISTS (SELECT 1 FROM item_stages s
                 WHERE s.item_id = i.item_id AND s.stage_key = 'INST' AND s.done_date IS NOT NULL)""",
}


def scope_clause(user: AuthUser) -> str:
    """Which items the dashboard shows this person: a manager's own projects, a drafter's own
    cutlists, everyone else workspace-wide. Binds `:uid`."""
    if user.auth_role == "manager":
        return "AND i.project_id IN (SELECT project_id FROM projects WHERE pm_id = :uid)"
    if user.auth_role == "drafter":
        return "AND i.cutlist_owner_id = :uid"
    return ""

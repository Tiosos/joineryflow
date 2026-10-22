"""The three dashboard cards' item filters, and who sees which items (Q633).

A dashboard card counts items and opens the list of the same items, so the count and the list
read ONE definition: this module. `home.queries` counts with it and `GET /tracking/items` lists
with it. Q591 will give Overdue / At Risk / Delayed one server definition; when it does, it
changes here and both follow.

The predicates are fixed SQL over the `items` alias `i` (never built from a request value) and
take the bound parameter `:today` where they need the date.
"""
from ..auth.sessions import AuthUser

# Filter key -> predicate on a Joinery Item (`i`).
CARD_FILTERS: dict[str, str] = {
    # at least one stage past its due date and not done
    "overdue": """
        EXISTS (SELECT 1 FROM item_stages s
                 WHERE s.item_id = i.item_id
                   AND s.due_date < :today
                   AND s.done_date IS NULL)""",
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

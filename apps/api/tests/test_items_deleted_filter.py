"""Every SQL string that reads `items` or `cutlist` must hide soft-deleted rows.

Deleting an item flags it (migration 0052), so a query that forgets `NOT i.deleted` shows a
deleted item in a list, a count or a lookup by id. `row_types.live_joinery_items` /
`not_deleted` (or a literal `deleted` test) is the predicate; this test finds the
statements that have none. A statement that deliberately reads deleted rows (or is a
bare FROM fragment completed elsewhere) goes in `ALLOWED` with the reason.
"""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
READS = re.compile(r"\b(?:FROM|JOIN)\s+(?:items|cutlist)\b", re.I)
HIDES = re.compile(r"live_joinery_items|not_deleted|\bdeleted\b|_JOINERY_I(?:TEM)?\b")

# (file, first words of the statement after the FROM/JOIN): reason
ALLOWED: dict[tuple[str, str], str] = {
    ("cutlists/queries.py", "DELETE FROM cutlist"):
        "the explicit cutlist-delete route, after `_cutlist_row` (filtered) resolved the id",
    ("items/queries.py", "SELECT status FROM items"):
        "reads the previous status of an item `_item_row` / the bulk existence check just resolved",
    ("material_takes/queries.py", "SELECT 1 FROM items WHERE item_id"):
        "row lock taken after `_item` (filtered) resolved the item",
    ("orders/queries.py", "FROM purchase_orders po"):
        "`_ORDER_FROM`: an order outlives its item (item_id is display-only); callers that "
        "start from an item (`list_orders_for_item`, `_prefill_from_item`) filter it themselves",
    ("orders/queries.py", "WITH reference AS"):
        "keeps the cutlist reference of an item's existing orders current; the item was resolved by the caller",
    ("project_contracts/actual_costs.py", "FROM stage_completion_log scl"):
        "Actual Costs: labour already spent stays costed in the project total, even on a deleted cutlist (the per-item split skips deleted items)",
    ("related_parts/queries.py", "FROM items i"):
        "`_PART_FROM`: a bare fragment; `get_related_part` and `list_for_parent` add `NOT i.deleted`",
    ("related_parts/queries.py", "DELETE FROM items"):
        "the related-part delete route, after `get_related_part` (filtered) resolved the id",
}


def _statements():
    for path in sorted(APP.rglob("*.py")):
        src = path.read_text()
        tree = ast.parse(src)
        nested = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)
                  for v in n.values}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Constant, ast.JoinedStr)) and id(node) not in nested:
                seg = ast.get_source_segment(src, node) or ""
                if READS.search(seg):
                    yield path.relative_to(APP).as_posix(), node.lineno, seg


def test_every_item_or_cutlist_read_hides_deleted_rows():
    missing = []
    for rel, line, seg in _statements():
        if HIDES.search(seg):
            continue
        if any(rel == f and key in seg for (f, key) in ALLOWED):
            continue
        missing.append(f"{rel}:{line}: {' '.join(seg.split())[:90]}")
    assert not missing, (
        "SQL reading items/cutlist without a deleted-row filter (add "
        "row_types.not_deleted / live_joinery_items, or list it in ALLOWED with a reason):\n"
        + "\n".join(missing)
    )

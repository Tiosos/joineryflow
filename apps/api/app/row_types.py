"""Which `items` rows are Joinery Items.

Migration `0028` put related parts (metal / benchtop / cushion) in `items`
alongside Joinery Items, told apart by `row_type` (Plan V1 Q447). A related
part is a **procurement row**: it carries its own Item ID, its own status
(Q450) and a supplier-order number, and it has **no** cutlist, no workflow
stages (Q419), no modules, parts, hardware lines, attachments or cut plan.

That makes every pre-`0028` query reading `items` wrong by default — each one
was written when `items` held Joinery Items and nothing else. This module is
the single place that says what "a Joinery Item" means in SQL, so the filter
reads the same at all 47 sites that need it.

Three kinds of call site, and only the first two take the filter:

* **Enumerations** — lists, counts, rollups. A related part leaking into one
  is the bug this exists to prevent.
* **Guards** — "does item :iid exist in my workspace?", asked before touching
  a child entity a related part cannot have. Filtering turns a related-part id
  into a clean 404 rather than an empty 200.
* **By-id mutation helpers** — these must stay unfiltered, because the
  related-part routes (Q450 status, Q452 reparent) reach their rows through
  them. Those sites carry a comment saying so; do not "fix" them.
"""

_JOINERY_ITEM = "joinery_item"


def joinery_items_only(alias: str = "i") -> str:
    """SQL predicate restricting an `items` alias to Joinery Item rows.

    Pass the alias the query uses (`i`, `it`, …), or the table name where the
    query has no alias.
    """
    return f"{alias}.row_type = '{_JOINERY_ITEM}'"

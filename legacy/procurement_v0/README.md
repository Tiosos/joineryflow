# Legacy `/procurement/*` (retired October 2026)

Reference copy of the first procurement API, ported from `legacy/procurement_api.py`
(orders, approvals, budget, PO attachments). **Not importable and not mounted**: the web
app never called it, and the v1 order layer is `app/orders` + `app/procurement_v1`
(Q553, Q556). Moved here from `apps/api/app/procurement/` with `git mv`; its test file is in
`tests/`.

Left in place on purpose:

- The nine legacy tables (`cost_centers`, `approval_workflows`, `budget_transactions`, …)
  and their migrations (Q435: data-preserving).
- The home dashboard's `pending_approvals` tile no longer reads `approval_workflows`: it counts orders with `status = 'Pending'`. A real approval flow is designed but not built (`docs/sub-projects/06-orders-procurement.md`).

To bring it back, build it properly rather than re-mounting this: copy what you need into
`apps/api/app/<new package>`, give it workspace-scoped tests, and wire the tile to it.
Q502 and the Orderbook sections of `docs/plan-v1/OPEN-QUESTIONS.md` hold the decisions.

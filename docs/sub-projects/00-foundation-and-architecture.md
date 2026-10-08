# Foundation And Architecture

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation): repository nature, dev loop, auth and RBAC, web shell, architecture invariants, design system. `CLAUDE.md` holds the condensed current rules.

## Repository Nature

**JoineryFlow** monorepo — a web replacement for a FileMaker-based joinery production system. Built across 7 sub-projects; **Foundation** (this branch) ships the auth shell, schema, and 6-tab IA. Subsequent sub-projects (PM Workbench, Procurement Workbench, Shop Floor, etc.) extend onto this base.

Layout:

- `apps/api/` — FastAPI + SQLAlchemy Core (`text()` queries, no ORM models) + Pydantic v2. Auth, RBAC, audit, procurement port.
- `apps/web/` — Next.js 16 (App Router, Turbopack) + Tailwind v4 + TypeScript. Auth shell, tab chrome, server-side proxy.
- `db/` — Alembic migrations `0001` → `0050`. Head is `0050_item_duplicated_from` (`items.duplicated_from_item_id` — a copy made by *Duplicate a Joinery Item* below links to its source). `0049_estimate_line_order_dismissal` is (`estimate_line.orders_dismissed_at/_by/_reason` — a quote line can be marked *ordered by hand*, see *Generate Orders: mark a line ordered by hand* below). `0048_estimate_line_orders_generated` is (`estimate_line.orders_generated_at` — Generate Orders can cover part of a won quote and a later run the rest, see *Generate Orders: per-line selection* below). `0047_po_attachment_file_blob` is (`po_attachments.file_blob_id` — legacy PO attachments move to the shared file store, see *Legacy PO attachments in the shared file store* below). `0046_budget_release_and_po_totals` is (`v_budget_utilisation` counts `Release` rows, legacy PO totals back-filled, `po_number_seq` advanced — see *Legacy procurement audit* below). `0045_po_summary_left_join_cost_centre` is (`v_po_summary` LEFT JOINs `cost_centers` — see *Legacy order views with no cost centre* below). `0044_shop_drawing_register` is (register columns on `shop_drawing` for the Shop Dwgs redesign — see *Shop Drawings register redesign* below). `0043_comment_module_revision` is comment threads on Modules and shop-drawing revisions (Plan V1 §29 — see *Comment threads on Modules and shop-drawing revisions* below). `0042_comments_notifications` is Comments + mentions + in-app notifications, Plan V1 §29 — see *Comments, mentions and notifications* below. `0041_estimate_orders_generated` is PO Generation from a Won Quote (Plan V1 §21 Q505 — one column, `estimate_revision.orders_generated_at`). `0040_lock_types_concurrency` is Plan V1 §L; `0039_qc_rework_packing` is Plan V1 §M; `0038_tender_lifecycle_financials` is Plan V1 §I; `0037_rbac_groups` is the Dynamic RBAC engine; `0036_item_project_detail` is Item & Project Detail 2.0 (`0035_tracking_2_0` is Tracking 2.0 — both authored in May, merged after `0034_material_take` (Material Take, #12)); `0033_search_outbox` is Global Search, #11. Each sub-project section below names the migration(s) it introduced. `0026`–`0032` all belong to the Cutlist + related parts + Orderbook sub-project (#10); `0030`–`0032` were not reserved up front — the Shop Floor re-key, the order schema and the Controlled Lock each needed one.
- `seed/` — `seed.hartwood_joinery` dev seed (workspace + 13 staff users).
- `legacy/` — Read-only quarantine of the original FileMaker-era prototypes (`procurement_api.py`, `*.jsx`, `*.html`, `*_schema.sql`, `product_spec.md`, `trackingv2.md`). Reference only. `REFINEMENT_BACKLOG.md` there tracks 7 open follow-ups from the 2026-05-10 alignment pass.
- `tests/e2e/` — 31 Playwright specs / 124 tests, incl. `smoke.spec.ts` (login + tabs), `pm_workbench.spec.ts`, `drafter_editor.spec.ts`, `procurement.spec.ts`, `shop_drawings.spec.ts`, `isample.spec.ts`, `pdf_generation.spec.ts`, `catalog.spec.ts`, `cv_import.spec.ts`, `estimating.spec.ts`, `cutlist_related_parts.spec.ts` (#10), `search.spec.ts` (#11), `material_take.spec.ts` (#12), `comments.spec.ts` (§29), `comments_module_revision.spec.ts` (§29, module + revision threads), `comment_counts.spec.ts` (§29, module + revision badges), `cv_replace_comments.spec.ts` (CV replace warning), `module_delete.spec.ts` (delete-module warning + lock checks), `cutlist_locks.spec.ts` (locks on every module / part write), `hardware_locks.spec.ts` (locks on hardware lines), `status_locks.spec.ts` (locks on status + stage dates), `attachments_locks.spec.ts` (locks on attachment slots), `queries_takes_locks.spec.ts` (locks on item queries + material takes), `catalog_supplier_link.spec.ts` (Catalog supplier link + Generate Orders from it), `document_register.spec.ts` (Document Register UI), `tracking_modal_files.spec.ts` (Tracking modal files), `qc_dashboard.spec.ts` (§4.2), `item_duplicate.spec.ts` (Plan V1 §2). **The suite is not idempotent**: `estimating.spec.ts`, `procurement.spec.ts` and `comments.spec.ts` fail on a second run against the same database (an estimate cannot convert twice; a duplicate "Test Supplier" batch trips Playwright strict mode; the comments spec reads a seeded notification, so the bell starts at 0 on a second run). **A re-seed is not enough**: the seed skips items that already exist, so it does not restore a lock or take an earlier run changed — run the whole suite against a **freshly created, migrated and seeded database** (see *e2e suite repair*).
- `docs/archive/specs/`, `docs/archive/plans/` — design specs and implementation plans.
- `docs/plan-v1/` — **Plan V1**: the customer's target specification, the gap analysis against this tree, and 154 open questions (Q432–Q586, 150 resolved). Mostly still a target; the sub-projects that are built are listed in *Plan V1 — target architecture* below, which is the record of what is true.


## Foundation dev loop

```
make up           # build + start db, meili, api, search-worker, web (Postgres 16, Meilisearch, FastAPI, Next.js 16)
make migrate      # apply Alembic 0001 -> 0050
make seed         # create hartwood-joinery workspace + 13 users + 2 projects + demo data for every shipped sub-project (dev password: hartwood-dev)
make test         # pytest in api container (100 test files, ~1541 tests; the `meili`-marked
                  # ones skip unless MEILI_URL is set — compose sets it)
make reindex      # rebuild the search index from Postgres (swap-index, no downtime)
                  # Runnable WITHOUT Docker too, which is worth knowing when the
                  # container is unavailable: `pyproject.toml` needs Python >=3.12
                  # (the shell default may be older), so make a 3.12 venv, run
                  # `pip install -e ".[dev]"`, point DATABASE_URL at any Postgres
                  # migrated to head, and run pytest. Takes ~13 minutes (measured; the
                  # suite is ~1400 tests against a real Postgres).
make e2e-docker   # Playwright smoke via official image (Windows-friendly; use `make e2e` on Linux/Mac with pnpm on PATH)
```

Login: http://localhost:3000/login -> `rin.park@hartwood.test` / `hartwood-dev` (or any `*.hartwood.test` seed user).
API health: http://localhost:3000/api/health -> `{"ok":true}` (proxied through Next.js to FastAPI).

**Important:** Running `make test` TRUNCATEs `workspace`, `app_user`, `session`, `audit_log` between cases. Re-run `make seed` if you need login working after a test run.

## Auth & RBAC

- Self-built auth: argon2id passwords (`apps/api/app/auth/passwords.py`), opaque 32-byte tokens (sha256 stored), httpOnly `jf_session` cookie, sliding 14d / hard-cap 30d (`apps/api/app/auth/sessions.py`).
- **7 auth roles**: `admin`, `manager`, `editor`, `drafter`, `estimator`, `purchase_officer`, `viewer`. `apps/api/app/auth/permissions.py`'s static `(role, module) -> set[action]` dict (`MATRIX`) is no longer the live source of truth — see *Dynamic RBAC engine* below — but it still documents each role's grants readably and is the fallback for any user with zero group memberships; the per-sub-project notes below explain *why* a row reads as it does. `purchase_officer` has read+comment on tracking, full read+write+approve on orderbook.
- **12 modules** (`_ALL_MODULES`): the 6 IA tabs `dashboard`, `tracking`, `list`, `shop_dwgs`, `isample`, `orderbook`, then `catalog`, `cut_floor`, `shop_floor`, `estimating`, `qc`, and admin-only `it_management`.
- 4 actions: `read`, `write`, `approve`, `comment`.
- FastAPI deps: `current_user` (resolves cookie -> AuthUser) and `require_permission(module, action, project_param=None)` factory in `apps/api/app/auth/rbac.py`, backed by the DB engine in `apps/api/app/auth/rbac_engine.py`.
- All authenticated mutations write to `audit_log` via `apps/api/app/auth/audit.py`.

## Web shell

- Browser -> Next.js Route Handler (`apps/web/app/api/[...proxy]/route.ts`) -> FastAPI. Browser **never** calls FastAPI directly.
- `apps/web/proxy.ts` (Next 16 renamed the `middleware` convention to `proxy`; runs in the Node.js runtime) enforces login redirect on all non-public paths.
- `apps/web/app/(app)/layout.tsx` does a server-side `fetchMe()` and renders `HAppChrome` (TopBar + tab strip + SideBar). `TabStrip.tsx` carries the 6 primary tabs plus a secondary row (`Catalog · Shop Floor · Cut Floor · QC · Estimating · Customers`); `SideBar.tsx` is the project list only.
- **The tab strip is gated on the user's effective grants**, not the real enforcement point. `TabStrip.tsx` filters each tab on `can(me, module, "read")` using the `permissions` map `/auth/me` serves — the Dynamic RBAC engine's workspace-wide grants for that user (see *`/auth/me` follows the permission groups*), not the bare role row. Today every default group holds `read` on every tab's module, so all tabs still render for everyone — the gate hides a tab once an admin removes that module's read grant from a user's groups. The API's 403 remains the actual access control; an unauthorised click still surfaces it. (If `me.permissions` is absent entirely — e.g. web deployed ahead of the API — the strip falls back to showing all tabs rather than blanking the nav.)
- Design tokens: `apps/web/app/globals.css` declares CSS custom properties + Tailwind v4 `@theme inline` block exposing `bg-h-bg`, `text-h-ink`, `text-h-muted`, `border-h-line`, `bg-h-accent`, `bg-h-surface`. **No `tailwind.config.ts`** — Tailwind v4 uses CSS-first config.

## Architecture (big picture)

**One database, three apps** (see `product_spec.md` §1):

1. **Project Information Management** (v1 target) — Drafter/PM/CEO. Project → Item → Module → Part + HardwareLine + 10-stage lifecycle.
2. **Shop Floor Ops** (v2) — Foreman worker assignment; reuses v1 fields.
3. **Cabinet Vision Integration Layer** (v2) — Material catalog, CV CSV import, CutPlan/CutSchedule.

**Key data-model invariants** (enforced across schemas and UI):

- **Six separate Material Catalog tables** (`board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`) — do NOT unify them; lifecycles differ. They are *intended* to share an abstract interface `(id, type, description, supplier, cost_unit, lead_time_days, notes)` — but **verify before relying on it**: `custom_made` names its supplier column `vendor`, not `supplier`. Of that list only `description`, `notes` and (since `0017`) `default_supplier` / `default_lead_time_days` are genuinely common to all six; the PK is `hire_id` on `equipment_hire` and `material_id` elsewhere. `0029` carries a per-table supplier-column map for this reason.
- **ProjectHardwareCatalog** is a project-scoped link layer; item hardware lines reference materials *through* it. Log-only governance (no approval step; every add/remove writes an audit row).
- **ProcurementBatch → Allocations → item_hardware_line_id** answers "is this item blocked on a material?" as a single join — no second window needed.
- **CutPlan ≠ CutSchedule.** Optimisation output vs. Machine team's daily ordering. Keep as two entities.
- **`items.num` comes from `joinery_number_seq` alone** (migration `0027`, Plan V1 Q541) — one company-wide counter shared by Item IDs, cutlist numbers and related parts, so a six-digit number never means two things. Allocate it **inside** the INSERT (`nextval('joinery_number_seq')`); never read `MAX(num)` and insert the result, which is the race B2a removed. The sequence has no owning table, so `TRUNCATE ... RESTART IDENTITY` does not reset it. `make seed` writes **fixed** numbers for idempotency and then advances the sequence past them — keep that step if you add seeded items.
- **`purchase_orders.po_number` comes from `po_number_seq`** (migration `0031`, Q564), formatted `PO-{year}-{0000}`. The legacy generator in `legacy/procurement_api.py:274` used `MAX(...) + 1` and carried the same race B2a removed — do not reinstate it. Like `joinery_number_seq` this sequence has **no owning table**, so `TRUNCATE ... RESTART IDENTITY` does not reset it: never assert an absolute PO number in a test, only the format and that numbers advance.
- **Terminology pins** (critical, legacy-FileMaker-era collisions):
  - `Stage` = site location/area (e.g. `Joinery Lab`, `Block B`).
  - `Zone` = numeric sub-division of Stage.
  - `lifecycle_stage` (or `stage_key`) = the 10 production milestones (`REQ`, `SM`, `LISTED`, `DOWN`, `CNC`, `EDGED`, `PAINTED`, `MADE`, `DEL`, `INST`). **Never reuse the bare word "stage"** for these in code. (**The pin still stands.** Q456 retires it only once `items.stage` is *gone*, and #10 did not remove it: `0026` added `area` / `room` as real tables and the UI now reads them, but `items.stage` / `rm_no` / `rm_desc` are **still present and still written** on every save, because Q435 requires the change to be data-preserving. A later migration drops them; the pin retires then, not now.)
  - `Status` = record state (`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD`).
  - `Status Symbol` = Drafter-only UI flag, not reported.

**Role model.** Operational JTBD roles map onto the 7 auth roles: CEO -> admin; PM -> manager; Drafter -> `drafter` (its own role since 0008); Foreman/Machine/Joiner -> editor; Procurement -> purchase_officer; Estimator -> `estimator` (added by 0021); Observer -> viewer. Drafter is the authoritative data-entry point; every other role is upstream or downstream.

`jtbd_role` is a free-text column on `app_user` (no CHECK constraint, despite the Foundation spec §5 sketching one) used for display only — the seed writes mixed-case values like `CEO`, `Drafter`, `CNC operator`. Nothing branches on it: `/home/dashboard`'s `_role_view` keys off `auth_role` alone, and `estimator`/`editor` currently fall through to the viewer shape.

**Procurement backend.** Ported from `legacy/procurement_api.py` (MySQL) to `apps/api/app/procurement/{schemas,queries,routes}.py` (Postgres). **25 endpoints** (was 32), all gated by `require_permission("orderbook", action)`. **Seven were retired**: the four `/vendors*` (Q565 — `/suppliers` is now the single surface over `vendors`, workspace-scoped; the legacy pair never were, and `0029`'s `workspace_id NOT NULL` had broken the POST) and the three `/inventory*` (Q544 — `0029` dropped `inventory`, `inventory_movements` and `v_inventory_status`, so they had been 500ing). Mounted at `/procurement/*`. The legacy DB views it reads (`v_po_summary`, `v_budget_utilisation`, `v_inventory_status`, `v_orders_due`) were skipped by migration 0002 and recreated by **migration 0006**; 0009 redefines `v_po_summary` after the `app_user` repoint; **`0045` turns its `cost_centers` join into a LEFT JOIN** so an order with no cost centre (nullable since `0031`) is no longer invisible to these routes. This namespace (orders, vendors, budget, approvals) is **not** used by the v1 product surface — that is `procurement_v1`.
**Fixed later — was completely unscoped.** The remaining 21 endpoints (orders, attachments, approvals, budget) had **zero workspace isolation**: any authenticated user with `orderbook` permission in *any* workspace could read or mutate *every* workspace's purchase orders, attachments, approvals and budget data. `purchase_orders`/`po_line_items`/`po_attachments`/`approval_workflows` now resolve through the same project-or-vendor join `orders/queries.py`'s `_ORDER_WORKSPACE` already established (`_PO_WORKSPACE_EXISTS` in `procurement/queries.py`); `budget_transactions`/`v_budget_utilisation` resolve through `cost_centers.workspace_id` (added by `0029` — initially missed on the first pass here, then found and fixed in the same round). `create_order` now also validates `vendor_id`, `cost_center_id` and `requester_id` against the caller's workspace before inserting, and `submit_for_approval` validates `approver_id` the same way — both FKs to `app_user` are joined to `full_name` in `v_po_summary` / `approval_history`, so an unvalidated foreign id would leak that user's name cross-workspace. (`decide_approval`'s own `approver_id` is never joined for display — only used in a changelog text string — so it is left unvalidated.) Pinned by `test_procurement_routes.py` (no prior test file existed for this module at all).

## Design system (binding)

Tokens live **once** in `apps/web/app/globals.css` (`@theme inline` block) and are mirrored as a JS object in `apps/web/lib/tokens.ts`. When editing any surface:

- Do not invent new colors — use Tailwind utilities `bg-h-bg`, `bg-h-surface`, `text-h-ink`, `text-h-muted`, `border-h-line`, `bg-h-accent`, `text-h-accent`. Inline styles can use `H.bg`, `H.ink`, etc. from `lib/tokens.ts`.
- Hi-fi reference designs in `legacy/` use a richer palette (`surfaceAlt`, `ink2..4`, `accentSoft`, `good`, `warn`, `bad`, `info`) — port into `globals.css` only when an actual feature needs them.
- Typography: Inter (default sans) for UI, JetBrains Mono for part #, PO #, ETAs, money. The `.h-mono` utility (with `tnum`) is wired in `globals.css`.
- Status taxonomy (`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD`) is canonical — see `legacy/product_spec.md` §12.3 before adding a new state.
- IA is fixed to **6 primary tabs** in this order: `Dashboard · Tracking · List · Shop Dwgs · iSample · Orderbook`, plus the admin-only IT Management at `/it`. Later sub-projects added a **secondary** strip after a divider — `Catalog · Shop Floor · Cut Floor · QC · Estimating · Customers` — which is where new top-level surfaces go; the primary six do not grow. Both live in `apps/web/components/chrome/TabStrip.tsx`. (**Plan V1 Q474 confirmed this rule stands**: Plan V1's `Cutlist` module **is** the existing `List` tab — which the RBAC module name already reflects, since `("list","read")` gates `cutlist.pdf`. No seventh primary tab.)


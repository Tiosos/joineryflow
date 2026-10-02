# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

---

## 0. RULE ZERO — when in doubt, ask (overrides everything below)

**If you are unsure, or two sources of truth disagree, STOP and ask the user a
question. Do not pick silently, do not guess, do not average the two.**

This outranks every other rule in this file, including "bias toward caution over
speed" and any instruction to keep momentum. A question costs minutes; a wrong
assumption buried in a migration or a schema costs days.

Ask — do not decide — whenever:

- **Two documents disagree.** `CLAUDE.md`, `docs/plan-v1/plan_v1.md`,
  `docs/plan-v1/OPEN-QUESTIONS.md`, a spec, a plan, or the code itself. If they
  conflict, the conflict *is* the question.
- **A decision is under-specified.** An answer that reads equally well two ways
  has not been answered. (Q454/Q455 said Area and Room become entities "with FKs
  from items", which fits both a nested and a sibling model — the real data had
  to force the question. That should have been asked first.)
- **The data contradicts the plan.** If what is actually in the database does
  not match what a document assumes, say so with the evidence before writing
  code against either.
- **A rule would have to be bent.** Anything this file calls *binding* or
  *invariant*, any terminology pin, any "never".
- **Scope is about to grow.** If the honest implementation is materially bigger
  than what was asked, name the gap before starting.

When you ask: give the concrete evidence (a row count, a file and line, the two
conflicting sentences), state the options, and say which you would pick and why.
Then wait.

When a decision *is* settled, record it where the next reader will look, and
note it when the code deliberately departs from a document — never leave the two
disagreeing silently.

---

**Tradeoff:** The guidelines below bias toward caution over speed. For trivial tasks, use judgment — but Rule Zero still applies.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Repository Nature

**JoineryFlow** monorepo — a web replacement for a FileMaker-based joinery production system. Built across 7 sub-projects; **Foundation** (this branch) ships the auth shell, schema, and 6-tab IA. Subsequent sub-projects (PM Workbench, Procurement Workbench, Shop Floor, etc.) extend onto this base.

Layout:

- `apps/api/` — FastAPI + SQLAlchemy Core (`text()` queries, no ORM models) + Pydantic v2. Auth, RBAC, audit, procurement port.
- `apps/web/` — Next.js 16 (App Router, Turbopack) + Tailwind v4 + TypeScript. Auth shell, tab chrome, server-side proxy.
- `db/` — Alembic migrations `0001` → `0047`. Head is `0047_po_attachment_file_blob` (`po_attachments.file_blob_id` — legacy PO attachments move to the shared file store, see *Legacy PO attachments in the shared file store* below). `0046_budget_release_and_po_totals` is (`v_budget_utilisation` counts `Release` rows, legacy PO totals back-filled, `po_number_seq` advanced — see *Legacy procurement audit* below). `0045_po_summary_left_join_cost_centre` is (`v_po_summary` LEFT JOINs `cost_centers` — see *Legacy order views with no cost centre* below). `0044_shop_drawing_register` is (register columns on `shop_drawing` for the Shop Dwgs redesign — see *Shop Drawings register redesign* below). `0043_comment_module_revision` is comment threads on Modules and shop-drawing revisions (Plan V1 §29 — see *Comment threads on Modules and shop-drawing revisions* below). `0042_comments_notifications` is Comments + mentions + in-app notifications, Plan V1 §29 — see *Comments, mentions and notifications* below. `0041_estimate_orders_generated` is PO Generation from a Won Quote (Plan V1 §21 Q505 — one column, `estimate_revision.orders_generated_at`). `0040_lock_types_concurrency` is Plan V1 §L; `0039_qc_rework_packing` is Plan V1 §M; `0038_tender_lifecycle_financials` is Plan V1 §I; `0037_rbac_groups` is the Dynamic RBAC engine; `0036_item_project_detail` is Item & Project Detail 2.0 (`0035_tracking_2_0` is Tracking 2.0 — both authored in May, merged after `0034_material_take` (Material Take, #12)); `0033_search_outbox` is Global Search, #11. Each sub-project section below names the migration(s) it introduced. `0026`–`0032` all belong to the Cutlist + related parts + Orderbook sub-project (#10); `0030`–`0032` were not reserved up front — the Shop Floor re-key, the order schema and the Controlled Lock each needed one.
- `seed/` — `seed.hartwood_joinery` dev seed (workspace + 13 staff users).
- `legacy/` — Read-only quarantine of the original FileMaker-era prototypes (`procurement_api.py`, `*.jsx`, `*.html`, `*_schema.sql`, `product_spec.md`, `trackingv2.md`). Reference only. `REFINEMENT_BACKLOG.md` there tracks 7 open follow-ups from the 2026-05-10 alignment pass.
- `tests/e2e/` — 28 Playwright specs / 104 tests, incl. `smoke.spec.ts` (login + tabs), `pm_workbench.spec.ts`, `drafter_editor.spec.ts`, `procurement.spec.ts`, `shop_drawings.spec.ts`, `isample.spec.ts`, `pdf_generation.spec.ts`, `catalog.spec.ts`, `cv_import.spec.ts`, `estimating.spec.ts`, `cutlist_related_parts.spec.ts` (#10), `search.spec.ts` (#11), `material_take.spec.ts` (#12), `comments.spec.ts` (§29), `comments_module_revision.spec.ts` (§29, module + revision threads), `comment_counts.spec.ts` (§29, module + revision badges), `cv_replace_comments.spec.ts` (CV replace warning), `module_delete.spec.ts` (delete-module warning + lock checks), `cutlist_locks.spec.ts` (locks on every module / part write), `hardware_locks.spec.ts` (locks on hardware lines), `status_locks.spec.ts` (locks on status + stage dates), `attachments_locks.spec.ts` (locks on attachment slots), `document_register.spec.ts` (Document Register UI), `tracking_modal_files.spec.ts` (Tracking modal files), `qc_dashboard.spec.ts` (§4.2). **The suite is not idempotent**: `estimating.spec.ts`, `procurement.spec.ts` and `comments.spec.ts` fail on a second run against the same database (an estimate cannot convert twice; a duplicate "Test Supplier" batch trips Playwright strict mode; the comments spec reads a seeded notification, so the bell starts at 0 on a second run). Re-seed between runs.
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — design specs and implementation plans.
- `docs/plan-v1/` — **Plan V1**: the customer's target specification, the gap analysis against this tree, and 107 open questions. Nothing in it is built. See *Plan V1 — target architecture* below.

## Plan V1 — target architecture (seven sub-projects built)

`docs/plan-v1/` holds **Plan V1**, the customer's specification for a
company-wide joinery workflow and control platform, with its interview
questions answered through Q431 (supplied 2026-09-17). It is mostly a
**target**, not a description of this tree — with seven exceptions: **Plan V1
#10 (Cutlist + related parts + Orderbook)**, **#11 (Global Search, §13)**,
**#12 (Material Take → Summary, §19–§20)**, **§3.4 (Dynamic RBAC engine,
Q466–473)**, **§I (Tender Lifecycle + Financials, §5–§6/§11/§16)**,
**§M (QC / Rework / Packing, §26–§28)** and **§L (Locking, Concurrency,
§11–§12, Q508/Q511/Q512)** are built, each with its own section below.
Everything else in Plan V1 remains unimplemented, apart from **§29 Comments** (a
partial build: 6 of its 8 object types, replies and @mentions, plus a minimal
in-app inbox — see *Comments, mentions and notifications* and *Comment threads
on Modules and shop-drawing revisions*).

- `docs/plan-v1/plan_v1.md` — the spec, verbatim and canonical.
- `docs/plan-v1/ALIGNMENT.md` — every Plan V1 section mapped onto current
  state: 82 rows, **4 shipped · 21 partial · 50 absent · 7 re-architecture** —
  the 2026-09-18 baseline, **not re-scored** after #10, #11, #12, the RBAC
  engine, §I, §M or §L (only the §13 search row, the §19 / §20 take and
  summary rows, and the §12 locking row have been updated in place — the
  first two moved to `PARTIAL`; the locking row's description was updated
  but stays `PARTIAL`, since Plan V1's ask for locks *below and above* item
  scope is still unmet by Q510's own confirmed ceiling).
- `docs/plan-v1/OPEN-QUESTIONS.md` — Q432–Q586, continuing Plan V1's own
  numbering. **150 of 154 resolved; every answerable question is answered.**
  Q574–Q580 settle the Search design (sub-project #11); Q581–Q586 the Material
  Take design (#12).
  Q552–Q573 were raised *while building* the Cutlist sub-project, each where a
  document and the code disagreed.
  The four left are **inputs only the customer can supply**: the SharePoint
  site URL (Q480), a real drawing filename (Q547), what the Cars / OH&S
  tabs hold (Q550), and what the Scope tab holds (Q572). The first two block
  §H entirely.

**Confirmed 2026-09-18** (Plan V1 §43, `OPEN-QUESTIONS.md` §A):

- **Q433** — Plan V1 is the **roadmap for this codebase**. It is not a separate
  product and not a rebuild; JoineryFlow evolves into it.
- **Q435** — shipped behaviour **may change, but only behind data-preserving
  migrations**.
- **Q438** — the **Cutlist becomes a first-class entity** owning the production
  workflow (conflict 1 below is accepted, not avoided).
- **Q437** — the **next sub-project is Cutlist + related parts** (conflicts 1
  and 2), built as one change. **Done** — widened by Q542 to take the whole
  Orderbook with it. See *Cutlist + related parts + Orderbook* below.

Apart from #10, #11, #12, the RBAC engine, §I, §M and §L, this section still
describes a target, and `CLAUDE.md` remains the record of what is actually
true in the tree.

**Before building anything from Plan V1, read `ALIGNMENT.md` §3.** It lists
seven places where Plan V1 contradicted an invariant stated as binding in *this*
file. **All seven are now decided** (re-scored 2026-09-18):

| Conflict | Outcome |
| --- | --- |
| 1. **Cutlist owns the workflow** (Q410–Q413) | **Built** (`0027`, `0030`). `item_stages` stays per-item as a **projection**, written by fan-out on completion (Q439). Shop Floor re-keyed to `(cutlist_id, stage_key)`; the `(item_id, 'INST')` half of Q445 turned out to be unreachable — Shop Floor has never been able to hold DEL or INST (**Q561**). |
| 2. **Related-part rows** (Q416–Q424) | **Built** (`0028`). Rows in `items` with a `row_type` + parent FK (Q447). The measured cost was **50 SQL call sites across 13 modules**; only **35** actually take the filter — `apps/api/app/row_types.py` holds the one definition and B1's note classifies the rest. |
| 3. **Project files in SharePoint** (Q398–Q400) | **Bounded.** Additive only — `file_blob` survives and keeps serving shop drawings, attachments and sample photos (Q479). Nothing in #5a/#5b/#5c is rewritten. Blocked on three customer inputs. |
| 4. **RBAC as data** (Plan V1 §3) | **Built** (`0037`). DB-backed with groups, but **project scope only — not item, not tab** (Q466). The 4 actions stay (Q469); today's 7 roles became 7 seed groups with identical grants (Q468), so day one is behaviour-preserving. See *Dynamic RBAC engine* below — Q472's rule-engine migration and Q473's comments feature were not part of this build (**Q473 has since been built — see *Comments, mentions and notifications***). |
| 5. ~~Navigation / Cutlist module~~ | **Closed (Q474).** Cutlist **is** the `List` tab — which the RBAC module name already reflects. The primary six do not grow. |
| 6. **Area / Room as entities** | **Built** (`0026`). Real project-scoped tables with Room **nested under** Area (Q552) and a composite FK `items (area_id, room_id) → room`. It was *not* the pure rename Q455 anticipated: `items.stage` / `rm_no` / `rm_desc` are **kept and still written** alongside the new FKs (Q435), so the terminology pin below still stands. |
| 7. **10 vs 14 lifecycle stages** | **Deferred (Q459).** Today's 10 stand; `PAINTED` before `MADE` with `paint_after_assembly` (Q461); one global `stages` lookup (Q462). Packing is the first extra stage to arrive (Q519). |

**Three decisions deliberately depart from Plan V1's prose** — the code is right
and should not be "fixed" to match: **Q499** (PM confirmation of the Material
Summary is advisory, against §20's release gate), **Q513** (no rollback, against
§11's 20 change states) and **Q527** (fixed KPI catalogue, against §32's
IT-defined formulas).

## Foundation dev loop

```
make up           # build + start db, meili, api, search-worker, web (Postgres 16, Meilisearch, FastAPI, Next.js 16)
make migrate      # apply Alembic 0001 -> 0047
make seed         # create hartwood-joinery workspace + 13 users + 2 projects + demo data for every shipped sub-project (dev password: hartwood-dev)
make test         # pytest in api container (97 test files, ~1420 tests; the `meili`-marked
                  # ones skip unless MEILI_URL is set — compose sets it)
make reindex      # rebuild the search index from Postgres (swap-index, no downtime)
                  # Runnable WITHOUT Docker too, which is worth knowing when the
                  # container is unavailable: `pyproject.toml` needs Python >=3.12
                  # (the shell default may be older), so make a 3.12 venv, run
                  # `pip install -e ".[dev]"`, point DATABASE_URL at any Postgres
                  # migrated to head, and run pytest. Takes ~2 minutes.
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

## Reference docs (read before large changes)

> **Read `docs/superpowers/plans/README.md` first.** It defines the status
> header every plan carries (shipped / in progress, migrations introduced,
> later changes), why the `- [ ]` checkboxes are *not* a progress signal, and
> which plans are shipped-state records written after the fact rather than
> forward plans.
>
> Treat a plan as the design record for the sub-project it names, and this
> file as the record of current state. Migration **0010** (item_edit_log
> reshape) has neither spec nor plan; the sub-project sections here are its
> only written reference.

- `docs/plan-v1/plan_v1.md` — **Plan V1**, the customer's canonical target spec, answered through Q431. A target, not current state.
- `docs/plan-v1/ALIGNMENT.md` — Plan V1 mapped onto this tree; read §3 before starting any Plan V1 work.
- `docs/superpowers/plans/2026-09-18-cutlist-related-parts-orderbook.md` — plan for sub-project #10: cutlist entity, related-part rows, Area/Room entities, and the Orderbook. **A1–A4, B1–B7, C1–C6, D1–D3 and E1–E2 are done**; only **E3** is open, blocked on a copy of the customer's real pilot data. Unusually for this repo its checkboxes *are* kept current and each finished task carries a `→` note recording what shipped and how it was verified.
- `docs/plan-v1/OPEN-QUESTIONS.md` — Q432–Q586, **150 of 154 resolved**. Every answerable question is answered; the four left are customer inputs — Q480 (SharePoint site URL), Q547 (drawing filename pattern), Q550 (Cars / OH&S contents) and Q572 (what the Scope tab holds).
- `legacy/product_spec.md` — product overview, JTBD roles, data model invariants, design tokens, IA. Authoritative for v1 product surface. (The Foundation spec's §10 cites this as `docs/product_spec.md`; it lives in `legacy/`.)
- `legacy/REFINEMENT_BACKLOG.md` — 7 open follow-ups from the 2026-05-10 alignment pass (the `make migrate -w /db` workaround, 7 missing palette tokens, a `/dev/legacy` compare route, mobile + dark-mode passes). Graduate an item into `docs/superpowers/plans/` when you pick it up.
- `legacy/trackingv2.md` — detailed v1 build plan for Project Information Management. Authoritative for module 1.
- `docs/superpowers/specs/2026-04-22-foundation-design.md` — Foundation spec.
- `docs/superpowers/plans/2026-04-22-foundation.md` — 31-task implementation plan (tracks all build decisions).
- `docs/superpowers/specs/2026-04-25-pm-workbench-design.md` — PM Workbench + Drafter Editor spec (sub-projects #2 + #3).
- `docs/superpowers/plans/2026-04-25-pm-workbench.md` — 33-task implementation plan for sub-projects #2 + #3.
- `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md` — Procurement Workbench v1 spec (sub-project #4).
- `docs/superpowers/plans/2026-04-28-procurement-workbench.md` — 24-task implementation plan for sub-project #4.
- `docs/superpowers/specs/2026-05-01-shop-drawings-design.md` — Shop Drawings + file-upload subsystem v1 spec (sub-project #5a).
- `docs/superpowers/plans/2026-05-01-shop-drawings.md` — 21-task implementation plan for sub-project #5a.
- `docs/superpowers/specs/2026-05-02-pdf-generation-design.md` — PDF generation + item attachments v1 spec (sub-project #5b).
- `docs/superpowers/plans/2026-05-02-pdf-generation.md` — 15-task implementation plan for sub-project #5b.
- `docs/superpowers/specs/2026-05-02-isample-design.md` — iSample (sample wall) v1 spec (sub-project #5c).
- `docs/superpowers/plans/2026-05-02-isample.md` — 14-task implementation plan for sub-project #5c.
- `docs/superpowers/specs/2026-05-05-cabinet-vision-design.md` — Cabinet Vision Integration spec (sub-projects #7a + #7b + #7c).
- `docs/superpowers/plans/2026-05-05-cabinet-vision-7a-catalog.md` — 15-task implementation plan for sub-project #7a.
- `docs/superpowers/plans/2026-05-05-cabinet-vision-7b-cv-import.md` — 19-task implementation plan for sub-project #7b.
- `docs/superpowers/plans/2026-05-08-cabinet-vision-7c-cut-floor.md` — 12-task implementation plan for sub-project #7c.
- `docs/superpowers/specs/2026-05-05-shop-floor-design.md` — Shop Floor Ops v2 spec (sub-project #8).
- `docs/superpowers/plans/2026-05-08-shop-floor.md` — 17-task implementation plan for sub-project #8.
- `docs/superpowers/plans/2026-05-26-estimating.md` — shipped-state record for sub-project #9a (migrations 0021–0023), backfilled 2026-08-14. Explains *why* the schema and workflow read as they do; this file stays the statement of current state.
- `docs/superpowers/specs/2026-05-27-tracking-2-0-design.md` + `docs/superpowers/plans/2026-05-27-tracking-2-0.md` — Tracking 2.0 (migration `0035`). **Shipped** — backend, frontend and seed. Authored before the numbers "#10"/"#11" were reassigned to Cutlist and Search; see *Tracking 2.0* below for the numbering note.
- `docs/superpowers/specs/2026-05-27-item-project-detail-2-0-design.md` + `docs/superpowers/plans/2026-05-27-item-project-detail-2-0.md` — Item & Project Detail 2.0 (migration `0036`). **Shipped** — backend, frontend, seed data and an e2e spec are all in. See *Item & Project Detail 2.0* below for what shipped and where it departs from the design doc.
- `docs/superpowers/specs/2026-09-24-search-design.md` + `docs/superpowers/plans/2026-09-24-search.md` — Global Search (sub-project #11, Plan V1 §13). **Shipped** (migration `0033`); the plan's checkboxes are kept current with a `→` note per task. See *Global Search* below.
- `docs/superpowers/specs/2026-09-24-material-take-design.md` + `docs/superpowers/plans/2026-09-24-material-take.md` — Material Take → Material Summary (sub-project #12, Plan V1 §19–§20). **Shipped** (migration `0034`); the plan's checkboxes are kept current with a `→` note per task. See *Material Take* below.
- `docs/superpowers/plans/2026-05-09-cutplan-optimiser.md` — shipped-state record for sub-project #9 (CutPlan optimiser: MaxRects + multi-sheet + board_inventory; migrations 0024 + 0025). Written as a stub plan, superseded in flight — the doc carries a planned-vs-shipped table.

## PM Workbench (sub-project #2 + #3)

- Lives on top of Foundation; migrations 0008 (drafter role widening) + 0009 (legacy users -> app_user repoint, projects.pm_id, drop users).
- Drafter-narrow gate: `require_drafter()` — items / modules / parts / hardware_lines / project_hardware_catalog mutations only allow `auth_role IN {drafter, manager, admin}`.
- New routers under `apps/api/app/{home, projects, items, parts, hardware_lines}/`. Mounted in `main.py`.
- Every item-scoped mutation writes both `audit_log` (workspace governance) and `item_edit_log` (item history) in the same DB transaction. Helper: `apps/api/app/edit_log.py`.
- Web routes: `/home`, `/projects`, `/tracking?project_id=`, `/items/[id]?tab=cutlist|hardware|board|log`. (#2 made `/home` the landing page in place of `/dashboard`; **#9a reversed that** — `/home` is now a bare `redirect("/dashboard")` and `/dashboard` is the real landing page.)
- Editor mode is detected by `proxy.ts` writing `x-pathname`; layout reads it and hides TabStrip + SideBar, swapping in a "← Return to home" link.
- State: raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / React Hook Form / Zustand in v1.**
- Procurement UI button on `/tracking` is hidden behind `NEXT_PUBLIC_PROCUREMENT_UI_READY=1`, now defaulted to `1` in `.env.example` (it was absent, so the button was off in every fresh dev setup even though #4 shipped). A `.env` copied before that fix won't have it.
- PDF generation buttons render disabled with tooltip ("ships in sub-project #5").
- **Controlled Lock** (migration `0032`, Q509 — replaces the advisory
  soft-lock). First save still claims ownership. A non-owner's save on a locked
  item is **no longer applied**: `PATCH /items/{id}` answers
  `409 {code: "LOCK_REQUEST_CREATED", …}` and the body is held as an
  `item_lock_request` row. `GET /items/{id}/lock-requests` lists them;
  `POST /lock-requests/{rid}/{approve,reject}` decides, restricted to the lock
  owner or a manager/admin. Approval replays the stored body through the
  ordinary save path — the **edit log credits the requester**, the audit row
  names the approver. Saving again revises your own pending request rather than
  queueing a second (`uniq_pending_lock_request`).
  `event='item.lock_overridden'` is **retired**: nothing emits it, and existing
  rows are history only. Scope is `PATCH /items/{id}` alone, **and there is no
  project-level lock** (Q566: `projects` has no lock column). **Exceptions since
  *Lock checks on module delete* and *Lock checks on the other module and part
  writes*:** every module and part write, and the CV import commit and every
  hardware line write, now answer to the item's locks too (Hard, Approval,
  Controlled). **Since *Lock checks on status and lifecycle*:** `/status`,
  `/items/bulk-status` and `/lifecycle/{stage_key}` answer to the **Hard and
  Controlled** locks — **not the Approval Lock**, which is cleared by a status
  change and so cannot gate one. **Since *Lock checks on attachments and the
  document register*:** every attachment-slot write and every Document Register
  write answers to all three (Hard, Approval, Controlled).
- Lifecycle stage_key (REQ..INST) ≠ items.stage (site location); never use bare "stage" for lifecycle.

## Procurement Workbench (sub-project #4)

- New backend module `apps/api/app/procurement_v1/` mounted at top-level paths
  (`/projects/{pid}/materials`, `/batches`, `/batches/{bid}/allocations`,
  `/procurement-queue`; it also shipped `/catalogs/{type}`, since retired —
  see #7a). The legacy `/procurement/*`
  namespace (orders, vendors, budget, approvals) is **left untouched** and is
  not used by the v1 product surface.
- Migration 0012 adds `procurement_batches.cancelled_at` and two indexes
  (`idx_batches_supplier`, `idx_alloc_batch`).
- `drafter` auth_role is **elevated to PM-parity** on the `orderbook` module
  (read+write+approve+comment) — this widens the matrix narrowed in 0008.
- Web routes:
  - `/orderbook` — cross-project queue grouped by supplier.
  - `/projects/[id]/procurement?tab=materials|batches|catalog` — project
    Procurement page.
  - `/tracking` adds an item-scoped `AvailabilityDrawer` triggered by
    clicking the availability chip; URL state
    `?drawer=item-availability&itemId=N`.
- Soft-cancel semantics: DELETE on `/batches/{bid}` sets `cancelled_at`. A
  batch with non-zero allocations returns 409 — the user must remove
  allocations first.
- Allocation over-commit: POST/PATCH on `/allocations` returns 409 when
  `sum(allocated) > qty_received` (or `qty_ordered` if not yet received).
- Status pill is **derived in SQL** via `CASE`; never persisted.
- All 6 catalog tables use `description` as the readable name and `sku` as
  the SKU (added by migration 0007). Each also has a legacy NOT NULL UNIQUE
  column: `code` (board), `internal_ref` (custom_made), `slab_id`
  (benchtop), `model_number` (appliance), `contract_ref` (equipment_hire).
  `equipment_hire` PK is `hire_id`, not `material_id`, and requires a
  `project_id` FK on insert.
- Seed (`make seed`) inserts one delivered batch + one in-transit batch +
  one allocation on project ALF-001 so the resolution-flow demo works
  out of the box.

## Shop Drawings + File-Upload Subsystem (sub-project #5a)

- New backend modules `apps/api/app/files/` (generic upload subsystem) and
  `apps/api/app/shop_drawings/`. Mounted at top-level paths from `main.py`.
- Migration 0013 adds three tables: `file_blob` (workspace-scoped, sha256-deduped),
  `shop_drawing` (project-scoped, room as free-text tag, points at
  `current_revision_id`), `shop_drawing_revision` (per-upload row, status state
  machine). Partial unique index `uniq_drawing_inflight` enforces "at most one
  draft/pending revision per drawing".
- `drafter` auth_role is **elevated to PM-parity** on the `shop_dwgs` module
  (read+write+approve+comment), continuing the elevated-drafter pattern from
  Procurement Workbench.
- File storage: `LocalDiskStore` behind a `FileStore` Protocol. Default root
  `/uploads`, set via `FILE_STORE_ROOT` env. Layout
  `<root>/<workspace_slug>/<sha256[0:2]>/<sha256>` (content-addressable,
  sharded). `docker-compose.yml` mounts a named `uploads` volume on the api
  service.
- Upload route `POST /files` does magic-byte mime sniff + extension
  cross-check + 25 MB cap + sha256 dedup. Download route `GET /files/{id}` is
  workspace-isolated (404 on cross-workspace) and streams via
  `StreamingResponse` with `Content-Disposition: inline` (RFC 8187 dual
  filename for non-ASCII names).
- Web routes (**superseded by *Shop Drawings register redesign* below** — the card
  grid, drawer and subtabs described here were replaced by a register table, a
  details panel and a full-screen viewer; the API and workflow notes stand):
  - `/shop-dwgs?project=…&subtab=current|in_review|archive&room=…&q=…` —
    list page with subtabs + filter strip + 3-col card grid.
  - `?drawing=N&rev=M` opens a right-side drawer with PDF/image viewer +
    revision history strip + contextual review actions.
- Workflow: `draft → pending → approved | rejected`. The not-uploader rule on
  approve/reject is enforced in the route handler; the partial unique index
  enforces the in-flight invariant. Approve updates
  `shop_drawing.current_revision_id` atomically. Archive 409s on already-
  archived (no silent re-archive); patch enforces creator-or-manager rule.
- Allowed file types: PDF / PNG / JPEG (validated by magic bytes), plus —
  since the 0036 attachment slots — SketchUp `.skp` and Cabinet Vision `.cvj`
  (see *Item & Project Detail 2.0*). SVG, DWG, etc. rejected with 415.
  **Shop drawings themselves still take PDF / PNG / JPEG only**: both bind
  paths check the blob's mime (422 otherwise), because `/files` no longer
  enforces that on its own.
- Thumbnails are deterministic SVG placeholders seeded from `drawing_id`
  (no PDF rendering pipeline in v1).
- Seed (`make seed`) inserts 2 fixture PDFs + 6 demo drawings on ALF-001
  spanning Current / In review / Archive. Re-runnable: the seed block does
  `DELETE FROM shop_drawing WHERE project_id = ALF-001` before inserts so
  it's idempotent.
- Out of scope (deferred to #5b/#5c): item attachments (CV drawing, floor
  plan, site-measure PDF), Combined PDF generation, real PDF thumbnails,
  Templates subtab, iSample tab, orphan blob GC, cloud storage backend,
  unarchive button.

## PDF Generation + Item Attachments (sub-project #5b)

- New backend modules `apps/api/app/item_attachments/` (3-slot CRUD over file_blob)
  and `apps/api/app/printing/` (WeasyPrint engine + Jinja2 templates +
  `cutlist.pdf` / `hardware.pdf` / `combined.pdf` routes). Both mounted at
  top-level paths from `main.py`.
- Migration 0015 adds `item_attachment(item_id, kind, file_blob_id, ...)` with
  `UNIQUE (item_id, kind)` slot constraint and `ON DELETE CASCADE` from items.
  Three legal kinds: `cv_drawing`, `floor_plan`, `site_measure` (**since
  `0036` there are five** — `sketchup` and `cabvision` added beside them; the
  Combined PDF still uses only these three. See *Item & Project Detail 2.0*).
  (Migration
  0014 was the workspace-isolation hardening that landed alongside this
  sub-project — `projects.workspace_id` direct FK + the `(p.pm_id IS NULL OR
  …)` predicate retired.)
- PDF engine: WeasyPrint 63+ (HTML→PDF render) + pypdf 5+ (merge generated
  + uploaded sources). Pango runtime libs added to the api Dockerfile
  (~25 MB). No new container.
- Print templates live at `apps/api/app/printing/templates/{cutlist,hardware,
  cover_combined,painting,missing_attachment}.html` + `print.css`. Inter +
  JetBrains Mono `.woff2` fonts committed under `seed/fonts/` (~400 KB).
- Print routes:
  - `GET /items/{iid}/cutlist.pdf` — render parts table.
  - `GET /items/{iid}/hardware.pdf` — render hardware grouped by **material
    type** (BOARD / HARDWARE / CUSTOM / BENCHTOP / APPLIANCE / HIRE; not by
    supplier — supplier-grouping deferred until catalog enrichment exposes
    per-table supplier columns).
  - `GET /items/{iid}/combined.pdf` — assembles cover + cutlist + hardware +
    3 attachments (or placeholder pages when missing or unparseable) +
    painting page (only when at least one part has `paint_instruction != 'NONE'`).
  - All return `inline; filename=...` Content-Disposition with
    `Cache-Control: no-store`. Browser opens in a new tab via
    `<a target="_blank">`.
- Item attachment routes:
  - `GET /items/{iid}/attachments` — bundle of 3 slots (5 since `0036`),
    populated or null.
  - `POST /items/{iid}/attachments/{kind}` — bind/replace via
    `{file_blob_id}` body. PDF-only mime gate (415 on PNG/JPEG; the
    file_blob table itself remains generic). Since `0036` the gate is per
    slot — `sketchup` / `cabvision` take `.skp` / `.cvj` instead.
  - `DELETE /items/{iid}/attachments/{kind}` — clear slot.
- RBAC: print routes use `("list", "read")` (any reader can print);
  attachment mutations use `("list", "write")` (drafter+, since drafter is
  PM-parity on `list`). The PDF-only gate is enforced in the route handler;
  `bind_attachment` returns `ValueError` which the route maps to 415.
- Workspace isolation: print + attachment routes scope through
  `projects.workspace_id = :w` directly (the workspace-isolation hardening
  in commit `cc7ea11` retired the legacy pm_id chain).
- Audit hooks: `item.print.{cutlist|hardware|combined}` per render;
  `item_attachment.{bind|clear}` per mutation. The bind audit payload includes
  `replaced_file_blob_id` when overwriting an existing slot.
- Web side:
  - New "Attachments" tab in the item editor at
    `apps/web/app/(app)/items/[id]/_components/AttachmentsTab.tsx` with three
    slot cards (one per kind). Each card supports Open / Replace / Delete
    (Replace + Delete gated on drafter+). Wired into `EditorTabs.tsx` via the
    `TABS` const + `TAB_LABELS` map; page.tsx threads `me?.auth_role` through
    as a new prop.
  - The 3 disabled "Print …" buttons in `EditorFooter.tsx` are now live
    `<a href="/api/items/{id}/{kind}.pdf" target="_blank">` download links.
    The Combined button shows a tooltip listing which slots are populated /
    missing (read from a prefetched attachments bundle).
- Seed: first 2 ALF-001 items get attachments on `make seed` — item 1 has
  3/3 slots populated (Combined shows all real PDFs), item 2 has 1/3
  (Combined shows 2 placeholder pages).
- Defensive PDF-merge fallback: `routes.py` validates each attachment's
  bytes via `pypdf.PdfReader` before merging. Unparseable PDFs (corrupt or
  fixture stubs) substitute the `missing_attachment.html` placeholder so the
  Combined render never crashes. Test fixtures benefit from this.
- Out of scope (deferred): iSample (sub-project #5c), async/queued render,
  PDF caching, real attachment thumbnails, PNG/JPEG attachments, supplier
  grouping in Hardware print, custom print templates, async fetch+Blob loading
  indicator (current Combined uses plain `target="_blank"`).

## iSample — Sample Wall (sub-project #5c)

- New backend module `apps/api/app/samples/` (CRUD + workflow + photo bind/clear
  + ledger). Mounted at top-level paths from `main.py`.
- Migration 0016 adds `sample(sample_id, project_id, title, room, hex_swatch,
  supplier, status, review_note, reviewed_by/at, photo_file_blob_id,
  archived_at/by, created_by/at, updated_at)` with hex regex CHECK
  (`^#[0-9A-Fa-f]{6}$`), 3-value status CHECK, and 3 indexes
  (project, project+status composite, partial WHERE archived_at IS NULL).
- RBAC: `isample` row in the matrix gives drafter/manager/admin
  `{read, write, approve, comment}` (PM-parity elevation pattern).
  Editor gets `{read, write}` (no approve). Viewer/purchase_officer get `{read}`.
- Workflow: `pending → approved | rejected`. Reject requires `review_note`.
  Reviewer cannot be the creator (in-handler check). Archive transition
  (creator on own OR manager+) sets `archived_at`. Rejected samples
  auto-show in Archive subtab.
- Subtabs:
  - **Board** = `archived_at IS NULL AND status IN ('pending','approved')`
  - **Approval ledger** = `audit_log` filtered to `event LIKE 'sample.%'`
    for samples in this project, paginated (50/page)
  - **Archive** = `archived_at IS NOT NULL OR status = 'rejected'`
- API endpoints (10):
  - `GET /projects/{pid}/samples?subtab=board|archive&q=&status=&supplier=`
  - `GET /projects/{pid}/samples/ledger?limit=50&offset=0`
  - `GET /samples/{sid}`
  - `POST /projects/{pid}/samples`
  - `PATCH /samples/{sid}` (creator-or-manager+)
  - `POST /samples/{sid}/approve`, `.../reject`, `.../archive`
  - `POST /samples/{sid}/photo`, `DELETE /samples/{sid}/photo`
- Photo handling: optional, single `file_blob_id` (PNG/JPEG only — PDF blobs
  rejected at the route layer with 415). Reuses #5a's `POST /files` upload
  endpoint and `GET /files/{id}` streaming download. Photo-as-background on
  card swatch when present, with hex chip overlay in bottom-right corner.
- Sample IDs displayed as `#SAM-{padded id}` matching #5a's `#SD-{padded}`
  convention. No alpha-prefix scheme.
- Web routes:
  - `/isample?project=…&subtab=board|ledger|archive&q=&status=&supplier=&sample=N&new=1`
  - 5-column responsive grid (drops to 4/3/2/1 columns at smaller widths)
  - Drawer opens on `?sample=N`, deep-linkable
  - "+ New sample" dialog with color picker + optional photo
- Workspace isolation: all queries gate via `projects.workspace_id = :w`
  (post-hardening pattern from `cc7ea11`). Cross-workspace returns 404.
- Audit hooks: `sample.{create|update|approve|reject|archive|upload_photo|clear_photo}`.
  The Approval ledger view IS this audit_log filtered.
- Seed: `make seed` adds 6 demo samples on ALF-001 — 2 approved + 2 pending
  (one with photo) + 1 rejected + 1 archived. Header reads
  `6 samples · 2 awaiting client · 3 approved · 1 rejected`.
- Out of scope (deferred): Suppliers as a real registry (free-text only),
  Clients tab (no client-facing surface), sample revisions (rejected =
  create new), Print Sample Board to PDF, real-time client signoff via link,
  bulk actions, sample categories, item linking, unarchive UI.

## Catalog enrichment + CV Mappings (sub-project #7a)

- New backend module `apps/api/app/catalog/` mounted at `/catalog/*`
  (singular). 7 sub-routers: 6 per
  material type (`board-materials`, `hardware-materials`, `custom-made`,
  `benchtop-materials`, `appliances`, `equipment-hire`) plus
  `/catalog/cv-mappings`. RBAC gate `("catalog", action)`.
- Migration 0017 adds 5 enrichment columns (`synonyms text[]`,
  `default_supplier`, `default_lead_time_days`, `archived_at`, `archived_by`)
  to all 6 catalog tables, plus a GIN index on `synonyms` and a partial
  active-row index. Also CREATEs `cv_material_mapping` (workspace-scoped
  UNIQUE on `(workspace_id, cv_code)`).
- New `catalog` row in the RBAC matrix. Drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`;
  purchase_officer `{read,comment}`; viewer `{read}`. Editor gets `write` so
  Foreman/Machine team can propose catalog edits.
- Soft-archive only — POST `/catalog/{slug}/{mid}/archive` sets
  `archived_at`+`archived_by`; 409 on already-archived. Hard delete is
  reserved for `cv_material_mapping`.
- Bulk import is all-or-nothing. POST `/catalog/{slug}/bulk` validates every
  row first; if any row fails Pydantic, returns `{created: 0, errors: [...]}`
  without inserting. Audit: one `catalog.{table}.csv_import` row per import
  (not per row).
- Web routes:
  - `/catalog?tab=board|hardware|custom_made|benchtop|appliance|hire|stock|cv-mappings`
    (`stock` added by 0025; `stock` and `cv-mappings` are self-contained
    panels — the six catalog-table tabs are typed as `MaterialTab`)
  - Reached from the `Catalog` entry on the TabStrip secondary row (it was a
    SideBar link when #7a shipped; #9a moved it). Not permission-gated.
- Workspace isolation enforced on every read + write via `workspace_id`
  column (already on the 6 catalog tables from migration 0007;
  added to `cv_material_mapping` by 0017). Cross-workspace returns 404.
- Route ordering caveat: cv-mapping routes (`/catalog/cv-mappings*`) are
  declared BEFORE the parameterised `/catalog/{slug}` routes in
  `apps/api/app/catalog/routes.py` so the literal path wins.
- **`/catalog/*` is the only surface for these six tables.** The parallel
  `/catalogs/*` (plural) module that Procurement Workbench v1 shipped —
  gated on `orderbook`, unscoped by workspace, and hard-deleting on DELETE —
  has been **retired**; the convergence #7a deferred is done. The project
  Procurement page's Catalog tab reads and writes through `/catalog/{slug}`.
  Guards in `test_catalog_routes.py` fail if the plural namespace returns.
  Removal is soft-archive only: there is no DELETE route on a catalog row.
  (Hard delete remains legal for `cv_material_mapping` alone.)
- Seed (`make seed`) enriches the existing 2 board_materials + 4
  hardware_materials with synonyms/supplier/lead-time, adds 4 new demo
  boards (BM-101..BM-104), and inserts 2 demo cv_material_mapping rows
  (`'18-PB' → board_materials.BM-001`, `'700.0KC2.054.00' →
  hardware_materials.HM-002`). Idempotent.
- Out of scope (deferred to #7b): `cv_import_run`, the Cutlist tab CV
  import wizard, the synonym-fuzzy resolver. (Deferred to #7c): Board tab,
  `/cut-floor` page, CutPlan, CutSchedule.

## CV Import wizard (sub-project #7b)

- New backend module `apps/api/app/cv/` — `parser.py` (CSV header
  normalisation + row coercion), `resolver.py` (mapping → synonyms[] →
  exact-sku → unknown), `queries.py` (run lifecycle + commit transaction),
  `routes.py` (4 routes mounted at top-level paths).
- Migration 0018 adds `cv_import_run(cv_import_run_id, project_id, item_id,
  source_filename, sha256, row_count, status, started_at, completed_at,
  error_log jsonb, created_by)` with status CHECK
  ('preview','committed','failed') and 2 indexes
  (`idx_cv_import_run_item`, `idx_cv_import_run_status`).
- New `cut_floor` row in the RBAC matrix (sits between `catalog` and
  `it_management` in `_ALL_MODULES`). Drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`;
  purchase_officer/viewer `{read}`. The full `/cut-floor` page + CutPlan +
  Board tab arrive in #7c — #7b only consumes the row from the CV import
  routes here.
- 5 routes:
  - `POST /items/{iid}/cv-imports/preview` — multipart `file` OR form
    field `body`. Parses, resolves, persists `cv_import_run` with
    `status='preview'` and the full snapshot in `error_log`.
  - `POST /items/{iid}/cv-imports/{run_id}/commit` — body `CvCommitIn`,
    optional `?mode=replace`. Single transaction inserts modules + parts +
    catalog rows + mappings + audit/edit log; flips run to `committed`.
  - `GET /items/{iid}/cv-imports` — history (newest first).
  - `GET /items/{iid}/cv-imports/replace-impact` (`cut_floor:write`, the
    commit's own gate; *added later, see below*) — `{modules, live_comments}`.
  - `GET /cv-imports/{run_id}` — single run + cached preview snapshot.
- 3-phase wizard mounted in the Drafter Editor Cutlist tab via
  `?tab=cutlist&import=cv`. Phase A (paste/upload), Phase B (resolve
  unknown codes inline — `Use existing` is disabled in v1; `Create new`
  ships for the 5 simple catalog tables; `Skip` always available),
  Phase C (confirm + optional **Replace existing modules** checkbox when
  the item already has modules — and, when those modules carry comments, an
  amber warning naming how many will be deleted with them).
- **Replace warns about the comments it deletes** (*added later; the user chose
  a **wizard warning only**, asked before building*). A comment cascades with the
  module it is on (migration `0043`), so `?mode=replace` deleted every module
  thread of the item without saying so. Now: Phase C fetches
  `GET /items/{iid}/cv-imports/replace-impact` **fresh when the step opens** (not
  from the preview, whose snapshot can be minutes old) and shows
  "**N comments** on these modules will be permanently deleted…" when N > 0; if
  the check itself fails it says so rather than stay silent. **The count is live
  comments, replies included** (`deleted_at IS NULL`, user's choice) — the
  cascade also removes soft-deleted rows, which are already gone from every
  screen, so the true row count can be higher. **The API is unchanged in what it
  allows**: `replace` is still an explicit opt-in and is *not* refused or gated
  on an acknowledgement (the user declined that). What changed is that the loss is
  now visible afterwards: `CvCommitOut.replaced_comment_count`, the
  `cv.import.replace_wipe` audit payload (`deleted_comment_count`) and the
  `cv.import.commit` payload (`replaced_comment_count`) carry the number, counted
  **before** the DELETE. The wizard's done message repeats it. Tests:
  five new in `test_cv_routes.py` (live-only count scoped to this item; zero
  case; 403 for a viewer / 404 for another workspace's item; the response and both
  audit rows; a first import reports 0) — **all five fail against the unfixed
  source**; `tests/e2e/cv_replace_comments.spec.ts` (3), re-runnable and run three
  times back to back beside `cv_import.spec.ts` (which shares `JO-TP01`).
- File caps enforced server-side: 1 MB hard cap (`MAX_CSV_BYTES`),
  10 000 logical rows (`MAX_LOGICAL_ROWS`). 415 with
  `code='FILE_TOO_LARGE'` or `code='TOO_MANY_ROWS'` if exceeded.
- Resolver order (per spec §6.2): `cv_material_mapping` → catalog
  `synonyms[]` (single-table hit) → catalog `sku` exact match → unknown.
  Multiple-table hit returns `unknown` with hint
  `multiple_synonym_matches`. Workspace-isolated everywhere via
  `WHERE workspace_id = :w`.
- Re-import: default 409 with `code='ITEM_NOT_EMPTY'` if the item already
  has modules. `?mode=replace` (or `body.replace=true`) wipes via
  DELETE-CASCADE and re-imports; audit emits `cv.import.replace_wipe`
  with `deleted_module_ids`.
- Commit transaction (per spec §6.6): inserts new catalog rows from
  `create_new` resolutions (legacy NOT NULL UNIQUE column derived from
  `sku`), writes `cv_material_mapping` for `use_existing`/`create_new`
  resolutions without a prior mapping, inserts modules + parts (parts
  with `paint_instruction='NONE'`), writes audit (`cv.import.commit` +
  per-part `part.create` + per-module `module.create`) and item_edit_log
  (per module `_create_module`, per part `_create_part`, one summary
  `_cv_import` row). Rollback on error sets `status='failed'` and emits
  `cv.import.fail`.
- **Schema constraint**: `parts` only has `board_material_id` (not a
  generic material FK), so non-board CV codes persist with
  `board_material_id=NULL`; the resolution trace is preserved in the
  `cv.import.commit` audit payload + `cv_import_run.error_log` snapshot
  + the part's `comment` field (`[material: {table}#{id}]`).
- Preview snapshot: full `CvPreviewOut` is stored in
  `cv_import_run.error_log` under key `_preview_snapshot`. The commit
  endpoint also reads `_parsed_parts` and `_resolutions` from the same
  jsonb column to rehydrate without re-parsing.
- "Create new" mini-form ships for the 5 simple catalog tables
  (board / hardware / custom_made / benchtop / appliances). Equipment
  Hire is disabled with a tooltip linking to `/catalog?tab=hire` (it
  requires a project_id FK on insert).
- Seed (`make seed`) writes 1 committed `cv_import_run` row on ALF-001
  item 1 (no real modules/parts inserted — they already exist from the
  PM Workbench seed). Idempotent: deletes existing rows for the item
  before inserting.
- Out of scope (deferred to #7c): CutPlan / CutSchedule / Board tab /
  `/cut-floor` page, Phase B `Use existing` typeahead. (Indefinite):
  bin-packing optimiser, three-way merge re-import UI, Cabinet Vision
  API integration.

## Cut Floor — CutPlan + CutSchedule + Board tab (sub-project #7c)

- New backend module `apps/api/app/cut_floor/` (schemas / queries /
  routes). All routes gated by `("cut_floor", action)`. The RBAC row
  itself was added in #7b — drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`
  (Machine team can mutate but not approve); purchase_officer / viewer
  `{read}` only.
- Migration 0019 adds `part_slot.part_id` (nullable FK →
  `parts(part_id)` ON DELETE SET NULL), `cut_schedule.{priority,
  assigned_to, created_at, created_by, updated_at}`, and
  `cut_plan.{created_by, notes}`. Two new indexes: `idx_part_slot_part`
  + `idx_cut_schedule_date_priority`.
- Note: existing `cut_plan` / `cut_sheet` / `part_slot` /
  `cut_schedule` PKs are named `id`, not `cut_plan_id` etc. Code
  follows the actual column names.
- Routes:
  - **CutPlan**: `POST /projects/{pid}/cut-plans` (single transaction
    creates plan + sheets + slots), `GET /projects/{pid}/cut-plans`
    (newest first), `GET /cut-plans/{plan_id}` (full nested),
    `GET /items/{iid}/cut-plan` (latest plan filtered to sheets that
    contain ≥1 slot for this item; foreign slots flagged `is_foreign`),
    `DELETE /cut-plans/{plan_id}` (409 with code `PLAN_HAS_SCHEDULES`
    when any non-cancelled `cut_schedule` references it; else hard
    delete + CASCADE).
  - **CutSchedule**: `GET /cut-schedules?date=&project_id=&status=`,
    `GET /cut-schedules/{sid}`, `POST /cut-schedules` (auto
    `priority = MAX + 100` for the day, or `100`),
    `PATCH /cut-schedules/{sid}` (transitions enforced — see below),
    `POST /cut-schedules/reorder` (rewrites priorities densely as
    `100, 200, 300 …` for an ordered id list of one date),
    `DELETE /cut-schedules/{sid}` (soft-cancel; second cancel is 409).
- Status transition matrix (binding):
  `planned → running → done`, plus `planned/running → cancelled`. Any
  other transition (e.g. `done → running`, `cancelled → *`) returns
  409 `{code: "BAD_TRANSITION", from, to}`.
- Workspace isolation everywhere via `cut_plan.workspace_id`. Cut
  schedules join through cut_plan; cut sheets and part slots join
  through cut_plan. Cross-workspace reads return 404.
- **Fixed later.** `cut_schedule.assigned_to` is a plain FK to `app_user`
  with no workspace check of its own, and `list_cut_schedules` /
  `get_cut_schedule` join it to `full_name` for display — unlike its sibling
  `shop_floor`, which validates every `worker_id` against
  `(workspace_id, is_shop_worker)`, `POST /cut-schedules` and
  `PATCH /cut-schedules/{sid}` accepted any `app_user.id` in the whole
  database, so a caller could assign (and thereby leak the name of) a user
  from a different workspace. `queries.user_in_workspace()` (same shape as
  `items/queries.py::_user_in_workspace` for `contractor_id`) now guards
  both routes; unvalidated ids get `422`. Pinned by
  `test_create_cut_schedule_rejects_foreign_assigned_to` /
  `test_patch_cut_schedule_rejects_foreign_assigned_to`.
- **Fixed later.** `has_active_schedules()` (the guard behind
  `DELETE /cut-plans/{plan_id}`'s `PLAN_HAS_SCHEDULES` 409, above) only
  blocked `planned`/`running` schedules — contradicting this file's own
  "non-cancelled" wording and letting a plan with a **`done`** schedule
  (a record that a nest was actually cut) hard-delete via `CASCADE`, taking
  that production record with it. `DELETE /cut-plans/{plan_id}` now blocks
  on any status other than `cancelled`, matching the documented rule; only
  a cancelled schedule no longer blocks deletion. Pinned by
  `test_delete_cut_plan_blocks_when_done_schedule_exists`, confirmed to
  fail (204 instead of 409) against the pre-fix code.
- Foreign-slot rule: `GET /items/{iid}/cut-plan` returns only sheets
  that contain ≥1 slot for the item (or its modules' parts). Slots
  whose `part_id` is null or belongs to *other* items in the project
  carry `is_foreign=true`. Slot label fallback order: `slot.label` →
  joined `parts.part_name` → `"slot {id}"`.
- Web routes:
  - **`/cut-floor?date=YYYY-MM-DD&project=`** — Machine team daily
    list. Date picker + back/forward arrows + project filter chip
    (defaults to "All projects"). `mutator` roles drag-reorder rows
    via HTML5 DnD. Each row: status pill + priority + plan name +
    assignee + Start / Mark done / Cancel.
  - **Item editor `/items/{id}?tab=board`** — `BoardTab.tsx` fetches
    `/api/items/{id}/cut-plan` and renders one SVG per sheet at
    800-px viewport, scaled to sheet dimensions. This-item slots fill
    `--h-accent` 60%; foreign slots fill `--h-line` 30%. Tooltip on
    hover. Empty state: "No CutPlan yet for this project."
  - Reached from the `Cut Floor` entry on the TabStrip secondary row
    (a SideBar link when #7c shipped; #9a moved it).
- Audit events: `cut_plan.{create,delete}`,
  `cut_schedule.{create,update,status_change,reorder,cancel}`. All
  routed through `apps/api/app/auth/audit.py::write_audit`.
- Seed (`make seed`) on ALF-001: 1 cut_plan "ALF-001 v1 nest", 1
  sheet (18-PB), **5 part_slots** (3 own + 2 foreign, for the Board-tab
  demo), and 2 cut_schedule rows (`running` today + `planned`
  tomorrow). Idempotent — `DELETE FROM cut_plan WHERE project_id =
  ALF-001` runs first.
- Out of scope **for #7c** (the optimiser it reserved
  `POST /projects/{pid}/optimise` for shipped later, in #9): CutPlan edit
  UI (v1 = create + delete + replace by creating a new plan),
  WebSocket schedule updates, `@dnd-kit/core`, mobile UI for
  `/cut-floor`, `cut_plan.is_current` flag (Board tab uses
  `MAX(id)`), CutSchedule export to PDF.

## Shop Floor Ops (sub-project #8)

> **Re-keyed by migration `0030` (B3).** `worker_assignment` and
> `stage_completion_log` now key on **`(cutlist_id, stage_key)`**, not the
> item — the production workflow belongs to the cutlist (Plan V1 Q412).
> `worker_assignment.item_id` is **gone**; `stage_completion_log.item_id`
> survives nullable as pre-`0030` provenance only. Completing a stage fans
> `item_stages.done_date` out to every linked item whose own order contains it
> (Q439 + Q562), and undo reverses the whole cutlist (Q446). Scope was the
> five production stages only when B3 shipped — **DEL and INST are still not
> assignable** (Q561) — but migration `0039` added **Packing** as a real 6th
> assignable stage (Q519); see *QC / Rework / Packing* further down. The
> notes below otherwise stand.

- Migration 0020 adds `app_user.is_shop_worker` (bool default false),
  `items.paint_after_assembly` (bool default false; when true the
  lifecycle order becomes DOWN → CNC → EDGED → MADE → PAINTED),
  `worker_assignment` (mutable assignment state with the partial
  unique index `uniq_active_assignment` on `(item_id, stage_key)
  WHERE status IN ('assigned','in_progress')`), and
  `stage_completion_log` (append-only history with `undone_at` soft-
  undo marker).
- New 10th IA module **`shop_floor`**. Foreman + Machine team both
  map to `editor` (`{read, write, comment}`); admin/manager get
  approve too; drafter `{read, comment}`; viewer / purchase_officer
  `{read}` only. Restrictions on who can override an in-progress
  assignment held by another worker are enforced in route handlers,
  not the matrix.
- Backend module `apps/api/app/shop_floor/` — `schemas.py`,
  `lifecycle.py` (pure helpers — `shop_floor_order`,
  `prior_stages`, `is_within_undo_window`), `queries.py`
  (workspace-isolated text() SQL, FOR UPDATE on mark-done +
  undo paths), `routes.py` mounting 10 endpoints:
  - `GET /projects/{pid}/shop-floor/board`
  - `GET /projects/{pid}/shop-floor/workers`
  - `GET /workers/{wid}/queue`
  - `GET /workers/{wid}/recent-completions`
  - `POST /projects/{pid}/items/{iid}/assignments`
  - `PATCH /assignments/{aid}` (reassign clears `started_at` and
    resets status to `assigned` per user decision)
  - `DELETE /assignments/{aid}` (soft-cancel)
  - `POST /assignments/{aid}/start` (idempotent)
  - `POST /assignments/{aid}/complete` (single transaction:
    `stage_completion_log` + `item_stages.done_date` +
    `worker_assignment.status='done'` + audit)
  - `POST /completions/{log_id}/undo` (worker <5 min via
    `is_within_undo_window`; supervisor any time)
- Status machine binding: `assigned → in_progress → done`, plus
  `assigned/in_progress → cancelled`. `done → in_progress` only via
  the undo path. `done → cancelled` is rejected at both DELETE and
  PATCH layers.
- Duplicate-active-assignment 409 surfaces the existing
  `assignment_id`, `worker_id`, `worker_name`, `status` so the UI
  can redirect to reassign instead of pleading retry (per user
  decision).
- Stage ordering enforced by `prior_stages_done()` reading
  `items.painting_req` AND `items.paint_after_assembly`. Mark-done
  for `CNC` before `DOWN` returns `409 STAGE_OUT_OF_ORDER` with the
  `missing` list. PAINTED is skipped from the order entirely when
  `painting_req = false`.
- Workspace isolation: every read/write joins `items.project_id ->
  projects.workspace_id`. Cross-workspace GETs and POSTs return 404.
- Worker-toggle endpoint at `PATCH /users/{uid}/shop-worker` (gated
  `("it_management", "write")` — admin-only). Audit event
  `it.worker_toggle`.
- Deactivating (`PATCH /users/{uid}` `is_active=false`) or un-flagging
  (`PATCH /users/{uid}/shop-worker` `is_shop_worker=false`) a worker who
  still holds `assigned`/`in_progress` assignments returns
  `409 HAS_ACTIVE_ASSIGNMENTS` (listing them) and changes nothing — reassign
  or cancel first (spec §15 Q3). `shop_floor.queries.active_assignments_for_worker`
  + `users.routes._guard_active_assignments`.
- Web routes:
  - **`/shop-floor?project=…`** — Foreman office board. Kanban
    DOWN | CNC | EDGED | PAINTED | MADE (**+ PACKING, a 6th column
    since migration `0039`** — see *QC / Rework / Packing* below).
    Per-card status pill + worker chip + reassign select + cancel
    button. Inline `AssignDialog`. 15-second polling.
  - **`/shop-floor/station/[worker_id]`** — kiosk display. Active
    card prominent (~70% viewport), big emerald Mark-done button on
    the in-progress card; the worker's own browser session sees the
    `UndoBannerStack` for completions in the last 5 minutes.
  - `/it` — admin-only `WorkerRosterPanel` listing every workspace
    user with a checkbox to toggle `is_shop_worker`. Optimistic
    update with revert on failure.
  - Reached from the `Shop Floor` entry on the TabStrip secondary row
    (a SideBar link when #8 shipped; #9a moved it).
- Audit hooks: `shop_floor.{assign|reassign|unassign|stage_start|
  stage_complete|stage_undo}` plus `shop_floor.assign_note_update`
  for note-only PATCH and `it.worker_toggle` for the admin roster
  panel.
- Seed (`make seed`) adds 4 shop workers to the staff roster and
  inserts **5 demo assignments** on ALF-001, one per item (one
  `in_progress`, one `done` with matching `stage_completion_log` and
  yesterday's `item_stages.done_date`, three `assigned`). The block asks
  for up to 6 (`LIMIT 6` items) but the demo project yields 5. Idempotent
  — wipes the ALF-001 shop-floor demo state before re-seeding.
- Out of scope (deferred): mobile-first responsive UI, real-time
  pub/sub (15-s poll instead), efficiency analytics dashboards,
  per-part painting tracking, `time_record` table for payroll,
  worker self-assignment, quality / rework loop, cross-project
  worker view, per-worker login (kiosk URL = pseudo-auth), PM
  "today's completions" widget on `/tracking`.

## Estimating (sub-project #9a)

> **Built without a spec or plan.** #9a shipped directly (commit `a7b8d3d`
> + follow-ups); the design record was backfilled afterwards as
> `docs/superpowers/plans/2026-05-26-estimating.md`, which explains *why*
> the schema and workflow read as they do. **This section stays the
> statement of current state.** #9 (CutPlan optimiser) is a *different*
> sub-project; it shipped after #9a, which is why estimating holds
> migration slots 0021–0023 and the optimiser's `grain_locked` landed
> as 0024.

> **Superseded by Plan V1 §I (migration `0038`).** The six-state
> `draft → sent → accepted/rejected/expired/withdrawn` workflow described
> below is **replaced**, not extended, by the 12-stage tender lifecycle —
> see *Tender Lifecycle + Financials* further down for the current state
> machine, Convert behaviour and endpoint list. The schema (`estimate`,
> `estimate_revision`, lines, snapshot columns), migrations 0021–0023, the
> `estimator` role and the RBAC/module points below all still stand
> unchanged; only the status enum, `_LEGAL_TRANSITIONS`, and the
> send/convert routes were rewritten. Kept here for the parts that are
> still accurate; don't read the "Revision workflow" or "Convert-to-Project"
> bullets below as current.

- New backend module `apps/api/app/estimating/` (`schemas.py`,
  `queries.py`, `routes.py`, `pdf.py` + `templates/quote.html`).
  Mounted at top-level paths from `main.py` (no path prefix — routes
  live at `/customers`, `/estimates`, `/revisions/{rid}/…`,
  `/lines/{lid}/…`, `/it/labour-rates`). All gated by
  `require_permission("estimating", action)` except `/it/labour-rates`
  (gated `("it_management", …)` — admin-only).
- **New 7th auth role `estimator`** (migration 0021 widens the
  `app_user.auth_role` CHECK). RBAC matrix (`apps/api/app/auth/permissions.py`):
  estimator gets `{read,write,approve,comment}` on `estimating`, plus
  read/comment across the other modules; `it_management` empty. All
  other roles get `estimating` read-only except drafter (`read,comment`).
  This is the first role added since drafter — the matrix now has
  **7 roles × 11 modules** (`estimating` is the 10th operational
  module, `it_management` the admin-only 11th).
- **New `estimating` IA module** in `_ALL_MODULES` (between
  `shop_floor` and `it_management`).
- Migrations:
  - **0021 `estimating_core`** — widens auth_role CHECK; creates
    `customer`, `estimate`, `estimate_revision`, `estimate_line`,
    `estimate_line_part` / `_hardware` / `_labour`,
    `workspace_labour_rate`; adds `projects.customer_id` +
    `projects.estimate_revision_id` (both nullable FKs, set on
    Convert). **Downgrade is a no-op** (irreversible; recover from
    0001–0020).
  - **0022 `estimate_expires_at`** — nullable `estimate_revision.expires_at`
    date (quote validity window).
  - **0023 `team_status`** — adds `app_user.work_status`
    (`IN|ON_SITE|SHOP|WFH|OFF`, nullable) + `location_label`. Backs the
    dashboard Team card, not estimating per se.
- **Data model.** `estimate` is the root (one per quoted job);
  `estimate_revision` is revisioned (`rev_no`, immutable once it leaves
  `draft`). Cost columns on lines/parts/hardware/labour are
  **snapshotted** (`*_snapshot`, `cost_extended` GENERATED) so a locked
  quote's numbers never drift when the live catalog changes; the live
  `material_id` ref is retained alongside for traceability. Partial
  unique index `uniq_estimate_draft` enforces at most one `draft`
  revision per estimate. `estimate_line_labour` snapshots the
  per-stage `workspace_labour_rate` on insert (UNIQUE on
  `(line_id, stage_key)`).
  - **Equipment hire is excluded** from `estimate_line_hardware`
    (`material_type IN ('HARDWARE','APPLIANCE')` only) — hire rows are
    project-scoped (`project_id` FK on the catalog row) and can't be
    referenced from a pre-project quote.
  - `estimate_line_part.material_type IN ('BOARD','CUSTOM','BENCHTOP')`.
- **Fixed later.** `create_line()` computed `SELECT COALESCE(MAX(seq), 0) + 1`
  against `estimate_line` and inserted without locking the parent revision —
  the `(revision_id, seq)` index (`0021`) is a plain index, not unique, so two
  concurrent `POST /revisions/{rid}/lines` calls on the same draft (a
  double-click, two tabs) could both read the same `MAX(seq)` and insert a
  duplicate. `create_line()` now calls the existing `lock_revision_for_update()`
  helper (already used by the status-transition and Convert paths) instead of
  the unlocked `_assert_draft()`, so a concurrent create on the same revision
  serializes instead of racing. No migration — `reorder_lines`/`patch_line`/
  `delete_line` never generate a new `seq`, so they weren't exposed. Pinned by
  `test_concurrent_create_line_serializes_instead_of_duplicating_seq`
  (`test_estimating_line_seq_race.py`), which reproduces the race with two
  real DB sessions on separate threads and confirms it fails against the
  pre-fix code (`[1, 1]` instead of `[1, 2]`).
- **Revision workflow (superseded — see *Tender Lifecycle + Financials*).**
  `_LEGAL_TRANSITIONS` in `queries.py` was the six-state
  `draft → sent|withdrawn`; `sent → accepted|rejected|expired|withdrawn`
  graph. Migration `0038` replaced it with the 12-stage lifecycle;
  `send` no longer exists as an action (folded into `advance`).
- **Convert-to-Project (superseded — see *Tender Lifecycle + Financials*).**
  `POST /revisions/{rid}/convert` still requires status `WON`
  (`409 BAD_STATUS` otherwise) and still rejects already-converted
  (`409 ALREADY_CONVERTED`) and archived-customer, but now also takes a
  body selecting which lines convert (Q490) and creates a
  `project_contract` row (Q491) alongside the project.
- **Endpoint count changed** — `/revisions/{rid}/send` was retired in
  favour of `/revisions/{rid}/advance`, and `/revisions/{rid}/handover-preview`
  was added; see *Tender Lifecycle + Financials* for the current list.
  Otherwise unchanged: Customers CRUD + archive; estimates list/detail/
  create/patch/revise; revision detail + patch + status transitions;
  line CRUD + reorder; per-line part / hardware / labour add/patch/delete;
  `GET /it/labour-rates` + `PATCH /it/labour-rates`;
  `GET /revisions/{rid}/quote.pdf` (WeasyPrint, `inline` with RFC 8187
  dual filename).
- Audit hooks: `customer.create` (+ patch/archive via queries),
  `estimate.{create|update|revise|line_add|line_edit|line_delete|
  line_reorder|part_add|part_edit|part_remove|hardware_add|hardware_edit|
  hardware_remove|labour_set|labour_clear|send|accept|reject|expire|
  withdraw|convert|print}`.
- Web routes:
  - `/estimating?subtab=active|archive&q=&customer=&status=` — list +
    `/estimating/[eid]` detail editor (`EstimatingClient` /
    `EstimateDetailClient`).
  - `/customers?q=&include_archived=` — customer registry
    (`/customers/[cid]` detail).
  - Both are new **secondary** TabStrip entries (see chrome changes
    below), not top-6 IA tabs.
- Seed (`make seed`): adds a 9th staff user
  (`kai.ngata@hartwood.test`, role `estimator`), 10 `workspace_labour_rate`
  rows (one per stage), 2 customers, and 3 demo `EST-2026-*` estimates.
  Idempotent — wipes `EST-2026-*` for the workspace before reinserting.
- Out of scope (deferred): ~~PO/supplier-order generation from a won quote~~
  **built, see *PO Generation from a Won Quote* below** (Convert still stops
  at project + contract creation — see *Tender Lifecycle + Financials* for
  what Convert gained), multi-currency, client
  e-signature / portal, estimate templates, per-line margin overrides
  beyond `unit_sell_override`, revision diff UI.

### Cross-cutting changes that shipped with #9a

These landed in the same batch (commits `a7b8d3d`, `620930e`,
`b910ab1`) and touch shared chrome — note them before editing those
surfaces:

- **`/home` → `/dashboard` rename.** `/home` now just
  `redirect("/dashboard")`. The real landing page is `/dashboard` (Team
  card + live workspace stats).
- **Public stats endpoint** `GET /public/stats` (`app/public/routes.py`,
  no auth) feeds the dashboard + the login page's stats block (no more
  hardcoded numbers).
- **Team-status feature.** `PATCH /me/status` (`work_status` +
  `location_label`, audit `user.status`) and
  `GET /workspace/team` (`team_router`, prefix `/workspace`) power the
  dashboard Team card.
- **TabStrip secondary row.** Beyond the fixed 6 top tabs, a secondary
  strip now carries `Catalog · Shop Floor · Cut Floor · Estimating ·
  Customers` (`apps/web/components/chrome/TabStrip.tsx`).
- **Design tokens expanded** to the full hi-fi palette
  (`ink2/3/4`, `surfaceAlt`, `accentSoft`, `info`) in `globals.css` —
  the previously-deferred richer palette from `legacy/` is now wired.
- **Tracking overhaul.** `TrackingClient` refactored into quick-filter
  chips + sub-tabs + search; new `ItemsTable`, `ItemDetailModal`,
  `ProjectDetailModal`, `StatusPopup`, `ProjectInfoBar`,
  `TrackingMetrics`. CUTLIST number links to `/items/[id]`; the ▶
  triangle opens `ItemDetailModal`. Status change accepts an optional
  note. The `/list` route is now wired (project switcher + search +
  the shared `ItemsTable`).

## CutPlan Optimiser (sub-project #9 + engine)

- Ships the wire contract + UI flow **and** a real nesting engine. The
  original naive shelf packer is kept as a selectable fallback / A/B
  baseline. Spec source: cabinet-vision design §8.1.
- Migration **0024 `grain_locked`** adds `grain_locked boolean NOT NULL
  DEFAULT false` to `board_materials` + `benchtop_materials`. Grain-locked
  parts are never rotated by the optimiser. (This is the migration the
  `2026-05-09` plan originally reserved as 0021 — renumbered after #9a
  consumed 0021–0023.)
- **`apps/api/app/cut_floor/optimiser.py`** — pure stdlib module (no DB, no
  Pydantic; unit-tested against deterministic inputs). Dataclasses
  `PackPart` (now carries a `uid` for multi-sheet tracking) / `PlacedSlot` /
  `Skip` / `PackResult` / `MultiPackResult`. Three packers:
  - `pack_naive` — shelf next-fit-decreasing (the original stub; baseline).
  - `pack_maxrects` — **MaxRects** nester. Places parts largest-first; runs
    three free-rect choice heuristics (Best-Short-Side-Fit,
    Best-Area-Fit, Bottom-Left) and keeps the best-yielding sheet. Splits
    free space against the part inflated by `kerf` so neighbours keep a saw
    gap; rotates non grain-locked parts. Robustly ≥ `pack_naive` on mixed
    parts, matches it on uniform grids.
  - `pack_sheets(parts, …, strategy, max_sheets)` — **multi-sheet** wrapper:
    overflow (`no_room`) parts roll onto a fresh sheet until placed or
    `max_sheets` is hit; `too_large` parts (bigger than the sheet) are never
    retried. Returns `MultiPackResult { sheets: [PackResult], skipped }`.
- **`POST /projects/{pid}/optimise`** (gated `("cut_floor","write")`) —
  pulls candidate parts (`candidate_parts_for_optimise`: parts → modules →
  items → project, with real dims, joined to their board material's
  `grain_locked`), expands each by `qty` (assigning a `uid`), calls
  `pack_sheets`, and returns `OptimiseOut { proposal: CutPlanIn, summary }`
  with **N** `CutSheetIn`. **Pure function: no DB writes, no audit, no
  commit.** The user reviews the proposal then forwards it to the existing
  `POST /projects/{pid}/cut-plans` (#7c), which owns persistence + the
  `cut_plan.create` audit. `OptimiseIn` gains `strategy` (`maxrects` default
  | `naive`) + `max_sheets` (default 20); `OptimiseSummary` gains
  `sheet_utilization[]` (per sheet) and `utilization_pct` is the mean across
  sheets used. Empty / all-oversized input → zero sheets in the proposal.
- Sheet stock is a **per-optimisation override** — `sheet_len_mm`,
  `sheet_wid_mm`, `kerf_mm` come in the request body (no
  `board_inventory` table yet).
- `grain_locked` round-trips through the catalog: added to the `board` +
  `benchtop` REGISTRY select/insert columns in
  `apps/api/app/catalog/queries.py` and to `PatchBoardIn` / `PatchBenchtopIn`.
- Web:
  - Shared **`SheetCanvas.tsx`** (`cut-floor/_components/`) — the SVG
    sheet renderer extracted from `BoardTab.tsx`; both surfaces import it.
    Known sheet dims pass `extent`; the Board tab infers extent from slots.
  - **`OptimiseDialog.tsx`** — two-phase: a form (project · plan name ·
    material SKU · sheet dims · kerf · **Algorithm** selector) → a preview
    (summary + one `SheetCanvas` **per sheet** + skipped-parts list) →
    **Save as plan** forwards the multi-sheet proposal to `createCutPlan`.
    Opened by an **Optimise…** button on the `/cut-floor` header (mutator
    roles only).
  - `/catalog?tab=board|benchtop` grid gains a **Grain** checkbox column
    that PATCHes `grain_locked`.
- Seed (`make seed`): grain-locks the walnut veneer demo board
  (`BM-103`) on ALF-001. Idempotent (an `UPDATE` after the DO-NOTHING
  insert).
- Dialog UX (shipped later): material-SKU **typeahead** (a `datalist` fed by
  `listCatalog`; the field stays free-text) and an **item picker** — a checkbox
  list of the project's items wired to `include_only_item_ids`. An empty
  `include_only_item_ids` means *no items*, not *no filter*
  (`candidate_parts_for_optimise` short-circuits); the dialog also disables
  **Optimise** when nothing is selected.
- Out of scope (still deferred): non-rectangular parts, grain-direction SVG
  visualisation, saving draft proposals, stock **consumption** (see below —
  `/optimise` reads stock but never reserves or decrements it).

## Board inventory — sheet stock (migration 0025)

- Migration **0025 `board_inventory`** — one row per (workspace, board
  material, sheet size): `len_mm`, `wid_mm`, `qty_on_hand`, `location`,
  `notes`. UNIQUE on `(workspace_id, material_id, len_mm, wid_mm)`, so
  adjusting stock is an UPDATE of `qty_on_hand`, not a second row. Indexes on
  `(workspace_id, material_id)` plus a partial one `WHERE qty_on_hand > 0`
  for the optimiser's hot path.
- **`/optimise` reads stock; it never writes it.** The pure-function invariant
  from #9 holds — no reserving, no decrementing. Consumption on cut-plan
  completion is a deliberate later decision, not an oversight.
- `OptimiseIn.sheet_len_mm` / `sheet_wid_mm` are now **optional**:
  - omitted → the server picks the **largest in-stock sheet** for
    `material_sku` (by area, tie-broken by quantity) and sets
    `sheet_dims_from_stock=true`;
  - omitted with no stock on hand → `422 {code: "NO_SHEET_SIZE"}`;
  - supplied → explicit dims win, so ad-hoc stock the catalog doesn't know
    about can still be nested against.
- `OptimiseSummary` gains `sheet_len_mm`, `sheet_wid_mm`,
  `sheet_dims_from_stock`, `sheets_available`, `sheet_shortfall`.
  **`sheets_available` is `null` when no stock is recorded at that size** —
  that means *unknown*, not zero, so the UI must not claim a shortfall
  against it.
- Routes (`apps/api/app/cut_floor/`, queries in `inventory_queries.py`),
  reads gated `("cut_floor","read")`, writes `("cut_floor","write")`:
  - `GET /board-inventory?material_sku=&in_stock_only=`
  - `POST /board-inventory` — **upsert** by (material, size); posting the same
    size again sets the quantity instead of duplicating. Omitted `location` /
    `notes` are preserved, not clobbered. `404 UNKNOWN_MATERIAL` for an
    unknown SKU.
  - `PATCH /board-inventory/{id}` (qty / location / notes),
    `DELETE /board-inventory/{id}`.
- Audit: `board_inventory.{upsert|update|delete}`.
- Web: a **Sheet Stock** tab on `/catalog` (`StockPanel`) lists stock by
  material + size with inline qty/location editing, remove, and a
  set-stock form (the same upsert, so re-entering a size updates it).
  `OptimiseDialog` defaults to **Use sheet size from stock** (the dim
  inputs grey out; kerf stays editable since it's a saw property, not a stock
  one), lists what's on hand under the SKU field, and shows a shortfall
  banner when a nest needs more sheets than exist. Saving is still allowed —
  a short nest is a purchasing signal, not an error.
- Seed (`make seed`): 6 stock rows across 5 boards on the demo workspace —
  BM-101 deliberately stocked in **two** sizes (2440×1220 and 3600×1800) to
  exercise the largest-sheet pick, and BM-104 at **zero** to exercise the
  out-of-stock path. Idempotent via the same upsert.

## Cutlist + related parts + Orderbook (sub-project #10)

> **Plan V1 #10** — selected by Q437, widened by Q542 to take the whole
> Orderbook with it. Plan + per-task verification notes:
> `docs/superpowers/plans/2026-09-18-cutlist-related-parts-orderbook.md`.
> Every binding rule traces to a numbered answer in
> `docs/plan-v1/OPEN-QUESTIONS.md`; Q552–Q573 were raised *while building*,
> each where a document and the code disagreed.

Seven migrations, `0026`–`0032`. The A-series (`0026`–`0029`) shipped as
schema-only ahead of any code; `0030`–`0032` were not reserved up front —
the Shop Floor re-key, the order schema and the Controlled Lock each needed one.

**No RBAC matrix change** (Q432). Still 7 roles × 11 modules. Cutlist routes
reuse `("list", action)` because Q474 settled that Cutlist *is* the `List`
tab; orders and suppliers reuse `("orderbook", action)`; areas/rooms reuse
`("tracking", action)`.

### Schema

- **`0026_area_room`** — `area` (project-scoped, Q457) + `room` **nested under
  area** (Q552). Composite FK `items (area_id, room_id) → room (area_id,
  room_id)` so an item's room can never drift out of its area. `level` and
  `zone` stay plain columns, not hierarchy levels (Q546).
- **`0027_cutlist`** — `cutlist (cutlist_id, project_id, cutlist_no UNIQUE,
  name, created_by)`, project-scoped rather than carrying `workspace_id`
  (the post-`0014` pattern `shop_drawing` / `sample` use). `items.cutlist_id`
  nullable and single-column, so an item may have none (Q440) and can never
  hold two (Q411). Introduces **`joinery_number_seq`**.
- **`0028_related_parts`** — `items.row_type` (`joinery_item` | `related_part`),
  `items.parent_item_id` self-FK, and a `related_part_type` lookup seeded with
  metal / benchtop / cushion (Q448) so IT can add a fourth without a migration.
  Nesting is **one level only** (Q449), enforced by a generated
  `parent_row_type` column feeding a composite FK — not by application code.
  CHECKs also forbid a related part holding a `cutlist_id` (Q417) and require
  a type key on exactly the related-part rows.
- **`0029_orderbook`** — revives the legacy `/procurement/*` schema as the
  order layer rather than building beside it (Q502). **There is no new `order`
  / `order_line` table and no new `supplier` table**: `purchase_orders` +
  `po_line_items` *are* the order layer (Q553) and `vendors` *is* the supplier
  entity (Q556). Adds `purchase_orders.project_id` (Q554 — workspace is
  derived by joining `projects`, not denormalised), `.item_id`, and `attributes
  jsonb` on both tables (Q503). Drops legacy `inventory` / `inventory_movements`
  / `v_inventory_status` — `board_inventory` (`0025`) wins (Q544). Adds
  `supplier_id` / `default_supplier_id` to all six catalog tables **beside**
  their free text, which Q435 requires keeping.
- **`0030_shop_floor_cutlist`** — re-keys `worker_assignment` and
  `stage_completion_log` to `(cutlist_id, stage_key)`. See the Shop Floor
  section above.
- **`0031_order_categories`** — makes the inherited office-procurement schema
  usable for joinery: `purchase_orders.cost_center_id` becomes nullable
  (Q563), the frozen `category` CHECK becomes an `order_category` lookup
  (Q557) seeded with the six legacy values plus eight joinery ones, and
  **`po_number_seq`** replaces the legacy `MAX(...) + 1` generator (Q564).
- **`0032_item_lock_request`** — the Controlled Lock. See the PM Workbench
  section above.

### Key invariants

- **One number space** (Q541). `joinery_number_seq` feeds Item IDs, cutlist
  numbers **and** related parts, so a six-digit number never means two things.
  Allocate it **inside** the INSERT; never `MAX(num) + 1` (that race is what
  B2a removed). Q540 gave every pre-existing item its own cutlist carrying its
  `num`, so historical numbers survive recognisably — which is also why
  `cutlist_no` carries **no width CHECK**.
- **`item_stages` stays per-item, as a projection** (Q439). Completing a stage
  on a cutlist fans the `done_date` out to every linked item whose own order
  contains that stage — *selectively*, not blanket (Q562), so a
  `painting_req = false` item never receives a PAINTED date from a sibling.
  Undo reverses the whole cutlist (Q446).
- **Late link leaves history blank** (Q539). An item linked to a cutlist that
  has already completed a stage gets **no** backfill; its cell stays empty and
  it catches up at the next completion. `fan_in_stage_undone` handles it for
  free — there is no row to clear.
- **A related part never carries a cutlist number** (Q417) — a DB CHECK, not a
  convention. It shares its **parent's** Group ID (Q416/Q453) and, in Tracking,
  shows its **issued order number** where a cutlist number would be.
- **An order's CUTLIST NO. is the parent's** (Q428), may be blank if the parent
  has none yet (Q429), and is filled in / rewritten automatically when the
  parent gains or changes a cutlist (Q430/Q431) — one function,
  `orders.queries.sync_orders_for_item`, called from the cutlist link/unlink
  paths. It lives in `orders/` because the orders own the column being written.
- **`row_type` filtering is centralised.** `apps/api/app/row_types.py` holds
  the single `joinery_items_only(alias)` definition. Of the 50 SQL call sites
  reading `items`, **35** carry it; the rest are item-scoped by id or
  deliberately want both kinds — B1's note in the plan classifies all 50.
  Add the helper, not a hand-written predicate. Grep finds far fewer than 35
  hits: 16 modules import it and most bind the result to a module constant
  (`_JOINERY_I = joinery_items_only("i")`) interpolated into several queries.
- **Item cost does not roll up** (Q543, deliberate). Orders carry cost;
  nothing aggregates it onto an item yet.

### Backend modules

All mounted at top-level paths from `main.py`.

- `apps/api/app/areas/` — 3 endpoints (`GET /projects/{pid}/areas`,
  `POST /projects/{pid}/areas`, `POST /areas/{aid}/rooms`), gated
  `("tracking", action)` with `require_drafter()` on the writes. Creating a
  duplicate returns 409 **carrying the existing id**, so a racing create just
  selects it.
- `apps/api/app/cutlists/` — 7 endpoints, gated `("list", action)`. Includes
  `POST /cutlists/{cid}/items` / `DELETE .../items/{iid}` for link + unlink.
  `GET /cutlists/{cid}` rolls parts and hardware up **flat across the
  cutlist's items**.
- `apps/api/app/related_parts/` — 7 endpoints. No migration of its own —
  `0028` carries every structural rule; this module turns what a CHECK cannot
  express into clean 409s instead of raw constraint violations.
- `apps/api/app/suppliers/` — 6 endpoints over `vendors`, gated
  `("orderbook", action)`, **workspace-scoped** (the four legacy
  `/procurement/vendors*` routes never were, and `0029`'s `workspace_id NOT
  NULL` had broken their POST — they are retired, Q565).
- `apps/api/app/orders/` — 9 endpoints, gated `("orderbook", action)`, at
  top-level paths and separate from the still-untouched legacy
  `/procurement/*` namespace. `POST /orders` prefills project / location /
  cutlist number from the item rather than asking for them (Q427).
  `GET /orders` is the **workspace-wide** list behind the Orderbook page and
  must stay declared *before* `/orders/{po_id}` so the literal path wins — the
  same ordering caveat `catalog/routes.py` carries. It also returns the Q554
  order that has no project at all (that one reaches its workspace through its
  vendor), which no project page can show.
- **Fixed later.** `add_line()` computed `SELECT COALESCE(MAX(line_number), 0)
  + 1` against `po_line_items` with no lock on the parent `purchase_orders`
  row, racing against `UNIQUE (po_id, line_number)` (`0002`) — and, unlike
  every other mutation in this module, the route had **no** `IntegrityError`
  handling at all, so two concurrent `POST /orders/{po_id}/lines` calls on
  the same order raised a raw 500. `_lock_order_for_update()` (same shape as
  estimating's `lock_revision_for_update()`) now locks the order row before
  the `MAX+1` read, so a concurrent `add_line()` on the same order serializes
  instead of racing. No migration. Pinned by
  `test_concurrent_add_line_serializes_instead_of_duplicating_line_number`
  (`test_orders_line_number_race.py`), confirmed to fail against the pre-fix
  code with a raw `UniqueViolation` on `po_line_items_po_id_line_number_key`.
  (A parallel-looking race was suspected in `shop_drawings.add_revision()`'s
  `rev_no` allocation, but turned out **not reachable**: every new revision
  is inserted `status='draft'`, so any two concurrent inserts on the same
  drawing always collide first on the partial unique index
  `uniq_drawing_inflight` — which the route already turns into a clean 409 —
  before the `rev_no` collision could ever surface. Verified by writing the
  same race test there and watching it hit `uniq_drawing_inflight`, not an
  unhandled 500; no code change was needed.)
- Item lock requests live in `apps/api/app/items/` — see PM Workbench above.

### Web

- **`/tracking`** — `ItemsTable` nests related parts under their parent,
  **collapsed by default** (Q420–Q422), with an **empty stage-strip area** for
  them (Q419 — scoped to the date columns only; their other columns still
  render). The leftmost column shows a cutlist number for an item and an
  issued order number for a related part (Q417), and a **seventh column-set
  `O/BOOK`** (Q570) shows Order # / Supplier / Status / ETA. **Create Order**
  opens the one generic form plus key/value `attributes` rows (Q426, Q503).
- **`/orderbook`** — two tabs since E2. **Orders** (default) reads
  `purchase_orders` and honours `?order=<po_number>` by selecting the row,
  scrolling it into view and opening its detail panel — the "locate the order"
  half of Q418. **Delivery queue** is #4's supplier-grouped procurement-batch
  queue, kept rather than replaced because Q504 leaves batches beneath orders
  as the allocation mechanism. Money and quantity arrive as **JSON strings**
  (Pydantic `Decimal`), not numbers — `lib/orders-types.ts` records that;
  typing them `number` compiles and then throws `toFixed is not a function`.
- **`/list`** — now the **Cutlist module workspace** (Q474), not a mirror of
  Tracking's item grid. `CutlistClient` lists a project's cutlists and opens
  one into Items / Parts / Hardware panes. Opens as a `target="_blank"` tab
  (Q545) and is deep-linkable (Q478).
- **Item editor** — `AreaRoomPicker` replaces the free-text Area/Room fields,
  with inline `+ New…` creation from the selector. A move is audited (Q458),
  and moving area clears a room that would be orphaned.
- **Project Details modal** — gains a `Project Stats` tab. Cars / OH&S and
  Scope are **omitted pending Q550 / Q572**, not stubbed.

### Known gaps

- **Fixed later.** The item editor's own hardware query (`hardware_lines/
  queries.py::list_catalog` + `list_source_catalog`) used to read the catalog
  `supplier` column alone, rendering "—" on every row since `0017` put the
  real value in `default_supplier`. Now `COALESCE`s both, same as the cutlist
  rollup already did (`vendor` for `custom_made`), pinned by
  `test_catalog_supplier_falls_back_to_default_supplier` and
  `test_source_catalog_supplier_falls_back_to_default_supplier`.
- Q508's Hard / Approval lock types and Q511 / Q512 have no home yet.
- **E3 is the one task of #10 left open** — migrating a copy of the customer's
  real pilot data (Q436) to confirm Q540's number preservation. It is blocked
  on data that has not been supplied, not on work.
- `apps/web/components/pm/TrackingGrid.tsx` is **dead code**: #9a replaced it
  with `ItemsTable` (`b910ab1`) and nothing renders it. Left in place per §3
  (mention unrelated dead code, do not delete it) — but do not read it as the
  Tracking grid, because it is not.

> **Fixed during E2, recorded because the shape recurs.** #9a's Tracking
> overhaul dropped the **availability chip** when `ItemsTable` replaced
> `TrackingGrid`, and with it the *only* entry point to the
> `AvailabilityDrawer` — `TrackingClient.setDrawerItemId` was left being called
> with `null` and nothing else, so a documented #4 feature was reachable only
> by hand-typing `?drawer=item-availability&itemId=N`. Nobody noticed because
> the e2e spec covering it had been failing on an unrelated login assertion
> since the same batch. **A failing or skipped spec is not coverage**; when one
> goes red for a trivial-looking reason, check what it stopped guarding.

### Seed

`make seed` gives **every** seeded Joinery Item an `area` + `room` and its own
cutlist numbered as itself — 8 areas and 13 rooms across the two demo projects
(6 and 9 of them on ALF-001). On ALF-001 it then adds cutlist **297830
"SS Bench run (shared)"** carrying two items with one `DOWN` completion fanned
out to both, plus a third item linked *afterwards* whose `DOWN` cell stays
blank (Q539); two related parts under ST-CT01, one with an issued order and one
without; supplier `Corian Stoneworks`; and one purchase order. Idempotent.

> **The recurring trap, recorded once.** Alembic backfills only touch rows that
> exist when the migration runs — and `make seed` inserts rows *afterwards*.
> This silently broke cutlists and left area/room empty. Every seed block that
> creates an item must now create its cutlist, area and room too. The
> per-item cutlist blocks also re-INSERT on every run (their idempotency guard
> is on `items`, not `cutlist`), so anything that *moves* an item between
> cutlists has to drop the vacated row unconditionally.

## Global Search (sub-project #11)

> Plan V1 §13, selected by Q520. Design: `docs/superpowers/specs/2026-09-24-search-design.md`;
> plan with per-task verification notes: `docs/superpowers/plans/2026-09-24-search.md`.
> Every rule traces to Q525 or Q574–Q580.

- **Infrastructure.** Two new compose services: `meili`
  (`getmeili/meilisearch:v1.54.0`, **no host port**, `MEILI_*` keys in `.env`)
  and `search-worker` (the api image running `python -m app.search.worker`,
  **no `--reload`** — restart it after editing `app/search/`). Meili's data
  is disposable: `make reindex` rebuilds it from Postgres.
- **Migration `0033_search_outbox` — the repo's first triggers** (Q578).
  `search_enqueue(kind, id_col)` sits on 15 tables (plus `estimate_revision`,
  which enqueues its estimate) and writes `(entity_type, entity_id)` to
  `search_outbox` in the writer's own transaction. `search_fanout()` sits on
  six parents whose values are embedded in child documents (project code,
  area / room / cutlist names, supplier and customer names) and fires only
  when one of those columns changes. **Any new write path is covered
  automatically; a new *searchable table* needs a trigger in a migration and a
  loader in `documents.py`** — `test_search_reindex.py` fails if the two
  disagree. `TRUNCATE` fires no row triggers, which is why the test suite
  truncates `search_outbox` itself (`conftest.TRUNCATE_TABLES`).
- **The outbox holds identity only.** The worker locks rows `FOR UPDATE SKIP
  LOCKED`, loads each row's *current* state, waits for Meili task success,
  then deletes exactly the ids it locked — so an outage loses nothing and a
  write mid-pass survives. A committed edit is searchable in ~3 s.
- **`app/search/`** — `index.py` (`SearchIndex` protocol, `MeiliIndex` over
  httpx, `FakeIndex` for tests; **`build_filter` is the only producer of
  filter strings** and always carries `workspace_id`), `documents.py` (the
  only module that knows the source schema; one loader per kind), `worker.py`,
  `reindex.py`, `routes.py`.
- **`GET /search?q=&types=&project_id=&include_archived=&limit=&offset=`** —
  `current_user` only; **no RBAC matrix change**. A type is visible when the
  caller's *effective* `read` grant covers its module (`routes.TYPE_MODULE`;
  the Dynamic RBAC engine since *Global Search RBAC sync* below — it was the
  static role matrix when this shipped); unreadable types are
  dropped silently, never 403'd. `503 SEARCH_UNAVAILABLE` on outage, with no
  Postgres fallback. **`GET /search/health`** is gated
  `("it_management","read")` — which the matrix gives **manager** as well as
  admin.
- **Binding search behaviour.** `codes` (item / cutlist / PO / estimate /
  SKU numbers) has **typo tolerance off**, and every query uses
  `matchingStrategy: "all"`: a number one keystroke off, or `EST-2026-0001`
  matching `EST-2026-0002` by dropping a word, would be a *different record*
  (`joinery_number_seq` is shared, Q541).
- **Coverage (Q576 + Q579):** 11 types. Area / room names are searchable
  through item documents, not as results; people are deferred; suppliers are
  indexed with **no link** (no supplier page exists). **Never indexed:**
  secrets, money columns, `vendors.bank_account` / `tax_id` /
  `payment_terms` / `rating`, customer `abn` — pinned by sentinel tests.
- **`archived` (Q580)** mirrors each record's own page: void items, and
  `archived_at` on drawings, samples, customers and catalog rows, plus rejected
  samples and rejected / expired / withdrawn estimates. Soft-deleted items are
  never indexed. Cancelled orders, inactive suppliers and closed projects stay
  visible.
- **Web.** `components/chrome/SearchBox.tsx` in `TopBar` (`/` focuses it),
  `/search?q=&type=&include_archived=` (not a tab), and a Search panel on
  `/it`. The browser still only ever talks to the Next proxy.
- **Fixed after the merge.** Four seeded catalog rows (one each in
  `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`) had
  **`workspace_id` NULL**, making them invisible on `/catalog` as well as in
  search. `seed/hartwood_joinery.py` now sets `workspace_id` on insert and
  backfills the four rows on any database seeded before the fix.

## Material Take → Material Summary (sub-project #12)

> Plan V1 §19–§20, step 3 of `ALIGNMENT.md` §6. Design:
> `docs/superpowers/specs/2026-09-24-material-take-design.md`; plan with
> per-task verification notes: `docs/superpowers/plans/2026-09-24-material-take.md`.
> Every rule traces to Q80, Q495–Q501 or Q581–Q586.

- **Migration `0034_material_take`** — `material_take` (per Joinery Item,
  versioned; partial unique indexes allow **one draft and one approved** per
  item), `material_take_line`, `material_take_review`, `material_summary`,
  `material_summary_line`, `material_summary_source`. Not searchable (no
  `0033` triggers). Source rows **cascade**: items can be hard-deleted, and a
  lost source makes its line read stale.
- **A take is generated, then owned by a person** (Q80). `material_takes/
  generation.py` reads parts + hardware lines and never writes (Q501).
  **Boards are fractional sheets per item** — part area ÷ sheet area, rounded
  *up* to 2 dp — and the summary rounds up **once** over the project (Q586:
  per-item whole sheets overcounted, 6 against 3 on the seed's MDF). Sheet
  size: largest in-stock `board_inventory` size → largest recorded size →
  catalog size → else the line is in **m²**. Hardware sums per material.
  Edging and finishing are **manual** `OTHER` lines (Q584 — no data to
  generate from). Related parts never get a take (Q424).
- **Fixed later.** `generate()` checked for an existing draft with a plain,
  unlocked `SELECT`, then computed `SELECT COALESCE(MAX(version), 0) + 1`,
  then inserted — no lock in between. Unlike `shop_drawings` (where the
  equivalent race is masked by a constraint the route already handles), this
  module's route (`material_takes/routes.py`'s `_call`) catches only the
  app-level `NotFound`/`Conflict` exceptions, not `IntegrityError`, so two
  concurrent `POST /items/{iid}/material-take/generate` calls on an item with
  no existing draft could both pass the check and race on `uniq_take_draft` /
  `UNIQUE(item_id, version)` (`0034`) — the loser got a raw 500 instead of the
  clean `409 DRAFT_EXISTS` the pre-check is meant to give. `generate()` now
  locks the `items` row (`FOR UPDATE`) before the draft-exists check, so a
  concurrent call on the same item serializes instead of racing. No
  migration. Pinned by `test_concurrent_generate_serializes_instead_of_raw_500`
  (`test_material_take_generate_race.py`), confirmed to fail against the
  pre-fix code with a raw `UniqueViolation` on
  `material_take_item_id_version_key`.
- **Draft → approved → superseded.** Only a draft changes; an approved take is
  immutable (`409 TAKE_NOT_DRAFT`) and a change means version `n + 1`. On a
  generated line, material / unit / description are read-only and changing
  `wastage_pct` re-derives `qty`. Every mutation writes `audit_log` **and**
  `item_edit_log` in one transaction.
- **Drift, not drawings (Q583).** A take reads **outdated** when its item's
  live parts / hardware would now *generate* differently — manual lines and a
  person's adjustments never count. The reviewer records No / Partial / Full
  impact; Partial / Full opens the next version. Shop drawings are **not
  linked to items**, so there is no drawing-triggered review and no warning at
  drawing approval (Q497's advisory warning waits for that link).
- **Summary** (`material_summaries/`) — consolidates each item's *current
  approved* take, one line per material (`OTHER` by exact description), keeps
  per-item sources with their take version, lists items with no approved take.
  Computed on read, never stored: **stale** (a source item has a newer
  approved version, or a source vanished), **nest sheets** from the latest
  CutPlan (Q582 — `cut_sheet.material_sku` resolves through the catalog SKU
  **or** `cv_material_mapping`, because the seed's nest is labelled by CV code
  `18-PB`), and read-only **on order / received** from the existing
  `procurement_v1` rollup. **Confirmation is advisory** (Q499) and freezes the
  summary (`409 SUMMARY_CONFIRMED`); rebuild to revise. No ordering from a
  line yet (Q585).
- **RBAC — no matrix change.** Everything is `("list", …)`. Take edits and
  summary build / edits also need `require_drafter()` (drafter / manager /
  admin — §20's PM / Coordinator / Designer); approve and confirm need `list`
  approve; purchase officers read. Workspace-isolated through
  `items → projects.workspace_id`; another workspace gets 404.
- **Web.** Item editor **Material Take** tab (`?tab=take`, `MaterialTakeTab`);
  Procurement page **Summary** tab (`/projects/[id]/procurement?tab=summary`,
  `MaterialSummaryPanel`). Quantities are **strings** in
  `lib/material-take-types.ts` (the `orders-types.ts` lesson).
  **JSX whitespace trap, hit twice here:** text that continues onto a second
  line after a `{…}` expression or an element lost its leading space in the
  build ("4 linesmay be outdated") — build such sentences as one template
  string or add an explicit `{" "}`.
- **Seed.** On ALF-001: approved takes on every item with parts except one
  (left as a draft, so it is listed as missing), one built summary, then one
  item at v2 — so the summary opens with stale lines. Built through the same
  query functions the API uses, so audit / edit-log rows are real. Idempotent.

## Tracking 2.0 (migration `0035`) — shipped

> Design: `docs/superpowers/specs/2026-05-27-tracking-2-0-design.md`; plan:
> `docs/superpowers/plans/2026-05-27-tracking-2-0.md`. Authored 2026-05-27 on
> a separate branch, merged into `main` 2026-09-24 (commit `8ac99d5`) —
> *after* #12, out of migration-number order relative to its own title.
> **Numbering collision, noted once here for both this and the next
> section:** both docs call themselves sub-projects "#10" and "(#11)"; those
> numbers were free when written in May but are now held by Cutlist +
> Orderbook and Global Search, which were built and merged first. Go by
> migration number or date, never by the label inside either doc.

- **Migration `0035`** adds `workspace_counter(workspace_id, name,
  next_value)` — an atomic per-workspace counter, `apps/api/app/counters/
  next_value()` — plus six `items` columns: `jid_code`, `jid_color` (hex,
  CHECKed), `var_boq` (`BOQ`/`VAR`, default `BOQ`), `contractor_id` (FK →
  `app_user`, workspace-validated on write), `total_amount`,
  `site_measure_notes`.
- **Closes the legacy-parity gap on `/tracking`.** The grid gained JID code +
  colour swatch, a VAR/BOQ pill, Contractor, Total $, and exposure of
  columns that already existed on `items` but weren't in the API response
  (`floor_plan`, `rls`, `joiery_details`, `painting_req`,
  `solid_surface_req`, `cutlist_printed`, `group_id`, `item_code`,
  `assembler`, `lister`). Stage cells switched from checkmark to
  `done_date` (`DD.MM.YY`).
- **Subtabs** (`ItemsTable.tsx`'s `SUB_TABS`): `DATE · TO BE ORDERED · iTIME
  · HARDWARE · SITE MEASURE · INVOICE · QC · O/BOOK`. DATE, TO BE ORDERED
  (a filter — `availability.blocked > 0`, not a separate table), HARDWARE,
  SITE MEASURE and O/BOOK render real data; `iTIME`, `INVOICE` and `QC`
  stay `—` placeholders pending a future invoicing/variations sub-project
  neither doc built.
- **Bulk status.** `POST /items/bulk-status` (`tracking:write`) applies one
  status + one required note to up to 500 items in a single transaction;
  missing or cross-workspace ids come back in the response instead of
  404ing the whole call. The single-item `PATCH /items/{id}/status` was
  tightened the same way — `note` is now required, not an optional
  empty-string fallback.
- **`workspace_counter` has no caller yet, deliberately.** Its own design
  doc says it's seeded here ahead of a future PO/invoice/JID-numbering
  consumer; nothing in this tree calls `next_value()` outside its own unit
  tests (`test_counter.py`). Not a gap — don't invent a caller for it.
- **RBAC — no matrix change.** New fields ride the existing
  `require_drafter()` + `tracking:write` combo in `items/routes.py`;
  `contractor_id` writes are rejected (422) if the user isn't in the
  caller's own workspace.
- **Seed.** `make seed` gives every ALF-001 item a `jid_code`/`jid_color`
  pair, marks one item `VAR`, assigns `contractor_id` on two items, sets
  `total_amount` on every item, a `site_measure_notes` on the SS-Bench
  item, and one `workspace_counter` row.
- Backend, frontend and seed all shipped; covered by
  `test_tracking_bulk_status.py` plus extensions to `test_items_routes.py`.
- **Fixed after the merge:** `ItemOut` declared the six new fields but
  `get_item_detail` never selected them, so `GET` and `PATCH /items/{id}`
  always answered `jid_code: null, var_boq: "BOQ"` (etc.) whatever the row
  held — the Tracking grid, which reads through `list_items_for_project`,
  was right all along. Pinned by
  `test_get_item_returns_tracking_2_0_fields`.

## Item & Project Detail 2.0 (migration `0036`) — shipped

> Design: `docs/superpowers/specs/2026-05-27-item-project-detail-2-0-design.md`;
> plan: `docs/superpowers/plans/2026-05-27-item-project-detail-2-0.md`. Same
> authoring-vs-merge-order caveat as Tracking 2.0 above.

- **Migration `0036`** adds `projects.closed_at`/`closed_by`;
  `project_contact` (`kind IN (office, site)`); `project_lift_access` (one
  row per project); `item_query` (Q&A per item); `item_document` (an open
  document register beyond the four named attachment slots); widens
  `item_attachment_kind_check` to add `sketchup`/`cabvision` (`cv_drawing`
  stays; the migration's comment calls it a "legacy synonym", but the code
  treats it as its own slot — see below); `project_labour_hours_view` (returns zero —
  a future labour-hours integration populates it).
- **Backend shipped:** `ProjectOut` now surfaces FileMaker-era `projects`
  columns that already existed but weren't exposed (`builder`,
  `classification`, `site_street/suburb/postcode/state`,
  `tg_project_manager`, `tg_coordinator`) plus the new `closed_at`/
  `closed_by`; `POST /projects/{id}/close-out` (admin/manager,
  `409 ALREADY_CLOSED`) — **the only way to close** (user, 2026-09-25):
  `PATCH {status: "Closed"}` is 422, so `closed_at` / `closed_by` are always
  stamped, and PATCHing `status` to `Current` / `Hold` **re-opens**, clearing
  both (the design doc's §9 rule, which the merged code had not implemented); `project_contacts/` (POST/GET/PATCH/DELETE,
  `tracking:{read,write}`); `project_lift_access/` (GET/PUT/DELETE, one row
  per project); `item_queries/` (ask on `list:read`, answer/edit-answer on
  `list:write`, second answer without `allow_overwrite` returns 409). **The
  last three routers were built in the same merge but not registered in
  `main.py`** — `apps/api/app/{item_queries,project_contacts,
  project_lift_access}/routes.py` existed with complete queries/schemas
  and zero mount, so all 11 endpoints were unreachable until a follow-up
  fix (`fix(api): mount item_queries, project_contacts,
  project_lift_access routers`). They are now live and were verified
  end-to-end against a migrated database.
- **Document Register backend** (`item_documents/`, built after the merge):
  `GET /items/{iid}/documents` (`list:read`), `POST /items/{iid}/documents`,
  `PATCH /documents/{did}` (label / sort_order; `label: null` clears it,
  `sort_order: null` is 422) and `DELETE /documents/{did}` (all
  `list:write`). Unbinding deletes the register row only — the `file_blob`
  stays, as everywhere else (no orphan GC). Audit
  `item.document.{bind,update,unbind}`. Three choices made while building,
  each where the design doc was silent or a sibling module disagreed:
  - **`list:write` alone gates writes, so editors can bind.** The design
    doc says `list:write`; `item_attachments` adds `require_drafter()` on
    top. The doc for *this* feature wins; the sibling `item_queries` (same
    doc) also uses `list:write` alone.
  - **Joinery Items only.** A related part gets 404, the same rule the
    named attachment slots follow. The design doc predates related parts.
    Widening later is additive; narrowing would orphan rows.
  - **Writes `item_edit_log` as well as `audit_log`**, per the PM Workbench
    invariant (`_document_bind` / `_document_unbind`, and
    `document.{id}.{field}` per changed field). **Fixed later:**
    `item_attachments` and `item_queries` used to write audit only; both now
    write `item_edit_log` too (`attachment.{kind}` on bind/clear;
    `_query_create` on ask, `query.{id}.answer` on answer/edit-answer),
    pinned by `test_bind_writes_item_edit_log` / `test_clear_writes_item_edit_log`
    and `test_ask_answer_edit_round_trip`'s edit-log assertion.

  A bound blob must be PDF, PNG or JPEG (415 otherwise); `POST /files`
  already only stores those three, so the check guards the register if the
  upload allowlist ever widens. Covered by `test_item_documents.py` (10
  tests).
- **Item reference fields are writable** (built after the merge):
  `PATCH /items/{id}` accepts `floor_plan`, `rls`, `joiery_details`
  (`varchar(64)` — longer is 422) and `cutlist_printed`, through the usual
  `_PATCH_FIELD_MAP` path, so they get one edit-log row per field and go
  through the Controlled Lock like every other field. `ItemOut` (the
  `GET` / `PATCH /items/{id}` payload) now returns them.
- **Attachment slots are five, purely additive** (built after the merge;
  **decided by the user**, 2026-09-25). The design doc called `cv_drawing` a
  "legacy synonym" without saying of what; the answer is that it is **not a
  synonym in the code**: `cv_drawing` ("CV Production Drawing") keeps its own
  slot and its existing rows, and `sketchup` / `cabvision` are two further,
  independent slots. `item_attachments/` now offers
  `cv_drawing · sketchup · cabvision · floor_plan · site_measure` and the
  bundle always carries all five.
  **Each slot takes one format** (user, 2026-09-25): `sketchup` a `.skp`,
  `cabvision` a `.cvj`, the other three a PDF — anything else is 415
  (`item_attachments.queries.KIND_MIME`).
  **Uploading them** (`files/validators.py`, also the user's call): the
  "signature *and* extension must agree" rule still holds. `.skp` is
  `FF FE FF 0E` (SketchUp 2021+) or the OLE compound-file signature (older
  SketchUp); `.cvj` is OLE. OLE is shared by both — and by `.doc`/`.xls`/`.msi`
  — so for OLE the extension picks between `.skp` and `.cvj` and any other
  name is refused. Stored mimes are `application/vnd.sketchup.skp` and
  `application/x-cabinet-vision-job`. **The 25 MB cap is unchanged for every
  type** — a larger SketchUp model gets 413; the user chose that over a
  per-type cap. The signatures come from published format notes, not from a
  customer file: verify against a real `.skp` / `.cvj` when one is available.
  Widening `/files` meant adding a mime check wherever a blob is bound
  without one: shop drawings (422) and the lift-access sketch (415) keep
  PDF / PNG / JPEG; samples (PNG / JPEG) and the Document Register
  (PDF / PNG / JPEG) already had their own.
  **The Combined PDF is unchanged** — still `cv_drawing`, `floor_plan`,
  `site_measure` only (also the user's call; pinned by
  `test_print_combined_ignores_sketchup_and_cabvision`). Do not "fix" this
  into a rename or an alias. The web `AttachmentsTab` still shows only the
  three Combined slots; `lib/print.ts` counts only those three so its
  "N of 3" label can't overflow when the new slots are bound via the API.
- **Frontend shipped** (plan tasks T08–T12, `docs/superpowers/plans/
  2026-05-27-item-project-detail-2-0.md`; each task's `→` note there records
  what was built and how it was verified):
  - `EditorTabs.tsx` now carries 8 tabs: `cutlist · hardware · board · take
    · attachments · actions · query · log`. New **Actions** tab (Set status
    — reuses the existing `StatusPopup`; Mark REQ done today; Jump to
    Orderbook) and **Query** tab (ask/answer, `list:write` — `{drafter,
    manager, admin, editor}`, one role wider than `AttachmentsTab`'s writer
    set since `item_queries` doesn't add `require_drafter()`).
  - **Cutlist Printed and the three reference fields (Floor Plan / RLS /
    Joinery Details) live in `ItemMetadataPanel`'s existing `FIELDS` array**,
    not a separate header-chip row or Refs panel — Painting Req / Solid
    Surface Req were already there with the identical pattern. A deliberate
    simplification versus the design sketch.
  - **`AttachmentsTab` widened to 5 slots** (`sketchup` / `cabvision` cards
    now render; `AttachmentSlotCard`'s file-picker `accept` is a per-kind
    map, not hardcoded `.pdf`), with a small "Combined PDF" badge on the 3
    slots Combined actually uses. `lib/attachments-types.ts` gained
    `COMBINED_PDF_KINDS` distinct from the now-5-wide `ATTACHMENT_KINDS`, so
    `print.ts`'s "N of 3" copy stays correct.
  - **New page `/projects/[id]`** — header strip (status pill, builder,
    classification, install/value, Close-out button) + 3-column layout
    (Details / Contacts / Lift & Access) + a Labour Hours card. **RBAC is
    split three ways, not one `canEdit`**: Details/close-out gate on the
    manual `manager`/`admin` check in `projects/routes.py` (not a
    `require_permission` row); Contacts/Lift-access gate on `tracking:write`
    (`{editor, drafter, manager, admin}`, one role wider). Status stays a
    **read-only pill** — no Current/Hold reopen control was added, even
    though the backend already supports it via a plain PATCH, because
    nothing in scope asked for that control on this page. `/projects` (the
    list page) gained a "Details →" link per row, and the Tracking modal
    gained "Open full project page →" in its footer.
  - `pm-types.ts` and `attachments-types.ts` had drifted from the Python
    schemas before this work started (fields the API had served since
    `0035`/`0036` were simply missing from the TS types) — resynced as a
    prerequisite.
- **Seed data shipped.** `seed/hartwood_joinery.py` sets ALF-001's `builder`
  / `classification` / site address / TG team via the real
  `patch_project()` query function (not raw SQL), and adds 4 contacts (2
  office + 2 site), lift access notes + a sketch, 2 `item_query` rows on the
  first joinery item (1 open, 1 answered), and 2 `item_document` rows —
  each through the same query functions the API uses, so seeded rows carry
  real `audit_log` / `item_edit_log` entries.
- **e2e coverage:** new `tests/e2e/item_project_detail.spec.ts` (3 tests) —
  the item editor's Query/Actions/Attachments tabs, the project page from
  both entry points, and close-out's RBAC gate. Deliberately checks that
  close-out is *invisible* to a drafter rather than actually performing a
  close-out — doing so would durably close ALF-001 for every other spec
  sharing one `make e2e` run.
- **RBAC — no matrix change**, per its design doc: `project_contact`/
  `project_lift_access` reuse `tracking:{read,write}`; `item_query` reuses
  `list:{read,write}`; close-out is admin/manager only.
- **Tests:** `test_project_enrichment.py` (enriched `ProjectOut`, close-out,
  re-open), `test_project_contacts.py`, `test_project_lift_access.py`,
  `test_item_queries.py`, `test_item_documents.py`, plus the attachment,
  upload and item-route files extended above, plus the new e2e spec.
- **Fixed later.** `PartsGrid.tsx` (Cutlist tab) left a stray whitespace text
  node as a `<tr>` child (a `<th /> {/* comment */}` pattern — the space
  before the comment was a real text child), which React logged as a
  hydration warning on every item editor load. Predated this sub-project
  entirely; fixed by dropping the space before each trailing comment.

## Dynamic RBAC engine (Plan V1 §3.4, Q466–473) — shipped

> Built directly against the confirmed decisions in `docs/plan-v1/OPEN-QUESTIONS.md`
> §F, the same way #9a shipped without a spec or plan — there is no
> `docs/superpowers/{specs,plans}/` doc for this one; this section is its only
> written record.

Replaces the static `apps/api/app/auth/permissions.py` matrix as the *live*
source of truth for `require_permission`, with the DB-backed, project-scoped
engine Q466 confirmed — while keeping day one bit-for-bit
behaviour-preserving (Q468, Q435) and touching none of the ~181 existing
`require_permission(module, action)` call sites.

- **Migration `0037`** adds three tables: `permission_group` (workspace_id,
  name, is_system — direct `workspace_id` column, Q555's pattern, since a
  group has no other join path), `group_module_grant` (group_id, module,
  action), `user_group_membership` (user_id, group_id, `project_id` nullable
  — NULL means workspace-wide). A unique index on
  `(user_id, group_id, COALESCE(project_id, 0))` prevents duplicate
  workspace-wide memberships, since plain UNIQUE treats NULLs as distinct.
  **Backfill, in the same migration:** every workspace that already existed
  gets 7 system groups named after the 7 auth roles, with grants copied
  **verbatim from `MATRIX`** (188 rows, machine-generated from the live dict
  when the migration was authored, not hand-transcribed); every existing
  `app_user` gets a workspace-wide membership in the group matching their
  `auth_role`. Verified on a real Postgres 16 instance: grant counts per role
  (44/41/27/33/18/15/10 = 188) and one membership per seeded user, exactly
  matching `MATRIX`.
- **`apps/api/app/auth/rbac_engine.py`** — `effective_actions(db, user,
  module, project_id=None)` is the resolver: union of `group_module_grant`
  rows across every membership where `project_id IS NULL OR project_id =
  :pid`, most-permissive-wins across a user's groups (Q469). **`MATRIX` is
  the fallback**, not dead code — a user with **zero** memberships (any test
  file's raw-SQL `INSERT INTO app_user`, or a workspace created after `0037`
  ran — there is no "create workspace" route in v1) is governed by it
  exactly as before; a user with at least one membership is fully
  DB-governed, and an empty result for them is a real "no", never a
  fallback trigger. `seed_system_groups(db, workspace_id)` is the live,
  idempotent equivalent of the migration's one-time backfill — for a
  workspace created later, or for tests — not wired to any trigger,
  deliberately (see *Known gaps* below). `swap_default_group_membership(...)`
  moves a user's workspace-wide membership when their `auth_role` changes.
- **`require_permission(module, action, project_param=None)`**
  (`apps/api/app/auth/rbac.py`) is unchanged in effect for every existing
  call site: omitting `project_param` (all ~181 of them) checks
  workspace-wide grants only, which is exactly what the `0037` backfill gives
  every pre-existing user — verified by running the **full existing test
  suite (881 passed, 10 meili-skipped) with zero regressions**. Passing
  `project_param="pid"` (the path-parameter name holding a project id) makes
  the check *also* honour memberships scoped to that one project — a real
  behaviour difference, safe to add anywhere a project id is directly in the
  path, since no membership is project-scoped until an admin deliberately
  creates one. Wired onto `apps/api/app/areas/routes.py`'s two
  `/projects/{pid}/...` routes as a working demonstration (not a general
  rewire — see *Known gaps*). `apps/api/app/project_contracts/routes.py`
  (added by §I, migration `0038`) is the second adopter — its three
  `/projects/{pid}/contract...` / `/projects/{pid}/actual-costs` routes pass
  `project_param="pid"` from the day they were written, not retrofitted.
- **`PATCH /users/{uid}`** (`apps/api/app/users/routes.py`) now calls
  `swap_default_group_membership` when `auth_role` is in the patch, so a
  role change doesn't leave the old role's DB grants in effect under the new
  engine.
- **Admin CRUD API** — `apps/api/app/permission_groups/` (schemas / queries
  / routes), mounted at `/permission-groups`, gated `it_management` (read:
  admin+manager per the existing matrix row; write: admin only — the "IT
  configures access without a deploy" surface Q466 asked for):
  - `GET /permission-groups` — every group + its grants.
  - `POST /permission-groups` — create a group; 409 on a duplicate name,
    carrying the existing `group_id` (the areas/rooms 409-with-id pattern).
  - `PUT /permission-groups/{gid}/grants` — replace-all; 422 on an unknown
    module/action.
  - `DELETE /permission-groups/{gid}` — 409 `SYSTEM_GROUP` on one of the 7
    seeded groups, 409 `GROUP_HAS_MEMBERS` while it still has memberships.
  - `GET/POST /permission-groups/{gid}/memberships`,
    `DELETE /permission-groups/memberships/{mid}` — 422 `UNKNOWN_USER` /
    `UNKNOWN_PROJECT` for a foreign id, 409 `MEMBERSHIP_EXISTS` (carrying the
    existing `membership_id`) on a duplicate.
  - `GET /permission-groups/users/{uid}/memberships` — one user's
    memberships across all groups.
  - Every mutation writes `audit_log` (`permission_group.{create,
    set_grants,delete}`, `permission_group.membership.{create,delete}`).
- **Web — Groups panel on `/it` (shipped later, follow-up pass).**
  `PermissionGroupsPanel.tsx` (`apps/web/app/(app)/it/_components/`), a new
  `libs/permission-groups-{types,fetch}.ts` pair, and one new line in
  `it/page.tsx`. Sidebar list of all groups (name, `system` badge, grant
  count) + a detail pane: a 12-module × 4-action grants grid with dirty-state
  tracking (Save button only enables when changed, and switching groups or
  creating a new one while dirty prompts a discard confirm — the same
  `window.confirm` shape `removeGroup` already used), and a Members table
  (add/remove, workspace-wide vs. project-scoped). System groups hide the
  Delete button; deleting a group that still has members surfaces the
  backend's `409 GROUP_HAS_MEMBERS` inline. Verified end-to-end in a real
  browser against a live migrated stack (group create/select/delete,
  grants save, membership add, the two 409 paths) — this is the first
  sub-project in this file verified that way rather than by `tsc`/`next
  build`/pytest alone, per this session's UI-testing requirement.
  **Fixed along the way — `GET /users` / `PATCH /users/{uid}` 500'd for
  every real seeded user.** `UserOut.email` (`apps/api/app/users/schemas.py`)
  was `EmailStr`, a *response*-validation type, and `email-validator>=2.2`
  rejects `.test` as an RFC 2606 reserved TLD — so both routes broke against
  any `*.hartwood.test` address the moment a real browser (not the test
  suite's `@example.com` fixtures) exercised them. This was silently
  breaking the already-shipped `WorkerRosterPanel` (#8) too, not just the
  new membership picker here. Fixed to plain `str`, matching
  `auth/schemas.py`'s existing stance that email format is enforced upstream
  and an output field just echoes what's stored. Pinned by
  `test_admin_lists_users_with_reserved_tld_email`.
- **What Q466–473 answered but this build deliberately does not do:**
  - **Q472** (move hand-written per-object rules — `require_drafter()`, the
    not-uploader approve rule, creator-or-manager, the 5-minute undo window
    — into the engine as rules) is **not built**. They stay exactly where
    they are, in route handlers. A generic rule language is real design work
    Q472's own text flags as a cost, not a schema addition.
  - **Q470**'s critical actions (Lock, Unlock, Override, Configure) stay
    deliberately **outside** `group_module_grant` — they are not matrix
    actions, so most-permissive-wins never applies to them, and nothing here
    tries to express them as grants.
  - **Q473** (build §29 comments so the `comment` action stops being a dead
    grant) was **not built here — since built, see *Comments, mentions and
    notifications***. Originally: **not built** — a new entity, 8 object types and @mentions is
    a separate feature, not part of the permission engine itself.
  - **CLOSED — see *Global Search RBAC sync* below.** (Originally: `apps/api/app/search/routes.py`'s
    type-visibility check — the function is `readable_types`, not the
    `visible_types()` this bullet first named — filtered on
    `has_permission(auth_role, ...)`, the static matrix, not this engine.
    Kept for history.) A user whose grants an admin customised
    via the new engine (e.g. revoked `list:read` from their group, or gave
    them a project-scoped-only grant) will not see that reflected in which
    search result *types* are visible to them. Search's own workspace/project
    filtering on the results themselves is unaffected.
  - The **181 existing endpoints were not rewired** to pass `project_param`.
    They are unaffected (workspace-wide checks, unchanged), but a project id
    already in most of their paths is not yet exploited — that is additive
    work for whichever surface needs it next, not a gap in the engine.
- **Tests:** `test_rbac_engine.py` (resolver: fallback, DB-override,
  `seed_system_groups` parity with `MATRIX`, project scoping,
  most-permissive-wins, the `patch_user` auth_role-change swap end-to-end,
  and the `project_param` HTTP-level proof) and
  `test_permission_groups_routes.py` (admin CRUD, access control, delete
  guards, membership validation) — 26 tests, all passing against a real
  migrated Postgres 16 instance; the pre-existing `test_rbac.py` /
  `test_rbac_drafter.py` / `test_permissions.py` / `test_shop_drawings_rbac.py`
  / `test_users_routes.py` / `test_area_room_routes.py` pass unchanged.
- **Known gaps, recorded rather than silently left:**
  - No automatic group provisioning for a workspace created through the API —
    there is no "create workspace" route in v1 today. **`make seed` is a
    real instance of this**, though: it creates the `hartwood-joinery`
    workspace *after* `0037`'s one-time backfill already ran, so without a
    fix the seeded workspace would ship with zero `permission_group`/
    `group_module_grant`/`user_group_membership` rows and `GET
    /permission-groups` would show nothing on a fresh `make up && make
    migrate && make seed`. Fixed: `seed/hartwood_joinery.py` now calls
    `seed_system_groups()` right after creating the workspace and gives
    every seeded user a workspace-wide membership matching their
    `auth_role`, mirroring `0037`'s backfill exactly. `seed_system_groups()`
    is still ready to be called from a future "create workspace" route when
    one exists — this fix doesn't add one.
  - No web UI for the admin API — **closed, see above.**
  - Q472, Q470's rule layer, Q473's comments, and the broader project-scoped
    rewire of existing endpoints are open follow-ups, not oversights.


## Tender Lifecycle + Financials (Plan V1 §5–§6/§16–§17, Q487–494/548–549) — shipped

> Selected by the user as the largest coherent block of decided-but-unbuilt
> Plan V1 questions after §F (Dynamic RBAC engine). Built directly against
> the confirmed decisions in `docs/plan-v1/OPEN-QUESTIONS.md` — no separate
> spec or plan doc, the same way #9a and the RBAC engine shipped. This
> section is its only written record. **Replaces**, not extends, the
> six-state workflow described in the *Estimating (sub-project #9a)* section
> above — see the superseded-callout there before reading its "Revision
> workflow" / "Convert-to-Project" bullets.

- **Migration `0038`** — widens `estimate_revision.status` from 6 values to
  the **12-stage tender lifecycle** of Plan V1 §5: 11 sequential stages
  (`OPPORTUNITY, INITIAL_REVIEW, GO_NO_GO, INFO_REQUESTED, DOCS_RECEIVED,
  ESTIMATING, SUPPLIER_PRICING, INTERNAL_REVIEW, QUOTE_PREPARED,
  MGMT_APPROVAL, SUBMITTED`) plus one terminal position resolving to
  `WON` / `LOST` / `WITHDRAWN` (Q488). Existing rows are remapped
  (Q435 data-preserving): `draft → QUOTE_PREPARED`, `sent → SUBMITTED`,
  `accepted → WON`, `rejected → LOST`, `expired → LOST` (Q548 — Plan V1's
  12 stages have no Expired terminal; mapping onto Lost keeps the reason
  distinguishable in the audit event name even though the status collapses),
  `withdrawn → WITHDRAWN`. A `draft` row lands at **QUOTE_PREPARED**, not
  stage 1 — an in-flight quote already did the opportunity/review/pricing
  work the new early stages describe, and restarting it would make it walk
  stages that, in substance, already happened.
- **`locked_at` generalises "draft".** The old partial unique index
  `uniq_estimate_draft` (`WHERE status = 'draft'`) becomes
  `uniq_estimate_unlocked` (`WHERE locked_at IS NULL`) — the same "at most
  one revision per estimate not yet sent to the client" invariant, now
  correct across all 10 pre-Submitted stages instead of naming just one of
  them. `locked_at` is set exactly once, at `MGMT_APPROVAL → SUBMITTED`, and
  never cleared. Every former `status == "draft"` gate in `queries.py`
  (line create/patch/delete, part/hardware/labour mutation, patch of the
  revision itself) is now a `locked_at IS NULL` check — `_assert_draft` was
  renamed `_assert_unlocked`. **Migration data-integrity note**: a row
  inserted directly by raw SQL with a locked status but no `locked_at` set
  would collide with the new index against a genuinely-unlocked sibling —
  the migration backfills
  `locked_at = COALESCE(locked_at, sent_at, accepted_at, rejected_at, created_at)`
  for every row in a locked status before creating the index, so this can't
  happen even against pre-existing data with hand-inserted rows.
- **`project_contract` (one row per project, immutable `original_value`) +
  `project_contract_variation`** (append-only). `current_value` is
  **computed on read** as `original_value + SUM(variation.amount_delta)`,
  never stored — the same "nowhere to drift" stance `material_summary`
  (#12) already takes (Q491).
- **`_LEGAL_TRANSITIONS`** (`apps/api/app/estimating/queries.py`) — each of
  the 10 sequential stages permits its successor or `WITHDRAWN`;
  `SUBMITTED` permits `WON` / `LOST` / `WITHDRAWN`; the three terminals
  permit nothing. `next_tender_stage()` reads the fixed
  `TENDER_STAGE_ORDER` tuple. Any illegal transition → `409
  {code:"BAD_TRANSITION", from, to}`, unchanged from #9a.
- **One generic `advance()` action covers all 10 forward steps**,
  including `MGMT_APPROVAL → SUBMITTED` — that step's lock-and-snapshot
  business logic (the labour-rate snapshot, `locked_at`, `sent_at`) lives
  in `transition_revision()`'s `target == "SUBMITTED"` branch and fires
  here too, so there is no separate `/send` entry point any more.
  `POST /revisions/{rid}/advance` replaces `/revisions/{rid}/send`
  (**404, retired** — not aliased).
- **`reject` vs `expire` still write distinct audit events** despite both
  landing on the same `LOST` status (Q548 collapses the status, not the
  audit trail) — `transition_revision()` takes an explicit `lost_kind`
  param (`"rejected"` default, `"expired"` from the `/expire` route) rather
  than inferring intent from `lost_reason`'s text.
- **`revise()` restarts a new draft at `ESTIMATING`, not `OPPORTUNITY`**
  (design decision — Plan V1 does not say where a revision restarts): the
  opportunity/review/go-no-go/info-gathering work already happened for this
  tender and doesn't need repeating just because the price is being redone.
- **Handover review screen (Q490).** `GET /revisions/{rid}/handover-preview`
  returns the lines that would become Joinery Items plus the contract value
  Convert would default to (the quote's own GST-inclusive total). The PM
  reviews before converting rather than Convert running unconditionally —
  warranted because Q489 has handover generating a project's entire Joinery
  Item list, not just the project shell.
- **Convert-to-Project, extended.** `POST /revisions/{rid}/convert` still
  requires status `WON` (`409 BAD_STATUS`), still rejects already-converted
  (`409 ALREADY_CONVERTED`, carrying the existing `project_id`) and
  archived-customer, and still re-resolves every part/hardware snapshot
  against the live catalog before writing anything (`409 CATALOG_GONE`
  listing every failure). New: an optional `include_line_ids` body field —
  omitted converts every line (old behaviour unchanged by default), an
  excluded line simply produces no Joinery Item while the rest of the quote
  is unaffected — and an optional `contract_value` override (defaults to
  the quote's own total). The `project_contract` row is created in the same
  transaction as the project, `items`, `modules`, `parts` and
  `project_hardware_catalog` rows Convert already wrote in #9a.
- **Documentation error found and corrected while building this.**
  `docs/plan-v1/OPEN-QUESTIONS.md`'s Q489 claimed "Estimate lines currently
  do **not** become items on convert" — false from the day it was written:
  `convert_to_project()` has created real Joinery Items since #9a's
  original commit (`a7b8d3d`), before Q489 was ever asked. There was no
  line-to-item mapping gap to build; what this sub-project actually added
  on top of the existing mapping is the *selective* handover (`include_line_ids`)
  Q490 asked for. Corrected in place in `OPEN-QUESTIONS.md` rather than
  silently rewritten — see the note under Q489 there.
- **Actual costs rollup (Q493/Q549), `apps/api/app/project_contracts/
  actual_costs.py`.** Pure read, nothing stored — the same "derive, don't
  capture twice" stance #9's `/optimise` already takes. Two sources:
  - **Materials** — `procurement_batches.qty_received * cost_per_unit`,
    summed per project. Project-level only (Q492 caps granularity at
    Project + Item, and there is no per-item allocation path for
    BOARD/CUSTOM/BENCHTOP batches today, the same gap #12's Material
    Summary already lives with for the same reason).
  - **Labour** — each `stage_completion_log` row's duration
    (`completed_at - worker_assignment.started_at`) priced at
    `workspace_labour_rate`. A completion belongs to a **cutlist**
    (migration `0030`), shared by every item on it, so its cost is
    **apportioned across the cutlist's items by each item's share of total
    part area** (`len_mm * wid_mm * qty`, summed per item) — falling back
    to an equal split when no item on the cutlist has any measurable part
    area yet. A completion with no `assignment_id` (nullable — pre-`0030`
    provenance rows) is excluded, not zero-costed: there is no `started_at`
    to derive a duration from.
  - `GET /projects/{pid}/actual-costs` returns `materials_actual`,
    `labour_actual`, `total_actual` and a `labour_by_item` breakdown map.
- **Backend module `apps/api/app/project_contracts/`** (`schemas.py`,
  `queries.py`, `actual_costs.py`, `routes.py`), mounted at top-level paths.
  3 endpoints, all gated `("tracking", action, project_param="pid")` — the
  **second adopter** of the Dynamic RBAC engine's project-scoped check
  (`apps/api/app/areas/routes.py` was the first, written before this
  sub-project as a demonstration only):
  - `GET /projects/{pid}/contract` — 404 if the project has none yet
    (predates Q491 or wasn't created from a converted estimate — not an
    error).
  - `POST /projects/{pid}/contract/variations` — creating the row *is* the
    decision (§6: "the PM decides whether a change becomes a Variation");
    there is no separate approval step here — whoever can write already
    decided.
  - `GET /projects/{pid}/actual-costs` — always 200 (zeros when nothing to
    roll up yet), 404 only for a foreign/missing project.
- **RBAC — no matrix change.** Contract/actual-costs routes reuse
  `tracking:{read,write}`, same as `project_contacts` / `project_lift_access`
  (Item & Project Detail 2.0) — Contract Value lives on the project page
  alongside them.
- **Web.**
  - `apps/web/lib/estimating-types.ts` — `TENDER_STAGE_ORDER`,
    `TENDER_STAGE_LABELS`, the widened 14-value `EstimateStatus` union,
    `HandoverPreview*`, `ConvertResult` (now carries `contract_value`).
  - `apps/web/lib/project-contract-types.ts` + `-fetch.ts` (new) —
    `ProjectContract`, `ContractVariation`, `ActualCosts`,
    `projectContractApi.addVariation()`.
  - `EstimateDetailClient.tsx` — the single "Send" button became
    `advance()` + a dynamic label (`nextStageLabel()` reads
    `TENDER_STAGE_LABELS[TENDER_STAGE_ORDER[i+1]]`; shows "Submit to
    client" rather than "Advance → Submitted" on the last hop, and disables
    when advancing to Submitted with zero lines). `ConvertPreviewDialog`
    now renders one checkbox per line (backed by a `Set<number>` selection
    state) sourced from the handover-preview endpoint, instead of a single
    confirm button.
  - New `ProjectFinancialsCard.tsx` on `/projects/[id]` — Contract Value
    (original + current) + an inline "+ Add variation" form, plus the
    read-only Materials / Labour / Total actual-costs strip. Renders "No
    contract on this project yet" rather than hiding itself when the
    project predates Q491.
  - `CustomerDetailClient.tsx` and `EstimatingClient.tsx`'s
    `STATUS_COLOURS` maps widened to all 14 statuses (found via `tsc
    --noEmit`, not the initial grep — `CustomerDetailClient` lives outside
    `estimating/` and was missed on the first pass).
- **Seed.** `make seed` now lands the three demo estimates on
  `QUOTE_PREPARED` / `SUBMITTED` / `WON` (was `draft` / `sent` / `accepted`)
  and adds one `project_contract` row on ALF-001 (`$185,000.00`) with one
  variation (`+$4,250.00`, "Client-requested benchtop upgrade") — through
  the same query functions the API uses, so the seeded row carries a real
  `audit_log` entry. Idempotent (`DELETE FROM project_contract WHERE
  project_id = :p` before insert).
- **Tests:** `test_estimating_lifecycle.py` (new — full 12-stage transition
  graph, including `/send`'s 404 retirement), `test_estimating_handover.py`
  (new — preview + selective convert), `test_project_contracts_routes.py`
  (new — contract CRUD + RBAC), `test_actual_costs.py` (new — labour
  apportionment, a 2:1 item-area split verified against a $200 completion
  → $133.33 / $66.67), plus `test_estimating_routes.py` /
  `test_estimating_workspace_isolation.py` / `test_home_dashboard.py`
  updated in place for the new status literals and transition actions.
  Full suite (915 passed, 10 skipped, 1 failed) run against a real migrated
  Postgres 16 instance with zero regressions outside the files above. The
  one failure, `test_search_reindex.py::test_real_reindex_swaps_and_drops_temp`,
  is a pre-existing local-environment gap unrelated to this work: unlike its
  sibling `meili`-marked tests it reads `os.environ["MEILI_URL"]` directly
  instead of skipping when unset, so it only runs (and fails) when no
  Meilisearch instance is reachable — `make test`'s docker-compose
  environment always sets `MEILI_URL`, so CI never sees this.
- **`tests/e2e/estimating.spec.ts` updated** for the new seed statuses
  (`QUOTE_PREPARED` / `SUBMITTED` / `WON` in place of
  `draft` / `sent` / `accepted`); the Convert button and quote-PDF link
  gates it exercises (`WON` / `SUBMITTED` respectively) were unchanged by
  this rewrite.
- **Out of scope (deferred):** ~~PO/supplier-order generation from a won
  quote~~ **built, see *PO Generation from a Won Quote* below**, Q472-style
  per-object rule migration into the RBAC engine for this module's
  hand-written gates (unaffected — none were added here), a rollback path
  for `_LEGAL_TRANSITIONS` (Q513 already ruled this out generally), and
  moving `Cars/OH&S`/`Scope` tab content onto the new financials card
  (blocked on Q550/Q572, unrelated customer inputs).

## QC / Rework / Packing (Plan V1 §26–§28, Q515–519) — shipped

> Selected by the user over §L (Locking/Concurrency) after §I shipped —
> chosen as the "bolt on a new subsystem" option, additive to existing
> surfaces rather than a rewrite of save semantics on the busiest ones.
> Built directly against `docs/plan-v1/OPEN-QUESTIONS.md` §M — no separate
> spec or plan doc, the same way #9a, the RBAC engine and §I shipped. This
> section is its only written record.

- **Migration `0039`** — three new tables (`qc_defect`, `qc_checklist_item`,
  `rework`), a `PACKING` row in the `stages` lookup (`sort_order 85`,
  between `MADE=80` and `DEL=90`), widened `worker_assignment` /
  `stage_completion_log` CHECKs to admit `'PACKING'`, and a backfill of
  `group_module_grant` for the new `qc` RBAC module across every existing
  workspace's 7 system groups (see *RBAC* below — this is **not** the same
  thing as adding `qc` to the static `MATRIX`, and both were required).
- **QC is a module, not a workflow stage** (Q515) — Plan V1 §22 lists QC
  among the stages, but §26 describes it as checking *the work just
  completed* at whatever stage that was, a cross-cutting activity rather
  than a milestone. `items.stage_key` / `lifecycle_stage` is untouched by
  QC; only Packing (below) is a real 11th stage.
- **`qc_defect`** — one row per finding, optionally tagged with the
  `stage_key` whose work is being checked. Two states only: `open` →
  `resolved`. Raising/editing a defect is `qc:write`; resolving it is
  `qc:approve` — a defect a Foreman raises isn't self-closed, matching the
  shop_drawings not-uploader-approves pattern. A resolved defect is
  immutable (`409` on edit or on resolving twice).
- **`qc_checklist_item`** — a per-item QC checklist line (`label`,
  `is_checked`, `checked_by`/`checked_at`, `sort_order`). Plan V1 §2 lists
  "QC checklist" among what a duplicated Joinery Item copies and "QC
  results"/"Defects" among what it must *not* copy — item duplication
  itself is not built anywhere in this tree yet, so there is nothing to
  wire that distinction into today; noted for whoever builds it.
- **`rework`** — **one entity with a `kind` CHECK** (`internal`/`full`),
  not two entity types (Q516): "they differ in when they occur and how much
  work they involve, but what must be recorded — cause, scope, cost and
  responsibility — is the same" (`plan_v1.md` line 1926-1929), and those
  four fields plus `kind` are exactly the columns. **Rework never reopens a
  completed stage** (Q517) — it is a parallel record; the original
  `stage_completion_log` rows stay intact. This also sidesteps a real
  problem the shared cutlist would otherwise create: production stages
  belong to the cutlist and are shared by every linked item, so reopening
  one for a single item would have reopened it for all of them.
  Closing rework is `qc:approve`, same shape as resolving a defect.
- **The QC-timing rule (Q518) is guidance, not enforced.** §26 describes
  what happens depending on how far the work has progressed (before
  Listing QC doesn't need to know; after Listing but before Assembly the
  Lister updates the cutlist; after Assembly it's Internal Rework; after
  Installation it's Full Rework) — none of this is checked in code. The
  `kind` a defect becomes is the QC operator's call.
- **Packing (Q519) — a real 11th lifecycle stage, with scanning.** Unlike
  QC, Packing genuinely is a stage: "the first addition to the workflow
  stage list since Q459 kept the existing ten" (`plan_v1.md` line 2130).
  It is the 6th Shop Floor stage — `SHOP_FLOOR_ORDER_DEFAULT` /
  `_PAINT_LAST` (`apps/api/app/shop_floor/lifecycle.py`) both now end in
  `PACKING` unconditionally, after `MADE`/`PAINTED` regardless of their
  relative order, since Packing always comes after all
  fabrication/finishing. Assignable, start/complete, undo — all exactly
  like `DOWN`/`CNC`/`EDGED`/`PAINTED`/`MADE`. `DEL`/`INST` remain outside
  Shop Floor (Q561, unchanged).
- **Scanning without the native app.** Q519 confirms Packing as "a tracked
  stage, with scanning," and ties that to Q532's dedicated native site
  application — which does not exist anywhere in this repo (`apps/api` +
  `apps/web` is the whole stack). Rather than wait on that separate
  project, scanning is built **in the browser**: `getUserMedia` + `jsQR`
  decode QR frames from the camera, no native app and no new backend
  service. A manual-entry fallback (type the number) covers cameraless
  browsers, denied permission, and desktop testing.
  - **`GET /items/{id}/label`** (new page, deliberately **outside** the
    `(app)` route group so it renders bare, not wrapped in TopBar/SideBar
    chrome — proxy.ts's `PUBLIC` allowlist is path-based, not
    route-group-based, so the page still redirects to `/login` without a
    session) renders a QR code (the `qrcode` npm package, client-side
    canvas) encoding the item's own `num` — the one value `joinery_number_seq`
    already guarantees unique, not a new identifier scheme. "Print Label"
    sits next to the three existing print links in `EditorFooter.tsx`.
  - **The scan target is the whole cutlist, not a single item.** Shop
    Floor's unit is the cutlist (migration `0030`); one "Mark Packing
    done" action completes it for every linked item, and there is no
    per-item completion state to scan against. Scanning **any one** item's
    label on the cutlist is enough — `StationCard.item_numbers` (new field,
    `worker_queue()`'s `array_agg` of the cutlist's item `num`s) is what the
    scanner checks the decoded value against.
  - `PackingScanner.tsx` (`shop-floor/station/[worker_id]/_components/`) —
    only wired into the kiosk's `MarkDoneDialog` when
    `card.stage_key === "PACKING"`; every other stage keeps the plain
    confirm button unchanged.
- **RBAC — new `qc` module, the 12th** (between `estimating` and
  `it_management` in `_ALL_MODULES`). Mirrors `shop_floor`'s
  drafter-is-downstream shape, not the elevated-drafter pattern most other
  modules use — QC is production-floor territory:
  - admin/manager: `{read,write,approve,comment}`
  - editor: `{read,write,comment}` — can raise a defect/checklist
    item/rework, cannot resolve or close one
  - drafter: `{read,comment}` — same shape as `shop_floor`'s drafter row
  - estimator/purchase_officer/viewer: `{read}`

  **This needed two separate changes, not one.** Adding `"qc"` to
  `_ALL_MODULES` and to the static `MATRIX` dict makes it available to
  `seed_system_groups()` for any workspace created (or re-seeded) *after*
  this migration — but every already-existing workspace's system groups
  were populated once, by `0037`'s own hardcoded backfill, and the Dynamic
  RBAC engine (§F) resolves a user with real memberships from
  `group_module_grant` alone, never falling back to `MATRIX` for them. So
  migration `0039` also inserts the 16 `(role, 'qc', action)` rows directly
  into `group_module_grant` for every workspace's existing 7 system groups
  — the same shape 0037's own backfill used, scoped to just the new
  module. Skipping this would have left `qc` invisible to every real user
  in every workspace that existed before `0039`, while still passing any
  test that creates a fresh zero-membership user (which falls back to
  `MATRIX` and would look right for the wrong reason).
- **Backend module `apps/api/app/qc/`** (`schemas.py`, `queries.py`,
  `routes.py`), mounted at top-level paths. **12 endpoints**, all
  Joinery-Items-only (`joinery_items_only()`, the `item_documents`
  precedent — a related part gets 404) and workspace-isolated through
  `items → projects.workspace_id`:
  - `GET/POST /items/{iid}/qc/defects`, `PATCH /qc/defects/{did}`,
    `POST /qc/defects/{did}/resolve`
  - `GET/POST /items/{iid}/qc/checklist`, `PATCH /qc/checklist/{cid}`,
    `DELETE /qc/checklist/{cid}`
  - `GET/POST /items/{iid}/qc/rework`, `PATCH /qc/rework/{rid}`,
    `POST /qc/rework/{rid}/close`
  - Every mutation writes `audit_log` **and** `item_edit_log` in the same
    transaction, per the PM Workbench invariant. Audit events:
    `qc.defect.{create,update,resolve}`,
    `qc.checklist.{add,check,uncheck,update,remove}`,
    `qc.rework.{create,update,close}`.
- **Web.** New **QC** tab in the item editor (`EditorTabs.tsx`, between
  Query and Log) — `QcTab.tsx` renders all three sections (Defects,
  Checklist, Rework) on one screen, matching the density of
  `AttachmentsTab`/`QueryTab` rather than three separate tabs. Shop Floor's
  office board (`ShopFloorClient.tsx`) and its types (`shop-floor-types.ts`)
  gained the 6th `PACKING` column; the kiosk (`StationClient.tsx`) gained
  the scan-gated `MarkDoneDialog` path described above.
- **Seed.** `make seed` on ALF-001's first joinery item: 1 open + 1
  resolved defect, a 3-item QC checklist (2 checked), 1 open Internal
  Rework — built through the real `app.qc.queries` functions, so seeded
  rows carry genuine `audit_log`/`item_edit_log` entries, same as #11/#12's
  seed blocks. A second item gets one `assigned` `PACKING` `worker_assignment`
  (raw SQL, matching the pre-existing #8 shop_floor seed block's own idiom)
  so the board's 6th column isn't empty out of the box. Idempotent —
  each table's target-item rows are dropped before re-inserting.
- **Tests:** `test_qc_routes.py` (new, 15 tests — defect/checklist/rework
  round-trips, `qc:write` vs `qc:approve` split via editor-cannot-resolve/
  close, resolved/closed immutability, Joinery-Items-only 404s,
  cross-workspace isolation, audit+edit-log writes), two new PACKING tests
  in `test_shop_floor_routes.py` (assignable + completes after `MADE`;
  before `MADE` is `409 STAGE_OUT_OF_ORDER`), `test_shop_floor_lifecycle.py`
  updated in place for the new 6-stage ordering (existing "last stage has
  no later stages" tests were pinned to `MADE`, now correctly `PACKING`),
  and `test_permission_groups_routes.py`'s admin-grant-count assertion
  updated `44 → 48` (12 modules × 4 actions, was 11 × 4) — the one test in
  the whole suite that hardcoded a MATRIX-derived total and needed
  updating for a module addition. Full suite (932 passed, 10 skipped, 1
  pre-existing unrelated failure — the same local-only `MEILI_URL` gap
  noted in *Tender Lifecycle + Financials* above) run against a real
  migrated Postgres 16 instance with zero regressions outside the files
  named here.
- **Out of scope (deferred):** ~~the standalone cross-project **QC
  Dashboard** Plan V1 §4.2 names~~ **built, see *QC Dashboard* below**
  (this section shipped the per-item surfaces that back it); QC checklist templates or
  per-project configuration (today's checklist is ad-hoc per item, added
  free-text, matching Simplicity First over building a template system
  nothing asked for); linking a `rework` row to the `qc_defect` that caused
  it (Plan V1 doesn't ask for the link, and rework can originate without a
  formal defect record, e.g. found on site); §L's remaining Hard/Approval
  lock types and field-level optimistic concurrency (the alternative this
  round didn't pick — **since built, see *Locking + Concurrency* below**);
  native mobile app work under Q532 (Packing's scanning need is met without
  it, per above).

## Locking + Concurrency (Plan V1 §11–§12, Q508/Q511/Q512) — shipped

> Selected as the next sub-project after §M — it is the option §M's own
> "out of scope" note named as "the alternative this round didn't pick".
> Built directly against `docs/plan-v1/OPEN-QUESTIONS.md` §L's five
> confirmed answers, the same way #9a, the RBAC engine, §I and §M shipped:
> no separate spec or plan doc. This section is its only written record.

Closes out **Q566**'s list of what B7 (the Controlled Lock, migration
`0032`) left unbuilt: Q508's Hard and Approval lock types, and Q511/Q512's
field-level optimistic concurrency. Q509 (soft-lock → Controlled Lock) and
Q510 (item + project granularity, read as a ceiling) were already done —
see *PM Workbench* above.

- **Migration `0040`** — `items.hard_locked_at` / `hard_locked_by` (Hard
  Lock, Q508) and a `field_versions jsonb` column on each of `items`,
  `cutlist` and `purchase_orders` (Q511/Q512's three named surfaces).
  Approval Lock (also Q508) gets **no column**: "information automatically
  locks when approved" binds directly to the existing Status taxonomy's
  `APPROVED` value on `items.status` — there is nothing to store that isn't
  already there. **Q510 remains a ceiling, not a mandate**: no project-level
  lock column is added, for the same reason `0032`'s docstring already gave
  for the Controlled Lock — `projects` has no lock column of any kind, so a
  project lock would be new functionality with no owner or UI, not a
  conversion of something that exists.
- **Hard Lock (Q508 type 1) — item-scoped, `PATCH /items/{id}` only.**
  Unlike the Controlled Lock, there is no request-and-approve path around
  it: `POST /items/{id}/hard-lock` (manager/admin only, a manual
  `auth_role` check matching `claim_or_release_lock`'s transfer-permission
  pattern, not a new RBAC action) blocks the item for **everyone, including
  the current owner**, until the same authority clears it with `DELETE` on
  the same path. Scope matches the Controlled Lock's own documented
  boundary: `/status` and `/lifecycle/{stage_key}` did not consult either
  lock when this shipped (**the Hard Lock now stops them too — see *Lock checks on
  status and lifecycle***). Audited as `item.hard_lock` / `item.hard_unlock`.
- **Approval Lock (Q508 type 3) — derived, not stored.** Setting
  `items.status` to `APPROVED` (via `PATCH /items/{id}/status` or
  `POST /items/bulk-status`) locks `PATCH /items/{id}` with
  `409 APPROVAL_LOCKED`; moving status away from `APPROVED` unlocks it.
  Both directions are audited (`item.approval_lock` / `item.approval_unlock`)
  from inside `patch_item_status()`/`bulk_patch_item_status()`, even though
  there is no lock column for the event to name — Q516 requires every
  lock/unlock to be audited regardless of mechanism.
- **Field-level optimistic concurrency (Q511/Q512).** `apps/api/app/
  concurrency.py` holds the one shared implementation —
  `check_field_conflicts()` / `bump_field_versions()` — used identically by
  `items/queries.py::patch_item()`, `cutlists/queries.py::patch_cutlist()`
  and `orders/queries.py::patch_order()`. A PATCH may carry
  `expected_versions: {field: version}`, read from a prior GET's own
  `field_versions`; a named field whose stored version has moved on is a
  **409 FIELD_CONFLICT** naming just that field (with its `current_value`),
  not the whole record — Q366's "lock only the fields genuinely in
  conflict," now actually buildable. **Omitting `expected_versions` (every
  pre-existing caller, and any field not being changed) keeps
  last-write-wins for that field** — this is additive, verified by running
  every existing test in `test_lock_semantics.py`, `test_order_routes.py`
  and the cutlist suite unchanged and green.
  - **Checked only on the direct-apply path for items.** When the item is
    Controlled-Locked by someone else, nothing is written by that PATCH — it
    becomes a pending request instead (see *PM Workbench* above) — so there
    is no concurrent-write race for versioning to catch; the Controlled Lock
    already serialises that case through its own approve/reject flow. A
    version bump also happens when a held request is later approved, so a
    GET taken after approval reflects the field's new version correctly —
    and that approval path re-checks Hard Lock / Approval Lock too (see
    *Fixed later* below), since the requester's proposal predates either.
  - **`cutlist` has one patchable field** (`name`), so its conflict surface
    is trivial by construction — Q442 already made `cutlist_no` and
    `created_by` immutable.
  - **`purchase_orders`** reuses the module's existing `_PATCHABLE` set;
    every field in it is versioned, not a hand-picked subset.
- **Fixed later (max-level code review, same day).** The first pass's
  read-then-write field-version check had no row lock on any of the three
  surfaces: `patch_item`/`patch_cutlist`/`patch_order` all read the current
  row with a plain `SELECT`, so two concurrent PATCHes on the same field
  could both pass `check_field_conflicts()` against the same stale read and
  the second's write would silently clobber the first's — exactly the
  "nothing is silently overwritten" guarantee this feature exists to
  provide, undone by its own race. `_item_row` / `_cutlist_row` / `get_order`
  now take `for_update: bool = False`; the three `patch_*` functions pass
  `for_update=True` for their initial read (every other, read-only caller is
  unaffected), the same `SELECT ... FOR UPDATE` shape `_lock_order_for_update`
  / `lock_revision_for_update` already use elsewhere in this codebase.
  Pinned by `test_concurrent_patch_serializes_field_version_check_instead_of_lost_update`
  (two real DB sessions on separate threads), confirmed to fail against the
  pre-fix code. Three smaller findings from the same review: `decide_lock_request`'s
  approval path called `_apply_item_changes()` without ever checking Hard
  Lock or Approval Lock, so a request approved after either was set would
  slip through — both are now checked there too (`test_approving_a_lock_request_is_blocked_by_hard_lock`
  / `..._by_approval_lock`); `patch_cutlist`'s conflict branch hardcoded
  `conflicts["name"]`, raising an unhandled `KeyError`/500 if
  `expected_versions` ever named a different key — now generic like the
  items/orders versions (`test_cutlist_conflict_on_unrelated_expected_version_key_does_not_500`);
  and `ItemMetadataPanel.tsx`'s Area/Room save sent `expected_versions` for
  **both** `area_id` and `room_id` even though `AreaRoomPicker.onChange`
  only ever changes one of them, so a concurrent edit to the *other* field
  could wrongly reject an unrelated save — it now versions only the key
  actually present in the payload.
- **Web.** `ItemMetadataPanel.tsx`'s existing per-field PATCH calls now send
  `expected_versions` for the field being saved (and, for the Area/Room
  picker, for whichever of `area_id`/`room_id` that specific change actually
  touches — never both) and surface
  `FIELD_CONFLICT`/`HARD_LOCKED`/`APPROVAL_LOCKED` inline next to the field,
  alongside the existing `LOCK_REQUEST_CREATED` message — this is the same
  per-field error-banner mechanism, not a new one. `CutlistClient.tsx`'s
  rename prompt does the same for `name`. New `HardLockBanner.tsx`
  (manager/admin see a toggle; everyone else sees the banner while locked)
  and `ApprovalLockBanner.tsx` (informational only — unlocking is a status
  change on the Actions tab, not a button) sit above the metadata panel on
  `/items/[id]`. **`purchase_orders` has no PATCH-editing UI at all yet** —
  `orders-types.ts` carries `PatchOrderIn`/`field_versions` for whenever
  that surface is built, but nothing in this pass invents one.
- **Deliberately not seeded.** Every other sub-project's seed block leaves a
  demo row behind, but Hard Lock and Approval Lock each block **every**
  PATCH on the item they sit on — Hard Lock unconditionally, Approval Lock
  until status moves off `APPROVED` — and this repo's fixed e2e suite
  (`tests/e2e/`) PATCHes seeded ALF-001 items across several specs. Locking
  one of them in `make seed` risks breaking a spec this pass has no way to
  run and verify (Playwright needs a live browser + full stack). The
  feature is fully covered by `test_lock_types_concurrency.py` instead;
  don't add a seeded Hard/Approval lock without first confirming no e2e
  spec touches that item.
- **RBAC — no matrix change.** Hard Lock's manager/admin check is a manual
  `auth_role` check in `items/queries.py`, the same shape
  `claim_or_release_lock`'s transfer permission and `decide_lock_request`'s
  decider permission already use — not a new RBAC action, matching Q508's
  own silence on what should gate it.
- **Tests:** `test_lock_types_concurrency.py` (17 tests) — Hard Lock
  set/clear/block-everyone-including-owner/manager-only, Approval Lock
  auto-lock/unlock on status change, field-conflict 409s on all three
  surfaces with `current_value` in the response, correct-version saves
  succeeding and bumping again, a same-record-different-field save proving
  Q366's per-field (not per-record) conflict scope, plus the four review-fix
  regressions named above. Full suite (950 passed, 10 skipped, 1
  pre-existing unrelated failure — the same local-only `MEILI_URL` gap noted
  in *Tender Lifecycle + Financials* above) run against a real migrated
  Postgres 16 instance with zero regressions outside
  `test_lock_types_concurrency.py` itself.
- **Out of scope (deferred):** Q472's rule-engine migration of hand-written
  per-object rules (`require_drafter()`, the not-uploader approve rule,
  creator-or-manager, the 5-minute undo window) into the Dynamic RBAC
  engine — unaffected by this pass, still open from *Dynamic RBAC engine*
  above; extending Hard/Approval Lock or field-level concurrency to any
  surface beyond the three Q508/Q511 named (Q510 is a ceiling, not an
  invitation to widen); a PATCH-editing UI for orders (above); resolving a
  `FIELD_CONFLICT` by merging the two versions client-side (today's UI just
  tells the user to reload — a merge view is real design work Q366 doesn't
  ask for either).


## PO Generation from a Won Quote (Plan V1 §21, Q505) — shipped

> Selected by the user as the next sub-project after §L, closing the gap
> named twice as deferred — in *Estimating* and *Tender Lifecycle +
> Financials* — since Convert-to-Project shipped: Convert stops at project
> + contract creation, and every material the quote priced still had to be
> re-entered by hand into the Orderbook. Built directly against Plan V1
> §21's "Create PO" (Q505) and the existing orders/catalog schema — no
> separate spec or plan doc, the same way #9a, the RBAC engine, §I, §M and
> §L shipped. This section is its only written record.

- **Sources from the revision's own line breakdown**
  (`estimate_line_part` / `estimate_line_hardware`), not the converted
  project's items and not the Material Summary. Two reasons, both found
  during design, not assumed:
  - The converted project's `parts` table only retains a real material FK
    for **BOARD** (`board_material_id`) — CUSTOM/BENCHTOP catalog links
    survive there only as a `[material: {type}#{id}]` comment string
    (#9a's own schema constraint note). Reading the revision directly
    keeps every `material_id` real for all five order-eligible types.
  - The Material Summary (#12) was considered and rejected: **Q585**
    already confirmed "no create-order-from-line in v1" for that surface,
    deferring it to §21's full required/ordered/received/outstanding
    design. Building it there now would have contradicted a settled
    answer, not filled a gap.
- **Live catalog pricing, not the quote's frozen snapshot.** Each material
  is re-resolved against its catalog row at generation time (sku,
  description, cost, `default_supplier_id`) rather than reusing
  `cost_per_unit_snapshot` — Plan V1 §21 requires stale project-specific
  pricing to be caught before PO creation, and generation typically
  happens well after the quote was priced (Convert already requires
  `WON`, and there is no deadline after that). `_resolve_order_source()`
  (`apps/api/app/estimating/queries.py`) is a sibling of the existing
  `_resolve_part_snapshot` / `_resolve_hardware_snapshot` used when a line
  is first priced — same tables, but reading current values and the real
  `default_supplier_id` FK (migration `0029`) instead of the free-text
  `default_supplier` those two read.
- **Grouped by live default supplier, one PO per supplier.** Every
  distinct `(material_type, material_id)` referenced anywhere in the
  selected lines is **consolidated into one PO line with a summed
  quantity** — the same SKU quoted on five lines becomes one line for the
  total, not five, because a real procurement PO groups by SKU. Cut
  dimensions (`len_mm`/`wid_mm`) are deliberately dropped: they're cutting
  information for Production, not purchasing information for a PO. A
  material with no `default_supplier_id` can't become a PO line
  automatically (`purchase_orders.vendor_id` is `NOT NULL`) and is
  returned as `unassigned` instead — surfaced for the PM to order by hand
  via the existing per-item Create Order flow, never blocking the
  suppliers that DO have one. A PO's `category` is the material_type most
  represented in its lines (`"BOARD".capitalize() == "Board"`, matching
  `order_category`'s joinery keys from migration `0031` exactly — most
  suppliers specialise, so this is usually unambiguous, not an arbitrary
  pick on a tie).
- **Reuses the orders module end-to-end** (`orders.queries.create_order` /
  `add_line`) rather than inventing a parallel order entity — the same
  "`purchase_orders` + `po_line_items` ARE the order layer" stance
  Q502/Q553 already established for #10. Each generated PO carries
  `attributes: {"generated_from_revision_id": <rid>}` for traceability (no
  new column) and lands at the module's own default `status = 'Draft'` —
  Procurement reviews and edits from there like any other order.
- **Migration `0041`** — one column, `estimate_revision.orders_generated_at
  timestamptz NULL`. Guards `generate_orders()` to run **at most once per
  revision**: the revision is already locked by the time it's WON, so its
  line breakdown is frozen and there is no legitimate reason to
  regenerate from it. Set once, never cleared — the same "quote is
  frozen" stance `locked_at` already takes.
- **Backend** — `apps/api/app/estimating/{queries,schemas,routes}.py`
  (no new module; PO generation is estimating's own concern, keyed by
  revision like Convert and the handover preview):
  - `GET /revisions/{rid}/order-preview` — the review screen before
    generating, same shape Convert's own `handover_preview` established
    for Q490: every group + the unassigned list, computed fresh, nothing
    written.
  - `POST /revisions/{rid}/generate-orders` — `include_line_ids` (default:
    every line, same shape as `ConvertIn`). Requires the revision already
    **converted** (`409 NOT_CONVERTED` otherwise — a PO needs a real
    project to attach to) and rejects a second call
    (`409 ORDERS_ALREADY_GENERATED`). `409 UNKNOWN_LINE_IDS` on a foreign
    line id, mirroring Convert.
  - Both gated `estimating:approve`, the same gate Convert and the
    handover preview use (admin/manager/estimator).
  - Audit: `estimate.generate_orders` on the revision, plus the orders
    module's own `order.create` / `order.line_add` per PO/line it creates
    (reused, not duplicated).
- **Fixed later, found live-testing this feature.** `convert_to_project()`
  hardcoded every `parts` row's `seq` to `1` instead of incrementing per
  part in the module — harmless while no seed or test fixture had more
  than one part on a single quote line, but `uq_parts_module_seq
  (module_id, seq)` (migration `0007`-era constraint) rejects a second
  part with the same seq, so **any WON quote line with two or more
  parts — of any material type, not just duplicates — raised a raw
  `IntegrityError`/500 instead of converting.** This had shipped
  undetected since #9a's original commit; the seed data and every
  existing test fixture happen to give each line at most one part. Found
  because verifying PO generation live needed a line quoting two
  different board materials to exercise both the "assigned" and
  "unassigned" grouping paths in one request. Fixed by enumerating
  `part_seq` per module instead of a literal `1`. Pinned by
  `test_convert_line_with_two_parts_does_not_collide_on_seq`
  (`test_estimating_routes.py`), confirmed to fail
  (`UniqueViolation` on `uq_parts_module_seq`) against the pre-fix code.
- **Web.** `EstimateDetailClient.tsx` gains a "Generate orders" button
  (visible once `converted_project_id` is set and `orders_generated_at`
  isn't) opening `OrderPreviewDialog` — styled like the existing
  `ConvertPreviewDialog`: one card per supplier group with its lines and
  live unit cost, an amber unassigned-materials card, and a confirm button
  that calls `generate-orders` with no line filter (the API supports
  `include_line_ids`; the v1 UI doesn't expose per-line selection for
  this action — Simplicity First, and every converted line is normally
  meant to be ordered). After generating, a result banner names the
  order/line counts and any unassigned materials, links to the Orderbook,
  and the button is replaced by a permanent "Orders generated {time}"
  note on reload — read from the same `orders_generated_at` the backend
  guards on, not local component state.
- **RBAC — no matrix change.** Reuses `estimating:approve`, already
  granted to admin/manager/estimator.
- **Tests:** `test_estimating_generate_orders.py` (new, 13 tests) —
  supplier grouping, quantity consolidation across lines, the unassigned
  path, both 409s (`NOT_CONVERTED`, `ORDERS_ALREADY_GENERATED`),
  `include_line_ids` filtering, `UNKNOWN_LINE_IDS`, workspace isolation,
  the `estimating:approve` RBAC gate (via a second same-workspace user —
  no role has `estimating:write` without also having `approve`, so
  testing the gate needs a lesser-privileged user looking at a quote
  someone else built), and the audit row + `orders_generated_at` write.
  Plus the `convert_to_project` regression test above. Full suite (965
  passed, 10 skipped, 1 pre-existing unrelated failure — the same
  local-only `MEILI_URL` gap noted in *Tender Lifecycle + Financials*
  above) run against a real migrated Postgres 16 instance with zero
  regressions outside the files named here.
- **Deliberately not seeded.** None of the seed's three demo estimates
  are converted — the WON one is left that way on purpose (§I's seed
  note: "ready for a human to click Convert"), and auto-converting it in
  `make seed` would silently remove the Convert button
  `tests/e2e/estimating.spec.ts` exercises against it. Verified instead
  by live-testing the full flow (create quote → WON → Convert → Generate
  orders → Orderbook) against a real browser and a real migrated
  Postgres, per this session's UI-testing requirement — the same
  live-testing pass that surfaced the `convert_to_project` seq bug above.
- **Out of scope (deferred):** per-line selection in the Generate Orders
  dialog (the API already supports `include_line_ids`; nothing in this
  pass builds the UI for it); §21's much larger Procurement target
  (supplier comparison, PO → Confirmation → Receipt → Inspection flow,
  procurement exceptions, supplier performance tracking, claims/credits,
  deposits/progress payments) — this ships only "Create PO" (Q505)'s real
  purchase order, not the surrounding workflow Plan V1 describes around
  it; regenerating orders after a partial run (there is no legitimate way
  to add more once `orders_generated_at` is set — the revision is
  frozen); rolling generated-order cost back onto the item or project
  (Q543's "item cost does not roll up" stance is unaffected — orders
  carry cost, nothing aggregates it further here either).

## Orderbook — Purchase Order editing UI — shipped

> Selected as the next sub-project after PO Generation from a Won Quote —
> the gap that surfaced live-testing it: a generated PO's consolidated
> lines (summed quantities, live-catalog cost at generation time) had no
> way to be corrected before sending to a supplier, and the Orders tab
> itself was entirely read-only. Built directly against the existing
> `orders/` module and §L's field-version machinery — no separate spec or
> plan doc, the same way most sub-projects after #9a have shipped. This
> section is its only written record.

- **The order header PATCH already existed** (built for §L) — this
  sub-project closes the two gaps around it: no way to edit or remove an
  individual `po_line_items` row once added (only `POST .../lines`
  existed), and no web UI at all for either the header PATCH or the line
  endpoints.
- **`PATCH /orders/{po_id}/lines/{line_id}`** and
  **`DELETE /orders/{po_id}/lines/{line_id}`** (`apps/api/app/orders/
  {schemas,queries,routes}.py`), both gated `orderbook:write`, both
  workspace-isolated through the same `_ORDER_WORKSPACE` join every other
  route in the module uses. `patch_line()` / `remove_line()` reuse
  `_lock_order_for_update()` — the same row lock `add_line()` already took
  to serialize against `UNIQUE (po_id, line_number)` — so a concurrent
  edit and a concurrent add on the same order can't race either.
  `PatchOrderLineIn` covers `item_description` / `sku` / `quantity` /
  `unit` / `unit_price`; `line_number` and the provenance columns
  (`material_table`, `material_id` — which catalog row a generated line
  came from, if any) are not patchable. Both routes return the full
  `OrderDetailOut` (order + refreshed `lines`), matching `add_line`'s
  existing return shape.
- **No `expected_versions` on lines, deliberately.** §L's field-level
  optimistic concurrency (Q511/Q512) is scoped to exactly three named
  surfaces — items, cutlist, and the order **header** — and lines were
  never one of them; widening it to per-line versioning here would be
  scope creep the user never asked for, the same "Q510 is a ceiling, not
  an invitation to widen" reasoning this file already states for a
  different boundary. Line edits stay last-write-wins, like every
  pre-existing field on every surface §L didn't name.
- **`DELETE /orders/{po_id}/lines/{line_id}` returns `200 OrderDetailOut`,
  not the `204` its sibling `DELETE /orders/{po_id}` (whole-order
  soft-cancel) uses** — a deliberate, noted departure: the web UI needs
  the refreshed `lines` array immediately after removing one, and a line
  delete is a hard delete (no soft-cancel state to represent), unlike the
  order-level endpoint it otherwise resembles.
- **Web — `/orderbook`'s Orders tab is no longer read-only.**
  `orderbook/page.tsx` now fetches `me` (it never had before — the one
  page-level file under `(app)/` missing it) and threads it through
  `OrderbookTabs.tsx` to `OrdersClient.tsx`, which computes
  `canEdit = can(me, "orderbook", "write")`. Selecting a row now fetches
  the full `GET /orders/{po_id}` detail (with `lines` and `field_versions`)
  instead of reusing the already-fetched list row, which never carried
  either. The detail panel:
  - Editable header fields (status / priority selects; order number /
    supplier ref / notes / internal comments as blur-to-save inputs;
    required/ordered/ETA dates) follow the same `patchField` +
    `expected_versions` pattern `ItemMetadataPanel.tsx` established for
    §L — a `FIELD_CONFLICT` names the one field and its `current_value`
    rather than failing the whole save.
  - An editable lines table (inline blur-to-save per cell, a Remove button
    per row) plus an Add-line mini-form, wired to the three line
    endpoints. All editing controls are hidden — not just disabled — for
    a caller without `orderbook:write`, matching the rest of this app's
    read-only-role convention.
  - Q418's existing `?order=<po_number>` deep link is unaffected: it still
    selects and scrolls to the row; the panel that opens under it is what
    changed.
- **RBAC — no matrix change.** Reuses `orderbook:{read,write}`, already
  granted per the existing matrix (drafter has full read+write+approve+
  comment on `orderbook` since Procurement Workbench's elevated-drafter
  pattern; purchase_officer has read+write+approve; editor/viewer/
  estimator read-only).
- **`purchase_orders.total_amount` is now kept in sync with its lines.**
  The column predates `po_line_items` and was never wired to it — every PO
  `generate_orders` (§21/Q505) creates gets its lines via `add_line()` but
  `total_amount` stays at its 0.00 default forever, so the Orderbook and
  this new detail panel showed "Total: $0.00" under a stack of real-dollar
  lines. `add_line()` / `patch_line()` / `remove_line()` now all call a
  shared `_recompute_total_amount()` (`SUM(line_total)` over the PO's
  lines) after their write, and it bumps `field_versions["total_amount"]`
  too (a plain UPDATE bypassing that would let a stale header PATCH
  silently clobber the freshly-summed total with no `FIELD_CONFLICT` — see
  *Fixed later* below) — a no-op when the sum hasn't actually changed, so
  it never bumps the version for nothing. Deliberately narrow: `quantity` /
  `unit_cost` (singular fields with no coherent value across multiple
  lines) are left untouched, and a header-only order that never gets a
  line (the original per-item Create Order flow) is unaffected, since
  nothing there calls these three functions. **Known gap — CLOSED, see
  *Purchase order status guard* below**: when this shipped, neither the
  line routes nor the pre-existing header PATCH blocked editing a
  `Cancelled`/`Delivered` order — there was no order-status guard anywhere
  in this module.
- **Tests:** 16 new cases in `test_order_routes.py` — line PATCH updates
  editable fields and recomputes `line_total`, 404 for an unknown line
  (both with a real patch body and with an empty/non-patchable one — see
  *Fixed later* below) and for a line on a different order, line DELETE
  removes it and 404s the same way, both routes 403 for a `viewer`-role
  same-workspace user, a cross-workspace PATCH 404s, a parametrized case
  rejecting an explicit `null` for each of the three `NOT NULL` fields, two
  cases pinning the `total_amount` rollup (single line, and summed across
  two), one proving its version bump is real bookkeeping, one proving a
  direct header PATCH to `total_amount` is a no-op once lines exist (but
  still works on a header-only order), one proving a `FIELD_CONFLICT`'s
  `current_value` for a Decimal field stays a string, and one proving a
  stale `total_amount` version in a batch PATCH's `expected_versions`
  doesn't block an unrelated field in the same call. Full suite green
  against a real migrated Postgres 16 instance (existing 14 + new 17 in
  the module; zero regressions elsewhere).
- **Fixed later (six rounds of max-level code review, same day).**
  `patch_line()`'s empty-fields early return (a PATCH with `{}` or a
  non-patchable key like `line_number`) skipped the line-existence check
  the UPDATE's rowcount otherwise performs, so it 200'd with the order
  instead of 404ing for a line that doesn't exist on this PO — now checks
  existence explicitly before returning, pinned by
  `test_patch_line_404_for_unknown_line_with_no_patchable_fields`.
  `LineRow`'s local input state never resynced to the server's canonical
  value after a successful save (`quantity: "5"` round-trips as `"5.000"`,
  a `numeric(10,3)` column) — the next blur's dirty check
  (`quantity !== line.quantity`) kept firing an unnecessary PATCH and a
  fresh `order.line_update` audit row on every blur of that cell for the
  rest of the panel's life, even with no further edit; each of the five
  editable fields now has a `useEffect` resyncing local state to the
  matching `line.*` prop. The same missing-resync shape existed on the
  three header-field helpers (`EditableField`, `EditableDateField`,
  `BlurTextArea`) with a sharper consequence: after any *other* field's
  save refreshed `order` (and its `field_versions`), a stale local value
  left in an untouched field would be resubmitted with the now-current
  `expected_versions`, passing the conflict check and **silently
  overwriting a concurrent edit with no 409** — defeating §L/Q511-Q512's
  whole guarantee. All three now resync via `useEffect` on their value
  prop, and (a second finding on the same components) now skip the save
  entirely when the value is unchanged from props, matching `LineRow`'s
  existing dirty-check and stopping a bare tab-through from firing a
  no-op PATCH that bumps `field_versions` and hands the next real editor a
  false `FIELD_CONFLICT`. `fieldErrorMessage`'s `NOT_FOUND` branch checked
  `body.detail.code === "NOT_FOUND"`, but `patch_order_route`'s 404 is a
  plain string detail (`"order not found"`, matching every other 404 in
  this module) — the branch was unreachable dead code; it now checks
  `res.status === 404` instead. `EditableDateField` saved on every
  `onChange` rather than `onBlur` (the pattern every other editable field
  in this file, and `ItemMetadataPanel.tsx`'s own fields, follow) — a
  native `<input type="date">` fires `onChange` with `""` after each
  keystroke while typing a date directly, so the first keystroke into
  Required-by/Ordered/ETA immediately PATCHed the field to `null`, wiping
  an existing date before the user finished typing a new one; now saves on
  blur like its siblings. `PatchOrderLineIn` typed `item_description` /
  `quantity` / `unit_price` nullable (to allow *omitting* them) with
  nothing rejecting an explicit `null` for these `NOT NULL` columns, so
  `{"quantity": null}` passed validation and hit the UPDATE as a raw
  `IntegrityError`/500; a `model_validator` now rejects an explicit null
  for the three with a clean 422, pinned by the parametrized test above.
  The `total_amount` rollup above was also raised in this pass, as a
  pre-existing gap (predating this sub-project, in `add_line()`) that this
  sub-project's own new line-mutation surface made worse by giving PMs new
  ways (edit, remove) to drift the header further from the lines under it.
  A fourth pass, after the rollup landed, found two more: the rollup's own
  plain `UPDATE` bypassed `bump_field_versions()`, so a stale header PATCH
  read before a line changed the total could pass its `FIELD_CONFLICT`
  check and silently clobber the freshly-summed value — writing that fix
  exposed a **second, older, latent bug it was the first to actually
  trigger**: `patch_order_route`'s 409 handler puts `current_value`
  straight into `HTTPException`'s `detail`, which Starlette serializes
  with plain `json.dumps` (bypassing the response_model's Pydantic
  encoding) — a `Decimal` (`quantity`/`unit_cost`/`total_amount`) or a
  `date` (`required_date`/`date_ordered`/`due_date`) in that dict 500s
  instead of returning the 409. This has been reachable since §L shipped
  `patch_order`'s field-conflict path — no existing test exercised a
  conflict on any of those six fields, only string ones — and is fixed
  here, scoped to the `orders` module alone, by wrapping the detail in
  `jsonable_encoder()`; the identical shape likely exists in `items`'s and
  `cutlist`'s own conflict paths too (neither touched by this diff), left
  as a known gap rather than fixed opportunistically outside this module
  (**since fixed — see *FIELD_CONFLICT serialisation on items and cutlists***).
  Pinned by `test_recomputed_total_amount_bumps_its_field_version` (the
  version bump) and `test_field_conflict_current_value_serializes_decimal_as_string`
  (the encoder fix, added in the next pass below — this test alone would
  have failed differently, with a raw 500, before it). Separately,
  `removeLine()`'s error path showed
  "Remove failed" for a 404 on a line already removed (a double-click
  before the confirm dialog, or a second user's earlier removal) even
  though the goal — the line being gone — was already achieved; it now
  treats that 404 as success and skips the request entirely when the line
  is already absent from the last-known order.

  A fifth pass found the version-bump fix above had only patched the
  *symptom*, not the actual defect it was describing: `total_amount` was
  still directly `PATCH`-able via the header at the same time
  `_recompute_total_amount()` was writing it from the lines — two writers
  for one field, and a version bump doesn't resolve that, because the
  rollup isn't submitting an "expected prior value" to check against, it's
  deriving one; a manual header PATCH could still land after a line change
  and silently discard the freshly-summed total with no error either way.
  `patch_order()` now drops `total_amount` from a PATCH's patchable fields
  once the order has ≥1 line — the same way `_LINE_PATCHABLE` already
  drops `line_number` — so once the rollup starts writing it, it's the
  field's only writer; a header-only order (no lines, the original
  per-item Create Order flow) is unaffected and keeps direct access. Also
  from this pass: `jsonable_encoder()` (the previous pass's own fix, above)
  encodes a `Decimal` as a JSON **number**, breaking this codebase's own
  pinned convention that every money/quantity field serializes as a
  string (`orders-types.ts`'s header comment, restated in nearly every
  `-types.ts` file this session has touched) — `current_value` now goes
  through a small `_conflict_safe_value()` that stringifies
  `Decimal`/`date`/`datetime` before `jsonable_encoder` ever sees it, so
  the type stays consistent regardless of which layer serializes the
  response. And `AddLineForm.submit()`'s `setBusy(false)` sat after an
  unguarded `await onAdd(...)`, so a thrown network error or invalid-JSON
  response left "+ Add line" stuck disabled on "Adding…" for the rest of
  the panel's life; it now runs in a `finally`. Pinned by
  `test_total_amount_is_not_directly_patchable_once_lines_exist` and
  `test_field_conflict_current_value_serializes_decimal_as_string`.
  **Noted, not fixed:** `generate_orders()` (§21) calls `add_line()` once
  per consolidated material, so each now triggers its own
  `_recompute_total_amount()` — a SUM-and-conditional-UPDATE round trip per
  line instead of one after the whole batch. For the PO sizes this
  produces (materials consolidated per supplier on one quote) this is
  negligible; summing once after the loop would need a parameter threaded
  through a different module's function and isn't worth that coupling for
  a micro-optimization with no observed correctness cost.

  A sixth pass found the fifth pass's own `total_amount` fix was itself
  incomplete: dropping `total_amount` from `fields` left it in
  `payload.expected_versions` untouched, and `check_field_conflicts()`
  evaluates every key in that map regardless of whether `fields` still
  includes it — so a batch PATCH naming both `status` and `total_amount`
  together (each with its own `expected_versions`, the exact pattern this
  module's own docstring describes) would raise a spurious
  `FIELD_CONFLICT` on `total_amount` once its version had moved via the
  rollup, blocking the unrelated `status` write it was never meant to
  gate. Fixed narrowly — `total_amount` alone is dropped from
  `expected_versions` too, once lines exist — **not** by filtering to
  `fields` in general: `test_cutlist_conflict_on_unrelated_expected_version_key_does_not_500`
  (§L, cutlist) already pins the opposite behavior on purpose for every
  *other* field — a caller naming an unrelated/bogus key in
  `expected_versions` is meant to conflict, not be silently dropped — so a
  blanket filter would have broken that established, tested contract
  instead of fixing this one field's specific tension. Pinned by
  `test_stale_total_amount_expected_version_does_not_block_an_unrelated_write`.
  Separately: none of `patchField()` / `patchLine()` / `removeLine()` /
  `addLine()` in `OrdersClient.tsx` wrapped their `fetch()`/`res.json()` in
  try/catch, unlike the established pattern (`ItemMetadataPanel.tsx`'s own
  `patchField`) — a thrown network error left the calling field's onBlur
  handler mid-await with no revert and no visible error, looking saved
  while nothing had reached the server; all four now catch and report,
  matching that pattern exactly (`AddLineForm.submit()`'s `finally` from
  the fourth pass stays as defense in depth, but `addLine` itself no
  longer throws).

  A seventh pass found one more real gap and confirmed two prior notes were
  the right call to leave alone: `_recompute_total_amount()`'s `UPDATE`
  never set `updated_at`, unlike every other mutation in this module
  (`patch_order`, `cancel_order`, `sync_orders_for_item` all set
  `updated_at = now()`) — a line add/edit/remove genuinely changes the
  order, so its timestamp should move too; fixed, pinned inline in
  `test_add_line_returns_the_order_with_the_new_line`. Re-raised but
  **not fixed, on inspection**: rejecting a negative `quantity` /
  `unit_price` on the new line-PATCH endpoint — checked against every
  sibling Decimal field in this codebase (`estimate_line`'s `qty` /
  `cost_per_unit_snapshot`, this same module's own pre-existing
  `CreateOrderLineIn`) and **none** carry a `gt=0`/`ge=0` constraint
  anywhere; only percentage fields do. Adding one here alone would be a
  new, unprecedented rule for this one endpoint, not a fix to something
  this sub-project broke — left alone, consistent with the rest of the
  codebase. The order-status guard and the `EditableField`/
  `EditableDateField`/`BlurTextArea` duplication were both re-raised too;
  both already had their own notes above (*Known gap* and *Known
  duplication, not fixed*) and stood unchanged then — the guard has since
  shipped, see *Purchase order status guard*; the duplication remains.
- **Known duplication, not fixed.** `EditableField` / `EditableDateField` /
  `BlurTextArea` re-implement the same per-field PATCH +
  `expected_versions` + resync-and-dirty-check shape `ItemMetadataPanel.tsx`
  (`MetaField` / `NotesField`) and `CutlistClient.tsx` already carry as
  independent copies — a third one here. Flagged, not extracted into a
  shared hook: pulling three call sites with slightly different save
  signatures into one helper is a real refactor with its own risk, out of
  scope for a PATCH-editing UI on one more surface.
- **Out of scope (deferred):** per-line `expected_versions` (above);
  bulk line operations (multi-select delete, CSV re-import into an
  existing order); a PATCH-editing UI for anything on the Delivery Queue
  tab (`procurement_batches` — untouched, still #4's surface); reordering
  lines (`line_number` is immutable, matching `add_line`'s own
  auto-increment-only stance).

## Purchase order status guard — shipped

> Chosen by the user as "Option B" from the suggestion list that followed
> Global Search RBAC sync — **note the labels differ between lists**: this is
> Option B of *that* list, not Option B (Comments) of *Deferred options*
> below, and the user was asked which was meant before work started. Closes
> the gap the Orderbook editing section recorded as "Known gap, not fixed".
> No migration, no spec or plan doc; this section is its written record.

- **Rule.** An order whose `status` is `Cancelled` or `Delivered`
  (`orders.queries.FROZEN_STATUSES`) is read-only in the orders module:
  - **Lines** — `POST` / `PATCH` / `DELETE /orders/{po_id}/lines…` answer
    `409 {code: "ORDER_LOCKED", status}`. Enforced in the one place all three
    already pass through, `_lock_order_for_update()`, which now reads the
    status under the same `FOR UPDATE` lock — so a status change racing an
    edit cannot slip past the check. It raises `OrderLocked`; the routes turn
    that into the 409. A frozen order also answers 409 before any
    line-existence 404 (the order's state is answered first); an unknown
    *order* is still 404.
  - **Header** — `PATCH /orders/{po_id}` may change **`status` and nothing
    else**. Any other field answers `409 {code: "ORDER_LOCKED", status,
    blocked_fields: [...]}`. A mixed `{status, notes}` PATCH is **refused
    whole, not trimmed**: a 200 that silently dropped half the request would
    lie, and the caller can simply send two calls. `total_amount` on an order
    that has lines is still dropped silently first (its own rule — the
    rollup is the only writer), so a `total_amount`-only PATCH stays a no-op
    rather than a 409.
- **Settled decisions (user, asked before building; each was under-specified
  by every document):**
  1. **Which statuses freeze: Cancelled and Delivered.** Cancelled is dead;
     Delivered has been reconciled against goods received and invoices.
     `Rejected` stays editable — it can be fixed and resubmitted — as do
     `Draft` / `Pending` / `Approved` / `Hold` / `Quote` / `Next`.
  2. **`status` stays writable on a frozen order** — the deliberate,
     versioned, audited way back in. A mistaken cancel or delivery is
     reopened by PATCHing `status` (to anything, including another frozen
     status), after which the order is editable again. The alternative, a
     fully frozen order, would make that mistake fixable only in the
     database.
- **What it deliberately does not touch.**
  - **`DELETE /orders/{po_id}`** (soft-cancel) is unchanged: it still
    accepts a `Delivered` order and answers `ALREADY_CANCELLED` on a second
    call. Cancelling is a status change, which the rule permits.
  - **`sync_orders_for_item`** still rewrites CUTLIST NO. on a frozen order
    (Q430/Q431): that is the system keeping a reference true, not a person
    editing the order. Pinned by
    `test_cutlist_number_sync_still_reaches_a_frozen_order`.
  - **The legacy `/procurement/*` namespace** writes `Delivered` /
    `Cancelled` itself (`procurement/queries.py`) and carries no guard; this
    is scoped to `orders/`, the surface the Orderbook page uses.
  - **`generate_orders()`** is unaffected — it only adds lines to orders it
    has just created as `Draft`.
- **Web.** `OrdersClient.tsx` mirrors the set as `FROZEN_STATUSES`
  (**the backend is the source of truth and enforces it**; the constant only
  decides what to render). On a frozen order, for a caller who can write, the
  status select is kept and every other control — priority, the five header
  fields, notes, internal comments, and the whole lines table with Remove and
  Add-line — is rendered read-only, with a banner naming the status and how to
  reopen. A read-only role sees no banner (there is nothing for them to
  reopen). `ORDER_LOCKED` from a stale panel (the order was cancelled
  elsewhere while this one sat open) shows "Order is Cancelled — change its
  status to edit" beside the field, **refetches the order and refreshes the
  list**, so the panel lands in the frozen state instead of staying editable
  and failing again. ~~The status-set duplicated in TypeScript is a small
  drift risk~~ — **removed: `OrderOut.locked` is server-computed and the web
  reads it, see *Server-computed `locked` on orders* below.**
- **Fixed in review (same day).** `cancel_order` (`DELETE /orders/{po_id}`)
  is the *other* way into a frozen state, and it read the order with a plain
  `SELECT` and never bumped `field_versions["status"]` — so a panel that
  loaded the order before it was cancelled could PATCH `status` back with a
  still-valid `expected_versions` and silently undo the cancel, contradicting
  the "deliberate, versioned" reopen this section describes; two concurrent
  cancels could also both pass the `ALREADY_CANCELLED` check. It now takes the
  same `FOR UPDATE` lock and bumps the status version (pinned by
  `test_cancel_bumps_the_status_version_so_a_stale_reopen_is_a_conflict`).
  Separately, a lock message from a stale edit ("Order is Cancelled — change
  its status to edit") stayed in the panel's error state and reappeared under
  the same field once the order was reopened; a successful `status` change now
  clears every per-field and per-line message. `add_line` gained a docstring
  stating that it raises `OrderLocked`, since the freeze made a hidden
  precondition of it (`estimating.generate_orders` is safe only because it adds
  to orders it has just created as Draft).
- **Known gaps, found in review and deliberately not fixed.** (1) ~~`status` is
  an unvalidated string on `PatchOrderIn`~~ **Closed — see *Order field
  validation* below** (and note the `null` half was worse than described here:
  it persisted and broke every read; `priority` had the same bug, and a
  cross-workspace `vendor_id` hole turned up beside it). (2) ~~The `FROZEN_STATUSES` set exists in Python
  and TypeScript~~ (**closed — see *Server-computed `locked` on orders***), and the four handlers in
  `OrdersClient.tsx` each repeat a three-line "if locked, refetch and refresh
  the list" block; a shared helper would remove the latter but is a refactor of
  handlers this change only touched at the edges.
- **Tests:** 18 new cases in `test_order_routes.py` — all three line
  operations refused on each frozen status with nothing applied; non-status
  header fields refused with `blocked_fields`; a mixed PATCH refused whole;
  status as the way back in (and the order editable again afterwards); a
  move between frozen statuses; five non-frozen statuses stay editable; an
  unknown order is still 404 (and an unknown line on a frozen order is 409);
  the cutlist sync reaching a frozen order; a `total_amount`-only PATCH on a
  frozen order staying a no-op; cancelling a Delivered order; and the
  versioned-cancel regression above. The five refusal tests were confirmed
  to **fail against the pre-guard code**.
  Verified live in a browser against a migrated database: freeze via the
  status select, banner and editors gone, still frozen after reload, reopen,
  the stale-panel case (order cancelled out-of-band → refused, panel
  refreshed, nothing persisted), and a viewer sees no banner.
- **Out of scope (deferred):** guarding `Rejected`; ~~a server-computed
  `locked` flag~~ (**built, see below**); the same guard on the legacy `/procurement/*` routes;
  restricting who may reopen a frozen order (today anyone with
  `orderbook:write`, like every other status change) — a
  manager-only reopen would be a rule to decide, not assume.

## Comments, mentions and notifications (Plan V1 §29, Q473 / Q521 / Q523) — shipped

> Chosen by the user as the next sub-project after the Purchase order status
> guard ("Go with Comments (§29)"). §29 was under-specified in three ways, so
> the user was asked before any code was written — the three answers below are
> **settled decisions**, not assumptions. No spec or plan doc; this section is
> its written record. Q473 (build §29, so `comment` stops being a dead grant),
> Q521 (notifications: in-app only) and Q523 (mentions ship with comments)
> were already confirmed.

- **Settled scope (user).**
  1. **Four object types, not eight** (*since six — Module and shop-drawing
     revision were added by `0043`, see the section below; Task and Change are
     still not built*). §29 names Project, Area, Room, Joinery
     Item, Component, Task, Change and Revision. **Task and Change are not
     entities in this tree** (Q524 decided a `task` table, nobody built it;
     §11's change engine is unbuilt), and **Component / Revision are
     ambiguous** (module or part? shop-drawing or estimate revision?). v1
     covers **Project, Area, Room and Joinery Item** — the four that exist.
     The other four get a thread when their entity does; adding one is a new
     nullable FK column + an `object_type` branch, not a redesign.
  2. **Comments, one-level replies and @mentions.** Attachments / photos,
     decision marking, "internal notes" and company / team / department
     discussion areas are **not built** (§29 lists them; a channel entity +
     membership is a materially bigger build).
  3. **A minimal in-app inbox** behind the mentions — not §30's
     Event → Recipient → Channel rules engine: no preferences, grouping,
     acknowledgement, escalation, email or push.
- **Migration `0042`.**
  - `comment` — the object is **four nullable real FKs** (`project_id`,
    `area_id`, `room_id`, `item_id`) with `CHECK num_nonnulls(...) = 1`, not a
    polymorphic `(object_type, object_id)` pair: deleting an item / area /
    room / project takes its thread with it (`ON DELETE CASCADE`) instead of
    leaving dangling comments, and `object_type` is a **generated column**, so
    there is no second source of truth. `workspace_id` is a direct column
    (the Q555 pattern — a comment spans four parents with no single join
    path), set from the resolved object.
  - **Replies are one level deep, enforced by the database**, the way `0028`
    enforces Q449: `parent_is_reply` is always false when a parent is set, so
    the composite FK `(parent_comment_id, parent_is_reply) → comment
    (comment_id, is_reply)` can only be satisfied by a top-level comment.
    Which object a reply belongs to is **inherited from its parent by the
    application** — a reply request names only `parent_id`, never an object,
    so the two cannot disagree (the DB cannot express that check across four
    nullable columns; `MATCH SIMPLE` skips a FK with any NULL column).
  - `comment_mention (comment_id, user_id)` and `notification` (recipient,
    actor, `kind IN ('mention','reply')`, `read_at`) with
    `UNIQUE (recipient_id, comment_id, kind)` — re-mentioning someone on edit
    cannot ping them twice. **Not searchable** (no `0033` trigger).
- **Backend — `apps/api/app/comments/` and `apps/api/app/notifications/`**,
  mounted at top-level paths.
  - `GET /comments?object_type=&object_id=` (`tracking:read`),
    `POST /comments` (`tracking:comment`), `PATCH /comments/{cid}`,
    `DELETE /comments/{cid}`, and `GET /projects/{pid}/comment-counts`
    (`tracking:read`; live comments per area and per room of one project —
    deleted ones are not counted, an area or room with none is simply absent). **This is the first place the `comment` action
    is enforced** — the four original object types are governed by the
    `tracking` module (areas / rooms already gate on it); a Module and a
    revision are governed by `list` and `shop_dwgs` instead (*see below*). A viewer (read only) can read
    a thread and cannot post; editor, drafter, purchase officer, estimator,
    manager and admin can.
  - **Edit is author-only — even a manager cannot edit someone else's words**
    (`403 NOT_AUTHOR`). **Delete is the author, or a manager / admin**
    (`403 FORBIDDEN`), and is a **soft delete** (`409 ALREADY_DELETED` on a
    second). A deleted comment survives only as a blanked placeholder while a
    surviving reply hangs off it; a deleted reply, or a deleted top-level
    with no replies, disappears from the API. Replying to a deleted comment
    is `409 PARENT_DELETED`; a reply to a reply is `409 REPLY_TO_REPLY`.
    These per-object rules live in the query layer, not the matrix (Q472 is
    still not built).
  - **Joinery Items only** — a related part has no thread (404), the
    `item_documents` / `qc` precedent and §29's own wording.
  - **Mentions are ids, not parsed text.** The client sends
    `mentioned_user_ids`; the body's `@Name` is presentation. Each id must be
    an **active user of this workspace who can read what the thread links
    to** (checked against the Dynamic RBAC engine, workspace-wide) or the whole
    request is refused `422 BAD_MENTION` listing the ids and **nothing is
    written** — a notification linking someone to a record they cannot open is
    worse than refusing. "Can read" is `tracking:read` for a Project / Area /
    Room thread and **`tracking:read` + `list:read` for an Item thread**,
    because the notification opens the item editor and `GET /items/{id}` is
    gated on `list` (the engine lets an admin grant one without the other; every
    default role holds both). The same pair gates *reading and posting* to an
    item thread (`403` without `list:read`). At most **20** mentions per
    comment. Only *newly added* mentions are validated on an edit: one already
    on the comment must not block an unrelated typo fix because its owner has
    since lost access. A mention notifies the mentioned user (never yourself); a reply
    notifies the parent's author, **unless they were also mentioned** (the
    mention wins, one row) **and only if that author can still read the thread**
    — a reply is never refused over its recipient, it is just not sent to
    someone who could no longer open it. Editing replaces the mention set: a *newly added*
    mention is notified, a *removed* one keeps the notice already sent (they
    were told), and an unchanged edit is a no-op (no `edited_at`, no audit).
  - Notifications (`current_user` only, no RBAC row — like `/search`, it shows
    a person only what is addressed to them): `GET /notifications?unread_only=
    &limit=&offset=` (newest first, with `unread_count`),
    `POST /notifications/{nid}/read` (404 if it is not yours),
    `POST /notifications/read-all`. **Notifications whose comment was
    deleted are hidden and not counted** — a badge pointing at nothing would
    be a lie. **So are notifications the recipient can no longer read**: an
    excerpt is comment text, so without `tracking:read` the inbox is empty and
    without `list:read` item threads are left out (hidden, not deleted — they
    return if access is restored). Marking read is audited
    (`notification.read`, `notification.read_all`), **once per real change** —
    re-marking a read notification, or a read-all that marks none, writes
    nothing — so "every authenticated mutation is audited" holds without
    bending it. (A first draft skipped this on the project-favourites
    precedent; the review pointed at the stated rule.)
  - Creating a comment takes `FOR KEY SHARE` on its object's row, so a hard
    delete racing the INSERT waits instead of surfacing as a raw FK 500.
  - Every comment mutation writes `audit_log` (`comment.{create,edit,delete}`)
    and — on an item — `item_edit_log` in the same transaction, per the PM
    Workbench invariant (`_comment_create`, `comment.{id}`, `_comment_delete`).
    Bodies are stripped before the length check (1–5000): a whitespace-only
    body is a clean `422`, not a raw `ck_comment_body_len` violation (found by
    the test suite — the first pass validated length before stripping).
- **Web.**
  - `components/comments/CommentThread.tsx` (+ `MentionTextarea`,
    `mentions.ts`) — one component for any object type: post, one-level
    reply, edit own, delete (own, or manager / admin), with an `@` picker fed
    from `/workspace/team` (arrow keys / Enter / Escape; a full name with a
    space can be typed). Which members get notified is derived from the
    **final text** (`mentionedIds`, longest name first with each match
    consumed, so `@Ann Lee` does not also mention `Ann`), so deleting an
    inserted `@Name` un-mentions it; only names the API confirmed are
    highlighted in a stored body. Two members with the very same full name
    cannot be told apart by text — only the first is mentioned. Timestamps
    render in the viewer's own zone (`formatLocalTs`), not as sliced server
    time. `canComment` mirrors `tracking:comment`;
    the API enforces it regardless.
  - **Surfaces: the item editor's Comments tab
    (`/items/[id]?tab=comments`), a Comments card and an **Areas & Rooms card**
    on `/projects/[id]`.** Area and Room have no page of their own, so their
    threads live on the Areas & Rooms card
    (`ProjectAreasCommentsCard.tsx`, placed there by the user): the project's
    areas with their nested rooms, each with a comment-count badge, and the
    selected one's `CommentThread` beside the list. The selection lives in the
    URL (`?area=<id>` / `?room=<id>`) so it can be linked to, and that is
    exactly what a notification for an Area or Room comment deep-links to
    (`/projects/{pid}?area=…`). **A click sets local state and the URL
    together, synchronously** (`history.replaceState`, which Next 16 integrates
    with `useSearchParams` — per the bundled docs), and a URL change that did
    not come from a click — a notification followed *while already on this
    page*, or back/forward — is synced back into state. **A deep link scrolls the card
    into view** (it is the last card on the page, 1447px down against a 720px
    viewport); a click on a row does not. A link to an area or room that has
    since been deleted says so instead of showing nothing. Posting, replying,
    editing or deleting refreshes the badges (`CommentThread`'s `onMutated`;
    only the newest refresh may write, so two quick posts cannot leave a stale
    count). A project with no areas says areas are created from an item's Area
    picker. A room's notification label names its area (`R01 Kitchen (Level 1)`),
    because "R01" alone is ambiguous across areas.
  - **Found in review, worth remembering: a selection with a live input beside
    it must change synchronously.** Two earlier cuts were wrong in opposite
    ways. Deriving the selection purely from `useSearchParams()` with
    `router.replace` meant the URL — and so the thread — changed only after a
    server round trip; until then the *previous* thread's input was still on
    screen, a test typed into it, and the text was thrown away when the thread
    remounted (Playwright: "element was detached from the DOM"), and two quick
    clicks raced their landings. Holding the selection in state alone left a
    same-page notification link unable to switch the thread. It is now local
    state **plus** a synchronous `replaceState`, with a URL→state sync for
    changes that are not ours. The area/room roster is fetched once by the card
    and passed to each thread (`roster` prop) rather than once per remount, and
    is deliberately **not** cached in a module: that would outlive a logout and
    show the previous user's team to the next one. A link naming an area or room
    created since the page loaded triggers one refetch of the list before the
    card calls it deleted.
  - `NotificationBell` in the `TopBar` (unread badge, six most recent,
    mark-all-read; **polls once a minute and on window focus — there is no
    push channel, by Q521**) and a `/notifications` page (not a tab).
- **Seed.** `make seed` on ALF-001: three comments on the first joinery item
  (a drafter mentions the foreman, the foreman replies, a manager comments)
  and one project comment mentioning the drafter — through the same query
  functions the API uses — so Juno Okafor's bell starts at 1 and Noa
  Lindqvist's at 2. It also leaves one comment on that item's own area and one
  on its room (**no mentions**, so those bell counts are unchanged) so the
  Areas & Rooms card opens with badges. Idempotent (the demo item's, project's,
  areas' and rooms' threads are dropped first; notifications cascade).
- **RBAC — no matrix change.** `tracking:{read,comment}`, already granted.
- **Tests.** `test_comments.py` (46 cases): each object type round-trips;
  the `comment` action is enforced; body trim / bounds; related part 404;
  workspace isolation on every verb; replies inherit the object, refuse
  reply-to-reply, and the DB itself rejects reply-to-reply, two objects and
  none; deleting the object takes its thread; mention / reply notification
  rules (self-silent, mention beats reply, unique on edit, only new mentions
  notified); bad mentions (foreign, inactive, unknown, and a user whose only
  group grants nothing on `tracking`) refused whole with nothing written;
  author-only edit, author-or-manager delete, deleted-thread shapes, hidden
  notifications; inbox read-state and ownership; audit + `item_edit_log`;
  and seven regression tests for the review fixes above (item threads need
  `list:read`, an unchanged mention never blocks an edit, no reply to a parent
  author who lost access, the inbox hides what is no longer readable, mark-read
  audited once, the FOR KEY SHARE lock, the 20-mention cap) — six were
  confirmed to **fail against the pre-fix code**; the cap test was tightened
  after it turned out to pass there for the wrong reason. Four more cover the
  Areas & Rooms work: counts are per area and per room (replies count; item
  and project threads do not), deleted comments are not counted, counts are
  scoped to one project, and the endpoint needs `tracking:read` and a project
  in this workspace; and the notification-link test now pins
  `/projects/{pid}?area=…` / `?room=…` (it used to assert an area had *no*
  link).
  `tests/e2e/comments.spec.ts` (6 tests) was run against a live migrated,
  seeded stack: a mention reaches the bell and opens the item's Comments tab
  with the mention highlighted and the reply nested; the `@` picker, edit,
  and a manager's delete; a viewer sees the thread with no form; the Areas &
  Rooms card (badges, an area's and a room's thread, the room's badge
  following a post); a mention on an area's thread deep-linking the
  notification to that thread; the project page's thread. The migration
  downgrades and re-upgrades cleanly.
- **Known gaps, recorded rather than silently left.**
  - Task and Change have no thread at all (above); Component and Revision got
    one in `0043` (as a Module and a shop-drawing revision — an estimate
    revision still has none).
    (Area / Room had no UI when Comments first shipped; the Areas & Rooms card
    closed that.)
  - The Areas & Rooms card lives only on `/projects/[id]`: an item's editor
    does not link to its own area's or room's thread. It is one click away, not
    inline.
  - `GET /projects/{pid}/comment-counts` and every `/comments` route check
    **workspace-wide** `tracking` grants, while `GET /projects/{pid}/areas`
    honours a project-scoped membership (`project_param`). A user whose only
    `tracking:read` is project-scoped therefore sees the area list but gets 403
    for counts and threads (the badges silently vanish; the thread shows the
    error). The same ceiling mentions and Global Search already document;
    passing `project_param` on the comment routes needs the object's project
    resolved before the permission check, so it is a design change, not a
    one-liner.
  - A mention of a user who is later deactivated is left in the stored body;
    editing the comment drops that mention (the roster no longer lists them).
  - `_readers` asks the RBAC engine once per mentioned user (one or two
    queries each), which is why mentions are capped at 20; resolving a whole
    id set in one query would mean re-implementing the engine's
    membership-fallback rule beside it (the same call Global Search made).
  - The bell's poll is a plain interval: a comment made in another window
    shows up within a minute, not instantly.
  - Who may be mentioned is decided from workspace-wide grants only — a user
    whose only `tracking` access is a project-scoped membership cannot be
    mentioned, the same ceiling Global Search documents.
- **Out of scope (deferred):** Task and Change threads (Component and Revision
  were built by `0043`); attachments /
  photos, decisions, internal notes and discussion areas; §30's rules engine,
  preferences, email / push, grouping and escalation; search over comments;
  a comment count on the Tracking grid.

## Deferred options (recorded, not built)

Three alternatives were proposed alongside Purchase Order editing (above)
when this session was asked to suggest the next sub-project; the user chose
PO editing and asked that the other three be recorded rather than dropped
silently. **B (Comments), C (QC Dashboard) and D (Search RBAC sync) have all
since been built.**

- ~~**Option B — Comments (Plan V1 §29, Q473).**~~ **Built — see *Comments,
  mentions and notifications* above.** Kept for history: a generic comment/mention
  system over 8 object types, the feature that would finally give the
  `comment` RBAC action (present on every module in the matrix since
  Foundation) something real to gate — today it is a dead grant everywhere
  except `isample`/`shop_drawings`-style review notes, which are bespoke
  fields, not this. Sized larger than PO editing: a new entity, @mentions,
  and a decision on which 8 object types get a comment thread first.
  Already named once as deferred, in *Dynamic RBAC engine* above (Q473).
- ~~**Option C — QC Dashboard (Plan V1 §4.2).**~~ **Built — see *QC
  Dashboard* below.** Kept for history: the standalone cross-project
  dashboard the *QC / Rework / Packing* section above explicitly named as
  out of scope when that sub-project shipped the per-item QC surfaces
  (defects/checklist/rework tabs, PACKING stage) that would back it. This
  ships only the aggregation view on top of data that already exists —
  lower schema risk than B, but needs a design decision on what it
  aggregates across (open defects by project? by supplier? by stage?)
  that Plan V1 doesn't spell out.
- ~~**Option D — Sync Global Search's RBAC check to the Dynamic RBAC
  engine.**~~ **Built — see *Global Search RBAC sync* below.** B and C
  remain unstarted.

## Global Search RBAC sync — shipped

> Chosen by the user from the four options proposed after the Orderbook
> editing UI (the recommended one: smallest, clearest "done"). Closes the
> gap *Dynamic RBAC engine* recorded as "flagged, not silently resolved".
> No migration, no spec or plan doc; this section is its written record.

- **What changed.** `apps/api/app/search/routes.py::readable_types(db, user)`
  (was `readable_types(auth_role)`) now asks the Dynamic RBAC engine
  (`rbac_engine.has_permission_db`) instead of the static `MATRIX`, so a
  group's grants — customised through the Permission Groups admin UI —
  decide which result **types** a member sees, in both directions: a
  revoked `orderbook:read` hides order/supplier results, and a custom group
  granting only `orderbook:read` hides item results even though the role's
  `MATRIX` row would show them. `GET /search` gained a `db` dependency to
  supply the session. Nothing else moved; the Meilisearch filter still
  always carries `workspace_id`, and unreadable types are still dropped
  silently, never 403'd.
- **Settled decision — workspace-wide grants only (`project_id=None`).**
  The option's own note flagged this as needing to be stated, not assumed.
  Search has no single project in scope (the `project_id` query param
  narrows *results*, it is not a permission scope), so a project-scoped
  membership is deliberately not consulted. **Consequence, recorded
  rather than hidden:** a user whose *only* memberships are project-scoped
  gets no result types at all — the engine treats "has any membership"
  as fully DB-governed and never falls back to `MATRIX`, and a
  project-scoped grant is invisible at workspace scope. Pinned by
  `test_project_scoped_only_membership_sees_no_types`. In practice this
  needs an admin to deliberately strip a user's workspace-wide group;
  Q466's model is project memberships *added to* a role group. If that
  becomes a real need, passing the request's `project_id` into the check
  when supplied is safe (the index filter already restricts to that
  project) — but an unfiltered search would still show nothing, so it is
  a design question, not a one-line fix.
- **Cost.** `readable_types` resolves each *distinct module* once (11 types
  map onto 7 modules) rather than once per type — it runs on every
  keystroke of the TopBar box, and each engine call is a query (two when
  the grant set is empty). A single all-grants query would be cheaper
  still; not done, since it would re-implement the engine's
  membership-fallback rule beside the engine.
- **Test infrastructure trap, recorded because it recurs.**
  `rbac_engine.py` does `from .permissions import MATRIX`, binding its own
  name. A test that swaps the fallback matrix must patch
  **`rbac_engine.MATRIX`**, not `permissions.MATRIX` — patching the latter
  replaces an attribute the engine never reads, and the test passes or
  fails for the wrong reason. `test_unreadable_type_is_dropped_silently`
  was patched this way; `_login()`'s raw-SQL users hold zero memberships,
  so they still exercise the fallback.
- **Tests:** three new in `test_search_routes.py` — revoking a system
  group's grant hides the type, a custom group governs in both directions
  (and `types=` cannot reach past it), and the project-scoped-only ceiling.
  Full suite green (985 passed, 10 skipped, the same pre-existing local
  `MEILI_URL` failure) before the last two tests were added; the search
  route module alone re-run green after (21 passed).
- **Was a known gap here: `/auth/me` served the static matrix.** **Closed — see
  *`/auth/me` follows the permission groups* below.**

## `/auth/me` follows the permission groups — shipped

> Chosen by the user ("Go with /auth/me permissions") from the gaps left open
> after the Areas & Rooms card — the one *Global Search RBAC sync* recorded as
> "its own decision". No migration, no spec or plan doc; this section is its
> written record.

- **What changed.** `GET /auth/me` served `permissions_for(user.auth_role)` —
  the static `MATRIX` row — while every `require_permission` check and (since
  the Search sync) Global Search already asked the Dynamic RBAC engine. So a
  user whose grants an admin customised through the Permission Groups panel saw
  the tab strip and every `can(me, …)` write affordance follow the *role*, not
  the *groups*: a revoked `orderbook:read` dropped the Orderbook results from
  search and still showed the Orderbook tab. `/auth/me` now serves
  `rbac_engine.effective_permissions(db, user)`, so the web tier follows the
  same grants the API enforces, in both directions.
- **`effective_permissions` is one grants query, not twelve.** `/auth/me` runs on
  every page load; calling `effective_actions` per module would cost 12–24
  queries. It reads the user's workspace-wide grants once and applies the
  engine's own fallback rule: a module with grants uses them; otherwise a user
  holding **any** membership gets `[]` (a real "no"), and a user holding **none**
  gets the `MATRIX` row (`permissions_for`). It deliberately re-states that
  rule beside the engine's rather than sharing it, so
  `test_effective_permissions_agrees_with_effective_actions` pins the two
  together across every branch — do not loosen it. Same response shape as
  before: every module present, actions sorted, `[]` meaning no access.
- **Settled decision — workspace-wide grants only.** The map carries no
  project, so a project-scoped membership is not represented in it (the same
  ceiling Global Search and the comment routes document, and what the ~181
  call sites without a `project_param` check anyway). Consequence: a user whose
  *only* memberships are project-scoped gets an all-empty map, and the tab
  strip hides everything for them, even though a route that passes
  `project_param` would let them in on that project. Pinned by
  `test_effective_permissions_project_scoped_only_membership_is_empty`. Serving
  per-project grants would mean a second payload keyed by project, which is a
  design change, not part of this.
- **`MATRIX` is still the fallback and `permissions_for` still exists** — the
  route no longer calls it directly, `effective_permissions` does, for a user
  with zero memberships (every test file's raw-SQL user). Nothing else changed:
  `require_permission`, the 181 call sites and the web `can()` are untouched.
- **Web.** No behavioural change to `TabStrip` / `can()`; only the comments in
  `lib/permissions.ts` that said "for this user's role". The tab-strip gate is
  now live in the sense the *Web shell* section anticipated: removing a module's
  `read` grant from a group hides that tab for its members.
- **Tests.** In `test_rbac_engine.py`: parity with `effective_actions` across
  zero memberships, a narrow group, a project-scoped membership, and
  most-permissive-wins; the project-scoped-only ceiling; parity with the seeded
  system group for every role in `MATRIX`; and an HTTP test that a grant
  revoked from a group disappears from `/auth/me` (confirmed to **fail against
  the old route**: `['read'] == []`). The existing
  `test_me_includes_permissions_matching_the_matrix` still passes unchanged —
  a zero-membership user falls back to the matrix, which is the point of the
  fallback. Verified live in a browser against a migrated, seeded stack: a
  seeded viewer's Orderbook tab and `me.orderbook` (`["read"]`) both went away
  after the grant was deleted from the viewer group, on reload.
- **Known gaps, recorded.**
  - ~~The web `Module` type in `lib/permissions.ts` lacked `"qc"`.~~ **Closed by
    the QC Dashboard**, whose tab is the first thing to call `can(me, "qc", …)`.
  - A permissions change takes effect on the user's **next page load** — there
    is no push channel, and `(app)/layout.tsx` fetches `me` per navigation.
  - Q472's per-object rules (`require_drafter()` etc.) are still hand-written
    in route handlers, so a group grant cannot express them and `can(me, …)`
    is a coarse gate for those surfaces, as it already was.

## QC Dashboard (Plan V1 §4.2, Q515) — shipped

> Chosen by the user as the next sub-project after `/auth/me` ("Next task is QC
> Dashboard (§4.2). Ask me any questions"). §4.2 names a "QC Dashboard" and says
> nothing else, so the user was asked before any code was written; the answers
> below are **settled decisions**, not assumptions. No migration, no spec or plan
> doc; this section is its written record. It is the option *Deferred options*
> called C, and it closes the gap *QC / Rework / Packing* named as out of scope.

- **Settled decisions (user).**
  1. **Scope: only items whose cutlist has started but not finished.** The user's
     wording was "current cutlists have not been assigned to finished but have
     already started to make", which was ambiguous, so it was asked again and
     confirmed. A cutlist has no finished flag, so both words are **derived from
     Shop Floor** (Q412: the workflow belongs to the cutlist):
     *started* = an assignment on the cutlist with `started_at` set and not
     cancelled, **or** any `stage_completion_log` row not undone;
     *finished* = a `PACKING` completion not undone (PACKING is the last Shop
     Floor stage; DEL / INST are not assignable, Q561). A merely `assigned` task
     is **not** started; a cancelled start is not started; an undone completion
     is not a completion; an undone PACKING puts a cutlist back in scope.
     **An item with no cutlist is out of scope** (nothing to have started).
  2. **Open records only**, for both defects and rework. Resolved defects and
     closed rework are history and stay on the item's own QC tab.
  3. **Contents:** open defects by project and by stage, open rework by project
     and kind (with cost), and a drill-down list of the items carrying open
     records. Checklist completion and a per-record worklist were offered and
     **not** chosen.
  4. **`/qc` on the secondary tab strip, gated on `qc:read`.** No new permission:
     IT already controls it through the permission groups, and the tab hides
     when `qc:read` is removed (the `/auth/me` work). Q466 deliberately did not
     build tab-level scoping, so this is the same module gate every other tab has.
  5. **Read-only**, every row linking to `/items/{id}?tab=qc` where raising,
     resolving and closing already live with their own `qc:write` / `qc:approve`
     rules. Nothing on the dashboard mutates data, so it writes no audit row.
  6. **Fixed numbers, filterable by project and date range** — no configurable
     widgets, matching Q527 (fixed KPI catalogue, no formula engine).
- **Records outside the scope are counted, never dropped.** That is a choice made
  while building, not one the user asked for: with a started-but-not-finished
  scope, a defect raised on a cutlist nobody has begun would otherwise vanish
  from QC entirely. `scope.open_defects_out_of_scope` /
  `open_rework_out_of_scope` say how many were left out, and the page shows an
  amber note when either is non-zero. Related parts are neither in scope nor
  counted as outside it (they are not Joinery Items; a defect on one cannot be
  raised through the API anyway).
- **Backend — `apps/api/app/qc/dashboard.py`** (+ schemas, one route in
  `qc/routes.py`). `GET /qc/dashboard?project_id=&date_from=&date_to=`, gated
  `("qc", "read")`. One `scope` CTE feeds every number so they cannot disagree
  about which items count. `404` for a project outside the workspace, `422` when
  `date_from` is after `date_to`. The date range filters when a record was
  **raised** (`created_at`, inclusive of both ends) — for an open record that is
  the only date it has; there is no "resolved in range" because resolved records
  are not shown. Stage order comes from the `stages` lookup's `sort_order`, with
  untagged defects last. **Stage labels are lookup data and differ between
  databases** (`Marked Down` in one, `Down` in another), so tests assert
  `stage_key`, never a label.
- **Rework cost can under-count, and says so.** `rework.cost` is optional, so
  `rework_cost_total` sums only what was recorded and `rework_cost_missing`
  counts the open rework with no cost. The page shows `—` (not `$0.00`, which
  reads as a real total) when *nothing* has been priced, and "Excludes N open
  rework with no cost recorded" otherwise. Money arrives as a JSON string, as
  everywhere else.
- **Web.** `/qc` (`app/(app)/qc/page.tsx` + `QcDashboardClient.tsx`), a `QC` entry
  on the secondary strip after Cut Floor (production tabs together, Estimating and
  Customers still a pair). Filters live in state **and** the URL
  (`?project=&from=&to=`, via `history.replaceState`, the pattern the Areas &
  Rooms card uses) so a filtered view is linkable and survives a reload; only
  the newest request may write, so a slow response for an earlier filter cannot
  overwrite the one on screen. `lib/permissions.ts`'s `Module` type gained
  `"qc"` (it lagged `0039`).
- **Seed.** `make seed` adds to what §M already left on ALF-001: an open `CNC`
  defect on the third item (its cutlist has a `DOWN` completion — in scope, and a
  second stage for the chart) and an open, untagged defect on the second item
  (its cutlist is only *assigned* — out of scope, so the amber note has
  something to say). Through `app.qc.queries`, so the rows carry real audit /
  edit-log entries. Idempotent (both items' defects are dropped first). The
  dashboard then opens with 2 open defects, 1 open rework with no cost, and
  1 defect not counted.
- **RBAC — no matrix change.** `qc:read`, already granted to every role.
- **Tests.** `test_qc_dashboard.py` (15): scope at **every** boundary (started,
  completed, unpacked are in; no cutlist, not started, merely assigned,
  cancelled start, undone completion, finished are out) and an undone PACKING
  bringing a cutlist back; out-of-scope counted for both kinds of record; open
  only; by project and stage with untagged last and the oldest age; rework by
  kind with cost and unpriced count; drill-down oldest first and omitting clean
  items; the empty dashboard; related parts not counted; project filter scoping
  even the out-of-scope counts; the date range (inclusive, and applied to the
  out-of-scope counts too); the 404 / 422 edges; `qc:read` required (a group
  stripped of `qc` gets 403) and sufficient (a viewer sees it); workspace
  isolation; read-only writes no audit row. **The scope test was confirmed to
  fail against a loosened "started"** (any assignment counts: 5 items in scope
  instead of 3). `tests/e2e/qc_dashboard.spec.ts` (4) was run against a live
  migrated, seeded stack: the numbers and the amber note, a row drilling to the
  item's QC tab, filters narrowing / persisting across a reload / clearing, and a
  viewer seeing the same numbers with no buttons on the page. The spec is
  read-only, so unlike estimating / comments it is safe to re-run without
  re-seeding. `smoke.spec.ts` and `item_project_detail.spec.ts` (which touch the
  tab strip) still pass.
- **Known gaps, recorded.**
  - **Checklist completion, a per-record worklist and resolved / closed history
    are not on the dashboard** (not chosen). The drill-down goes to the item.
  - **No supplier breakdown.** Defects and rework are not linked to a supplier;
    adding that is a schema change, not a query.
  - `rework.responsibility` is free text, so there is no "by person / team"
    view either.
  - The scope is derived, so a cutlist whose stages were never assigned through
    Shop Floor (work recorded some other way) reads as *not started* and its
    defects show only in the amber count.
  - The date range uses the database session's time zone for its day
    boundaries, and "oldest" ages are computed in the browser.
  - The dashboard does not poll: the numbers refresh on a filter change or a
    reload, not on a timer (the bell and the Shop Floor board do poll).
  - **Two grants, one click.** The dashboard needs `qc:read`; the drill-down
    opens `/items/{id}`, which needs `list:read`. Every default group holds
    both, but an admin who grants one without the other gives a user a link that
    403s — the same pairing gap Comments documents for item threads. The Project
    filter's list comes from `GET /projects` (`tracking:read`), so it too comes
    back empty for a group that holds `qc:read` alone.
  - **Full rework mostly falls outside the scope.** Q518 puts Full Rework *after
    Installation*, and Installation is after PACKING — the point at which a
    cutlist leaves the dashboard's scope. So open `full` rework (and defects
    found on site) are counted only in the amber "not counted" note, and the
    Full column and cost tile are structurally sparse. This is the direct
    consequence of the user's confirmed "started but not finished" rule, not a
    bug, and the rule was **not** changed; whether post-PACKING open records
    should also be counted is the open question it leaves.
- **Out of scope (deferred):** the other §4.2 department dashboards (Estimating,
  Project Management, Procurement, Material, Production, Installation,
  Management); §4.3's management KPI dashboards; user-arranged widgets;
  export / scheduled reports (§31).

## Order field validation (`PatchOrderIn` / `CreateOrderIn`) — shipped

> Chosen by the user as "PatchOrderIn.status validation" — the first of the two
> *Known gaps* left under *Purchase order status guard*. It grew twice while being
> built, each time because checking the neighbouring fields turned up the same
> bug or a worse one, and **each time the user was asked before it grew**: first
> `priority` and `category` (settled: "Yes: priority and category too"), then a
> cross-workspace `vendor_id` hole (settled: "Fix it in this PR"). No migration,
> no spec or plan doc; this section is its written record.

- **What was wrong, each measured before fixing.** `PatchOrderIn` took bare
  `str` / `int` for fields the database constrains, and `patch_order` sent them
  straight into the UPDATE:
  - **`status` / `priority` — an unknown value** (`"Foo"`, but also `"draft"`,
    `" Draft"`, `""`: the CHECKs are exact and case-sensitive) was a raw
    `CheckViolation` 500 (the route has no `IntegrityError` handling).
  - **`status` / `priority` — an explicit `null` poisoned the whole Orderbook.**
    This file had recorded it as "leaves an order with no status"; it was much
    worse. Both columns are nullable and NULL satisfies the CHECK, so it was
    **written**; the route calls `db.commit()` *before* FastAPI validates the
    response, so the NULL **persisted**, and then `OrderOut.status: str` /
    `priority: str` 500'd on **every read of that order — including the
    workspace-wide `GET /orders` behind the Orderbook page**. One `null` from
    anyone with `orderbook:write` took the Orderbook list down for the whole
    workspace until the row was repaired in the database. Reproduced on the
    unfixed code for both fields (`PATCH → 500`, DB value `NULL`, `GET
    /orders/{id} → 500`, `GET /orders → 500`).
  - **`category`, `vendor_id`, `description`** are `NOT NULL`, so an explicit
    `null` was a raw 500 (nothing persisted). An unknown `category` was a raw FK
    500 (the column references the `order_category` lookup).
  - **`vendor_id` — a cross-workspace hole.** `create_order` checks the vendor is
    in the caller's workspace; `patch_order` never did. `PATCH /orders/{id}` with
    **another workspace's `vendor_id` returned 200, saved it, and the response
    carried that workspace's supplier name** (verified live). An order with no
    project reaches its workspace *through its vendor* (Q554/Q555), so this could
    also have moved such an order into the other workspace. An unknown
    `vendor_id` was a 500.
- **The fix — `apps/api/app/orders/{schemas,queries,routes}.py`.**
  - **`OrderStatus` and `OrderPriority`** are `Literal`s of the values in
    `purchase_orders_status_check` / `_priority_check` (migration `0002`).
    `PatchOrderIn.status` / `.priority` use them; **`CreateOrderIn.priority`
    does too** (its unknown value was the same 500, at the INSERT).
  - **One `field_validator`** on `PatchOrderIn` refuses an explicit `null` for the
    five fields `vendor_id`, `description`, `category`, `status`, `priority`. A
    `field_validator` rather than `PatchOrderLineIn`'s `model_validator` on
    purpose: it runs only for a field the caller **supplied** (an omitted field is
    untouched) **and** the 422 names the field (`loc` ends in `status`, not just
    `body`). Explicit null is *rejected*, not read as "no change" — the choice
    `PatchOrderLineIn` already made, so it was not asked. `description` is in the
    set because it is the identical `NOT NULL` failure beside its siblings.
  - **`category` is checked against the lookup, not a `Literal`** — `order_category`
    is data IT can extend without a migration (Q557). `_category_exists()` runs in
    `patch_order` **and `create_order`**; unknown → `422 {code: "UNKNOWN_CATEGORY",
    category}`. **An archived category is still accepted**: the FK always did, this
    turns a 500 into a refusal and adds no archiving rule (pinned, and recorded as
    a gap, not endorsed).
  - **`vendor_id` is checked in `patch_order`** with the same
    `_vendor_in_workspace()` `create_order` now shares (one query, previously
    inline): unknown *or another workspace's* → `404 {code: "VENDOR_NOT_FOUND",
    vendor_id}`, the create route's own precedent and shape. Nothing is written,
    versioned or audited, and the foreign name never appears in the response.
  - **Order of checks in `patch_order`:** `NOT_FOUND` → `ORDER_LOCKED` (a frozen
    order answers its state first, whatever the values) → the two reference checks
    → `FIELD_CONFLICT` → write. A `{status: bad, notes: …}` PATCH is refused
    whole: nothing half-applied.
  - `OrderOut` is **unchanged** (`status: str`, `priority: str`): narrowing a
    *response* type would turn any legacy row holding an unexpected value into a
    500 on read, the exact failure this removes on the write side.
- **The `Literal`s are hand-kept copies of the DB CHECKs**, like `FROZEN_STATUSES`
  and the web's `STATUSES`. Unlike those they are **pinned**:
  `test_the_accepted_statuses_are_exactly_the_databases` /
  `..._priorities_...` read the CHECK from `pg_constraint` and fail if a migration
  changes one side (the first also asserts `FROZEN_STATUSES` is a subset). **A
  migration that adds a status must update `OrderStatus`, `FROZEN_STATUSES` if it
  should freeze, and `OrdersClient.tsx`'s `STATUSES`** — the first is enforced by a
  test, the web copy is not.
- **Web.** `lib/orders-types.ts`'s `PatchOrderIn`: `vendor_id`, `description`,
  `category`, `status`, `priority` lost their `| null`, so the *type* documents
  what the API refuses. It is documentation only: `patchField` in
  `OrdersClient.tsx` takes `value: unknown`, so the compiler cannot catch a null
  sent through it. No UI change: the selects can only send valid values, and any
  other failure already reads "Save failed (422)".
- **Tests** (`test_order_routes.py`, 46 new). DB-parity for status and priority;
  all nine statuses and all six priorities accepted; seven bad statuses and six
  bad priorities each a 422 that names the field and writes **nothing** (values,
  `field_versions`, `updated_at` and the `order.update` audit count unchanged);
  null `status` / `priority` a 422 that leaves the order **and `GET /orders`**
  readable (the poisoned-row regression); null for `vendor_id` / `description` /
  `category` a 422; unknown category a 422 with its code and nothing written, a
  known one accepted, an archived one still accepted; **another workspace's vendor
  refused 404 with the foreign name absent from the body and the order unchanged
  and still listed**, an unknown vendor a 404, a same-workspace vendor still fine;
  a frozen order answering `ORDER_LOCKED` before any reference check; a mixed
  `{status, notes}` PATCH refused whole; an omitted field untouched; create
  refusing an unknown priority / category cleanly and creating nothing. Run
  against the **unfixed source first (stashed): 27 of them fail**, and the 22 that
  pass there are the controls (valid values accepted, omitted fields untouched).
  Verified live over real HTTP against a migrated, seeded stack: every bad case
  above refused with nothing written and `GET /orders` still 200; valid changes
  still 200. (A first live attempt at the vendor case appeared to return 422 — that
  was malformed JSON from a shell variable capturing two lines, not the API; redone
  it showed the hole, which is why the check is worth trusting only when read
  twice.)
- **Known gaps, recorded — same shape, deliberately not fixed here.**
  - **The route commits before the response is validated.** That is *why* a
    response-model failure could poison a row, and it holds for every route in the
    app, not just this one. The five fields above can no longer trigger it here;
    closing the *class* means validating before `commit()`, a cross-cutting change.
    Other nullable columns that a response model types as non-null are worth
    auditing for the same poison. **Audited — see *Null-write audit* below**: one
    more real case (`PATCH /suppliers` `status`) and 32 raw 500s, all fixed; the
    "validate before `commit()`" half was deliberately **not** done.
  - ~~**`create_order` does not validate `project_id`**~~ **Closed — see *Small
    fixes: order `project_id` and the CV `ITEM_NOT_EMPTY` message* below.**
    (Found in review, then measured: `POST /orders` with another workspace's
    `project_id` was a raw 500, and **nothing persisted and nothing leaked** — an
    unvalidated-input 500, not an isolation break. `PatchOrderIn` does not accept
    `project_id` at all, so only create was exposed.)
  - **`PATCH` answers a bad `vendor_id` with `404`** (mirroring `create_order`'s
    `VENDOR_NOT_FOUND`, and what the user was told when asked), while the same
    handler answers an unknown `category` with `422`. A client keying on the bare
    status code cannot tell "vendor missing" from "order missing" — `OrdersClient`'s
    `fieldErrorMessage` maps every 404 to "Order not found". Harmless today because
    the UI has no vendor control, but a wart: on PATCH the path resource *does*
    exist, so `422` would be the tidier code. Left matching `create`.
  - **Reference checks re-validate an unchanged value**, so re-sending an order's
    *current* `vendor_id` / `category` is checked again. Only matters for data
    written through the old hole; the UI sends neither.
  - `CreateOrderIn.vendor_id` / `description` are required by the schema, so they
    have no null hole; `CreateOrderIn.status` does not exist (orders are created
    `Draft`).
  - The **legacy `/procurement/*`** namespace has its own order writes and was not
    touched.
  - An **archived category** can still be assigned (above).

## Comment threads on Modules and shop-drawing revisions (Plan V1 §29, migration `0043`) — shipped

> Chosen by the user ("Next task is comment threads for Task, Change, Component
> and Revision"). Two of the four had no entity and two were ambiguous, so the
> user was asked before any code was written; the four answers below are
> **settled decisions**, not assumptions. No spec or plan doc; this section is
> its written record. It extends *Comments, mentions and notifications* above,
> which records why v1 stopped at four object types.

- **Settled scope (user).**
  1. **Task and Change: skipped.** Neither is a table (grep of migrations
     `0001`–`0042` finds none; Q524 decided a `task` table nobody built, §11's
     change engine is unbuilt). Building either would mean inventing the entity,
     and Change has no defined shape outside that unbuilt engine. They get a
     thread when their entity exists — a nullable FK column + one `object_type`
     branch, as before.
  2. **Component = a Module** (`modules`, one level below a Joinery Item), not a
     Part. Parts number in the hundreds per item after a CV import and are rarely
     discussed one by one.
  3. **Revision = a shop-drawing revision** (`shop_drawing_revision`), not an
     estimate revision — §29's "approval discussions" and drawing references, and
     the approve / reject flow already exists to hang discussion on. An estimate
     revision has no thread.
  4. **Each type's own module governs its thread**, instead of `tracking` for
     all: a Module by `list`, a revision by `shop_dwgs`. See below — this is the
     one change that reaches back into the four original types' code.
- **Migration `0043`** — `comment.module_id` and `comment.revision_id`, both real
  FKs with `ON DELETE CASCADE`; `ck_comment_one_object` widened to exactly one of
  **six**; `object_type` regenerated (Postgres cannot alter a generation
  expression, so it is dropped and re-added — nothing depends on it, and
  `varchar(8)` still fits: `revision` is exactly 8). Downgrade deletes module /
  revision threads (they have no home in the `0042` shape) and restores it; the
  upgrade / downgrade / upgrade cycle was run on a database holding real rows.
  Not searchable (no `0033` trigger).
- **Per-type permissions** (`comments/queries.py`: `COMMENT_MODULE`,
  `READ_MODULES`). `comment` on the object's own module posts, edits and
  deletes; `read` on every module the thread links into reads it:

  | Type | `comment` | `read` |
  | --- | --- | --- |
  | project / area / room | `tracking` | `tracking` |
  | item | `tracking` | `tracking` + `list` |
  | **module** | **`list`** | **`list`** |
  | **revision** | **`shop_dwgs`** | **`shop_dwgs`** |

  The default roles differ from `tracking` in exactly the way that shows the gate
  works: `purchase_officer` holds `tracking:comment` but only `read` on `list` and
  `shop_dwgs`, so it can comment on an item and can read but not write a module
  or revision thread. Without this a user who cannot open a drawing could read
  the discussion about it — the leak class the item thread's `list:read` rule
  already exists to avoid. Mentions (`_readers`) and the inbox follow the same
  table, so a mention needs `read` on the object's own modules.
- **The routes no longer carry a fixed `require_permission("tracking", …)`.**
  Which module gates a comment depends on what it is a comment *on*, so the
  routes use `current_user` and check per type: `GET` and top-level `POST`
  know the type from the request; **`PATCH`, `DELETE` and a reply look the
  comment's type up first** (`queries.object_type_of`, workspace-scoped) and
  then check. Consequence: `PATCH`/`DELETE` on an unknown comment is now `404`
  for everyone, where a caller without `tracking:comment` used to get `403`
  first. The project comment-counts route is unchanged (`tracking:read`).
- **A reply now needs the read modules too — a tightening of existing
  behaviour, found while doing this.** A reply names no object, so the old route
  had no type to check and skipped the read check for it: a user holding
  `tracking:comment` but not `list:read` could reply to an item thread, although
  *Comments* above says the pair gates "reading and posting". The type now comes
  from the parent, so a reply to an item thread without `list:read` is `403`
  (pinned by `test_a_reply_on_an_item_thread_now_needs_list_read_too`). No
  default role is affected — every one holds both.
- **Joinery Items only, again.** A module of a related part has no thread (404):
  the thread's link opens the item editor. A revision has no such rule (a
  drawing belongs to a project, not an item).
- **Edit log.** A module comment writes `item_edit_log` against **the module's
  item** (`_comment_create`, `comment.{id}`, `_comment_delete`), per the PM
  Workbench invariant; a revision belongs to no item and writes `audit_log`
  only (`comment.*`, target `module:{id}` / `revision:{id}`).
- **Notifications.** `notifications/routes.py` now decides visibility **per
  object type** from `READ_MODULES` instead of "empty without `tracking:read`,
  item threads need `list:read`": a notification is shown while the recipient can
  read every module its thread links into. So a user holding `list:read` but no
  `tracking` at all now sees module notifications (before, the whole inbox was
  empty for them). `list_notifications` / `unread_count` take a `types` list in
  place of `include_items`. Links and labels:
  - module → `/items/{item_id}?tab=cutlist&module={module_id}`,
    label `M01 Base (#297871)`;
  - revision → `/shop-dwgs?project={pid}&drawing={did}&rev={rid}&comments=1`,
    label `Vanity plan · v1`.
- **Web.**
  - **Module** — the item editor's Cutlist tab shows the active module's thread
    under its parts (`data-testid="module-comments"`). The selection is now
    `?module=<id>` — a click sets state and the URL together, synchronously
    (`history.replaceState`), and a URL change that is not from a click (a
    notification followed while already on the page) is synced back into state,
    the same reasoning the Areas & Rooms card documents. **Fixed later: `+ Add
    module` was broken by this.** `ModuleTree` adds a module, calls
    `router.refresh()` and selects it in the same tick; `selectModule`'s
    `history.replaceState` then raced that refresh and the refreshed module list
    never arrived — the tab kept saying "Add a module to start the cutlist" (the
    API had returned 201; a manual reload showed the module). It shipped in the
    module-threads change unnoticed because nothing exercised adding a module.
    `selectModule` now leaves the URL alone for an id not yet in the item's list.
    Pinned by `cv_replace_comments.spec.ts`'s "adding a module shows it, selected,
    with its comment thread" — **confirmed to fail without the guard** (1 module
    where 2 are expected) and to pass with it.
    `EditorTabs` gained a `canCommentOnModule` prop (`list:comment`) beside
    `canComment` (`tracking:comment`, the item thread's).
  - **Revision** — `DrawingDrawer` gets a **collapsible** "Comments on vN" panel
    for the selected revision (`data-testid="revision-comments"`), collapsed by
    default so it never squeezes the PDF viewer; `?comments=1` (what the
    notification link carries) opens it on arrival. The drawer used to read
    `?rev=` only as its *initial* state, so a notification for another revision
    followed while the drawer was already open was ignored; it now follows the
    URL. `canComment` is `can(me, "shop_dwgs", "comment")`.
  - `CommentObjectType` / `NotificationOut.object_type` widened in
    `lib/comments-types.ts`. `NotificationBell` and `/notifications` needed no
    change: they render `url` and `object_label`.
- **Seed.** ALF-001's first item's first module gets a foreman comment, and the
  project's first non-archived shop-drawing revision (pending preferred) a
  manager comment — **no mentions**, so the seeded bell counts (Juno 1, Noa 2) are
  unchanged. Both are looked up rather than assumed, and dropped first so a
  re-run does not stack them (verified: two runs, one comment each).
- **RBAC — no matrix change.** `list:comment` and `shop_dwgs:comment` were
  already granted.
- **Tests.** `test_comments_module_revision.py` (29): both new types round-trip
  with replies; threads stay per-object across all six; the DB holds exactly one
  object and regenerates `object_type`; a related part's module has no thread;
  workspace isolation on every verb; cascade on module / revision delete; the
  `FOR KEY SHARE` lock for both; the default roles (purchase_officer, viewer,
  editor); a group with **only** `list` (or only `shop_dwgs`) can read and post,
  while **`tracking` alone cannot reach the thread**; `comment` without `read` is
  refused; edit and delete follow the comment's own module; replies gated on the
  parent's module (and the item-reply tightening); mentions need read on the
  object's modules; both notification links and labels; the inbox following each
  type's modules including "no `tracking` at all"; audit + edit log. **Eight of
  them were confirmed to fail** with `comments/routes.py` reverted to the fixed
  `tracking` gate (the other 21 pass there — the schema, queries and
  notifications are unchanged in that run — so they are controls, not gate
  tests). The 46 existing `test_comments.py` cases pass **unchanged** on the
  refactored routes. `tests/e2e/comments_module_revision.spec.ts` (4) was run
  against a live migrated, seeded stack: a drafter's module comment mentioning a
  manager and the manager's bell opening that module; a viewer reading but not
  posting to a module thread; a manager's revision comment mentioning a drafter
  and the drafter's bell opening the drawer with the panel expanded; a viewer
  reading but not posting to a revision thread. A same-page follow (notification
  for the item's *second* module while its first was selected) was checked
  separately and works with no reload; it is not a permanent spec because it
  needs an item with two modules, which only the seed's "SS Bench" has.
- **Known gaps, recorded.**
  - **Deleting a module deletes its thread — and a CV re-import with
    `?mode=replace` deletes the threads on every module of the item.** Both
    remove modules by `DELETE` (`parts/queries.py`, `cv/queries.py`; see the CV
    Import section), and a comment cascades with the module it is on. That follows from
    the user's choice of Module as Component with the cascade the migration
    documents — SET NULL would violate the exactly-one CHECK — but nothing warns
    about it: `cv.import.replace_wipe`'s audit payload lists the deleted module
    ids and not how many comments went with them. **CV re-import is now covered — see
    *Replace warns about the comments it deletes* in the CV Import section**: the
    wizard warns, and the count is on the commit response and both audit rows.
    **Deleting a single module is now covered too — see *Delete module asks
    first* below** (it also gained the UI control it never had).
  - ~~**No comment counts for modules or revisions.** The Areas & Rooms card has
    badges (`GET /projects/{pid}/comment-counts`); the module list and the
    revision history strip do not, so a thread is found by opening it (or by a
    mention). One count endpoint per parent would close it.~~ **Closed — see
    *Comment counts on modules and revisions* below** (by embedding the counts in
    payloads the screens already fetch, not by adding count endpoints).
  - **A module's thread is not shown on the Hardware or other item tabs**, only
    on Cutlist, and a revision's only in the drawer.
  - The same workspace-wide-grants ceiling as the other comment routes: a
    project-scoped `list` / `shop_dwgs` membership is not consulted.
  - An **estimate** revision still has no thread, and Component means Module, not
    Part — both are the user's settled scope, not oversights.
- **Out of scope (deferred):** Task and Change threads; Part and estimate-revision
  threads; ~~counts / badges on the module list and revision strip~~ (**built, see *Comment counts on modules and revisions***); everything the
  *Comments* section already defers (attachments, decisions, internal notes,
  discussion areas, §30's rules engine).

## Delete module asks first (Plan V1 §29 follow-up, no migration) — shipped

> Chosen by the user ("Next task is a warning before deleting a single module").
> It closed the last gap *Replace warns about the comments it deletes* left open,
> but the request assumed something that was not true: **there was no way to
> delete a module from the UI.** `DELETE /modules/{mid}` existed, `PM.deleteModule`
> was defined in `pm-fetch.ts`, and nothing called it (`ModuleTree` has no delete
> control). A warning needs something to warn before, so the user was asked before
> any code was written; the three answers below are **settled decisions**, not
> assumptions. No migration, no spec or plan doc; this section is its record.

- **Settled decisions (user).**
  1. **Scope: add a Delete module control and a confirm dialog** — the first way
     to delete a module from the UI, so this is a new capability, not only a
     warning.
  2. **Advisory only, not enforced by the API** — the same call as the CV
     re-import warning. `DELETE /modules/{mid}` keeps deleting exactly as before;
     the dialog is the safeguard.
  3. **The dialog names parts and comments**, not comments alone.
- **Backend — `apps/api/app/parts/`.**
  - `GET /modules/{mid}/delete-impact` → `{parts, live_comments}`. Read-only, gated
    `require_drafter()` — **the delete's own gate** (drafter / manager / admin) —
    and workspace-scoped through `_item_id_for_module` (Joinery Items only; another
    workspace's module and an unknown id are both 404). Declared beside the other
    `/modules/{mid}` routes; no path collides (`PATCH /modules/{mid}` and
    `POST /modules/{mid}/parts` differ by method / suffix).
  - **What is counted.** `parts` = part **rows** (the number a person sees in the
    grid), not the sum of their `qty`. `live_comments` = comments on the module
    with `deleted_at IS NULL`, **replies included** — the same rule as the CV
    replace warning. The cascade also removes soft-deleted rows, so the true row
    count can be higher.
  - **The count is recorded, not returned.** `delete_module` counts *before* the
    DELETE and writes `deleted_parts` and `deleted_comment_count` into the
    `module.delete` audit payload. The route still answers **`204` with no
    body**: changing it to `200` would change what existing API callers see, and
    the user chose "advisory, existing callers keep working". (The option offered
    to the user said the count would also be "returned"; that half was
    deliberately **not** done, for the reason above.)
- **Web — `cutlist/DeleteModuleDialog.tsx` + `CutlistTab.tsx`.** A **Delete
  module** button in a header row above the active module's parts grid
  (`data-testid="delete-module"`), shown to drafter / manager / admin only — the
  web mirrors `require_drafter`, the API decides. It opens a confirm dialog that
  reads `delete-impact` **fresh when it opens**: "This permanently deletes the
  module and its **3 parts** and **3 comments**. It can't be undone.", or "This
  module is empty." when both are 0. If the lookup fails it says "Couldn't check
  what this module contains…" instead of implying the module is empty. The
  Delete button stays disabled until the numbers (or the failure) are on screen,
  so the person always sees them first; Cancel and Escape close it. A `404` on
  delete (already gone elsewhere) counts as success.
  - **After a delete the tab refreshes and selects a neighbour in state — and
    deliberately leaves the URL alone.** `router.refresh()` followed by
    `history.replaceState` is the race that broke `+ Add module` (see *Comment
    threads on Modules…*); a stale `?module=<deleted id>` is harmless because
    `moduleFrom` only accepts ids still in the item. Deleting the last module
    returns to the empty state.
- **Tests.** Four new in `test_parts_routes.py`: the impact counts the module's
  parts and live comments only (replies counted, a soft-deleted comment and a
  sibling module's comment not); an empty module reads 0/0; the gate (editor and
  viewer 403, another workspace and an unknown id 404); and the delete writes the
  counts to the audit row, still answers 204 and cascades — **all four fail
  against the unfixed source** (the six existing parts tests pass as controls).
  `tests/e2e/module_delete.spec.ts` (4; 7 since the lock checks), run twice back to back against a live
  migrated, seeded stack: the full add → comment → warning → Cancel → Delete cycle
  on `JO-TP01` on a module the spec creates (so nothing seeded is deleted); the
  parts count on a seeded module (Cancel only); the lookup-failed message via a
  route intercept; and editor / viewer are not offered the button.
- **Known gaps, recorded.**
  - ~~A module can still be deleted on an item that is Hard-Locked,
    Approval-Locked or Controlled-Locked.~~ **Closed — see *Lock checks on module
    delete* below.**
  - The count is live comments only (above); an API caller who skips the
    lookup gets no warning at all — by the user's choice.
  - No undo: deletion is permanent, as it always was.
- **Out of scope (deferred):** enforcing an acknowledgement in the API; returning
  the counts in the DELETE response; a warning before deleting a **part** (a
  single row, nothing cascades from it).

## Lock checks on module delete (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on module delete"). It closes the
> gap *Delete module asks first* recorded, and it is the **first place §L's locks
> reach beyond `PATCH /items/{id}`**. The request left three things open, so the
> user was asked before any code was written; the three answers below are
> **settled decisions**, not assumptions. No migration, no spec or plan doc; this
> section is its written record.

- **Settled decisions (user).**
  1. **Scope: module delete only.** `POST /items/{id}/modules`, `PATCH /modules/{mid}`,
     every part write, hardware lines and CV import (including its `replace` mode,
     which deletes every module of the item) **still never consult a lock** — the
     recommended option, kept narrow on purpose. See *Known gaps*.
  2. **Hard + Approval + Controlled.** A delete cannot be held as a Controlled-Lock
     request (`item_lock_request` stores a `PatchItemIn` body, which can only carry
     field edits), so it is **refused** instead. Otherwise a lock could be bypassed
     by deleting where it forbids editing.
  3. **UI: disable with the reason, plus a 409 fallback.**
- **The rule — `items.queries.assert_item_content_unlocked`.** Called by
  `parts.queries.delete_module` right after the workspace lookup and *before*
  anything is counted, audited or deleted; raises `ItemContentLocked`, which
  `delete_module_route` turns into `409 {detail: {code, …}}`:
  - **`HARD_LOCKED`** (`locked_by`) — everyone, including the owner and admins.
  - **`APPROVAL_LOCKED`** — `items.status = 'APPROVED'`.
  - **`ITEM_LOCKED`** (`owner_id`, `owner_name`) — `item_locked` with someone else
    as `cutlist_owner_id`. **The owner and managers/admins pass**, matching who can
    decide a lock request. `cutlist_owner_id` is *sticky* (survives Unlock), so it
    is `item_locked` that matters: an owner with no active lock never blocks.
  - `HARD_LOCKED` / `APPROVAL_LOCKED` use the same codes and bodies as
    `PATCH /items/{id}`; `ITEM_LOCKED` is new (the PATCH path answers a Controlled
    Lock with `LOCK_REQUEST_CREATED` instead). The lookup takes the item row
    `FOR UPDATE`, so a lock set concurrently is seen or waits for the delete's
    transaction. A refused delete writes **nothing**: no audit row, no edit log.
  - `delete_module` now takes the acting `AuthUser` (`actor=`) instead of
    `actor_id=`, because the Controlled-Lock exemption needs the role. Its only
    caller is the route.
  - `GET /modules/{mid}/delete-impact` is **not** gated by any lock (read-only; the
    dialog can still be opened by someone who will then be refused).
- **Web — `cutlist/moduleLock.ts`.** `moduleLockReason(item, userId, role)` mirrors
  the rule from data the page already holds (`hard_locked_at`, `status`,
  `item_locked`, `cutlist_owner_id`); when it returns a reason, the **Delete
  module** button is `disabled` with the reason as its `title` **and** as a line
  in a notice at the top of the tab (`data-testid="cutlist-locked"` since the
  follow-up below moved it there from under the header row — a tooltip alone is
  invisible on a disabled button). `lockMessage(code, detail)` holds the wording
  for a code, shared with the dialog: a `409` on the delete (a stale page that
  still offered the button) shows that message in the dialog and leaves it open,
  nothing deleted. The client check only decides what to show — the API refuses
  regardless. **The client message for `ITEM_LOCKED` cannot name the owner**
  (`ItemOut` carries `cutlist_owner_id` but no name); the server's 409 does.
- **Tests.** Four new in `test_parts_routes.py`: a Hard Lock refuses everyone (an
  admin included), leaves module / parts / comments untouched and writes no audit
  row, then passes once cleared; an Approval Lock likewise until status moves off
  `APPROVED`; a Controlled Lock refuses a non-owner (naming the owner), leaves the
  impact lookup open, and lets a manager and the owner through; a sticky owner
  with no active lock does not block. **The first three fail against the unfixed
  source** (the sticky-owner one passes there — it is the control). Three new in
  `tests/e2e/module_delete.spec.ts`, each restoring the item exactly as seeded:
  a Hard Lock disables the button for a manager, with the reason, and unlocking
  re-enables it; seeded `JO-K-103` (Controlled-Locked, drafter-owned) is open to a
  manager, and after ownership is transferred to the manager the drafter is
  disabled — then transferred back and enabled again; and a mocked `409
  ITEM_LOCKED` shows the owner's name in the dialog. **All three fail against the
  unfixed web code.** Also checked over real HTTP through the proxy: a Hard-Locked
  item's delete answers `409 HARD_LOCKED` and the module is still there.
- **Known gaps, recorded.**
  - ~~Every other write under a locked item is still open.~~ **Closed for module
    and part writes and CV import — see *Lock checks on the other module and part
    writes* below; hardware lines — see *Lock checks on hardware lines*.**
  - ~~`PATCH /items/{id}/status` and `/lifecycle/{stage_key}` still never consult the
    lock.~~ **Closed for the Hard and Controlled locks — see *Lock checks on status
    and lifecycle* below.**
  - A Controlled Lock is not held as a request for a delete: the person is told to
    ask the owner or a manager. There is no "request a delete" flow.
  - The role check for the Controlled-Lock exemption is a hand-written
    `auth_role in (manager, admin)`, like `decide_lock_request`'s — Q472 is still
    not built.
- **Out of scope (deferred):** a lock-request flow for a delete; naming the lock
  owner in the disabled-button text.

## Lock checks on the other module and part writes (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on the other module and part
> writes"). It extends *Lock checks on module delete* above. The request left the
> reach open, so the user was asked before any code was written; the two answers
> below are **settled decisions**, not assumptions. The rule itself is the one the
> delete already settled (Hard + Approval + Controlled, refused because none of these
> can be held as a `PatchItemIn` request) and was carried over, not re-asked. No
> migration, no spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **Reach: the five module / part routes, plus CV import commit.** The routes
     are `POST /items/{id}/modules`, `PATCH /modules/{mid}`, `POST /modules/{mid}/parts`,
     `PATCH /parts/{pid}` and `DELETE /parts/{pid}` (with `DELETE /modules/{mid}`
     already covered). CV import was added because it writes modules and parts and
     its `replace` mode **deletes modules — which sidestepped the delete lock**.
     **Hardware lines were offered and not chosen**, so they still never consult a
     lock.
  2. **UI: one notice + controls disabled**, not per-control tooltips or 409
     messages alone.
- **Backend.** `parts.queries.{create_module, patch_module, create_part, patch_part,
  delete_part}` now take the acting `AuthUser` (`actor=`, was `actor_id=`) and call
  `items.queries.assert_item_content_unlocked` right after resolving the item — before
  anything is written, audited or logged; each route turns `ItemContentLocked` into
  the same `409 {detail: {code, …}}` the delete uses. An unknown id is still 404 (the
  lookup runs first). **A refused write changes and logs nothing** (pinned by
  comparing module / part rows, `item_edit_log` and `audit_log` counts before and
  after). **CV commit** checks in the route after the run is validated
  (404 / `RUN_NOT_PENDING` first) and before anything else, so a refused commit
  **leaves the run `preview`** and the same run commits once the lock is gone.
  Preview, `replace-impact` and the delete-impact lookup are read-only or write only
  the run row and are not gated. One consequence worth knowing: **part edits on an
  APPROVED item are refused** until its status moves off Approved (the Approval Lock
  read as Q508 says — "information locks when approved").
- **Web.** `moduleLockReason` now decides for the whole Cutlist tab, and
  `lockFromError(e)` reads a `409` lock refusal from either error shape in use
  (`ApiError.body` in pm-fetch, the CV helper's `detail`). `CutlistTab` shows one
  notice at the top (`data-testid="cutlist-locked"`, drafter / manager / admin only —
  the roles that can write) and disables **+ Add module**, **+ Add row**, every part
  cell (including the Paint select), **part delete**, **Import from CV** and
  **Delete module**. A `409` from a stale page shows the server's reason and **reverts**
  the edit: a refused cell edit restores its value, a refused add adds no row, a
  refused delete brings the row back. `PaintSelect` gained a `key` on its value so
  the rollback actually resets it (it kept its local state before). The wizard shows
  the reason when its commit is refused.
- **Tests.** `test_parts_routes.py` (+22): all five routes × Hard and Approval Lock
  (refused for the owner and an admin alike, nothing changed or logged, then the
  same request succeeds once cleared); all five × Controlled Lock (a non-owner
  refused naming the owner; the owner and a manager pass); a sticky owner with no
  active lock and an unlocked item do not block; unknown ids stay 404.
  `test_cv_routes.py` (+8): first import and `replace` × all three locks — 409, no
  module or part written, run still `preview`, then the same run commits once
  unlocked — plus the owner and a manager passing a Controlled Lock. **21 of the new
  cases fail against the unfixed source** (the rest are the controls: owner / manager
  passes, unlocked, sticky owner, 404s). `tests/e2e/cutlist_locks.spec.ts` (4): a Hard
  Lock disables every control for a manager, with the reason, and unlocking restores
  them; seeded `JO-K-103` (Controlled-Locked, drafter-owned) is open to a manager,
  and after ownership moves to the manager the drafter is disabled, then restored;
  a stale page reverts a refused edit / add / delete with the owner named; the CV
  wizard shows a refused commit's reason. **All four fail against the unfixed web
  code.** Each e2e test puts the item back exactly as seeded.
- **Known gaps, recorded.**
  - ~~Hardware lines still ignore every lock.~~ **Closed — see *Lock checks on
    hardware lines* below.**
  - ~~`PATCH /items/{id}/status` and `/lifecycle/{stage_key}` still never consult the
    lock.~~ **Closed for the Hard and Controlled locks — see *Lock checks on status
    and lifecycle* below.**
  - ~~**`CvImportDialog`'s `ITEM_NOT_EMPTY` branch looks dead**~~ **Closed — see
    *Small fixes: order `project_id` and the CV `ITEM_NOT_EMPTY` message* below.**
    (It read `e.detail.code`, but `cv-fetch.ts` keeps the whole parsed body
    `{detail: {code}}` in `e.detail`, so the friendly message never showed and the
    person saw `commitCvImport: 409`.)
  - **The notice is hidden from read-only roles**, while their controls are disabled
    too — a viewer on a locked item sees disabled controls and the lock banner above
    the page, not the cutlist notice.
  - The same hand-written `auth_role in (manager, admin)` Controlled-Lock exemption,
    and no "request a change" flow for a refused write — Q472 is still not built.
- **Out of scope (deferred):** a request flow for a refused module / part write; guarding the CV `preview` (it writes only a run row).

## Lock checks on hardware lines (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on hardware lines") — the gap
> *Lock checks on the other module and part writes* left as "offered and not chosen".
> Both questions it would have raised were already settled by the two rounds before
> it, so **nothing was re-asked**: the rule is the same `assert_item_content_unlocked`
> (Hard + Approval + Controlled, refused because none can be held as a `PatchItemIn`
> request) and the UI is the same "one notice + controls disabled". No migration, no
> spec or plan doc; this section is its written record.

- **Backend.** `hardware_lines.queries.{create_hardware_line, patch_hardware_line,
  delete_hardware_line}` take the acting `AuthUser` (`actor=`, was `actor_id=`) and check
  the lock right after resolving the item, before anything is written, audited or
  logged; the three routes (`POST /items/{id}/hardware_lines`, `PATCH` and `DELETE
  /hardware_lines/{lid}`) turn `ItemContentLocked` into the same `409 {detail: {code,
  …}}` the module / part routes use. Unknown ids stay 404. **A refused write changes
  and logs nothing.** Deleting a line also **cascades its procurement allocations**
  (`batch_allocations`, `ON DELETE CASCADE`), which is one more reason the delete is
  refused rather than allowed. The Approval Lock consequence is the same as for parts:
  hardware edits on an APPROVED item are refused until its status moves off Approved.
- **Deliberately not locked: the project catalog.** `POST` / `DELETE
  /projects/{pid}/hardware_catalog` (and the Pantry's **+ Add from global**) belong to
  the **project**, not to an item, so no item's lock can govern them; a catalog row
  is shared by every item of the project. Pinned by
  `test_project_catalog_writes_are_not_governed_by_an_items_lock` (a Hard-Locked item
  does not stop a catalog add, and `DELETE` of a row still 409s only because a line
  references it). *This is an assumption made while building, not a user decision* —
  the alternative (locking a project's catalog while any of its items is locked) has
  no owner to name and would be new functionality.
- **Estimate Convert is unaffected.** `estimating.convert_to_project` inserts hardware
  lines for **brand-new** items it has just created, so there is no lock to consult.
- **Web.** `HardwareTab` now takes `currentUserId` / `currentUserRole` (threaded from
  `EditorTabs`) and reuses `moduleLockReason` / `lockFromError` from
  `cutlist/moduleLock.ts` — the file is named for modules but now serves the whole item
  editor, and its wording changed to "cutlist or hardware"; it was **not renamed**, to
  keep the diff to what the task needs. One notice at the top (`data-testid=
  "hardware-locked"`, drafter / manager / admin only, the roles that can write) and the
  Pantry's **+**, the Cart's quantity steppers, note field and **Remove** are disabled.
  A `409` from a stale page shows the server's reason and **reverts** the edit (the note
  and quantity roll back, a refused add adds no line, a refused remove brings the line
  back). **+ Add from global** stays enabled (project catalog, above).
- **Tests.** `test_hardware_lines_routes.py` (+15): all three routes × Hard and Approval
  Lock (refused for the owner and an admin alike, nothing changed or logged, then the same
  request succeeds once cleared); all three × Controlled Lock (a non-owner refused naming
  the owner; the owner and a manager pass); an unlocked item and a sticky owner do not
  block; unknown ids stay 404; the project catalog is not governed by an item's lock.
  **9 of the new cases fail against the unfixed source** (the rest are controls).
  `tests/e2e/hardware_locks.spec.ts` (3): a Hard Lock disables every hardware control for
  a manager, with the reason (and leaves **+ Add from global** on), unlocking restores
  them; seeded `JO-K-103` (Controlled-Locked, drafter-owned) is open to a manager, and
  after ownership moves to the manager the drafter is disabled, then restored; a stale
  page reverts a refused note / add / remove with the owner named. **All three fail
  against the unfixed web code.** Each puts the item back exactly as seeded.
- **Known gaps, recorded.**
  - **Locks now cover the whole item editor's writes to an item's cutlist and hardware,
    but not everything on an item**: `PATCH /items/{id}/status` and `/lifecycle/
    {stage_key}` **now consult it too (Hard and Controlled — see *Lock checks on status
    and lifecycle* below)**, and **attachments and the document register now do too
    (see *Lock checks on attachments and the document register* below)**, but the
    other item-scoped writes — queries, QC records, comments and material takes — do
    not. None was asked for; whether any of them should follow is a product question
    (a comment on an approved item, for instance, is probably meant to stay possible).
  - No "request a change" flow for a refused write, and the same hand-written
    `auth_role in (manager, admin)` Controlled-Lock exemption — Q472 is still not built.
  - `moduleLock.ts` is named for modules but serves hardware too (above).
- **Out of scope (deferred):** locks on the other item-scoped writes named above; a
  request flow for a refused write; locking the project catalog.

## Shop Drawings register redesign (migration `0044`) — shipped

> Chosen by the user: "use https://tgsdr.com/ as reference for the shop drawing",
> then screenshots of the customer's own **Tg Register** (the site itself is
> blocked by the environment's egress proxy, so the screenshots are the only
> reference seen). The request was under-specified, so the user was asked before
> any code was written; the answers below are **settled decisions**, not
> assumptions. It supersedes the *web* half of *Shop Drawings + File-Upload
> Subsystem (#5a)* (the card grid + drawer); that section's backend, workflow and
> RBAC still stand. No spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **Layout + new fields, not a new workflow.** The four revision statuses
     (`draft / pending / approved / rejected`), the not-uploader rule and the
     in-flight index are untouched. Tg's own statuses are shown as **queues
     derived from them** (below), never stored.
  2. **Keep our light design tokens.** Nothing was added to `globals.css`; the
     Tg screenshots are dark navy and that was declined. Existing tokens only
     (`h-good/warn/bad/info/accent-soft`, with `/15` tints for chips).
  3. **Four screens:** register table, full-screen viewer, details panel, left
     queue rail.
  4. **Replaces `/shop-dwgs` in place.** Old links still land somewhere sensible:
     `?subtab=current|in_review|archive` map to the Completed / Internal Review /
     Archive queues (`page.tsx::LEGACY_SUBTAB`).
  5. **No link to Joinery Items.** `joinery_id` is free text; drawings are still
     project-scoped and unlinked to items (the gap Q497 waits on).
- **Migration `0044`** — additive columns on `shop_drawing`: `drawing_no`,
  `type` (`IFA | IFC`, default `IFA`), `level`, `joinery_id`, `zone`, `room_no`,
  `assigned_to` (FK `app_user`), `due_date`, `submitted_at`; `UNIQUE (project_id,
  drawing_no)`. **`drawing_no` is nullable on purpose**: the seed and ~10 test
  fixtures INSERT drawings with raw SQL, and the API allocates the number on
  create. It reads `{project_code}-{seq:03d}` (`COLES-001`) from
  `workspace_counter` name `sd:{project_id}` — the first real caller of
  `counters.next_value` — never `MAX+1`. Existing rows are numbered per project in
  `drawing_id` order and the counters advanced past them. **`type` allows only
  IFA / IFC** (the two in the screenshots); a third value needs a migration.
- **Queues are derived, not stored** (`shop_drawings/schemas.py::Queue`): the
  drawing's **latest revision** decides — `being_drawn` (draft),
  `internal_review` (pending), `update_required` (rejected), `completed`
  (approved) — and `awaiting_submission` (approved, no `submitted_at`),
  `submitted` (`submitted_at` set) and `archive` (`archived_at` set) are filters
  over those. They overlap by design (a submitted drawing is also completed), so
  the per-queue counts do **not** sum to the total. `GET
  /projects/{pid}/shop-drawings` gained `queue=`, `assigned_to=` and `queues`
  (project-wide counts, unaffected by the room / search filters);
  `?subtab=` still works and `queue` overrides it. `q` now also matches
  `drawing_no` and `joinery_id`. Each card carries its `queue` and a
  `comment_count` (live comments on any of its revisions).
- **New endpoint** `GET /shop-drawings/{did}/history` (`shop_dwgs:read`) — the
  drawing's `shop_drawing.*` audit rows, newest first. The details panel's
  **Status History** tab shows the create / revision / archive events and
  **Audit Log** shows all of them, including field edits.
- **Editing** stays the existing rule — creator or manager / admin
  (`PATCH /shop-drawings/{id}`, 403 otherwise) — and now covers every register
  field plus `submitted_at`. `assigned_to` is **validated against the caller's
  workspace** (422; an unchecked FK would leak a foreign user's name through the
  `full_name` join — the `cut_schedule.assigned_to` lesson), an explicit `null`
  for `title` / `type` is a 422 (both NOT NULL), and audit payload dates are
  ISO strings. The web hides the inputs for anyone else; the API decides.
- **Web** — `shop-dwgs/_components/`: `RegisterTable` (sortable, blanks last
  either way, client-side paging at 25, an "Overdue" tag when `due_date` is past
  and the drawing is not completed / archived), `QueueRail` (progress donut, "My
  drawings" = `assigned_to = me`, one entry per queue), `DetailsPanel` (docked to
  the right of the table; commit-on-blur fields that resync and skip unchanged
  values; Revisions / Notes / Attachments / Status History / Audit Log tabs; the
  revision comment thread keeps `data-testid="revision-comments"` and its
  collapsed-by-default toggle), `DrawingViewer` (full screen, `?viewer=1`; zoom /
  Fit / download, a versions list, the revision's comment thread as
  *Communication*, drawing info and the review actions). Removed as orphaned:
  `DrawingCard`, `DrawingDrawer`, `SubtabStrip`, `BlueprintPlaceholder`,
  `VersionChip`, `RevisionHistoryStrip`. **URL state**: `project`, `queue`,
  `mine`, `room`, `q`, `drawing`, `rev`, `viewer`, `comments`. The notification
  link (`…&drawing=&rev=&comments=1`) still opens the details panel with the
  thread expanded.
- **Deliberately not built, and why.** *An in-app page counter and page
  thumbnail strip* in the viewer — they need a PDF renderer (pdf.js) the app does
  not ship. The viewer embeds the browser's own PDF viewer (zoom via `#zoom=`),
  so in Chrome its built-in toolbar already shows a page counter and thumbnails
  (seen in the verification screenshot); other browsers differ. Images use CSS
  scaling and have no pages.
  *Annotate* and *Coordinator references* (the screenshots' viewer) have nothing
  behind them here. *Bulk row selection*. The **Attachments tab lists each
  revision's file**: a drawing has no other attachments. *"Upload drawing" is now
  hidden without `shop_dwgs:write`* (it was shown to everyone and 403'd).
- **Seed.** ALF-001's six drawings get numbers `ALF-001-001…006` (counter reset
  with the drawings on re-run), a type, level, Joinery ID, an assignee and
  due / submitted dates **relative to today** so the overdue flag is right
  whenever the seed runs: *Kitchen island* is an overdue draft; *Bathroom vanity*
  is approved and submitted; *Hallway storage* is approved and awaiting
  submission.
- **Search** — a drawing's `drawing_no` and `joinery_id` are now search codes
  (`app/search/documents.py`).
- **Tests.** `test_shop_drawings_register.py` (9): sequential numbering,
  round-trip, bad `type` 422, foreign `assigned_to` 422 on create *and* patch
  (nothing written), patch + audit + null-title 422, every queue's membership and
  the counts, search / assigned filters, comment count, history 404. The existing
  47 shop-drawing / search-document tests pass unchanged.
  `tests/e2e/shop_drawings.spec.ts` (+3): the register columns, queue filter
  (URL + reload), overdue flag and sort; details panel → viewer → zoom → back; a
  viewer sees the details read-only. Both existing specs were kept and only the
  drawer's `#SD-` click became a register-row click
  (`comments_module_revision.spec.ts`). The new e2e tests are read-only against
  the seed, so they re-run without re-seeding.
- **Known gaps, recorded.**
  - The queue counts are computed per project; there is no cross-project
    "My Drawings" number (the count next to the rail's toggle is on/off, not a
    total).
  - Sorting and paging are client-side over the whole project's list, which is
    fine for hundreds of drawings and is the thing to revisit at thousands.
  - Rev shows the revision **number** (`v3`), not Tg's letters (`A`, `B`).
  - `type`, `level`, `zone` and `room_no` are not searchable filters yet, only
    `q` over title / number / Joinery ID.
- **Out of scope (deferred):** linking a drawing to a Joinery Item; Tg's own
  status names as stored states; a dark theme; pdf.js page navigation.

## Lock checks on status and lifecycle (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on status and lifecycle"). It closes
> the gap every earlier lock round recorded as "unchanged §L scope". The request
> collided with a rule already in this file, so the user was asked before any code was
> written; the four answers below are **settled decisions**, not assumptions. No
> migration, no spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **The Approval Lock applies to neither route.** It is derived from
     `status = 'APPROVED'`, and changing status is the documented way to clear it
     (*Locking + Concurrency*; `ApprovalLockBanner`), so gating `/status` on it would make
     an approved item impossible to unlock. Lifecycle was decided the same way, because
     approval (drawings signed off) is exactly when production dates start being recorded.
     Hard and Controlled gate both routes.
  2. **Bulk status skips locked items and lists them**, rather than refusing the whole
     batch — the pattern `not_found` / `cross_workspace` already set.
  3. **Shop Floor's fan-out is not gated.** Completing a stage writes `item_stages.done_date`
     onto every linked item (Q439); that is the system projecting a cutlist-level fact, like
     `sync_orders_for_item` rewriting CUTLIST NO., not a person editing the item.
  4. **Same Controlled-Lock rule as the other writes** — the owner and managers/admins
     pass; anyone else, foremen (`editor`) included, is refused.
- **Backend.** `items.queries.assert_item_content_unlocked` gained
  `include_approval: bool = True`; status and lifecycle pass `False`, so the check is the
  Hard Lock and someone else's Controlled Lock only (codes `HARD_LOCKED`, `ITEM_LOCKED`,
  same bodies as the other routes). `patch_item_status`, `bulk_patch_item_status` and
  `patch_lifecycle` take the acting `AuthUser` (`actor=`, was `actor_id=`) and check right
  after resolving the item, **before anything is written, audited or logged**; the two
  single-item routes turn `ItemContentLocked` into `409 {detail: {code, …}}`. Unknown ids
  stay 404, and an invalid `stage_key` is still `400` (validated before any lock).
  `POST /items/bulk-status` answers `200` with a new **additive** field
  `locked: [{item_id, code, owner_name}]`; skipped items get no status-log, audit or edit-log
  row, and everything else in the batch is applied.
- **A Hard Lock beats the Approval state**: a hard-locked APPROVED item answers
  `HARD_LOCKED` on these routes, not a pass.
- **Web.** `cutlist/moduleLock.ts` gained a `LockScope` (`"content"` | `"status"`) on
  `moduleLockReason` / `lockMessage` / `lockFromError`; `"status"` leaves the Approval Lock
  out and words the Hard Lock as "before its status or stage dates can be changed". The
  Actions tab shows one notice (`data-testid="actions-locked"`, drafter / editor / manager /
  admin only — the roles that can act) and disables **Set status** and **Mark REQ done**.
  `StatusPopup` takes optional `currentUserId` / `currentUserRole` (passed by both callers):
  with them it shows the reason up front (`data-testid="status-locked"`) and disables
  **Update Current Item**; a `409` from a stale page shows the server's reason and keeps the
  dialog open. `BulkStatusDialog`'s response type gained `locked`, and Tracking's banner reads
  "N updated · M skipped (locked: #12, #14)".
- **Tests.** `test_status_lifecycle_locks.py` (13): Hard Lock refuses everyone (an admin
  included) on both routes, nothing changed or logged, then the same request succeeds once
  cleared; Controlled Lock refuses a non-owner and a foreman, naming the owner, while the
  owner and a manager pass; unlocked and sticky-owner items don't block; **the Approval Lock
  does not stop a status change (and audits `item.approval_unlock`) or a lifecycle date**; a
  Hard Lock wins over an approved item; unknown ids 404 and a bad stage key 400; bulk skips
  Hard / Controlled items and lists them while updating the rest (including an APPROVED item),
  a manager and the owner pass, and an unlocked batch reports `locked: []`. **Eight fail against
  the unfixed source**; the other five are controls. `tests/e2e/status_locks.spec.ts` (5) ran
  against a live migrated, seeded stack: a Hard Lock disables both Actions for a manager and
  unlocking restores them; seeded Controlled-Locked `JO-K-103` is open to a manager and, once
  ownership moves to the manager, disabled for the drafter — then restored; **an APPROVED item
  keeps both Actions and the status dialog usable and can be moved off Approved**; a stale page
  shows the owner's name for a refused status and a refused date; a mocked bulk response with a
  skipped item reads in the banner. **Four fail against the unfixed web code** (the Approval Lock
  one is the control). Each test puts the item back exactly as seeded.
- **Known gaps, recorded.**
  - **A Hard Lock can still receive a date from Shop Floor** — completing a stage on the item's
    cutlist writes `item_stages.done_date` regardless (decision 3). Only the manual lifecycle route
    is refused, so Tracking and the item's own lock can disagree until it is unlocked.
  - **A foreman is refused on a drafter's Controlled Lock** (decision 4). Marking a stage date
    for an item a drafter has claimed needs the drafter or a manager — the same friction the
    module / part / hardware writes already have, now reaching the two things foremen actually do.
  - No "request a change" flow for a refused status or date; the Controlled-Lock exemption is
    still a hand-written `auth_role in (manager, admin)` check (Q472 not built).
  - Still not lock-checked: item queries, QC records, comments and material takes (none
    asked for; a comment on an approved item should probably stay possible). Attachments
    and the document register **are now — see *Lock checks on attachments and the document
    register* below.**
  - `moduleLock.ts` is named for modules but now serves hardware, status and stage dates.
- **Out of scope (deferred):** gating Shop Floor's fan-out; the Approval Lock on either route;
  a request flow for a refused write; the other item-scoped writes named above.

## Lock checks on attachments and the document register (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on attachments and the document
> register") — the gap *Lock checks on hardware lines* and *Lock checks on status and
> lifecycle* both recorded as "not asked for". The one open decision — whether the
> Approval Lock applies — was asked before any code was written, and is a **settled
> decision**, not an assumption. Everything else was settled by the earlier lock rounds
> and carried over. No migration, no spec or plan doc; this section is its written record.

- **Settled decision (user).** **Hard + Approval + Controlled, for both.** Unlike status and
  lifecycle (where status *is* the unlock lever), attachments and the register are plain
  information, so the same rule as the cutlist and hardware writes applies: an approved item's
  whole information set locks together (Q508 — "information locks when approved"). To replace a
  floor plan or add a register document on an approved item, move its status off Approved first.
  The alternatives offered — attachments only, or neither — were declined.
- **What is gated.** All five writes, each refused with `409 {detail: {code, …}}` (`HARD_LOCKED`,
  `APPROVAL_LOCKED`, `ITEM_LOCKED` — the same codes and bodies as the other routes):
  `POST` / `DELETE /items/{iid}/attachments/{kind}` and `POST /items/{iid}/documents`,
  `PATCH` / `DELETE /documents/{did}`. **Relabelling and reordering a register document is a change
  too** and is refused like the rest (an assumption made while building — the register has no web UI
  to show the question, and a Hard Lock means "cannot change"). Reads (`GET` bundle, `GET` register,
  the print routes) are never gated.
- **Backend.** `item_attachments.queries.{bind_attachment, clear_attachment}` and
  `item_documents.queries.{bind_document, patch_document, unbind_document}` take the acting
  `AuthUser` (`actor=`, was `actor_id=`) and call `items.queries.assert_item_content_unlocked` right
  after resolving the item — **before** the blob is validated, and before anything is written,
  audited or logged; the routes turn `ItemContentLocked` into the 409. Unknown ids stay 404: the
  lookup runs first, and `clear_attachment` on an unknown item finds nothing to lock and falls
  through to its 404. So a locked item with a bad mime answers `409`, not `415`. **A refused write
  changes and logs nothing** (pinned by comparing slot rows, register rows, `item_edit_log` and
  `audit_log` counts before and after). `patch_document` / `unbind_document` resolve the document's
  item from the document, so a lock on *that* item governs it.
- **Not gated, deliberately: `POST /files`.** Uploading a blob belongs to the workspace, not to an
  item, so no item's lock can govern it (the same reason the project hardware catalog stayed open). A
  refused bind therefore leaves an unreferenced `file_blob` behind — exactly like every other
  abandoned upload, and there is still no orphan GC. *An assumption made while building.*
- **The register had no web UI when this shipped** (its rule was covered by pytest alone) — **it has one
  now, see *Document Register web UI* below.**
- **Web.** `AttachmentsTab` takes `item` and `currentUserId` (threaded from `EditorTabs`) and shows one
  notice (`data-testid="attachments-locked"`, drafter / manager / admin only — the roles the tab already
  lets write); `AttachmentSlotCard` disables **Upload / Replace** and **Delete** with the reason as
  `title`, and a refusal from a stale page shows the server's reason. `lib/attachments-fetch.ts`
  errors now carry `status` and `body` (they used to throw a bare message, so a 409 read
  "[object Object]" or "clear failed: 409" and `lockFromError` had nothing to read). `moduleLock.ts`'s
  `"content"` wording now says "cutlist, hardware or attachments".
- **Seed.** `seed/hartwood_joinery.py` builds an `AuthUser` for the drafter to call `bind_document`
  (it now needs an actor); verified by running the whole seed against a fresh migrated database — the
  "2 item documents" line still prints. Nothing new is seeded: as with the other locks, a seeded lock
  would risk the fixed e2e suite.
- **Tests.** `test_attachments_documents_locks.py` (30): all five writes × Hard and Approval Lock
  (refused for a drafter and an admin alike, nothing changed or logged, then the same request succeeds
  once cleared); all five × Controlled Lock (a non-owner refused naming the owner; the owner passes; a
  manager passes); an editor refused on the three register writes (`list:write` alone gates them, so
  editors may write it); an unlocked item and a sticky owner do not block; reads are never gated;
  unknown ids stay 404 under a Hard Lock. **18 fail against the unfixed source**; the other 12 are
  controls. `test_item_attachments_crud.py` was updated in place for `actor=`.
  `tests/e2e/attachments_locks.spec.ts` (4) ran against a live migrated, seeded stack: a Hard Lock
  disables every slot control for a manager, with the reason, and unlocking restores them; seeded
  Controlled-Locked `JO-K-103` is open to a manager and, once ownership moves to the manager, disabled
  for the drafter — then restored; an approved item disables them until status moves off Approved; a
  stale page shows the owner's name for a refused delete and a refused upload. **All four fail against
  the unfixed web code.** Each puts the item back exactly as seeded. (The stale-page test uploads a
  small PDF through the real `/files` before the mocked bind is refused, leaving one deduplicated blob.)
- **Known gaps, recorded.**
  - Still not lock-checked: item queries, QC records, comments and material takes (none asked for).
  - No "request a change" flow for a refused write; the Controlled-Lock exemption is still a
    hand-written `auth_role in (manager, admin)` check (Q472 not built).
  - A refused bind leaves an unreferenced blob (above); the Combined PDF and print routes read
    whatever the slots hold and never consult a lock.
  - `moduleLock.ts` is named for modules but now serves hardware, status, stage dates and attachments.
- **Out of scope (deferred):** ~~a web UI for the Document Register~~ (**built, see below**); gating `POST /files`; a request flow
  for a refused write; the other item-scoped writes named above.

## Small fixes: order `project_id` and the CV `ITEM_NOT_EMPTY` message (no migration) — shipped

> Chosen by the user ("go with the next recommendation tasks" — the first item of the
> recommendation, a small bug-fix change with two items). Both were **already recorded
> here as known gaps** (*Order field validation* and *Lock checks on the other module and
> part writes*) after being found and measured, and neither needed a decision: the fix in
> each case was the behaviour the surrounding code already promised. No migration, no spec
> or plan doc; this section is its written record.

- **`POST /orders` validates an explicit `project_id`.** `orders.queries._project_in_workspace`
  (the sibling of `_vendor_in_workspace`) is checked in `create_order` after the vendor and
  category checks; an unknown **or another workspace's** project answers
  `404 {code: "PROJECT_NOT_FOUND", project_id}` — the create route's own `VENDOR_NOT_FOUND` /
  `ITEM_NOT_FOUND` precedent, so a client sees one shape for "the thing you named is not
  yours". *That the code is a 404 rather than a 422 is the precedent, not a fresh decision.*
  Nothing is created, and the foreign project's name never appears in the response. Not checked,
  because already safe: an item-derived project (resolved through the item's own workspace join)
  and no project at all (Q554's project-less order, which reaches its workspace through its
  vendor). **The check order is now vendor → category → project → item.**
- **The CV wizard's `ITEM_NOT_EMPTY` message now shows.** `CvImportDialog` read
  `e.detail.code`; the body FastAPI sends is `{detail: {code}}` and `cv-fetch.ts` keeps all of it
  on `e.detail`, so the code sits at `e.detail.detail.code` (the shape `lockFromError` already
  reads). One line. It is reachable when the page went stale — someone else added modules after
  the wizard opened, since the Replace checkbox is only offered when the item already has modules.
- **Tests.** `test_order_routes.py` (+5): another workspace's project refused 404 with the foreign
  name absent, nothing created and the list still empty; an unknown project refused; this
  workspace's project still creates; no project and the item-derived project still create; an
  unknown vendor still answers first. **The two refusal tests fail against the unfixed source**
  (they surfaced the raw `IntegrityError`); the other three are controls. `cv_import.spec.ts` (+1)
  mocks the API's exact 409 body and asserts the friendly message appears and `commitCvImport: 409`
  does not — **it fails against the unfixed web code** and passes with the fix.
- **Found while verifying, not fixed: `cv_import.spec.ts`'s existing test is racy in dev mode.**
  It clicks the row's `/items/…` link the instant the row is visible; against a freshly started
  `next dev` the page is not yet hydrated, the click does nothing, and the test times out on the
  URL assertion (a diagnostic run with a 3 s pause before the click navigates fine). The new test
  reads the `href` and `goto`s it, as the lock specs do; the old one was left alone (it fails
  before reaching any code this change touches). e2e is not part of CI (which runs pytest + `tsc`).
- **Known gaps, recorded.** `PATCH /orders/{id}` still answers a bad `vendor_id` with `404` while an
  unknown `category` is a `422` (unchanged, noted under *Order field validation*).

## Document Register web UI (no migration, no API change) — shipped

> Chosen by the user ("go with the next recommendation tasks"): the gap *Lock checks on
> attachments and the document register* and *Item & Project Detail 2.0* both recorded as "the
> register has no web UI". Two things were open, so the user was asked before any code was written;
> the answers are **settled decisions**, not assumptions. Web only — `item_documents/` is unchanged.

- **Settled decisions (user).**
  1. **Placement: a "Document register" section on the item editor's Attachments tab**, below the five
     named slots — not a new tab, not the Tracking modal. `ItemDetailModal`'s "No documents attached for
     v1." placeholder is therefore **still there and still untrue**; it was not touched (not chosen).
  2. **Write controls follow the API: `list:write` — drafter, manager, admin and editor.** That is one
     role wider than the attachment slots on the same tab (drafter / manager / admin), so the tab now
     holds two writer sets (`WRITER_ROLES`, `REGISTER_WRITER_ROLES` in `AttachmentsTab.tsx`). The web
     mirrors the role set; the API decides.
- **Web.** `DocumentRegister.tsx` (`items/[id]/_components/`) + `lib/item-documents-fetch.ts` (errors carry
  `status` / `body`, as `attachments-fetch.ts` does, so `lockFromError` can word a 409). One row per
  document: label (commit-on-blur / Enter, resyncs to the server's value and **skips an unchanged blur** so a
  tab-through writes no audit row; a refused save puts the server's label back), filename · size · uploader ·
  date, **Open**, **↑ / ↓**, **Remove** (confirm). **Add document** uploads through `/files` then binds
  (PDF / PNG / JPEG picker hint; the API's 415 is the gate) and **appends** after the highest `sort_order`.
  - **Reorder renumbers the whole list.** New documents default to `sort_order = 0`, so ties are the normal
    case and swapping two values would do nothing. A move renumbers `0..n-1` and PATCHes only the rows whose
    number changed — up to N sequential PATCHes, each an `item.document.update` audit row and each checking
    the lock. Not atomic: a failure part-way leaves a partly renumbered list (the list is re-fetched, so the
    screen shows the truth).
  - **One lock notice for the tab.** `AttachmentsTab` now decides the lock reason for either writer set and
    shows a single `attachments-locked` notice, so an **editor** (register writer, not slot writer) sees the
    reason too; the slot cards and the register each get the reason only when their own writer set applies.
    Same rule as everywhere (`moduleLockReason`: Hard + Approval + Controlled), so **relabelling and
    reordering on an APPROVED item are disabled**, matching the API. Controls are disabled with the reason as
    `title`; a `409` from a stale page shows the server's reason. The reason wording still says "cutlist,
    hardware or attachments" — it does not name the register.
  - Read-only roles get the list and **Open**, no inputs, no buttons. The register lists Joinery Items only,
    like the API (a related part's editor never reaches this tab).
- **Tests.** `tests/e2e/document_register.spec.ts` (5), run against a live migrated, seeded stack and
  re-run six-plus times: a drafter adds, relabels, reorders and removes (and an unchanged blur writes
  nothing); an editor can add while the slot **Upload / Replace** buttons are absent, a viewer only reads;
  a Hard Lock disables every control for a manager with the reason; another user's Controlled Lock disables
  an editor's and shows them the notice; a stale page shows the owner's name for a refused relabel / remove /
  add and puts the label back. **All five fail without the `AttachmentsTab` wiring.** Each test leaves the
  item as seeded — including every seeded document's `sort_order`, which a reorder would otherwise leave
  renumbered. `attachments_locks.spec.ts` and `item_project_detail.spec.ts` still pass. No backend test was
  needed or added: the routes are unchanged and already covered by `test_item_documents.py` and
  `test_attachments_documents_locks.py`.
- **Found while testing — a test bug that destroyed seed data.** The first draft removed `rows.last()` right
  after an upload. The page still showed a row the spec had just deleted through the API, so the row count
  matched instantly and the click landed on a stale row — the seeded second document. The spec now reloads
  first and targets the new row by filename. Worth remembering: a count assertion is satisfied by stale rows.
- **Known flake, not the feature.** About one full-spec run in ten failed with `apiRequestContext.post: read
  ECONNRESET` on the Hard Lock test's `POST /api/items/{id}/hard-lock` through `next dev`'s proxy; the same
  call passes on retry. `attachments_locks.spec.ts` makes the same call and is exposed to it too.
- **Known gaps, recorded.**
  - ~~`ItemDetailModal` (Tracking) still shows the "No documents attached for v1." placeholder.~~ **Closed —
    see *Tracking modal shows the register and the SketchUp / CabVision slots* below.**
  - Labels only — a register document has no other metadata, and a rename cannot be undone except by typing
    the old one back.
  - A refused bind leaves an unreferenced `file_blob` (as for attachments; `POST /files` is not gated).
  - The reorder controls are per-row buttons, not drag-and-drop.
- **Out of scope (deferred):** ~~register UI outside the item editor (the Tracking modal)~~ (**built, see below**); drag-and-drop;
  bulk upload; document categories or types.

## Tracking modal shows the register and the SketchUp / CabVision slots (no migration, no API change) — shipped

> Chosen by the user ("Go with option 1", from the list of candidates after the Document Register UI).
> Two things were open, so the user was asked before any code was written; both answers are **settled
> decisions**. Web only.

- **Settled decisions (user).**
  1. **Read-only.** The modal lists the register's documents with an **Open** link each and a
     "Manage on Attachments tab →" link to `/items/{id}?tab=attachments`, where editing (and its lock and
     writer-role rules) already lives. No inputs and no buttons in the modal's register.
  2. **Fill in the SketchUp / CabVision rows too** — the user chose this over leaving them as recorded-stale.
     They had been hard-coded to a dash since `0036` made both slots real.
- **Web — `tracking/_components/ItemDetailModal.tsx` (only file changed).** `ItemFiles` fetches
  `getAttachments` and `listDocuments` (the existing helpers) when the modal's item changes. Both reads are
  `list:read`, the gate `GET /items/{id}` already needs, so no role sees a new error. **Only the newest request may
  write** (Previous / Next changes the item mid-flight). **A failed read says so** ("Couldn't load the document
  register." / "Couldn't load" in the slot row) rather than reading as "nothing attached"; an empty register says
  "No documents in the register."; a slot shows its filename and **Open**, or a dash.
- **A related part never reaches this code.** Tracking gives one no ▶ button and `GET /items/{id}` answers 404 for it
  (Q559), so the modal errors before rendering; an earlier draft had a related-part branch and it was removed as
  unreachable rather than left untested.
- **Tests.** `tests/e2e/tracking_modal_files.spec.ts` (4), run three times back to back against a live migrated,
  seeded stack: the modal lists the seeded item's documents read-only with Open links and the Manage link (and the
  old placeholder is gone); **Next shows the next item's own documents** (no stale rows from the previous item); a
  bound `.skp` shows its filename and Open link while the CabVision row stays a dash (the test unbinds it in a
  `finally`, and clears the slot first so a run killed before its cleanup cannot fail the next); a failed load
  says so and does not claim the register is empty. **All four fail against the unfixed modal.**
  `item_project_detail`, `attachments_locks`, `document_register` and `pm_workbench` still pass.
- **Found while testing.** A negative run with `--timeout 12000` timed out mid-test 3 and left a bound SketchUp slot in
  the live database: a Playwright timeout closes the request context, so the `finally` that unbinds cannot run.
  Cleaned by hand. If you run the spec with a short `--timeout`, check `item_attachment` for a stray `sketchup` row.
- **Known gaps, recorded.**
  - ~~**The modal's other disabled fields are still hard-coded dashes**: Floor Plan, RLS, Joiery Details and
    Cutlist Printed~~ **Closed — see *Tracking modal shows the reference fields and JID* below.**
  - The modal's `Actions` and `Query` tabs are still "Coming soon." stubs (both are real on the item editor).
  - The register list is not paged or scrollable beyond `max-h-48`, and shows label only (as on the editor).
- **Out of scope (deferred):** editing from the modal; ~~the four fields above~~ (**built, see below**); the two stub tabs.

## Null-write audit (`schema_guards.no_null`, no migration) — shipped

> Chosen by the user ("go with the audit", after "Suggest the next task and give me
> reasons"). It is the audit *Order field validation* recorded as a known gap: the orders bug
> (an explicit `null` written into a nullable column that the response model types non-null,
> poisoning every later read) could exist anywhere. The scope was asked before any code was
> written; the answer is a **settled decision**: **fix the poison and all the raw-500 fields**.
> The third option offered — also reject *unknown values* for constrained string fields — was
> **not chosen**, and moving validation ahead of `commit()` app-wide was **never in scope**.
> No migration, no spec or plan doc; this section is its written record.

- **Method (measured, not guessed).** A static scan listed every write schema field that accepts
  an explicit `null` (**359 fields on 81 routes**; a name-matching heuristic against the database
  was too noisy to trust). Then every PATCH / PUT field was **probed empirically**: on a scratch copy
  of the seeded database, send `{field: null}` to the route for a real row and record what
  happens — refused 4xx, accepted, a **raw 500 with nothing written**, or a **poison** (500 *and*
  the column is now NULL, i.e. the write landed before the response failed validation).
  221 (route, field) pairs across 34 routes (two routes, `/me/status` and the lifecycle date
  route, had no row to probe). Then a **read-side crawl**: every GET route whose path ids could be resolved
  (**96**) before and after all the accepted nulls were left in place, diffing status codes, because a
  null a PATCH accepts can still break a *different* read model.
- **Found, before the fix.** **One poison:** `PATCH /suppliers/{vendor_id}` `status`. `vendors.status`
  is nullable and `SupplierOut.status` is `str`, so the null persisted and `GET /suppliers` and
  `GET /suppliers/{id}` answered 500 for the whole workspace — the orders bug again, in the
  module next door. **32 raw 500s:** an explicit null for a field whose column is `NOT NULL`
  (nothing persisted, but a 500 instead of a 422). The crawl confirmed nothing else breaks a read:
  after all 91 accepted-null probes (before the fix) the only routes that changed were `/suppliers` and
  `/suppliers/1` (200 → 500) — the known poison, which doubled as the crawl's control.
- **The fix — `apps/api/app/schema_guards.py`.** `no_null(*fields)` is a `field_validator`
  factory: an explicit null is a **422 that names the field** (`loc` ends in the field), and, being a
  `field_validator`, it runs **only for a field the caller supplied**, so omitting a field is untouched
  (the reason the field is typed `X | None = None`). It is attached as `reject_null = no_null(...)` to
  **18 schemas / 33 fields**: `PatchSupplierIn` (`name`, `category`, `status`), `PatchSampleIn`
  (`title`, `hex_swatch`), `UserPatch` (`full_name`, `is_active`), `PatchBatchIn` (`qty_ordered`,
  `qty_received`), `PatchProjectIn` (`name`), `PatchContactIn` (`kind`, `name`, `sort_order`),
  `BoardInventoryPatchIn` (`qty_on_hand`), `CutSchedulePatchIn` (`priority`), `PatchRelatedPartIn`
  (`related_part_type_key`), material-take `PatchLineIn` (`qty`, `wastage_pct`), and in estimating
  `PatchEstimateIn` (`title`), `PatchRevisionIn` (`markup_pct`, `gst_pct`), `PatchLineIn`
  (`description`, `qty`, `unit`), `PatchPartIn` (`qty`, `paint_instruction`), `PatchHardwareIn`
  (`qty`), and QC's `PatchDefectIn` (`description`), `PatchChecklistItemIn` (`label`, `is_checked`,
  `sort_order`), `PatchReworkIn` (`cause`, `scope`). **`PatchOrderIn` / `PatchOrderLineIn` keep their
  own earlier validators** (untouched). Fields whose column legitimately clears (notes, dates, a contact
  name) are deliberately **not** guarded: clearing them is the point.
  **Re-probed after the fix:** 0 poison, 0 raw 500 (was 1 and 32); the same 33 fields now answer 422.
- **Tests.** `test_null_write_guards.py` — every (schema, field) refuses an explicit null naming the
  field, and every schema still accepts an empty body (33 + 18 cases) — and three new in
  `test_supplier_routes.py`: null `status` is a 422, **writes nothing, and `GET /suppliers` and
  `GET /suppliers/{id}` stay 200** (the poison regression); null `name` / `category` a clean 422; and
  a control that `contact_name` still clears to null. **36 of them fail against the unfixed source**
  (33 schema cases + the 3 supplier HTTP tests); the rest are controls. The two probe / crawl scripts
  were throwaway and are **not in the repo**.
- **Known gaps, recorded.**
  - **The guard is opt-in.** A *new* PATCH schema must call `no_null` for its NOT NULL fields; nothing
    fails if it forgets, because a generic test would have to know each field's column and nullability.
    The next audit is the same two steps above.
  - **POST bodies: audited afterwards, found clean — see *POST-body null audit* below.**
  - **Not audited:** `PATCH /me/status` and
    `PATCH /items/{id}/lifecycle/{stage_key}` (no resolvable row in the probe); **unknown values** for
    constrained strings (`status`, `kind`, `paint_instruction`, ...) beyond what each schema already
    validates — the option the user did not choose.
  - **The audit saw only routes with a resolvable row and the first row of each resource**, and a
    read that no crawled GET exercises could still be broken by a null. 96 GET routes were crawled, not all.
  - **Accepted nulls that are legal but odd:** `PATCH /projects` accepts `status: null` (the column is
    nullable and every crawled read tolerated it), as do related parts' `status` / `description`. They
    are not poison, so they were left; a NULL project status is unlikely to be intended.
  - **Commit-before-validate is unchanged** (user's decision): a *new* nullable-column-versus-non-null-
    response mismatch introduced later can poison a row again, because every route still commits
    before FastAPI validates the response.
  - The 422 body is FastAPI's default (`detail: [{loc, msg}]`), so the web shows its generic
    "Save failed (422)" — no web change was needed or made.
- **Out of scope (deferred):** ~~POST bodies~~ (**audited, see below**); unknown-value validation for
  constrained strings; validating before `commit()`; a generic guard that infers NOT NULL from the schema.

## POST-body null audit (no code change, no migration) — measured, found clean

> Chosen by the user ("Go for POST-body null audit"), the follow-up the section above
> recorded as "not audited". **The result is that there is nothing to fix**, so no scope
> question was asked and no schema, test or migration changed; this section is the record
> so the audit is not repeated. The probe scripts were throwaway and are **not in the repo**.

- **Method — the PATCH audit's, adapted to creates.** The static scan lists every POST body
  field that accepts an explicit `null`: **45 routes / 138 fields**. Each create route got a
  hand-built **valid base body** (a control that must answer 2xx) and then the base with one
  field set to `null`, on a scratch clone of the seeded database, with per-table row counts
  taken around every call: *nothing gained* = refused or raw 500, *rows gained* = persisted
  (and, if the answer was a 500, **poison**). 32 create routes were probed in one process. The
  13 state-changing action routes (`approve`, `reject`, `complete`, `resolve`, `close`,
  `expire`, `withdraw`, `convert`, `generate-orders`, `assign`, `reviews`, `decide`) can only
  succeed once per database, so each ran in its **own fresh clone**, once with the field
  omitted and once with `null`.
- **Result: 0 poison, 0 raw 500.** Of the 138 (route, field) pairs: **121 accepted** (a nullable
  column, or a value the query layer defaults — `estimate_no` becomes `EST-2026-…`, `type`
  becomes `IFA`, `paint_instruction` becomes `NONE`), **2 refused 422** (`POST /comments`
  `object_type` / `object_id`: the schema already requires both together) and **1 `409
  MEMBERSHIP_EXISTS`** (`project_id: null` *means* workspace-wide, and that membership existed —
  the control, not a defect). The 14 action pairs were all 200 with `null`, identical to the
  omitted control. **Nothing answered 500.** Reason it differs from PATCH: a POST names the
  columns it writes and the create schemas type the NOT NULL ones as required or give them a
  non-null default, so a `null` is refused by pydantic or replaced before the INSERT.
- **Read side, crawled.** 96 GET routes were crawled after all probes, three ways — the first
  row of each resource, the *newest* row of each (the probe-created ones), and a targeted pass
  pinned to ALF-001 with both the first item and the most null-heavy created item (null
  description / qty / code / stage; parts with no name or length; modules with no name).
  **No 5xx anywhere.** A first pass only read the oldest rows and so could not have seen a
  probe row; the newest-row and pinned passes exist because of that.
- **Found while probing, not caused by a null — since fixed, see *Approving an order with no
  cost centre* below.** `POST /procurement/approvals/{workflow_id}/decide` answered **500 for an
  approval on a purchase order with no cost centre**, with the field omitted too. `0031` made
  `purchase_orders.cost_center_id` nullable (Q563) but the legacy handler still ran
  `int(po["cost_center_id"])` after `decide` → `commit_budget`, so it raised `TypeError`.
  Nothing was written, and the seed's one PO has no cost centre, so it was reachable on the
  demo data.
- **Legal-but-odd, left:** a create can now leave real NULLs in nullable columns that some
  screens may render as blank — `items.description` / `qty` / `code`, `parts.part_name` /
  `len_mm`, `modules.name` — because the columns and the read models allow it. Every crawled
  read tolerated them; whether a create *should* require a description is a product call.
- **Known gaps, recorded.** The probe used one hand-built body per route, so a route whose
  behaviour depends on *other* body fields (a different `material_type`, a related-part `status`)
  was tested down one path only; `POST /catalog/{slug}/bulk`, the CV-import commit and the
  file / photo bind routes take non-null-typed bodies and were not probed; a crawl that
  reads 96 GET routes is not every read; and — as before — every route still commits before
  FastAPI validates the response.


## Approving an order with no cost centre (legacy `/procurement/*`, no migration) — shipped, then superseded

> Chosen by the user ("go for your pick 4xx refusal"), from the two options the
> *POST-body null audit* offered: refuse with a clear 4xx, or skip the budget
> commitment. **Superseded — see *Orders with no cost centre: approve and deliver*
> below**: the `409 NO_COST_CENTRE` this section shipped (#55) was replaced by
> "approve proceeds, no commitment". Kept for what it found and why it was replaced.

- **What it did.** `POST /procurement/approvals/{workflow_id}/decide` with `approve` on an
  order whose `cost_center_id` is NULL answered `409 {code: "NO_COST_CENTRE"}` before writing
  anything (it had been a raw 500: `int(None)` after the decision was recorded). Reject was
  never affected. Tests pinned the refusal; the reject and with-cost-centre tests were controls.
- **Why it was replaced.** The refusal's message told people to "assign a cost centre", and the
  reason for picking it over skipping the commitment was that skipping would leave the budget
  understated. **Both rested on a premise that turned out false: no route can assign a cost
  centre to an existing order** — the legacy `PATCH /procurement/orders/{id}` (`POUpdate`) has no
  `cost_center_id`, and the v1 `orders/` module has none at all — and an order with no cost centre
  (nullable by design since `0031`, Q563) belongs to no cost-centre budget, so there is nothing for
  a skipped commitment to understate. The refusal made such an order impossible to approve through
  this route with no way out. Found while looking at the sibling `deliver` route; the user was
  shown the evidence and chose to revisit.
- **Found while testing — since fixed, see *Legacy order views with no cost centre* below.**
  `v_po_summary` inner-joined `cost_centers`, so a cost-centre-less order was a 404 here.

## Legacy order views with no cost centre (migration `0045`) — shipped

> Chosen by the user ("Go with The v_po_summary LEFT JOIN fix"), the gap *Approving an
> order with no cost centre* recorded as "asked for: no". Nothing in the change was
> under-specified — the join was the bug — so nothing was asked before building; one
> *sibling* bug found on the way was left for a decision (below). No spec or plan doc;
> this section is its written record.

- **What was wrong.** `0031` made `purchase_orders.cost_center_id` nullable (Q563), but
  `v_po_summary` (`0006`, redefined by `0009`) still `JOIN`ed `cost_centers`. Every read in
  `procurement/queries.py` goes through the view, so an order with no cost centre was
  invisible to the legacy namespace: `GET /procurement/orders/{id}` answered **404**, and the
  list, the filters and both approval queues (pending and history) omitted it, although the
  row existed and the order could still be approved (now with no commitment posted — see *Orders with no cost centre: approve and deliver*).
  The seed's one purchase order is such an order.
- **The fix — `0045_po_summary_left_join_cost_centre`.** `cost_centers` becomes a `LEFT JOIN`;
  `cost_center_id`, `cost_center` and `cost_center_code` read **NULL** for such an order.
  The vendor and requester joins are on NOT NULL columns and are unchanged. The migration
  is `CREATE OR REPLACE VIEW`, valid because the output columns, their order and their types
  are identical — nothing depending on the view is dropped. The downgrade restores the
  inner join (verified: upgrade → downgrade → upgrade on a migrated database; the view
  definition flips `JOIN` ↔ `LEFT JOIN`). Only `v_po_summary` changes: `v_orders_due`
  never joined `cost_centers`, and `v_budget_utilisation` reads `cost_centers` itself.
- **Workspace scoping is unchanged.** It resolves through the project-or-vendor join, not
  through the cost centre, so a wider view does not show another workspace's order (pinned).
- **Tests** (`test_procurement_routes.py`, 3 new): an order with no cost centre is a `200`
  from `GET /procurement/orders/{id}` with NULL cost-centre fields and is in the list and the
  pending-approvals queue — **fails at `0044`** (404); an order with a cost centre still names
  it; another workspace's cost-centre-less order stays a 404 and out of the list (both
  controls that pass either way). The earlier helper that read the workflow id from the table
  to dodge this 404 now goes through the same path as a real caller.
- **Found while building — since fixed, see *Orders with no cost centre: approve and deliver*
  below.** `PATCH /procurement/orders/{po_id}/deliver` had the same `int(po["cost_center_id"])`
  the approve route had (a 500 with nothing written), and more besides.
- **Known gaps, recorded.** The legacy `/procurement/*` namespace is still not used by the
  v1 surface, so nothing on the web changed.

## Orders with no cost centre: approve and deliver (legacy `/procurement/*`, no migration) — shipped

> Chosen by the user ("go to fix the second bug of the same family. ask me any question").
> Three things were open, so the user was asked before any code was written; the answers
> below are **settled decisions**, not assumptions. No migration, no spec or plan doc; this
> section is its written record. It **supersedes** the `409 NO_COST_CENTRE` on approve
> (*Approving an order with no cost centre*, #55).

- **The rule (user).** *An order with no cost centre belongs to no cost-centre budget, so it
  neither commits nor spends one.* `0031` made `purchase_orders.cost_center_id` nullable
  (Q563) and **no route can assign one afterwards** (legacy `POUpdate` and the v1 `orders/`
  module both lack the field), so "no cost centre" is a permanent property of such an order,
  not a gap to be filled:
  - **Approve** (`POST /approvals/{id}/decide`) **succeeds**, posts **no** `Commitment` row, and
    the changelog line reads "… (no cost centre — no commitment posted)". Reject is unchanged.
  - **Deliver** (`PATCH /orders/{id}/deliver`) **succeeds**, posts **no** `Expenditure` row, and
    the changelog line reads "… (no cost centre — no expenditure posted)".
  - With a cost centre both behave exactly as before.
  *Why this over a 409 (the user's call, against the recommendation this file previously
  carried):* a refusal would have made such an order impossible to approve or deliver through
  these routes with no way to make it possible, and delivery records a physical fact (the goods
  arrived) that a missing budget entry should not block.
- **`deliver` also needs Approved (user: verify, fix if real — it was).** `mark_delivered`'s
  UPDATE was guarded by `status = 'Approved'`, but the `Expenditure` insert and the "Marked
  Delivered" changelog ran regardless, so delivering a **Draft** order answered `200
  {"status": "Delivered"}`, left the order **Draft**, and posted an `Expenditure` (reproduced
  before the fix: `HTTP 200 | PO STATUS Draft | BUDGET ROWS [('Expenditure', …)]`). The same hole
  made a **second** `deliver` on a Delivered order post a **second** Expenditure. Now
  `queries.mark_delivered` returns `None` when its UPDATE matched no row and the route answers
  **`409 {code: "BAD_STATUS", message}`** with nothing written — the codes-and-409 shape the rest
  of the app uses, rather than this module's older bare-string 400s.
- **Code.** `procurement/routes.py::decide_approval` records the decision first and then posts the
  commitment only when a cost centre exists (the refusal and its early read are gone);
  `mark_delivered` (route) branches on the `None` and on the cost centre; `queries.mark_delivered`
  reads `rowcount`.
- **Tests** (`test_procurement_routes.py`): approving with no cost centre is `200`, ends
  `Approved` / `Approved` with **0** budget rows and the changelog note — *replaces* the
  refusal test; delivering an Approved order posts one `Expenditure` (control, beside its
  `Commitment`); delivering with no cost centre delivers with **0** rows and the note; delivering
  a **Draft** order is a `409 BAD_STATUS` that leaves the order row (status **and** changelog) and
  the budget untouched; delivering **twice** leaves exactly one `Expenditure`; another workspace's
  order is a 404 and stays Approved. **Four fail against the previous routes** (approve-no-cost-
  centre, deliver-no-cost-centre, deliver-Draft, deliver-twice); the rest, and the reject and
  with-cost-centre approve tests, are controls. The Draft reproduction and an approve/deliver
  probe were throwaway and are not in the repo.
- **Known gaps, recorded.**
  - **An order with no cost centre is invisible to cost-centre budget reporting by design**
    (`v_budget_utilisation` reads `cost_centers`); there is no "unallocated spend" view, and
    nothing flags that such an order has no budget line. Whether there should be one is a product
    call, not a bug.
  - **No route assigns a cost centre to an existing order** (above). Not built; it is what would
    make "attach it later, then commit" possible.
  - ~~The legacy `/procurement/*` namespace still does not use the order-status guard.~~
    **Closed — see *Legacy procurement audit* below.**

## Tracking modal shows the reference fields and JID (no migration, no API change) — shipped

> Chosen by the user ("fill in the Tracking modal's placeholder fields"), the gap *Tracking modal
> shows the register and the SketchUp / CabVision slots* recorded as "not asked for". Three things were
> open, so the user was asked before any code was written; the answers are **settled decisions**.
> Web and seed only.

- **Settled decisions (user).**
  1. **Read-only.** Editing stays on the item editor's `ItemMetadataPanel`, which already owns the
     Controlled / Hard / Approval locks, field-version conflicts and revert-on-refusal. Duplicating that
     in a third place was the alternative offered and declined.
  2. **The header's JID box is included** (asked because it was *not* in what the user named): it showed
     only the word "JID" with no value although `jid_code` / `jid_color` are on `ItemOut`. It now shows the
     colour swatch and code, the same pair the Tracking grid's `JidCell` renders. Empty when the item has
     neither (`data-testid="modal-jid"`).
  3. **The `Actions` and `Query` stub tabs are left as "Coming soon."** — both are real on the item editor
     with their own lock and role rules; making them work here is a separate feature.
- **Web — `tracking/_components/ItemDetailModal.tsx` (only component changed).** Floor Plan, RLS and
  Joiery Details read `item.floor_plan` / `rls` / `joiery_details`; Cutlist Printed reads
  `item.cutlist_printed`. An empty value shows a dash, a NULL `cutlist_printed` shows a dash, `false` an
  open circle, `true` a tick. The `disabled` prop on `Field` and `CheckRow` had no other caller and was
  removed.
- **`items.cutlist_printed` defaults to TRUE** (legacy FileMaker port, `0001`), so every item reads as
  printed unless someone unticks it. A test that only looked at a ticked item would prove nothing.
- **Seed.** `seed/hartwood_joinery.py` sets `floor_plan` / `rls` / `joiery_details` and
  `cutlist_printed = FALSE` on ALF-001's **first** item only (inside the Tracking 2.0 loop's existing
  `UPDATE`, `COALESCE`d so a re-run is harmless), so the modal shows real values there, an open circle
  for Cutlist Printed, and dashes / a tick on the rest. **Direct SQL, not a PATCH**: `PATCH /items/{id}`
  claims the item's Controlled Lock, which a test could not put back.
- **Tests.** `tests/e2e/tracking_modal_files.spec.ts` (4 → 6): the modal shows the item's values (compared
  with `GET /api/items/{id}`, after asserting the seed made them non-empty so the test cannot pass on
  dashes), the JID swatch and code, an open circle for Cutlist Printed, and no inputs; **Next** shows the
  next item's own values (dashes and a tick), not the previous item's. Run three times back to back
  against a live migrated, seeded stack; **both new tests fail against the unfixed modal** (the other four
  pass there) and `item_project_detail`, `pm_workbench` and `smoke` still pass. No backend test was added:
  no API changed.
- **Found while testing.** The sandbox's Chromium (`chromium-1194`) does not match the Playwright this repo
  pins (it wants `1217`), so `playwright test` cannot launch. A throwaway config that spreads
  `playwright.config.ts` and adds `launchOptions.executablePath` pointing at `/opt/pw-browsers/chromium-1194/
  chrome-linux/chrome` runs it without touching the repo; it was deleted afterwards.
- **Known gaps, recorded.**
  - The modal's `Actions` and `Query` tabs are still stubs (above).
  - The Estimator Notes box at the bottom of the left column renders as a narrow textarea under its label
    (an existing layout quirk in `Field`'s textarea branch, not touched).
- **Out of scope (deferred):** editing from the modal; the two stub tabs.

## Legacy procurement audit (`/procurement/*`, migration `0046`) — shipped

> Chosen by the user ("go for the legacy procurement audit"), the follow-up the orders-with-no-cost-centre
> work kept finding siblings for. Method: the null-write audit's — probe a scratch clone of the seeded
> database, measure before and after, and only then fix. The scope and two policies were asked before any
> code was written; the answers are **settled decisions**: fix **all four groups** below, PATCH `status`
> **"keep it, like the v1 module"**, and a delivery **posts a negative `Release`**. The probe scripts were
> throwaway and are not in the repo. The web app does not call this namespace (grep, and no e2e spec does),
> so no web change was needed.

- **Group 1 — clear defects.**
  - **PO numbers.** `generate_po_number` used `MAX(...) + 1` while the v1 `orders/` module draws from
    `po_number_seq` into the same table, so the two handed out the same number and the v1 create then failed
    on the unique index. Legacy now uses `nextval('po_number_seq')` too (Q564). `0046` advances the sequence
    past the highest `PO-YYYY-NNNN` already in use, because a database holding legacy-made numbers ahead of it
    would keep colliding (found when the first suite run hit `PO-2026-0012`). Nothing is renumbered and the
    sequence is never moved backwards.
  - **Totals.** `POST /orders` and `duplicate` never set `purchase_orders.total_amount` (the MySQL triggers
    were not ported), so every order with lines approved a **$0 Commitment**. Both now call the v1 module's
    `_recompute_total_amount`. `0046` back-fills existing orders with lines and a $0 total; a figure anyone set
    is never overwritten and `updated_at` is left alone. **Budget rows already posted at $0 are not rewritten**
    (append-only ledger).
  - **`cancel`** answered 200 "Cancelled" and logged it for any status with the order unchanged; it is now
    `409 BAD_STATUS` unless the order is Draft, Rejected or Hold.
  - **`decide`** moved the order whatever its status (approving a Cancelled or Delivered order made it Approved
    and posted a commitment); it now needs the order to be Pending (`409 BAD_STATUS`), checked **before** the
    workflow row is touched so a refusal writes nothing. The pending-approvals queue lists Pending orders only.
  - **Paging** (`limit` / `offset` / history `limit`) rejects negatives with 422 (raw 500 before).
  - **Duplicate `line_number`s** in a create body are a 422 (raw unique-violation 500 before).
  - **`duplicate`** now keeps `project_id`, `item_id`, `attributes` and each line's `attributes` /
    `material_table` / `material_id`, which it used to drop.
- **Group 2 — PATCH bypass.** `PATCH /orders/{id}` could jump Draft → Approved (no workflow, no commitment),
  → Delivered (no expenditure) or Approved → Cancelled (commitment left behind), and could overwrite the
  `changelog`. Now, the v1 *Purchase order status guard*'s rule:
  - a **Cancelled / Delivered** order is read-only except `status` (`409 ORDER_LOCKED` with `blocked_fields`;
    a mixed PATCH is refused whole);
  - on any other order `status` is **not writable** here (`409 STATUS_NOT_PATCHABLE`) — it moves through
    submit / decide / deliver / cancel, which post the budget rows;
  - `changelog` is read-only (422). A status change on a frozen order appends `(status X → Y)` to the log.
- **Group 3 — budget double count (migration `0046`).** Approve posts a `Commitment` and deliver an
  `Expenditure`, and nothing took the commitment back, so a delivered $110 order read as $220 in
  `v_budget_utilisation`. `budget_transactions` already allowed a `Release` type nobody used. **Deliver now posts
  a negative `Release`** for the outstanding commitment (`release_commitment`: the sum of the PO's Commitment
  and Release rows, posted only when positive, so a second release is impossible and a partial one is exact),
  and the view sums Commitment + Expenditure + Release. The downgrade restores the two-type view.
- **Group 4 — attachments and hardening.**
  - `uploaded_by` is validated against the caller's workspace (`422`); the listing's name join is
    workspace-scoped for older rows, so a historic foreign id no longer leaks a name.
  - Files get a unique on-disk name (`{uuid}_{name}`): two uploads called `quote.pdf` used to share a path, the
    second replacing the first's bytes and deleting one removing both. Delete keeps a file another row still
    points at (historic shared paths). *(Superseded for new uploads by migration `0047` — they no longer touch
    the local disk; see *Legacy PO attachments in the shared file store*. Rows older than it still use this.)*
  - Uploads are read in 1 MB chunks with the 25 MB `MAX_BYTE_SIZE` cap (`413`) and the file is removed if
    anything fails after it was written. `file_path` is no longer in the listing.
  - **Attachments on a Cancelled / Delivered order are read-only**, upload **and delete** (`409 ORDER_LOCKED`).
    The user named uploads; blocking delete too was a call made while building.
- **Tests** (`test_procurement_routes.py`, ~35 new; the file is 66). The new tests were run against the unfixed
  source (queries / routes / schemas stashed): **36 fail, 30 pass** (the passes are controls). An existing RTO
  filter test PATCHed `status` to stage its data; it now stages through SQL. Migration checked on a scratch
  database: upgrade → downgrade → upgrade, the back-fill, and the sequence jump (12 → 500, never backwards).
- **Known gaps, recorded.**
  - **Reopening a frozen order through `PATCH status` can bypass the workflow and the budget** — that is the
    user-chosen option: e.g. Delivered → Approved → deliver posts a second `Expenditure`, and no commitment is
    posted on reopen.
  - Workflow design left as found: any user with `orderbook:approve` can decide any workflow, the named approver
    need not hold a role that can approve, self-approval is allowed, and a Rejected order cannot be resubmitted.
  - ~~Attachments still go to `./uploads` (CWD-relative), **not** the mounted `uploads` volume, and there is no
    download route.~~ **Closed — see *Legacy PO attachments in the shared file store* below.**
  - The v1 `orders/` module can still set a Pending order's status directly, orphaning its workflow (the
    pending-queue filter hides the effect).
  - The legacy category enum has 6 of the 14 `order_category` keys.
  - Historical Commitment / Expenditure rows posted at $0 remain.

## Legacy PO attachments in the shared file store (`/procurement/*`, migration `0047`) — shipped

> Chosen by the user ("go with the next recommendation task" — the first follow-up I listed: the gap *Legacy
> procurement audit* recorded as "attachments still go to `./uploads`… and there is no download route").
> Two things were open, each asked before any code was written; the answers are **settled decisions**, not
> assumptions: **move to the shared `FileStore` / `file_blob`** (over just pointing `UPLOAD_DIR` at the volume),
> **add a download route**, **new uploads follow the app-wide allowlist**, and **old rows are left alone**
> (no backfill). No spec or plan doc; this section is its written record. The web does not call this
> namespace, so no web change was needed.

- **What was wrong.** `POST /procurement/orders/{id}/attachments` wrote to `UPLOAD_DIR` = `./uploads`, relative
  to the api process's working directory — inside the container's own layer, not the mounted `uploads` volume —
  so a rebuilt container lost every file while the rows stayed. Nothing could read a file back at all (no download
  route), and any type was accepted unchecked.
- **Migration `0047`** — one nullable column, `po_attachments.file_blob_id` → `file_blob`. No `ON DELETE`: a blob is
  never deleted anywhere in this app (no orphan GC). `file_path` stays and is nullable. **Nothing is backfilled**
  (reading the filesystem in a migration is fragile and untestable in CI; most old files are probably already gone).
- **Upload — `procurement/routes.py::upload_attachment`.** Same contract as `POST /files`, which it now shares a
  store with: 25 MB cap (`413`), empty file `400`, magic-byte sniff that must agree with the extension
  (**`415`**), sha256 dedup per workspace. So the accepted types are **PDF, PNG, JPEG, `.skp`, `.cvj`** — an `.xlsx`,
  `.docx` or `.txt` quote is now a `415` where it used to be accepted. *That is a deliberate tightening the user
  chose*; the `attachment_type` field (`File | PDF | Image`) is unchanged and unrelated to the sniff. The bytes go
  through `FileStore.put`, the `file_blob` row is written (with the same `file_blob.create` audit as `/files`), and
  the attachment row points at it with `file_path` NULL. A dedup hit reuses the existing blob and writes no
  bytes. Gated `orderbook:write` (not `shop_dwgs:write`, which `/files` needs). All earlier checks are kept and
  still run **first**: workspace, `uploaded_by` in this workspace (`422`), and the Cancelled / Delivered freeze
  (`409 ORDER_LOCKED`).
  - **Failure cleanup removes only bytes this request wrote.** A deduplicated blob belongs to other rows, so a
    failure after a dedup hit deletes nothing; a failure after a fresh `put` rolls back and deletes the file.
- **Download — `GET /procurement/orders/{po_id}/attachments/{attachment_id}/download`** (new), `orderbook:read`.
  Workspace-scoped through `po_in_workspace`; the blob join is **also** scoped to the caller's workspace
  (`file_blob_id` is a plain FK with no workspace of its own, so a row pointing across workspaces serves nothing —
  `404`). Unknown attachment, attachment on another order, and a file whose bytes are gone are all `404`. A
  frozen order's attachments can still be downloaded (reading is not editing).
  - **Blob-backed rows stream `inline`** with the stored mime and the RFC 8187 dual filename, like `GET /files/{id}`
    — safe because the type was sniffed on the way in.
  - **Legacy rows (no blob) stream from `file_path` if it still exists, always as `attachment`** with
    `X-Content-Type-Options: nosniff` and `no-store`: those files were never sniffed, so the browser must never
    render one (an uploaded `.html` would otherwise run in the app's origin). A missing file or NULL path is `404`.
- **Delete.** A blob-backed attachment deletes its **row only** — the blob is deduplicated, other rows (and other
  modules) may share it, and nothing collects orphans. A legacy row keeps its old behaviour (unlink the file unless
  another row shares the path). `queries.get_attachment` now takes `workspace_id` and returns the blob columns.
- **Removed:** the `UPLOAD_DIR` constant and its `UPLOAD_DIR` env var (nothing else read it). `FILE_STORE_ROOT`
  (`/uploads`, the mounted volume) is the only storage setting.
- **Tests** (`test_procurement_routes.py`, 66 → 83). The `upload_dir` fixture now sets `FILE_STORE_ROOT`, and test
  content is a real PDF header (`b"data"` would now be a 415). New: an upload lands in the store with a blob row and
  NULL `file_path`; identical bytes share one blob across orders; same-name uploads keep their own content; deleting
  a row keeps a blob another row uses; the four refusals (`.xlsx`, `.txt`, extension disagreeing with the bytes,
  empty) leave no row, no blob and no file; a failure after the write removes the bytes, and does **not** when the
  blob is shared; download streams the bytes with the right headers and filename; `404` across workspaces, for a
  foreign workspace's blob, for an unknown id / wrong order, for a gone legacy file, for a gone blob; `403` for a
  group with no `orderbook` grant; a legacy row downloads only as an attachment with `nosniff`; a frozen order can
  still be downloaded from. **15 fail against the unfixed source**; the 12 that pass there are controls (several
  are `404` cases that pass only because the route did not exist). Migration checked on a scratch database: upgrade
  → downgrade → upgrade.
- **Known gaps, recorded.**
  - **Old attachments are not recoverable by this change.** Rows from before `0047` still point at a container-local
    path; where the file is gone the download is a `404` and the row stays in the list.
  - The `/files` upload route is unchanged and still gated `shop_dwgs:write`; a user with `orderbook:write` and no
    `shop_dwgs` grant can attach through this route (which writes the blob itself) but cannot use `/files`.
  - Orphaned blobs from removed attachments stay (no GC), as everywhere else; the 25 MB cap is unchanged.
  - **Not verified in a browser or by e2e** — there is no web surface for this namespace.

## FIELD_CONFLICT serialisation on items and cutlists (no migration) — shipped

> Chosen by the user ("go with 1") from the suggestion list after the legacy procurement audit; it is
> the gap *Orderbook — Purchase Order editing UI* recorded as "the identical shape likely exists in
> `items`'s and `cutlist`'s own conflict paths". Nothing in it was under-specified, so nothing was
> asked. No migration, no spec or plan doc; this section is its written record.

- **What was wrong (reproduced before fixing).** A `FIELD_CONFLICT`'s `current_value` rides in
  `HTTPException(detail=...)`, which bypasses the response_model's encoding and goes through
  Starlette's plain `json.dumps`. `patch_order` had been fixed for this; `patch_item` and
  `patch_cutlist` still put the raw column value in, so a conflict on a non-string value was a raw
  `TypeError` 500 instead of the 409:
  - **Items:** `total_amount` is a versioned, patchable `Decimal`. A stale-version PATCH on it
    500'd. This is the one *reachable by a normal client*.
  - **Cutlists:** `expected_versions` may name any key and `current_value` is read from the row for
    whatever key it names, so naming a datetime column (`created_at`) 500'd. Contrived, but the same
    code path. (`name`, the only patchable field, is a string.)
  - Items cannot hit the datetime case: the items row carries no datetime column a caller can reach
    (`hard_locked_at` is only set under a Hard Lock, which refuses the PATCH before the conflict check).
- **The fix.** The orders module's private `_conflict_safe_value` moved to
  `app/concurrency.py::conflict_safe_value` and all three modules call it where they fill
  `current_value`. Decimal and date / datetime become **strings** (not `jsonable_encoder`'s float, which
  would break this API's money-is-a-string invariant). Items and cutlist routes are unchanged; orders keeps
  its `jsonable_encoder` wrapper.
- **Tests** (`test_lock_types_concurrency.py`, 2 new): an item `total_amount` conflict answers 409 with
  `current_value == "1234.50"` (a string) and the stale write does not land; a cutlist conflict naming
  `created_at` answers 409. **Both fail against the unfixed source** (`TypeError: Object of type Decimal /
  datetime is not JSON serializable`). The existing orders conflict test still passes through the shared
  helper. 173 pass across the lock, order, cutlist and item route files.
- **Known gaps, recorded.** `expected_versions` is not validated against the real field names, so a
  caller can still name any key (cutlist reads it from the row; items falls back to the key itself). That
  is the behaviour `test_cutlist_conflict_on_unrelated_expected_version_key_does_not_500` pins on purpose.
  The three modules each still call `check_field_conflicts` and fill `current_value` themselves.

## Server-computed `locked` on orders (no migration) — shipped

> Chosen by the user ("go with the next recommendation task") from the suggestion list after the
> `FIELD_CONFLICT` fix — the drift risk *Purchase order status guard* recorded. Nothing in it was
> under-specified, so nothing was asked. **Guarding `Rejected`, which that list paired with it, was
> deliberately dropped, not built:** the status guard's settled decision is that `Rejected` stays editable
> ("it can be fixed and resubmitted"), and reopening that would contradict the user's own answer. No
> migration, no spec or plan doc; this section is its written record.

- **What was wrong.** "Which statuses freeze an order" lived twice: `FROZEN_STATUSES` in Python, which
  enforces it (`409 ORDER_LOCKED`), and a hand-copied constant in `OrdersClient.tsx`, which decided what to
  render. A third frozen status added server-side would have been enforced but not hidden, and nothing
  pinned the two together (unlike `OrderStatus`, which a test checks against the DB CHECK).
- **The fix.** `OrderOut` gained a pydantic `computed_field` **`locked: bool`** — `status in FROZEN_STATUSES`.
  `OrderDetailOut` extends `OrderOut`, so `GET /orders`, `GET /orders/{id}` and every response that returns the
  order (the header PATCH, all three line mutations) carry it; it is computed on serialisation, so there is no
  column, no extra query and nothing to keep in sync. The web's `OrderRow.locked` is read by
  `OrderDetailPanel` in place of the old constant, which is deleted. The API still enforces the rule exactly as
  before; the flag only tells the UI what to render.
- **`FROZEN_STATUSES` moved to `orders/schemas.py`** (beside `OrderOut`), because `queries.py` already
  imports `schemas.py` and the flag needs the set — the other direction would be a circular import.
  `orders.queries` re-imports it under the same name, so `orders.queries.FROZEN_STATUSES`, the legacy
  `procurement` module's re-export of it and the existing test import are unchanged.
- **Tests** (`test_order_routes.py`, 10 new). `locked` is true for exactly `Cancelled` and `Delivered` across
  **all nine statuses**, on both the detail and the list; and it follows a reopen — on the reopening PATCH's own
  response and on a line mutation's. The expected set is written out literally in the test, not read from
  `FROZEN_STATUSES`, so the test can disagree with the code. **All 10 fail against the unfixed source**
  (`KeyError: 'locked'`). 195 pass across the order, legacy-procurement and lock test files; `tsc --noEmit` is clean.
  **Not verified in a browser or by an e2e run** — the stack was not up and no spec covers the frozen banner; the
  UI change is a one-line swap of where `frozen` comes from, with every `setOrder` call fed from an API response
  that carries the flag.
- **Known gaps, recorded.**
  - **`OrdersClient.tsx`'s `STATUSES` (the status select) is still a hand-kept copy** of the DB CHECK; only the
    frozen set was removed.
  - The four handlers in `OrdersClient.tsx` still each repeat the "if locked, refetch and refresh the list"
    block (unchanged).
  - The legacy `/procurement/*` routes do not return `locked` (the web does not call them).

## Comment counts on modules and revisions (Plan V1 §29 follow-up, no migration) — shipped

> Chosen by the user ("go with the next recommendation task" — the first gap *Comment threads on
> Modules and shop-drawing revisions* recorded: "no comment counts for modules or revisions"). Two
> things were open, each asked before any code was written; the answers are **settled decisions**,
> not assumptions: **embed `comment_count` in payloads the screens already fetch** (over new
> count endpoints like `GET /projects/{pid}/comment-counts`), and **badges on the module list and on
> both revision lists** (the details panel's Revisions tab and the viewer's versions list).

- **What a count is.** The thread's **live** comments — `deleted_at IS NULL`, **replies included** —
  the rule the Areas & Rooms badges and the register's per-drawing count already follow. So a deleted
  parent that survives only as a blanked placeholder (because a live reply hangs off it) is **not**
  counted, and a top-level comment deleted with no replies simply drops out.
- **Backend (no new route, no migration).**
  - `ModuleOut.comment_count` (`items/schemas.py`, default 0) is filled by `GET /items/{id}`'s module
    query (a correlated `count(*)` on `comment.module_id`) **and** by `parts.queries.get_module`, the
    helper behind `POST /items/{id}/modules` and `PATCH /modules/{mid}` — so a patched module's
    response carries its true count, not a default zero. A new module reads 0.
  - `RevisionOut.comment_count` (`shop_drawings/schemas.py`, default 0) is filled by the one query
    that builds a drawing's revision list, which every route returning a `DrawingDetailOut` shares
    (`GET`, the `PATCH`, the create and the add-revision routes), so none can answer a stale zero.
  - **Gating needed no change:** each count rides a route whose read rule already equals its thread's —
    `list:read` for `GET /items/{id}` (a module thread needs `list:read`) and `shop_dwgs:read` for
    `GET /shop-drawings/{id}` (a revision thread needs `shop_dwgs:read`) — so a count is never served
    to someone who could not open the thread. Counts are workspace-scoped through the same item /
    drawing lookups, and a related part's modules never reach this code (404, as before).
- **Web.** `components/comments/CommentBadge.tsx` — the "💬 N" chip (nothing at 0, `data-testid=
  "comment-badge"`), the same look as the Areas & Rooms card's own `CountBadge`, which was **left as it
  was** rather than migrated (it is a private copy in `ProjectAreasCommentsCard.tsx`; a later cleanup
  can point it at the shared one). Used by `ModuleTree` (each module row), `DetailsPanel`'s
  `RevisionList` and `DrawingViewer`'s Versions list. `ModuleOut` / `Revision` in
  `lib/pm-types.ts` / `lib/shop-drawings-types.ts` gained `comment_count: number`.
  **The badges follow a post, reply, edit or delete with no reload**, because each thread now tells its
  parent: the Cutlist tab's module thread calls `router.refresh()`; the details panel and the viewer
  call their own `refresh()` (each holds its own copy of the drawing detail) as well as
  `props.onChanged` (the register list). **Both hookups are load-bearing** — with either removed the
  badge stayed one behind (6 vs 7, 9 vs 10) and the e2e failed. `router.refresh()` here is safe against
  the `+ Add module` race recorded under *Comment threads on Modules…* because the module thread never
  touches the URL.
- **Seed.** Nothing new: the seed already leaves one comment on the first item's first module and one
  on an in-review revision, so a fresh `make seed` opens with a 💬 1 on each.
- **Tests.** `test_comment_counts_module_revision.py` (15): a module / revision with no comments reads 0;
  the count is its live thread with replies included; per module and per revision, not per item or per
  drawing; the item, project and the *other* kind of thread do not count; a deleted comment is not
  counted, and a deleted parent with a live reply counts only the reply; the module create / patch and
  the drawing PATCH responses carry the true count; a read-only role sees the same numbers; another
  workspace's comments never count. **All 15 fail against the unfixed source** (`comment_count` is
  absent from the payloads). `tests/e2e/comment_counts.spec.ts` (2), run against a live migrated, seeded
  stack and **re-run back to back**: the first module's badge shows the seed's 💬 1 and becomes baseline
  + 1 after a post from the screen; the latest revision's badge in the details panel, then in the
  viewer's Versions list, each following a post made there. Both fail without the web changes (no badge)
  and, separately, with the `onMutated` hookups removed (stale badge). The neighbouring
  `comments_module_revision`, `cv_replace_comments` and `shop_drawings` specs still pass (12). Like the
  other comment specs these add comments and leave the rows behind.
- **Known gaps, recorded.**
  - **The counts are loaded with the page, not pushed**: a comment another person makes shows up on the
    next page load or after you post, reply, edit or delete on that thread yourself — there is no poll
    (the bell polls; these badges do not).
  - **Only the module and revision lists carry a badge.** A module's thread is still shown only on the
    Cutlist tab, a revision's only in the details panel and viewer, and the Hardware / other item tabs and
    the register table's per-drawing count (all revisions summed, unchanged) are as they were.
  - The module count query runs once per module row of the item detail (a correlated subquery); an item
    has a handful of modules, so this is negligible, but a bulk "counts for N items" surface would want a
    grouped query instead.
- **Out of scope (deferred):** counts on the Tracking grid or the Cutlist module summary elsewhere; an
  unread / "new since you looked" marker; polling the counts; migrating the Areas & Rooms card onto
  `CommentBadge`.

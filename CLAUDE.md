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

---

# Project reference

> **How this file is organised.** This file is the *rulebook*: what is true now, and what you must not break. The per-sub-project history (design choices, review rounds, test names, known gaps) was moved **verbatim** to `docs/sub-projects/` — read the relevant file before large changes to that area. Index: `docs/sub-projects/README.md`.

## 1. What this is

**JoineryFlow** — a web replacement for a FileMaker-based joinery production system. Monorepo:

| Path | What |
| --- | --- |
| `apps/api/` | FastAPI + SQLAlchemy Core (`text()` queries, no ORM models) + Pydantic v2 |
| `apps/web/` | Next.js 16 (App Router, Turbopack) + Tailwind v4 + TypeScript |
| `db/` | Alembic migrations `0001`→`0051` (head `0051_estimate_line_material_order`) |
| `seed/` | `seed.hartwood_joinery` dev seed (workspace + 13 staff users + demo data) |
| `legacy/` | Read-only FileMaker-era prototypes. Reference only |
| `apps/api/tests/` | pytest suite (~100 files; counts drift, so none are recorded here). Shared setup: `conftest.py` + `helpers*.py` (see §3) |
| `tests/e2e/` | Playwright specs (31 spec files, plus `helpers.ts`; see §3) |
| `docs/plan-v1/` | **Plan V1**: customer's target spec, gap analysis, open questions (Q432–Q586) |
| `docs/superpowers/` | Older specs + plans (read `plans/README.md` first) |
| `docs/sub-projects/` | History of every built sub-project, moved out of this file |

Plan V1 is the **roadmap**, not a description of the tree (Q433); shipped behaviour may change only behind data-preserving migrations (Q435). `docs/plan-v1/ALIGNMENT.md` maps it onto the code — **read its §3 before building anything from Plan V1**. Three decisions deliberately depart from Plan V1's prose and must not be "fixed": **Q499** (PM confirmation of the Material Summary is advisory), **Q513** (no rollback of change states), **Q527** (fixed KPI catalogue).

## 2. Dev loop

```
make up           # build + start db, meili, api, search-worker, web
make migrate      # alembic upgrade head
make seed         # hartwood-joinery workspace + 13 users + demo data (dev password: hartwood-dev)
make test         # pytest in api container (meili-marked tests skip unless MEILI_URL set)
make reindex      # rebuild the search index from Postgres
make e2e-docker   # Playwright via official image (Windows-friendly)
```

- Login `http://localhost:3000/login` → `rin.park@hartwood.test` / `hartwood-dev` (any `*.hartwood.test` user). Health: `/api/health`.
- `make test` TRUNCATEs `workspace`, `app_user`, `session`, `audit_log`, so re-run `make seed` afterwards.
- Without Docker: needs Python ≥3.12 (make a venv), `pip install -e ".[dev]"`, `DATABASE_URL` at a migrated Postgres, then pytest. The seed finds its sample files relative to itself, so `python -m seed.hartwood_joinery` works outside the container too.
- `search-worker` runs with **no `--reload`** — restart it after editing `app/search/`.

## 3. Testing rules

- **e2e baseline = a freshly created, migrated, seeded database.** The seed skips items that already exist, so a re-seed does not restore a lock or take an earlier run changed. `estimating`, `procurement` and `comments` specs are not re-runnable on one database.
- CI runs e2e as an **advisory** job (production build, `next start`, `retries: 1` in CI). Never skip, disable or quarantine a spec to get green. A retried-and-passed spec is "flaky": read it.
- Specs run alphabetically in one worker and share state. When a spec fails, the guilty one is usually *earlier*: check `audit_log` for who touched what. Every spec must put shared state (locks, takes) back as seeded.
- Click-before-hydration and "locator matches a different element with the same role/test id" are the two recurring flake shapes. Prefer `href` + `goto`, or retry the click (`toPass`).
- A count assertion is satisfied by stale rows — reload and target by name.
- **A failing or skipped spec is not coverage.** When one goes red for a trivial-looking reason, check what it stopped guarding.
- Tests for a fix must be shown to **fail against the unfixed source**.
- Test infrastructure traps: patch **`rbac_engine.MATRIX`**, not `permissions.MATRIX`; never assert an absolute PO or Item number (sequences survive `TRUNCATE`); tests assert `stage_key`, never lookup labels.
- **Shared test setup lives in one place; do not copy it into a file.** pytest: `tests/conftest.py` re-asserts `status_options` / `stages` before every test (never seed them yourself), provides cleanup (`truncate_after` fixture, `truncate_fixture(*extra)` for extra tables), auto-skips `meili`-marked tests without `MEILI_URL`, and hashes passwords with minimal argon2 cost (the hash is still argon2id). `tests/helpers.py` is the one `login()` / `login_same_workspace()` / `create_project()` / `set_item()`; `helpers_<family>.py` hold the per-feature builders. **A test file never imports from another `test_*.py`.** e2e: `tests/e2e/helpers.ts` `login(page, email = MANAGER)`; `smoke.spec.ts` keeps its inline login because login is what it tests.
- **Workspace isolation is probed for every route with a path id** (`test_workspace_isolation_probe.py`): an admin of another workspace must get exactly the answer a nonexistent id gets (status and body), so a 403, a 200 or a different message is a leak. A new id route is covered automatically. If the test says an operation was "not really probed", make it probable (seed data, `BODY_OVERRIDES`, `REAL_ID_QUERIES`) or write a dedicated test and list it in `NOT_PROBED` with the reason (one marked `GAP:` has no dedicated test). The control user is the seeded admin; permission-group mutations run last because they change what that admin may do. Foreign ids inside a request *body* are probed by `test_workspace_isolation_body_probe.py` (A's admin names B's row in each FK field; B's row must be answered like a nonexistent one). Its `KNOWN_LEAKS` are open defects, not exemptions: fix the route and remove the entry. Ids in a *query string* (`?project_id=`, `?customer_id=`…) are probed by `test_workspace_isolation_query_probe.py`: a list with no path id is called by another workspace's admin with workspace A's real id, because that is the direction that leaks data (A's admin passing B's id proves nothing when B owns no rows). Both probes also fail on any 5xx (a route that crashes on a bad id answers the real and the ghost id alike, so the comparison alone would pass it). Shared machinery: `tests/helpers_probe.py`.
- CI also runs `ruff --select F401,F841,F811` over `apps/api/app` and `apps/api/tests` (an unused variable is often a dropped assertion). A fixture imported from a helper module needs `# noqa: F401`. The `search` e2e specs skip on a Meilisearch 503 locally but **fail** when `CI` is set (the CI stack starts Meilisearch).

## 4. Seed rules

- Alembic backfills touch only rows that exist at migration time; `make seed` inserts rows *afterwards*. **Every seed block that creates an item must also create its cutlist, area and room.**
- Seeds write fixed numbers then advance `joinery_number_seq` — keep that step.
- Seed through the **same query functions the API uses** so audit / edit-log rows are real. Idempotent: drop target rows first.
- **Do not seed a Hard / Approval lock** — it would break e2e specs that PATCH ALF-001 items.
- A new workspace needs `seed_system_groups()` (RBAC groups) — the seed calls it.

## 5. Auth & RBAC

- Argon2id passwords, opaque 32-byte tokens (sha256 stored), httpOnly `jf_session` cookie, sliding 14d / hard cap 30d.
- **7 roles**: `admin, manager, editor, drafter, estimator, purchase_officer, viewer`. **12 modules**: `dashboard, tracking, list, shop_dwgs, isample, orderbook` (the 6 tabs) + `catalog, cut_floor, shop_floor, estimating, qc` + admin-only `it_management`. **4 actions**: `read, write, approve, comment`.
- **Live source of truth is the DB engine** (`auth/rbac_engine.py`, groups + memberships, migration `0037`). `MATRIX` in `auth/permissions.py` is the readable record and the **fallback only for a user with zero memberships**. A user with ≥1 membership is fully DB-governed; an empty result is a real "no".
- `require_permission(module, action, project_param=None)`; most call sites check workspace-wide grants only. Project-scoped memberships are honoured only where `project_param` is passed. `/auth/me`, Global Search and comment routes use **workspace-wide grants only** (a user with only project-scoped memberships sees nothing there).
- Adding a module needs **both** a `MATRIX` entry **and** a migration inserting `group_module_grant` rows for existing workspaces.
- Per-object rules (`require_drafter()`, not-uploader-approves, creator-or-manager, 5-min undo) live in route handlers, not the engine (Q472 not built). Drafter is PM-parity on `orderbook`, `shop_dwgs`, `isample`, `catalog`, `cut_floor`.
- Every authenticated mutation writes `audit_log` (`auth/audit.py`); item-scoped mutations also write `item_edit_log` in the same transaction.
- `jtbd_role` is display-only; nothing branches on it.

## 6. Web shell

- Browser → Next.js Route Handler (`app/api/[...proxy]/route.ts`) → FastAPI. **The browser never calls FastAPI directly.** `proxy.ts` enforces login redirect.
- `(app)/layout.tsx` does server-side `fetchMe()` and renders chrome. Editor mode (`/items/[id]`) hides TabStrip + SideBar.
- **IA is fixed: 6 primary tabs** `Dashboard · Tracking · List · Shop Dwgs · iSample · Orderbook` (the `List` tab *is* the Cutlist module, Q474) plus admin-only `/it`. New top-level surfaces go on the **secondary strip**: `Catalog · Shop Floor · Cut Floor · QC · Estimating · Customers`. The strip hides a tab when `can(me, module, "read")` is false; the API's 403 is the real control.
- State: raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / React Hook Form / Zustand.**
- Design tokens live once in `globals.css` (`@theme inline`) and `lib/tokens.ts`. **Do not invent colours** — use `bg-h-*`, `text-h-*`, `border-h-line`. Inter for UI, JetBrains Mono (`.h-mono`) for part #, PO #, ETAs, money. No `tailwind.config.ts`.
- **Money and quantities arrive as JSON strings** (Pydantic `Decimal`). Type them `string` in `lib/*-types.ts`; typing `number` compiles then throws at `toFixed`.
- **JSX whitespace trap:** text that continues onto a second line after a `{…}` or element loses its leading space. Use a template string or `{" "}`.
- A selection with a live input beside it must change **synchronously** (local state + `history.replaceState`); do not call `history.replaceState` right after `router.refresh()` for an id not yet in the refreshed list.

## 7. Data-model invariants (binding)

- **Six separate catalog tables** (`board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`) — never unify. Common to all: `description`, `notes`, `default_supplier(_id)`, `default_lead_time_days`. `custom_made` calls its supplier column `vendor`; `equipment_hire` PK is `hire_id` and needs `project_id`. Soft-archive only; hard delete only for `cv_material_mapping`. `/catalog/*` is the only surface.
- **Number sequences, never `MAX+1`, allocated inside the INSERT:** `joinery_number_seq` (Item IDs, cutlist numbers, related parts — Q541) and `po_number_seq` (`PO-{year}-{0000}`). Neither has an owning table, so `TRUNCATE … RESTART IDENTITY` does not reset them. Per-project drawing numbers come from `workspace_counter`.
- **Terminology pins:** `Stage` = site location (`items.stage`, still written, Q435); `Zone` = sub-division of Stage; `lifecycle_stage`/`stage_key` = the production milestones (`REQ SM LISTED DOWN CNC EDGED PAINTED MADE DEL INST`, plus `PACKING` as a Shop Floor stage since `0039`) — **never use bare "stage" for these**; `Status` = record state (`CLEAR VOID NOTE! LIVE APPROVED HOLD`); `Status Symbol` = drafter-only UI flag.
- **Cutlist owns the production workflow** (Q412). Shop Floor keys on `(cutlist_id, stage_key)`. `item_stages` stays per-item as a *projection* fanned out on completion (Q439/Q562); undo reverses the whole cutlist (Q446); a late-linked item gets no backfill (Q539). DEL/INST are not Shop Floor stages (Q561).
- **Related parts** are `items` rows with `row_type='related_part'` + parent FK (one level only, DB-enforced). They never hold a cutlist number (Q417), share the parent's Group ID, and have no thread, take, QC or attachments (404). **Use `row_types.joinery_items_only(alias)`** — never a hand-written predicate.
- **Area / Room** are real project-scoped tables, Room nested under Area; composite FK `items (area_id, room_id)`.
- **CutPlan ≠ CutSchedule** (two entities). `/optimise` is a pure function (no writes); sheet stock is read, never consumed.
- **Procurement:** `purchase_orders` + `po_line_items` *are* the order layer (Q553) and `vendors` is the supplier entity (Q556). Item cost does **not** roll up (Q543). Batch status pill is derived in SQL. Allocation over-commit is 409. The legacy `/procurement/*` namespace is not used by the v1 UI.
- **Order coverage is per (quote line, material)** in `estimate_line_material_order` (row = ordered or ordered by hand; no row = pending). `estimate_line.orders_generated_at` / `orders_dismissed_*` are **derived** from it (`_refresh_line_state`) for a line that references catalog materials, and written directly only for a line with none. Never write the line columns for a materials line by hand.
- **Estimating:** `locked_at` (set once at `MGMT_APPROVAL → SUBMITTED`) is the "frozen" gate; the 12-stage tender lifecycle replaced the old six states; `advance()` is the only forward action (`/send` is retired). Cost columns are snapshotted. `current_value` of contracts is computed on read.
- **Material Take:** generated, then person-owned; approved takes are immutable (new version = n+1); boards are fractional sheets per item, rounded up once over the project (Q586).
- **Workspace isolation everywhere**: scope through `projects.workspace_id` (or the entity's own `workspace_id`); cross-workspace is **404**. Any FK to `app_user` / `vendors` / `projects` taken from a request body must be validated against the caller's workspace (it would otherwise leak names). A catalog material taken from a body goes through `catalog.queries.assert_material_in_workspace` (after the lock check, before any write): another workspace's row and a missing one both answer `404 {code: MATERIAL_NOT_FOUND}`. `POST /items/bulk-status` reports another workspace's item as `not_found`, like a missing one (there is no `cross_workspace` list).
- **Search:** the outbox is identity-only; a new searchable table needs a trigger in a migration *and* a loader in `documents.py` (a test enforces this). `codes` have typo tolerance **off**. Never index secrets, money, bank/tax fields.
- **Files:** `file_blob` is workspace-scoped, sha256-deduped, never deleted (no orphan GC), shared by shop drawings, attachments, register, samples and PO attachments. Allowed: PDF / PNG / JPEG, plus `.skp` / `.cvj` (signature **and** extension must agree). 25 MB cap. Each binder checks the mime it accepts.

- **ProjectHardwareCatalog** is a project-scoped link layer: item hardware lines reference materials *through* it (log-only governance, every add/remove audited). `ProcurementBatch → Allocations → item_hardware_line_id` answers "is this item blocked on a material?" as one join.
- **Three apps, one database:** Project Information Management (Drafter/PM/CEO; Project → Item → Module → Part + HardwareLine + lifecycle), Shop Floor Ops, Cabinet Vision integration layer. Drafter is the authoritative data-entry point.
- **Legacy `/procurement/*`** (orders, budget, approvals; ported from `legacy/procurement_api.py`) is workspace-scoped through the project-or-vendor join (`_PO_WORKSPACE_EXISTS`); `create_order` / `submit_for_approval` validate every foreign id.

## 8. API conventions

- Mutations that can be refused return `409 {detail: {code, …}}` with a stable `code`. Prefer codes-and-409 over bare strings.
- **Null-write guard:** a PATCH schema must call `schema_guards.no_null(...)` for every field whose column is `NOT NULL` (explicit `null` → 422 naming the field). A `null` written to a nullable column that a response model types non-null **poisons every later read**, because routes commit before the response is validated. Opt-in — nothing fails if you forget.
- Field-level optimistic concurrency (`concurrency.py`): PATCH may carry `expected_versions`; a stale field is `409 FIELD_CONFLICT` with a **string-safe** `current_value` (`conflict_safe_value`). Reads for PATCH use `SELECT … FOR UPDATE`.
- Computing `MAX(seq)+1` needs a parent-row lock (`FOR UPDATE`) — races found and fixed in estimate lines, order lines, material-take generate.
- `LOCKED`/frozen order statuses (`Cancelled`, `Delivered`) are read-only except `status`; `OrderOut.locked` is server-computed — the web reads it, never copies the set.
- Route ordering: literal paths (`/orders`, `/catalog/cv-mappings`) must be declared **before** parameterised ones.

## 9. Locks (Plan V1 §12) — one table

Three lock types on an item: **Hard** (`hard_locked_at`, manager/admin set it, blocks everyone incl. owner), **Approval** (derived from `status = 'APPROVED'`, no column), **Controlled** (`item_locked` + `cutlist_owner_id`; owner and manager/admin pass). All checks go through `items.queries.assert_item_content_unlocked(include_approval, include_controlled)` and run **before** anything is written, audited or logged — a refused write changes nothing. Codes: `HARD_LOCKED`, `APPROVAL_LOCKED`, `ITEM_LOCKED` (and `LOCK_REQUEST_CREATED` for `PATCH /items/{id}`, which holds the edit as a request instead of refusing).

| Write | Hard | Approval | Controlled |
| --- | :-: | :-: | :-: |
| `PATCH /items/{id}` | ✔ | ✔ | request held |
| Modules, parts, CV import commit (incl. replace), module delete | ✔ | ✔ | ✔ refused |
| Hardware lines, attachment slots, Document Register | ✔ | ✔ | ✔ refused |
| `/status`, `/bulk-status` (skips + lists locked), `/lifecycle/{stage}` | ✔ | — | ✔ |
| Answer / edit-answer a query; every material-take write | ✔ | — | ✔ |
| **Ask** a query | ✔ | — | — |

**Deliberately not locked:** QC records, comments, Material Summary, project hardware catalog, `POST /files`, Shop Floor's `item_stages` fan-out, reads and print routes. `cutlist_owner_id` is sticky — only `item_locked` matters. Web mirror: `cutlist/moduleLock.ts` (`moduleLockReason`, `lockFromError`, scopes `content | status | records`); one notice per tab, controls disabled with the reason, 409 fallback reverts the edit.

## 10. What is built

One entry per sub-project: what it is, the rule you most need, and the migration. Full history is in the named file under `docs/sub-projects/`.

### Core modules — `01-early-sub-projects.md`
- **Foundation (`0001`–`0007`, `0014`).** `0001` tracking port (users, projects, items, modules, parts, hardware lines, item stages / status / edit logs, the six catalog tables, batches and allocations); `0002` procurement port (vendors, cost centres, purchase orders + lines, attachments, approvals, budget transactions; legacy `users`, views and PO-number procedure deliberately skipped); `0003` CutPlan / sheet / part slot / CutSchedule; `0004` auth (`workspace`, `app_user`, `session`, `audit_log`); `0005` procurement user profile side-table; `0006` the four legacy views (`v_po_summary`, `v_budget_utilisation`, `v_inventory_status`, `v_orders_due`); `0007` catalog reconciliation (adds `workspace_id`, `sku`, `unit_cost`); `0014` direct `projects.workspace_id` isolation fix.
- **PM Workbench (#2/#3, `0008`–`0011`).** `/projects`, `/tracking`, item editor (`/items/[id]` tabs). Item writes need `require_drafter()` (drafter/manager/admin). Every item mutation writes `audit_log` + `item_edit_log` together. Controlled Lock replaced the soft lock (`0032`).
- **Procurement Workbench (#4, `0012`).** `procurement_v1`: project materials, batches, allocations, `/orderbook` delivery queue. Status pill derived in SQL; allocation over-commit and cancelling a batch with allocations are 409.
- **Shop Drawings (#5a, `0013`, redesign `0044`).** `/shop-dwgs` register table + details panel + full-screen viewer. Revision flow `draft → pending → approved|rejected`, approver ≠ uploader. Queues (Being drawn, Internal review…) are derived from the latest revision, never stored. `drawing_no` from `workspace_counter`.
- **PDF + attachments (#5b, `0015`, `0036`).** WeasyPrint cutlist / hardware / combined PDFs. Five attachment slots (`cv_drawing`, `sketchup`, `cabvision`, `floor_plan`, `site_measure`), one format each; Combined PDF uses only the original three.
- **iSample (#5c, `0016`).** Sample wall: `pending → approved|rejected`, reject needs a note, reviewer ≠ creator, approval ledger = filtered `audit_log`.
- **Catalog + CV mappings (#7a, `0017`).** `/catalog/*` over the six catalog tables; soft-archive only; bulk import all-or-nothing; `cv_material_mapping` is the only hard-delete.
- **CV import (#7b, `0018`).** 3-phase wizard (paste → resolve unknown codes → confirm). Resolver order: mapping → synonyms → SKU → unknown. Re-import 409s unless `replace`, which warns about comments it deletes.
- **Cut Floor (#7c, `0019`).** CutPlan + CutSchedule + Board tab. Status `planned → running → done`, cancel from planned/running; a plan with any non-cancelled schedule cannot be deleted.
- **Shop Floor (#8, `0020`, re-keyed `0030`).** Kanban + kiosk, keyed on `(cutlist_id, stage_key)`. Mark-done enforces stage order; undo within 5 min for workers. Packing is the 6th stage (`0039`).
- **Estimating (#9a, `0021`–`0023`; `0023` is team status for the dashboard).** Customers, estimates, revisioned quotes with snapshotted costs, quote PDF, Convert-to-Project. Status workflow superseded by the tender lifecycle (see below).
- **CutPlan optimiser (#9, `0024`) + board inventory (`0025`).** MaxRects multi-sheet nesting; `/optimise` is a pure function that reads sheet stock but never writes or consumes it.

### Cutlist, search, material take — `02-cutlist-search-material-take.md`
- **Cutlist + related parts + Orderbook (#10, `0026`–`0032`).** Area/Room entities, first-class Cutlist, related-part rows, orders on `purchase_orders`, one shared number sequence. Related parts never carry a cutlist number.
- **Global Search (#11, `0033`).** Meilisearch fed by a trigger-written outbox and a worker. `GET /search` is `current_user` only and drops unreadable types silently; 503 on outage.
- **Material Take → Summary (#12, `0034`).** Per-item takes (draft → approved → superseded) generated from parts/hardware, then owned by a person; project summary computed on read; confirmation is advisory.

### Tracking and item detail — `03-tracking-and-item-detail.md`
- **Tracking 2.0 (`0035`).** JID code/colour, VAR/BOQ, contractor, total; sub-tabs; bulk status (one status + required note, up to 500 items).
- **Item & Project Detail 2.0 (`0036`).** `/projects/[id]` page, contacts, lift access, item queries, Document Register, close-out (the only way to close; PATCH to Current/Hold reopens).
- **Tracking modal, Document Register UI.** Modal shows register, five slots and reference fields read-only; editing stays on the item editor.
- **Duplicate item (`0050`).** Same-project copy with its own new cutlist, status reset to `CLEAR`, QC checklist unticked; links to source via `duplicated_from_item_id`. Deleting an item removes its cutlist only if it has no production history.

### RBAC and locks — `04-rbac-and-locks.md`
- **Dynamic RBAC (`0037`).** Groups + memberships + grants in the DB, project scope only; `MATRIX` is the zero-membership fallback. Admin CRUD at `/permission-groups`, panel on `/it`.
- **RBAC sync.** `/auth/me` and Global Search read the engine, not the static matrix (workspace-wide grants only).
- **Locking + concurrency (`0040`).** Hard Lock, derived Approval Lock, field-level `expected_versions` on items, cutlists and order headers. Follow-up rounds extended lock checks to every route in the §9 table.

### Tender and QC — `05-tender-and-qc.md`
- **Tender lifecycle + financials (`0038`).** 12-stage lifecycle with `WON/LOST/WITHDRAWN`; Convert takes selected lines and creates a `project_contract`; variations append-only; actual costs derived from batches and labour.
- **QC / Rework / Packing (`0039`).** Defects, checklist, rework (one entity, `kind` internal/full; never reopens a stage), new `qc` module, Packing as an assignable stage with in-browser QR scanning.
- **QC Dashboard.** `/qc`, read-only: open defects/rework for cutlists started but not packed; records outside that scope are counted, not dropped.

### Orders and procurement — `06-orders-procurement.md`
- **PO generation from a won quote (`0041`, `0048`, `0049`, `0051`).** Groups materials by live default supplier, one draft PO per supplier per run. Coverage is **per material** (`estimate_line_material_order`): a material with a supplier orders now, one without stays pending; each can be marked "ordered by hand" with a required note (whole-line button covers all pending ones); a line is done when none is pending. Estimators can link a missing supplier from the dialog.
- **Catalog supplier link.** `default_supplier_id` editable in the grid, at create, via bulk import (exact-name match) and CV Create-new.
- **Orderbook editing + guards.** Header and line editing with field versions; `Cancelled`/`Delivered` orders are read-only except `status`; `OrderOut.locked` is server-computed; status/priority/category/vendor/project validated.
- **Legacy `/procurement/*` (`0045`–`0047`).** Cost-centre-less orders supported; deliver posts a `Release`; PATCH cannot bypass the workflow; PO attachments live in the shared file store with a download route.

### Comments — `07-comments.md`
- **Comments, mentions, notifications (`0042`, `0043`).** Threads on project, area, room, item, module and shop-drawing revision (Task/Change have no entities). One-level replies, @mentions by id, in-app bell only. Each type is gated by its own module.
- **Counts and warnings.** `comment_count` rides existing payloads; deleting a module or CV-replace warns first (advisory, API unchanged).

### Audits and CI — `08-audits-and-ci.md`
- **Null-write and POST-body audits.** PATCH nulls fixed with `no_null`; POST bodies found clean.
- **e2e repair and CI.** Whole suite verified on a fresh database; advisory Playwright job in `ci.yml`.

### Still open
Q480 SharePoint URL, Q547 drawing filename, Q550 Cars/OH&S tab, Q572 Scope tab; Task and Change comment threads (no entities); Q472 rule engine; §21's wider Procurement flow; E3 pilot-data migration. `apps/web/components/pm/TrackingGrid.tsx` is **dead code** (replaced by `ItemsTable`) — mention, don't delete.

## 11. Reference docs

`docs/sub-projects/00-foundation-and-architecture.md` (the pre-reorganisation preamble, verbatim), `docs/sub-projects/README.md` (index + the full old reference-docs list), `docs/plan-v1/{plan_v1,ALIGNMENT,OPEN-QUESTIONS}.md`, `docs/superpowers/plans/README.md`, `legacy/product_spec.md`, `legacy/trackingv2.md`, `legacy/REFINEMENT_BACKLOG.md`.

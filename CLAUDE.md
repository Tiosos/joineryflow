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
| `db/` | Alembic migrations `0001`→`0077` (head `0077_appliance_fields`) |
| `seed/` | `seed.hartwood_joinery` dev seed (workspace + 13 staff users + demo data) |
| `legacy/` | Read-only FileMaker-era prototypes. Reference only |
| `apps/api/tests/` | pytest suite (~100 files; counts drift, so none are recorded here). Shared setup: `conftest.py` + `helpers*.py` (see §3) |
| `tests/e2e/` | Playwright specs (59 spec files, plus `helpers.ts`; see §3) |
| `docs/plan-v1/` | **Plan V1**: customer's target spec, gap analysis, open questions (Q432–Q586) |
| `docs/archive/` | Archived specs + plans for built sub-projects (read `docs/archive/README.md` first); current state lives in `docs/sub-projects/` |
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
- `make test` runs pytest in parallel (`-n auto --dist loadfile`): each xdist worker builds its own `<db>_gwN` database (migrate + seed, in `conftest.py`), so your dev database is untouched. `make test-serial` runs one process against `DATABASE_URL` and TRUNCATEs `workspace`, `app_user`, `session`, `audit_log`, so re-run `make seed` afterwards.
- Without Docker: needs Python ≥3.12 (make a venv), `pip install -e ".[dev]"`, `DATABASE_URL` at a migrated Postgres, then pytest. The seed finds its sample files relative to itself, so `python -m seed.hartwood_joinery` works outside the container too.
- `search-worker` runs with **no `--reload`** — restart it after editing `app/search/`.

## 3. Testing rules

- **e2e baseline = a freshly created, migrated, seeded database.** The seed skips items that already exist, so a re-seed does not restore a lock or take an earlier run changed. The suite **is re-runnable on one database** (checked by running it twice without re-seeding; only the `search` specs, which need Meilisearch, differ): a spec that consumes or changes data builds its own — a name unique to the run (`Date.now()`), or a fixture made through the API — and asserts on that, never on a seeded row it changes. Do not add items to ALF-001 from a spec: "the first item" / "the first tracking row" of that project are what the comments, query and procurement specs open, so a fixture goes in a project of its own. CI runs the suite twice on one database (the second pass is the re-runnability guard), so a spec that only passes on a fresh database fails there. A spec puts back what it adds (`drafter_editor` deletes its part and hardware line).
- The e2e job is a **required** check on `main` (branch protection; production build, `next start`, `retries: 1` in CI). `ci.yml` skips docs-only PRs, so `ci-docs-only.yml` reports the same four job names as instant passes for them: **keep the job names in both files in sync** with the required checks. Never skip, disable or quarantine a spec to get green. A retried-and-passed spec is "flaky": read it.
- Specs run alphabetically in one worker and share state. When a spec fails, the guilty one is usually *earlier*: check `audit_log` for who touched what. Every spec must put shared state (locks, takes) back as seeded.
- Click-before-hydration and "locator matches a different element with the same role/test id" are the two recurring flake shapes. Prefer `href` + `goto`, or retry the click (`toPass`).
- A count assertion is satisfied by stale rows — reload and target by name.
- **A failing or skipped spec is not coverage.** When one goes red for a trivial-looking reason, check what it stopped guarding.
- Tests for a fix must be shown to **fail against the unfixed source**.
- Test infrastructure traps: patch **`rbac_engine.MATRIX`**, not `permissions.MATRIX`; never assert an absolute PO or Item number (sequences survive `TRUNCATE`); tests assert `stage_key`, never lookup labels.
- **Shared test setup lives in one place; do not copy it into a file.** pytest: `tests/conftest.py` re-asserts `status_options` / `stages` before every test (never seed them yourself), provides cleanup (`truncate_after` fixture, `truncate_fixture(*extra)` for extra tables), auto-skips `meili`-marked tests without `MEILI_URL`, and hashes passwords with minimal argon2 cost (the hash is still argon2id). `tests/helpers.py` is the one `login()` / `log_in(slug, email, client=)` / `login_same_workspace()` / `create_project()` / `set_item()`; `helpers_<family>.py` hold the per-feature builders. **A test file never imports from another `test_*.py`.** e2e: `tests/e2e/helpers.ts` `login(page, email = MANAGER)`; `smoke.spec.ts` keeps its inline login because login is what it tests.
- **Workspace isolation is probed for every route with a path id** (`test_workspace_isolation_probe.py`): an admin of another workspace must get exactly the answer a nonexistent id gets (status and body), so a 403, a 200 or a different message is a leak. A new id route is covered automatically. If the test says an operation was "not really probed", make it probable (seed data, `BODY_OVERRIDES`, `REAL_ID_QUERIES`) or write a dedicated test and list it in `NOT_PROBED` with the reason. The control user is the seeded admin; permission-group mutations run last because they change what that admin may do. Foreign ids inside a request *body* are probed by `test_workspace_isolation_body_probe.py` (A's admin names B's row in each FK field; B's row must be answered like a nonexistent one). Its `KNOWN_LEAKS` are open defects, not exemptions: fix the route and remove the entry. Ids in a *query string* (`?project_id=`, `?customer_id=`…) are probed by `test_workspace_isolation_query_probe.py`: a list with no path id is called by another workspace's admin with workspace A's real id, because that is the direction that leaks data (A's admin passing B's id proves nothing when B owns no rows). Both probes also fail on any 5xx (a route that crashes on a bad id answers the real and the ghost id alike, so the comparison alone would pass it). Shared machinery: `tests/helpers_probe.py`.
- CI also runs `ruff --select F401,F841,F811` over `apps/api/app` and `apps/api/tests` (an unused variable is often a dropped assertion). A fixture imported from a helper module needs `# noqa: F401`. The `search` e2e specs skip on a Meilisearch 503 locally but **fail** when `CI` is set (the CI stack starts Meilisearch).

## 4. Seed rules

- Alembic backfills touch only rows that exist at migration time; `make seed` inserts rows *afterwards*. **Every seed block that creates an item must also create its cutlist, area and room.**
- Seeds write fixed numbers then advance `joinery_number_seq` — keep that step.
- Seed through the **same query functions the API uses** so audit / edit-log rows are real. Idempotent: drop target rows first.
- **Do not seed a Hard / Approval lock** — it would break e2e specs that PATCH ALF-001 items. The one seeded Controlled-Lock *request* is on TRT-014's K-103, which no lock e2e spec uses.
- A new workspace needs `seed_system_groups()` (RBAC groups) — the seed calls it.

## 5. Auth & RBAC

- Argon2id passwords, opaque 32-byte tokens (sha256 stored), httpOnly `jf_session` cookie, sliding 14d / hard cap 30d.
- **7 roles**: `admin, manager, editor, drafter, estimator, purchase_officer, viewer`. **12 modules**: `dashboard, tracking, list, shop_dwgs, isample, orderbook` (the 6 tabs) + `catalog, cut_floor, shop_floor, estimating, qc` + admin-only `it_management`. **4 actions**: `read, write, approve, comment`.
- **Live source of truth is the DB engine** (`auth/rbac_engine.py`, groups + memberships, migration `0037`). `MATRIX` in `auth/permissions.py` is the readable record and the **fallback only for a user with zero memberships**. A user with ≥1 membership is fully DB-governed; an empty result is a real "no".
- `require_permission(module, action, project_param=None)`; most call sites check workspace-wide grants only. Project-scoped memberships are honoured only where `project_param` is passed. `/auth/me`, Global Search and comment routes use **workspace-wide grants only** (a user with only project-scoped memberships sees nothing there).
- Adding a module needs **both** a `MATRIX` entry **and** a migration inserting `group_module_grant` rows for existing workspaces.
- Per-object rules (`require_drafter()`, not-uploader-approves, creator-or-manager, 5-min undo) live in route handlers, not the engine (Q472 not built). Drafter is PM-parity on `orderbook` (**except `approve`**: deciding an order, `Approved` / `Rejected`, is purchase officer, manager and admin, `0054` / `0056`), `shop_dwgs`, `isample`, `catalog`, `cut_floor`.
- Every authenticated mutation writes `audit_log` (`auth/audit.py`); item-scoped mutations also write `item_edit_log` in the same transaction.
- `jtbd_role` is display-only; nothing branches on it.

## 6. Web shell

- Browser → Next.js Route Handler (`app/api/[...proxy]/route.ts`) → FastAPI. **The browser never calls FastAPI directly.** `proxy.ts` enforces login redirect.
- `(app)/layout.tsx` does server-side `fetchMe()` and renders chrome. Editor mode (`/items/[id]`) hides TabStrip + SideBar. The project SideBar shows on Dashboard only (`HAppChrome.SIDEBAR_ROUTES`); Tracking (header bar) and Shop Dwgs (filter row) have their own project switchers and need the width.
- **IA is fixed: 6 primary tabs** `Dashboard · Tracking · List · Shop Dwgs · iSample · Orderbook` (the `List` tab *is* the Cutlist module, Q474) plus admin-only `/it`. New top-level surfaces go on the **secondary strip**: `Catalog · Shop Floor · Cut Floor · QC · Estimating · Customers`. The strip hides a tab when `can(me, module, "read")` is false; the API's 403 is the real control.
- State: raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / React Hook Form / Zustand.**
- Design tokens live once in `globals.css` (`@theme inline`) and `lib/tokens.ts`. **Do not invent colours** — use `bg-h-*`, `text-h-*`, `border-h-line`. Inter for UI, JetBrains Mono (`.h-mono`) for part #, PO #, ETAs, money. No `tailwind.config.ts`.
- **Money and quantities backed by a Pydantic `Decimal` arrive as JSON strings.** Type them `string` in `lib/*-types.ts`; typing `number` compiles then throws at `toFixed`. A field the API declares `float` or `int` (e.g. `unit_cost`/`qty` in `lib/pm-types.ts`, from `hardware_lines`) arrives as a JSON number and is typed `number`. Check the Pydantic type, not the name.
- **Risky actions confirm through `useConfirm()`** (`components/confirm/ConfirmProvider`, mounted in `(app)/layout.tsx`): `if (!(await confirm({ title, message, confirmLabel }))) return;`, or `askReason({...})` when a reason is needed. Do not add `window.confirm` / `window.prompt` for delete, archive, cancel, reject or close-out. e2e specs answer it with `getByTestId("confirm-dialog-confirm")`, not `page.on("dialog")`.
- **Names and small forms ask through the same provider**: `askText({ title, label, initial, required })` (one box) and `askFields({ title, fields })` (several), both neutral-toned, resolving the trimmed text or `null` on cancel. No `window.prompt` / `window.confirm` is left in the web app; `window.alert` for errors still is.
- **JSX whitespace trap:** text that continues onto a second line after a `{…}` or element loses its leading space. Use a template string or `{" "}`.
- A selection with a live input beside it must change **synchronously** (local state + `history.replaceState`); do not call `history.replaceState` right after `router.refresh()` for an id not yet in the refreshed list.

## 7. Data-model invariants (binding)

- **Catalog now has nine tables (Oct 2026): Edging (`edging_materials`, `0069`, kind `EDGING`, slug `edging-materials`), Glass (`glass_materials`, `0070`, kind `GLASS`, slug `glass-materials`; a *part* kind on quotes, like Custom and Benchtop) and Solid Timber (`timber_materials`, `0074`, kind `TIMBER`, slug `timber-materials`; a *part* kind on quotes too) have tables of their own**, on top of the six below (tabs `?tab=edging` / `?tab=glass` / `?tab=timber`). Step 2 continues one type at a time; each new table must be added to every place a material is picked (see `docs/sub-projects/09-e3-pilot-data-import.md`, "Step 2, Edging", for the list) and to the CHECK constraints that name the kinds.
- **Catalog tabs are product types (user decision, Oct 2026; step 1 of 2).** The Catalog screen's tabs come from `product_type` (`GET /catalog/product-types`, `/catalog/by-type`); the nine tables below still hold the rows. The user's plan is one table per type with its own fields, done one type at a time and now complete (all 14 types done): nine physical tables (the six original ones plus Edging, Glass and Solid Timber), because **Delivery** (delivery fees and surcharges, not materials), **Supplies**, **Paint**, **TG Solid**, **Laminate** and **Contractor Manufacturing** (no field Hardware, Board, Benchtop or Custom lacks) **stay tabs without a table of their own**; a type added later may get a table when it needs its own fields: that makes a tenth table, so do not add features that assume nine tables without checking `docs/sub-projects/09-e3-pilot-data-import.md`.
- **Nine separate catalog tables** (`board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`, plus `edging_materials`, `glass_materials`, `timber_materials`) — never unify. Common to all: `description`, `notes`, `default_supplier(_id)`, `default_lead_time_days`. `custom_made` calls its supplier column `vendor`; `equipment_hire` PK is `hire_id` and needs `project_id`. Soft-archive only; hard delete only for `cv_material_mapping`. `/catalog/*` is the only surface. `unit_cost` (per unit, ex GST; the API sends a JSON number, a PATCH `null` clears it) is what Generate Orders and "add from catalog" start an order line's price from, and the Catalog grid has a Unit cost column to edit it. `product_type` (`0067`, free text up to 64, nullable, on all six tables) keeps the old system's finer type (Glass, Supplies, Paint, Laminate Benchtop...) beside the tab; the grid shows and edits it, filters by it, and the search box matches it. **Board (`0068`)**: `board_materials` keeps serving the Board and Laminate types and gains the old Orders screen's board fields (`colour`, `substrate`, `finish`, `sided`, `grain` as text beside the `grain_locked` switch, `rating`, `hmr`, `um` (`0075`), `product_website`, plain text, nullable), the **sheet size and thickness** (`sheet_len_mm`, `sheet_wid_mm` whole mm, `thickness_mm` numeric(6,2); columns since `0001`, now shown and edited, no migration; JSON numbers on the wire; PATCH `null` clears each) and one picture (`image_blob`, `PUT/GET/DELETE /catalog/board-materials/{id}/image`, PNG/JPEG, `has_image` on the row); they show in the Board grid and the New dialog. **Laminate stays a tab over `board_materials` for good** (settled Oct 2026: its old order screen is Board's fields plus UM, so it has no field or table of its own; `um` is why `0075` exists). Board orders do not store them (the pop-up shows them from the catalog, see Order pop-up tabs). **Edging (`0069`)**: `edging_materials` = the common catalog columns (`sku`, `description`, `cost_per_unit`, supplier link, `unit_cost`, `product_type`, synonyms, archive) plus `colour`, `edge_type` (the old screen's "Type"), `roll_length_m`, `edge_width_mm`, `edge_thickness_mm` (numbers; JSON numbers on the wire), `glued` (NOT NULL), `um`, `product_website` and one picture (`image_blob`; `PUT/GET/DELETE /catalog/{board-materials|edging-materials}/{id}/image`). The migration moved the Hardware rows typed Edging over keeping their ids and re-pointed every (material type, id) reference. Edging orders do not store the fields (shown from the catalog). **Glass (`0070`)**: `glass_materials` = the common columns plus `length_mm`, `width_mm`, `thickness_mm` (numbers), `colour`, `edge_finish`, `glass_type` and `power_point` (free text, not pick lists), `shaped` (NOT NULL), `um`, `product_website` and one picture (image routes as Edging's); the Custom rows typed Glass moved over keeping their ids (`vendor` became `supplier`, `cost` became `cost_per_unit`). Glass orders do not store the fields (shown from the catalog). **Laminate Benchtop (`0071`)**: `benchtop_materials` keeps serving the Laminate Benchtop type (and TG Solid, which stays a tab over this table for good: it has no field of its own, settled Oct 2026; Solid Timber moved out in `0074`) and gains `colour`, `underside`, `edge_details`, `laminate_supplier`, `laminate_code`, `finish`, `um`, `product_website` (text), `bench_length_mm`, `bench_width_mm` (the existing `thickness_mm` is the bench thickness; `slab_*` stay the supplier's slab), `pieces`, `joins`, `cable_entry` (integers), `shaped` (NOT NULL) and one picture (image routes as Board's). Benchtop orders do not store the fields (shown from the catalog). **Hardware (`0072`)**: `hardware_materials` keeps serving the Hardware type (and, until their own turns, Supplies and Paint); `brand` and `hardware_type` (columns since `0001`) are now shown and edited, and it gains `um`, `product_website` and one picture (image routes as Board's). Hardware orders do not store the fields (shown from the catalog). **Custom (`0073`)**: `custom_made` keeps serving Contractor Manufacturing (and Delivery) and gains `um`, `product_website` and one picture (image routes as Board's); Contractor Manufacturing gets no table of its own (its order screen has no field Hardware lacks). Custom orders do not store the fields (shown from the catalog). **Equipment Hire (`0076`)**: `equipment_hire` stays its own table (PK `hire_id`, needs `project_id`) and gains `um`, `product_website` and one picture (image routes as Board's, keyed on `hire_id`; `has_image` on the row); the old PLANT HIRE order screen has no other field. Hire orders do not store the fields (shown from the catalog). **Appliance (`0077`)**: `appliances` stays its own table (PK `material_id`) and gains `um`, `product_website` and one picture (image routes as Board's; `has_image` on the row); the old order screen for an appliance (order type HARDWARE) has no other field. Appliance orders do not store the fields (shown from the catalog). **Solid Timber (`0074`)**: `timber_materials` = the common columns (as Glass's) plus `colour`, `finish`, `grain` and `rating` (free text, as Board's; no `substrate`, `sided`, `hmr` or `grain_locked`), `thickness_mm`, `width_mm`, `length_mm` (numbers; JSON numbers on the wire), `um`, `product_website` and one picture (image routes as Edging's). The Benchtop rows typed Solid Timber (5 in the pilot data) moved over keeping their ids (`cost_per_slab` became `cost_per_unit`; `bench_length_mm` / `bench_width_mm` became `length_mm` / `width_mm`) and every (material type, id) reference was re-pointed from BENCHTOP to TIMBER; the quote *part* check accepts `TIMBER` because those rows were already quote parts. Solid Timber orders (the Orderbook pop-up and the Timber pressing form) do not store the fields (the pop-up shows them from the catalog).
- **Number sequences, never `MAX+1`, allocated inside the INSERT:** `joinery_number_seq` (Item IDs, cutlist numbers, related parts — Q541) and `po_number_seq` (`PO-{year}-{0000}`). Neither has an owning table, so `TRUNCATE … RESTART IDENTITY` does not reset them. Per-project drawing numbers come from `workspace_counter`.
- **Terminology pins:** `Stage` = site location (`items.stage`, still written, Q435); `Zone` = sub-division of Stage; `lifecycle_stage`/`stage_key` = the production milestones (`REQ SM LISTED DOWN CNC EDGED PAINTED MADE DEL INST`, plus `PACKING` as a Shop Floor stage since `0039`) — **never use bare "stage" for these**; `Status` = record state (`CLEAR VOID NOTE! LIVE APPROVED HOLD`); `Status Symbol` = drafter-only UI flag.
- **Cutlist owns the production workflow** (Q412). Shop Floor keys on `(cutlist_id, stage_key)`. `item_stages` stays per-item as a *projection* fanned out on completion (Q439/Q562); undo reverses the whole cutlist (Q446); a late-linked item gets no backfill (Q539). DEL/INST are not Shop Floor stages (Q561).
- **Items are soft-deleted** (`items.deleted`, `cutlist.deleted`, `0052`): `DELETE /items/{id}` flags the item, its related parts and its cutlist (once no live item is left in it); `POST /items/{id}/restore` (manager/admin) undoes it; a related part is soft-deleted the same way (`DELETE /related-parts/{id}`) and cannot be restored while its parent is deleted (`409 PARENT_DELETED`). A Hard Lock refuses the delete (`409 HARD_LOCKED`). A deleted item answers 404 everywhere. **Every SQL string that reads `items` or `cutlist` takes `row_types.not_deleted` / `live_joinery_items`** (`tests/test_items_deleted_filter.py` fails on one that does not); the only readers of deleted rows are `restore_item` and Tracking's Deleted list (`?deleted=true`).
- **Factories** (`factory`, `items.factory_id`, `0053`) are a per-workspace lookup of where work is made (`TG`, `SI`…); not users, no admin screen yet. `items.tg_solid` is a per-item tag, separate from `solid_surface_req`; `items.legacy_item_ref` keeps FileMaker's old id. Imported FileMaker numbers are kept as they are (`items.num`, `cutlist.cutlist_no`) and `joinery_number_seq` is moved past them (E3).
- **Related parts** are `items` rows with `row_type='related_part'` + parent FK (one level only, DB-enforced). They never hold a cutlist number (Q417), share the parent's Group ID, and have no thread, take, QC or attachments (404). **Use `row_types.joinery_items_only(alias)`** — never a hand-written predicate.
- **Area / Room** are real project-scoped tables, Room nested under Area; composite FK `items (area_id, room_id)`.
- **CutPlan ≠ CutSchedule** (two entities). `/optimise` is a pure function (no writes); sheet stock is read, never consumed.
- **Procurement:** `purchase_orders` + `po_line_items` *are* the order layer (Q553) and `vendors` is the supplier entity (Q556). Item cost does **not** roll up (Q543). Batch status pill is derived in SQL. Allocation over-commit is 409. The legacy `/procurement/*` namespace was **retired** in October 2026 (code kept as reference in `legacy/procurement_v0/`, not mounted).
- **Order coverage is per (quote line, material)** in `estimate_line_material_order` (row = ordered or ordered by hand; no row = pending). `estimate_line.orders_generated_at` / `orders_dismissed_*` are **derived** from it (`_refresh_line_state`) for a line that references catalog materials, and written directly only for a line with none. Never write the line columns for a materials line by hand.
- **Estimating:** `locked_at` (set once at `MGMT_APPROVAL → SUBMITTED`) is the "frozen" gate; the 12-stage tender lifecycle replaced the old six states; `advance()` is the only forward action (`/send` is retired). Cost columns are snapshotted. `current_value` of contracts is computed on read.
- **Quote PDF cache (`0062`):** `quote_pdf_cache` keeps the last PDF per revision, keyed on the SHA-256 of the rendered HTML (`estimating/pdf.py::cached_quote_pdf`), so an edit, a status change or a new day re-renders and anything else is served from the table. WeasyPrint costs about 6 s per 300 lines and 12 s per 800 (a straight line); the HTML render is cheap.
- **Material Take:** generated, then person-owned; approved takes are immutable (new version = n+1); boards are fractional sheets per item, rounded up once over the project (Q586).
- **Workspace isolation everywhere**: scope through `projects.workspace_id` (or the entity's own `workspace_id`); cross-workspace is **404**. Any FK to `app_user` / `vendors` / `projects` taken from a request body must be validated against the caller's workspace (it would otherwise leak names). A catalog material taken from a body goes through `catalog.queries.assert_material_in_workspace` (after the lock check, before any write): another workspace's row and a missing one both answer `404 {code: MATERIAL_NOT_FOUND}`. `POST /items/bulk-status` reports another workspace's item as `not_found`, like a missing one (there is no `cross_workspace` list).
- **Search:** the outbox is identity-only; a new searchable table needs a trigger in a migration *and* a loader in `documents.py` (a test enforces this). `codes` have typo tolerance **off**. Never index secrets, money, bank/tax fields.
- **Files:** `file_blob` is workspace-scoped, sha256-deduped (an upload that loses the dedup race adopts the winner's row, `files/blobs.py`, and never deletes bytes another row points at), never deleted (no orphan GC), shared by shop drawings, attachments, register, samples and PO attachments. Allowed: PDF / PNG / JPEG, plus `.skp` / `.cvj` (signature **and** extension must agree). 25 MB cap. Each binder checks the mime it accepts. **A blob has no name of its own**: identical bytes are one row, so `original_filename` is whoever uploaded them first; a row that points at a blob shows its type (or keeps its own `file_name`, as `po_attachments` does), never the blob's name.

- **ProjectHardwareCatalog** is a project-scoped link layer: item hardware lines reference materials *through* it (log-only governance, every add/remove audited). `ProcurementBatch → Allocations → item_hardware_line_id` answers "is this item blocked on a material?" as one join.
- **Three apps, one database:** Project Information Management (Drafter/PM/CEO; Project → Item → Module → Part + HardwareLine + lifecycle), Shop Floor Ops, Cabinet Vision integration layer. Drafter is the authoritative data-entry point.
- **Order decision (`0056`)**: the software runs **no approval process** (the 0054/0055 flow was removed in October 2026). An order added in the Orderbook starts `Pending` (orders generated from a won quote start `Draft`). A purchase officer, manager or admin (the `orderbook:approve` grant; the drafter has none) reviews it and sets `Approved` or `Rejected` by hand; any sign-off from a manager or admin happens outside the software. That grant covers setting either status and moving an order out of either, **cancelling (`DELETE /orders/{id}`) included** (`403 DECISION_FORBIDDEN`); everyone with `orderbook:write` edits the rest. `Rejected` needs a `rejection_note` (`409 REJECTION_NOTE_REQUIRED`; refused with any other status, `409 REJECTION_NOTE_NOT_APPLICABLE`; cleared when the order leaves Rejected); who changed a status and when is in `audit_log` (`order.update`), there are no "approved by" columns. Order size no longer matters: the approval limit, the PM flag, `needs_approval` and the "Delivered needs Approved" rule are gone. **The budget commitment follows the order** (`orders/budget.py::sync_commitment`): an order commits its total against `purchase_orders.cost_center_id` **while it is Approved**. Approving posts a `Commitment`; a later change to the total (header or line) or a move out of Approved posts the difference (a negative `Release`, which is how the ledger takes money back); choosing the cost centre after approval commits then. No cost centre = nothing. Cancelling releases what is outstanding (cancelling a Delivered order also takes its spend back, a negative `Expenditure`) and delivering posts the total as an `Expenditure` and releases it (`settle_on_close`, once per order); an order that already has an Expenditure is not committed again if it is reopened. A cost centre is optional on an order (Q563): `GET/POST /cost-centers` and `PATCH /cost-centers/{id}` (create, rename, switch off: purchase officer/admin; no delete; an inactive one stays on the orders that have it and cannot be chosen again, a rename shows on them at once). The ledger figures `budget_amount` / `committed` / `spent` / `remaining` are for **managers and admins only**: `GET /cost-centers` and the create / rename replies leave them out (not zeros) for everyone else, and the Orderbook shows none of them and has no budget editor (October 2026; see the next entry); the budget informs and never blocks. `PATCH /orders/{id}` `{cost_center_id}` must be this workspace's and active, and is frozen once any budget row is posted for the order (`409 COST_CENTER_LOCKED`). The seed makes one cost centre (`GEN`). **Order priority has three levels, `High`, `Medium`, `Low`** (`0058`): `Next`, `Hold` and `Quote` are order *statuses* only (the status check already allows them); orders that carried one as a priority were set to `Medium` and kept their status. **Orders waiting for a decision** are shown to the `purchase_officer` role only (the customer's choice, not every `orderbook:approve` holder): `GET /notifications` adds `orders_waiting` (newest 20) and `orders_waiting_count` for that role while it can read the Orderbook, on a first (`offset=0`), not unread-only page only (a separate reply model, `NotificationListWaitingOut`; everyone else gets `NotificationListOut`), the bell badge counts them (labelled "need attention", not "unread") and lists them above the comment notifications. They are derived from `status = 'Pending'` on every call (new, or moved back to Pending; a `Draft` is not waiting), so there is no table, no read state, and an order leaves the list the moment it is Approved, Rejected or Cancelled.
- **Orderbook like the old screen; budget on Tracking > Info (`0057`)**: the Orders list is grouped under the order type with the old columns and a row of buttons (**RTO** = Approved and not yet ordered, **TBO** = open and not yet ordered, Due / Over Due / Arrived / My Orders: client-side filters over the loaded list; **New** opens the order pop-up layout as a form and `Create order` saves a Pending order, project optional; **Supplier** opens the supplier list with edit and add over `GET/POST/PATCH /suppliers`; **Po** puts the ticked orders on a PO document (see the next entry)); a row opens the order as a **pop-up** (`?order=` still selects it) with the fields every order has, the type's own fields (`Acoustic`, `Benchtop`: in `attributes`; every other type, `Contractor` included, shows the description) and the old screen's tabs (see the next entry; **FILE / PDF** on HOME hold the order's files, see `orders/attachments.py`: `GET/POST /orders/{id}/attachments`, `GET …/{aid}/download`, `DELETE …/{aid}`, gated by `orderbook`, a Cancelled / Delivered order's files are read-only, same file rules as `POST /files`, the PDF box takes PDF only). `0057` adds the `Acoustic` ("Acoustic panel") and `Contractor` ("Contractor-manufacturing") order categories; `0066` adds the 13 other types of the old system's Order Type list (Contractor Install, Corian Clad, Delivery, Edging, Extra, Equipment, Glass, Laminate, Maintenance, Stone Clad, Solid Surface, Supplies, Wages), kept beside the types the old list lacks. **Money by material type**: `GET /orders/cost-breakdown` (`orderbook:read`, every order but Cancelled and Rejected) feeds the Orderbook's small **Cost centre** button, a pop-up with a collapsible table open by default; `GET /projects/{id}/budget` (**manager and admin only**, `403 BUDGET_FORBIDDEN`, another workspace's project a 404) feeds the **Budget tab of Tracking > Info** with the labour-hours tables blank (Q571, payroll not connected).
- **Order pop-up tabs (`0064`)**: HOME plus **Delivery** (`order_delivery`: one row per delivery received with qty, date, signed by, notes and a docket file; Sum received and Tot remaining are worked out; Received by = `purchase_orders.received_by`, Date delivered = `arrived_date`; the log is a record, it never changes the status, and a Cancelled / Delivered order's log is read-only, `409 ORDER_LOCKED`), **Stock** (stock-tracked orders of the same product code, not Cancelled / Rejected), **Tracking** (the linked item: name, MADE date, number, and the order's own number), **Supplier** (the supplier's company card: logo, website, notes, metadata, read-only here, edited in the Supplier list; `vendors.logo_blob/website/notes/metadata`), **Cutlists** (cutlists whose items use the product, found by the order's product code = a catalog SKU, through parts for boards and hardware lines for every catalog table) and **ADMIN** (`cancelled_at / cancelled_by / cancel_reason`, stamped whenever an order becomes Cancelled by the status or `DELETE /orders/{id}?reason=`, cleared when it leaves Cancelled; the pop-up asks for the reason). **Product image** = `purchase_orders.image_blob`, one PNG/JPEG (`PUT/GET/DELETE /orders/{id}/image`). **Glass C** (`0065`) is a price calculator: `glass_rate` is the per-workspace price list (kept by a purchase officer or admin; `glass` rates per m2, `process` rates per metre of perimeter `Lm` or per each), an order keeps its size and ticks (`order_glass_calc`), and the cost is worked out on every read (qty × rate × area / perimeter / 1, lines rounded to cents, the total from the unrounded sum: $63.25 + $15.96 shows $79.22); the total is shown, never written to the order; Copy Size reads `1471 x 1000 x 6` from the start of the description. **Timber** is the Timberwood Panels pressing form (`order_timber_form`; CREATE makes and keeps a PDF, CLEAR saves empty fields). **TGSolid** is a table of production rows (`order_tg_run`), a record only. A Cancelled / Delivered order's Delivery, Glass C, Timber and TGSolid are read-only. Routes live in `order_tabs/`. History: `docs/sub-projects/06-orders-procurement.md`. **HOME shows the catalog item behind the product code (2026-10-18; no migration, nothing stored on the order)**: `GET /orders/{id}/catalog-item` (`orderbook:read`; another workspace's order is a 404 like a missing one) returns `{items: [...]}`, every catalog row of this workspace whose SKU equals the order's product code (trimmed, case-insensitive, SKU also trimmed), across all nine tables in the fixed order `order_tabs.queries.CATALOG_MATCH_ORDER` (a test pins it to `catalog.queries.REGISTRY`), live rows before archived ones; Equipment Hire rows match only the order's own project (an order with no project matches none); no code or no match is `{items: []}`, never a 404. Each item has `type` (table key), `sku`, `description`, `product_type`, `um`, `product_website`, `archived`, `has_image` and `fields` = the type's own fields taken from the catalog's `*_FIELDS_TUPLE`s (no money, notes or supplier columns). A board's three sizes show as one `Sheet size (mm)` line, `3600 x 1200 x 0.7`, when all are set. The picture is `GET /orders/{id}/catalog-item/image?n=` (`orderbook:read`, not `catalog`): it serves the picture of the order's n-th match only, so an order cannot reach an arbitrary catalog picture. The pop-up's `CatalogItemBlock` shows the first match, notes the others, links the website only when it is http(s), and re-fetches when the product code is edited. **Orders still do not copy or edit these fields**; the catalog is the only place they live. History: `docs/sub-projects/09-e3-pilot-data-import.md`.
- **PO documents (`0059`)**: `po_document` is the header over the order layer (`purchase_orders` stays one row per ordered item). A PO groups **open orders of one supplier** (`409 SUPPLIER_MISMATCH` / `ORDER_NOT_OPEN` / `ORDER_ALREADY_ON_PO`) and marks them ordered (`date_ordered`); its number is a plain running number from `po_document_no_seq` (started at 100001; `0060` moved it past the old system's last PO number, 193970, so the next PO is 193971). `Reference no.` is hand-typed text. The **delivery charge is a real `Delivery Fee` order** on the PO (`PUT/DELETE /purchase-orders/{id}/delivery`), so it commits against a budget like any order. Totals skip Cancelled / Rejected lines. An order on a PO keeps its supplier (`409 ORDER_ON_PO`). Cancelling the PO frees its orders and cancels the Delivery Fee order, and is refused while the PO has invoices (`409 PO_HAS_INVOICES`). The Date ordered a PO gives an order is remembered (`purchase_orders.date_ordered_from_po`, `0061`): leaving the PO takes away only that date (and versions it), never a hand-typed one, and never a Cancelled / Delivered order's; editing the date on the order turns the flag off. A Delivery Fee order cancelled in the Orderbook is no charge (`delivery_charge` is null) and `PUT /delivery` replaces it. `vendor_contact` holds a supplier's contacts (`/suppliers/{id}/contacts`); `po_invoice` is the Invoice Details table (keyed to a PO line). `GET /purchase-orders/{id}/pdf | excel`. **Email Details is a `mailto:` link**: the PDF cannot be attached from a browser, so the user attaches it. Ticked staff are its `cc=`; their emails come from `GET /purchase-orders/staff` (`orderbook:read`), never from the open `/workspace/team`. Reads need `orderbook:read`, writes `orderbook:write`. **Invoice Details window (`0063`)**: ticking *Invoiced* on a line (or opening a row of the Invoice Details table) opens it; an invoice has a Payment Method, Qty, Total Cost (Ex), GST and Inc, notes and three file boxes (Delivery Doc, Invoice Doc, Non Delivery: `POST/GET/DELETE …/invoices/{id}/files/{delivery|invoice|non_delivery}`, PDF/PNG/JPEG). **GST is the server's**: 10% of Ex while `gst_auto`, else the typed figure; Inc = Ex + GST (Ex is typed, or ↻ = qty × the line's cost, in the window). A line can have several invoices (*+ Add*). **Authorisation Form Details window (`0063`)**: `po_authorisation`, one row per PO (`GET/PUT …/authorisation`): payment type, a deposit % **or** an amount (`409 DEPOSIT_BOTH`), date required by, on behalf of (a staff member); *Create Form* (`POST …/authorisation/form`) renders the PDF from the saved details and keeps it; the hand-signed scan goes in *Signed Form* (`…/authorisation/signed`). The old blank `/authorisation-form` is gone. **Payment Method / Payment Type** is one per-workspace list, `payment_method` (`GET/POST/PATCH /payment-methods`; purchase officer or admin keep it, like cost centres; a switched-off entry stays on rows that have it; seeded: Account, Credit card, Deposit, COD / Pay on delivery). **Staff photos**: an admin sets `app_user.photo_file_blob_id` on /it (`PUT/DELETE /users/{id}/photo`, PNG/JPEG); the PO staff list shows it (`GET /purchase-orders/staff/{id}/photo`). History and assumptions: `docs/sub-projects/06-orders-procurement.md`.
- **Legacy `/procurement/*`** is retired and unmounted; its tables stay (Q435). The home dashboard's `pending_approvals` tile counts `Pending` orders (`/orderbook?status=Pending`); the Overdue / This Week tiles open the Delivery queue with `?eta=`, and the Open POs tile opens the Orders list with `?status=open` ("not Delivered, Cancelled or Rejected", `orders.queries.open_orders_sql`, shared with the tile). Reference: `legacy/procurement_v0/README.md`.

## 8. API conventions

- Mutations that can be refused return `409 {detail: {code, …}}` with a stable `code`. Prefer codes-and-409 over bare strings.
- **Null-write guard:** a PATCH schema must call `schema_guards.no_null(...)` for every field whose column is `NOT NULL` (explicit `null` → 422 naming the field). A `null` written to a nullable column that a response model types non-null **poisons every later read**, because routes commit before the response is validated. Opt-in — nothing fails if you forget.
- Field-level optimistic concurrency (`concurrency.py`): PATCH may carry `expected_versions`; a stale field is `409 FIELD_CONFLICT` with a **string-safe** `current_value` (`conflict_safe_value`). Reads for PATCH use `SELECT … FOR UPDATE`.
- **Dynamic SQL names need an allow-list.** Values are always bound parameters; column and table names cannot be. An f-string `UPDATE … SET {list}` (or an interpolated table / column) must take its names from a fixed set: `sql_columns.require_columns(keys, ALLOWED)`, a filter `if k in <CONSTANT>`, a column map (`columns[k]`), or keys that are the declared fields of a request model (`payload.model_dump(...)`; no PATCH model may use `extra="allow"`). `tests/test_sql_set_columns.py` fails on a statement with none of these; one that is safe for another reason goes in its `ALLOWED` with the reason.
- **Workspace checks come from `workspace_scope.py`** (`project_in_workspace`, `user_in_workspace`, `vendor_in_workspace`): a new route imports them instead of writing the `SELECT 1 … AND workspace_id` again; older modules move over as they are touched (no big-bang rewrite). Item and catalog-material checks have their own helpers.
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
| `DELETE /items/{id}` (soft delete; restore is never refused) | ✔ | — | — |

**Held saves (Controlled-Lock requests)** are decided by the lock owner, a manager or an admin (drafter, manager, admin only: `require_drafter`): the item editor shows a banner with Approve / Reject, and `GET /notifications` lists them (`lock_requests_waiting`, derived, no read state) in the bell for those people. History: `docs/sub-projects/04-rbac-and-locks.md`.

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
- **Duplicate item (`0050`).** Same-project copy with its own new cutlist, status reset to `CLEAR`, QC checklist unticked; links to source via `duplicated_from_item_id`. Deleting an item is a soft delete (next entry).
- **Item soft delete + Deleted chip (`0052`).** Delete flags item, related parts and (when empty) cutlist; manager/admin restore; Tracking's Deleted chip lists them read-only with Restore; a Delete button joins the selection group and the item editor's header. Rule in §7; production history, QC and orders are untouched.

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
- **Legacy `/procurement/*` (`0045`–`0047`, retired Oct 2026).** Cost-centre-less orders supported; deliver posts a `Release`; PATCH cannot bypass the workflow; PO attachments live in the shared file store with a download route.

### Comments — `07-comments.md`
- **Comments, mentions, notifications (`0042`, `0043`).** Threads on project, area, room, item, module and shop-drawing revision (Task/Change have no entities). One-level replies, @mentions by id, in-app bell only. Each type is gated by its own module.
- **Counts and warnings.** `comment_count` rides existing payloads; deleting a module or CV-replace warns first (advisory, API unchanged).

### Data migration (E3) — `09-e3-pilot-data-import.md`
- **FileMaker Tracking 2.0 importer (`0053`).** `python -m app.importers.tracking_grid FILE.xlsx …` imports one project's items, cutlists, areas, rooms, stage dates (done dates; REQ is a due date), statuses and factories, keeping FileMaker's item and cutlist numbers. A dry run does the real inserts and rolls back; `--commit` keeps them and writes one audit row. Customer exports are never committed. Only the item grid is covered here (an installed item also gets REQ done, or Tracking's Overdue counts it). **Orders grid (second slice):** `python -m app.importers.orders_grid FILE.xlsx …` imports one project's orders (one `purchase_orders` row per FileMaker row, `OrderNumber` kept as `order_number` and shown in the Orders list's **Order no.** column, no PO documents; the requester is matched to a staff member by first name or kept in internal comments; an order is linked to an item only when its cutlist has exactly one; mapping in the module docstring and `docs/sub-projects/09-e3-pilot-data-import.md`). **Catalog (third slice):** the old catalog could not be exported, so `python -m app.importers.catalog_from_orders propose ORDERS.xlsx --out review.xlsx` guesses a catalog table per product code on the orders, a person corrects the sheet, and `… import review.xlsx --workspace-slug … --actor-email … [--commit]` writes code, SKU (= the code the Cutlists tab matches on), description, supplier, unit cost (the latest order's line total ÷ quantity, ex GST; a 0 stays 0) and the optional Type column (`product_type`) through the catalog's own insert; no equipment hire. Modules, parts, hardware, drawings and QC still need their own exports.

### Audits and CI — `08-audits-and-ci.md`
- **Null-write and POST-body audits.** PATCH nulls fixed with `no_null`; POST bodies found clean.
- **e2e repair and CI.** Whole suite verified on a fresh database; Playwright job in `ci.yml` (required check on `main` since PR #81).

### Still open
PO approval: cost centres have no delete, no report across cost centres and no hard budget limit. See `docs/sub-projects/06-orders-procurement.md`. Q480 SharePoint URL, Q547 drawing filename, Q550 Cars/OH&S tab, Q572 Scope tab; Task and Change comment threads (no entities); Q472 rule engine; §21's wider Procurement flow; the rest of E3 (see above). E3's first slice (the item grid) is built; the rest of the pilot data is open.

## 11. Reference docs

`docs/sub-projects/00-foundation-and-architecture.md` (the pre-reorganisation preamble, verbatim), `docs/sub-projects/README.md` (index + the full old reference-docs list), `docs/plan-v1/{plan_v1,ALIGNMENT,OPEN-QUESTIONS}.md`, `docs/archive/README.md`, `legacy/product_spec.md`, `legacy/trackingv2.md`, `legacy/REFINEMENT_BACKLOG.md`.

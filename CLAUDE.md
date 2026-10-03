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
| `db/` | Alembic migrations `0001`→`0050` (head `0050_item_duplicated_from`) |
| `seed/` | `seed.hartwood_joinery` dev seed (workspace + 13 staff users + demo data) |
| `legacy/` | Read-only FileMaker-era prototypes. Reference only |
| `tests/e2e/` | Playwright specs (see §3) |
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
- Without Docker: needs Python ≥3.12 (make a venv), `pip install -e ".[dev]"`, `DATABASE_URL` at a migrated Postgres, then pytest (~13 min).
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
- **Estimating:** `locked_at` (set once at `MGMT_APPROVAL → SUBMITTED`) is the "frozen" gate; the 12-stage tender lifecycle replaced the old six states; `advance()` is the only forward action (`/send` is retired). Cost columns are snapshotted. `current_value` of contracts is computed on read.
- **Material Take:** generated, then person-owned; approved takes are immutable (new version = n+1); boards are fractional sheets per item, rounded up once over the project (Q586).
- **Workspace isolation everywhere**: scope through `projects.workspace_id` (or the entity's own `workspace_id`); cross-workspace is **404**. Any FK to `app_user` / `vendors` / `projects` taken from a request body must be validated against the caller's workspace (it would otherwise leak names).
- **Search:** the outbox is identity-only; a new searchable table needs a trigger in a migration *and* a loader in `documents.py` (a test enforces this). `codes` have typo tolerance **off**. Never index secrets, money, bank/tax fields.
- **Files:** `file_blob` is workspace-scoped, sha256-deduped, never deleted (no orphan GC), shared by shop drawings, attachments, register, samples and PO attachments. Allowed: PDF / PNG / JPEG, plus `.skp` / `.cvj` (signature **and** extension must agree). 25 MB cap. Each binder checks the mime it accepts.

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

## 10. What is built (and where its history lives)

Each row's detail is in `docs/sub-projects/`. Migrations are named in the file.

| Area | Migrations | Detail file |
| --- | --- | --- |
| Foundation, PM Workbench, Procurement Workbench, Shop Drawings (+ register redesign), PDF + attachments, iSample, Catalog + CV mappings, CV import, Cut Floor, Shop Floor, Estimating #9a, CutPlan optimiser, board inventory | `0001`–`0025`, `0044` | `01-early-sub-projects.md` |
| Cutlist + related parts + Orderbook (#10), Global Search (#11), Material Take (#12) | `0026`–`0034` | `02-…` |
| Tracking 2.0, Item & Project Detail 2.0, Tracking modal, Document Register UI, Item duplicate, item-delete cutlist cleanup | `0035`, `0036`, `0050` | `03-…` |
| Dynamic RBAC, `/auth/me`, Search RBAC sync, Locking + Concurrency, all lock-check rounds, FIELD_CONFLICT | `0037`, `0040` | `04-…` |
| Tender lifecycle + financials, QC / Rework / Packing, QC Dashboard | `0038`, `0039` | `05-…` |
| PO generation (per-line, ordered-by-hand, supplier link), Orderbook PO editing + status guard, order validation, legacy `/procurement` audit + PO attachments | `0041`, `0045`–`0049` | `06-…` |
| Comments, mentions, notifications (6 object types), counts, delete-module warning | `0042`, `0043` | `07-…` |
| Null-write / POST audits, e2e repair, e2e in CI | — | `08-…` |

**Still open (customer inputs / deliberate gaps):** Q480 SharePoint URL, Q547 drawing filename, Q550 Cars/OH&S tab, Q572 Scope tab; Task and Change comment threads (no entities); Q472 rule engine; §21's wider Procurement flow; per-material order coverage; E3 pilot-data migration. `apps/web/components/pm/TrackingGrid.tsx` is **dead code** (replaced by `ItemsTable`) — mention, don't delete.

## 11. Reference docs

`docs/sub-projects/README.md` (index + the full old reference-docs list), `docs/plan-v1/{plan_v1,ALIGNMENT,OPEN-QUESTIONS}.md`, `docs/superpowers/plans/README.md`, `legacy/product_spec.md`, `legacy/trackingv2.md`, `legacy/REFINEMENT_BACKLOG.md`.

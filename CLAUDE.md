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
- `db/` — Alembic migrations `0001` → `0032`. Head is `0032_item_lock_request`. Each sub-project section below names the migration(s) it introduced. `0026`–`0032` all belong to the Cutlist + related parts + Orderbook sub-project (#10); `0030`–`0032` were not reserved up front — the Shop Floor re-key, the order schema and the Controlled Lock each needed one.
- `seed/` — `seed.hartwood_joinery` dev seed (workspace + 13 staff users).
- `legacy/` — Read-only quarantine of the original FileMaker-era prototypes (`procurement_api.py`, `*.jsx`, `*.html`, `*_schema.sql`, `product_spec.md`, `trackingv2.md`). Reference only. `REFINEMENT_BACKLOG.md` there tracks 7 open follow-ups from the 2026-05-10 alignment pass.
- `tests/e2e/` — 13 Playwright specs / 40 tests, incl. `smoke.spec.ts` (login + tabs), `pm_workbench.spec.ts`, `drafter_editor.spec.ts`, `procurement.spec.ts`, `shop_drawings.spec.ts`, `isample.spec.ts`, `pdf_generation.spec.ts`, `catalog.spec.ts`, `cv_import.spec.ts`, `estimating.spec.ts`, `cutlist_related_parts.spec.ts` (#10). **The suite is not idempotent**: `estimating.spec.ts` and `procurement.spec.ts` fail on a second run against the same database (an estimate cannot convert twice; a duplicate "Test Supplier" batch trips Playwright strict mode). Re-seed between runs.
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — design specs and implementation plans.
- `docs/plan-v1/` — **Plan V1**: the customer's target specification, the gap analysis against this tree, and 107 open questions. Nothing in it is built. See *Plan V1 — target architecture* below.

## Plan V1 — target architecture (one sub-project built)

`docs/plan-v1/` holds **Plan V1**, the customer's specification for a
company-wide joinery workflow and control platform, with its interview
questions answered through Q431 (supplied 2026-09-17). It is mostly a
**target**, not a description of this tree — with one exception: **Plan V1 #10
(Cutlist + related parts + Orderbook) is built**, and has its own section
below. Everything else in Plan V1 remains unimplemented.

- `docs/plan-v1/plan_v1.md` — the spec, verbatim and canonical.
- `docs/plan-v1/ALIGNMENT.md` — every Plan V1 section mapped onto current
  state: 82 rows, **4 shipped · 21 partial · 50 absent · 7 re-architecture**.
- `docs/plan-v1/OPEN-QUESTIONS.md` — Q432–Q573, continuing Plan V1's own
  numbering. **137 of 141 resolved; every answerable question is answered.**
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

Apart from #10, this section still describes a target, and `CLAUDE.md` remains
the record of what is actually true in the tree.

**Before building anything from Plan V1, read `ALIGNMENT.md` §3.** It lists
seven places where Plan V1 contradicted an invariant stated as binding in *this*
file. **All seven are now decided** (re-scored 2026-09-18):

| Conflict | Outcome |
| --- | --- |
| 1. **Cutlist owns the workflow** (Q410–Q413) | **Built** (`0027`, `0030`). `item_stages` stays per-item as a **projection**, written by fan-out on completion (Q439). Shop Floor re-keyed to `(cutlist_id, stage_key)`; the `(item_id, 'INST')` half of Q445 turned out to be unreachable — Shop Floor has never been able to hold DEL or INST (**Q561**). |
| 2. **Related-part rows** (Q416–Q424) | **Built** (`0028`). Rows in `items` with a `row_type` + parent FK (Q447). The measured cost was **50 SQL call sites across 13 modules**; only **35** actually take the filter — `apps/api/app/row_types.py` holds the one definition and B1's note classifies the rest. |
| 3. **Project files in SharePoint** (Q398–Q400) | **Bounded.** Additive only — `file_blob` survives and keeps serving shop drawings, attachments and sample photos (Q479). Nothing in #5a/#5b/#5c is rewritten. Blocked on three customer inputs. |
| 4. **RBAC as data** (Plan V1 §3) | **Bounded.** DB-backed with groups, but **project scope only — not item, not tab** (Q466). The 4 actions stay (Q469); today's 7 roles become 7 seed groups with identical grants (Q468), so day one is behaviour-preserving. |
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
make up           # build + start db, api, web (db: Postgres 16, api: FastAPI, web: Next.js 16)
make migrate      # apply Alembic 0001 -> 0032
make seed         # create hartwood-joinery workspace + 13 users + 2 projects + demo data for every shipped sub-project (dev password: hartwood-dev)
make test         # pytest in api container (60 test files, 638 tests)
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
- **7 auth roles**: `admin`, `manager`, `editor`, `drafter`, `estimator`, `purchase_officer`, `viewer`. Static `(role, module) -> set[action]` matrix in `apps/api/app/auth/permissions.py` — that file is the source of truth (Plan V1 §3 would replace it with a DB-backed engine; see `docs/plan-v1/ALIGNMENT.md` §3.4); the per-sub-project notes below only explain *why* a row reads as it does. `purchase_officer` has read+comment on tracking, full read+write+approve on orderbook.
- **11 modules** (`_ALL_MODULES`): the 6 IA tabs `dashboard`, `tracking`, `list`, `shop_dwgs`, `isample`, `orderbook`, then `catalog`, `cut_floor`, `shop_floor`, `estimating`, and admin-only `it_management`.
- 4 actions: `read`, `write`, `approve`, `comment`.
- FastAPI deps: `current_user` (resolves cookie -> AuthUser) and `require_permission(module, action)` factory in `apps/api/app/auth/rbac.py`.
- All authenticated mutations write to `audit_log` via `apps/api/app/auth/audit.py`.

## Web shell

- Browser -> Next.js Route Handler (`apps/web/app/api/[...proxy]/route.ts`) -> FastAPI. Browser **never** calls FastAPI directly.
- `apps/web/proxy.ts` (Next 16 renamed the `middleware` convention to `proxy`; runs in the Node.js runtime) enforces login redirect on all non-public paths.
- `apps/web/app/(app)/layout.tsx` does a server-side `fetchMe()` and renders `HAppChrome` (TopBar + tab strip + SideBar). `TabStrip.tsx` carries the 6 primary tabs plus a secondary row (`Catalog · Shop Floor · Cut Floor · Estimating · Customers`); `SideBar.tsx` is the project list only.
- **The tab strip is gated on the RBAC matrix**, not the real enforcement point. `TabStrip.tsx` filters each tab on `can(me, module, "read")` using the `permissions` map `/auth/me` serves. Today every role holds `read` on every tab's module, so all tabs still render for everyone — the gate only starts hiding tabs once some module's read grant is removed for a role. The API's 403 remains the actual access control; an unauthorised click still surfaces it. (If `me.permissions` is absent entirely — e.g. web deployed ahead of the API — the strip falls back to showing all tabs rather than blanking the nav.)
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

**Procurement backend.** Ported from `legacy/procurement_api.py` (MySQL) to `apps/api/app/procurement/{schemas,queries,routes}.py` (Postgres). **25 endpoints** (was 32), all gated by `require_permission("orderbook", action)`. **Seven were retired**: the four `/vendors*` (Q565 — `/suppliers` is now the single surface over `vendors`, workspace-scoped; the legacy pair never were, and `0029`'s `workspace_id NOT NULL` had broken the POST) and the three `/inventory*` (Q544 — `0029` dropped `inventory`, `inventory_movements` and `v_inventory_status`, so they had been 500ing). Mounted at `/procurement/*`. The legacy DB views it reads (`v_po_summary`, `v_budget_utilisation`, `v_inventory_status`, `v_orders_due`) were skipped by migration 0002 and recreated by **migration 0006**; 0009 redefines `v_po_summary` after the `app_user` repoint. This namespace (orders, vendors, budget, approvals) is **not** used by the v1 product surface — that is `procurement_v1`.

## Design system (binding)

Tokens live **once** in `apps/web/app/globals.css` (`@theme inline` block) and are mirrored as a JS object in `apps/web/lib/tokens.ts`. When editing any surface:

- Do not invent new colors — use Tailwind utilities `bg-h-bg`, `bg-h-surface`, `text-h-ink`, `text-h-muted`, `border-h-line`, `bg-h-accent`, `text-h-accent`. Inline styles can use `H.bg`, `H.ink`, etc. from `lib/tokens.ts`.
- Hi-fi reference designs in `legacy/` use a richer palette (`surfaceAlt`, `ink2..4`, `accentSoft`, `good`, `warn`, `bad`, `info`) — port into `globals.css` only when an actual feature needs them.
- Typography: Inter (default sans) for UI, JetBrains Mono for part #, PO #, ETAs, money. The `.h-mono` utility (with `tnum`) is wired in `globals.css`.
- Status taxonomy (`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD`) is canonical — see `legacy/product_spec.md` §12.3 before adding a new state.
- IA is fixed to **6 primary tabs** in this order: `Dashboard · Tracking · List · Shop Dwgs · iSample · Orderbook`, plus the admin-only IT Management at `/it`. Later sub-projects added a **secondary** strip after a divider — `Catalog · Shop Floor · Cut Floor · Estimating · Customers` — which is where new top-level surfaces go; the primary six do not grow. Both live in `apps/web/components/chrome/TabStrip.tsx`. (**Plan V1 Q474 confirmed this rule stands**: Plan V1's `Cutlist` module **is** the existing `List` tab — which the RBAC module name already reflects, since `("list","read")` gates `cutlist.pdf`. No seventh primary tab.)

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
- `docs/plan-v1/OPEN-QUESTIONS.md` — Q432–Q573, **137 of 141 resolved**. Every answerable question is answered; the four left are customer inputs — Q480 (SharePoint site URL), Q547 (drawing filename pattern), Q550 (Cars / OH&S contents) and Q572 (what the Scope tab holds).
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
  rows are history only. Scope is `PATCH /items/{id}` alone —
  `/status` and `/lifecycle/{stage_key}` never consulted the lock and still do
  not, and **there is no project-level lock** (Q566: `projects` has no lock
  column).
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
- Web routes:
  - `/shop-dwgs?project=…&subtab=current|in_review|archive&room=…&q=…` —
    list page with subtabs + filter strip + 3-col card grid.
  - `?drawing=N&rev=M` opens a right-side drawer with PDF/image viewer +
    revision history strip + contextual review actions.
- Workflow: `draft → pending → approved | rejected`. The not-uploader rule on
  approve/reject is enforced in the route handler; the partial unique index
  enforces the in-flight invariant. Approve updates
  `shop_drawing.current_revision_id` atomically. Archive 409s on already-
  archived (no silent re-archive); patch enforces creator-or-manager rule.
- Allowed file types: PDF / PNG / JPEG only (validated by magic bytes).
  SVG, DWG, etc. rejected with 415.
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
  Three legal kinds: `cv_drawing`, `floor_plan`, `site_measure`. (Migration
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
  - `GET /items/{iid}/attachments` — bundle of 3 slots, populated or null.
  - `POST /items/{iid}/attachments/{kind}` — bind/replace via
    `{file_blob_id}` body. PDF-only mime gate (415 on PNG/JPEG; the
    file_blob table itself remains generic).
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
- 4 routes:
  - `POST /items/{iid}/cv-imports/preview` — multipart `file` OR form
    field `body`. Parses, resolves, persists `cv_import_run` with
    `status='preview'` and the full snapshot in `error_log`.
  - `POST /items/{iid}/cv-imports/{run_id}/commit` — body `CvCommitIn`,
    optional `?mode=replace`. Single transaction inserts modules + parts +
    catalog rows + mappings + audit/edit log; flips run to `committed`.
  - `GET /items/{iid}/cv-imports` — history (newest first).
  - `GET /cv-imports/{run_id}` — single run + cached preview snapshot.
- 3-phase wizard mounted in the Drafter Editor Cutlist tab via
  `?tab=cutlist&import=cv`. Phase A (paste/upload), Phase B (resolve
  unknown codes inline — `Use existing` is disabled in v1; `Create new`
  ships for the 5 simple catalog tables; `Skip` always available),
  Phase C (confirm + optional **Replace existing modules** checkbox when
  the item already has modules).
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
> (Q439 + Q562), and undo reverses the whole cutlist (Q446). Scope is the five
> production stages only — **DEL and INST are still not assignable** (Q561).
> The notes below otherwise stand.

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
  - **`/shop-floor?project=…`** — Foreman office board. 5-column
    kanban DOWN | CNC | EDGED | PAINTED | MADE. Per-card status
    pill + worker chip + reassign select + cancel button. Inline
    `AssignDialog`. 15-second polling.
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
- **Revision workflow (binding).** `_LEGAL_TRANSITIONS` in `queries.py`:
  `draft → sent|withdrawn`; `sent → accepted|rejected|expired|withdrawn`;
  `accepted/rejected/expired/withdrawn` are terminal. Any illegal
  transition → `409 {code:"BAD_TRANSITION", from, to}`. `revise` clones
  the current revision into a new `draft` (`rev_no+1`). `approve` action
  gates lock-and-send + Convert.
- **Convert-to-Project.** `POST /revisions/{rid}/convert` requires
  status `accepted` (`409 BAD_STATUS` otherwise), rejects
  already-converted (`409 ALREADY_CONVERTED` with the existing
  `project_id`) and archived-customer, re-resolves each part snapshot,
  and creates a project wired to `projects.estimate_revision_id`.
- **32 endpoints** — Customers CRUD + archive; estimates list/detail/
  create/patch/revise; revision detail + patch + the 6 status
  transitions (`send/accept/reject/expire/withdraw/convert`); line
  CRUD + reorder; per-line part / hardware / labour add/patch/delete;
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
- Out of scope (deferred): PO/supplier-order generation from an accepted
  quote (Convert stops at project creation), multi-currency, client
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

- The item editor's own hardware query still reads the catalog `supplier`
  column alone. `0017` put the real value in `default_supplier`, so it renders
  "—" on every row. Pre-existing; the cutlist rollup coalesces both and is
  pinned by a test.
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

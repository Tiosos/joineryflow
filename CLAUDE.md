# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Nature

**JoineryFlow** monorepo — a web replacement for a FileMaker-based joinery production system. Built across 7 sub-projects; **Foundation** (this branch) ships the auth shell, schema, and 6-tab IA. Subsequent sub-projects (PM Workbench, Procurement Workbench, Shop Floor, etc.) extend onto this base.

Layout:

- `apps/api/` — FastAPI + SQLAlchemy Core (`text()` queries, no ORM models) + Pydantic v2. Auth, RBAC, audit, procurement port.
- `apps/web/` — Next.js 16 (App Router, Turbopack) + Tailwind v4 + TypeScript. Auth shell, 6-tab chrome, server-side proxy.
- `db/` — Alembic migrations (0001 tracking, 0002 procurement, 0003 cut-schedule, 0004 auth, 0005 procurement_user_profile, 0006 procurement views, 0007 material catalog hybrid, 0008 drafter role widening, 0009 app_user repoint + projects.pm_id).
- `seed/` — `seed.hartwood_joinery` dev seed (workspace + 8 staff users).
- `legacy/` — Read-only quarantine of the original FileMaker-era prototypes (`procurement_api.py`, `*.jsx`, `*.html`, `*_schema.sql`, `product_spec.md`, `trackingv2.md`). Reference only.
- `tests/e2e/` — Playwright specs: `smoke.spec.ts` (login + tabs), `pm_workbench.spec.ts` (PM happy path), `drafter_editor.spec.ts` (drafter happy path).
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — design specs and implementation plans.

## Foundation dev loop

```
make up           # build + start db, api, web (db: Postgres 16, api: FastAPI, web: Next.js 16)
make migrate      # apply Alembic 0001 -> 0009
make seed         # create hartwood-joinery workspace + 8 users + 2 projects + ~40 items/modules/parts/hardware (dev password: hartwood-dev)
make test         # pytest in api container (~74 tests)
make e2e-docker   # Playwright smoke via official image (Windows-friendly; use `make e2e` on Linux/Mac with pnpm on PATH)
```

Login: http://localhost:3000/login -> `rin.park@hartwood.test` / `hartwood-dev` (or any `*.hartwood.test` seed user).
API health: http://localhost:3000/api/health -> `{"ok":true}` (proxied through Next.js to FastAPI).

**Important:** Running `make test` TRUNCATEs `workspace`, `app_user`, `session`, `audit_log` between cases. Re-run `make seed` if you need login working after a test run.

## Auth & RBAC

- Self-built auth: argon2id passwords (`apps/api/app/auth/passwords.py`), opaque 32-byte tokens (sha256 stored), httpOnly `jf_session` cookie, sliding 14d / hard-cap 30d (`apps/api/app/auth/sessions.py`).
- 5 auth roles: `admin`, `manager`, `editor`, `purchase_officer`, `viewer`. Static `(role, module) -> set[action]` matrix in `apps/api/app/auth/permissions.py`. `purchase_officer` has read+comment on tracking, full read+write+approve on orderbook.
- 6 IA modules + admin-only IT: `dashboard`, `tracking`, `list`, `shop_dwgs`, `isample`, `orderbook`, `it_management`.
- 4 actions: `read`, `write`, `approve`, `comment`.
- FastAPI deps: `current_user` (resolves cookie -> AuthUser) and `require_permission(module, action)` factory in `apps/api/app/auth/rbac.py`.
- All authenticated mutations write to `audit_log` via `apps/api/app/auth/audit.py`.

## Web shell

- Browser -> Next.js Route Handler (`apps/web/app/api/[...proxy]/route.ts`) -> FastAPI. Browser **never** calls FastAPI directly.
- `apps/web/middleware.ts` enforces login redirect on all non-public paths.
- `apps/web/app/(app)/layout.tsx` does a server-side `fetchMe()` and renders `HAppChrome` (TopBar + 6-tab strip + SideBar).
- Design tokens: `apps/web/app/globals.css` declares CSS custom properties + Tailwind v4 `@theme inline` block exposing `bg-h-bg`, `text-h-ink`, `text-h-muted`, `border-h-line`, `bg-h-accent`, `bg-h-surface`. **No `tailwind.config.ts`** — Tailwind v4 uses CSS-first config.

## Architecture (big picture)

**One database, three apps** (see `product_spec.md` §1):

1. **Project Information Management** (v1 target) — Drafter/PM/CEO. Project → Item → Module → Part + HardwareLine + 10-stage lifecycle.
2. **Shop Floor Ops** (v2) — Foreman worker assignment; reuses v1 fields.
3. **Cabinet Vision Integration Layer** (v2) — Material catalog, CV CSV import, CutPlan/CutSchedule.

**Key data-model invariants** (enforced across schemas and UI):

- **Six separate Material Catalog tables** (`board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`) — do NOT unify them; lifecycles differ. They share an abstract interface `(id, type, description, supplier, cost_unit, lead_time_days, notes)`.
- **ProjectHardwareCatalog** is a project-scoped link layer; item hardware lines reference materials *through* it. Log-only governance (no approval step; every add/remove writes an audit row).
- **ProcurementBatch → Allocations → item_hardware_line_id** answers "is this item blocked on a material?" as a single join — no second window needed.
- **CutPlan ≠ CutSchedule.** Optimisation output vs. Machine team's daily ordering. Keep as two entities.
- **Terminology pins** (critical, legacy-FileMaker-era collisions):
  - `Stage` = site location/area (e.g. `Joinery Lab`, `Block B`).
  - `Zone` = numeric sub-division of Stage.
  - `lifecycle_stage` (or `stage_key`) = the 10 production milestones (`REQ`, `SM`, `LISTED`, `DOWN`, `CNC`, `EDGED`, `PAINTED`, `MADE`, `DEL`, `INST`). **Never reuse the bare word "stage"** for these in code.
  - `Status` = record state (`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD`).
  - `Status Symbol` = Drafter-only UI flag, not reported.

**Role model.** Six operational JTBD roles (CEO, PM, Drafter, Foreman, Machine, Procurement) map onto **five** auth roles (admin, manager, editor, purchase_officer, viewer). Procurement -> purchase_officer; CEO -> admin; PM -> manager; Drafter/Foreman/Machine -> editor; Observer -> viewer. Drafter is the authoritative data-entry point; every other role is upstream or downstream.

**Procurement backend.** Ported from `legacy/procurement_api.py` (MySQL) to `apps/api/app/procurement/{schemas,queries,routes}.py` (Postgres). 26 endpoints, all gated by `require_permission("orderbook", action)`. Mounted at `/procurement/*`. Some legacy DB views (`v_po_summary`, `v_inventory_status`, `v_budget_utilisation`) are not yet recreated in migration 0002 — endpoints depending on them will fail at runtime until a follow-up migration adds them.

## Design system (binding)

Tokens live **once** in `apps/web/app/globals.css` (`@theme inline` block) and are mirrored as a JS object in `apps/web/lib/tokens.ts`. When editing any surface:

- Do not invent new colors — use Tailwind utilities `bg-h-bg`, `bg-h-surface`, `text-h-ink`, `text-h-muted`, `border-h-line`, `bg-h-accent`, `text-h-accent`. Inline styles can use `H.bg`, `H.ink`, etc. from `lib/tokens.ts`.
- Hi-fi reference designs in `legacy/` use a richer palette (`surfaceAlt`, `ink2..4`, `accentSoft`, `good`, `warn`, `bad`, `info`) — port into `globals.css` only when an actual feature needs them.
- Typography: Inter (default sans) for UI, JetBrains Mono (`.h-mono`, with `tnum`) for part #, PO #, ETAs, money. Mono utility not yet wired — add in a future task.
- Status taxonomy (`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD`) is canonical — see `legacy/product_spec.md` §12.3 before adding a new state.
- IA is fixed to **6 top tabs** in this order: `Dashboard · Tracking · List · Shop Dwgs · iSample · Orderbook`, plus the admin-only IT Management at `/it`. Tab strip lives in `apps/web/components/chrome/TabStrip.tsx`.

## Reference docs (read before large changes)

- `legacy/product_spec.md` — product overview, JTBD roles, data model invariants, design tokens, IA. Authoritative for v1 product surface.
- `legacy/trackingv2.md` — detailed v1 build plan for Project Information Management. Authoritative for module 1.
- `docs/superpowers/specs/2026-04-22-foundation-design.md` — Foundation spec.
- `docs/superpowers/plans/2026-04-22-foundation.md` — 31-task implementation plan (tracks all build decisions).
- `docs/superpowers/specs/2026-04-25-pm-workbench-design.md` — PM Workbench + Drafter Editor spec (sub-projects #2 + #3).
- `docs/superpowers/plans/2026-04-25-pm-workbench.md` — 33-task implementation plan for sub-projects #2 + #3.
- `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md` — Procurement Workbench v1 spec (sub-project #4).
- `docs/superpowers/plans/2026-04-28-procurement-workbench.md` — 24-task implementation plan for sub-project #4.
- `docs/superpowers/specs/2026-05-01-shop-drawings-design.md` — Shop Drawings + file-upload subsystem v1 spec (sub-project #5a).
- `docs/superpowers/plans/2026-05-01-shop-drawings.md` — 21-task implementation plan for sub-project #5a.

## PM Workbench (sub-project #2 + #3)

- Lives on top of Foundation; migrations 0008 (drafter role widening) + 0009 (legacy users -> app_user repoint, projects.pm_id, drop users).
- Drafter-narrow gate: `require_drafter()` — items / modules / parts / hardware_lines / project_hardware_catalog mutations only allow `auth_role IN {drafter, manager, admin}`.
- New routers under `apps/api/app/{home, projects, items, parts, hardware_lines}/`. Mounted in `main.py`.
- Every item-scoped mutation writes both `audit_log` (workspace governance) and `item_edit_log` (item history) in the same DB transaction. Helper: `apps/api/app/edit_log.py`.
- Web routes: `/home` (default landing, replaces `/dashboard`), `/projects`, `/tracking?project_id=`, `/items/[id]?tab=cutlist|hardware|board|log`.
- Editor mode is detected by middleware writing `x-pathname`; layout reads it and hides TabStrip + SideBar, swapping in a "← Return to home" link.
- State: raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / React Hook Form / Zustand in v1.**
- Procurement UI button on `/tracking` is hidden behind `NEXT_PUBLIC_PROCUREMENT_UI_READY=1`.
- PDF generation buttons render disabled with tooltip ("ships in sub-project #5").
- Soft-lock semantics: first save claims ownership; non-owner saves are permitted but write `event='item.lock_overridden'` audit row.
- Lifecycle stage_key (REQ..INST) ≠ items.stage (site location); never use bare "stage" for lifecycle.

## Procurement Workbench (sub-project #4)

- New backend module `apps/api/app/procurement_v1/` mounted at top-level paths
  (`/projects/{pid}/materials`, `/batches`, `/batches/{bid}/allocations`,
  `/catalogs/{type}`, `/procurement-queue`). The legacy `/procurement/*`
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

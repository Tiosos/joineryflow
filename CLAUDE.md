# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Nature

**JoineryFlow** monorepo — a web replacement for a FileMaker-based joinery production system. Built across 7 sub-projects; **Foundation** (this branch) ships the auth shell, schema, and 6-tab IA. Subsequent sub-projects (PM Workbench, Procurement Workbench, Shop Floor, etc.) extend onto this base.

Layout:

- `apps/api/` — FastAPI + SQLAlchemy Core (`text()` queries, no ORM models) + Pydantic v2. Auth, RBAC, audit, procurement port.
- `apps/web/` — Next.js 16 (App Router, Turbopack) + Tailwind v4 + TypeScript. Auth shell, 6-tab chrome, server-side proxy.
- `db/` — Alembic migrations (0001 tracking, 0002 procurement, 0003 cut-schedule, 0004 auth).
- `seed/` — `seed.hartwood_joinery` dev seed (workspace + 8 staff users).
- `legacy/` — Read-only quarantine of the original FileMaker-era prototypes (`procurement_api.py`, `*.jsx`, `*.html`, `*_schema.sql`, `product_spec.md`, `trackingv2.md`). Reference only.
- `tests/e2e/` — Playwright smoke spec.
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — design specs and implementation plans.

## Foundation dev loop

```
make up           # build + start db, api, web (db: Postgres 16, api: FastAPI, web: Next.js 16)
make migrate      # apply Alembic 0001 -> 0004
make seed         # create hartwood-joinery workspace + 8 users (dev password: hartwood-dev)
make test         # pytest in api container (34 tests)
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

# PM Workbench — Design Spec

> **Later change — the soft-lock is gone (2026-09-19, migration `0032`).**
> §2's "Non-owner saves are permitted", §5's "Never blocks save" and all of
> §6.4 *Soft-lock mechanics* no longer describe the code: a non-owner's save on
> a locked item is held as an `item_lock_request` for the owner or a manager to
> approve or reject (Plan V1 Q509 / Q566), and `item.lock_overridden` is
> retired. Everything else in this spec stands; `CLAUDE.md` is the statement of
> current state.

**Date:** 2026-04-25
**Sub-project:** #2 + #3 (merged) of the JoineryFlow build, per `legacy/trackingv2.md` v1 grouping.
**Depends on:** Foundation (sub-project #1, branch `feat/foundation`, migrations 0001-0007).

**Scope.** PM Project Workbench (tracking grid) + Drafter Item Editor — the end-to-end PM->Drafter loop. PM lands on `/home`, opens a project, sees the tracking grid, clicks an item ▶, lands in the Drafter Item Editor with editable Cutlist + Hardware tabs, and returns to home.

**Out of scope** (deferred to later sub-projects): CV CSV import, Procurement UI, Exec Dashboard variants B-E, Print Combined PDF, full lock-transfer flow, real-time push, file blob uploads, Cabinet Vision integration, Shop Floor Ops surfaces.

---

## 1. Context & Decomposition

`legacy/trackingv2.md` is the canonical v1 build plan for "Project Information Management". It groups four pieces (Project Workbench grid, Drafter Item Editor, Procurement UI, CV import) under one v1 module. The Foundation spec (sub-project #1) split that into separate sub-projects #2-#5. This spec re-merges the two most-coupled pieces — **Project Workbench grid (#2)** and **Drafter Item Editor (#3)** — because they share data, audit hooks, and role enforcement. Procurement UI (#4) and CV import (#5) remain independent.

Sub-project sequencing after PM Workbench:
1. Foundation *(done)*
2. **PM Workbench** *(this spec; #2 + #3 merged)*
3. Procurement Workbench UI *(backend exists from Foundation T22)*
4. CV CSV import + PDF generation
5. Shop Floor Ops *(v2)*
6. Cabinet Vision deep integration *(v2)*

Each sub-project gets its own spec -> plan -> implementation cycle.

---

## 2. Data Model & Invariants

### 2.1 No new tables

Foundation migrations 0001-0007 already cover every table PM Workbench reads or writes. The catalog:

| Table | Role |
|---|---|
| `projects` | Tracking grid root; sidebar FAV/ALL list |
| `project_favourites` | Sidebar `★` toggle |
| `items` | One row per cutlist line; the tracking grid |
| `item_stages(item_id, stage_key, due_date, done_date)` | The 10 lifecycle milestones |
| `stages` | Lookup table for the 10 keys |
| `status_options`, `status_symbols` | Drafter-only UI flags + status taxonomy |
| `item_status_log`, `item_edit_log` | Soft-lock warning + Log tab |
| `modules`, `parts` | Cutlist tab grid |
| `item_hardware_lines(item_id, qty, catalog_id, note)` | Hardware tab grid |
| `project_hardware_catalog` | Material discriminator lives here, not on `item_hardware_line` |
| `project_hardware_catalog_log` | Logs every add/remove |
| `procurement_batches`, `batch_allocations` | Read-only — feeds availability strip |
| `audit_log` | Workspace-scoped governance |

The FK chain `item_hardware_lines.catalog_id -> project_hardware_catalog -> (board_materials | hardware_materials | custom_made | benchtop_materials | appliances | equipment_hire)` *structurally* enforces "Every item_hardware_line must resolve through the project catalog."

### 2.2 Migration 0008 — narrow `drafter` auth_role

Purpose: enforce `legacy/trackingv2.md` §3.2 invariant ("Drafter is the only writer for item / module / part / hardware-line data") without conflating Foreman/Machine, who also map to `auth_role=editor` today.

```sql
ALTER TABLE app_user DROP CONSTRAINT app_user_auth_role_check;
ALTER TABLE app_user ADD CONSTRAINT app_user_auth_role_check
  CHECK (auth_role IN ('admin','manager','editor','drafter','purchase_officer','viewer'));
```

Plus:
- Update `apps/api/app/auth/permissions.py` MATRIX: add `drafter` row with `{tracking, list}: {read, write, approve, comment}`, `{dashboard, shop_dwgs, isample, orderbook}: {read}`, `{it_management}: {}`.
- Update `apps/api/app/users/routes.py` `_VALID_ROLES` set to include `drafter`.
- Update `apps/api/tests/test_permissions.py` parametrized cases (add ~6 new cases for `drafter` row).
- Seed update: `UPDATE app_user SET auth_role='drafter' WHERE email='noa.lindqvist@hartwood.test'`.

### 2.3 Migration 0009 — repoint legacy `users` FKs to `app_user`

The Foundation 0001 port faithfully recreated the legacy MySQL `users` table (different shape than `app_user`, used `username`/`full_name`/`role`). T22 (procurement port) already migrated the *queries* to read from `app_user`; the *FKs* still point at the legacy table. With no live data anywhere, this is the right moment to clean up.

Migration steps:

1. Drop FK `projects.optimisation_drafter_id -> users(user_id)`. Re-add -> `app_user(id) ON DELETE SET NULL`.
2. Drop FK `project_favourites.user_id -> users(user_id)`. Re-add -> `app_user(id) ON DELETE CASCADE`.
3. Drop FK `project_hardware_catalog.added_by -> users(user_id)`. Re-add -> `app_user(id) ON DELETE SET NULL`.
4. Drop FK `project_hardware_catalog_log.changed_by -> users(user_id)`. Re-add -> `app_user(id) ON DELETE SET NULL`.
5. `items.cutlist_owner_id` (no FK declared in 0001 schema; just `BIGINT`). Add -> `FK app_user(id) ON DELETE SET NULL`.
6. Drop FKs on procurement tables (`purchase_orders.requester_id`, `po_attachments.uploaded_by`, `approval_workflows.approver_id`, `budget_transactions.created_by`, `inventory_movements.created_by`, `cost_centers.manager_id`) -> re-point to `app_user(id) ON DELETE SET NULL`.
7. Add new column + FK: `projects.pm_id BIGINT REFERENCES app_user(id) ON DELETE SET NULL`. Used for PM scoping. (The legacy text column `tg_project_manager varchar(128)` stays as a backup display string; `pm_id` is the authoritative FK.)
8. `CREATE OR REPLACE VIEW v_po_summary` and `v_orders_due` to JOIN `app_user` instead of `users`. (These views were built in 0006; this migration replaces them in place.)
9. `DROP TABLE users CASCADE` — the legacy table now has zero references.

**Down migration:** intentionally minimal (`-- intentionally not reversible; pre-PM-Workbench schema is recoverable from migrations 0001-0007 only`). The same nuclear-down pattern Foundation 0001 used.

### 2.4 Invariants (binding for v1)

1. **`stage_key` ≠ `items.stage`.** `stage_key` is the 10-step lifecycle (REQ->INST). `items.stage` is the site location (e.g. "Joinery Lab", "Block B"). Code MUST never use the bare word "stage" for lifecycle in identifiers — use `lifecycle_stage` or `stage_key`. (Reaffirmed from CLAUDE.md.)
2. **`item_hardware_line.catalog_id` is the only path to a material.** No `material_id` shortcut. Always JOIN through `project_hardware_catalog`.
3. **Every `project_hardware_catalog` add/remove writes to `project_hardware_catalog_log`** in the same DB transaction. The log is the governance record; no approval step in v1.
4. **Soft-lock semantics.** `items.item_locked` is set on first save by a Drafter. Non-owner saves are permitted but display a warning banner; the override is audited (`event: "item.lock_overridden"`).
5. **Drafter-narrow gate** is enforced by a new `require_drafter()` dependency for the four tightly-restricted endpoint groups (items / modules / parts / hardware_lines / project_hardware_catalog mutations). Other endpoints (status, lifecycle, project metadata, favourites) keep the existing matrix gate.

---

## 3. Architecture

Same stack as Foundation: Next.js Route Handler proxy -> FastAPI -> Postgres. Browser never calls FastAPI directly.

```
+----------------------------------------------------------+
|  Browser                                                  |
|  ------------------------------------------------------   |
|  Next.js (App Router, Tailwind v4)                        |
|   - middleware.ts (auth gate)                             |
|   - /home, /projects, /tracking, /items/[id]              |
|   - components/chrome/{TopBar, TabStrip, SideBar}         |
|   - app/api/[...proxy] -> FastAPI                         |
+--------------------------+-------------------------------+
                           | httpOnly jf_session cookie passes through
                           v
+----------------------------------------------------------+
|  FastAPI                                                  |
|  ------------------------------------------------------   |
|  /home/dashboard                                          |
|  /projects, /projects/{id}, /projects/{id}/favourites     |
|  /projects/{id}/items                                     |
|  /items/{id}, /items/{id}/{lock,status,lifecycle}         |
|  /items/{id}/availability                                 |
|  /modules/{id}, /parts/{id}                               |
|  /projects/{id}/hardware_catalog/*                        |
|  /hardware_lines/{id}                                     |
|                                                           |
|  Gates: require_permission() + new require_drafter()      |
|  Mutations: write_audit() + item_edit_log in same txn     |
+--------------------------+-------------------------------+
                           v
                     Postgres 16
```

### 3.1 New RBAC helper

```python
# apps/api/app/auth/rbac.py
def require_drafter():
    """Allow only auth_role in {drafter, manager, admin}.

    Use for the narrow §3.2 invariant: item / module / part /
    hardware_line / project_hardware_catalog mutations."""
    def _dep(user: AuthUser = Depends(current_user)) -> AuthUser:
        if user.auth_role not in ("drafter", "manager", "admin"):
            raise HTTPException(403, "drafter, manager, or admin required")
        return user
    return _dep
```

### 3.2 `AuthUser` extension

`AuthUser` adds `jtbd_role: str | None`. Sourced from `app_user.jtbd_role`. Used by `/home/dashboard` for view-shape personalization (CEO sees cross-project, PM sees own-project, Drafter sees own-cutlists).

---

## 4. Endpoints

All mutations write `audit_log` via existing `write_audit()` and (where item-scoped) write `item_edit_log` in the same DB transaction. Routes call `db.commit()` once at the end of the handler. Helpers (`write_audit`, `create_session`, etc.) only `flush()`.

### 4.1 Read surface

| Method | Path | Gate | Body / Query | Returns |
|---|---|---|---|---|
| GET | `/home/dashboard` | `current_user` | — | Composite `HomeDashboardOut`: metrics + my_day + deliveries_today + team_activity + favourite_projects + all_projects_count |
| GET | `/projects` | `require_permission("tracking", "read")` | `?fav=true|false` | List, role-scoped |
| GET | `/projects/{pid}` | `require_permission("tracking", "read")` | — | `ProjectOut` |
| GET | `/projects/{pid}/items` | `require_permission("tracking", "read")` | `?status&stage&q` | List with pivot of `item_stages` per stage_key, status, availability roll-up `{ready: N, blocked: M}` |
| GET | `/items/{id}` | `require_permission("list", "read")` | — | `ItemOut`: metadata + nested modules + parts + hardware_lines + last 50 log rows + lock_warning |
| GET | `/items/{id}/availability` | `require_permission("list", "read")` | — | Per-line: `{line_id, status: "ready"\|"ordered"\|"none", eta?, batch_id?}` |
| GET | `/projects/{pid}/hardware_catalog` | `require_permission("list", "read")` | — | Catalog rows JOIN-ed across the 6 source tables |

### 4.2 Write surface

| Method | Path | Gate | Notes |
|---|---|---|---|
| POST | `/projects` | manager/admin | Create. `pm_id` defaults to caller. |
| PATCH | `/projects/{pid}` | manager/admin | Edit metadata. |
| POST | `/projects/{pid}/favourites` / DELETE | `current_user` | Toggle FAV. |
| POST | `/projects/{pid}/items` | `require_drafter()` | New item. |
| PATCH | `/items/{id}` | `require_drafter()` | Edit metadata; soft-lock check; per-field log rows. |
| DELETE | `/items/{id}` | `require_drafter()` | Cascade-safety: 409 if `batch_allocations` references any of its hardware lines. |
| POST | `/items/{id}/lock` / DELETE | `require_drafter()` | Toggle `item_locked` + reassign `cutlist_owner_id`. |
| PATCH | `/items/{id}/status` | `require_permission("tracking", "write")` | CLEAR/VOID/NOTE!/LIVE/APPROVED/HOLD. Editor allowed (Foreman/Machine can flip). |
| PATCH | `/items/{id}/lifecycle/{stage_key}` | `require_permission("tracking", "write")` | Set `due_date` or `done_date`. Writes `item_status_log`. |
| POST | `/items/{id}/modules` | `require_drafter()` | Create module. |
| PATCH | `/modules/{mid}` | `require_drafter()` | |
| DELETE | `/modules/{mid}` | `require_drafter()` | |
| POST | `/modules/{mid}/parts` | `require_drafter()` | Manual parts entry (CV import deferred). |
| PATCH | `/parts/{pid}` | `require_drafter()` | |
| DELETE | `/parts/{pid}` | `require_drafter()` | |
| POST | `/projects/{pid}/hardware_catalog` | `require_drafter()` | Add from global. Writes log row in same txn. |
| DELETE | `/projects/{pid}/hardware_catalog/{cid}` | `require_drafter()` | 409 if `item_hardware_lines` reference it; logs. |
| POST | `/items/{id}/hardware_lines` | `require_drafter()` | Body `{catalog_id, qty, note}`. |
| PATCH | `/hardware_lines/{lid}` | `require_drafter()` | |
| DELETE | `/hardware_lines/{lid}` | `require_drafter()` | |

### 4.3 Pydantic shape conventions

- Inputs: `<Verb><Entity>In` (e.g., `CreateItemIn`, `PatchPartIn`).
- Outputs: `<Entity>Out` for single, `<Entity>List` for collections.
- Composite outputs (`/home/dashboard`, `/items/{id}`) get a top-level `<Surface>Out` shape.
- API speaks ISO 8601 dates only; DD/MM/YYYY is a frontend rendering concern.

### 4.4 Pagination

v1 ships no server-side pagination. Joinery projects rarely exceed ~200 items. Tracking grid and Hardware-tab catalog list both render full result. Cursor pagination added in a later sub-project once a project crosses 500 items.

---

## 5. UI Surfaces

All Server Components by default; `"use client"` only where interaction needs it. Reads via Next.js `fetch()` with `cache: "no-store"`. Mutations via client-side `fetch()` + `router.refresh()` to revalidate. **No TanStack Query / Zustand v1.**

State strategy:
- **Server state** -> fetched in Server Components (initial render); refresh on focus/manual.
- **Client state** -> controlled inputs.
- **URL state** -> filters, sort, active tab in search params (`/items/123?tab=hardware`).
- **No React Hook Form** in v1; parts grid uses controlled state with PATCH on blur.

### 5.1 `/home` — role-based landing

Hi-fi: `HiDashA` (artboard `dash-a` in `legacy/hi-dashboard.jsx`).

```
+----------------------------------------------------------+
| TopBar: JoineryFlow logomark · search pill · avatar      |
+----------------------------------------------------------+
| TabStrip                                                  |
+----------+-----------------------------------------------+
| SideBar  |  4 metric cards                                |
| FAV/ALL  |  My Day | Deliveries Today                    |
| project  |  Team activity                                 |
| list     |                                                |
+----------+-----------------------------------------------+
```

Single fetch to `/api/home/dashboard`. Sub-components receive props. Metric cards link to filtered `/tracking?status=overdue`. "My Day" rows link to `/items/{id}?tab=cutlist`. `★` toggle is a Client Component that POSTs to `/api/projects/{pid}/favourites`.

**Role-shape personalization** (driven by `jtbd_role`):
- CEO/admin -> cross-project metrics + project list "ALL"
- PM/manager -> metrics scoped to projects where `pm_id = me`
- Drafter -> metrics scoped to items where `cutlist_owner_id = me`; "My Day" foregrounded
- Foreman/Machine/Viewer -> read-only view
- purchase_officer -> fewer metric cards; Deliveries today highlighted

### 5.2 `/projects` — project list & CRUD

Server Component. Manager/admin: full CRUD. Others: read-only list.

- Table: project_code · name · pm · status · item_count · total_value · install_start
- "+ New project" button (manager/admin only) opens an inline drawer with a 6-field form
- Click row -> `/projects/{pid}` redirects to `/tracking?project_id=pid`

### 5.3 `/tracking` — PM Project Workbench grid

Hi-fi: `HiTracking` (artboard `track-a` in `legacy/hi-tracking-list.jsx`).

URL: `/tracking?project_id=42&status=LIVE&stage=LISTED&q=oak`. If no `project_id`, prompts user to pick from sidebar.

**Grid columns** (locked widths CUTLIST->QTY across sub-tabs per legacy `tracking.md` item #27):
```
☐ NUM · Status · Stage(site) · Zone · Lvl · Rm# · RmDesc ·
Code · Description · Qty · CutOwner · DueDates(by stage_key) ·
Availability(strip) · ▶
```

Sub-tabs (item #26): `DATE / iTIME / HARDWARE / SITE MEASURE / INVOICE / QC` — render different right-side column groups while keeping CUTLIST->QTY locked left. v1: DATE fully wired; iTIME/HARDWARE/SITE MEASURE/INVOICE/QC render schema-backed columns where data exists, else `—`.

**Item ▶ button** (item #30):
- If `auth_role IN {drafter, manager, admin}` -> push `/items/{id}?tab=cutlist`
- Else -> opens read-only details drawer overlay (no separate route)

**Material availability strip** (item #32) — per-row chip `3 ready / 2 blocked`. Click expands inline a per-hardware-line breakdown (data delivered with the row, no extra request).

**"Open Procurement" header button** (item #31) — hidden in v1 behind feature flag `NEXT_PUBLIC_PROCUREMENT_UI_READY`. Lights up when sub-project #4 lands.

**Filtering**: status / lifecycle stage / search query / cutlist owner. URL params; server filters where it can; client search-as-you-type.

### 5.4 `/items/[id]` — Drafter Item Editor

Hi-fi: `HiTracking` drawer pattern (left metadata column) + `HiListCutlist` (artboard `list-cut`) + `HiListHardware` (artboard `list-hw`).

```
+----------------------------------------------------------+
| <- Return to home  ITEM #297871 · Alfred St · Block B [x]|
+----------------------------------------------------------+
| Item metadata        | [Cutlist] [Hardware] [Board] [Log]|
| (controlled inputs)  | --------------------------------- |
| - Level / Room       |  Active tab body                  |
| - Description        |                                   |
| - Stage (site)       |                                   |
| - Assembler/Lister   |                                   |
| - Painting Req?      |                                   |
| - Solid Surface Req? |                                   |
| - Group/Item ID      |                                   |
| - Estimator Notes    |                                   |
+----------------------+-----------------------------------+
| Print Cutlist · Print Hardware · Print Combined · Lock   |
| (PDF disabled tooltip; Lock fully wired)                 |
+----------------------------------------------------------+
```

**Return controls.**
- **`<- Return to home`** in the TopBar slot (replaces the tab strip while editor is mounted). Click -> push `/home`.
- **`[x]` close-window button** in editor header. Calls `window.close()` if it returns true; else falls back to push `/home`.

**Soft-lock banner.** Renders above the tab strip when `item_locked = true && cutlist_owner_id !== me.id`:
> Locked by Noa Lindqvist — last edit 12 minutes ago. Your save will overwrite.

Never blocks save. Override is audited (`event: "item.lock_overridden"`).

**Cutlist tab** (`HiListCutlist` pattern). Layout: 220px room/module tree (left) + dense parts grid (right).
- Module tree from `/api/items/{id}` payload
- Parts grid editable rows: qty · part_name · len_mm · wid_mm · board_material · edge · colour · paint_instruction · comment
- "Add row" button at bottom (manual entry, no CV import in v1)
- "Add module" button on tree
- PATCH on blur, optimistic UI per cell, revert on 4xx
- Rev-C rows get `bg-h-accent-soft` background (matches hi-fi)

**Hardware tab** (`HiListHardware` pattern). Layout: pantry (left, grouped by catalog category) -> cart (right, 420px, grouped by supplier).
- Pantry: `project_hardware_catalog` rows grouped by `source_table` (board/hardware/custom_made/benchtop/appliance/equipment_hire). Search box.
- "Add from global" button opens modal listing rows from one of the 6 source tables not yet in project catalog. Click -> POST to `/projects/{pid}/hardware_catalog` (writes log) -> modal closes -> pantry refreshes.
- Cart: `item_hardware_lines` grouped by supplier name. Per row: qty stepper · catalog locked · note · availability chip.
- Availability chip uses `HStatus` mappings: green "in stock", info "ordered, ETA DD/MM", warn "no orders".
- Add hardware line: drag-from-pantry OR pantry row's `+` button.

**Board tab.** Visible-but-deferred: "Board view ships in v2 with Cabinet Vision integration."

**Log tab.** Last 50 `item_edit_log` rows reverse-chronological. Columns: ts · actor_name · field · old · new.

**Footer actions.**
- Print Cutlist · Print Hardware · Print Combined PDF — visible-but-disabled with tooltip "PDF generation ships in sub-project #5"
- Lock / Unlock — fully wired; toggles `item_locked` + reassigns `cutlist_owner_id`; only the current owner and admin/manager can flip lock state

### 5.5 Chrome additions

**`apps/web/components/chrome/SideBar.tsx`** (currently `—` stub):
- "ALL / FAV" toggle pill at top
- Project list (name + project_code + `★` toggle)
- Active project highlighted by `?project_id=` query param
- Server Component reads `/api/projects?fav=true|false`; favourite toggle is a Client subcomponent

**`apps/web/components/chrome/TopBar.tsx`**:
- When pathname starts with `/items/`, hide TabStrip and show "<- Return to home" instead
- Otherwise unchanged

---

## 6. Lifecycle, Status & Soft-Lock Mechanics

### 6.1 Lifecycle stages (`item_stages.stage_key`)

| stage_key | Meaning | Owner role |
|---|---|---|
| `REQ` | Requested (project intake) | manager (PM) |
| `SM` | Site Measure complete | editor (Foreman) or drafter |
| `LISTED` | Cutlist drawn / Drafter has it in the system | drafter |
| `DOWN` | Marked down for nesting / sent to optimisation | drafter (optimisation_drafter) |
| `CNC` | CNC-cut | editor (Machine) |
| `EDGED` | Edge-banded | editor (Machine) |
| `PAINTED` | Painted (paper-only tracking — no per-part v1) | editor |
| `MADE` | Assembled | editor (Foreman) |
| `DEL` | Delivered to site | editor (Foreman) |
| `INST` | Installed | editor (Foreman) |

**Transition rules.**
- `due_date` (target) and `done_date` (actual) per (item, stage_key).
- v1 enforces NO order-of-operations. Any owning role can flip any `done_date` they own.
- `PATCH /items/{id}/lifecycle/{stage_key}` writes `item_status_log` + `audit_log` in same txn.
- Lifecycle write does NOT touch `items.stage` (which is the *site* location).
- "Done" rollup metric: `count(*) WHERE done_date IS NOT NULL` divided by 10.

### 6.2 Status taxonomy (`items.status`)

| Status | Color (HStatus) | Meaning |
|---|---|---|
| `CLEAR` | good | No outstanding issue |
| `LIVE` | accent | Active in production |
| `APPROVED` | good | Spec approved (PM/CEO sign-off) |
| `HOLD` | warn | Paused — awaiting decision |
| `NOTE!` | warn | Drafter-flagged issue |
| `VOID` | bad | Cancelled item |

- `PATCH /items/{id}/status` body `{status: "..."}`. Gate `require_permission("tracking", "write")` — editor+ allowed.
- v1 enforces NO transition graph (intentional — joinery workflow is too fluid).
- `VOID` items still appear in tracking grid but are filtered out of `/home` metrics by default.

### 6.3 Status symbols

`status_symbols` per-item flag for Drafter's own visual triage. Stored as `items.status_symbol_id`. Edit gate: drafter-narrow (only `auth_role IN {drafter, manager, admin}`). NOT reported anywhere — cosmetic ephemera. Excluded from `/home` metrics. Audit-quiet (no audit row).

### 6.4 Soft-lock mechanics

**Lock activation.**
- First-save claims ownership: server sets `cutlist_owner_id = me` if NULL, AND sets `item_locked = true` if NULL/false.
- Owner can `DELETE /items/{id}/lock` to release (`item_locked = false` but `cutlist_owner_id` stays — claim is sticky for "My Day").

**Lock warning.**
- On open of `/items/{id}`, server returns `lock_warning` field in `ItemOut` when `item_locked = true && cutlist_owner_id != current_user.id`.
- Banner: Locked by `{owner_full_name}` — last edit `{since_minutes_ago}` minutes ago.
- Never blocks save.
- Non-owner save records audit `event: "item.lock_overridden"` with `payload: {prior_owner_id, new_owner_id}`. Owner is NOT changed automatically.

**Lock transfer (manual).**
- `POST /items/{id}/lock` body `{owner_id}`: if requestor is current owner OR `auth_role IN {manager, admin}`, set `cutlist_owner_id = body.owner_id`. Else 403.
- Used by the "Lock / Unlock" footer button.

### 6.5 `item_edit_log` writes

Every mutation on items / parts / hardware_lines / project_hardware_catalog writes one `item_edit_log` row in the same DB transaction:

```
item_edit_log (
  log_id      BIGSERIAL PK,
  item_id     BIGINT FK,
  actor_id    BIGINT FK app_user.id,
  field       text,        -- 'parts.qty' / 'hardware_lines.note' / 'item.description'
  old_value   text,
  new_value   text,
  ts          timestamptz DEFAULT now()
)
```

A PATCH that changes 3 fields -> 3 log rows. POST/DELETE -> one row with `field='_create'` or `_delete`.

The Log tab renders the last 50 rows. CEO/PM/Drafter/Foreman/Machine all read it (it's `list:read`).

`audit_log` and `item_edit_log` are **both** written: audit_log is workspace-scoped governance; item_edit_log is item-scoped history. Two purposes, two tables, same transaction.

---

## 7. Testing & Acceptance

### 7.1 Test pattern (continuation of Foundation)

Server-side tests run inside the api container via `make test` -> `pytest -q`.

Two existing fixture flavors in `apps/api/tests/conftest.py`:
- **Transaction-rollback `db` fixture** — for unit-level helpers
- **Real-`SessionLocal` + autouse TRUNCATE fixture** — for FastAPI `TestClient` routes (each test seeds with UUID-suffixed slug; teardown TRUNCATEs)

The TRUNCATE list extends to: `projects, items, modules, parts, item_hardware_lines, project_hardware_catalog, project_hardware_catalog_log, item_stages, item_status_log, item_edit_log` (+ existing `workspace, app_user, session, audit_log`).

### 7.2 New test files

```
apps/api/tests/
  test_rbac_drafter.py         # narrow drafter-or-above gate; 6-role × 4-action grid
  test_home_dashboard.py        # composite query shape; role-shape personalization
  test_projects_routes.py       # CRUD; role scoping
  test_items_routes.py          # CRUD + soft-lock + cross-workspace 404
  test_parts_routes.py          # parts/modules CRUD; rev-C flag
  test_hardware_lines_routes.py # CRUD + project_hardware_catalog log writes + availability
  test_lifecycle_status.py      # PATCH lifecycle/{stage_key}; PATCH status; transition log writes
  test_lock_semantics.py        # claim-on-first-save; non-owner warning; manual transfer
```

### 7.3 Existing test regressions

- `test_permissions.py` — adds `drafter` row (~6 new parametrize cases for tracking/list/orderbook/it_management).
- `test_users_routes.py` — `_VALID_ROLES` set in `users/routes.py` updates to include `drafter`.
- `test_auth_routes.py` — login as Noa now returns `auth_role: "drafter"`.

### 7.4 Coverage targets

Per `~/.claude/rules/common/testing.md` 80% minimum. PM Workbench surface is large; expect ~35-50 new tests covering:
- Every endpoint × authorized role × forbidden role pair
- Soft-lock claim, warning, override-audit
- Lifecycle PATCH writes log + audit
- `project_hardware_catalog` add/remove emits log row in same txn
- `/home/dashboard` shape per role
- Cross-workspace isolation

Frontend: no unit tests in v1. Visual regression deferred.

### 7.5 E2E smoke additions

Two new spec files extending Foundation's `tests/e2e/smoke.spec.ts`:

```
tests/e2e/
  pm_workbench.spec.ts    # PM happy path (rin.park@hartwood.test)
  drafter_editor.spec.ts  # Drafter happy path (noa.lindqvist@hartwood.test)
```

`pm_workbench.spec.ts` flow:
1. Login as Rin (manager).
2. Land on `/home`; assert 4 metric cards + project sidebar shows >=1 seeded project.
3. Click sidebar project -> `/tracking?project_id=...`.
4. Assert >=1 item row; CUTLIST->QTY locked layout.
5. Click ▶ on an item -> `/items/{id}?tab=cutlist`. Assert "Return to home" link visible.
6. Click "Return to home" -> URL ends `/home`.

`drafter_editor.spec.ts` flow:
1. Login as Noa (drafter).
2. Land on `/home`; "My Day" lists >=1 item.
3. Click item -> editor opens.
4. Cutlist tab: "Add row" -> fill `qty=2, part_name="Test"` -> blur -> assert PATCH success.
5. Hardware tab: pantry row `+` -> assert new line in cart.
6. Footer "Lock" -> click -> assert lock state flips.
7. Click `[x]` close-window -> either window closes or `/home` reached.

E2E uses existing `make e2e-docker` Makefile target.

### 7.6 Seed data extensions

`seed/hartwood_joinery.py` adds:

```python
PROJECTS = [
    ("ALF-001", "Alfred Street Renovation", "rin.park@hartwood.test"),
    ("TRT-014", "Trentham Heights",          "theo.blake@hartwood.test"),
]
# 5 items per project, each with:
#   - 1 module containing 3-4 parts
#   - 2-3 hardware lines (project_hardware_catalog populated)
#   - lifecycle: REQ done, SM done, LISTED varying
#   - status varies (CLEAR / LIVE / HOLD distribution)
```

Seed is idempotent (`ON CONFLICT DO NOTHING`). Re-runnable after `make test`.

### 7.7 Acceptance checklist

- `make migrate` reaches revision `0009`.
- `make seed` creates 2 projects + 10 items + ~30 parts + ~25 hardware_lines.
- `curl /api/home/dashboard` (cookie-authed as Rin) returns metrics + favourites.
- Login as Rin -> `/home` renders 4 metric cards + sidebar with 2 projects.
- Click project -> `/tracking?project_id=X` renders 5 rows; availability strip says "no orders".
- Click ▶ -> `/items/{id}?tab=cutlist`. Cutlist grid shows >=3 part rows. "Return to home" visible.
- Add a part row inline; PATCH succeeds; row persists on refresh.
- Switch to Hardware tab -> pantry lists rows; cart lists >=2 lines; availability chips render `warn:no orders`.
- Click "Lock" -> button toggles to "Unlock"; `audit_log` shows `item.lock` event.
- Login as Juno (foreman / `editor`). Open same item — soft-lock banner shows "Locked by Noa Lindqvist".
- PATCH a part as Juno -> 403 (drafter-narrow gate).
- PATCH lifecycle `CNC.done_date` as Juno -> 200 (editor allowed).
- Login as Mina (`purchase_officer`) — `/home` renders fewer cards; `/items/{id}` is read-only.
- Login as Aria (admin) — `/projects` allows creating new project; created with `pm_id = self`.
- Cross-workspace: workspace B admin -> GET workspace A item -> 404.
- `make test` -> all suites green (existing 34 + new ~40 = ~74 passing).
- `make e2e-docker` -> 3 smoke specs pass (Foundation's 1 + 2 new).
- `audit_log` rows present for every mutation; `item_edit_log` populated; `project_hardware_catalog_log` has add/remove rows from seed.

---

## 8. File Structure

```
apps/api/app/
  auth/
    rbac.py              # + require_drafter()
    permissions.py        # + 'drafter' row in MATRIX
    sessions.py           # + jtbd_role on AuthUser
  home/
    __init__.py
    routes.py             # GET /home/dashboard
    queries.py
    schemas.py            # HomeDashboardOut + sub-models
  projects/
    __init__.py
    routes.py             # CRUD + favourites
    queries.py
    schemas.py
  items/
    __init__.py
    routes.py             # CRUD + lock + lifecycle + status
    queries.py
    schemas.py
  parts/
    __init__.py
    routes.py             # modules + parts CRUD
    queries.py
    schemas.py
  hardware_lines/
    __init__.py
    routes.py             # hardware_lines + project_hardware_catalog + availability
    queries.py
    schemas.py
  main.py                  # mount 5 new routers

db/alembic/versions/
  0008_drafter_role.py            # CHECK + matrix + Noa flip
  0009_user_id_repoint.py         # legacy users -> app_user; + projects.pm_id; drop legacy users

seed/
  hartwood_joinery.py             # + PROJECTS + items + parts + hardware_lines

apps/web/app/(app)/
  home/page.tsx                   # replaces dashboard stub
  projects/page.tsx               # NEW project list/CRUD
  tracking/page.tsx               # replaces stub
  items/[id]/page.tsx             # NEW Drafter Item Editor
  items/[id]/cutlist/_components/ # parts grid + module tree client comps
  items/[id]/hardware/_components/# pantry + cart client comps

apps/web/components/chrome/
  SideBar.tsx                      # FAV/ALL toggle (replaces — stub)
  TopBar.tsx                       # + editor-mode logic
  ProjectSidebar.tsx               # NEW; client component for FAV toggles

apps/web/components/pm/
  StatusChip.tsx                   # HStatus mappings
  AvailabilityChip.tsx             # row availability indicator
  StageDates.tsx                   # 10-stage due/done date row

apps/web/lib/
  pm-types.ts                      # shared TS types matching API schemas

tests/e2e/
  pm_workbench.spec.ts             # NEW
  drafter_editor.spec.ts           # NEW

apps/api/tests/
  test_rbac_drafter.py
  test_home_dashboard.py
  test_projects_routes.py
  test_items_routes.py
  test_parts_routes.py
  test_hardware_lines_routes.py
  test_lifecycle_status.py
  test_lock_semantics.py
```

---

## 9. Sprint Plan (rough)

The implementation plan (next step after spec approval) breaks this into bite-sized tasks. High-level phasing:

1. **Phase 1 — Schema + RBAC**: migrations 0008, 0009; permissions matrix update; `require_drafter()` gate; tests.
2. **Phase 2 — API Read Surface**: `/home/dashboard`, `/projects`, `/tracking` reads, `/items/{id}` GET, availability roll-up.
3. **Phase 3 — API Write Surface**: items / parts / modules / hardware_lines / project_hardware_catalog mutations; lock; lifecycle/status writes; audit + edit_log integration.
4. **Phase 4 — Seed data extension**: projects + items + parts + hardware lines.
5. **Phase 5 — Web shell**: SideBar with FAV/ALL; TopBar editor-mode swap; `/home` layout; `/projects` page; `/tracking` page.
6. **Phase 6 — Drafter Editor**: tab shell + Return controls; Cutlist (parts grid + module tree); Hardware (pantry + cart); Log tab; soft-lock banner; footer.
7. **Phase 7 — E2E specs + acceptance**: 2 new Playwright specs; doc update; final acceptance run.

Estimated: **~45-60 implementation tasks** vs Foundation's 31.

---

## 10. Out-of-Scope Guard

Prevents scope creep into later sub-projects:

- **No PDF generation.** Print buttons rendered but disabled; tooltip "ships in sub-project #5".
- **No CV CSV import.** Three-way merge UI defers to sub-project #5.
- **No Procurement UI.** Backend ported in Foundation T22; UI is sub-project #4. "Open Procurement" button hidden behind feature flag.
- **No Exec Dashboard variants.** Only `HiDashA` (Command deck) ships. B/C/D/E artboards are reference-only.
- **No real-time push.** Request/refresh model: SWR-style on focus.
- **No Cabinet Vision integration.** Board tab placeholder.
- **No Shop Floor Ops surfaces.** Foreman gets read access only.
- **No file uploads.** SketchUp / CAB Vision file paths stored as text strings.

---

## 11. Resolved Decisions

- **Q1 scope:** Option B — PM Project Workbench grid + Drafter Item Editor merged.
- **Q2 in/out:**
  - #29 role-based landing -> in v1
  - #31 Open Procurement button -> hidden behind flag
  - #32 availability strip -> in v1
  - CV import -> skipped
  - Manual parts entry -> in v1 (only path)
  - PDF -> visible-but-disabled
  - Lock/Unlock -> soft-lock with warning
  - Log tab -> in v1
  - Board tab -> visible-but-deferred placeholder
- **Q3 RBAC enforcement:** Option D — narrow `drafter` auth_role for items/modules/parts/hardware_lines/project_hardware_catalog mutations; matrix unchanged elsewhere.
- **Section 2 legacy `users` FKs:** Option A — repoint all to `app_user.id`, drop legacy `users` table.
- **Return to home affordances:** dual — TopBar "<- Return to home" link (replaces tab strip in editor mode) + `[x]` close-window button in editor header.
- **State management:** raw `fetch()` + URL params + controlled inputs. No TanStack Query, no React Hook Form, no Zustand in v1.

---

## 12. Cross-References

- `legacy/trackingv2.md` — canonical v1 build plan.
- `legacy/product_spec.md` — product overview, role model, status taxonomy.
- `legacy/hi-*.jsx`, `legacy/Joinery Workflow Hi-fi.html` — visual binding for every surface.
- `docs/superpowers/specs/2026-04-22-foundation-design.md` — Foundation spec (sub-project #1).
- `docs/superpowers/plans/2026-04-22-foundation.md` — Foundation implementation plan (31 tasks; reference style).
- `CLAUDE.md` — repo nature, dev loop, design system, terminology pins.

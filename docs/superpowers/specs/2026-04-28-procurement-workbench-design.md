# JoineryFlow Procurement Workbench v1 — Design Spec

**Date:** 2026-04-28
**Sub-project:** #4 (Procurement Workbench v1)
**Branch base:** `feat/foundation` (post PM Workbench merge)
**Prior context:** `docs/superpowers/specs/2026-04-22-foundation-design.md`, `docs/superpowers/specs/2026-04-25-pm-workbench-design.md`, `legacy/trackingv2.md` §6

---

## 0. Goal

A PM looking at the **"0 ready / 2 blocked"** availability chip on a tracking row can drill into Procurement, see exactly which materials are blocking which item, place a batch order, allocate it, and clear the block — without leaving the app.

A Procurement officer (`purchase_officer`) can work cross-project: see all open batches grouped by supplier, drill into a project to act.

A Drafter (elevated to PM-parity authority for Procurement; see §7) can do the same as a manager.

---

## 1. Scope

### In scope

1. **Project material view** — every material a project consumes, grouped by the 6 catalog tables. Per row: demand · on-order · received · allocated · shortfall · earliest ETA · status pill.
2. **Batch editor** — CRUD on `procurement_batches` (create, update, soft-cancel).
3. **Allocation editor** — many-to-many linker between batches and `item_hardware_lines` with live "remaining unallocated" arithmetic.
4. **Catalog maintenance** — workspace-scoped CRUD UI for the 6 material catalog tables.
5. **Cross-project queue** — `/orderbook` top-tab landing for `purchase_officer`. Read-only at this surface; mutations happen in the project context.
6. **Item-scoped availability drawer** — opened by clicking the availability chip on a tracking row. Surfaces hardware-line-level shortfall + actions.

### Out of scope (deferred to v2 or later)

- Supplier email integration / mailto / templated PO PDF
- Stock / "company standing stock" inventory tracking (treated as a batch with `supplier='Stock'`)
- Real-time push notifications to the Machine team
- Touching the legacy `/procurement/*` namespace (orders, vendors, budget, approvals, inventory) — left mounted but unused
- Catalog import from CSV
- Supplier table (it remains free-text on batches in v1)
- Cost-center / budget linkage

---

## 2. Architecture

### 2.1 Backend layout

New module `apps/api/app/procurement_v1/` with one router per entity. Mount paths are **top-level** to avoid colliding with the legacy `/procurement/*` namespace, which is left in place untouched.

| Router | Mount path | Verbs | Purpose |
|---|---|---|---|
| `materials/routes.py` | `/projects/{pid}/materials` | `GET` | Project material rollup |
| `materials/routes.py` | `/items/{iid}/availability` | `GET` | Per-item drilldown for the availability drawer |
| `batches/routes.py` | `/batches` | `GET, POST` | List (filterable: project, supplier, status, eta_bucket); create |
| `batches/routes.py` | `/batches/{bid}` | `GET, PATCH, DELETE` | DELETE = soft-cancel (sets `cancelled_at`) |
| `allocations/routes.py` | `/batches/{bid}/allocations` | `GET, POST` | List + create within a batch |
| `allocations/routes.py` | `/allocations/{aid}` | `PATCH, DELETE` | Edit qty, remove |
| `catalogs/routes.py` | `/catalogs/{type}` | `GET, POST` | `type ∈ {board, hardware, custom_made, benchtop, appliance, hire}` |
| `catalogs/routes.py` | `/catalogs/{type}/{mid}` | `GET, PATCH, DELETE` | Per-row CRUD |
| `queue/routes.py` | `/procurement-queue` | `GET` | Cross-project rollup |

All routers mounted from `apps/api/app/main.py`. Auth via `require_permission("orderbook", action)`. SQL via SQLAlchemy Core `text()` (no ORM models), matching repo convention.

### 2.2 Web layout

```
apps/web/app/(app)/
  orderbook/page.tsx                              # cross-project queue (replaces stub)
  projects/[id]/procurement/
    page.tsx                                      # tabs: Materials | Batches | Catalog
    _components/
      ProjectMaterialsTable.tsx
      BatchesTable.tsx
      BatchDrawer.tsx                             # create/edit batch + inline allocations
      AllocationEditor.tsx                        # qty distribution UI inside drawer
      CatalogTabs.tsx                             # 6 sub-tabs, simple CRUD per type
  tracking/page.tsx                               # adds availability-chip click handler

apps/web/components/procurement/
  AvailabilityDrawer.tsx                          # item-scoped drawer over /tracking
  EtaPill.tsx
  ShortfallPill.tsx
  MaterialTypeTag.tsx
  BatchStatusPill.tsx

apps/web/lib/
  procurement-types.ts                            # mirrors API schemas
  procurement-fetch.ts                            # tiny fetch wrappers
```

State management: same approach as PM Workbench — raw `fetch()` + URL search params + controlled inputs. No TanStack Query / RHF / Zustand.

### 2.3 Two-level drill (item-scoped → project-scoped)

The "0 ready / 2 blocked" chip on a tracking row is a **client-only drawer trigger**, not a route navigation:

1. PM clicks chip → `<AvailabilityDrawer itemId={id}>` opens **over** `/tracking`.
2. URL gains `?drawer=item-availability&itemId=N` so the drawer survives refresh and can be deep-linked.
3. Drawer fetches `GET /items/{iid}/availability` and shows hardware lines + per-line state (need / on-order / received / allocated / shortfall).
4. Two actions per line:
   - **Allocate from existing batch** — expand inline allocation editor scoped to that line + matching material.
   - **Order more** — opens `BatchDrawer` (modal-over-modal is acceptable; small surface) pre-filled with the material.
5. A "Switch to project view" link routes to `/projects/{pid}/procurement?material_id=X`, closing the drawer and opening the project view filtered to that material.

### 2.4 Cross-project queue (`/orderbook`)

Default landing for `purchase_officer`. Visual target: `HiOrderbookOpen` artboard — dense table grouped by supplier, mono font for PO/dates/$.

- Subtabs: `Open · In transit · Delivered · Cancelled`
- Filters: supplier, project, ETA bucket
- Per row: PO ref · supplier · project · material · qty · ETA · status pill · "Open in project" link → `/projects/{pid}/procurement?batch_id=X`

Read-only here. All mutations happen in the project context to keep the per-project audit trail clean.

---

## 3. Data model

**No new tables.** Migration 0001 already has every table needed: `procurement_batches`, `batch_allocations`, `project_hardware_catalog`, plus the 6 catalog tables (`board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`).

### 3.1 Migration 0012 — small additions

| Change | Reason |
|---|---|
| `ALTER TABLE procurement_batches ADD COLUMN cancelled_at timestamptz` | Soft-cancel path: a batch with allocations cannot be physically deleted without cascading damage; soft-cancel preserves history. |
| `CREATE INDEX idx_batches_supplier ON procurement_batches (supplier)` | The cross-project queue groups by supplier. |
| `CREATE INDEX idx_alloc_batch ON batch_allocations (batch_id)` | Allocation lookups inside `BatchDrawer` and the rollup query. |

### 3.2 Status semantics (derived, never stored)

```text
batch_status =
  CANCELLED  if cancelled_at IS NOT NULL
  DELIVERED  elif received_date IS NOT NULL
  IN_TRANSIT elif ordered_date IS NOT NULL
  OPEN       else
```

Computed in SQL via a `CASE` expression. Returned from API as a string field; not persisted.

### 3.3 Material rollup query (the expensive one)

The Project Material View runs **one** query per project:

```sql
WITH demand AS (
  -- HARDWARE: sum(item_hardware_lines.qty) grouped by phc.material_type, phc.material_id
  SELECT phc.material_type, phc.material_id,
         SUM(ihl.qty) AS qty_demand
    FROM item_hardware_lines ihl
    JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
    JOIN items i ON i.item_id = ihl.item_id
   WHERE i.project_id = :pid
   GROUP BY phc.material_type, phc.material_id

  UNION ALL

  -- BOARD: sum(parts.qty) grouped by parts.board_material_id
  SELECT 'BOARD' AS material_type, p.board_material_id AS material_id,
         SUM(p.qty) AS qty_demand
    FROM parts p
    JOIN modules m ON m.module_id = p.module_id
    JOIN items   i ON i.item_id   = m.item_id
   WHERE i.project_id = :pid
     AND p.board_material_id IS NOT NULL
   GROUP BY p.board_material_id
),
batches AS (
  SELECT material_type, material_id,
         SUM(qty_ordered)  FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS qty_on_order,
         SUM(qty_received) AS qty_received,
         MIN(eta_date)     FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS earliest_eta
    FROM procurement_batches
   WHERE project_id = :pid
   GROUP BY material_type, material_id
),
allocations AS (
  SELECT pb.material_type, pb.material_id,
         SUM(ba.qty_allocated) AS qty_allocated
    FROM batch_allocations ba
    JOIN procurement_batches pb ON pb.batch_id = ba.batch_id
   WHERE pb.project_id = :pid
   GROUP BY pb.material_type, pb.material_id
)
SELECT d.material_type, d.material_id,
       d.qty_demand,
       COALESCE(b.qty_on_order, 0)  AS qty_on_order,
       COALESCE(b.qty_received, 0)  AS qty_received,
       COALESCE(a.qty_allocated, 0) AS qty_allocated,
       GREATEST(d.qty_demand - COALESCE(b.qty_received, 0) - COALESCE(b.qty_on_order, 0), 0) AS shortfall,
       b.earliest_eta
  FROM demand d
  LEFT JOIN batches     b USING (material_type, material_id)
  LEFT JOIN allocations a USING (material_type, material_id);
```

The 6 catalog tables are then joined in a follow-up `SELECT … WHERE material_id IN (…)` per type to enrich each row with `name + sku`. Cheap.

---

## 4. Project Material View

Single table grouped by `material_type` (6 collapsible sections). Per row:

| Column | Source |
|---|---|
| Material | catalog name + SKU |
| Demand | `qty_demand` |
| On order | `qty_on_order` |
| Received | `qty_received` |
| Allocated | `qty_allocated` |
| Shortfall | derived `max(0, demand − received − on_order)` |
| Earliest ETA | `earliest_eta` |
| Status pill | `OK` (shortfall=0) / `SHORT` (shortfall>0) / `OVERDUE` (`earliest_eta < CURRENT_DATE` and shortfall>0) |

Click row → expands inline:

- **Batches for this material** — sub-table; click row → opens `BatchDrawer`.
- **Items consuming this material** — sub-table; click row → opens `/items/{id}?tab=hardware` (or `?tab=cutlist` for `BOARD`).

URL state: `?expanded=BOARD:42` keeps the row expanded across refresh.

---

## 5. Batch editor (drawer)

Drawer over the project Procurement page. Form fields mirror `procurement_batches`:

- Project (locked from URL context)
- Material type (select) → Material (select chained to type, populated from the 6 catalog tables)
- Supplier (free text)
- PO ref (free text)
- Qty ordered (numeric) · Qty received (numeric)
- Cost per unit (numeric)
- Ordered date · ETA date · Received date
- Notes
- "Cancel batch" action (sets `cancelled_at = now()`; only enabled if no allocations or all allocations zero — otherwise show "Remove allocations first" tooltip)

Below the form, **inline AllocationEditor**:

- Each allocation row: item code · description · line note · qty
- Sum at bottom: `allocated / qty_received` with a chip going green when fully allocated
- "+ Allocate to item line" picker — autocomplete searches across the project's `item_hardware_lines` matching this batch's material; only lines with `shortfall > 0` are shown by default (toggle to show all)

Save model: PATCH for existing batches, POST for new. Allocation CRUD is per-row (no atomicity across siblings). Server-side guard: **sum of allocations ≤ qty_received** (or `qty_ordered` if not yet received). Over-commit returns `409 Conflict`.

---

## 6. Catalog maintenance

`/projects/[id]/procurement?tab=catalog` → 6 sub-tabs, one per catalog table. Simple table CRUD per tab. Add/edit dialog per type because the columns differ (board has thickness/colour; appliance has model/wattage; benchtop has finish; etc.).

The 6 catalogs are **workspace-scoped, not project-scoped** — they're shared across all projects in a workspace. v1 ignores cross-workspace concerns.

Catalog mutations write `audit_log`. They do **not** write `project_hardware_catalog_log` because that log is for `project_hardware_catalog` membership changes, not for the underlying SKU table.

---

## 7. RBAC + audit

| Role | Read | Write batches/allocations | Catalog CRUD | Notes |
|---|---|---|---|---|
| admin | ✓ | ✓ | ✓ | full |
| manager | ✓ | ✓ | ✓ | PM |
| **drafter** | **✓** | **✓** | **✓** | **elevated to PM parity for Procurement (this spec)** |
| purchase_officer | ✓ | ✓ | ✓ | primary user |
| editor | ✓ | — | — | Foreman / Machine read-only |
| viewer | ✓ | — | — | |

### 7.1 Code consequences of drafter elevation

- `apps/api/app/auth/permissions.py` — drafter gains `("orderbook", "write")` and `("orderbook", "approve")` in the static matrix.
- `apps/api/app/auth/rbac.py` — `require_permission("orderbook", action)` is matrix-driven, no special-casing required.
- `tests/test_permissions.py` and `tests/test_rbac_drafter.py` — extend with the elevated drafter row.
- No DB migration is required for this RBAC change (matrix is in code, not data).

### 7.2 Audit

Every mutation writes `audit_log` (workspace-scoped) with `event ∈ { batch.create, batch.update, batch.cancel, allocation.create, allocation.update, allocation.delete, catalog.create, catalog.update, catalog.delete }`. No `item_edit_log` writes (Procurement is project-scoped, not item-scoped).

---

## 8. Testing

### 8.1 API (~40 cases)

- RBAC matrix per endpoint × role (parametrised, mirrors `test_rbac_drafter.py`)
- CRUD per entity (batch, allocation, catalog) — happy path + 4xx edge cases
- Rollup correctness: golden-data fixture (3 items, 2 batches, partial allocations) → assert exact rollup numbers
- Allocation over-commit guard: POST allocation that would push sum > qty_received → 409
- Soft-cancel guard: DELETE batch with non-zero allocations → 409 with explanatory body
- Cross-workspace isolation: a manager from workspace A cannot read or mutate batches in workspace B

### 8.2 Web

No component tests in v1 (project hasn't established RTL pattern). Visual regression deferred.

### 8.3 Playwright E2E

One new spec `tests/e2e/procurement.spec.ts`:

1. Login as PM (`rin.park@hartwood.test`)
2. Navigate to `/tracking?project_id=1`
3. Click "0 ready / 2 blocked" chip on the first row
4. Drawer opens, asserts hardware lines visible
5. Click "Order more" on first line → BatchDrawer opens
6. Fill supplier, qty, eta_date → Save
7. Close drawer, re-open chip → assert "1 ordered, 1 blocked" (or similar)

---

## 9. Visual style

Tokens from `apps/web/app/globals.css`. Mono font (`.h-mono`, with `tnum`) for PO refs, dates, money columns — the utility class is **not yet wired** in `globals.css` and gets added as a small task in §10.

Status pills use the `bad/warn/good` tokens already added to globals (`StatusChip` precedent). New components: `EtaPill`, `ShortfallPill`, `BatchStatusPill`, `MaterialTypeTag`.

No new colours invented. Reference: `procurement_orderbook_dashboard.html` in `legacy/` for the dense-table feel.

---

## 10. Implementation phases (preview for the plan)

The actual task-level plan goes in `docs/superpowers/plans/2026-04-28-procurement-workbench.md`. Sketch:

1. **Phase 1 — RBAC + schema additions**
   - Migration 0012 (`cancelled_at`, indexes)
   - `permissions.py` drafter elevation on `orderbook`
   - Permission tests + RBAC drafter tests extended
   - Wire `.h-mono` utility in `globals.css` and `tokens.ts`

2. **Phase 2 — Material rollup API**
   - `procurement_v1/materials/{queries,routes,schemas}.py`
   - `/projects/{pid}/materials` + `/items/{iid}/availability`
   - Golden-data rollup tests

3. **Phase 3 — Batches + Allocations API**
   - `procurement_v1/batches/{queries,routes,schemas}.py`
   - `procurement_v1/allocations/{queries,routes,schemas}.py`
   - Over-commit + soft-cancel guards
   - CRUD tests

4. **Phase 4 — Catalogs API**
   - `procurement_v1/catalogs/{queries,routes,schemas}.py`
   - Type-discriminated POST/PATCH (one Pydantic model per type)
   - CRUD tests

5. **Phase 5 — Cross-project queue API**
   - `procurement_v1/queue/{queries,routes,schemas}.py`
   - `/procurement-queue`

6. **Phase 6 — Web: AvailabilityDrawer on tracking**
   - New components, drawer + URL state
   - Action wiring to BatchDrawer
   - E2E coverage of the resolution flow

7. **Phase 7 — Web: project Procurement page**
   - Materials / Batches / Catalog tabs
   - BatchDrawer + AllocationEditor

8. **Phase 8 — Web: Orderbook cross-project queue**
   - Replaces `/orderbook` stub
   - Subtabs + filters

9. **Phase 9 — Polish, seed expansion, CLAUDE.md note**
   - Extend `seed/hartwood_joinery.py` with batches + allocations covering the demo flow
   - Append Procurement Workbench dev notes to `CLAUDE.md`

---

## 11. Open assumptions (callable after spec approval)

These are decisions baked into the spec that you can still override before plan time:

1. **Routes use top-level paths** (`/batches`, `/catalogs/{type}`) instead of nested `/procurement/v1/`.
2. **AvailabilityDrawer is a drawer, not a route.** Alternative: full-page route at `/items/[id]/availability`.
3. **Inline allocation editor inside BatchDrawer**, not a standalone "allocate" page.
4. **One new migration (0012)** for status helpers + soft-cancel column.
5. **Catalog is workspace-scoped**, not project-scoped.
6. **No Supplier table** — supplier remains free text on batches.

---

## 12. Definition of done

- All 9 phases land in their own commits on a `feat/procurement-workbench` branch.
- API: ~40 new pytest cases passing on top of the existing 116; no regressions.
- Web: 1 new Playwright spec passing; existing 3 specs still passing.
- Seed: `make seed` produces a workspace where the resolution flow demo works without manual data entry.
- Branch merges into `feat/foundation` cleanly with `--no-ff`.
- `CLAUDE.md` gets a Procurement Workbench section appended.

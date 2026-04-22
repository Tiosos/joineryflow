# Project Information Management (v1) — Build Plan

> Replaces `tracking.md`. This is the detailed plan for **Product Module 1**
> of `product_spec.md` — the Tracking + Procurement + Drafter Editor that
> runs on a shared database with Shop Floor Ops (v2) and CV Integration (v2).
>
> Read `product_spec.md` first for the broader product context. This document
> focuses on *what to build for the v1 module*.

## 1. Context & Scope Boundary

**In scope for this plan:**
- The role-based landing page + role-specific entry points
- PM Project Workbench (the evolved `tracking_dashboard.html`)
- Drafter Item Editor (new, item-centric, three-list tabs)
- Procurement module (independent window, schema-driven, minimal UI)
- CV CSV import (one-shot, inside Item Editor)
- Data-model work: Material Catalog (6 tables), ProjectHardwareCatalog,
  Item/Module/Part hierarchy, CutPlan skeleton

**Out of scope (here):**
- Shop Floor Ops (Foreman's Today Board, efficiency analytics) — v2 module
- Machine team's Cut Schedule UI — v2
- Real-time push/notifications — v1 is request/refresh
- CV push-back (CV is closed)
- Per-part painting tracking (paper-only, confirmed)

## 1.5 Hi-fi Surface Map

The hi-fi canvas (`Joinery Workflow Hi-fi.html`) + the five `hi-*.jsx` files
are the **visual spec** for every v1 surface. `wireframes-hifi.jsx` owns the
shared chrome, palette, and primitives — do not invent new tokens.

### 1.5.1 Surface → artboard binding

| v1 surface | Hi-fi artboard id | Source component | File |
|---|---|---|---|
| Login | `auth-login` | `HiLogin` | `hi-login-it.jsx` |
| Role-based landing (§4 #29) | `dash-a` | `HiDashA` (Command deck, **default**) | `hi-dashboard.jsx` |
| PM Project Workbench — tracking grid | `track-a` | `HiTracking` | `hi-tracking-list.jsx` |
| Drafter Item Editor — Cutlist tab (§5.2) | `list-cut` | `HiListCutlist` | `hi-tracking-list.jsx` |
| Drafter Item Editor — Hardware tab (§5.3) | `list-hw` | `HiListHardware` | `hi-tracking-list.jsx` |
| Procurement Module (§6) | `order-open` | `HiOrderbookOpen` | `hi-order-dwg-sample.jsx` |
| Shop Drawings register | `dwg-grid` | `HiShopDrawings` | `hi-order-dwg-sample.jsx` |
| Sample approval board | `sample-board` | `HiSamplebook` | `hi-order-dwg-sample.jsx` |
| Admin / IT Management | `auth-it` | `HiITManagement` | `hi-login-it.jsx` |
| Exec alternate dashboards (deferred v2) | `dash-b`..`dash-e` | `HiDashB/C/D/E` | `hi-dashboard.jsx` |

**Variants policy.** Only Dashboard A (Command deck) ships in v1. B
(Activity stream), C (My-Day kanban), D (Week Gantt), E (BrB staff board)
are kept as references for v2 role-specific landings.

### 1.5.2 Top-level IA (6 tabs)

Hi-fi canonical tab order, applied via `HAppChrome.tabs`:

`Dashboard · Tracking · List · Orderbook · Shop Dwgs · iSample`

The current `tracking_dashboard.html` exposes 7 tabs (Cutlist and Hardware
split, iVariations separate). v1 migrates to the 6-tab layout by merging
**Cutlist + Hardware** into one **List** tab with subtabs. iVariations
moves under the item drawer, not a top-level tab.

### 1.5.3 Chrome & primitives (from `wireframes-hifi.jsx`)

- **HAppChrome** — 48px top bar (logomark `◴` + wordmark + tab strip +
  search pill + avatar), optional subtab strip beneath, 220px left
  project sidebar with FAV / ALL toggles, main body in `.h-wrap`.
- **Primitives** — `.h-btn` / `.h-btn-primary` / `.h-btn-accent` /
  `.h-btn-ghost`, `.h-card`, `.h-pill`, `.h-eyebrow`, `.h-input`,
  `.h-subtab`, `.h-row-hover`, `.h-mono`.
- **Icons** — `Icons` dictionary in `wireframes-hifi.jsx`; reuse names.
- **Status** — `HStatus` component; mappings fixed (see §1.5.5).

### 1.5.4 Design tokens (H palette)

| Token | Value | Use |
|---|---|---|
| `--h-bg` | `#fbfaf7` | Page bg |
| `--h-surface` | `#ffffff` | Card / row |
| `--h-surface-alt` | `#f4f2ed` | Group header, subtle fill |
| `--h-line` | `#e4e0d8` | 1px borders |
| `--h-ink` / `--h-ink2` / `--h-ink3` | `#1b1a17` / `#5a574f` / `#8f8b80` | Text ramp |
| `--h-accent` | `#c96442` | Terracotta primary accent |
| `--h-accent-soft` | `#f3e0d6` | Highlighted row (e.g. rev-C) |
| `--h-good` | `#3f7d48` | CLEAR / APPROVED / ARRIVED |
| `--h-warn` | `#c48a2e` | HOLD / NOTE! |
| `--h-bad` | `#b4443d` | VOID / REJECTED / OVERDUE |
| `--h-info` | `#3d6b8a` | SUBMITTED / ORDERED |

**Typography.** Inter (UI) + JetBrains Mono (part #, PO #, dates, money);
root has `font-feature-settings: "cv11","ss01","tnum"`.

### 1.5.5 Status taxonomy (fixed)

| Colour | States |
|---|---|
| good | `CLEAR`, `APPROVED`, `ARRIVED` |
| accent | `LIVE`, `RTO`, `NEXT` |
| warn | `HOLD`, `NOTE!` |
| bad | `VOID`, `REJECTED`, `OVERDUE` |
| info | `SUBMITTED`, `ORDERED` |
| neutral | `TBC` |

Gantt stage colours (when v2 schedules land): Draft `#94a3b8` · Review
`warn` · Cut `accent` · QC `info` · Pack `good`.

### 1.5.6 Role model reconciliation

Hi-fi `HiITManagement` defines **4 auth roles**: Admin · Manager · Editor ·
Viewer. v1 JTBD roles (§2.1) map as follows:

| JTBD role | Auth role |
|---|---|
| CEO | Admin |
| PM | Manager |
| Drafter | Editor |
| Procurement | Editor (scope = Procurement module) |
| Foreman (v1) | Viewer |
| Machine (v1) | Viewer |

Permissions are enforced by auth role + per-project scope; JTBD role
drives the *default landing surface* only.

## 2. Architecture

### 2.1 Role-based routing

All six roles hit the same login URL. Landing page is identical for
everyone: **project list + favourites + "today" summary**. Diverges from
there based on role — function entries are filtered by permissions.

| Role | Entry points visible on landing | Lands where by default |
|---|---|---|
| CEO | All | Exec Dashboard |
| PM | All for own projects | PM Project Workbench |
| Drafter | Item Editor + read-only Procurement for own projects | My-projects list → Item Editor |
| Foreman (v1) | Read-only Project Workbench for attribution | PM Project Workbench (read-only) |
| Machine (v1) | Read-only material ETA | Procurement (read-only) |
| Procurement | Procurement module + read-only Drafter hardware lists | Procurement dashboard (independent window) |

Foreman and Machine team have minimal v1 surfaces — their proper UIs are
v2. v1 is enough for them to *see* the data; writing back comes in v2.

### 2.2 Surfaces

**PM Project Workbench** = current `tracking_dashboard.html` with items
1–28 from the legacy `tracking.md` carried forward (see §4 below). This
surface is the most complete piece of v1.

**Drafter Item Editor** = new. Item-centric. Opens when Drafter (or anyone
with permission) clicks a row in the Project Workbench. See §5.

**Procurement Module** = independent window (spawned by a "Procurement"
link or keyboard shortcut), so users can put it on a second monitor
alongside the Project Workbench. Schema-driven grid over
`procurement_batch`, `allocations`, per-project material universe. Minimal
UI in v1 — the heavy lift is the data model. See §6.

**Exec Dashboard** = CEO view. Cross-project KPIs, weekly report generator.
Minimal v1: render the metrics that already aggregate from the tracking
schema. Deep analytics defer to v2.

### 2.3 Two-window workflow (no longer a workaround)

The two-screen PM/Drafter pattern is *supported but not required*:
- Drafter can open Item Editor on monitor 1 and Procurement on monitor 2
  for material cross-reference.
- Item Editor has an inline "material availability" strip per hardware
  line that answers the common query without ever opening Procurement.
- Procurement's "which items consume this batch?" join is one click, not
  a cross-window scan.

## 3. Data Model (v1)

The full model is in `product_spec.md` §5. What matters for *this build*:

### 3.1 Tables to add to `tracking_schema.sql`

Already in v1 schema (`tracking_schema.sql` as of this writing):
`users`, `projects`, `project_favourites`, `items`, `item_stages`,
`item_status_log`, `item_edit_log`, `stages` (lookup), `status_options`,
`status_symbols`.

New tables required for v1:
- `board_materials` — CV board codes (`18-PB` etc.)
- `hardware_materials` — supplier SKUs
- `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`
  (schema scaffolding; usage in v1 ranges from full CRUD for hardware +
  board to simple stubs for appliances/equipment_hire)
- `project_hardware_catalog` — link table, see spec §5.3
- `modules` — one row per MOD per item (populated by CV import in v2,
  editable manually in v1)
- `parts` — one row per CV-exported part, FK to `modules`
- `item_hardware_lines` — qty + material_id + note, FK to `items` and to
  the appropriate material table (via `material_type` discriminator)
- `procurement_batches`, `batch_allocations` — procurement schema from
  `procurement_schema.sql` adapted to the tracking module's foreign keys

### 3.2 Key invariants

- **Drafter is the only writer for item / module / part / hardware-line
  data.** Other roles read, propose changes, or correct post-hoc.
- **ProjectHardwareCatalog is mutable by Drafter and PM on that project.**
  Every `item_hardware_line.material_id` must resolve through this
  project-scoped catalog (not directly to the global catalog).
- **Module/Part rows exist but Drafter doesn't edit them in v1 UI.** They
  come from CV import (v2). v1 just stores the skeleton so CV import
  later doesn't need schema migration.
- **`Stage` in the items grid = site block (e.g. Joinery Lab, PC2, Stone,
  Block B).** It is *not* the production line or lifecycle stage. See
  spec §5.6.

## 4. PM Project Workbench — carry forward from `tracking.md`

All 28 numbered scope items from the original `tracking.md` remain in
force, implemented in `tracking_dashboard.html`, with the following
clarifications:

- Items 1–25: unchanged.
- **Item 26 (sub-tabs DATE/iTIME/HARDWARE/SITE MEASURE/INVOICE/QC):** still
  applies, but the placeholder columns under iTIME / HARDWARE / SITE
  MEASURE / INVOICE / QC are now schema-backed in v1 (wired to
  `board_materials` ETA for HARDWARE tab, labour-time from v2 schema for
  iTIME, etc.) rather than pure placeholders.
- **Item 27 (pixel-identical column lock CUTLIST→QTY across sub-panels):**
  Confirmed working; DATE is the authoritative layout.
- **Item 28 (status-symbol column + 2×2 header + filter dropdown):**
  Confirmed working.

New items specific to the v1 build:

29. **Role-based landing page** — shared for all six roles. Built from
    `HiDashA` (artboard `dash-a`): 4 metric cards (Overdue / Due today /
    In progress / Deliveries today), a **My day** list, a **Deliveries
    today** panel, and a **Team** strip with recent-activity feed. Project
    list lives in the `HAppChrome` left sidebar (FAV / ALL). Function-entry
    tiles filtered by signed-in role. Top-level route `/home`.
30. **"Open in Item Editor" as the row's primary action** — the existing
    ▶ triangle button (item #17) now opens the new Drafter Item Editor
    (§5) for users with write permission, and the legacy read-only
    details modal for everyone else. Permissions fork, same entry point.
31. **"Open Procurement" button in the project header** — opens the
    Procurement module in an independent window (not a modal), scoped to
    the current project. Designed for the two-monitor workflow.
32. **Material availability strip on every item row** — a small inline
    indicator per row showing "materials ready / N blocked" derived from
    `item_hardware_lines → batch_allocations → procurement_batches.eta`.
    Click to expand a per-hardware-line breakdown. Replaces the implicit
    "switch to Procurement window to check" workflow.

## 5. Drafter Item Editor (new, v1)

Item-centric full-page editor. Opens when a Drafter clicks an item row (or
equivalently, the ▶ button for users with write permission).

### 5.1 Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ ← Back to Project       ITEM DETAILS        CUTLIST # 297871     │
├──────────────────────┬───────────────────────────────────────────┤
│                      │  [ Cutlist ] [ Hardware ] [ Board ]       │
│ Item metadata        │                                            │
│ (left column)        │  (active tab body)                        │
│ - Level / Room       │                                            │
│ - Description        │  Cutlist:   CV import + line editor        │
│ - Stage (site)       │  Hardware:  picker from proj catalog       │
│ - Assembler/Lister   │  Board:     project-level optimisation     │
│ - Painting Req?      │             (view-only for most Drafters)  │
│ - Solid Surface Req? │                                            │
│ - Group/Item ID      │                                            │
│ - Estimator Notes    │                                            │
├──────────────────────┴───────────────────────────────────────────┤
│  Print Cutlist │ Print Hardware │ Print Combined PDF │ Lock/Unlock│
└──────────────────────────────────────────────────────────────────┘
```

**Hi-fi binding.** Visual target = `HiTracking` drawer pattern (artboard
`track-a`) for the left metadata column, and `HiListCutlist` / `HiListHardware`
(artboards `list-cut`, `list-hw`) for the tab bodies. Tabs rendered with
`.h-subtab`; footer buttons with `.h-btn` + `.h-btn-accent` for primary.

### 5.2 Cutlist tab

Visual pattern: `HiListCutlist` (artboard `list-cut`). Layout = 220px room
tree (left) + dense parts grid (right); rev-C rows use `--h-accent-soft`
background; CV-import banner sits as a dismissible `.h-card` above the grid.

- **CV Import widget** — file-picker for the CV CSV export for this item.
  On import: creates `modules[]` + `parts[]` rows under the item. Existing
  rows can be replaced (overwrite) or merged (keep Drafter edits).
- **Part list grid** — editable rows: qty, part name, len, wid, material
  (dropdown from `board_materials`), edge, colour, comment.
- **Item-level fields** — project description (free text), a few boolean
  options (painting, solid-surface, cutlist-printed flag, etc.).
- **Per-cutlist note field** — free text that appears on printed PDFs.
- **Lock semantics** — the Drafter who *creates* the cutlist has edit
  rights; other Drafters on the project have read-only by default, can
  request transfer.

### 5.3 Hardware tab

Visual pattern: `HiListHardware` (artboard `list-hw`). Layout = pantry
(left, grouped by catalogue category) → cart (right, 420px, grouped by
supplier) with qty stepper per line and footer totals. Status chips on the
availability column use `HStatus` mappings from §1.5.5.

- **Line editor** — each row: qty + material picker + note.
- **Material picker** — searches the project's `project_hardware_catalog`
  first; has an "Add from global catalog" affordance that pulls any row
  from `hardware_materials` into the project catalog (logs who added it).
- **Material availability column** — per row: "in stock", "ordered, ETA
  DD/MM", "not ordered", derived live from `batch_allocations`.
- **Rendering parity** — print output matches the `HARDWARE LIST sample
  PDF` layout: Qty / Type / Description / Supplier·Brand / Notes columns,
  with the item header block (Item / Level / Room / Stage / Lister).

### 5.4 Board tab

- **View of the project-level optimisation** scoped to this item's parts.
- In v1, editable only by the project's designated Optimisation Drafter;
  everyone else sees read-only.
- In v2, this becomes the CV-integration surface where nesting output
  feeds the Machine team's Cut Schedule.

### 5.5 Footer actions

- **Print Cutlist** → renders `parts[]` to PDF (template matches
  `CV export sample PDF` visual style).
- **Print Hardware** → renders `item_hardware_lines[]` to PDF (template
  matches `HARDWARE LIST sample PDF`).
- **Print Combined PDF** → merges: (1) cutlist cover note + (2) cutlist
  parts + (3) CV production drawing (uploaded per item) + (4) floor plan
  (uploaded per item) + (5) site-measure PDF (uploaded per item) + (6)
  optional painting parts list. One-click.
- **Lock / Unlock** — toggles the item's editable state for other Drafters.

### 5.6 Edit log

Every change on this editor writes to `item_edit_log` (already in schema).
Shown inline in a "Log" tab consistent with scope item #25.

## 6. Procurement Module (schema-driven, minimal v1 UI)

Independent-window app. **Visual target = `HiOrderbookOpen`** (artboard
`order-open`): subtabs `Open / In transit / Delivered / Returns /
Suppliers`, dense PO table grouped by supplier, `.h-mono` for PO#/dates/
money columns. Design tokens from §1.5.4; no redefinition.

Still evolves `procurement_orderbook_dashboard.html` styling where hi-fi
is silent; builds on `procurement_api.py` + `procurement_schema.sql` tables.

**v1 surfaces:**

1. **Project material view** — grid of all materials consumed by a
   project, grouped by material table (6 categories). Each row: material
   name + SKU + total qty demanded across items + on-order qty + received
   qty + allocated qty + shortfall. Click a row → drill to batches + the
   specific `item_hardware_lines` it supplies.
2. **Batch editor** — CRUD for `procurement_batches`. Supplier, PO ref,
   ordered/eta/received dates, qty, per-unit cost. No email integration in v1.
3. **Allocation editor** — many-to-many linker: given a batch, choose
   which `item_hardware_lines` consume it and in what qty. Live arithmetic
   for remaining unallocated qty.
4. **Material catalog maintenance** — simple CRUD tables for each of the
   six Material Catalog tables. Hidden behind a "Catalog" nav item; only
   accessible to PM and Procurement roles.

**Deferred to v2:**
- Supplier email integration (mailto + templated messages)
- Stock / inventory tracking (the "company standing stock" Drafters
  currently select from). v1 treats standing stock as just another
  procurement batch with `supplier = 'Stock'`.
- Real-time ETA push to Machine Team

## 7. CV CSV Import (v1 minimum)

Triggered inside the Drafter Item Editor → Cutlist tab → "Import from CV".

1. Drafter selects the CV CSV export for this item.
2. Backend parses the CSV into `modules[]` + `parts[]` rows under the item.
3. Any material codes not yet in `board_materials` are flagged; Drafter
   can add-to-catalog or remap on the fly.
4. Existing edits to the item's parts can be preserved via a three-way
   merge dialog (new CV vs existing DB vs proposed merge).

**Not in v1:**
- Automatic periodic re-sync with CV
- Pushing status back into CV (CV is closed)
- Auto-translation of CV field names (done manually via a small mapping
  table the Drafter maintains)

## 8. Migration from `tracking_dashboard.html`

The existing prototype becomes the **PM Project Workbench** surface
unchanged, except:

- ITEMS array is removed; data comes from the API.
- The modal that opens on ▶ click is replaced by a route to the new
  Item Editor page (see §5).
- The "Open Procurement" button is added to the project header (item #31).
- The "material availability strip" (item #32) is added to each row.

No visual redesign of the grid itself — items 1–28 keep their spec.

## 9. File Structure

**Existing (keep):**
- `procurement_orderbook_dashboard.html` — style reference. Still the
  canonical design-token source for every UI.
- `tracking_dashboard.html` — becomes PM Project Workbench; detached from
  in-memory ITEMS, wired to API.
- `procurement_api.py` + `procurement_schema.sql` — existing backend;
  extended to cover the six Material Catalog tables and
  `project_hardware_catalog`.
- `tracking_schema.sql` — existing v1 schema; extended per §3.1.
- `filemaker.md` — legacy field-name reference.

**New (this build):**
- `drafter_item_editor.html` — new Drafter Item Editor page (§5). Built
  from `HiTracking` drawer + `HiListCutlist` + `HiListHardware`.
- `exec_dashboard.html` — CEO surface (lightweight). Built from `HiDashA`.
- `home.html` — role-based landing page (§4 item 29). Built from `HiDashA`
  + `HAppChrome` sidebar (FAV/ALL project list).
- `shop_drawings.html` — Shop Dwgs tab (artboard `dwg-grid`, `HiShopDrawings`).
- `samplebook.html` — iSample tab (artboard `sample-board`, `HiSamplebook`).
- `it_management.html` — Admin surface (artboard `auth-it`, `HiITManagement`).
- `login.html` — Login split (artboard `auth-login`, `HiLogin`).
- `tracking_api.py` (or extend `procurement_api.py` into `trendgosa_api.py`)
  — backend endpoints for the tracking surfaces.
- `samples/` — reference PDFs (CV export + Hardware List) lived here as
  design-source material. Do not ship to production.

**Retired:**
- `tracking.md` — superseded by this file. Kept in repo for history.

## 10. Verification (v1)

1. Seed the DB with three projects (Alfred / Trentham / 7ss) and ~20
   items. Log in as each role in turn; confirm the landing page renders,
   favourites persist, role-filtered entry points behave.
2. As a Drafter, open an item → Item Editor → import a CV CSV → edit a
   few cutlist rows → add three hardware lines → print combined PDF.
   Verify the PDF matches `HARDWARE LIST sample PDF` and `CV export
   sample PDF` layouts visually.
3. As Procurement, create two batches for the same hardware material;
   allocate them across four items; open the item editor for one of those
   items and confirm the hardware-line availability strip reflects
   allocation + ETA correctly.
4. As PM, open the Project Workbench → confirm every scope item 1–28
   still works → click ▶ on a row and land in the new Item Editor.
5. As CEO, land on Exec Dashboard; confirm KPIs compute correctly from
   live data.
6. All date rendering: `DD/MM/YYYY`. All widths CUTLIST→QTY: identical
   across sub-tabs (item #27 regression check).
7. **Hi-fi parity check.** Open each new surface beside its artboard in
   `Joinery Workflow Hi-fi.html`. Verify: 48px top bar + 220px sidebar
   chrome, H palette tokens applied (no stray colours), Inter + JetBrains
   Mono typography, status chips use `HStatus` mappings from §1.5.5, and
   the 6-tab IA (§1.5.2) is in canonical order.

## 11. Resolved Decisions

See `product_spec.md` §7 for cross-product resolved decisions. Build-specific
ones:

- **CV import merge strategy.** **Three-way merge UI** (new CV vs existing
  DB vs proposed merge). UX-heavier but preserves Drafter edits safely;
  simple overwrite rejected. See §7 for the import workflow.
- **Print PDF engine.** **Headless Chrome → PDF.** Chosen for flexibility
  with multi-file merging (combined-PDF case pulls cutlist + CV drawing +
  floor plan + site-measure PDF + painting list in one pass). WeasyPrint
  rejected on merge-flexibility grounds.
- **"Optimisation Drafter" designation.** **Confirmed:** one Drafter per
  project runs board optimisation. Stored as `project.optimisation_drafter_id`
  (FK → `users.id`), editable by PM.

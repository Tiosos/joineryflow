# Trendgosa Production System — Product Spec

> Replaces the legacy FileMaker desktop system with a web-based, multi-role,
> multi-module suite sharing a single database. Derived from the brainstorming
> session captured in this repo; supersedes scattered planning in `tracking.md`.

## 1. Product Overview

Trendgosa's joinery business currently runs on FileMaker Pro, where a single
flat dashboard tries to serve everyone (CEO, PM, Drafter, Foreman, Machine
team, Procurement). This over-serves no one: every role reads the same 20+
column grid looking for the 2–3 columns that matter to them, and the
connective tissue that should live in the database (project ↔ item ↔ material
↔ purchase ↔ stock) lives instead in people's heads and in "open two windows
side-by-side" muscle memory.

**The product is one database with three independent-but-coupled apps**:

1. **Project Information Management** — Drafter / PM / CEO surface. Source of
   truth for every project, item, cutlist, and hardware list. v1 target.
2. **Shop Floor Ops** — Foreman-led workshop app. Worker assignment, today
   view, efficiency, quality. v2.
3. **Cabinet Vision Integration Layer** — Material catalog, cutlist import,
   board-optimisation handoff. Infrastructure for (1) and (2). v2.

v1 ships product (1) with data-model hooks for (2) and (3) already in place.

## 2. Users & Roles

Six roles, one codebase, role-based routing. All roles see the same login
landing page: project list + favourites + today's plan. Role-specific function
entries then branch from there.

| Role | Default view after login | What they own | Can peek into |
|---|---|---|---|
| **CEO** | Exec dashboard (cross-project KPIs, weekly auto-report) | All projects, add/edit/delete. | Every other role's view. |
| **PM** | Assigned projects' item progress grid (~ today's `tracking_dashboard.html`) | Schedules, stage targets, cost-of-labour visibility. | Drafter + Foreman + Machine + Procurement views for *own projects*. |
| **Drafter** | My-projects item list → item editor | All item details, cutlists, hardware lists, the project Hardware Catalog for their projects. **Final confirmer for any tracking data.** | Read-only into Procurement for material availability. |
| **Foreman** | Shop-floor Today Board (tablet/wall display) + Office PC back-office view | Worker assignment, completion logging, time records, Assembler efficiency. | Read-only item progress for attribution. |
| **Machine team** | Today's cut schedule | Daily cut sequencing across projects. Consumes CutPlans produced by Drafter's optimisation. | Read-only procurement ETA for in-stock validation. |
| **Procurement** | Per-project material dashboard (independent window, two-screen-friendly) | Batches, supplier comms (email), allocation of batches to item hardware lines, stock ETAs. | Read-only Drafter hardware lists. |

**Key invariant:** Drafter is the authoritative data entry point for items,
cutlists, and hardware. Every other role is either upstream (defining what to
build) or downstream (consuming or correcting).

## 3. Core JTBD

Three user jobs the product must win on — if any of these fail, the product
fails regardless of feature count.

1. **"Keep every project's information accurate and in-sync across six
   roles."** Single source of truth, live updates, no re-entry.
2. **"Let a Drafter produce a complete, printable set of item documents
   (Cutlist + Hardware List) from a CV export in minutes, not hours."** CV
   import + template-based PDF output.
3. **"Let anyone answer 'is this item blocked on a material?' without opening
   a second window."** BOM + procurement-batch allocation visible per item.

## 4. Module Breakdown (three products, one database)

### 4.1 Project Information Management (v1)

Covers: project CRUD, item CRUD, cutlist + hardware list creation/editing,
project-level hardware catalog, stage tracking (REQ → INST), status column,
status symbols, filters, role-based entry points.

**Surfaces:**
- CEO Dashboard (read-heavy KPIs, weekly report)
- PM Project Workbench (= evolved `tracking_dashboard.html`)
- Drafter Item Editor (item-centric, 3-list tabs)
- Procurement (independent window, material × batch × allocation)

**Details:** see `trackingv2.md`.

### 4.2 Shop Floor Ops (v2)

Covers: Foreman's worker assignment, today view (dual-surface: shop-floor
display + office PC), time logging, efficiency analytics, quality monitoring.
Data flows: Foreman logs → PM dashboard aggregates → CEO report summarises.

**Surfaces:**
- Shop-floor display (read + mark-done, no edit, auto-login)
- Foreman Office PC (full assignment + edit + history)
- PM "Labour & Progress" report panel (read-only)

**v1 hooks:** items already carry `assembler` / `lister` fields and stage
dates; the Shop Floor app writes back to these.

### 4.3 Cabinet Vision Integration Layer (v2)

Covers: Material Catalog (six tables — see §5), CV CSV import into an item's
Module/Part structure, Drafter's optimisation workflow, CutPlan output →
Machine team's Cut Schedule.

**Surfaces:**
- Drafter's CV Import widget (inside Item Editor)
- Drafter's Project Optimisation Workbench (project-level, one per project)
- Machine team's Cut Schedule (day-level, cross-project)

**v1 hooks:** Material Catalog tables exist in the v1 schema so Drafter
hardware lists can reference them immediately. Item/Module/Part hierarchy is
present even if only Item is edited in v1.

## 5. Data Model (v1 minimum)

### 5.1 Core hierarchy

```
Project
 └── Item                   (≈ one Cutlist #, one CV PDF)
      ├── Module            (MOD 1..N, from CV; data-model only in v1)
      │    └── Part         (qty, len, wid, material_id, edge, colour, comment)
      ├── HardwareLine      (qty, material_id, notes)  — picks from project hardware catalog
      └── Stage[10]         (REQ / SM / LISTED / DOWN / CNC / EDGED / PAINTED / MADE / DEL / INST)
                            each with due_date, done_date
```

### 5.2 Material Catalog — SIX tables, not one

Materials have fundamentally different lifecycles; don't unify them.

| Table | Examples | Coding | Procurement mode |
|---|---|---|---|
| `board_materials` | `18-PB`, `32-MDF`, `16-BLACK`, `19-A/WALNUT/BAM X` | Company-internal codes | Sheet stock, cut on demand |
| `hardware_materials` | Hinges, runners, handles, brackets | Supplier SKU (`700.0KC2.054.00`) | Per-piece ordering |
| `custom_made` | Bespoke items commissioned from external fabricators | Internal ref + vendor quote | One-off PO per item |
| `benchtop_materials` | Stone slabs, solid-surface sheets | Slab ID / lot number | Per-slab, sometimes per-cut |
| `appliances` | Integrated ovens, fridges, dishwashers | Manufacturer model number | Per-unit, long lead-time |
| `equipment_hire` | Rented tools/machinery used on a project | Hire contract ref | Time-based billing |

All six tables share a common abstract interface:
`(id, type, description, supplier, cost_unit, lead_time_days, notes)` —
but keep them as separate tables so schema evolution doesn't thrash.

### 5.3 Project Hardware Catalog — a mutable link layer

Drafters and PMs build up a **project-scoped approved materials list** during
a project, drawing from (and sometimes extending) the global catalogs.

```
ProjectHardwareCatalog (link table)
  ├── project_id
  ├── material_type   (which of the 6 catalogs)
  ├── material_id
  ├── added_by
  └── added_at
```

Item hardware lines reference a material *via* this project-scoped catalog —
this is what lets Procurement see "for Project X, the committed material
universe is these 42 SKUs," and lets the Drafter extend it on demand.

### 5.4 Procurement ↔ Tracking join

```
ProcurementBatch
  ├── material_type, material_id   → Material Catalog row
  ├── supplier, po_ref
  ├── ordered_date, eta_date, received_date
  └── Allocations (many)
       ├── item_hardware_line_id   → specific item consuming this batch
       └── qty_allocated
```

The query "is this item blocked on a material?" is a join from
`items → hardware_lines → allocations → procurement_batch.eta`. No second
window required.

### 5.5 CV Integration (v2, but schema-ready in v1)

```
CutPlan                  (one per optimisation run, project-scoped)
  └── CutSheet           (one per physical board being cut)
       └── PartSlot      (position + sequence on that sheet)
            └── part_id  → specific Item.Module.Part

CutSchedule              (Machine team's daily plan, separate from CutPlan)
  └── (date, cut_plan_id, priority, assigned_to)
```

**CutPlan ≠ CutSchedule.** Optimisation tells you *how* to cut; Machine team
decides *when* based on PM priorities. Two entities, one pipeline.

### 5.6 Terminology pins (avoid FileMaker-era ambiguity)

- **Stage** = area/block within the building being fitted out
  (e.g. `Joinery Lab`, `PC2`, `Block B`). *Site location*, not production line.
- **Zone** = numeric sub-division of Stage (e.g. `03`, `04`).
- **Status** = current record state for process/admin
  (`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD`).
- **Status Symbol** = Drafter-only lightweight flag
  (`question / warning / ok / blocked`). UI only, not reporting.
- **Lifecycle Stage** = the 10 production milestones (`REQ` … `INST`). Never
  collide with *Stage* above — in code, use `lifecycle_stage` or the specific
  stage key (`stage_key = 'CNC'`).

## 6. v1 Scope vs Deferred

### In v1
- Project Information Management module (4.1), including:
  - Role-based landing page + per-role entry points (Drafter, PM, CEO)
  - `tracking_dashboard.html` evolved into PM Project Workbench
  - Drafter Item Editor (new — see `trackingv2.md` §Drafter Editor)
  - Procurement module (independent window) — wire to schema only; UI minimal
- Full schema including all six Material Catalog tables, CutPlan/CutSchedule,
  ProjectHardwareCatalog, Module/Part hierarchy (populated by CV import in
  v2; manually editable in v1)
- CV CSV import (one-shot, manual trigger inside Item Editor)
- PDF generation for Cutlist + Hardware List from data (replaces FileMaker PDFs)
- Authentication + role-based permissions

### Deferred to v2
- Shop Floor Ops module (Foreman's workflow, workshop displays)
- Machine team's Cut Schedule UI (schema exists; UI later)
- CV push-back (write to CV) — CV is closed-system, not attempted
- Real-time notifications across roles (Cut Schedule changes → PM/Drafter/
  Foreman/Procurement). v1 is polling/refresh; v2 introduces pub/sub.
- Supplier email integration in Procurement
- Efficiency analytics + weekly auto-reports (schema present, reports later)

### Explicitly out of scope
- **Per-part painting tracking** — remains paper-based (current practice
  confirmed). System tracks `PAINTED` at item level only.
- **Pushing back into Cabinet Vision** — CV is closed.
- **Mobile-first layouts** — desktop browser targets only. Shop-floor tablet
  is a fixed-width display, not "responsive" in the mobile sense.

## 7. Resolved Decisions

1. **CV import gaps.** Known missing fields from CV export: **edging
   specification** and **paint instruction** (double-side / single-side /
   edge-only). Drafter fills these in manually post-import. v2 automation
   target: add these as first-class fields in the CV-import mapping step so
   they're explicitly prompted rather than silently missing.
2. **Project Hardware Catalog governance.** **Log-only, no approval step.**
   Every add/remove writes an audit row (`added_by`, `added_at`, action).
   Free-for-all write, full traceability via log.
3. **Cross-project PM access.** **Read-only by default** when a PM views a
   project they are not assigned to. Write access requires explicit grant
   (e.g. PM covering a colleague) — grant mechanism TBD in implementation.
4. **Equipment Hire billing.** **One contract = one project.** Data model:
   `equipment_hire.project_id` is a single FK, no allocation table needed.
   Simplifies schema and billing attribution.

## 8. Product Identity & Branding

- **Product name:** **JoineryFlow** (wordmark: "Joinery" in ink + "Flow" in accent).
  Logomark: filled square, ink background, `◴` glyph in accent.
- **Workspace model:** single-tenant workspaces (reference fixture:
  "Hartwood Joinery Co.", Studio plan, ~12 seats). Workspace slug is used at
  login (e.g. `hartwood-joinery`).
- **Tagline:** "Every joint, every delivery, every drawing — in one place."
- **Login landing stats** (shown on marketing/brand panel of the login screen):
  live projects, parts tracked, suppliers — pulled from workspace-level
  aggregates.

## 9. Top-Level IA (6 Tabs)

Hi-fi canonicalises the top nav to **six tabs, in order**:

1. **Dashboard** — role-aware home (see §10)
2. **Tracking** — part-level status across all rooms of the active project
3. **List** — *subtabs:* Cutlist (default) · Hardware Portal
4. **Orderbook** — *subtabs:* Open (default) · In transit · Delivered · Returns · RTO · Suppliers
5. **Shop Dwgs** — *subtabs:* Current (default) · In review · Archive · Templates
6. **iSample** — *subtabs:* Board (default) · Approval ledger · Clients · Suppliers · Archive

**Global chrome** (`HAppChrome` in `wireframes-hifi.jsx`):

- Top bar (48px): logomark + wordmark · tab strip · `Search · ⌘K` pill ·
  bell · avatar.
- Optional subtab strip immediately under the top bar, right-aligned
  `chromeExtra` slot for per-surface primary actions.
- Fixed left sidebar (220px): "Projects" eyebrow + "+" · filter pill ·
  scrollable project list with 3px accent rail on active row · mono `#id`
  under each name · user footer (avatar · name · title · settings cog).
- Body area (flex-1, `--h-bg`), internal scroll only.

**Tab-taxonomy reconciliation note.** The current
`tracking_dashboard.html` prototype ships **7 tabs** (Cutlist + iVariations
separate, Hardware elsewhere). The target v1 taxonomy follows hi-fi:
Cutlist + Hardware collapse into **List** with two subtabs. Migrate to the
6-tab layout for any new work on the PM Project Workbench.

## 10. Surface Catalog (hi-fi → v1 build targets)

Each surface below is a one-to-one build target for v1. Visual source is
`wireframes-hifi.jsx` primitives + the named hi-fi artboard.

### 10.1 Auth & Admin

| Surface | Source | Purpose |
|---|---|---|
| **Login** | `HiLogin` (`hi-login-it.jsx`) | Split layout — ink-dark brand panel (left) with tagline + live stats, 420px form panel (right) with email / password / workspace selector + SSO. |
| **IT Management** | `HiITManagement` (`hi-login-it.jsx`) | Settings-style chrome (`Workspace / IT Management` breadcrumb, "Admin mode" pill). Subtabs: **Users · Roles & Permissions · Invitations · Integrations · Audit Log · Billing**. Aside shows workspace card + quick stats. Main: users table (checkbox · avatar · title · role pill · status dot · last active · overflow) + quick-view role/permission matrix + recent activity feed. |

### 10.2 Dashboard — five directions, A is the default

Implement **A** in v1. B–E are deferred options retained as design
references.

| Dir | Source | Layout |
|---|---|---|
| **A · Command deck** *(default)* | `HiDashA` | Header greeting · 4 metric cards (Open parts · Orders in transit · Samples awaiting client · Hours logged today) · 2-col grid: **My day** checklist (left, 1.35fr) + **Deliveries today** card (right, 1fr) · **Team** unified card: you-row (accentSoft), 7-tile who's-in strip, nested "Recent activity" feed. |
| B · Activity stream | `HiDashB` | Filter chips + grouped-by-day activity list · right rail with Pins + Upcoming deliveries. |
| C · My-day Kanban | `HiDashC` | 5 columns (Backlog / Today / In progress / Waiting / Done) with drag affordances. |
| D · Week timeline | `HiDashD` | 10-day Gantt over all cutlists for one project, bars coloured by stage (Draft / Review / Cut / QC / Pack), dashed "today" line. |
| E · BrB staff board | `HiDashE` | Who's-in summary cards + staff cards grid + shop-floor live stations strip. |

**Status-light legend** (consistent across Dashboard + IT + Shop Floor):
In = good · On site = info · Shop = accent · WFH = warn · Off = ink3.

### 10.3 Tracking

Source: `HiTracking` (`hi-tracking-list.jsx`).

- Header: `Tracking · <Project>` + `237 parts, 14 statuses tracked`.
- Right actions: Export · Print manifest · **Add part** (accent).
- **Status tally pill row** — one pill per status in taxonomy, each with a
  colour dot and mono count; `All` pill is ink-filled. Clicking a pill
  filters.
- Table columns: `Part # (mono) · Description · Location · Type · Status ·
  Note · Assignee avatar`. Selected row highlighted in `accentSoft`.
- Quick-filters: Room · Type · Assignee · Search.
- Right **part drawer** (320px, collapsible): status pill + part# + title ·
  Specs grid · coloured note block (`warnSoft` + `warn` left rule) · Set
  status / Reply buttons · History timeline (status pill per event).

### 10.4 List

Two subtabs share chrome. Shared `chromeExtra`: **Import CV**, **Add part**
(Cutlist); **Kit sheet**, **Send to shop** (Hardware Portal).

#### 10.4.1 Cutlist (default)

Source: `HiListCutlist`.

- Header: `Cutlist · <Project>` · `Rev C` pill · History · Export.
- **Room tree sidebar** (220px): `Level 3` eyebrow + room rows (chevron +
  name + mono part count). Active room in `accentSoft` with 2px accent left
  border. "Common" sub-group underneath. Footer: `Import from CV…` accent
  link.
- **Parts table** columns: `Part (mono) · Description · W × D × T (mono) ·
  Substrate · Face · Edge · Qty (mono bold) · Status`. Row backgrounds
  encode recent change (`warnSoft/66` for changed-in-rev, `infoSoft/33` for
  new).
- **CV import banner** — bottom of table, `accentSoft` background +
  upload icon + message ("review N unmatched materials from …csv") +
  Dismiss / **Open review** (accent).

#### 10.4.2 Hardware Portal

Source: `HiListHardware`.

- Dual-pane: **Pantry** (left, 1.2fr) · **Cart** (right, 420px).
- Pantry grouped by category (Hinges / Handles / Runners / Fasteners). Row:
  `Name · SKU (mono) · Qty-in-stock (warn if < 100) · Supplier · Pull (btn)`.
- Cart grouped **by supplier catalogue** (Blum / Hafele / Ovvo). Group
  header: name · line-count · mono subtotal. Line row: name + SKU·room
  caption + qty stepper + line subtotal.
- Cart footer (surfaceAlt): Subtotal · Shop labour est. · Total with rule ·
  Save draft + **Send to shop →** (accent).

### 10.5 Orderbook

Source: `HiOrderbookOpen` (`hi-order-dwg-sample.jsx`), subtab = Open.

- Header: `18 open POs · $14,820 outstanding · 2 overdue`.
- Project-filter pill strip: `All projects` (ink primary) + per-project
  count pills. Right: `Overdue only`, `Kanban` view toggle.
- **Grouped-by-supplier table**: supplier header (letter tile + name + POs
  count pill + "Overdue: N" or "Next: …" caption + mono subtotal). Body
  columns: `PO# (mono) · Project · Description · Ordered · ETA · Status ·
  Total · ⋯`. Overdue ETA rendered in bad.

### 10.6 Shop Drawings

Source: `HiShopDrawings`, subtab = Current.

- Header: `22 drawings across 7 rooms · 5 awaiting review`. Right: Grid/List.
- Filter strip: search · Room · Status · Reviewer.
- **3-col thumbnail grid.** Each card:
  - 16:10 SVG blueprint placeholder with grid pattern + title rule + dim
    callout (deterministic from seed so thumbs stay stable across renders).
  - Status pill (top-left) + version chip (`v4`, mono, top-right, surface).
  - Footer: mono drawing id + title, room caption, reviewer avatar, mono date.

### 10.7 iSample

Source: `HiSamplebook`, subtab = Board.

- Header: `28 samples across 5 projects · 6 awaiting client · 2 rejected`.
- Filter chips: All · Awaiting client (warn count) · Approved (good count) ·
  Rejected (bad count) · search.
- **5-col sample-wall grid.** Each card:
  - Square swatch filled with sample colour, subtle 135° repeating-linear
    sheen overlay, status pill top-left, mono sample-id chip top-right on
    translucent surface.
  - Footer: title · project·room caption · reviewer avatar + decision
    caption.

## 11. Role & Permission Model (auth layer)

Operational JTBD taxonomy (§2) has **six roles**. The technical auth/RBAC
layer is coarser — mapping established by `HiITManagement`:

| Auth role | Can |
|---|---|
| **Admin** | Everything: create projects, edit, order, approve, manage users, view audit. |
| **Manager** | Create projects, edit cutlist/drawings, place orders, approve samples, view activity. No user management. |
| **Editor** | Edit cutlist/drawings, view activity. Cannot create projects, order, or approve. |
| **Viewer** | Read-only across the workspace; view activity log. |

**JTBD-role → Auth-role mapping** (v1 default; workspace admins may
override per user):

| JTBD role (§2) | Default auth role |
|---|---|
| CEO | Admin |
| PM | Manager |
| Drafter | Editor |
| Foreman | Editor (upgraded per-workspace if they run purchasing) |
| Machine team | Editor |
| Procurement | Manager (needs ordering + approval rights) |

**User states:** `Active · Invited · Suspended` — rendered as coloured dot
+ label, not a status pill.

**IT Management subtabs** (admin-only):
`Users · Roles & Permissions · Invitations · Integrations · Audit Log ·
Billing`. Audit log entries are text rows
("Bill Ma promoted Rin Park to Editor · 2m ago").

## 12. Design System (binding spec)

### 12.1 Tokens (from `H` palette in `wireframes-hifi.jsx`)

```
bg          #fbfaf7       page
surface     #ffffff       card
surfaceAlt  #f4f2ed       group header, subtle fills
surfaceDeep #ece9e0       deeper surface
line        #e4e0d8       borders
line2       #d0ccc2       strong borders (buttons)
ink         #1b1a17       primary text
ink2        #5a574f       secondary text
ink3        #8f8b80       tertiary text
ink4        #b5b1a6       quaternary text / disabled
accent      #c96442       primary accent (terracotta)
accentDeep  #a84f31       accent hover
accentSoft  #f3e0d6       highlighted row / banner bg
good        #3f7d48       (soft #e2efdf)
warn        #c48a2e       (soft #f4e7cf)
bad         #b4443d       (soft #f2dcd9)
info        #3d6b8a       (soft #dce6ed)
```

**Typography.** Inter (400/500/600/700) for UI · JetBrains Mono
(400/500/600) for part numbers, PO numbers, ETAs, money. Root
`font-feature-settings: "cv11", "ss01"`; mono adds `"tnum"`.

### 12.2 Primitives

All primitive classes are defined once in `wireframes-hifi.jsx` and must
be reused verbatim:

- `.h-btn` (base, 5/10px, 12/500, 5px radius, line2 border)
- `.h-btn-primary` (ink fill), `.h-btn-accent` (accent fill),
  `.h-btn-ghost` (transparent)
- `.h-pill` (10px radius, 11/500, line border, surfaceAlt)
- `.h-eyebrow` (10/600, uppercase, 0.08em letter-spacing, ink3)
- `.h-card` (surface, 1px line, 8px radius)
- `.h-input` (1px line, 12/inherit, focus → accent)
- `.h-subtab` (6/14, 12/500), `.h-subtab-active` (ink + 2px ink underline,
  600 weight)
- `.h-row-hover` (surfaceAlt on hover)
- `.h-mono` (JetBrains Mono + tnum)
- `HAvatar(label, size, color)` — circular initials, 0.38× font size
- `HStatus(s)` — coloured pill, uses the canonical status map below
- `HIcon(d, size, stroke)` + `Icons` dictionary (search, plus, bell, chev,
  chevR, filter, clock, box, cart, print, user, settings, upload, download,
  grid, list, eye, edit, x, menu, lock, key, shield, activity, project,
  logout, arrowU, arrowD, check, tag, users, refresh, import, room, dollar,
  history)

### 12.3 Status taxonomy (canonical across modules)

| Colour | States |
|---|---|
| good | `CLEAR`, `APPROVED`, `ARRIVED` |
| accent | `LIVE`, `RTO`, `NEXT` |
| warn | `HOLD`, `NOTE!` |
| bad | `VOID`, `REJECTED`, `OVERDUE` |
| info | `SUBMITTED`, `ORDERED` |
| neutral (ink2/surfaceAlt) | `TBC` |

Gantt bars on the Week Timeline dashboard use a parallel stage palette:
Draft = slate (`#94a3b8`) · Review = warn · Cut = accent · QC = info ·
Pack = good.

### 12.4 Data fixtures to reuse for prototypes

Keep these string sets stable across mocks so screens align:

- Projects: `Alfred Level 3 Fitout #2273`, `Monash Uni FFT · Caulfield
  #2351`, `Monash Uni FFT · Clayton #2350`, `VSBA Mickleham Sec. #2347`,
  `The Trentham #2289`, `7SS Flinders West #2255`, `Riverside Richmond
  #2232`.
- Staff: Bill Ma (BM/accent, Estimator/Admin), Jules Roh (JR/info, PM),
  Rin Park (RP/good, Drafter/Editor), Sam Oduya (SO/#7a5193, Shop Lead),
  Mina Klee (MK/bad, Purchasing), Theo Akkad (TA/#6f7a51, Carpenter),
  Priya Shah (PS/warn, Designer), Dan Kowalski (DK/ink3, Site Supervisor).
- Suppliers: Blum · Hafele · Briggs Veneer · Polytec · Laminex · Ovvo ·
  Joseph Giles.

## 13. Reference Files

- `tracking.md` — original (superseded) plan, retained for context.
- `trackingv2.md` — detailed build plan for module 4.1 (Project Information
  Management).
- `tracking_schema.sql` — current v1 schema; will need the Material Catalog
  + Module/Part + ProjectHardwareCatalog additions described in §5.
- `procurement_orderbook_dashboard.html` — style / token reference.
- `procurement_api.py` / `procurement_schema.sql` — existing procurement
  backend; evolves to match §5.4.
- `tracking_dashboard.html` — current prototype; becomes the PM Project
  Workbench surface in v1.
- `filemaker.md` — FileMaker source-of-truth for field names + legacy UI
  conventions.
- CV export sample + Hardware List sample PDFs (referenced during this
  design work) — should live under a `samples/` folder for future reference.

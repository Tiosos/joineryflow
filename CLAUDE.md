# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Nature

This is a **design + prototype repo** for **JoineryFlow**, a web replacement for a FileMaker-based joinery production system. It contains:

- Hi-fi visual specs as standalone **React JSX files** (`hi-*.jsx`, `wireframes-hifi.jsx`) — design artifacts, not a built application. No `package.json`, no bundler config, no build step currently wired up.
- Self-contained **HTML prototypes** (`tracking_dashboard.html`, `procurement_orderbook_dashboard.html`, `drafter_item_editor.html`, `home.html`, `Joinery Workflow Hi-fi.html`) that render via raw CDN React/Tailwind — open directly in a browser.
- A **FastAPI + SQLAlchemy (MySQL)** backend for the procurement module (`procurement_api.py`).
- **MySQL schemas** (`procurement_schema.sql`, `trackingv2_schema.sql`).
- Product and build spec documents (`product_spec.md`, `trackingv2.md`).

There is no root package manifest, no test suite, no CI, and no git repo initialized here. Treat edits as design-doc / prototype iteration unless the user explicitly asks to scaffold a real app.

## Running / Developing

### FastAPI backend (`procurement_api.py`)

```
pip install fastapi uvicorn sqlalchemy pymysql cryptography pydantic[email] python-multipart
export DATABASE_URL="mysql+pymysql://user:password@localhost/procurement_db"
export UPLOAD_DIR=./uploads
export ALLOW_ORIGINS=http://localhost:3000,http://localhost:5173
uvicorn procurement_api:app --reload
```

Schema is loaded from `procurement_schema.sql` / `trackingv2_schema.sql` directly into MySQL. The API uses raw `text()` queries via SQLAlchemy, not ORM models.

### HTML prototypes

Open the `.html` files directly in a browser. They pull React + Tailwind from CDNs and include their own mock data.

### JSX hi-fi files

`wireframes-hifi.jsx`, `hi-dashboard.jsx`, `hi-login-it.jsx`, `hi-order-dwg-sample.jsx`, `hi-tracking-list.jsx` are React component source shown inside the `Joinery Workflow Hi-fi.html` canvas. When modifying, preserve the `H` palette object and primitive class names (`.h-btn`, `.h-pill`, `.h-card`, `.h-eyebrow`, `.h-subtab`, `.h-mono`, `HAvatar`, `HStatus`, `HIcon`, `Icons`) — other surfaces import them by convention.

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

**Role model.** Six operational roles (CEO, PM, Drafter, Foreman, Machine, Procurement) map onto four auth roles (Admin, Manager, Editor, Viewer) — see `product_spec.md` §11. Drafter is the authoritative data-entry point; every other role is upstream or downstream.

**Procurement backend** (`procurement_api.py`) aligns 1:1 with FileMaker Orderbook layout and is the template for how other modules will be wired to MySQL. It uses raw SQL via `sqlalchemy.text()` + Pydantic v2 schemas; no ORM models. Uploads go to `UPLOAD_DIR` on disk.

## Design system (binding)

Tokens, typography, status colours, and primitive class names are defined **once** in `wireframes-hifi.jsx` (the `H` palette + primitive `<style>` block) and reused everywhere. When editing any surface:

- Do not invent new colors — use `H.bg / surface / surfaceAlt / ink / ink2..4 / accent / accentSoft / good / warn / bad / info`.
- Typography: Inter for UI, JetBrains Mono (`.h-mono`, with `tnum`) for part #, PO #, ETAs, money.
- Status taxonomy is canonical across modules — see `product_spec.md` §12.3 before adding a new state.
- IA is fixed to **6 top tabs**: `Dashboard · Tracking · List · Orderbook · Shop Dwgs · iSample`. The older 7-tab layout in `tracking_dashboard.html` is legacy; new work uses 6 tabs with Cutlist + Hardware as subtabs under **List**.

## Surface ↔ source file map

When asked to change a screen, identify the source first (`trackingv2.md` §1.5.1 has the full binding):

| Surface | Source component | File |
|---|---|---|
| Login / IT Management | `HiLogin`, `HiITManagement` | `hi-login-it.jsx` |
| Dashboard (Command deck = v1 default) | `HiDashA` (B–E deferred) | `hi-dashboard.jsx` |
| Tracking grid | `HiTracking` | `hi-tracking-list.jsx` |
| List — Cutlist / Hardware Portal | `HiListCutlist`, `HiListHardware` | `hi-tracking-list.jsx` |
| Orderbook | `HiOrderbookOpen` | `hi-order-dwg-sample.jsx` |
| Shop Drawings | `HiShopDrawings` | `hi-order-dwg-sample.jsx` |
| iSample | `HiSamplebook` | `hi-order-dwg-sample.jsx` |
| Chrome + primitives + tokens | `HAppChrome`, `H`, `Icons` | `wireframes-hifi.jsx` |

## Reference docs (read before large changes)

- `product_spec.md` — product overview, roles, data model invariants, design tokens, IA. Authoritative.
- `trackingv2.md` — detailed v1 build plan for Project Information Management. Authoritative for module 1.

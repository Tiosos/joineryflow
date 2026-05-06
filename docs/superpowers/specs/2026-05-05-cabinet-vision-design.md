# JoineryFlow Cabinet Vision Integration Layer — Design Spec

**Date:** 2026-05-05
**Sub-project:** #7 (Cabinet Vision Integration Layer v2 — Material catalog enrichment + CV CSV import + CutPlan / CutSchedule UI)
**Sub-project slicing:** Ships in three independently-mergeable slices, in order:
- **#7a — Catalog enrichment + Mappings UI** (migration 0017, the `catalog` RBAC module, `/catalog` page incl. CV Mappings subtab; the catalog write-side that everything else depends on)
- **#7b — CV Import wizard** (migration 0018, the `cv_import_run` register, the `/items/{id}?tab=cutlist&import=cv` 3-phase wizard; depends on #7a's catalog + mapping CRUD)
- **#7c — CutPlan / CutSchedule + Board tab** (migration 0019, the `cut_floor` RBAC module, `/cut-floor` page + Drafter Board tab; independent of #7a/#7b — could ship in parallel but sequenced after for review bandwidth)
**Sequencing:** Cabinet Vision ships **before** Shop Floor (sub-project #8). Shop Floor's spec lives at `docs/superpowers/specs/2026-05-05-shop-floor-design.md` and assumes migrations 0017–0019 are already applied.
**Branch base:** `feat/foundation` (HEAD `2f72c89`; latest migration on disk is 0016).
**Prior context:**
- `docs/superpowers/specs/2026-04-22-foundation-design.md`
- `docs/superpowers/specs/2026-04-25-pm-workbench-design.md`
- `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md`
- `docs/superpowers/specs/2026-05-01-shop-drawings-design.md`
- `docs/superpowers/specs/2026-05-02-pdf-generation-design.md`
- `docs/superpowers/specs/2026-05-02-isample-design.md`
- `legacy/product_spec.md` §4.3, §5.2, §5.5, §5.6
- `legacy/trackingv2.md` §7
- `db/alembic/versions/0003_cut_schedule.py`
- `db/alembic/versions/0007_material_catalog_reconciliation.py`

---

## 0. Goal

Cabinet Vision is the closed CAD program every Drafter at Hartwood lives in. The current bridge between CV and JoineryFlow is a Drafter manually retyping the CV cutlist export into the part grid. This sub-project wires up the full **CV → JoineryFlow → Machine Floor** pipeline that the v1 schema was deliberately shaped for but never exercised:

1. **Enrich the six material catalog tables** with the missing fields needed to make CV codes resolvable (synonyms, default supplier, default lead time, cost). v1 left these "schema-ready" but sparsely populated; #7 ships the workspace-scoped CRUD UI plus a bulk CSV importer so a workspace admin can land their full catalog in an afternoon.
2. **Ship CSV import** inside the Drafter Item Editor's Cutlist tab — a two-phase preview/commit flow that parses a CV-style CSV, resolves every material code through `cv_material_mapping` + per-table `synonyms`, surfaces unknown codes as a resolution UI, and on commit writes Modules + Parts in a single transaction.
3. **Ship the Drafter Board tab** — per-item visual rendering of the project `cut_plan` showing each `cut_sheet` with `part_slot` rectangles for parts that belong to this item.
4. **Ship the Machine team's Cut Schedule view** — a new top-level `/cut-floor` page (drag-reorder daily list of `cut_schedule` rows with status pills planned → running → done | cancelled).

The optimiser itself (real bin-packing nesting) stays out of scope; v1 of #7 lets a Drafter manually build a `cut_plan` from existing parts. The shape of the pipeline is what matters; a real nesting engine slots in behind the same API in a future sub-project.

---

## 1. Scope

### In scope

1. **`cv_import_run` register** — workspace-isolated via `items → projects.workspace_id`. Per-row record of every preview/commit attempt, with status (`preview` | `committed` | `failed`), source filename, sha256 of the uploaded blob, row count, started/completed timestamps, and a `jsonb` error log capturing per-row issues.
2. **`cv_material_mapping` register** — workspace-scoped translation table from a freeform CV code (`18-PB`, `700.0KC2.054.00`) to one of the six target catalog tables + a row in that table. Drafter-curated; entries grow naturally as imports resolve unknown codes. UNIQUE on `(workspace_id, cv_code)`.
3. **Catalog enrichment** — add a `synonyms text[]` column to each of the six catalog tables (`board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`) for fuzzy matching during import. CRUD routes per table with bulk-create + per-row patch + archive (soft-delete via `archived_at`). `/catalog` page with 6-tab strip, one tab per material type, each tab is an editable grid plus "Bulk import CSV" button.
4. **Cutlist tab — Import from CV wizard.**
   - **Phase A (preview):** Drafter pastes CSV or picks a file. Backend parses with strict header detection, normalises columns, and returns a structured `CvPreview` payload listing every row mapped to one of: `mapped` (CV code resolved through `cv_material_mapping`), `synonym_match` (fuzzy hit on a catalog row's `synonyms[]`), `unknown` (no resolution), or `invalid` (bad numeric data, missing required fields). The `cv_import_run` row is written with `status='preview'`.
   - **Phase B (resolve unknown):** UI lists every `unknown` row with three options per row — pick existing catalog material (search across all 6 tables), create new catalog material inline, or skip the row. Each pick of "existing" auto-writes a `cv_material_mapping` row so future imports of the same CV code are instant.
   - **Phase C (commit):** Drafter clicks "Import {n} parts in {m} modules". Backend opens a single transaction, writes Modules and Parts under the item, updates `cv_material_mapping` for resolved codes, sets `cv_import_run.status='committed'`, and writes audit + item edit log rows.
5. **Board tab — per-item CutPlan render.** New tab on the Drafter Item Editor (board slots in after Hardware, before Log). Reads the project's most-recent `cut_plan` and renders each `cut_sheet` as a scaled SVG rectangle with each `part_slot` drawn at its `(x, y, w, h)` and labelled. Slots whose `part_id` matches a part of *this* item are highlighted; foreign slots are dimmed but shown for context. Read-only in v1.
6. **CutPlan API** — manual create (`POST /projects/{id}/cut-plans` with a `sheets[]` payload), read (list + by-id), and read-by-item (the Board tab fetches `GET /items/{iid}/cut-plan`). Delete is hard delete in v1.
7. **CutSchedule API + `/cut-floor` page** — Machine team's daily list. `POST /cut-schedules` to add a plan to a date; `PATCH /cut-schedules/{id}` to update `priority`, `scheduled_for`, `status`, or `assigned_to`. Drag-reorder is `POST /cut-schedules/reorder` that takes an ordered `id[]` and assigns dense `priority` values. Status transitions enforced: `planned → running → done`; `planned → cancelled`; `running → cancelled`. Other transitions return 409.
8. **RBAC** — two new modules: `catalog` (catalog enrichment) and `cut_floor` (CV import + CutPlan + CutSchedule + Board tab + `/cut-floor`). `cv_material_mapping` writes go through `catalog`. Drafter is elevated to admin/manager parity on both modules.
9. **Audit hooks** on every mutation: `cv.import.{preview|commit|fail}`, `catalog.{table}.{create|update|archive}`, `catalog.csv_import`, `cv_material_mapping.{create|update|delete}`, `cut_plan.{create|delete}`, `cut_schedule.{create|reorder|status_change|cancel}`.
10. **Seed updates** — populate one Cabinet Vision-style import on ALF-001 item 1 (8–10 parts across 2 modules), enrich both seeded `board_materials` rows with `synonyms[]`, add 2 demo `cv_material_mapping` rows, write one demo `cut_plan` (1 sheet, 8 slots) on ALF-001 with two `cut_schedule` entries — one `planned` for tomorrow, one `running` for today.

### Out of scope (deferred)

- **Real bin-packing optimiser** — v1 ships manual CutPlan creation. The wire format is set; the engine is not.
- **Automatic re-sync from Cabinet Vision** — every CV import is manually triggered.
- **Push-back into Cabinet Vision** — CV is closed. JoineryFlow never writes back.
- **Three-way merge of imports** — re-importing onto an item with existing modules/parts is a 409 unless the Drafter passes `?mode=replace`.
- **CV API integration** — there is no CV server-side API to call.
- **Cut Schedule mobile UI** — desktop-first.
- **Per-table supplier enrichment beyond a single `default_supplier` text column** — richer per-table fields are a future enrichment pass.
- **Sheet stock inventory** — catalog data only; real workspace stock-on-hand belongs to Shop Floor.
- **Optimisation Drafter role enforcement** — any drafter+ can create CutPlans on any project they can read.

---

## 2. Architecture

### 2.1 Backend layout

Three new app modules. Follow the repo convention: SQLAlchemy Core `text()` queries, Pydantic v2, `require_permission` dependency, all mutations write `audit_log`, item-scoped mutations *also* write `item_edit_log` via the helper at `apps/api/app/edit_log.py`.

```
apps/api/app/cv/
  __init__.py
  routes.py            # CV import preview + commit + run history
  queries.py           # text() SQL — CV runs + mapping lookups + commit transaction
  parser.py            # CSV header normalisation + row -> typed dict
  resolver.py          # mapping + synonyms-fuzzy-match resolver
  schemas.py           # CvPreviewIn, CvPreviewOut, CvCommitIn, CvImportRunOut, CvMappingIn

apps/api/app/catalog/
  __init__.py
  routes.py            # 6 sub-routers (one per table) + bulk-csv-import + mapping CRUD
  queries.py           # text() SQL — per-table CRUD with audit
  schemas.py           # BoardMaterialOut, HardwareMaterialOut, ... CatalogBulkImportIn

apps/api/app/cut_floor/
  __init__.py
  routes.py            # cut_plan + cut_schedule routes
  queries.py           # text() SQL with audit
  schemas.py           # CutPlanIn, CutSheetIn, PartSlotIn, CutPlanOut, CutScheduleOut, ReorderIn
```

Wire all three routers into `apps/api/app/main.py` after the existing `parts_router` registration.

### 2.2 Web layout

```
apps/web/app/(app)/
  catalog/
    page.tsx                          # tabbed grid + bulk-import button
    _components/
      CatalogTabs.tsx                 # 7-tab strip (6 materials + mappings)
      CatalogGrid.tsx                 # editable grid (per-table)
      CatalogBulkImportDialog.tsx
      MappingPanel.tsx                # cv_material_mapping CRUD
  cut-floor/
    page.tsx                          # daily schedule with drag reorder
    _components/
      ScheduleList.tsx
      ScheduleRow.tsx                 # status pill + assigned-to + plan link
      AddPlanDialog.tsx
  items/[id]/_components/
    BoardTab.tsx                      # per-item CutPlan render (svg)
    CvImportDialog.tsx                # 3-phase wizard (preview -> resolve -> commit)
    UnknownCodeRow.tsx                # one row in resolve phase
```

`EditorTabs.tsx` extends `TABS` to include a `board` tab between hardware and log. The Cutlist tab gets a new "Import from CV" button in its toolbar that opens `CvImportDialog`.

### 2.3 Routing decisions

- New top-level page `/catalog` — admin/manager/drafter access; other roles 403 at `require_permission("catalog","read")`.
- New top-level page `/cut-floor` — admin/manager/drafter (full) and editor (Machine team — read+write+comment, no approve).
- Both new pages live behind the existing app shell but as `/catalog` and `/cut-floor` *do not* belong in the canonical 6-tab IA — they are reachable from the SideBar's secondary section.
- The Drafter Board tab is *inside* the item editor (not a top-level page).

### 2.4 File store reuse

The CV import uploaded CSV is **not** stored in `file_blob` — it is a transient artefact. Only the SHA256 + filename + row count are kept on `cv_import_run`. The CSV bytes are read into memory, parsed, and discarded.

The `/catalog` "Bulk import CSV" upload is similarly transient.

### 2.5 Workspace isolation

All registers gate via `projects.workspace_id` (or `workspace_id` directly for catalog tables, since 0007 added that column to all six). Pattern matches the post-`0014` workspace-isolation hardening.

---

## 3. Data Model

### 3.1 New tables

#### `cv_import_run`

```sql
CREATE TABLE cv_import_run (
  cv_import_run_id  bigserial    PRIMARY KEY,
  project_id        bigint       NOT NULL REFERENCES projects(project_id),
  item_id           bigint       NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  source_filename   varchar(255) NOT NULL,
  sha256            char(64)     NOT NULL,
  row_count         int          NOT NULL DEFAULT 0,
  status            text         NOT NULL CHECK (status IN ('preview','committed','failed')),
  started_at        timestamptz  NOT NULL DEFAULT now(),
  completed_at      timestamptz,
  error_log         jsonb        NOT NULL DEFAULT '[]'::jsonb,
  created_by        bigint       NOT NULL REFERENCES app_user(id)
);

CREATE INDEX idx_cv_import_run_item ON cv_import_run (item_id);
CREATE INDEX idx_cv_import_run_status ON cv_import_run (project_id, status);
```

#### `cv_material_mapping`

```sql
CREATE TABLE cv_material_mapping (
  cv_material_mapping_id bigserial    PRIMARY KEY,
  workspace_id           bigint       NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
  cv_code                varchar(255) NOT NULL,
  target_material_table  text         NOT NULL CHECK (target_material_table IN
    ('board_materials','hardware_materials','custom_made',
     'benchtop_materials','appliances','equipment_hire')),
  target_material_id     bigint       NOT NULL,
  notes                  text,
  created_by             bigint       NOT NULL REFERENCES app_user(id),
  created_at             timestamptz  NOT NULL DEFAULT now(),
  updated_at             timestamptz  NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, cv_code)
);

CREATE INDEX idx_cv_material_mapping_target ON cv_material_mapping (target_material_table, target_material_id);
```

There is **no FK on `target_material_id`** because it can point at six different tables; the application layer is responsible for writing a valid `(table, id)` pair. Catalog routes never hard-delete (only archive) so dangling references are not a concern.

### 3.2 Modifications to existing tables

#### `part_slot` — link to a real `part`

```sql
ALTER TABLE part_slot
  ADD COLUMN part_id bigint REFERENCES parts(part_id) ON DELETE SET NULL;

CREATE INDEX idx_part_slot_part ON part_slot (part_id);
```

Nullable, no backfill — v1 had no real cut plans.

#### `cut_schedule` — add `priority` + `assigned_to`

```sql
ALTER TABLE cut_schedule
  ADD COLUMN priority    int    NOT NULL DEFAULT 0,
  ADD COLUMN assigned_to bigint REFERENCES app_user(id) ON DELETE SET NULL,
  ADD COLUMN created_at  timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN created_by  bigint REFERENCES app_user(id),
  ADD COLUMN updated_at  timestamptz NOT NULL DEFAULT now();

CREATE INDEX idx_cut_schedule_date_priority ON cut_schedule (scheduled_for, priority);
```

`priority` is rewritten in dense `100, 200, 300, …` chunks on every reorder so we can insert between two rows by computing `(prev + next) / 2` without churning every row.

#### `cut_plan` — add `created_by` + `notes`

```sql
ALTER TABLE cut_plan
  ADD COLUMN created_by  bigint REFERENCES app_user(id),
  ADD COLUMN notes       text;
```

No `is_current` flag — Board tab queries `MAX(cut_plan_id) WHERE project_id = :pid`.

#### Six catalog tables — add `synonyms[]` + `default_supplier` + `default_lead_time_days` + `archived_at`

For each of the six catalog tables:

```sql
ALTER TABLE board_materials
  ADD COLUMN synonyms              text[]      NOT NULL DEFAULT '{}',
  ADD COLUMN default_supplier      varchar(128),
  ADD COLUMN default_lead_time_days int,
  ADD COLUMN archived_at           timestamptz,
  ADD COLUMN archived_by           bigint REFERENCES app_user(id);

CREATE INDEX idx_board_materials_synonyms ON board_materials USING gin (synonyms);
CREATE INDEX idx_board_materials_active   ON board_materials (workspace_id) WHERE archived_at IS NULL;
```

Repeat for `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`.

### 3.3 Catalog write-path peculiarities

Each catalog table has a legacy NOT NULL UNIQUE column from migration 0007 (`code` on `board_materials`, `internal_ref` on `custom_made`, `slab_id` on `benchtop_materials`, `model_number` on `appliances`, `contract_ref` on `equipment_hire`; `hardware_materials` natively has `sku`). Catalog CRUD routes mirror procurement-v1 catalog routes — they fill the legacy column from the `sku` field on insert when the caller doesn't provide it. `equipment_hire` continues to require a `project_id` FK on insert, so its catalog tab demands a project picker; the other five tabs do not.

### 3.4 Workspace isolation invariant

Catalog tables: `(workspace_id, sku)` UNIQUE constraint. `cv_material_mapping` is workspace-scoped. `cv_import_run` is item-scoped (workspace resolved through the item's project). `cut_plan` and `cut_schedule` are workspace-scoped through `cut_plan.workspace_id` (already on the table from migration 0003).

---

## 4. API surface

### 4.1 Catalog enrichment routes

For each of the six tables (sub-router pattern):

| Method | Path | Gate | Notes |
|---|---|---|---|
| `GET`    | `/catalog/board-materials?q=&supplier=&archived=false` | `("catalog","read")` | List with optional filters. |
| `GET`    | `/catalog/board-materials/{mid}` | `("catalog","read")` | Single row including `synonyms[]`. |
| `POST`   | `/catalog/board-materials` | `("catalog","write")` | Create. UNIQUE on `(workspace_id, sku)`. Audit: `catalog.board_materials.create`. |
| `PATCH`  | `/catalog/board-materials/{mid}` | `("catalog","write")` | Partial update. Per-field audit row. |
| `POST`   | `/catalog/board-materials/{mid}/archive` | `("catalog","write")` | Soft-delete. |
| `POST`   | `/catalog/board-materials/bulk` | `("catalog","write")` | Bulk-create CSV. Returns `{created: N, errors: [...]}`. Single transaction; all-or-nothing for v1. |

Repeat under `/catalog/{hardware-materials | custom-made | benchtop-materials | appliances | equipment-hire}`.

#### CV mapping CRUD

| Method | Path | Gate | Notes |
|---|---|---|---|
| `GET`    | `/catalog/cv-mappings?q=` | `("catalog","read")` | List. |
| `POST`   | `/catalog/cv-mappings` | `("catalog","write")` | Create. UNIQUE on `(workspace_id, cv_code)` returns 409. |
| `PATCH`  | `/catalog/cv-mappings/{mid}` | `("catalog","write")` | Repoint to a different `(table, id)`. |
| `DELETE` | `/catalog/cv-mappings/{mid}` | `("catalog","write")` | Hard delete. |

### 4.2 CV import routes

| Method | Path | Gate | Notes |
|---|---|---|---|
| `POST` | `/items/{iid}/cv-imports/preview` | `("cut_floor","write")` | Multipart form: `file` + optional `body` paste. Parses, resolves materials, writes `cv_import_run` with `status='preview'`. Audit: `cv.import.preview`. |
| `POST` | `/items/{iid}/cv-imports/{run_id}/commit` | `("cut_floor","write")` | Body: resolutions + `replace` flag. Single transaction creates modules + parts, updates `cv_material_mapping`, sets `cv_import_run.status='committed'`. |
| `GET`  | `/items/{iid}/cv-imports` | `("cut_floor","read")` | History. |
| `GET`  | `/cv-imports/{run_id}` | `("cut_floor","read")` | Single run with rehydrated preview. |

### 4.3 CutPlan routes

| Method | Path | Gate | Notes |
|---|---|---|---|
| `POST`   | `/projects/{pid}/cut-plans` | `("cut_floor","write")` | Body: `{name, notes, sheets: [{sheet_no, material_sku, slots: [...]}]}`. Single transaction. |
| `GET`    | `/projects/{pid}/cut-plans` | `("cut_floor","read")` | List, newest first. |
| `GET`    | `/cut-plans/{plan_id}` | `("cut_floor","read")` | Full plan. |
| `GET`    | `/items/{iid}/cut-plan` | `("cut_floor","read")` | Most-recent project plan filtered to sheets containing slots from this item; foreign slots flagged `is_foreign=true`. |
| `DELETE` | `/cut-plans/{plan_id}` | `("cut_floor","write")` | Hard delete (CASCADE cleans up sheets + slots). 409 if a `cut_schedule` references this plan. |

### 4.4 CutSchedule routes

| Method | Path | Gate | Notes |
|---|---|---|---|
| `GET`   | `/cut-schedules?date=YYYY-MM-DD` | `("cut_floor","read")` | List for a single day, ordered by `priority ASC`. |
| `GET`   | `/cut-schedules/{sid}` | `("cut_floor","read")` | One row with linked plan summary. |
| `POST`  | `/cut-schedules` | `("cut_floor","write")` | Body: `{cut_plan_id, scheduled_for, assigned_to?}`. Priority auto-assigned to `MAX(priority) + 100`. |
| `PATCH` | `/cut-schedules/{sid}` | `("cut_floor","write")` | Partial update. Status transitions enforced. 409 on illegal transition. |
| `POST`  | `/cut-schedules/reorder` | `("cut_floor","write")` | Body: `{scheduled_for, ordered_ids}`. Server rewrites priorities densely. |
| `DELETE`| `/cut-schedules/{sid}` | `("cut_floor","write")` | Soft-cancel (`status='cancelled'`). |

### 4.5 Web routes (Next.js)

- `/catalog?tab=board|hardware|custom|benchtop|appliances|equipment_hire&q=&archived=`
- `/catalog?tab=cv-mappings&q=`
- `/cut-floor?date=YYYY-MM-DD`
- Item editor `/items/{id}?tab=board`
- CV import dialog opens *inside* `/items/{id}?tab=cutlist&import=cv`

---

## 5. RBAC matrix delta

Two new modules slot into `apps/api/app/auth/permissions.py`. The matrix body gets:

```python
Module = Literal[
    "dashboard",
    "tracking",
    "list",
    "shop_dwgs",
    "isample",
    "orderbook",
    "catalog",          # added by sub-project #7a
    "cut_floor",        # added by sub-project #7c
    "it_management",
]
# Note: `shop_floor` will be appended by sub-project #8 (Shop Floor Ops) which
# ships *after* the three Cabinet Vision slices. Until then, the matrix has
# 9 modules.

# Per-row additions (other rows unchanged):

"editor": {
    m: {"read", "write", "comment"}
    for m in ("dashboard","tracking","list","shop_dwgs","isample","cut_floor")
} | {
    "orderbook": {"read","comment"},
    "catalog":   {"read","write","comment"},   # editor can propose catalog edits
    "it_management": set(),
}

"drafter": {
    "dashboard":     {"read"},
    "tracking":      {"read","write","approve","comment"},
    "list":          {"read","write","approve","comment"},
    "shop_dwgs":     {"read","write","approve","comment"},
    "isample":       {"read","write","approve","comment"},
    "orderbook":     {"read","write","approve","comment"},
    "catalog":       {"read","write","approve","comment"},
    "cut_floor":     {"read","write","approve","comment"},
    "it_management": set(),
}

"purchase_officer": {
    ...
    "catalog":     {"read","comment"},
    "cut_floor":   {"read"},
    ...
}
```

### 5.1 Why `editor` gets write on `catalog`

Foreman / Machine team often knows "this is the supplier code we actually use" before the Drafter does. Letting them propose catalog edits (no approve) keeps that knowledge from being bottlenecked behind a Drafter. Audit log captures every change.

### 5.2 Why `purchase_officer` gets `comment` on `catalog`

Procurement's job is sourcing materials; they need to read the catalog and leave a comment when a code's supplier is wrong. Write/approve still belongs to drafter+.

---

## 6. CSV Import workflow detail

### 6.1 Header normalisation

The parser at `apps/api/app/cv/parser.py` accepts a strict header regex per logical column:

| Logical column | Accepted header patterns (case-insensitive, whitespace stripped) |
|---|---|
| `module_no` | `MOD`, `Module`, `ModuleNo`, `Module #`, `Mod #` |
| `part_name` | `Part Name`, `PartName`, `Description`, `Item` |
| `qty` | `Qty`, `Quantity`, `#` |
| `len_mm` | `Length`, `Len`, `L`, `Length (mm)` |
| `wid_mm` | `Width`, `Wid`, `W`, `Width (mm)` |
| `thickness_mm` | `Thickness`, `Thk`, `T` (informational; not stored on `parts` v1) |
| `material_code` | `Material`, `Material Code`, `MaterialCode`, `Code`, `Sku` |
| `edge` | `Edge`, `Edging` |
| `colour` | `Colour`, `Color`, `Finish` |
| `notes` | `Notes`, `Note`, `Comment` |

Required logical columns: `module_no`, `part_name`, `qty`, `len_mm`, `wid_mm`, `material_code`. Missing required column → 422.

### 6.2 Resolver order

For each row's `material_code`:

1. **Mapping hit** — `cv_material_mapping WHERE workspace_id = :w AND cv_code = :code`. Resolution: `mapped`.
2. **Synonym hit** — for each of the six tables, `WHERE :code = ANY(synonyms)`. Exactly one hit across all six → `synonym_match`. Multiple → `unknown` with hint `multiple_synonym_matches`.
3. **Exact-sku hit** — match on `sku` column or legacy NOT NULL UNIQUE column. Resolution: `synonym_match`.
4. **Otherwise** — `unknown`. UI surfaces in Phase B.

### 6.3 Phase A response shape

```json
{
  "run_id": 42,
  "summary": {"row_count": 12, "mapped": 8, "synonym": 2, "unknown": 1, "invalid": 1},
  "modules": [
    {"module_no": 1, "parts": [
      {"row_index": 1, "part_name": "Side Panel L", "qty": 1, "len_mm": 720,
       "wid_mm": 580, "cv_code": "18-PB",
       "resolution": {"kind": "mapped",
                      "target_table": "board_materials",
                      "target_material_id": 7,
                      "target_description": "18mm Particleboard White"}}
    ]}
  ],
  "unknown_codes": [
    {"cv_code": "18-WAX", "occurrences": 2, "suggested_table": "board_materials"}
  ],
  "errors": [
    {"row_index": 12, "code": "INVALID_NUMERIC", "field": "len_mm", "value": "abc"}
  ]
}
```

### 6.4 Persistence of preview snapshot

The full `CvPreviewOut` payload is also stored on `cv_import_run.error_log` under the key `_preview_snapshot` so `GET /cv-imports/{run_id}` can rehydrate without re-parsing.

### 6.5 Phase B — resolve unknown

UI shows one row per `unknown_codes[]` with three actions:

- **Use existing** — typeahead across all six tables. On commit auto-writes `cv_material_mapping`.
- **Create new** — inline mini-form scoped to the suggested table. On commit creates the catalog row first, then writes the mapping, then uses it.
- **Skip** — drops the rows that reference this code.

### 6.6 Phase C — commit transaction

```sql
BEGIN;
  -- 1. (per "create_new") INSERT into target catalog table
  -- 2. (per "use_existing" missing mapping) INSERT cv_material_mapping
  -- 3. INSERT modules (one per distinct module_no)
  -- 4. INSERT parts for each non-skipped row
  -- 5. UPDATE cv_import_run SET status='committed', completed_at=now()
  -- 6. INSERT audit_log: cv.import.commit + per-part part.create
  -- 7. INSERT item_edit_log per module + per part
COMMIT;
```

Rollback on error → `cv_import_run.status='failed'`.

### 6.7 Re-import semantics

- Default: 409 if the item already has any modules or parts.
- `?mode=replace`: DELETE all modules (CASCADE wipes parts) before commit. Audit: `cv.import.replace_wipe`.
- `?mode=append` deferred to a future three-way merge UI.

### 6.8 Audit + item edit log

The commit transaction writes:
- One `audit_log` `cv.import.commit` with `payload = {run_id, modules_created, parts_created, mappings_created}`.
- One `audit_log` per created part (`part.create`).
- One `item_edit_log` per created module (`field='_create_module'`).
- One `item_edit_log` per created part (`field='_create_part'`).
- One `item_edit_log` summary `field='_cv_import'`, `new_value='{run_id} ({M} parts)'`.

---

## 7. UI surfaces

### 7.1 `/catalog` page

- Server component `fetchMe()` for role gating, then renders `CatalogTabs`.
- 7-tab strip: `Board · Hardware · Custom · Benchtop · Appliances · Equipment Hire · CV Mappings`.
- Each material tab: filter strip (search + supplier select + archived toggle) + sortable grid (SKU, Description, Default supplier, Lead time, Unit cost, Synonyms, Updated). Inline-edit pattern.
- Bulk-import dialog: paste CSV or pick a file, see 3-line header preview, click Import → server returns `{created, errors}`.
- CV Mappings subtab: simple register grid with Add / Repoint / Delete.

### 7.2 Drafter Editor — Cutlist tab Import dialog

`CvImportDialog.tsx` is a 3-phase wizard:

- **Phase A (Upload)**: textarea for paste + file picker. Submit → server preview.
- **Phase B (Resolve)**: summary chip + unknown-codes list with three-action inline UI.
- **Phase C (Commit)**: confirmation panel "Import 11 parts in 2 modules under Item ALF-001-ITEM-1?". Existing data warning if the item already has modules.

Closes on success and reloads the Cutlist grid via existing `fetch()` calls.

### 7.3 Drafter Editor — Board tab

- Header: "Project CutPlan — `{plan_name}` (created `{date}` by `{author}`)".
- For each `cut_sheet` containing slots from this item: SVG canvas (max 800px wide, scaled to sheet aspect ratio) with each `part_slot` as a `<rect>`. Foreign slots in `--h-line` at 30% opacity; this-item slots in `--h-accent` at 60% opacity. Tooltip on hover.
- Empty state: "No CutPlan yet for this project."
- Read-only in v1.

### 7.4 `/cut-floor` page

- Date picker (default today). Forward/back arrows.
- Sortable list of `cut_schedule` rows for the date, drag-to-reorder (HTML5 DnD; no library).
- Each row: status pill · plan name · supplier chip · assigned-to avatar · Start / Mark done / Cancel buttons.
- "Add to today" dialog with CutPlan picker + assigned-to picker.
- Reorder fires `POST /cut-schedules/reorder`.

---

## 8. Migrations needed

Three migrations, one per sub-project slice. Each ships independently with its own RBAC + UI.

- **`0017_catalog_enrichment.py`** (#7a) — `synonyms[]` + `default_supplier` + `default_lead_time_days` + `archived_at` + `archived_by` on all 6 catalog tables (board / hardware / custom / benchtop / appliances / equipment_hire). Plus the GIN indexes on `synonyms` and partial active-row indexes. Plus the `cv_material_mapping` table (the mapping register lives in #7a because the `/catalog` Mappings subtab needs it).
- **`0018_cv_import.py`** (#7b) — `cv_import_run` table + indexes. Depends on `cv_material_mapping` (already in 0017).
- **`0019_cut_floor.py`** (#7c) — `part_slot.part_id` FK, `cut_schedule.priority` + `assigned_to` + `created_at` + `created_by` + `updated_at`, `cut_plan.created_by` + `notes`. Plus `idx_cut_schedule_date_priority` and `idx_part_slot_part`.

Combined DDL (split per migration when implementing):

```python
"""(0017 catalog_enrichment): synonyms + default_supplier + lead_time + archive
on 6 catalog tables; cv_material_mapping table.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-05
"""
from alembic import op

# === Migration 0017 (#7a) ===
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade_0017():
    # Catalog enrichment on 6 tables + cv_material_mapping
    for tbl in ("board_materials","hardware_materials","custom_made",
                "benchtop_materials","appliances","equipment_hire"):
        op.execute(f"""
        ALTER TABLE {tbl}
          ADD COLUMN synonyms              text[]      NOT NULL DEFAULT '{{}}',
          ADD COLUMN default_supplier      varchar(128),
          ADD COLUMN default_lead_time_days int,
          ADD COLUMN archived_at           timestamptz,
          ADD COLUMN archived_by           bigint REFERENCES app_user(id);
        CREATE INDEX idx_{tbl}_synonyms ON {tbl} USING gin (synonyms);
        CREATE INDEX idx_{tbl}_active   ON {tbl} (workspace_id) WHERE archived_at IS NULL;
        """)
    op.execute(r"""
    CREATE TABLE cv_material_mapping (
      cv_material_mapping_id bigserial    PRIMARY KEY,
      workspace_id           bigint       NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
      cv_code                varchar(255) NOT NULL,
      target_material_table  text         NOT NULL CHECK (target_material_table IN
        ('board_materials','hardware_materials','custom_made',
         'benchtop_materials','appliances','equipment_hire')),
      target_material_id     bigint       NOT NULL,
      notes                  text,
      created_by             bigint       NOT NULL REFERENCES app_user(id),
      created_at             timestamptz  NOT NULL DEFAULT now(),
      updated_at             timestamptz  NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, cv_code)
    );
    CREATE INDEX idx_cv_material_mapping_target
      ON cv_material_mapping (target_material_table, target_material_id);
    """)


# === Migration 0018 (#7b) ===
# revision = "0018"
# down_revision = "0017"


def upgrade_0018():
    op.execute(r"""
    -- 1. cv_import_run
    CREATE TABLE cv_import_run (
      cv_import_run_id  bigserial    PRIMARY KEY,
      project_id        bigint       NOT NULL REFERENCES projects(project_id),
      item_id           bigint       NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
      source_filename   varchar(255) NOT NULL,
      sha256            char(64)     NOT NULL,
      row_count         int          NOT NULL DEFAULT 0,
      status            text         NOT NULL CHECK (status IN ('preview','committed','failed')),
      started_at        timestamptz  NOT NULL DEFAULT now(),
      completed_at      timestamptz,
      error_log         jsonb        NOT NULL DEFAULT '[]'::jsonb,
      created_by        bigint       NOT NULL REFERENCES app_user(id)
    );
    CREATE INDEX idx_cv_import_run_item   ON cv_import_run (item_id);
    CREATE INDEX idx_cv_import_run_status ON cv_import_run (project_id, status);
    """)


# === Migration 0019 (#7c) ===
# revision = "0019"
# down_revision = "0018"


def upgrade_0019():
    op.execute(r"""
    -- 1. part_slot.part_id
    ALTER TABLE part_slot
      ADD COLUMN part_id bigint REFERENCES parts(part_id) ON DELETE SET NULL;
    CREATE INDEX idx_part_slot_part ON part_slot (part_id);

    -- 2. cut_schedule enrichment
    ALTER TABLE cut_schedule
      ADD COLUMN priority    int    NOT NULL DEFAULT 0,
      ADD COLUMN assigned_to bigint REFERENCES app_user(id) ON DELETE SET NULL,
      ADD COLUMN created_at  timestamptz NOT NULL DEFAULT now(),
      ADD COLUMN created_by  bigint REFERENCES app_user(id),
      ADD COLUMN updated_at  timestamptz NOT NULL DEFAULT now();
    CREATE INDEX idx_cut_schedule_date_priority ON cut_schedule (scheduled_for, priority);

    -- 3. cut_plan metadata
    ALTER TABLE cut_plan
      ADD COLUMN created_by bigint REFERENCES app_user(id),
      ADD COLUMN notes      text;
    """)


def downgrade():
    # All three migrations have non-trivial column adds with defaults backfilled.
    # Downgrade is best-effort: drop the new columns + tables in reverse order.
    pass
```

---

## 9. Seed updates

Modifications to `seed/hartwood_joinery.py`:

1. **Enrich existing board_materials** — set `synonyms` arrays + `default_supplier='Laminex Australia'` + `default_lead_time_days=5`.
2. **Add 4 more board_materials** — `19-MELAMINE-WHITE`, `25-MDF`, `16-BLACK`, `19-WALNUT` with synonyms.
3. **Enrich existing hardware_materials** — synonyms arrays.
4. **Add 2 cv_material_mappings** — `'18-PB' → board_materials.18mm-pb`, `'700.0KC2.054.00' → hardware_materials.blum-runner`.
5. **Add CV import on ALF-001 item 1** — `cv_import_run` row with `status='committed'`, 2 modules, 9 parts.
6. **Add demo CutPlan on ALF-001** — name `"ALF-001 v1 nest"`, 1 sheet, 8 part_slots covering 6 of the 9 imported parts.
7. **Add 2 cut_schedule rows** — one `running` for today, one `planned` for tomorrow.
8. **Idempotency** — wrap each block in `DELETE ... WHERE` guards before inserts.

Header in seed file: `"6 board_materials · 4 hardware · 2 cv_mappings · 1 cv_import_run · 1 cut_plan · 2 cut_schedules"`.

---

## 10. Test plan

### 10.1 Pytest (api)

`apps/api/tests/test_cv_parser.py`:
- Header normalisation across alias forms.
- Required-column missing → `ValueError`.
- Numeric coercion + invalid rows.

`apps/api/tests/test_cv_resolver.py`:
- Mapping hit beats synonym hit.
- Multiple synonym tables → `unknown` with hint.
- Workspace isolation.

`apps/api/tests/test_cv_routes.py`:
- Preview writes `status='preview'`.
- Commit creates modules + parts + audit + edit log in one transaction.
- Re-import without `?mode=replace` → 409.
- Re-import with `?mode=replace` wipes and re-creates.
- Phase B `create_new` resolution actually inserts the catalog row.
- Cross-workspace `GET /cv-imports/{run_id}` → 404.
- Empty body → 422.

`apps/api/tests/test_catalog_routes.py`:
- 7 sub-routers each get smoke create/list/patch/archive tests.
- `equipment_hire` POST without `project_id` → 422.
- Bulk import 5-row CSV with 1 bad row → all-or-nothing.
- `synonyms` round-trips through GIN index.

`apps/api/tests/test_cut_floor_routes.py`:
- Plan creation in one transaction.
- `/items/{iid}/cut-plan` returns only relevant sheets, foreign slots flagged.
- Status transitions enforced.
- Reorder writes dense priorities.
- 409 deleting a plan with active schedules.

`apps/api/tests/test_rbac_matrix.py`:
- Drafter has full `catalog` + `cut_floor`.
- Editor has `read+write+comment` on `catalog` (no approve).
- Purchase officer has `read+comment` on `catalog`, `read` only on `cut_floor`.
- Viewer has `read` on both.

Coverage target: ≥80%.

### 10.2 E2E (Playwright)

`tests/e2e/cabinet_vision.spec.ts`:
- **Scenario A:** Drafter imports CV CSV with 1 unknown code → resolves → commits.
- **Scenario B:** Drafter views Board tab → SVG renders, tooltips work.
- **Scenario C:** Machine team reorders schedule → priority order persists.
- **Scenario D:** Drafter edits catalog → audit log shows update.

---

## 11. Audit events

| Event | Source | Payload shape |
|---|---|---|
| `cv.import.preview` | preview route | `{run_id, source_filename, row_count, summary}` |
| `cv.import.commit`  | commit route | `{run_id, modules_created, parts_created, mappings_created}` |
| `cv.import.fail`    | preview/commit error | `{run_id, error}` |
| `cv.import.replace_wipe` | commit `?mode=replace` | `{run_id, deleted_module_ids}` |
| `cv_material_mapping.create/update/delete` | mapping CRUD | `{cv_code, ...}` |
| `catalog.{table}.create/update/archive/csv_import` | catalog CRUD | per-action payload |
| `cut_plan.create/delete` | plan CRUD | `{plan_id, name, ...}` |
| `cut_schedule.create/update/status_change/reorder/cancel` | schedule CRUD | per-action payload |

All events use the `audit_log` helper from `apps/api/app/auth/audit.py`.

---

## 12. Open questions — RESOLVED 2026-05-05

All open questions resolved per the "current bias" path. Decisions below are binding for the implementation plans.

1. **Bin-packing engine API contract — RESOLVED.** Future optimizer ships as a separate `POST /projects/{pid}/optimise` endpoint that *returns* a `CutPlanIn` for the user to confirm-then-commit. The `POST /projects/{pid}/cut-plans` endpoint stays as the canonical persistence path; the optimizer is a proposal generator that calls it on confirm.
2. **CV CSV column-name normalisation table — RESOLVED.** Python constant in `apps/api/app/cv/parser.py`. Workspace-editable header table is YAGNI.
3. **Re-import semantics — RESOLVED.** Binary 409-or-`?mode=replace`. Three-way merge UI is deferred indefinitely.
4. **`cut_plan.is_current` flag — RESOLVED.** Defer. Board tab uses `MAX(cut_plan_id)`. Adding the flag later is a backwards-compatible nullable column.
5. **Synonyms array max length cap — RESOLVED.** No limit in v1.
6. **Drag-reorder — RESOLVED.** Hand-rolled HTML5 DnD. Add `@dnd-kit/core` only if QA files a UX defect.
7. **Equipment hire on `/catalog` — RESOLVED.** Stays on `/catalog` with a project picker; UI marks it visually as the odd one out.
8. **`cv_import_run.error_log` snapshot size — RESOLVED.** No cap in v1.
9. **PartSlot `label` fallback when `part_id` is null — RESOLVED.** Yes, render in foreign-slot grey, label as tooltip text.
10. **Cross-project CutSchedule project filter — RESOLVED.** Yes, single filter chip; defaults to "All projects".

---

**End of spec.** Ready for the planner agent to break into a 24–28 task implementation plan covering migration 0018, three new app modules, RBAC matrix update, four new web pages/tabs, seed updates, and the test suite expansion.

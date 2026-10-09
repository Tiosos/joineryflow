# Cabinet Vision (7a catalog, 7b CV import, 7c cut floor)

> Merged from `specs/2026-05-05-cabinet-vision-design.md`, `plans/2026-05-05-cabinet-vision-7a-catalog.md`, `plans/2026-05-05-cabinet-vision-7b-cv-import.md`, `plans/2026-05-08-cabinet-vision-7c-cut-floor.md` (October 2026). Each part below is the original text, verbatim, with headings pushed down two levels; use `git log --follow` on the original paths for history. This is a record of intent at one moment, not a description of the current code: see `docs/sub-projects/` and `CLAUDE.md`.


## Design spec

### JoineryFlow Cabinet Vision Integration Layer — Design Spec

**Date:** 2026-05-05
**Sub-project:** #7 (Cabinet Vision Integration Layer v2 — Material catalog enrichment + CV CSV import + CutPlan / CutSchedule UI)
**Sub-project slicing:** Ships in three independently-mergeable slices, in order:
- **#7a — Catalog enrichment + Mappings UI** (migration 0017, the `catalog` RBAC module, `/catalog` page incl. CV Mappings subtab; the catalog write-side that everything else depends on)
- **#7b — CV Import wizard** (migration 0018, the `cv_import_run` register, the `/items/{id}?tab=cutlist&import=cv` 3-phase wizard; depends on #7a's catalog + mapping CRUD)
- **#7c — CutPlan / CutSchedule + Board tab** (migration 0019, the `cut_floor` RBAC module, `/cut-floor` page + Drafter Board tab; independent of #7a/#7b — could ship in parallel but sequenced after for review bandwidth)
**Sequencing:** Cabinet Vision ships **before** Shop Floor (sub-project #8). Shop Floor's spec lives at `docs/archive/2026-05-05-shop-floor.md` and assumes migrations 0017–0019 are already applied.
**Branch base:** `feat/foundation` (HEAD `2f72c89`; latest migration on disk is 0016).
**Prior context:**
- `docs/archive/2026-04-22-foundation.md`
- `docs/archive/2026-04-25-pm-workbench.md`
- `docs/archive/2026-04-28-procurement-workbench.md`
- `docs/archive/2026-05-01-shop-drawings.md`
- `docs/archive/2026-05-02-pdf-generation.md`
- `docs/archive/2026-05-02-isample.md`
- `legacy/product_spec.md` §4.3, §5.2, §5.5, §5.6
- `legacy/trackingv2.md` §7
- `db/alembic/versions/0003_cut_schedule.py`
- `db/alembic/versions/0007_material_catalog_reconciliation.py`

---

#### 0. Goal

Cabinet Vision is the closed CAD program every Drafter at Hartwood lives in. The current bridge between CV and JoineryFlow is a Drafter manually retyping the CV cutlist export into the part grid. This sub-project wires up the full **CV → JoineryFlow → Machine Floor** pipeline that the v1 schema was deliberately shaped for but never exercised:

1. **Enrich the six material catalog tables** with the missing fields needed to make CV codes resolvable (synonyms, default supplier, default lead time, cost). v1 left these "schema-ready" but sparsely populated; #7 ships the workspace-scoped CRUD UI plus a bulk CSV importer so a workspace admin can land their full catalog in an afternoon.
2. **Ship CSV import** inside the Drafter Item Editor's Cutlist tab — a two-phase preview/commit flow that parses a CV-style CSV, resolves every material code through `cv_material_mapping` + per-table `synonyms`, surfaces unknown codes as a resolution UI, and on commit writes Modules + Parts in a single transaction.
3. **Ship the Drafter Board tab** — per-item visual rendering of the project `cut_plan` showing each `cut_sheet` with `part_slot` rectangles for parts that belong to this item.
4. **Ship the Machine team's Cut Schedule view** — a new top-level `/cut-floor` page (drag-reorder daily list of `cut_schedule` rows with status pills planned → running → done | cancelled).

The optimiser itself (real bin-packing nesting) stays out of scope; v1 of #7 lets a Drafter manually build a `cut_plan` from existing parts. The shape of the pipeline is what matters; a real nesting engine slots in behind the same API in a future sub-project.

---

#### 1. Scope

##### In scope

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

##### Out of scope (deferred)

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

#### 2. Architecture

##### 2.1 Backend layout

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

##### 2.2 Web layout

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

##### 2.3 Routing decisions

- New top-level page `/catalog` — admin/manager/drafter access; other roles 403 at `require_permission("catalog","read")`.
- New top-level page `/cut-floor` — admin/manager/drafter (full) and editor (Machine team — read+write+comment, no approve).
- Both new pages live behind the existing app shell but as `/catalog` and `/cut-floor` *do not* belong in the canonical 6-tab IA — they are reachable from the SideBar's secondary section.
- The Drafter Board tab is *inside* the item editor (not a top-level page).

##### 2.4 File store reuse

The CV import uploaded CSV is **not** stored in `file_blob` — it is a transient artefact. Only the SHA256 + filename + row count are kept on `cv_import_run`. The CSV bytes are read into memory, parsed, and discarded.

The `/catalog` "Bulk import CSV" upload is similarly transient.

##### 2.5 Workspace isolation

All registers gate via `projects.workspace_id` (or `workspace_id` directly for catalog tables, since 0007 added that column to all six). Pattern matches the post-`0014` workspace-isolation hardening.

---

#### 3. Data Model

##### 3.1 New tables

###### `cv_import_run`

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

###### `cv_material_mapping`

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

##### 3.2 Modifications to existing tables

###### `part_slot` — link to a real `part`

```sql
ALTER TABLE part_slot
  ADD COLUMN part_id bigint REFERENCES parts(part_id) ON DELETE SET NULL;

CREATE INDEX idx_part_slot_part ON part_slot (part_id);
```

Nullable, no backfill — v1 had no real cut plans.

###### `cut_schedule` — add `priority` + `assigned_to`

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

###### `cut_plan` — add `created_by` + `notes`

```sql
ALTER TABLE cut_plan
  ADD COLUMN created_by  bigint REFERENCES app_user(id),
  ADD COLUMN notes       text;
```

No `is_current` flag — Board tab queries `MAX(cut_plan_id) WHERE project_id = :pid`.

###### Six catalog tables — add `synonyms[]` + `default_supplier` + `default_lead_time_days` + `archived_at`

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

##### 3.3 Catalog write-path peculiarities

Each catalog table has a legacy NOT NULL UNIQUE column from migration 0007 (`code` on `board_materials`, `internal_ref` on `custom_made`, `slab_id` on `benchtop_materials`, `model_number` on `appliances`, `contract_ref` on `equipment_hire`; `hardware_materials` natively has `sku`). Catalog CRUD routes mirror procurement-v1 catalog routes — they fill the legacy column from the `sku` field on insert when the caller doesn't provide it. `equipment_hire` continues to require a `project_id` FK on insert, so its catalog tab demands a project picker; the other five tabs do not.

##### 3.4 Workspace isolation invariant

Catalog tables: `(workspace_id, sku)` UNIQUE constraint. `cv_material_mapping` is workspace-scoped. `cv_import_run` is item-scoped (workspace resolved through the item's project). `cut_plan` and `cut_schedule` are workspace-scoped through `cut_plan.workspace_id` (already on the table from migration 0003).

---

#### 4. API surface

##### 4.1 Catalog enrichment routes

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

###### CV mapping CRUD

| Method | Path | Gate | Notes |
|---|---|---|---|
| `GET`    | `/catalog/cv-mappings?q=` | `("catalog","read")` | List. |
| `POST`   | `/catalog/cv-mappings` | `("catalog","write")` | Create. UNIQUE on `(workspace_id, cv_code)` returns 409. |
| `PATCH`  | `/catalog/cv-mappings/{mid}` | `("catalog","write")` | Repoint to a different `(table, id)`. |
| `DELETE` | `/catalog/cv-mappings/{mid}` | `("catalog","write")` | Hard delete. |

##### 4.2 CV import routes

| Method | Path | Gate | Notes |
|---|---|---|---|
| `POST` | `/items/{iid}/cv-imports/preview` | `("cut_floor","write")` | Multipart form: `file` + optional `body` paste. Parses, resolves materials, writes `cv_import_run` with `status='preview'`. Audit: `cv.import.preview`. |
| `POST` | `/items/{iid}/cv-imports/{run_id}/commit` | `("cut_floor","write")` | Body: resolutions + `replace` flag. Single transaction creates modules + parts, updates `cv_material_mapping`, sets `cv_import_run.status='committed'`. |
| `GET`  | `/items/{iid}/cv-imports` | `("cut_floor","read")` | History. |
| `GET`  | `/cv-imports/{run_id}` | `("cut_floor","read")` | Single run with rehydrated preview. |

##### 4.3 CutPlan routes

| Method | Path | Gate | Notes |
|---|---|---|---|
| `POST`   | `/projects/{pid}/cut-plans` | `("cut_floor","write")` | Body: `{name, notes, sheets: [{sheet_no, material_sku, slots: [...]}]}`. Single transaction. |
| `GET`    | `/projects/{pid}/cut-plans` | `("cut_floor","read")` | List, newest first. |
| `GET`    | `/cut-plans/{plan_id}` | `("cut_floor","read")` | Full plan. |
| `GET`    | `/items/{iid}/cut-plan` | `("cut_floor","read")` | Most-recent project plan filtered to sheets containing slots from this item; foreign slots flagged `is_foreign=true`. |
| `DELETE` | `/cut-plans/{plan_id}` | `("cut_floor","write")` | Hard delete (CASCADE cleans up sheets + slots). 409 if a `cut_schedule` references this plan. |

##### 4.4 CutSchedule routes

| Method | Path | Gate | Notes |
|---|---|---|---|
| `GET`   | `/cut-schedules?date=YYYY-MM-DD` | `("cut_floor","read")` | List for a single day, ordered by `priority ASC`. |
| `GET`   | `/cut-schedules/{sid}` | `("cut_floor","read")` | One row with linked plan summary. |
| `POST`  | `/cut-schedules` | `("cut_floor","write")` | Body: `{cut_plan_id, scheduled_for, assigned_to?}`. Priority auto-assigned to `MAX(priority) + 100`. |
| `PATCH` | `/cut-schedules/{sid}` | `("cut_floor","write")` | Partial update. Status transitions enforced. 409 on illegal transition. |
| `POST`  | `/cut-schedules/reorder` | `("cut_floor","write")` | Body: `{scheduled_for, ordered_ids}`. Server rewrites priorities densely. |
| `DELETE`| `/cut-schedules/{sid}` | `("cut_floor","write")` | Soft-cancel (`status='cancelled'`). |

##### 4.5 Web routes (Next.js)

- `/catalog?tab=board|hardware|custom|benchtop|appliances|equipment_hire&q=&archived=`
- `/catalog?tab=cv-mappings&q=`
- `/cut-floor?date=YYYY-MM-DD`
- Item editor `/items/{id}?tab=board`
- CV import dialog opens *inside* `/items/{id}?tab=cutlist&import=cv`

---

#### 5. RBAC matrix delta

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

##### 5.1 Why `editor` gets write on `catalog`

Foreman / Machine team often knows "this is the supplier code we actually use" before the Drafter does. Letting them propose catalog edits (no approve) keeps that knowledge from being bottlenecked behind a Drafter. Audit log captures every change.

##### 5.2 Why `purchase_officer` gets `comment` on `catalog`

Procurement's job is sourcing materials; they need to read the catalog and leave a comment when a code's supplier is wrong. Write/approve still belongs to drafter+.

---

#### 6. CSV Import workflow detail

##### 6.1 Header normalisation

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

##### 6.2 Resolver order

For each row's `material_code`:

1. **Mapping hit** — `cv_material_mapping WHERE workspace_id = :w AND cv_code = :code`. Resolution: `mapped`.
2. **Synonym hit** — for each of the six tables, `WHERE :code = ANY(synonyms)`. Exactly one hit across all six → `synonym_match`. Multiple → `unknown` with hint `multiple_synonym_matches`.
3. **Exact-sku hit** — match on `sku` column or legacy NOT NULL UNIQUE column. Resolution: `synonym_match`.
4. **Otherwise** — `unknown`. UI surfaces in Phase B.

##### 6.3 Phase A response shape

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

##### 6.4 Persistence of preview snapshot

The full `CvPreviewOut` payload is also stored on `cv_import_run.error_log` under the key `_preview_snapshot` so `GET /cv-imports/{run_id}` can rehydrate without re-parsing.

##### 6.5 Phase B — resolve unknown

UI shows one row per `unknown_codes[]` with three actions:

- **Use existing** — typeahead across all six tables. On commit auto-writes `cv_material_mapping`.
- **Create new** — inline mini-form scoped to the suggested table. On commit creates the catalog row first, then writes the mapping, then uses it.
- **Skip** — drops the rows that reference this code.

##### 6.6 Phase C — commit transaction

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

##### 6.7 Re-import semantics

- Default: 409 if the item already has any modules or parts.
- `?mode=replace`: DELETE all modules (CASCADE wipes parts) before commit. Audit: `cv.import.replace_wipe`.
- `?mode=append` deferred to a future three-way merge UI.

##### 6.8 Audit + item edit log

The commit transaction writes:
- One `audit_log` `cv.import.commit` with `payload = {run_id, modules_created, parts_created, mappings_created}`.
- One `audit_log` per created part (`part.create`).
- One `item_edit_log` per created module (`field='_create_module'`).
- One `item_edit_log` per created part (`field='_create_part'`).
- One `item_edit_log` summary `field='_cv_import'`, `new_value='{run_id} ({M} parts)'`.

---

#### 7. UI surfaces

##### 7.1 `/catalog` page

- Server component `fetchMe()` for role gating, then renders `CatalogTabs`.
- 7-tab strip: `Board · Hardware · Custom · Benchtop · Appliances · Equipment Hire · CV Mappings`.
- Each material tab: filter strip (search + supplier select + archived toggle) + sortable grid (SKU, Description, Default supplier, Lead time, Unit cost, Synonyms, Updated). Inline-edit pattern.
- Bulk-import dialog: paste CSV or pick a file, see 3-line header preview, click Import → server returns `{created, errors}`.
- CV Mappings subtab: simple register grid with Add / Repoint / Delete.

##### 7.2 Drafter Editor — Cutlist tab Import dialog

`CvImportDialog.tsx` is a 3-phase wizard:

- **Phase A (Upload)**: textarea for paste + file picker. Submit → server preview.
- **Phase B (Resolve)**: summary chip + unknown-codes list with three-action inline UI.
- **Phase C (Commit)**: confirmation panel "Import 11 parts in 2 modules under Item ALF-001-ITEM-1?". Existing data warning if the item already has modules.

Closes on success and reloads the Cutlist grid via existing `fetch()` calls.

##### 7.3 Drafter Editor — Board tab

- Header: "Project CutPlan — `{plan_name}` (created `{date}` by `{author}`)".
- For each `cut_sheet` containing slots from this item: SVG canvas (max 800px wide, scaled to sheet aspect ratio) with each `part_slot` as a `<rect>`. Foreign slots in `--h-line` at 30% opacity; this-item slots in `--h-accent` at 60% opacity. Tooltip on hover.
- Empty state: "No CutPlan yet for this project."
- Read-only in v1.

##### 7.4 `/cut-floor` page

- Date picker (default today). Forward/back arrows.
- Sortable list of `cut_schedule` rows for the date, drag-to-reorder (HTML5 DnD; no library).
- Each row: status pill · plan name · supplier chip · assigned-to avatar · Start / Mark done / Cancel buttons.
- "Add to today" dialog with CutPlan picker + assigned-to picker.
- Reorder fires `POST /cut-schedules/reorder`.

---

#### 8. Migrations needed

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

#### 9. Seed updates

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

#### 10. Test plan

##### 10.1 Pytest (api)

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

##### 10.2 E2E (Playwright)

`tests/e2e/cabinet_vision.spec.ts`:
- **Scenario A:** Drafter imports CV CSV with 1 unknown code → resolves → commits.
- **Scenario B:** Drafter views Board tab → SVG renders, tooltips work.
- **Scenario C:** Machine team reorders schedule → priority order persists.
- **Scenario D:** Drafter edits catalog → audit log shows update.

---

#### 11. Audit events

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

#### 12. Open questions — RESOLVED 2026-05-05

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


## Implementation plan — 7a catalog

### JoineryFlow Catalog Enrichment + CV Mappings UI Implementation Plan

> **Status: shipped.** Migration `0017`. Current state lives in
> `## Catalog enrichment + CV Mappings (sub-project #7a)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/archive/README.md`).

> **Later change:** The risk note telling you **not** to retire the procurement-side
> `/catalogs/*` is superseded — that surface was retired in `64ef89e` and
> `/catalog/*` is now the only one.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Later change — superseded in part by Plan V1 (see `docs/plan-v1/`).** The
> `supplier` / `default_supplier` free-text columns this plan enriched become
> **foreign keys to a real supplier entity** (Q506), which Plan V1 §21's supplier
> comparison, performance tracking and five supplier statuses all require.

**Date:** 2026-05-05
**Sub-project:** #7a — Catalog enrichment + CV Mappings UI (the first slice of #7 Cabinet Vision Integration)
**Spec:** `docs/archive/2026-05-05-cabinet-vision.md` — read §1 (scope), §2.1 (backend layout), §3.1–3.4 (catalog enrichment + `cv_material_mapping`), §4.1 (catalog routes incl. CV mappings), §5 (RBAC), §7.1 (`/catalog` page UI), §8 (migration 0017 portion only), §9 (seed updates limited to catalog enrichment + 2 cv_material_mapping rows).
**Branch base:** `feat/foundation` (HEAD `2f72c89`; latest migration on disk is `0016_sample.py`).

---

#### Goal

Ship the **catalog write-side** that everything else in #7 depends on. By the end of this slice, a Drafter (or any drafter+/manager+/admin) can:

1. Open `/catalog` and see a 7-tab strip (Board · Hardware · Custom · Benchtop · Appliances · Equipment Hire · CV Mappings).
2. Edit a row inline (description / sku / supplier / lead time / synonyms) — saves on blur.
3. Add new rows via a per-tab "+ New" button. Equipment-hire requires a project picker; the other five do not.
4. Bulk-import a CSV (3-line preview) — single-transaction all-or-nothing — and see `{created, errors}` in the dialog.
5. Soft-archive a row (sets `archived_at` + `archived_by`); the archived toggle in the filter strip controls visibility.
6. Open the **CV Mappings** subtab and CRUD `cv_material_mapping` rows that translate freeform CV codes (e.g. `18-PB`, `700.0KC2.054.00`) to a `(target_material_table, target_material_id)` pair. Hard-delete here is fine; the table has no downstream references in #7a.

#7a does **not** ship: the CV CSV preview/commit wizard (deferred to **#7b**), `cv_import_run` register (deferred to **#7b**), CutPlan/CutSchedule + Board tab + `/cut-floor` page (deferred to **#7c**), or the bin-packing optimiser (indefinite).

---

#### Outcome

- One DB migration (`0017_catalog_enrichment.py`) adds five enrichment columns to all six catalog tables (`synonyms text[]`, `default_supplier varchar(128)`, `default_lead_time_days int`, `archived_at timestamptz`, `archived_by bigint REFERENCES app_user(id)`), plus a GIN index on `synonyms` and a partial active-row index, on each. It also CREATEs `cv_material_mapping` with its UNIQUE + index per spec §3.1.
- One new `catalog` module is added to the RBAC matrix in `apps/api/app/auth/permissions.py`. Drafter/manager/admin get `{read, write, approve, comment}`. Editor gets `{read, write, comment}`. Purchase officer gets `{read, comment}`. Viewer gets `{read}`. (See spec §5 + §5.1 + §5.2.)
- One new backend module `apps/api/app/catalog/` (routes + queries + schemas) — 7 sub-routers (one per material type + one for `cv-mappings`) wired into `apps/api/app/main.py`.
- One new web page `/catalog` with 7 tabs + filter strip + editable grid + bulk-import dialog + Mappings panel; one new SideBar entry; two new lib helpers (`catalog-types.ts`, `catalog-fetch.ts`).
- Seed extension: enriches the existing 2 `board_materials` + 4 `hardware_materials` rows with `synonyms[]` + `default_supplier`, adds 4 more `board_materials` demo rows, and inserts 2 demo `cv_material_mapping` rows. Idempotent.
- Tests: `test_catalog_routes.py` (~25 cases), `test_cv_mapping_routes.py` (~10 cases), `test_catalog_workspace_isolation.py` (~6 cases), and 5 new `isample`-style entries appended to `test_permissions.py` for the new module. Plus a Playwright `tests/e2e/catalog.spec.ts` happy-path.
- CLAUDE.md gets a new "Catalog enrichment + CV Mappings (sub-project #7a)" subsection mirroring the iSample/PDF/Procurement entries.

#### Risks

- **Per-table column shape divergence.** Each of the six catalog tables has a different legacy NOT NULL UNIQUE column from migration 0007 (`code` on board, `internal_ref` on custom_made, `slab_id` on benchtop, `model_number` on appliance, `contract_ref` on equipment_hire; hardware natively uses `sku`). The enrichment columns are the *same* across all six, but the per-table CRUD must continue to honour the legacy NOT NULL constraints. Mitigation: a single `REGISTRY` dict (mirroring `apps/api/app/procurement_v1/catalogs/queries.py` lines 19–56) drives every sub-router. The plan reuses the existing `(table, id_col, select_cols, insertable_cols)` shape and **extends** `select_cols` + `insertable_cols` with the five new enrichment columns per row.
- **`equipment_hire` is special.** Its PK is `hire_id` (not `material_id`) and it requires a `project_id` FK on insert. The web bulk-import + "+ New" UI must show a project picker only on this tab.
- **Procurement-side `/catalogs/*` already exists.** The existing module at `apps/api/app/procurement_v1/catalogs/` is gated by `("orderbook", *)`; it stays untouched. The new `/catalog/*` (singular) routes are a parallel surface gated by `("catalog", *)`. **Do not** rewire procurement to the new module — the procurement queue UI still depends on its current path. (The two surfaces will converge in a future cleanup; that is out of scope for #7a.)
- **GIN index on `synonyms`.** Postgres GIN over `text[]` requires `ANY(:code) ILIKE` style lookups in #7b's resolver. We add the index now to keep #7b cheap; it has zero impact on #7a write paths but does cost ~200 ms of migration time on a fresh seed.
- **Workspace isolation regression.** All six catalog tables already have `workspace_id`. The new `cv_material_mapping` table is workspace-scoped via `workspace_id` FK. Every read + write path must filter on `workspace_id = :w` from `AuthUser`. Mitigation: `test_catalog_workspace_isolation.py` covers cross-workspace 404 on every sub-router.

---

#### Pre-flight checklist

- [ ] Confirm working tree is clean: `git status` shows only `.gitignore`, `.claude/`, and `.pnpm-store/` (per the conversation start snapshot).
- [ ] Confirm branch: `git rev-parse --abbrev-ref HEAD` → `feat/foundation`.
- [ ] Confirm latest migration on disk: `ls db/alembic/versions/ | sort | tail -3` → `0014_*`, `0015_*`, `0016_sample.py`.
- [ ] Confirm baseline pytest: `docker compose exec api pytest -q` → expected pass count from CLAUDE.md (≥ 261 passing).
- [ ] Confirm `make up` is current: `docker compose ps` shows `api`, `db`, `web` all `Up`.
- [ ] Read spec §1, §3.1–3.4, §4.1, §5, §7.1, §8, §9 once before starting.
- [ ] Read sibling code: `apps/api/app/procurement_v1/catalogs/{queries.py,routes.py}` (the structural template), `apps/api/app/samples/queries.py` (workspace-isolation pattern), and `apps/api/app/samples/routes.py` (RBAC + error mapping).

---

#### File structure (locked)

```
apps/api/app/
  catalog/
    __init__.py
    routes.py                # 7 sub-routers + bulk-import + cv-mappings CRUD
    queries.py               # text() SQL — REGISTRY-driven CRUD with audit
    schemas.py               # Pydantic v2 — In/Out/Bulk per sub-resource
  auth/
    permissions.py           # MODIFY: add `catalog` to Module + _ALL_MODULES + per-role rows
  main.py                    # MODIFY: include_router(catalog_router)

apps/api/tests/
  conftest.py                # MODIFY: add `cv_material_mapping` to TRUNCATE_TABLES
  test_catalog_routes.py     # NEW — ~25 cases
  test_cv_mapping_routes.py  # NEW — ~10 cases
  test_catalog_workspace_isolation.py  # NEW — ~6 cases
  test_permissions.py        # MODIFY: append 5 catalog-row tests

db/alembic/versions/
  0017_catalog_enrichment.py # NEW

seed/
  hartwood_joinery.py        # MODIFY: enrich existing rows + 4 new boards + 2 mappings

apps/web/app/(app)/catalog/
  page.tsx                              # NEW — server wrapper
  _components/
    CatalogClient.tsx                   # client wrapper (URL state owner)
    CatalogTabs.tsx                     # 7-tab strip
    CatalogFilters.tsx                  # search + supplier + archived toggle
    CatalogGrid.tsx                     # editable per-table grid
    CatalogRow.tsx                      # one row (inline-edit on blur)
    NewCatalogRowDialog.tsx             # create
    CatalogBulkImportDialog.tsx         # paste/upload CSV
    MappingPanel.tsx                    # cv_material_mapping CRUD
    NewMappingDialog.tsx

apps/web/lib/
  catalog-types.ts                      # mirrors API schemas
  catalog-fetch.ts                      # tiny fetch wrappers

apps/web/components/chrome/
  SideBar.tsx                           # MODIFY: + "Catalog" entry, drafter+ visible

tests/e2e/
  catalog.spec.ts                       # NEW happy-path

docs/archive/plans/
  2026-05-05-cabinet-vision-7a-catalog.md  # this file

CLAUDE.md                               # MODIFY: append Catalog (#7a) subsection
```

---

#### Phase 1 — Schema + RBAC (3 tasks)

##### Task 1: Migration 0017 — catalog enrichment + `cv_material_mapping`

**Files:**
- Create: `db/alembic/versions/0017_catalog_enrichment.py`

This is the wire-format-locked migration. Per spec §8, all five enrichment columns go on all six tables in a single revision; `cv_material_mapping` lands in the same migration so the `/catalog` Mappings subtab has a register to bind to.

- [ ] **Step 1: Write the migration**

Create `db/alembic/versions/0017_catalog_enrichment.py`:

```python
"""catalog enrichment + cv_material_mapping — sub-project #7a

Adds:
- synonyms text[] + default_supplier + default_lead_time_days +
  archived_at + archived_by on all 6 catalog tables.
- GIN index on synonyms; partial active-row index (workspace_id) WHERE archived_at IS NULL.
- cv_material_mapping (workspace, cv_code) UNIQUE register.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-05
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


CATALOG_TABLES = (
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
)


def upgrade():
    for tbl in CATALOG_TABLES:
        op.execute(f"""
        ALTER TABLE {tbl}
          ADD COLUMN synonyms               text[]      NOT NULL DEFAULT '{{}}',
          ADD COLUMN default_supplier       varchar(128),
          ADD COLUMN default_lead_time_days int,
          ADD COLUMN archived_at            timestamptz,
          ADD COLUMN archived_by            bigint REFERENCES app_user(id);
        """)
        op.execute(f"CREATE INDEX idx_{tbl}_synonyms ON {tbl} USING gin (synonyms);")
        op.execute(
            f"CREATE INDEX idx_{tbl}_active ON {tbl} (workspace_id) "
            f"WHERE archived_at IS NULL;"
        )

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


def downgrade():
    op.execute("-- intentionally not reversible; recover via 0001-0016 only")
```

- [ ] **Step 2: Apply the migration**

```bash
docker compose exec -T api sh -c "cd /db && alembic upgrade head"
```

Expected output ends with `INFO  [alembic.runtime.migration] Running upgrade 0016 -> 0017`.

- [ ] **Step 3: Verify columns + indexes on each table**

```bash
for tbl in board_materials hardware_materials custom_made benchtop_materials appliances equipment_hire; do
  docker compose exec -T db psql -U jf -d joineryflow -c "\d+ $tbl" | grep -E "synonyms|default_supplier|default_lead_time_days|archived_at|archived_by"
done
docker compose exec -T db psql -U jf -d joineryflow -c "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'idx_%_synonyms' OR indexname LIKE 'idx_%_active';"
```

Expected: 5 rows × 6 tables = 30 lines. 12 indexes (6 GIN + 6 partial active).

- [ ] **Step 4: Verify `cv_material_mapping`**

```bash
docker compose exec -T db psql -U jf -d joineryflow -c "\d+ cv_material_mapping"
docker compose exec -T db psql -U jf -d joineryflow -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'cv_material_mapping';"
```

Expected: 9 columns; UNIQUE on `(workspace_id, cv_code)`; CHECK on `target_material_table`; FKs to workspace + app_user; pkey + UNIQUE + `idx_cv_material_mapping_target`.

- [ ] **Step 5: Smoke-test the CHECK constraint**

```bash
docker compose exec -T db psql -U jf -d joineryflow -v ON_ERROR_STOP=0 <<'SQL'
BEGIN;
INSERT INTO workspace(slug,name) VALUES('mig17','Mig17') RETURNING id \gset
INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
  VALUES (:id,'mt17@test','MT17','x','drafter') RETURNING id AS uid \gset
-- bad target_material_table
INSERT INTO cv_material_mapping(workspace_id, cv_code, target_material_table, target_material_id, created_by)
  VALUES (:id, 'X', 'not_a_table', 1, :uid);
ROLLBACK;
SQL
```

Expected: INSERT fails with `ERROR: new row for relation "cv_material_mapping" violates check constraint "cv_material_mapping_target_material_table_check"`.

- [ ] **Step 6: Re-run the full pytest suite**

```bash
docker compose exec api pytest -q
```

Expected: same pass count as the pre-migration baseline (no test depends on these new columns yet).

- [ ] **Step 7: Commit**

```
feat(db): migration 0017 — catalog enrichment + cv_material_mapping (#7a)
```

---

##### Task 2: Add `cv_material_mapping` to `TRUNCATE_TABLES`

**Files:**
- Modify: `apps/api/tests/conftest.py`

The `truncate_all` fixture needs the new table in its tuple so end-to-end tests start clean. FK ordering: `cv_material_mapping` references `workspace` and `app_user` only; it can sit anywhere above `workspace` and `app_user`. Place it just below `audit_log` to keep the visual grouping (cross-cutting registers).

- [ ] **Step 1: Edit `apps/api/tests/conftest.py`**

In the `TRUNCATE_TABLES` tuple, add `"cv_material_mapping"` between `"projects"` and `"audit_log"`:

```python
TRUNCATE_TABLES = (
    "shop_drawing_revision",
    "shop_drawing",
    "sample",
    "item_attachment",
    "file_blob",
    "batch_allocations",
    "procurement_batches",
    "project_hardware_catalog_log",
    "project_hardware_catalog",
    "item_hardware_lines",
    "parts",
    "modules",
    "item_status_log",
    "item_edit_log",
    "item_stages",
    "items",
    "project_favourites",
    "projects",
    "cv_material_mapping",
    "audit_log",
    "session",
    "app_user",
    "workspace",
)
```

Note: the six catalog tables (`board_materials`, etc.) are deliberately *not* in `TRUNCATE_TABLES` because the tests rely on the seed-loaded baseline rows. New tests for #7a INSERT their own catalog rows inside the per-test transaction — the rollback fixture cleans them up.

- [ ] **Step 2: Verify the suite still passes**

```bash
docker compose exec api pytest -q
```

Expected: same pass count as before.

- [ ] **Step 3: Commit**

```
test(api): truncate cv_material_mapping in conftest (#7a)
```

---

##### Task 3: RBAC matrix — add `catalog` module

**Files:**
- Modify: `apps/api/app/auth/permissions.py`
- Modify: `apps/api/tests/test_permissions.py`

Per spec §5, the new `catalog` module needs to slot into the `Module` Literal + `_ALL_MODULES` tuple, and each role needs an explicit `catalog` row (no `_ALL_MODULES` derivation traps — the matrix uses dict comprehensions in some places that already excluded `it_management`; re-read before editing).

- [ ] **Step 1: Read `apps/api/app/auth/permissions.py`** to confirm current shape (we know it's 7 modules: dashboard, tracking, list, shop_dwgs, isample, orderbook, it_management).

- [ ] **Step 2: Append failing tests to `apps/api/tests/test_permissions.py`**

```python
def test_drafter_catalog_full_access():
    """Drafter is elevated to admin/manager parity on catalog (#7a)."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["catalog"] == {"read", "write", "approve", "comment"}


def test_editor_catalog_can_read_write_comment_no_approve():
    from app.auth.permissions import MATRIX
    assert MATRIX["editor"]["catalog"] == {"read", "write", "comment"}


def test_purchase_officer_catalog_read_and_comment():
    from app.auth.permissions import MATRIX
    assert MATRIX["purchase_officer"]["catalog"] == {"read", "comment"}


def test_viewer_catalog_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["viewer"]["catalog"] == {"read"}


def test_manager_admin_catalog_full_access():
    from app.auth.permissions import MATRIX
    assert MATRIX["manager"]["catalog"] == {"read", "write", "approve", "comment"}
    assert MATRIX["admin"]["catalog"] == {"read", "write", "approve", "comment"}
```

- [ ] **Step 3: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_permissions.py -v -k "catalog"
```

Expected: 5 failures (the `catalog` module doesn't exist in the matrix yet).

- [ ] **Step 4: Update `apps/api/app/auth/permissions.py`**

```python
Module = Literal[
    "dashboard",
    "tracking",
    "list",
    "shop_dwgs",
    "isample",
    "orderbook",
    "catalog",          # NEW (#7a)
    "it_management",
]

_ALL_MODULES: tuple[str, ...] = (
    "dashboard",
    "tracking",
    "list",
    "shop_dwgs",
    "isample",
    "orderbook",
    "catalog",          # NEW (#7a)
    "it_management",
)
```

Per-role updates:

```python
"editor": {
    m: {"read", "write", "comment"}
    for m in ("dashboard", "tracking", "list", "shop_dwgs", "isample")
}
| {
    "orderbook": {"read", "comment"},
    "catalog":   {"read", "write", "comment"},   # NEW
    "it_management": set(),
},
"drafter": {
    "dashboard":     {"read"},
    "tracking":      {"read", "write", "approve", "comment"},
    "list":          {"read", "write", "approve", "comment"},
    "shop_dwgs":     {"read", "write", "approve", "comment"},
    "isample":       {"read", "write", "approve", "comment"},
    "orderbook":     {"read", "write", "approve", "comment"},
    "catalog":       {"read", "write", "approve", "comment"},   # NEW
    "it_management": set(),
},
"purchase_officer": {
    "dashboard":     {"read"},
    "tracking":      {"read", "comment"},
    "list":          {"read"},
    "shop_dwgs":     {"read"},
    "isample":       {"read"},
    "orderbook":     {"read", "write", "approve", "comment"},
    "catalog":       {"read", "comment"},   # NEW
    "it_management": set(),
},
```

The `admin`, `manager`, and `viewer` rows use `_ALL_MODULES` comprehensions, so adding `catalog` to that tuple automatically grants them the right perms (full for admin; full for manager; read for viewer).

- [ ] **Step 5: Run targeted tests, confirm pass**

```bash
docker compose exec api pytest tests/test_permissions.py -v -k "catalog"
```

Expected: 5 passed.

- [ ] **Step 6: Run full pytest suite**

```bash
docker compose exec api pytest -q
```

Expected: previous count + 5.

- [ ] **Step 7: Commit**

```
feat(rbac): add catalog module + drafter/editor/purchase_officer parity (#7a)
```

---

#### Phase 2 — Backend module (6 tasks)

##### Task 4: Pydantic schemas (`apps/api/app/catalog/schemas.py`)

**Files:**
- Create: `apps/api/app/catalog/__init__.py`
- Create: `apps/api/app/catalog/schemas.py`

The module owns 7 logical sub-resources. Schemas go in one file because (a) they share enrichment-column types and (b) the file stays under 200 lines.

- [ ] **Step 1: Package init**

Create `apps/api/app/catalog/__init__.py`:

```python
"""Catalog enrichment + CV mapping CRUD (sub-project #7a).

Workspace-scoped CRUD across the 6 material catalog tables, plus the
cv_material_mapping register that translates freeform CV codes to
(target_table, target_id). All routes gated by ("catalog", action)."""
```

- [ ] **Step 2: Schemas**

Create `apps/api/app/catalog/schemas.py`. Pattern: every sub-resource has `CreateXIn`, `PatchXIn`, and a permissive `XOut` (mapping-friendly, `extra="allow"` so per-table legacy columns flow through).

```python
"""Pydantic v2 schemas for the catalog module."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CatalogTable = Literal[
    "board_materials",
    "hardware_materials",
    "custom_made",
    "benchtop_materials",
    "appliances",
    "equipment_hire",
]


# === Enrichment-column mixins (shared across the 6 tables) ===

class _EnrichmentFields(BaseModel):
    """Fields added to every catalog table by migration 0017."""
    synonyms: list[str] = Field(default_factory=list)
    default_supplier: str | None = Field(default=None, max_length=128)
    default_lead_time_days: int | None = Field(default=None, ge=0, le=999)


# === Per-table create schemas ===
# Each forwards (sku, description, ...legacy_unique...) plus the enrichment fields.

class CreateBoardIn(_EnrichmentFields):
    code: str = Field(min_length=1, max_length=32)        # legacy NOT NULL UNIQUE
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateHardwareIn(_EnrichmentFields):
    sku: str = Field(min_length=1, max_length=64)         # legacy NOT NULL UNIQUE
    description: str = Field(min_length=1, max_length=255)


class CreateCustomMadeIn(_EnrichmentFields):
    internal_ref: str = Field(min_length=1, max_length=64)  # legacy NOT NULL UNIQUE
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateBenchtopIn(_EnrichmentFields):
    slab_id: str = Field(min_length=1, max_length=64)     # legacy NOT NULL UNIQUE
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateApplianceIn(_EnrichmentFields):
    model_number: str = Field(min_length=1, max_length=64)  # legacy NOT NULL UNIQUE
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)


class CreateEquipmentHireIn(_EnrichmentFields):
    contract_ref: str = Field(min_length=1, max_length=64)  # legacy NOT NULL UNIQUE
    sku: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    project_id: int   # FK required for hire only


# === Per-table patch schemas (every field optional) ===

class PatchBaseIn(_EnrichmentFields):
    description: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=64)


class PatchBoardIn(PatchBaseIn):
    code: str | None = Field(default=None, max_length=32)


class PatchHardwareIn(PatchBaseIn):
    pass


class PatchCustomMadeIn(PatchBaseIn):
    internal_ref: str | None = Field(default=None, max_length=64)


class PatchBenchtopIn(PatchBaseIn):
    slab_id: str | None = Field(default=None, max_length=64)


class PatchApplianceIn(PatchBaseIn):
    model_number: str | None = Field(default=None, max_length=64)


class PatchEquipmentHireIn(PatchBaseIn):
    contract_ref: str | None = Field(default=None, max_length=64)
    project_id: int | None = None


# === Out shape ===

class CatalogRowOut(BaseModel):
    """Permissive: routes return dict-of-mappings; this just labels it."""
    model_config = ConfigDict(extra="allow")
    type: str
    archived_at: datetime | None = None


class CatalogListOut(BaseModel):
    type: str
    rows: list[CatalogRowOut]


# === Bulk import ===

class BulkRowError(BaseModel):
    row_index: int
    error: str


class BulkImportIn(BaseModel):
    """Generic bulk-import body: a list of dicts shaped like CreateXIn for the
    target table. Validation is per-row inside the route; we keep this Any-shaped
    so the same schema serves all 6 tables."""
    rows: list[dict] = Field(min_length=1, max_length=1000)


class BulkImportOut(BaseModel):
    created: int
    errors: list[BulkRowError]


# === CV mapping ===

class CreateCvMappingIn(BaseModel):
    cv_code: str = Field(min_length=1, max_length=255)
    target_material_table: CatalogTable
    target_material_id: int
    notes: str | None = Field(default=None, max_length=2000)


class PatchCvMappingIn(BaseModel):
    cv_code: str | None = Field(default=None, max_length=255)
    target_material_table: CatalogTable | None = None
    target_material_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CvMappingOut(BaseModel):
    cv_material_mapping_id: int
    workspace_id: int
    cv_code: str
    target_material_table: CatalogTable
    target_material_id: int
    target_description: str | None = None
    notes: str | None = None
    created_by: int
    created_at: datetime
    updated_at: datetime


class CvMappingListOut(BaseModel):
    rows: list[CvMappingOut]
    total: int
```

- [ ] **Step 3: No tests yet** — schemas are validated through routes in later tasks.

- [ ] **Step 4: Commit**

```
feat(api): catalog schemas (#7a)
```

---

##### Task 5: Queries layer (`apps/api/app/catalog/queries.py`)

**Files:**
- Create: `apps/api/app/catalog/queries.py`

This is the workhorse. The REGISTRY mirrors `apps/api/app/procurement_v1/catalogs/queries.py` but extends `select_cols` and `insertable_cols` with the five enrichment columns. Workspace isolation is mandatory on every read + write.

- [ ] **Step 1: Write `queries.py`**

Create `apps/api/app/catalog/queries.py`:

```python
"""Catalog CRUD with workspace isolation + audit hooks.

REGISTRY-driven: one dict entry per material type. The five enrichment columns
(synonyms, default_supplier, default_lead_time_days, archived_at, archived_by)
are present on every table per migration 0017. Per-table legacy NOT NULL UNIQUE
columns (code, internal_ref, slab_id, model_number, contract_ref) are honoured
via insert_cols.

Routes own the transaction boundary; queries flush only.
"""
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# (table, id_col, select_cols_csv, insertable_cols_tuple)
ENRICHMENT_SELECT = (
    "synonyms, default_supplier, default_lead_time_days, archived_at, archived_by"
)
ENRICHMENT_INSERT = (
    "synonyms", "default_supplier", "default_lead_time_days",
    # archived_at + archived_by are written by the archive route, not by create/patch
)

REGISTRY: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "board": (
        "board_materials",
        "material_id",
        f"material_id, code, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("code", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "hardware": (
        "hardware_materials",
        "material_id",
        f"material_id, sku, description, workspace_id, {ENRICHMENT_SELECT}",
        ("sku", "description", *ENRICHMENT_INSERT),
    ),
    "custom_made": (
        "custom_made",
        "material_id",
        f"material_id, internal_ref, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("internal_ref", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "benchtop": (
        "benchtop_materials",
        "material_id",
        f"material_id, slab_id, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("slab_id", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "appliance": (
        "appliances",
        "material_id",
        f"material_id, model_number, description, sku, workspace_id, {ENRICHMENT_SELECT}",
        ("model_number", "description", "sku", *ENRICHMENT_INSERT),
    ),
    "hire": (
        "equipment_hire",
        "hire_id",
        f"hire_id, contract_ref, project_id, description, sku, workspace_id, "
        f"{ENRICHMENT_SELECT}",
        ("contract_ref", "project_id", "description", "sku", *ENRICHMENT_INSERT),
    ),
}


def list_catalog(
    db: Session,
    *,
    type_: str,
    workspace_id: int,
    q: str | None = None,
    supplier: str | None = None,
    archived: bool = False,
) -> list[dict]:
    table, id_col, cols, _ = REGISTRY[type_]
    where = ["workspace_id = :w"]
    params: dict = {"w": workspace_id}
    if not archived:
        where.append("archived_at IS NULL")
    if q:
        where.append("(description ILIKE :q OR sku ILIKE :q)")
        params["q"] = f"%{q}%"
    if supplier:
        where.append("default_supplier = :sup")
        params["sup"] = supplier
    sql = (
        f"SELECT {cols} FROM {table} "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY {id_col} DESC"
    )
    return [dict(r) | {"type": type_} for r in db.execute(text(sql), params).mappings()]


def get_catalog_row(
    db: Session, *, type_: str, mid: int, workspace_id: int
) -> dict | None:
    table, id_col, cols, _ = REGISTRY[type_]
    sql = text(
        f"SELECT {cols} FROM {table} "
        f"WHERE {id_col} = :id AND workspace_id = :w"
    )
    r = db.execute(sql, {"id": mid, "w": workspace_id}).mappings().first()
    return (dict(r) | {"type": type_}) if r else None


def create_catalog_row(
    db: Session, *, type_: str, fields: dict[str, Any], workspace_id: int
) -> int:
    table, id_col, _, insert_cols = REGISTRY[type_]
    use = {k: v for k, v in fields.items() if k in insert_cols}
    if not use:
        raise ValueError("no insertable fields supplied")
    use["workspace_id"] = workspace_id
    cols = list(use.keys())
    sql = text(
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)}) "
        f"RETURNING {id_col}"
    )
    return db.execute(sql, use).scalar()


def patch_catalog_row(
    db: Session, *, type_: str, mid: int, fields: dict, workspace_id: int
) -> int | None:
    if not fields:
        return mid
    table, id_col, _, insert_cols = REGISTRY[type_]
    use = {k: v for k, v in fields.items() if k in insert_cols}
    if not use:
        return mid
    sets = ", ".join(f"{c} = :{c}" for c in use.keys())
    sql = text(
        f"UPDATE {table} SET {sets} "
        f"WHERE {id_col} = :id AND workspace_id = :w "
        f"RETURNING {id_col}"
    )
    return db.execute(sql, {**use, "id": mid, "w": workspace_id}).scalar()


def archive_catalog_row(
    db: Session, *, type_: str, mid: int, actor_id: int, workspace_id: int
) -> int | None:
    table, id_col, _, _ = REGISTRY[type_]
    sql = text(
        f"UPDATE {table} SET archived_at = now(), archived_by = :a "
        f"WHERE {id_col} = :id AND workspace_id = :w AND archived_at IS NULL "
        f"RETURNING {id_col}"
    )
    return db.execute(sql, {"a": actor_id, "id": mid, "w": workspace_id}).scalar()


# === CV mapping ===

def list_cv_mappings(
    db: Session, *, workspace_id: int, q: str | None = None
) -> dict:
    where = ["m.workspace_id = :w"]
    params: dict = {"w": workspace_id}
    if q:
        where.append("(m.cv_code ILIKE :q OR m.notes ILIKE :q)")
        params["q"] = f"%{q}%"
    rows = db.execute(text(f"""
        SELECT m.cv_material_mapping_id, m.workspace_id, m.cv_code,
               m.target_material_table, m.target_material_id,
               m.notes, m.created_by, m.created_at, m.updated_at,
               CASE m.target_material_table
                 WHEN 'board_materials'    THEN (SELECT description FROM board_materials    WHERE material_id = m.target_material_id)
                 WHEN 'hardware_materials' THEN (SELECT description FROM hardware_materials WHERE material_id = m.target_material_id)
                 WHEN 'custom_made'        THEN (SELECT description FROM custom_made        WHERE material_id = m.target_material_id)
                 WHEN 'benchtop_materials' THEN (SELECT description FROM benchtop_materials WHERE material_id = m.target_material_id)
                 WHEN 'appliances'         THEN (SELECT description FROM appliances         WHERE material_id = m.target_material_id)
                 WHEN 'equipment_hire'     THEN (SELECT description FROM equipment_hire     WHERE hire_id     = m.target_material_id)
               END AS target_description
          FROM cv_material_mapping m
         WHERE {' AND '.join(where)}
         ORDER BY m.cv_material_mapping_id DESC
    """), params).mappings().all()
    return {"rows": [dict(r) for r in rows], "total": len(rows)}


def get_cv_mapping(db: Session, *, mid: int, workspace_id: int) -> dict | None:
    r = db.execute(text("""
        SELECT cv_material_mapping_id, workspace_id, cv_code,
               target_material_table, target_material_id,
               notes, created_by, created_at, updated_at
          FROM cv_material_mapping
         WHERE cv_material_mapping_id = :id AND workspace_id = :w
    """), {"id": mid, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def create_cv_mapping(
    db: Session, *, payload: dict, actor_id: int, workspace_id: int
) -> int:
    sql = text("""
        INSERT INTO cv_material_mapping
          (workspace_id, cv_code, target_material_table, target_material_id,
           notes, created_by)
        VALUES (:w, :code, :tbl, :tid, :notes, :a)
        RETURNING cv_material_mapping_id
    """)
    return db.execute(sql, {
        "w": workspace_id,
        "code": payload["cv_code"],
        "tbl":  payload["target_material_table"],
        "tid":  payload["target_material_id"],
        "notes": payload.get("notes"),
        "a": actor_id,
    }).scalar()


def patch_cv_mapping(
    db: Session, *, mid: int, fields: dict, workspace_id: int
) -> int | None:
    use = {k: v for k, v in fields.items() if k in
           ("cv_code", "target_material_table", "target_material_id", "notes")}
    if not use:
        return mid
    sets_parts = [f"{c} = :{c}" for c in use]
    sets_parts.append("updated_at = now()")
    sql = text(
        f"UPDATE cv_material_mapping SET {', '.join(sets_parts)} "
        f"WHERE cv_material_mapping_id = :id AND workspace_id = :w "
        f"RETURNING cv_material_mapping_id"
    )
    return db.execute(sql, {**use, "id": mid, "w": workspace_id}).scalar()


def delete_cv_mapping(db: Session, *, mid: int, workspace_id: int) -> int | None:
    return db.execute(text(
        "DELETE FROM cv_material_mapping "
        "WHERE cv_material_mapping_id = :id AND workspace_id = :w "
        "RETURNING cv_material_mapping_id"
    ), {"id": mid, "w": workspace_id}).scalar()
```

- [ ] **Step 2: Commit**

```
feat(api): catalog queries — REGISTRY + workspace isolation (#7a)
```

---

##### Task 6: Routes layer (`apps/api/app/catalog/routes.py`)

**Files:**
- Create: `apps/api/app/catalog/routes.py`

7 sub-routers in one file. The pattern mirrors `apps/api/app/procurement_v1/catalogs/routes.py`. Differences from the procurement-side surface:
1. Path prefix is `/catalog` (singular), not `/catalogs`.
2. Gate is `("catalog", action)`, not `("orderbook", action)`.
3. Workspace isolation propagates through every read + write path.
4. Audit events follow `catalog.{table}.{create|update|archive|csv_import}`.
5. The 6 sub-routers use friendly URL slugs (board-materials, hardware-materials, custom-made, benchtop-materials, appliances, equipment-hire), and a small `URL_TO_TYPE` map translates back to REGISTRY keys.

**Important route-ordering caveat:** FastAPI matches `/catalog/cv-mappings` against `/catalog/{slug}` first if `{slug}` is declared earlier. Declare the literal `/catalog/cv-mappings` routes **before** the parameterised `/catalog/{slug}` routes in the file so the literal path wins.

- [ ] **Step 1: Write `routes.py`** (cv-mapping routes declared first):

```python
"""Catalog HTTP routes — sub-project #7a.

Layout:
1) /catalog/cv-mappings   (literal — must be declared first)
2) /catalog/{slug}        (parameterised — 6 material types via URL_TO_TYPE)
3) /catalog/{slug}/bulk   (literal sub-path)
4) /catalog/{slug}/{mid}/archive

All gated by ("catalog", action). Workspace isolation via
`AuthUser.workspace_id`. Mutations write `audit_log`.
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    BulkImportIn,
    BulkImportOut,
    BulkRowError,
    CreateApplianceIn,
    CreateBenchtopIn,
    CreateBoardIn,
    CreateCustomMadeIn,
    CreateCvMappingIn,
    CreateEquipmentHireIn,
    CreateHardwareIn,
    PatchApplianceIn,
    PatchBenchtopIn,
    PatchBoardIn,
    PatchCustomMadeIn,
    PatchCvMappingIn,
    PatchEquipmentHireIn,
    PatchHardwareIn,
)

router = APIRouter(tags=["catalog"])

URL_TO_TYPE: dict[str, str] = {
    "board-materials":     "board",
    "hardware-materials":  "hardware",
    "custom-made":         "custom_made",
    "benchtop-materials":  "benchtop",
    "appliances":          "appliance",
    "equipment-hire":      "hire",
}


def _resolve_type(slug: str) -> str:
    if slug not in URL_TO_TYPE:
        raise HTTPException(404, f"Unknown catalog slug: {slug}")
    return URL_TO_TYPE[slug]


# ============================================================
# CV mappings (declared FIRST so the literal path wins routing)
# ============================================================

@router.get("/catalog/cv-mappings")
def list_cv_mappings_route(
    q_search: str | None = Query(None, alias="q"),
    user: AuthUser = Depends(require_permission("catalog", "read")),
    db: Session = Depends(get_db),
):
    return q.list_cv_mappings(db, workspace_id=user.workspace_id, q=q_search)


@router.post("/catalog/cv-mappings", status_code=201)
def create_cv_mapping_route(
    body: CreateCvMappingIn,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    try:
        mid = q.create_cv_mapping(
            db, payload=body.model_dump(), actor_id=user.id, workspace_id=user.workspace_id,
        )
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"cv_code already mapped: {e.orig}")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cv_material_mapping.create",
        target=f"cv_material_mapping:{mid}",
        payload={"cv_code": body.cv_code, "target_material_table": body.target_material_table},
    )
    db.commit()
    return q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id)


@router.patch("/catalog/cv-mappings/{mid}")
def patch_cv_mapping_route(
    mid: int,
    body: PatchCvMappingIn,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    if q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Mapping not found")
    fields = body.model_dump(exclude_none=True)
    try:
        q.patch_cv_mapping(db, mid=mid, fields=fields, workspace_id=user.workspace_id)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"cv_code already mapped: {e.orig}")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cv_material_mapping.update",
        target=f"cv_material_mapping:{mid}", payload=fields,
    )
    db.commit()
    return q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id)


@router.delete("/catalog/cv-mappings/{mid}", status_code=204)
def delete_cv_mapping_route(
    mid: int,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    if q.get_cv_mapping(db, mid=mid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Mapping not found")
    q.delete_cv_mapping(db, mid=mid, workspace_id=user.workspace_id)
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="cv_material_mapping.delete",
        target=f"cv_material_mapping:{mid}",
    )
    db.commit()
    return None


# ============================================================
# Generic 6-table sub-routers
# ============================================================

@router.get("/catalog/{slug}")
def list_catalog_route(
    slug: str,
    q_search: str | None = Query(None, alias="q"),
    supplier: str | None = None,
    archived: bool = False,
    user: AuthUser = Depends(require_permission("catalog", "read")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    rows = q.list_catalog(
        db, type_=type_, workspace_id=user.workspace_id,
        q=q_search, supplier=supplier, archived=archived,
    )
    return {"type": type_, "rows": rows}


@router.post("/catalog/{slug}/bulk", response_model=BulkImportOut)
def bulk_import_route(
    slug: str,
    body: BulkImportIn,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    """All-or-nothing: validate every row first; insert only if all clean."""
    type_ = _resolve_type(slug)
    schema_cls = {
        "board": CreateBoardIn, "hardware": CreateHardwareIn,
        "custom_made": CreateCustomMadeIn, "benchtop": CreateBenchtopIn,
        "appliance": CreateApplianceIn, "hire": CreateEquipmentHireIn,
    }[type_]

    errors: list[BulkRowError] = []
    validated_rows: list[dict] = []
    for i, raw in enumerate(body.rows):
        try:
            v = schema_cls.model_validate(raw).model_dump()
        except Exception as e:
            errors.append(BulkRowError(row_index=i, error=str(e)))
            continue
        validated_rows.append(v)

    if errors:
        return BulkImportOut(created=0, errors=errors)

    created = 0
    for i, v in enumerate(validated_rows):
        try:
            q.create_catalog_row(
                db, type_=type_, fields=v, workspace_id=user.workspace_id
            )
            created += 1
        except IntegrityError as e:
            db.rollback()
            return BulkImportOut(
                created=0,
                errors=[BulkRowError(row_index=i, error=f"unique constraint: {e.orig}")],
            )

    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.csv_import", target=f"catalog.{type_}:bulk",
        payload={"created": created},
    )
    db.commit()
    return BulkImportOut(created=created, errors=[])


@router.get("/catalog/{slug}/{mid}")
def get_catalog_row_route(
    slug: str, mid: int,
    user: AuthUser = Depends(require_permission("catalog", "read")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    row = q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(404, "Catalog row not found")
    return row


@router.post("/catalog/{slug}", status_code=201)
def create_catalog_row_route(
    slug: str,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    schema_cls = {
        "board": CreateBoardIn, "hardware": CreateHardwareIn,
        "custom_made": CreateCustomMadeIn, "benchtop": CreateBenchtopIn,
        "appliance": CreateApplianceIn, "hire": CreateEquipmentHireIn,
    }[type_]
    try:
        validated = schema_cls.model_validate(payload).model_dump()
    except Exception as e:
        raise HTTPException(422, str(e))
    try:
        mid = q.create_catalog_row(
            db, type_=type_, fields=validated, workspace_id=user.workspace_id
        )
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"unique constraint: {e.orig}")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.create", target=f"catalog.{type_}:{mid}",
    )
    db.commit()
    return q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)


@router.patch("/catalog/{slug}/{mid}")
def patch_catalog_row_route(
    slug: str, mid: int,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    if q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Catalog row not found")
    schema_cls = {
        "board": PatchBoardIn, "hardware": PatchHardwareIn,
        "custom_made": PatchCustomMadeIn, "benchtop": PatchBenchtopIn,
        "appliance": PatchApplianceIn, "hire": PatchEquipmentHireIn,
    }[type_]
    try:
        validated = schema_cls.model_validate(payload).model_dump(exclude_none=True)
    except Exception as e:
        raise HTTPException(422, str(e))
    q.patch_catalog_row(
        db, type_=type_, mid=mid, fields=validated, workspace_id=user.workspace_id,
    )
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.update", target=f"catalog.{type_}:{mid}",
        payload=validated,
    )
    db.commit()
    return q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)


@router.post("/catalog/{slug}/{mid}/archive")
def archive_catalog_row_route(
    slug: str, mid: int,
    user: AuthUser = Depends(require_permission("catalog", "write")),
    db: Session = Depends(get_db),
):
    type_ = _resolve_type(slug)
    rid = q.archive_catalog_row(
        db, type_=type_, mid=mid, actor_id=user.id, workspace_id=user.workspace_id,
    )
    if rid is None:
        if q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id) is None:
            raise HTTPException(404, "Catalog row not found")
        raise HTTPException(409, "already archived")
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event=f"catalog.{type_}.archive", target=f"catalog.{type_}:{mid}",
    )
    db.commit()
    return q.get_catalog_row(db, type_=type_, mid=mid, workspace_id=user.workspace_id)
```

- [ ] **Step 2: Mount router**

In `apps/api/app/main.py`, add the import + `include_router` call (alphabetical, between `auth_router` and `files_router`):

```python
from .catalog.routes import router as catalog_router
# ...
app.include_router(catalog_router)
```

- [ ] **Step 3: Smoke-test the wiring**

```bash
docker compose restart api
docker compose exec api curl -s http://localhost:8000/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print(sorted(p for p in d['paths'] if p.startswith('/catalog')))"
```

Expected: 7 unique paths — `/catalog/cv-mappings`, `/catalog/cv-mappings/{mid}`, `/catalog/{slug}`, `/catalog/{slug}/bulk`, `/catalog/{slug}/{mid}`, `/catalog/{slug}/{mid}/archive`.

- [ ] **Step 4: Commit**

```
feat(api): catalog routes — 6 per-table CRUD + cv-mappings + bulk (#7a)
```

---

##### Task 7: Pytest — `test_catalog_routes.py`

**Files:**
- Create: `apps/api/tests/test_catalog_routes.py`

Coverage: ~25 cases. The fixture pattern mirrors `apps/api/tests/test_samples_crud.py` — every test gets its own workspace + drafter user via the `db` rollback fixture.

- [ ] **Step 1: Write tests**

Create `apps/api/tests/test_catalog_routes.py`. Test list (each test is its own function):

1. `test_list_board_materials_returns_seeded_rows` — happy-path GET.
2. `test_list_filters_by_q` — search by description substring.
3. `test_list_filters_by_supplier`.
4. `test_list_archived_false_excludes_archived` — archive a row, list w/o `archived=true`, assert it's gone.
5. `test_list_archived_true_includes_archived`.
6. `test_get_board_material_by_id_returns_synonyms` — round-trip through GIN.
7. `test_get_unknown_id_returns_404`.
8. `test_get_unknown_slug_returns_404` — `/catalog/not-a-slug/1`.
9. `test_post_board_material_creates_row_with_synonyms`.
10. `test_post_board_material_returns_409_on_duplicate_code` — UNIQUE on `(workspace_id, sku)` + legacy unique on `code`.
11. `test_post_hardware_material_with_default_supplier_and_lead_time`.
12. `test_post_equipment_hire_requires_project_id` — POST without `project_id` → 422.
13. `test_post_equipment_hire_with_project_id_succeeds`.
14. `test_patch_partial_update_only_changed_columns` — PATCH with only `default_supplier`.
15. `test_patch_synonyms_replaces_array`.
16. `test_patch_unknown_id_returns_404`.
17. `test_archive_sets_archived_at_and_archived_by`.
18. `test_archive_already_archived_returns_409`.
19. `test_archive_unknown_id_returns_404`.
20. `test_bulk_import_5_rows_all_succeed` — POST `/catalog/board-materials/bulk` with 5 valid rows; expect `{created: 5, errors: []}`.
21. `test_bulk_import_with_one_invalid_row_creates_zero` — 5 rows, one missing `description`; expect `{created: 0, errors: [{row_index: i, error: ...}]}`.
22. `test_bulk_import_writes_one_audit_row` — assert one `catalog.board.csv_import` audit row, not 5 per-row creates.
23. `test_create_writes_catalog_table_create_audit` — assert audit `event = catalog.board.create`.
24. `test_patch_writes_catalog_table_update_audit_with_payload`.
25. `test_archive_writes_catalog_table_archive_audit`.

Each test follows the pattern of `apps/api/tests/test_samples_crud.py`: create workspace + drafter user inside the rollback transaction, log in via `TestClient`, hit the route, assert response shape + DB state.

- [ ] **Step 2: Run, expect ~25 passing**

```bash
docker compose exec api pytest tests/test_catalog_routes.py -v
```

- [ ] **Step 3: Commit**

```
test(api): catalog CRUD + bulk import (#7a) — 25 cases
```

---

##### Task 8: Pytest — `test_cv_mapping_routes.py`

**Files:**
- Create: `apps/api/tests/test_cv_mapping_routes.py`

Coverage: ~10 cases.

- [ ] **Step 1: Write tests**

1. `test_list_cv_mappings_empty_workspace_returns_zero`.
2. `test_post_cv_mapping_creates_row`.
3. `test_post_cv_mapping_duplicate_code_returns_409` — same `(workspace_id, cv_code)` twice.
4. `test_post_cv_mapping_with_invalid_target_table_returns_422` — `target_material_table='not_a_table'`.
5. `test_get_cv_mapping_returns_target_description` — verify the CASE-correlated description join populates `target_description`.
6. `test_patch_cv_mapping_repoints_to_new_target`.
7. `test_patch_cv_mapping_unknown_id_returns_404`.
8. `test_delete_cv_mapping_hard_deletes`.
9. `test_delete_cv_mapping_unknown_id_returns_404`.
10. `test_create_writes_audit_event_cv_material_mapping_create`.

- [ ] **Step 2: Run + commit**

```
test(api): cv_material_mapping CRUD (#7a) — 10 cases
```

---

##### Task 9: Pytest — `test_catalog_workspace_isolation.py`

**Files:**
- Create: `apps/api/tests/test_catalog_workspace_isolation.py`

Coverage: ~6 cases. Two-workspace fixture for cross-workspace 404 verification.

- [ ] **Step 1: Write tests**

1. `test_list_board_materials_excludes_other_workspace_rows`.
2. `test_get_board_material_in_other_workspace_returns_404`.
3. `test_patch_board_material_in_other_workspace_returns_404`.
4. `test_archive_board_material_in_other_workspace_returns_404`.
5. `test_list_cv_mappings_excludes_other_workspace_rows`.
6. `test_post_cv_mapping_in_my_workspace_does_not_collide_with_other_workspace_same_cv_code` — UNIQUE is `(workspace_id, cv_code)`, not just `cv_code`.

- [ ] **Step 2: Run + commit**

```
test(api): catalog workspace isolation (#7a) — 6 cases
```

---

#### Phase 3 — Web layer (5 tasks)

##### Task 10: Lib helpers (`catalog-types.ts` + `catalog-fetch.ts`)

**Files:**
- Create: `apps/web/lib/catalog-types.ts`
- Create: `apps/web/lib/catalog-fetch.ts`

- [ ] **Step 1: Write `catalog-types.ts`**

```typescript
export type CatalogTable =
  | "board_materials"
  | "hardware_materials"
  | "custom_made"
  | "benchtop_materials"
  | "appliances"
  | "equipment_hire";

export type CatalogSlug =
  | "board-materials"
  | "hardware-materials"
  | "custom-made"
  | "benchtop-materials"
  | "appliances"
  | "equipment-hire";

export interface CatalogRow {
  type: string;
  material_id?: number;
  hire_id?: number;
  workspace_id: number;
  sku: string;
  description: string;
  // Per-table legacy unique columns
  code?: string | null;
  internal_ref?: string | null;
  slab_id?: string | null;
  model_number?: string | null;
  contract_ref?: string | null;
  project_id?: number | null;
  // Enrichment
  synonyms: string[];
  default_supplier: string | null;
  default_lead_time_days: number | null;
  archived_at: string | null;
  archived_by: number | null;
}

export interface CatalogListResp {
  type: string;
  rows: CatalogRow[];
}

export interface BulkImportResp {
  created: number;
  errors: { row_index: number; error: string }[];
}

export interface CvMapping {
  cv_material_mapping_id: number;
  workspace_id: number;
  cv_code: string;
  target_material_table: CatalogTable;
  target_material_id: number;
  target_description: string | null;
  notes: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface CvMappingListResp {
  rows: CvMapping[];
  total: number;
}
```

- [ ] **Step 2: Write `catalog-fetch.ts`**

```typescript
import type {
  BulkImportResp,
  CatalogListResp,
  CatalogRow,
  CatalogSlug,
  CvMapping,
  CvMappingListResp,
} from "./catalog-types";

const headers = { "Content-Type": "application/json" };

export async function listCatalog(args: {
  slug: CatalogSlug;
  q?: string | null;
  supplier?: string | null;
  archived?: boolean;
}): Promise<CatalogListResp> {
  const sp = new URLSearchParams();
  if (args.q) sp.set("q", args.q);
  if (args.supplier) sp.set("supplier", args.supplier);
  if (args.archived) sp.set("archived", "true");
  const url = `/api/catalog/${args.slug}${sp.size ? `?${sp.toString()}` : ""}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`listCatalog: ${res.status}`);
  return res.json();
}

export async function createRow(slug: CatalogSlug, body: Record<string, unknown>): Promise<CatalogRow> {
  const res = await fetch(`/api/catalog/${slug}`, {
    method: "POST", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createRow: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function patchRow(slug: CatalogSlug, mid: number, body: Record<string, unknown>): Promise<CatalogRow> {
  const res = await fetch(`/api/catalog/${slug}/${mid}`, {
    method: "PATCH", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patchRow: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function archiveRow(slug: CatalogSlug, mid: number): Promise<CatalogRow> {
  const res = await fetch(`/api/catalog/${slug}/${mid}/archive`, {
    method: "POST", credentials: "include",
  });
  if (!res.ok) throw new Error(`archiveRow: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function bulkImport(slug: CatalogSlug, rows: Record<string, unknown>[]): Promise<BulkImportResp> {
  const res = await fetch(`/api/catalog/${slug}/bulk`, {
    method: "POST", credentials: "include", headers, body: JSON.stringify({ rows }),
  });
  if (!res.ok) throw new Error(`bulkImport: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function listCvMappings(q?: string | null): Promise<CvMappingListResp> {
  const url = q ? `/api/catalog/cv-mappings?q=${encodeURIComponent(q)}` : "/api/catalog/cv-mappings";
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`listCvMappings: ${res.status}`);
  return res.json();
}

export async function createCvMapping(body: {
  cv_code: string;
  target_material_table: string;
  target_material_id: number;
  notes?: string | null;
}): Promise<CvMapping> {
  const res = await fetch("/api/catalog/cv-mappings", {
    method: "POST", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createCvMapping: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function patchCvMapping(mid: number, body: Record<string, unknown>): Promise<CvMapping> {
  const res = await fetch(`/api/catalog/cv-mappings/${mid}`, {
    method: "PATCH", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patchCvMapping: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function deleteCvMapping(mid: number): Promise<void> {
  const res = await fetch(`/api/catalog/cv-mappings/${mid}`, {
    method: "DELETE", credentials: "include",
  });
  if (!res.ok) throw new Error(`deleteCvMapping: ${res.status}`);
}
```

- [ ] **Step 3: Commit**

```
feat(web): catalog lib types + fetch wrappers (#7a)
```

---

##### Task 11: `/catalog` page shell + tabs + grid

**Files:**
- Create: `apps/web/app/(app)/catalog/page.tsx`
- Create: `apps/web/app/(app)/catalog/_components/CatalogClient.tsx`
- Create: `apps/web/app/(app)/catalog/_components/CatalogTabs.tsx`
- Create: `apps/web/app/(app)/catalog/_components/CatalogFilters.tsx`
- Create: `apps/web/app/(app)/catalog/_components/CatalogGrid.tsx`
- Create: `apps/web/app/(app)/catalog/_components/CatalogRow.tsx`
- Create: `apps/web/app/(app)/catalog/_components/NewCatalogRowDialog.tsx`

The page mirrors `apps/web/app/(app)/isample/page.tsx` (server wrapper that fetches `me` + projects, then defers to a client component owning URL state).

> **Note:** This Next.js codebase ships breaking changes from older versions (per `apps/web/AGENTS.md`). Before editing any page, consult `node_modules/next/dist/docs/` for current API conventions.

- [ ] **Step 1: `page.tsx`**

```tsx
import { redirect } from "next/navigation";
import { fetchMe } from "@/lib/session";
import CatalogClient from "./_components/CatalogClient";

interface PageProps {
  searchParams: Promise<{
    tab?: string;
    q?: string;
    supplier?: string;
    archived?: string;
    project?: string;  // for equipment-hire only
  }>;
}

const VALID_TABS = [
  "board", "hardware", "custom", "benchtop",
  "appliances", "equipment_hire", "cv-mappings",
] as const;

export default async function Page({ searchParams }: PageProps) {
  const sp = await searchParams;
  const me = await fetchMe();
  if (!me) redirect("/login");

  const tab = (VALID_TABS as readonly string[]).includes(sp.tab ?? "")
    ? (sp.tab as (typeof VALID_TABS)[number])
    : "board";

  return (
    <CatalogClient
      me={me}
      initialTab={tab}
      initialQ={sp.q ?? null}
      initialSupplier={sp.supplier ?? null}
      initialArchived={sp.archived === "true"}
      initialProjectId={sp.project ? Number(sp.project) : null}
    />
  );
}
```

- [ ] **Step 2: `CatalogClient.tsx`** — owns URL state, dispatches to either `<CatalogGrid slug={...} />` or `<MappingPanel />` based on tab. Re-uses the URL-state pattern from `ISampleClient.tsx`.

- [ ] **Step 3: `CatalogTabs.tsx`** — 7 tab buttons, current tab highlighted via `bg-h-surface text-h-ink border-h-line`. URL link: `/catalog?tab={key}`.

- [ ] **Step 4: `CatalogFilters.tsx`** — search input (200ms debounce → URL update), supplier select (populated from current tab's distinct supplier set), archived toggle.

- [ ] **Step 5: `CatalogGrid.tsx`** — renders rows in a table layout (Description, SKU, Legacy-unique-col, Default supplier, Lead time, Synonyms, Updated). Inline-edit on cell click → contenteditable or input → blur fires `patchRow`. Synonyms cell shows a comma-joined input (split on `,` on save).

- [ ] **Step 6: `CatalogRow.tsx`** — one `<tr>`. Local state per cell. On blur, if changed, call `patchRow` and update parent state via callback.

- [ ] **Step 7: `NewCatalogRowDialog.tsx`** — modal form. Per-tab field set: every tab has `description`, `sku`, `default_supplier`, `default_lead_time_days`, `synonyms` (comma-input). Plus the legacy-unique field per tab (`code` for board, `internal_ref` for custom_made, etc.). Equipment-hire adds a project picker.

- [ ] **Step 8: Visual smoke-test**

```bash
make up
# log in as Noa Lindqvist (drafter)
# navigate to /catalog
# confirm: 7 tabs render; "Board" tab is selected; grid lists 6 board_materials rows
# inline-edit a description cell; blur; F5; the change persists
# click "+ New" → fill form → save; new row appears at top
```

- [ ] **Step 9: Commit**

```
feat(web): /catalog page shell + tabs + grid + inline-edit (#7a)
```

---

##### Task 12: Bulk import dialog

**Files:**
- Create: `apps/web/app/(app)/catalog/_components/CatalogBulkImportDialog.tsx`

The dialog accepts either a file picker (`<input type="file" accept=".csv">`) or a textarea paste. It parses client-side using `String.split('\n')` + simple comma-tokeniser (no PapaParse — keep it dep-free). The first non-blank line is the header; subsequent lines are data rows. Each row is sent as a single dict to the server.

- [ ] **Step 1: Write the dialog**

```tsx
"use client";

import { useState } from "react";
import { bulkImport } from "@/lib/catalog-fetch";
import type { BulkImportResp, CatalogSlug } from "@/lib/catalog-types";

interface Props {
  slug: CatalogSlug;
  onClose: () => void;
  onCommitted: (resp: BulkImportResp) => void;
}

function parseCsv(text: string): { headers: string[]; rows: Record<string, string>[] } {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return { headers: [], rows: [] };
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(",").map((c) => c.trim());
    const r: Record<string, string> = {};
    headers.forEach((h, i) => (r[h] = cells[i] ?? ""));
    return r;
  });
  return { headers, rows };
}

export default function CatalogBulkImportDialog(p: Props) {
  const [csvText, setCsvText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const parsed = parseCsv(csvText);

  const buildRows = (): Record<string, unknown>[] =>
    parsed.rows.map((r) => {
      const out: Record<string, unknown> = { ...r };
      if (out.synonyms != null && typeof out.synonyms === "string") {
        out.synonyms = (out.synonyms as string).split(/\s*\|\s*/).filter(Boolean);
      }
      if (out.default_lead_time_days != null && out.default_lead_time_days !== "") {
        out.default_lead_time_days = Number(out.default_lead_time_days);
      } else {
        delete out.default_lead_time_days;
      }
      if (out.project_id != null && out.project_id !== "") {
        out.project_id = Number(out.project_id);
      }
      return out;
    });

  const onFile = async (f: File | null) => {
    if (!f) return;
    setCsvText(await f.text());
  };

  const onSubmit = async () => {
    setBusy(true); setErr(null);
    try {
      const resp = await bulkImport(p.slug, buildRows());
      p.onCommitted(resp);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 grid place-items-center">
      <div className="bg-h-surface text-h-ink p-6 rounded-md w-[640px] max-h-[80vh] overflow-auto">
        <h2 className="text-lg font-semibold mb-3">Bulk import — {p.slug}</h2>
        <input type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
        <textarea
          className="w-full h-32 border border-h-line p-2 mt-2 font-mono text-xs"
          placeholder="header1,header2,...\nval,val,..."
          value={csvText}
          onChange={(e) => setCsvText(e.target.value)}
        />
        {parsed.headers.length > 0 && (
          <div className="text-xs text-h-muted mt-2">
            Detected {parsed.rows.length} rows · headers: {parsed.headers.join(", ")}
          </div>
        )}
        {err && <div className="text-xs text-red-500 mt-2">{err}</div>}
        <div className="flex gap-2 mt-4">
          <button onClick={p.onClose} className="px-3 py-1 border border-h-line">Cancel</button>
          <button
            onClick={onSubmit}
            disabled={busy || parsed.rows.length === 0}
            className="px-3 py-1 bg-h-accent text-white"
          >
            {busy ? "Importing…" : `Import ${parsed.rows.length} rows`}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire the trigger button into `CatalogGrid.tsx`** — toolbar adds a "Bulk import" button alongside "+ New". On commit, parent re-fetches the list and shows a toast (or alert) with `created`/`errors` counts.

- [ ] **Step 3: Commit**

```
feat(web): catalog bulk import dialog — paste/file CSV (#7a)
```

---

##### Task 13: Mappings panel

**Files:**
- Create: `apps/web/app/(app)/catalog/_components/MappingPanel.tsx`
- Create: `apps/web/app/(app)/catalog/_components/NewMappingDialog.tsx`
- Modify: `apps/web/components/chrome/SideBar.tsx`

When `tab=cv-mappings`, `CatalogClient` renders `<MappingPanel />` instead of `<CatalogGrid />`. The panel is a simpler grid: `cv_code`, `target_material_table`, `target_description` (joined), `notes`, `Updated`, plus a Delete button per row and a "+ New mapping" button.

- [ ] **Step 1: Write `MappingPanel.tsx`** — plain table; row click reveals an edit form (same shape as the new-mapping dialog but pre-filled).

- [ ] **Step 2: Write `NewMappingDialog.tsx`** — fields: `cv_code` (text), `target_material_table` (select with 6 options), `target_material_id` (typeahead — fetches `/catalog/{slug}` and shows description; commits the chosen `material_id` or `hire_id`), `notes` (textarea).

The typeahead is the only non-trivial piece. Since #7a is single-workspace, the typeahead can fetch the full list once per table and filter client-side (catalogs are O(100s of rows), not millions).

- [ ] **Step 3: SideBar entry**

In `apps/web/components/chrome/SideBar.tsx`, add a "Catalog" link visible to anyone with `catalog.read` (i.e. all roles except `it_management`-only). Slot below Orderbook.

- [ ] **Step 4: Smoke-test**

```bash
# log in as Noa
# /catalog?tab=cv-mappings
# click "+ New mapping" → cv_code="18-PB-TEST" → table=board_materials → pick "18mm Particleboard White" → save
# row appears
# click delete → row disappears
```

- [ ] **Step 5: Commit**

```
feat(web): /catalog cv-mappings subtab + sidebar entry (#7a)
```

---

#### Phase 4 — Seed + e2e + docs (2 tasks)

##### Task 14: Seed extension

**Files:**
- Modify: `seed/hartwood_joinery.py`

Per spec §9, only the catalog enrichment + 2 cv_material_mapping rows belong in #7a. CV import + cut_plan + cut_schedule rows are deferred to #7b/#7c.

- [ ] **Step 1: Find the existing board + hardware seed block**

Read `seed/hartwood_joinery.py` to locate where `board_materials` and `hardware_materials` rows are inserted.

- [ ] **Step 2: Enrich existing rows + add new ones**

After the existing material inserts, add an idempotent block:

```python
def seed_catalog_enrichment(db, workspace_id):
    """Sub-project #7a: enrich existing rows + add 4 demo board_materials +
    2 cv_material_mapping rows. Idempotent."""
    # Enrich existing 2 board_materials
    db.execute(text("""
        UPDATE board_materials
           SET synonyms = ARRAY['18-PB','18mm PB','PB-18'],
               default_supplier = 'Laminex Australia',
               default_lead_time_days = 5
         WHERE workspace_id = :w AND code = '18-PB'
    """), {"w": workspace_id})
    db.execute(text("""
        UPDATE board_materials
           SET synonyms = ARRAY['25-MDF','MDF-25','25mm MDF'],
               default_supplier = 'Laminex Australia',
               default_lead_time_days = 7
         WHERE workspace_id = :w AND code = '25-MDF'
    """), {"w": workspace_id})

    # Enrich existing hardware_materials (4 rows)
    db.execute(text("""
        UPDATE hardware_materials
           SET synonyms = ARRAY['blum-runner','blum 700','runner-700'],
               default_supplier = 'Blum Australia',
               default_lead_time_days = 14
         WHERE workspace_id = :w AND sku = '700.0KC2.054.00'
    """), {"w": workspace_id})
    # ... similar UPDATEs for the other 3 hardware rows.

    # 4 new board_materials demo rows
    NEW_BOARDS = [
        {"code": "19-MELAMINE-WHITE", "sku": "MEL-19-WH",
         "description": "19mm Melamine White",
         "synonyms": ["19-WH-MEL", "Melamine 19 White"],
         "default_supplier": "Laminex Australia", "default_lead_time_days": 5},
        {"code": "16-BLACK", "sku": "MEL-16-BK",
         "description": "16mm Melamine Black",
         "synonyms": ["16-BK", "Black 16"],
         "default_supplier": "Laminex Australia", "default_lead_time_days": 5},
        {"code": "19-WALNUT", "sku": "VEN-19-WAL",
         "description": "19mm Walnut Veneer",
         "synonyms": ["19-WAL", "Walnut Veneer"],
         "default_supplier": "Briggs Veneers", "default_lead_time_days": 21},
        {"code": "12-BIRCH-PLY", "sku": "PLY-12-BIR",
         "description": "12mm Birch Plywood",
         "synonyms": ["12-PLY-BIR", "Birch 12"],
         "default_supplier": "Plyco", "default_lead_time_days": 10},
    ]
    for r in NEW_BOARDS:
        db.execute(text("""
            INSERT INTO board_materials
              (workspace_id, code, sku, description,
               synonyms, default_supplier, default_lead_time_days)
            VALUES (:w, :code, :sku, :desc, :syn, :sup, :lt)
            ON CONFLICT (workspace_id, sku) DO NOTHING
        """), {
            "w": workspace_id, "code": r["code"], "sku": r["sku"],
            "desc": r["description"], "syn": r["synonyms"],
            "sup": r["default_supplier"], "lt": r["default_lead_time_days"],
        })

    # 2 cv_material_mapping demo rows
    drafter_id = db.execute(text("""
        SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'drafter' LIMIT 1
    """), {"w": workspace_id}).scalar()
    pb_mid = db.execute(text("""
        SELECT material_id FROM board_materials WHERE workspace_id = :w AND code = '18-PB'
    """), {"w": workspace_id}).scalar()
    blum_mid = db.execute(text("""
        SELECT material_id FROM hardware_materials WHERE workspace_id = :w AND sku = '700.0KC2.054.00'
    """), {"w": workspace_id}).scalar()
    db.execute(text("""
        INSERT INTO cv_material_mapping
          (workspace_id, cv_code, target_material_table, target_material_id, created_by)
        VALUES (:w, '18-PB', 'board_materials', :tid, :u)
        ON CONFLICT (workspace_id, cv_code) DO NOTHING
    """), {"w": workspace_id, "tid": pb_mid, "u": drafter_id})
    db.execute(text("""
        INSERT INTO cv_material_mapping
          (workspace_id, cv_code, target_material_table, target_material_id, created_by)
        VALUES (:w, '700.0KC2.054.00', 'hardware_materials', :tid, :u)
        ON CONFLICT (workspace_id, cv_code) DO NOTHING
    """), {"w": workspace_id, "tid": blum_mid, "u": drafter_id})

    db.commit()
```

Update the seed file's "what gets seeded" docstring at the top to add: `"6 board_materials · 4 hardware (enriched) · 2 cv_mappings"`.

- [ ] **Step 3: Wire it into the seed entry point**

Call `seed_catalog_enrichment(db, workspace_id)` after the existing material seeds.

- [ ] **Step 4: Re-seed and verify**

```bash
make seed
docker compose exec -T db psql -U jf -d joineryflow -c "SELECT code, default_supplier, synonyms FROM board_materials ORDER BY material_id;"
docker compose exec -T db psql -U jf -d joineryflow -c "SELECT cv_code, target_material_table, target_material_id FROM cv_material_mapping;"
```

Expected: 6 board rows, 2 mapping rows.

- [ ] **Step 5: Run twice to confirm idempotency**

```bash
make seed && make seed
```

Expected: same row counts; no constraint violations.

- [ ] **Step 6: Commit**

```
feat(seed): catalog enrichment + 2 cv_material_mapping rows (#7a)
```

---

##### Task 15: Playwright e2e + CLAUDE.md

**Files:**
- Create: `tests/e2e/catalog.spec.ts`
- Modify: `CLAUDE.md`

Per spec §10.2 plus the "Scenario D: Drafter edits catalog" entry.

- [ ] **Step 1: Write `tests/e2e/catalog.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";

const DEV_USER = "noa.lindqvist@hartwood.test";
const DEV_PASS = "hartwood-dev";

test.describe("catalog (#7a)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[name="email"]', DEV_USER);
    await page.fill('input[name="password"]', DEV_PASS);
    await page.click('button[type="submit"]');
    await page.waitForURL("**/home");
  });

  test("drafter creates a board material and sees it in the grid", async ({ page }) => {
    await page.goto("/catalog?tab=board");
    await page.click('button:has-text("+ New")');
    await page.fill('input[name="code"]', "TEST-99");
    await page.fill('input[name="sku"]', "TEST-99-SKU");
    await page.fill('input[name="description"]', "E2E test board");
    await page.fill('input[name="default_supplier"]', "Test Supplier Pty");
    await page.fill('input[name="default_lead_time_days"]', "9");
    await page.click('button:has-text("Save")');
    await expect(page.locator('td:has-text("E2E test board")')).toBeVisible();
  });

  test("drafter inline-edits a cell", async ({ page }) => {
    await page.goto("/catalog?tab=board");
    const cell = page.locator('td[data-field="default_supplier"]').first();
    await cell.click();
    await cell.fill("Edited Supplier");
    await cell.blur();
    await page.reload();
    await expect(page.locator('td:has-text("Edited Supplier")').first()).toBeVisible();
  });

  test("drafter archives a row", async ({ page }) => {
    await page.goto("/catalog?tab=board");
    const archiveBtn = page.locator('button[aria-label="archive"]').first();
    const sku = await page.locator('td[data-field="sku"]').first().innerText();
    await archiveBtn.click();
    await expect(page.locator(`td:has-text("${sku}")`)).not.toBeVisible();
    await page.click('input[name="archived"]');
    await expect(page.locator(`td:has-text("${sku}")`)).toBeVisible();
  });

  test("drafter creates a cv mapping", async ({ page }) => {
    await page.goto("/catalog?tab=cv-mappings");
    await page.click('button:has-text("+ New mapping")');
    await page.fill('input[name="cv_code"]', "E2E-CV-CODE");
    await page.selectOption('select[name="target_material_table"]', "board_materials");
    await page.click('li:has-text("18mm Particleboard White")');
    await page.click('button:has-text("Save")');
    await expect(page.locator('td:has-text("E2E-CV-CODE")')).toBeVisible();
  });
});
```

- [ ] **Step 2: Run e2e**

```bash
make e2e-docker
```

Expected: all 4 catalog scenarios pass alongside existing specs.

- [ ] **Step 3: Update `CLAUDE.md`**

Append a new subsection after the iSample one:

```markdown
## Catalog enrichment + CV Mappings (sub-project #7a)

- New backend module `apps/api/app/catalog/` mounted at `/catalog/*` (singular,
  not the existing procurement-side `/catalogs/*`). 7 sub-routers: 6 per
  material type plus `/catalog/cv-mappings`. RBAC gate `("catalog", action)`.
- Migration 0017 adds 5 enrichment columns (`synonyms text[]`,
  `default_supplier`, `default_lead_time_days`, `archived_at`, `archived_by`)
  to all 6 catalog tables, plus a GIN index on `synonyms` and a partial active
  index. Also CREATEs `cv_material_mapping` (workspace-scoped UNIQUE on
  `(workspace_id, cv_code)`).
- New `catalog` row in the RBAC matrix. Drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`;
  purchase_officer `{read,comment}`; viewer `{read}`.
- Soft-archive only — POST `/catalog/{slug}/{mid}/archive` sets
  `archived_at`+`archived_by`; 409 on already-archived. Hard delete is
  reserved for `cv_material_mapping`.
- Bulk import is all-or-nothing. POST `/catalog/{slug}/bulk` validates every
  row first; if any row fails Pydantic, returns `{created: 0, errors: [...]}`
  without inserting. Audit: one `catalog.{table}.csv_import` row per import
  (not per row).
- Web routes:
  - `/catalog?tab=board|hardware|custom|benchtop|appliances|equipment_hire|cv-mappings`
  - SideBar entry visible to all roles with `catalog.read`.
- Workspace isolation enforced on every read + write via `workspace_id`
  column (already on the 6 catalog tables from migration 0007;
  added to `cv_material_mapping` by 0017).
- Route ordering caveat: cv-mapping routes are declared before
  `/catalog/{slug}` in `routes.py` so the literal path wins.
- The procurement-side `/catalogs/*` (plural) module at
  `apps/api/app/procurement_v1/catalogs/` is **not** retired by #7a — it
  remains the auth path the procurement queue depends on. The two surfaces
  will converge in a future cleanup.
- Out of scope (deferred to #7b): `cv_import_run`, the Cutlist tab CV
  import wizard, the synonym-fuzzy resolver. (Deferred to #7c): Board tab,
  `/cut-floor` page, CutPlan, CutSchedule.
```

Add a corresponding entry in the "Reference docs" section of CLAUDE.md:

```markdown
- `docs/archive/2026-05-05-cabinet-vision.md` — Cabinet Vision Integration spec (sub-projects #7a + #7b + #7c).
- `docs/archive/2026-05-05-cabinet-vision.md` — 15-task implementation plan for sub-project #7a.
```

- [ ] **Step 4: Final pytest + e2e + docker compose ps sanity**

```bash
docker compose exec api pytest -q
make e2e-docker
docker compose ps
```

Expected: all green. New pytest count = baseline + ~46 (25 catalog + 10 mapping + 6 isolation + 5 permissions).

- [ ] **Step 5: Commit**

```
feat(e2e): catalog happy-path spec + CLAUDE.md notes (#7a)
```

---

#### Definition of done

- [ ] Migration `0017_catalog_enrichment.py` applied; `\d+ board_materials` etc. show 5 new columns; `\d+ cv_material_mapping` shows the table.
- [ ] `apps/api/app/auth/permissions.py` has `catalog` in `Module` + `_ALL_MODULES` + per-role rows.
- [ ] `apps/api/app/catalog/{schemas,queries,routes}.py` exist; `main.py` mounts `catalog_router`.
- [ ] `apps/api/tests/test_catalog_routes.py` (~25), `test_cv_mapping_routes.py` (~10), `test_catalog_workspace_isolation.py` (~6), and 5 new `test_permissions.py` cases all pass.
- [ ] `apps/api/tests/conftest.py` includes `cv_material_mapping` in `TRUNCATE_TABLES`.
- [ ] Web `/catalog?tab=...` page renders; 7 tabs visible; inline-edit works; bulk-import dialog accepts paste + file; Mappings subtab CRUD works; SideBar shows the entry.
- [ ] `seed/hartwood_joinery.py` enriches existing rows + adds 4 new boards + 2 cv mappings; running `make seed` twice is idempotent.
- [ ] `tests/e2e/catalog.spec.ts` passes via `make e2e-docker`.
- [ ] CLAUDE.md has the "Catalog enrichment + CV Mappings (sub-project #7a)" subsection.
- [ ] Audit events firing on real requests:
  - [ ] `catalog.{board|hardware|custom_made|benchtop|appliance|hire}.create` on POST
  - [ ] `catalog.{table}.update` on PATCH
  - [ ] `catalog.{table}.archive` on archive POST
  - [ ] `catalog.{table}.csv_import` on bulk POST
  - [ ] `cv_material_mapping.create` / `.update` / `.delete`
- [ ] Cross-workspace 404s verified manually (log in as a second-workspace drafter; visit `/api/catalog/board-materials/{mid}` of an ALF-001 row → 404).
- [ ] No regressions: existing pytest count + new tests = green; existing e2e specs (`smoke`, `pm_workbench`, `drafter_editor`, `isample`) all pass.

---

#### Risks + mitigations recap

| Risk | Mitigation |
|---|---|
| Per-table column-shape divergence | REGISTRY dict + per-slug Pydantic schema in routes.py |
| equipment_hire requires project_id | dedicated `CreateEquipmentHireIn` schema + UI project picker on that tab only |
| Procurement /catalogs/* still in use | New `/catalog/*` (singular) is parallel; do NOT rewire procurement queue |
| GIN index migration time | Acceptable on a fresh seed; add now to keep #7b cheap |
| Workspace isolation regression | `test_catalog_workspace_isolation.py` covers every sub-router |
| Route ordering trap on `/catalog/{slug}` vs `/catalog/cv-mappings` | Declare cv-mappings routes before parameterised slug routes in `routes.py` |
| Inline-edit blur-spam (one PATCH per blur) | Acceptable for v1 — workspace catalog is small; add debounce only if QA flags |
| Bulk-import 1000-row cap (Pydantic Field max_length) | Documented in schema; UI surfaces the limit before submit |

---

#### Out-of-band follow-ups (deferred to #7b/#7c)

- **#7b — CV Import wizard:** migration 0018 (`cv_import_run`), `apps/api/app/cv/{routes,queries,parser,resolver,schemas}.py`, the 3-phase preview/commit dialog inside the Cutlist tab, the Phase B unknown-codes UI that auto-writes new `cv_material_mapping` rows on resolve. Depends on #7a's `cv_material_mapping` register + `synonyms[]` columns.
- **#7c — CutPlan / CutSchedule + Board tab:** migration 0019 (`part_slot.part_id`, `cut_schedule` enrichment, `cut_plan` metadata), `apps/api/app/cut_floor/`, the `/cut-floor` page, the Drafter Editor Board tab, the `cut_floor` RBAC module. Independent of #7a/#7b mechanically; sequenced after for review bandwidth.
- **Procurement-side `/catalogs/*` retirement:** future cleanup pass to converge the two parallel catalog surfaces. Not blocked by #7a.

**End of plan.**


## Implementation plan — 7b CV import

### JoineryFlow CV Import Wizard Implementation Plan

> **Status: shipped.** Migration `0018`. Current state lives in
> `## CV Import wizard (sub-project #7b)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/archive/README.md`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Date:** 2026-05-05
**Sub-project:** #7b — CV Import wizard (the second slice of #7 Cabinet Vision Integration)
**Spec:** `docs/archive/2026-05-05-cabinet-vision.md` — read §1 (scope items 1, 4, 8), §2.1 (backend layout — `apps/api/app/cv/`), §3.1 (`cv_import_run`), §4.2 (CV import routes), §5 (RBAC — `cut_floor` row), §6 (CSV import workflow detail end-to-end), §7.2 (Cutlist tab Import dialog), §8 (migration 0018 portion only), §9 (seed updates limited to cv_import_run + import demo), §10.1 (test plan — `test_cv_parser.py`, `test_cv_resolver.py`, `test_cv_routes.py`).
**Branch base:** `feat/foundation` after #7a merge (HEAD `83fe558`; latest migration on disk is `0017_catalog_enrichment.py`).
**Baseline:** 334 passed, 1 skipped, 0 failed (verified 2026-05-07).

---

#### Goal

Ship the **CV CSV import wizard** that turns a Cabinet Vision part-list export into Modules + Parts under a Drafter Editor item, in one transaction, with a 3-phase preview / resolve / commit UX. By the end of this slice, a Drafter (or any drafter+/manager+/admin) can:

1. Open `/items/{id}?tab=cutlist`, click **"Import from CV"** in the Cutlist toolbar.
2. **Phase A (Upload):** Paste CSV text *or* pick a file ≤ 1 MB, click **Preview**. Backend parses headers, normalises rows, resolves every `material_code` through `cv_material_mapping` → catalog `synonyms[]` → catalog `sku`, and returns a `CvPreviewOut` payload listing every row classified as `mapped` / `synonym_match` / `unknown` / `invalid`. A `cv_import_run` row with `status='preview'` is persisted.
3. **Phase B (Resolve unknowns):** UI lists every `unknown` row with three inline actions — **Use existing** (typeahead across all 6 catalog tables), **Create new** (5 simple tables only — equipment_hire disabled with a tooltip linking to `/catalog`), **Skip**. Picks of "Use existing" auto-write a `cv_material_mapping` row on commit.
4. **Phase C (Commit):** Confirmation panel "Import {n} parts in {m} modules under Item ALF-001-ITEM-1." When the item already has modules, the panel shows a **"Replace existing modules"** checkbox; unchecked + existing data → 409, checked → wipes modules (CASCADE) before commit. On commit, single transaction: insert new catalog rows from "Create new" picks, write `cv_material_mapping` rows for each "Use existing" pick, insert Modules + Parts, set `cv_import_run.status='committed'`, write audit + item_edit_log.
5. View import history via `GET /items/{iid}/cv-imports` (rendered later in #7c — for #7b the route exists but is consumed only by tests).

#7b does **not** ship: catalog enrichment / Mappings UI (already in #7a), CutPlan / CutSchedule / Board tab / `/cut-floor` page (deferred to **#7c**), bin-packing optimiser (indefinite), three-way merge re-import UI (indefinite), Cabinet Vision API integration (indefinite — CV is closed).

---

#### Outcome

- One DB migration (`0018_cv_import.py`) creates `cv_import_run` per spec §3.1 with the two indexes (`idx_cv_import_run_item`, `idx_cv_import_run_status`).
- One new `cut_floor` module is added to the RBAC matrix in `apps/api/app/auth/permissions.py`. Drafter / manager / admin get `{read, write, approve, comment}`. Editor gets `{read, write, comment}`. Purchase officer gets `{read}`. Viewer gets `{read}`. (Spec §5.) #7b adds the row, ships **no** UI for `cut_floor` yet — the row is consumed only by the CV import routes here, then reused by #7c without redeclaration.
- One new backend module `apps/api/app/cv/` (parser + resolver + queries + routes + schemas) — 4 routes wired into `apps/api/app/main.py` after the catalog router.
- One new client component `CvImportDialog.tsx` mounted in the Cutlist tab toolbar, plus a small `UnknownCodeRow.tsx` and `CreateCatalogRowMiniForm.tsx`. URL state: `/items/{id}?tab=cutlist&import=cv` opens the dialog deep-linkably.
- Seed extension: adds 1 demo `cv_import_run` (committed) on ALF-001 item 1. Idempotent.
- Tests: `test_cv_parser.py` (~10 cases), `test_cv_resolver.py` (~8 cases), `test_cv_routes.py` (~15 cases), and 5 new `cut_floor`-row entries appended to `test_permissions.py`. Plus a Playwright `tests/e2e/cv_import.spec.ts` happy-path (Scenario A from spec §10.2).
- CLAUDE.md gets a new "CV Import wizard (sub-project #7b)" subsection mirroring the prior sub-project entries.

#### Risks

- **Unknown vs. invalid classification ambiguity.** A row with a mistyped numeric (`len_mm = "abc"`) AND an unknown `material_code` is classified as `invalid` — invalid wins. The parser produces structured errors first; the resolver only sees rows that parsed cleanly. Mitigation: parser returns `(parsed_parts, errors, row_count)`; the resolver is a pure function over the parsed-parts stream.
- **Phase B "Create new" mini-form scope creep.** Each of the 5 simple catalog tables has slightly different required columns (`board_materials.code`, `custom_made.internal_ref`, `benchtop_materials.slab_id`, `appliances.model_number`, `hardware_materials.sku`). Mitigation: the mini-form auto-derives the legacy NOT NULL UNIQUE column from the entered `sku` (mirrors the catalog routes' insert behaviour). `equipment_hire` requires a `project_id` FK and is *disabled* in the mini-form — the row text says **"Open `/catalog` to add an Equipment Hire row, then return."**
- **Preview snapshot storage location.** Per spec §6.4 the full `CvPreviewOut` lives in `cv_import_run.error_log['_preview_snapshot']`. This conflates "errors" with "preview cache" but matches the spec; the column name is misleading rather than the schema being wrong. We keep the spec wording. (Future cleanup: rename column to `state_snapshot jsonb` after #7c.)
- **Re-import 409 semantics.** Default behaviour: 409 if the item already has any modules or parts. `?mode=replace` wipes via DELETE-CASCADE. The web confirm dialog shows the "Replace existing modules" checkbox **only when** the preview detects the item has existing modules, so the drafter cannot accidentally wipe. The check is evaluated server-side, not client-side, on every commit.
- **CSV size cap = 1 MB / 10 000 logical rows.** A real Hartwood item rarely exceeds 100 parts; 1 MB is generous. Files above the cap return 415 with `code=FILE_TOO_LARGE`. Counted *before* parsing to avoid OOM.
- **`cut_floor` module landing in #7b before its UI ships in #7c.** The module appears in the matrix with no top-level `/cut-floor` page yet. Test guard: `test_permissions.py` asserts the `cut_floor` row in every role; integration test `test_cv_routes.py::test_drafter_can_preview_and_commit` exercises the gate.
- **Synonym lookup must use `:code = ANY(synonyms)`** (NOT `synonyms @> ARRAY[:code]`, which Postgres does not push down through ANY() in older planner versions). The resolver SQL uses `WHERE :code = ANY(synonyms) AND archived_at IS NULL`.

---

#### Pre-flight checklist

- [ ] Confirm clean working tree: `git status` shows only `.gitignore`, `.claude/`, `.pnpm-store/`, and `docs/archive/2026-05-05-shop-floor.md` (the parallel Shop Floor spec — untouched by #7b).
- [ ] Confirm branch: `git rev-parse --abbrev-ref HEAD` → `feat/foundation`.
- [ ] Confirm latest migration: `ls db/alembic/versions/ | sort | tail -3` → `0015_*`, `0016_sample.py`, `0017_catalog_enrichment.py`.
- [ ] Confirm baseline: `docker compose exec -T api pytest -q` → **334 passed, 1 skipped, 0 failed** (recorded 2026-05-07).
- [ ] Confirm stack up: `docker compose ps` shows `api`, `db`, `web` all `Up`.
- [ ] Read spec §1, §3.1, §4.2, §5, §6 (full), §7.2, §8 (0018 block), §10.1 once before starting.
- [ ] Read sibling code:
   - `apps/api/app/catalog/{queries.py,routes.py,schemas.py}` — REGISTRY-driven CRUD pattern + audit hook style.
   - `apps/api/app/items/{queries.py,routes.py}` — workspace isolation through `projects.workspace_id = :w` predicate.
   - `apps/api/app/parts/{queries.py,routes.py}` — single-transaction insert pattern, edit_log integration.
   - `apps/api/app/edit_log.py` — `write_item_edit_log()` helper signature.
   - `apps/api/app/samples/routes.py` — RBAC + multipart upload pattern (we mimic for the CSV upload).

---

#### File structure (locked)

```
apps/api/app/
  cv/
    __init__.py
    routes.py                 # 4 routes: POST preview, POST commit, GET /items/{iid}/cv-imports, GET /cv-imports/{run_id}
    queries.py                # text() SQL — cv_import_run insert/update + commit transaction (modules + parts) + history
    parser.py                 # CSV header normalisation + ParsedPart + RowError
    resolver.py               # pure-fn resolver — order: mapping → synonym → exact-sku → unknown
    schemas.py                # Pydantic v2 — CvPreviewIn, CvPreviewOut, CvRowResolution, CvCommitIn, CvCommitOut, CvImportRunOut
  auth/
    permissions.py            # MODIFY: add `cut_floor` to Module Literal + _ALL_MODULES + per-role rows
  main.py                     # MODIFY: include_router(cv_router)

apps/api/tests/
  conftest.py                 # MODIFY: add `cv_import_run` to TRUNCATE_TABLES (above audit_log)
  test_cv_parser.py           # NEW — ~10 cases (header normalisation + numeric coercion + invalid rows)
  test_cv_resolver.py         # NEW — ~8 cases (mapping > synonym > exact > unknown; workspace isolation)
  test_cv_routes.py           # NEW — ~15 cases (preview + commit + 409 re-import + ?mode=replace + RBAC + cross-workspace 404 + 415 file-too-large)
  test_permissions.py         # MODIFY: append 5 cut_floor-row tests

db/alembic/versions/
  0018_cv_import.py           # NEW — cv_import_run + 2 indexes

seed/
  hartwood_joinery.py         # MODIFY: add 1 cv_import_run (committed) for ALF-001 item 1

apps/web/app/(app)/items/[id]/_components/cutlist/
  CutlistTab.tsx              # MODIFY: add "Import from CV" toolbar button + dialog mount + ?import=cv URL state
  CvImportDialog.tsx          # NEW — 3-phase wizard
  UnknownCodeRow.tsx          # NEW — one row in Phase B (Use existing | Create new | Skip)
  CreateCatalogRowMiniForm.tsx # NEW — inline create form for the 5 simple tables

apps/web/lib/
  cv-types.ts                 # mirrors backend Pydantic schemas
  cv-fetch.ts                 # tiny fetch wrappers (preview, commit, history)

tests/e2e/
  cv_import.spec.ts           # NEW — Scenario A from spec §10.2 (drafter imports → resolves 1 unknown → commits → 9 parts visible)

docs/archive/plans/
  2026-05-05-cabinet-vision-7b-cv-import.md  # this file

CLAUDE.md                     # MODIFY: append "CV Import wizard (sub-project #7b)" subsection
```

---

#### Phase 1 — Schema + RBAC (3 tasks)

##### Task 1: Migration 0018 — `cv_import_run`

**Files:**
- Create: `db/alembic/versions/0018_cv_import.py`

Per spec §3.1 + §8. Single new table, two indexes. The `cv_material_mapping` register already shipped in 0017 — #7b only adds the run register.

- [ ] **Step 1: Write the migration**

```python
"""cv_import_run register — sub-project #7b

Adds cv_import_run with status CHECK + indexes per spec §3.1.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-05
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
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


def downgrade():
    op.execute("-- intentionally not reversible; recover via 0001-0017 only")
```

- [ ] **Step 2: Apply the migration**

```bash
docker compose exec -T api sh -c "cd /db && alembic upgrade head"
```

Expected output ends with `INFO  [alembic.runtime.migration] Running upgrade 0017 -> 0018`.

- [ ] **Step 3: Verify columns + indexes**

```bash
docker compose exec -T db psql -U jf -d joineryflow -c "\d+ cv_import_run"
docker compose exec -T db psql -U jf -d joineryflow -c "SELECT indexname FROM pg_indexes WHERE tablename = 'cv_import_run';"
```

Expected: 11 columns; pkey + `idx_cv_import_run_item` + `idx_cv_import_run_status`.

- [ ] **Step 4: Smoke-test the CHECK constraint**

```bash
docker compose exec -T db psql -U jf -d joineryflow -v ON_ERROR_STOP=0 <<'SQL'
INSERT INTO cv_import_run(project_id,item_id,source_filename,sha256,status,created_by)
  VALUES (1, 1, 'x', repeat('a',64), 'bad_status', 1);
SQL
```

Expected: `ERROR: new row for relation "cv_import_run" violates check constraint "cv_import_run_status_check"`.

- [ ] **Step 5: Re-run the full pytest suite**

```bash
docker compose exec -T api pytest -q
```

Expected: **334 passed, 1 skipped** (no test depends on the new table yet).

- [ ] **Step 6: Commit**

```
feat(db): migration 0018 — cv_import_run (#7b)
```

---

##### Task 2: Add `cv_import_run` to `TRUNCATE_TABLES`

**Files:**
- Modify: `apps/api/tests/conftest.py`

The `truncate_all` fixture needs the new table so tests start clean. FK ordering: `cv_import_run` references `projects`, `items`, `app_user` — sits above `projects` in the truncation order (truncate child first).

- [ ] **Step 1: Edit `apps/api/tests/conftest.py`**

In `TRUNCATE_TABLES`, insert `"cv_import_run"` between `"items"` and `"project_favourites"`.

- [ ] **Step 2: Verify the suite still passes**

```bash
docker compose exec -T api pytest -q
```

Expected: **334 passed, 1 skipped**.

- [ ] **Step 3: Commit**

```
test(api): truncate cv_import_run in conftest (#7b)
```

---

##### Task 3: RBAC matrix — add `cut_floor` module

**Files:**
- Modify: `apps/api/app/auth/permissions.py`
- Modify: `apps/api/tests/test_permissions.py`

Per spec §5. The `cut_floor` module lands in #7b (not #7c) so the CV import routes here can gate on it without forward-declaration. #7c will *reuse* the row when it adds `/cut-floor` and CutPlan routes.

- [ ] **Step 1: Read `apps/api/app/auth/permissions.py`** to confirm current shape (8 modules after #7a: dashboard, tracking, list, shop_dwgs, isample, orderbook, catalog, it_management).

- [ ] **Step 2: Append failing tests to `apps/api/tests/test_permissions.py`**

```python
def test_drafter_cut_floor_full_access():
    """Drafter is elevated to admin/manager parity on cut_floor (#7b)."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["cut_floor"] == {"read", "write", "approve", "comment"}


def test_editor_cut_floor_can_read_write_comment_no_approve():
    from app.auth.permissions import MATRIX
    assert MATRIX["editor"]["cut_floor"] == {"read", "write", "comment"}


def test_purchase_officer_cut_floor_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["purchase_officer"]["cut_floor"] == {"read"}


def test_viewer_cut_floor_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["viewer"]["cut_floor"] == {"read"}


def test_manager_admin_cut_floor_full_access():
    from app.auth.permissions import MATRIX
    assert MATRIX["manager"]["cut_floor"] == {"read", "write", "approve", "comment"}
    assert MATRIX["admin"]["cut_floor"] == {"read", "write", "approve", "comment"}
```

- [ ] **Step 3: Run, confirm fail**

```bash
docker compose exec -T api pytest tests/test_permissions.py -v -k "cut_floor"
```

Expected: 5 failures.

- [ ] **Step 4: Update `apps/api/app/auth/permissions.py`**

Add `cut_floor` to the `Module` Literal + `_ALL_MODULES` tuple between `catalog` and `it_management`. Per-role updates per spec §5:

```python
"editor": {
    m: {"read", "write", "comment"}
    for m in ("dashboard", "tracking", "list", "shop_dwgs", "isample", "cut_floor")
} | {
    "orderbook": {"read", "comment"},
    "catalog":   {"read", "write", "comment"},
    "it_management": set(),
},

"drafter": {
    "dashboard":    {"read"},
    "tracking":     {"read", "write", "approve", "comment"},
    "list":         {"read", "write", "approve", "comment"},
    "shop_dwgs":    {"read", "write", "approve", "comment"},
    "isample":      {"read", "write", "approve", "comment"},
    "orderbook":    {"read", "write", "approve", "comment"},
    "catalog":      {"read", "write", "approve", "comment"},
    "cut_floor":    {"read", "write", "approve", "comment"},
    "it_management": set(),
},

"purchase_officer": {
    ...,
    "catalog":   {"read", "comment"},
    "cut_floor": {"read"},
    ...,
},

"viewer": {
    m: {"read"} for m in (
        "dashboard","tracking","list","shop_dwgs","isample",
        "orderbook","catalog","cut_floor",
    )
} | {"it_management": set()},

"manager": ...,  # add "cut_floor": {"read","write","approve","comment"}
"admin":   ...,  # add "cut_floor": {"read","write","approve","comment"}
```

- [ ] **Step 5: Run, confirm green**

```bash
docker compose exec -T api pytest tests/test_permissions.py -q
```

- [ ] **Step 6: Commit**

```
feat(rbac): add cut_floor module + drafter/editor parity (#7b)
```

---

#### Phase 2 — Backend parser + resolver (3 tasks)

##### Task 4: `apps/api/app/cv/schemas.py`

**Files:**
- Create: `apps/api/app/cv/__init__.py` (empty package marker)
- Create: `apps/api/app/cv/schemas.py`

Pydantic v2 models for the wire format. Spec §6.3 nails down `CvPreviewOut`. We mirror it field-for-field.

- [ ] **Step 1: Create `apps/api/app/cv/__init__.py`** (empty file).

- [ ] **Step 2: Create `apps/api/app/cv/schemas.py`** with the following models:
   - `CvRowError` — `{row_index: int, code: str, field: str | None, value: str | None, message: str}`.
   - `CvRowResolution` — discriminated union on `kind`:
     - `mapped`: `{kind, target_table, target_material_id, target_description}`
     - `synonym_match`: same shape as `mapped`
     - `unknown`: `{kind, hint?: str}` (e.g. `multiple_synonym_matches`).
   - `CvParsedPart` — `{row_index, part_name, qty, len_mm, wid_mm, thickness_mm: int | None, cv_code, edge: str | None, colour: str | None, notes: str | None, resolution: CvRowResolution}`.
   - `CvParsedModule` — `{module_no: int, parts: list[CvParsedPart]}`.
   - `CvUnknownCode` — `{cv_code, occurrences, suggested_table: str | None}`.
   - `CvPreviewSummary` — `{row_count, mapped, synonym, unknown, invalid}`.
   - `CvPreviewOut` — `{run_id, summary: CvPreviewSummary, modules: list[CvParsedModule], unknown_codes: list[CvUnknownCode], errors: list[CvRowError]}`.
   - `CvCommitResolution` — discriminated union on `action`:
     - `use_existing`: `{action, cv_code, target_table, target_material_id}`
     - `create_new`: `{action, cv_code, target_table, sku, description, default_supplier?, default_lead_time_days?}`  — `target_table` ∈ the 5 simple tables only.
     - `skip`: `{action, cv_code}`
   - `CvCommitIn` — `{resolutions: list[CvCommitResolution], replace: bool}`.
   - `CvCommitOut` — `{run_id, modules_created: int, parts_created: int, mappings_created: int, catalog_rows_created: int, replaced_module_ids: list[int]}`.
   - `CvImportRunOut` — `{cv_import_run_id, project_id, item_id, source_filename, sha256, row_count, status, started_at, completed_at: datetime | None, created_by: int}`.

- [ ] **Step 3: Verify imports cleanly**

```bash
docker compose exec -T api python -c "from app.cv.schemas import CvPreviewOut, CvCommitIn; print('ok')"
```

- [ ] **Step 4: Commit**

```
feat(api): cv schemas — preview/commit/history (#7b)
```

---

##### Task 5: `apps/api/app/cv/parser.py`

**Files:**
- Create: `apps/api/app/cv/parser.py`

Pure function. Input: raw CSV bytes (already size-checked by route). Output: `(list[ParsedPart], list[CvRowError], int row_count)`. Header normalisation per spec §6.1.

- [ ] **Step 1: Define the header-alias table** as a module-level constant `HEADER_ALIASES`:

```python
HEADER_ALIASES = {
    "module_no":     ("MOD","Module","ModuleNo","Module #","Mod #"),
    "part_name":     ("Part Name","PartName","Description","Item"),
    "qty":           ("Qty","Quantity","#"),
    "len_mm":        ("Length","Len","L","Length (mm)"),
    "wid_mm":        ("Width","Wid","W","Width (mm)"),
    "thickness_mm":  ("Thickness","Thk","T"),
    "material_code": ("Material","Material Code","MaterialCode","Code","Sku"),
    "edge":          ("Edge","Edging"),
    "colour":        ("Colour","Color","Finish"),
    "notes":         ("Notes","Note","Comment"),
}

REQUIRED_COLUMNS = ("module_no","part_name","qty","len_mm","wid_mm","material_code")
```

A normalisation helper `_normalise_header(s) -> str` strips spaces and lowercases.

- [ ] **Step 2: Public function signature**

```python
@dataclass
class ParsedPart:
    row_index: int
    module_no: int
    part_name: str
    qty: int
    len_mm: int
    wid_mm: int
    thickness_mm: int | None
    cv_code: str
    edge: str | None
    colour: str | None
    notes: str | None


def parse_csv(raw_bytes: bytes) -> tuple[list[ParsedPart], list[CvRowError], int]:
    ...
```

- [ ] **Step 3: Behaviour**

  - Decode `raw_bytes` as UTF-8 with `errors="replace"`. If 0 lines → raise `ValueError("empty CSV")`.
  - Parse with `csv.DictReader`. If any of `REQUIRED_COLUMNS` is missing after alias resolution → raise `ValueError(f"missing required column: {col}")`. Caller maps to 422.
  - For each row (1-indexed `row_index` starting at 1 = first data row):
    - Coerce numerics. On `ValueError` from `int()` produce a `CvRowError(code='INVALID_NUMERIC', field='len_mm', value=raw, message=...)` and skip.
    - `qty <= 0` or `len_mm <= 0` or `wid_mm <= 0` → `CvRowError(code='INVALID_DIMENSION')`.
    - Trim string fields. Empty `part_name` → `CvRowError(code='MISSING_REQUIRED', field='part_name')`.
    - Empty `material_code` → `CvRowError(code='MISSING_REQUIRED', field='material_code')`.
  - Return `(parts, errors, total_rows_seen)`.

- [ ] **Step 4: Smoke-import**

```bash
docker compose exec -T api python -c "from app.cv.parser import parse_csv; print(parse_csv(b'Module,Part Name,Qty,Length,Width,Material\n1,A,1,720,580,18-PB\n'))"
```

- [ ] **Step 5: Commit**

```
feat(api): cv parser — header normalisation + row coercion (#7b)
```

---

##### Task 6: `apps/api/app/cv/resolver.py`

**Files:**
- Create: `apps/api/app/cv/resolver.py`

Resolves each `ParsedPart.cv_code` against the resolver order in spec §6.2.

- [ ] **Step 1: Public signature**

```python
def resolve_codes(
    conn: Connection,
    workspace_id: int,
    parts: list[ParsedPart],
) -> dict[str, CvRowResolution]:
    """Return {cv_code: resolution} for every distinct code in `parts`."""
```

- [ ] **Step 2: Resolution order per spec §6.2**

  1. **Mapping hit:** `SELECT target_material_table, target_material_id FROM cv_material_mapping WHERE workspace_id=:w AND cv_code=:code`. If hit → `kind='mapped'`. Fetch `target_description` from the target catalog table by id.
  2. **Synonym hit:** for each of the 6 catalog tables, `SELECT id, sku, description FROM {tbl} WHERE workspace_id=:w AND :code = ANY(synonyms) AND archived_at IS NULL`. Collect across tables. Exactly 1 hit total → `kind='synonym_match'`. ≥2 hits across tables → `kind='unknown'` with `hint='multiple_synonym_matches'`.
  3. **Exact-sku hit:** `SELECT ... FROM {tbl} WHERE workspace_id=:w AND sku=:code AND archived_at IS NULL`. Same dispatch as synonyms; classified as `synonym_match` per spec §6.2 step 3.
  4. **Otherwise:** `kind='unknown'` (no `hint`).

- [ ] **Step 3: Suggested-table inference** (for `CvUnknownCode.suggested_table`)

A simple regex heuristic in `resolver.py`:

  - Code starts with `\d{2}-` → `board_materials` (e.g. `18-PB`, `19-MELAMINE-WHITE`).
  - Code matches `\d{3}\.\d` → `hardware_materials` (e.g. `700.0KC2.054.00`).
  - Otherwise → `None`.

Used by Phase B's UI to pre-select the target tab in the "Create new" mini-form.

- [ ] **Step 4: Verify with REPL**

```bash
docker compose exec -T api python -c "from app.cv.resolver import suggest_table; print(suggest_table('18-PB'), suggest_table('700.0KC2.054.00'), suggest_table('weird-code'))"
```

Expected: `board_materials hardware_materials None`.

- [ ] **Step 5: Commit**

```
feat(api): cv resolver — mapping > synonym > exact-sku (#7b)
```

---

#### Phase 3 — Backend queries + routes (3 tasks)

##### Task 7: `apps/api/app/cv/queries.py`

**Files:**
- Create: `apps/api/app/cv/queries.py`

text() SQL. Three logical groups:

1. **Run lifecycle:** `insert_run_preview`, `update_run_committed`, `update_run_failed`, `get_run_by_id`, `list_runs_for_item`.
2. **Commit transaction:** `commit_import` — single function, single transaction.
3. **Helpers:** `count_modules_for_item`, `delete_modules_cascade`, `lookup_target_description`.

- [ ] **Step 1: Implement `insert_run_preview(conn, *, project_id, item_id, source_filename, sha256, row_count, error_log_jsonb, created_by) -> int`** returning the new run_id.

- [ ] **Step 2: Implement `commit_import` skeleton** per spec §6.6:

```python
def commit_import(
    conn,
    *,
    workspace_id: int,
    project_id: int,
    item_id: int,
    run_id: int,
    parsed_parts: list[ParsedPart],
    resolutions: dict[str, CvCommitResolution],
    mode: str,  # "default" | "replace"
    created_by: int,
) -> CvCommitOut:
    # 1. (mode=replace) delete modules; capture deleted_module_ids
    # 2. for each `create_new` resolution: INSERT into target catalog table
    # 3. for each `use_existing` (no existing mapping): INSERT cv_material_mapping
    # 4. INSERT modules — one per distinct module_no
    # 5. INSERT parts — for each non-skipped row, with material_table + material_id resolved
    # 6. UPDATE cv_import_run SET status='committed', completed_at=now()
    # 7. write audit_log: cv.import.commit + per-part part.create
    # 8. write item_edit_log per module + per part + summary _cv_import row
```

All steps in a single SAVEPOINT; rollback on any error → set `status='failed'` and re-raise.

- [ ] **Step 3: Module rows insertion**

`modules` table columns (verify via `\d+ modules`): `item_id, module_no, name?, ...`. Use `module_no` as the natural key per item; if a part references `module_no=1` and we already inserted a module with `module_no=1`, reuse its id (in-memory map).

- [ ] **Step 4: Part rows insertion**

`parts` columns include `module_id, name, qty, len_mm, wid_mm, material_table, material_id, paint_instruction default 'NONE', edge, colour, notes`. Map `cv_code` → `(material_table, material_id)` via the resolutions + already-resolved `mapped`/`synonym_match` from preview snapshot.

- [ ] **Step 5: Audit + edit log**

  - `audit_log`: 1 row `event='cv.import.commit'`, `payload={run_id, modules_created, parts_created, mappings_created, catalog_rows_created}`.
  - `audit_log`: 1 row per part `event='part.create'`.
  - If `mode='replace'`: 1 row `event='cv.import.replace_wipe'`, `payload={run_id, deleted_module_ids}`.
  - `item_edit_log`: 1 row per module `field='_create_module'`.
  - `item_edit_log`: 1 row per part `field='_create_part'`.
  - `item_edit_log`: 1 summary row `field='_cv_import'`, `new_value='{run_id} ({M} parts)'`.

Use the existing `apps/api/app/edit_log.py::write_item_edit_log()` helper.

- [ ] **Step 6: Commit**

```
feat(api): cv queries — preview/commit/history (#7b)
```

---

##### Task 8: `apps/api/app/cv/routes.py` — preview + commit

**Files:**
- Create: `apps/api/app/cv/routes.py`
- Modify: `apps/api/app/main.py` (include router)

Per spec §4.2.

- [ ] **Step 1: Router setup**

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from app.auth.rbac import require_permission
from app.db import get_conn

cv_router = APIRouter(prefix="", tags=["cv"])
MAX_CSV_BYTES = 1_048_576  # 1 MB
MAX_LOGICAL_ROWS = 10_000
```

- [ ] **Step 2: `POST /items/{iid}/cv-imports/preview`**

```python
@cv_router.post("/items/{iid}/cv-imports/preview")
async def preview_cv_import(
    iid: int,
    file: UploadFile | None = File(None),
    body: str | None = Form(None),
    me=Depends(require_permission("cut_floor", "write")),
    conn=Depends(get_conn),
) -> CvPreviewOut:
    # 1. Resolve project_id + workspace_id from item, 404 if cross-workspace
    # 2. Read bytes from file OR body (exactly one required)
    # 3. 415 if len(bytes) > MAX_CSV_BYTES, code='FILE_TOO_LARGE'
    # 4. parse_csv(raw_bytes) -> (parts, errors, row_count)
    #    - 422 on missing required column with the column name
    #    - 415 if row_count > MAX_LOGICAL_ROWS
    # 5. resolve_codes(...) -> {code: resolution}
    # 6. Build CvPreviewOut payload (group parts by module_no in ascending order)
    # 7. Insert cv_import_run with status='preview', error_log={...preview, _preview_snapshot:...}
    # 8. audit_log: event='cv.import.preview', payload={run_id, source_filename, row_count, summary}
    # 9. Return payload (with run_id populated)
```

Workspace gate: SELECT projects.workspace_id WHERE item.id = :iid; 404 if `workspace_id != me.workspace_id`.

- [ ] **Step 3: `POST /items/{iid}/cv-imports/{run_id}/commit`**

```python
@cv_router.post("/items/{iid}/cv-imports/{run_id}/commit")
async def commit_cv_import(
    iid: int,
    run_id: int,
    body: CvCommitIn,
    mode: str = "default",  # query string ?mode=replace
    me=Depends(require_permission("cut_floor", "write")),
    conn=Depends(get_conn),
) -> CvCommitOut:
    # 1. Workspace gate
    # 2. Load run; 404 if not found / wrong item / wrong workspace
    # 3. 409 if run.status != 'preview'
    # 4. Rehydrate parsed_parts from run.error_log['_preview_snapshot']
    # 5. Validate every unknown_code has a resolution in body.resolutions; 422 otherwise
    # 6. Validate `replace` field matches `mode` query (defence-in-depth)
    # 7. count_modules_for_item — if >0 and mode != 'replace': 409 code='ITEM_NOT_EMPTY'
    # 8. commit_import(...) inside a transaction
    # 9. On exception: update_run_failed, audit cv.import.fail, re-raise
```

- [ ] **Step 4: Wire into `apps/api/app/main.py`**

Add `from app.cv.routes import cv_router` and `app.include_router(cv_router)` after the catalog router include.

- [ ] **Step 5: Smoke-test by hand**

```bash
curl -X POST http://localhost:8000/items/1/cv-imports/preview \
  -F "body=Module,PartName,Qty,Length,Width,Material
1,Side L,1,720,580,18-PB
1,Side R,1,720,580,18-PB" \
  -b "jf_session=..." | jq
```

Expected: `summary.row_count=2`, both rows resolved as `mapped`.

- [ ] **Step 6: Commit**

```
feat(api): cv routes — preview + commit + workspace gate (#7b)
```

---

##### Task 9: `apps/api/app/cv/routes.py` — history GET endpoints

**Files:**
- Modify: `apps/api/app/cv/routes.py`

- [ ] **Step 1: `GET /items/{iid}/cv-imports`**

```python
@cv_router.get("/items/{iid}/cv-imports")
async def list_cv_imports(
    iid: int,
    me=Depends(require_permission("cut_floor", "read")),
    conn=Depends(get_conn),
) -> list[CvImportRunOut]:
    # Workspace gate. Order by started_at DESC. No paging in v1.
```

- [ ] **Step 2: `GET /cv-imports/{run_id}`**

```python
@cv_router.get("/cv-imports/{run_id}")
async def get_cv_import_run(
    run_id: int,
    me=Depends(require_permission("cut_floor", "read")),
    conn=Depends(get_conn),
) -> dict:
    # Resolves run -> item -> project -> workspace; 404 if cross-workspace.
    # Returns {run: CvImportRunOut, preview: CvPreviewOut | None}
```

- [ ] **Step 3: Smoke-test**

```bash
curl http://localhost:8000/items/1/cv-imports -b "jf_session=..." | jq
```

- [ ] **Step 4: Commit**

```
feat(api): cv history routes (#7b)
```

---

#### Phase 4 — Tests (3 tasks)

##### Task 10: `apps/api/tests/test_cv_parser.py`

**Files:**
- Create: `apps/api/tests/test_cv_parser.py`

~10 cases covering header normalisation + numeric coercion + invalid rows.

- [ ] **Step 1: Test cases**

   1. `test_parse_canonical_header` — perfect headers, 1 module, 2 parts → 2 ParsedPart, 0 errors.
   2. `test_parse_alias_headers` — `MOD,Description,Qty,L,W,Code` → resolves to module_no/part_name/qty/len_mm/wid_mm/material_code.
   3. `test_missing_required_column_raises` — missing `Material` column → `ValueError("missing required column: material_code")`.
   4. `test_invalid_numeric_produces_row_error` — `len_mm="abc"` → `CvRowError(code='INVALID_NUMERIC', field='len_mm')`. Other rows still parse.
   5. `test_invalid_dimension_produces_row_error` — `qty=0` → `code='INVALID_DIMENSION'`.
   6. `test_empty_part_name_produces_row_error` — empty `Part Name` cell → `code='MISSING_REQUIRED', field='part_name'`.
   7. `test_empty_material_code_produces_row_error` — empty `Material` cell → `code='MISSING_REQUIRED', field='material_code'`.
   8. `test_thickness_optional` — missing `Thickness` column → parses fine; `parsed_part.thickness_mm is None`.
   9. `test_unicode_part_name` — `Part Name="Côté"` → preserved.
   10. `test_empty_csv_raises` — `parse_csv(b"")` → `ValueError("empty CSV")`.

- [ ] **Step 2: Run, all green**

```bash
docker compose exec -T api pytest tests/test_cv_parser.py -v
```

Expected: 10 passed.

- [ ] **Step 3: Commit**

```
test(api): cv parser — 10 cases (#7b)
```

---

##### Task 11: `apps/api/tests/test_cv_resolver.py`

**Files:**
- Create: `apps/api/tests/test_cv_resolver.py`

~8 cases covering resolver dispatch + workspace isolation.

- [ ] **Step 1: Test cases**

  1. `test_mapping_hit_beats_synonym` — workspace W has both a mapping and a synonym for `18-PB`. Resolver returns `kind='mapped'`.
  2. `test_synonym_hit_when_no_mapping` — only synonym present → `kind='synonym_match'`.
  3. `test_exact_sku_hit` — neither mapping nor synonym; SKU exact match → `kind='synonym_match'`.
  4. `test_unknown_returns_unknown_kind` — no hits → `kind='unknown'`, no hint.
  5. `test_multiple_synonym_tables_returns_unknown_with_hint` — same code in `board_materials.synonyms` AND `hardware_materials.synonyms` → `kind='unknown', hint='multiple_synonym_matches'`.
  6. `test_workspace_isolation` — workspace A has mapping; workspace B does not. Resolver in B returns `unknown` for the same code.
  7. `test_archived_synonym_excluded` — synonym row with `archived_at IS NOT NULL` is ignored.
  8. `test_suggest_table_heuristic` — `suggest_table('18-PB') == 'board_materials'`; `suggest_table('700.0KC2.054.00') == 'hardware_materials'`; `suggest_table('weirdcode') is None`.

- [ ] **Step 2: Run, all green**

```bash
docker compose exec -T api pytest tests/test_cv_resolver.py -v
```

- [ ] **Step 3: Commit**

```
test(api): cv resolver — 8 cases (#7b)
```

---

##### Task 12: `apps/api/tests/test_cv_routes.py`

**Files:**
- Create: `apps/api/tests/test_cv_routes.py`

~15 cases — full preview + commit happy + RBAC + edge cases.

- [ ] **Step 1: Test cases**

  1. `test_drafter_can_preview` — POST preview with 2-row CSV (both `mapped`) → 200, `cv_import_run` row written with `status='preview'`.
  2. `test_preview_writes_audit_event` — `audit_log` contains `event='cv.import.preview'` with the run_id.
  3. `test_preview_unknown_code_classifies_as_unknown` — CSV with `18-WAX` (no mapping, no synonym) → row's `resolution.kind == 'unknown'`.
  4. `test_preview_invalid_numeric_returns_in_errors` — CSV with `Length=abc` → row appears in `errors[]` with `code='INVALID_NUMERIC'`.
  5. `test_preview_missing_required_column_returns_422` — header without `Material` → 422.
  6. `test_preview_file_too_large_returns_415` — 2 MB body → 415, `code='FILE_TOO_LARGE'`.
  7. `test_drafter_can_commit_simple` — preview with 2 mapped rows, commit with empty resolutions, replace=False → 200, `modules_created=1, parts_created=2`. `cv_import_run.status='committed'`.
  8. `test_commit_with_create_new_inserts_catalog_row` — preview with 1 unknown code, commit with `create_new` resolution targeting `board_materials` → catalog row + mapping written + part inserted referencing them.
  9. `test_commit_re_import_without_replace_returns_409` — second preview+commit on the same item without `?mode=replace` → 409, `code='ITEM_NOT_EMPTY'`.
  10. `test_commit_re_import_with_replace_wipes_and_re_inserts` — 2nd commit with `?mode=replace` → 200, prior modules deleted, new modules written, audit `cv.import.replace_wipe` recorded.
  11. `test_editor_cannot_preview` — editor (no `cut_floor.write`) → 403.
  12. `test_purchase_officer_cannot_preview` — purchase_officer → 403.
  13. `test_cross_workspace_get_run_returns_404` — workspace B reading workspace A's run → 404.
  14. `test_commit_with_skip_drops_rows` — 3-row CSV with 1 skipped via `skip` resolution → only 2 parts inserted.
  15. `test_get_history_orders_by_started_at_desc` — 2 runs on the same item → list returns newest first.

- [ ] **Step 2: Run**

```bash
docker compose exec -T api pytest tests/test_cv_routes.py -v
```

Expected: 15 passed.

- [ ] **Step 3: Commit**

```
test(api): cv routes — 15 cases (#7b)
```

---

#### Phase 5 — Web UI (4 tasks)

##### Task 13: `apps/web/lib/cv-types.ts` + `apps/web/lib/cv-fetch.ts`

**Files:**
- Create: `apps/web/lib/cv-types.ts`
- Create: `apps/web/lib/cv-fetch.ts`

- [ ] **Step 1: `cv-types.ts`** — TypeScript mirrors of every Pydantic model in `apps/api/app/cv/schemas.py`. Use string-literal unions for `kind` and `action`.

- [ ] **Step 2: `cv-fetch.ts`** — three thin wrappers using the existing project pattern:

```typescript
export async function previewCvImport(itemId: number, formData: FormData): Promise<CvPreviewOut> { ... }
export async function commitCvImport(itemId: number, runId: number, body: CvCommitIn, mode?: 'replace'): Promise<CvCommitOut> { ... }
export async function listCvImports(itemId: number): Promise<CvImportRunOut[]> { ... }
```

- [ ] **Step 3: Type-check passes**

```bash
docker compose exec -T web pnpm tsc --noEmit
```

- [ ] **Step 4: Commit**

```
feat(web): cv types + fetch wrappers (#7b)
```

---

##### Task 14: `CvImportDialog.tsx` — Phase A (Upload) + dialog shell

**Files:**
- Create: `apps/web/app/(app)/items/[id]/_components/cutlist/CvImportDialog.tsx`
- Modify: `apps/web/app/(app)/items/[id]/_components/cutlist/CutlistTab.tsx`

- [ ] **Step 1: Add the toolbar button to `CutlistTab.tsx`**

Above the existing parts grid:

```tsx
<button
  type="button"
  onClick={() => router.push(`?tab=cutlist&import=cv`)}
  className="rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm font-medium text-h-ink hover:bg-h-surface"
>
  Import from CV
</button>
```

Mount the dialog when `searchParams.get('import') === 'cv'`.

- [ ] **Step 2: Build `CvImportDialog.tsx`** with three internal phases driven by local state:

```tsx
type Phase = 'upload' | 'resolve' | 'commit' | 'done';
const [phase, setPhase] = useState<Phase>('upload');
const [preview, setPreview] = useState<CvPreviewOut | null>(null);
const [resolutions, setResolutions] = useState<Record<string, CvCommitResolution>>({});
const [replace, setReplace] = useState(false);
```

Phase A UI:
- Textarea (10 rows) for paste.
- File input accepting `.csv,.txt`.
- "Preview" button — disabled until either textarea or file has content.
- On submit: build FormData, call `previewCvImport`, transition to Phase B (or directly Phase C if `unknown_codes.length === 0`).
- Error banner on 422 / 415 / network.

- [ ] **Step 3: Visual check**

Open `/items/1?tab=cutlist&import=cv`. Paste:

```
Module,Part Name,Qty,Length,Width,Material
1,Side Panel L,1,720,580,18-PB
```

Click Preview. Should advance to Phase B (no unknowns; or Phase C if zero unknowns).

- [ ] **Step 4: Commit**

```
feat(web): CvImportDialog Phase A — upload + preview (#7b)
```

---

##### Task 15: `CvImportDialog.tsx` — Phase B (Resolve)

**Files:**
- Modify: `apps/web/app/(app)/items/[id]/_components/cutlist/CvImportDialog.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/cutlist/UnknownCodeRow.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/cutlist/CreateCatalogRowMiniForm.tsx`

- [ ] **Step 1: `UnknownCodeRow.tsx`**

One row per `CvUnknownCode`. Three pill toggles: **Use existing | Create new | Skip**. Active pill swaps the row's right-hand pane:

  - **Use existing:** typeahead input → fetches `/api/catalog/{table}?q=` across all 6 tables, debounced 200ms, shows top-5 matches grouped by table label. Pick → resolution becomes `{action: 'use_existing', cv_code, target_table, target_material_id}`.
  - **Create new:** `CreateCatalogRowMiniForm.tsx`. Auto-selects the `suggested_table` from the preview. Fields: `sku` (required), `description` (required), `default_supplier`, `default_lead_time_days`. Equipment Hire is **disabled** with a tooltip linking to `/catalog?tab=hire`. Submit doesn't write yet — it just stages a `{action: 'create_new', ...}` resolution.
  - **Skip:** resolution becomes `{action: 'skip', cv_code}`.

- [ ] **Step 2: Phase B UI shell**

```tsx
{phase === 'resolve' && preview && (
  <>
    <SummaryStrip preview={preview} />
    <p className="text-sm text-h-muted">
      Resolve {preview.unknown_codes.length} unknown code(s) before importing.
    </p>
    {preview.unknown_codes.map((u) => (
      <UnknownCodeRow
        key={u.cv_code}
        unknown={u}
        resolution={resolutions[u.cv_code]}
        onChange={(r) => setResolutions({ ...resolutions, [u.cv_code]: r })}
      />
    ))}
    <button
      disabled={preview.unknown_codes.some(u => !resolutions[u.cv_code])}
      onClick={() => setPhase('commit')}
    >Continue</button>
  </>
)}
```

- [ ] **Step 3: Visual check**

Paste a CSV with one unknown code (e.g. `99-XYZ`). Phase B should list that code with the 3 pills. Pick "Skip" → Continue button enables.

- [ ] **Step 4: Commit**

```
feat(web): CvImportDialog Phase B — resolve unknowns (#7b)
```

---

##### Task 16: `CvImportDialog.tsx` — Phase C (Commit) + done

**Files:**
- Modify: `apps/web/app/(app)/items/[id]/_components/cutlist/CvImportDialog.tsx`

- [ ] **Step 1: Phase C UI**

```tsx
{phase === 'commit' && preview && (
  <>
    <p>Import {parsedTotal} parts in {moduleCount} modules under Item {item.code}?</p>
    {item.has_existing_modules && (
      <label>
        <input type="checkbox" checked={replace} onChange={e => setReplace(e.target.checked)} />
        Replace existing modules (item already has {item.module_count} modules — they will be deleted)
      </label>
    )}
    <button onClick={onConfirm}>Import</button>
  </>
)}
```

`onConfirm` calls `commitCvImport(itemId, run_id, {resolutions: Object.values(resolutions), replace}, replace ? 'replace' : undefined)`.

On 200: setPhase('done'), show success summary `{modules_created} modules, {parts_created} parts created`. After 2s auto-navigate to `?tab=cutlist` (drops `import=cv` query param) and refresh.

On 409 with `code='ITEM_NOT_EMPTY'` → if `replace` was unchecked, surface inline checkbox + "Replace and import" CTA in red.

- [ ] **Step 2: Visual check end-to-end**

  - Paste 2-row CSV with both rows mapped.
  - Phase A → Phase C (no unknowns).
  - Click Import.
  - Refresh — both parts appear in the cutlist grid.

- [ ] **Step 3: Commit**

```
feat(web): CvImportDialog Phase C — commit (#7b)
```

---

#### Phase 6 — Seed + E2E + Docs (3 tasks)

##### Task 17: Seed — add 1 committed `cv_import_run` for ALF-001 item 1

**Files:**
- Modify: `seed/hartwood_joinery.py`

- [ ] **Step 1: Seed block**

After the catalog/mapping seed block (added in #7a), append:

```python
# === CV Import demo (#7b) ===
db.execute(text("DELETE FROM cv_import_run WHERE item_id = :iid"), {"iid": alf_item_1_id})

run_id = db.execute(text("""
    INSERT INTO cv_import_run(project_id, item_id, source_filename, sha256,
                              row_count, status, started_at, completed_at, error_log, created_by)
    VALUES (:pid, :iid, 'demo-cv-import.csv', repeat('a', 64),
            9, 'committed', now() - interval '1 day', now() - interval '1 day' + interval '5 second',
            '[]'::jsonb, :uid)
    RETURNING cv_import_run_id
"""), {"pid": alf_project_id, "iid": alf_item_1_id, "uid": rin_park_id}).scalar_one()
```

(No actual modules/parts inserted from this — they already exist from the PM Workbench seed. The `cv_import_run` is a register row.)

- [ ] **Step 2: Re-run seed**

```bash
docker compose exec -T api python -m seed.hartwood_joinery
```

Expected: no errors. Header line includes `· 1 cv_import_run`.

- [ ] **Step 3: Verify**

```bash
docker compose exec -T db psql -U jf -d joineryflow -c "SELECT cv_import_run_id, status, row_count FROM cv_import_run;"
```

Expected: 1 row, `status='committed'`, `row_count=9`.

- [ ] **Step 4: Commit**

```
feat(seed): cv_import_run demo on ALF-001 item 1 (#7b)
```

---

##### Task 18: E2E happy-path — `tests/e2e/cv_import.spec.ts`

**Files:**
- Create: `tests/e2e/cv_import.spec.ts`

Per spec §10.2 Scenario A.

- [ ] **Step 1: Test outline**

```ts
test('drafter imports CV CSV with 1 unknown code, resolves, commits', async ({ page }) => {
  await loginAs(page, 'rin.park@hartwood.test', 'hartwood-dev');

  await page.goto('/items/1?tab=cutlist');
  await page.getByRole('button', { name: /Import from CV/i }).click();

  // Phase A
  await page.locator('textarea').fill(
    'Module,Part Name,Qty,Length,Width,Material\n' +
    '1,Side L,1,720,580,18-PB\n' +
    '1,Side R,1,720,580,99-MYSTERY\n'
  );
  await page.getByRole('button', { name: /^Preview$/i }).click();

  // Phase B — 1 unknown code
  await expect(page.getByText(/99-MYSTERY/)).toBeVisible();
  await page.getByRole('button', { name: /^Skip$/i }).first().click();
  await page.getByRole('button', { name: /^Continue$/i }).click();

  // Phase C — confirm
  await expect(page.getByText(/Import 1 parts in 1 modules/i)).toBeVisible();
  await page.getByRole('button', { name: /^Import$/i }).click();

  // Done
  await expect(page.getByText(/created/i)).toBeVisible({ timeout: 5000 });

  // Cutlist now shows the new part
  await expect(page.getByText(/Side L/)).toBeVisible();
});
```

- [ ] **Step 2: Run**

```bash
pnpm --dir apps/web exec playwright test cv_import.spec.ts
```

(Or `make e2e-docker` on Windows.)

- [ ] **Step 3: Commit**

```
feat(e2e): cv import happy-path (#7b)
```

---

##### Task 19: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a new section** immediately after the "Catalog enrichment + CV Mappings (sub-project #7a)" block:

```markdown
## CV Import wizard (sub-project #7b)

- New backend module `apps/api/app/cv/` — parser, resolver, queries, routes.
  Mounted at top-level paths: `POST /items/{iid}/cv-imports/preview`,
  `POST /items/{iid}/cv-imports/{run_id}/commit`,
  `GET /items/{iid}/cv-imports`, `GET /cv-imports/{run_id}`.
- Migration 0018 adds `cv_import_run(cv_import_run_id, project_id, item_id,
  source_filename, sha256, row_count, status, started_at, completed_at,
  error_log, created_by)` with status CHECK ('preview','committed','failed')
  and 2 indexes.
- New `cut_floor` row in the RBAC matrix. Drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`;
  purchase_officer/viewer `{read}`. The full `/cut-floor` page + CutPlan
  routes ship in #7c — #7b only consumes the row from the CV import
  routes.
- 3-phase wizard mounted in the Drafter Editor Cutlist tab via
  `?import=cv`. Phase A (paste/upload), Phase B (resolve unknown codes
  inline — Use existing | Create new | Skip), Phase C (confirm + commit
  with optional Replace existing modules checkbox).
- File caps: 1 MB hard cap, 10 000 logical rows. 415 with
  `code='FILE_TOO_LARGE'` if exceeded.
- Resolver order (per spec §6.2): cv_material_mapping → catalog
  synonyms[] (single-table hit) → catalog sku exact match → unknown.
  Multiple-table synonym hit returns `unknown` with hint
  `multiple_synonym_matches`. Workspace-isolated everywhere.
- Re-import: default 409 with `code='ITEM_NOT_EMPTY'` if the item already
  has modules. `?mode=replace` wipes (CASCADE) and re-imports; audit
  emits `cv.import.replace_wipe` with `deleted_module_ids`.
- Commit transaction (per spec §6.6): inserts new catalog rows from
  `create_new` resolutions, writes `cv_material_mapping` for
  `use_existing` resolutions without a prior mapping, inserts modules +
  parts, writes audit (`cv.import.commit` + per-part `part.create`) and
  item_edit_log (per module `_create_module`, per part `_create_part`,
  one summary `_cv_import`). All in a single transaction; rollback on
  error sets `status='failed'`.
- Preview snapshot: full `CvPreviewOut` is stored in
  `cv_import_run.error_log` under key `_preview_snapshot` so
  `GET /cv-imports/{run_id}` rehydrates without re-parsing.
- "Create new" mini-form ships for the 5 simple catalog tables
  (board / hardware / custom / benchtop / appliances). Equipment Hire
  is disabled with a tooltip linking to `/catalog?tab=hire` (it requires
  a project_id FK on insert).
- Seed (`make seed`) writes 1 committed `cv_import_run` row on ALF-001
  item 1 (no real modules/parts inserted — they already exist from the
  PM Workbench seed). Idempotent.
- Out of scope (deferred to #7c): CutPlan / CutSchedule / Board tab /
  `/cut-floor` page. (Indefinite): bin-packing optimiser, three-way
  merge re-import UI, Cabinet Vision API integration.
```

- [ ] **Step 2: Commit**

```
docs: CLAUDE.md — CV Import wizard (#7b)
```

---

#### Verification — full sweep

After all 19 tasks land, run:

```bash
docker compose exec -T api pytest -q                      # expect: ≥360 passed (334 baseline + ~30 new)
pnpm --dir apps/web exec tsc --noEmit                     # expect: 0 errors
pnpm --dir apps/web exec playwright test cv_import.spec.ts  # expect: 1 passed
```

Manual smoke test:

1. `make up && make migrate && make seed`.
2. Login as `rin.park@hartwood.test` / `hartwood-dev`.
3. Open `/items/1?tab=cutlist` → click **Import from CV**.
4. Paste a 3-row CSV mixing mapped + 1 unknown code → resolve → commit → confirm parts appear.
5. Try the same CSV again without `?mode=replace` → expect inline 409 error + "Replace and import" CTA.
6. Click "Replace and import" → confirm prior modules wiped, new ones written.
7. Login as an editor user → confirm "Import from CV" button is hidden (RBAC).

---

#### Out of scope for #7b (verbatim from spec)

- **Real bin-packing optimiser.** v1 ships manual CutPlan creation in #7c.
- **Automatic re-sync from Cabinet Vision.** Every CV import is manually triggered.
- **Push-back into Cabinet Vision.** CV is closed. JoineryFlow never writes back.
- **Three-way merge of imports.** Re-importing onto an item with existing modules/parts is a 409 unless the Drafter passes `?mode=replace`.
- **CV API integration.** There is no CV server-side API to call.
- **`/cut-floor` page + Drafter Board tab + CutPlan/CutSchedule routes.** All deferred to **#7c**.
- **Sheet stock inventory.** Belongs to Shop Floor (#8).
- **Async / queued render of large CSVs.** Synchronous in v1; the 1 MB / 10k row caps keep latency under 5 seconds.

---

#### Review notes (for the reviewer of the resulting PR)

- The `cut_floor` RBAC row landing here (rather than in #7c) is intentional — see Risks and the spec ambiguity flagged in plan-prep. Removing the row in #7c to "rejoin the spec" would force a backwards-incompatible permission change on a public route. Leave it.
- The "Replace existing modules" checkbox in Phase C is the only UI difference from spec §7.2 (the spec showed an "existing data warning" with no inline toggle). The toggle is strictly more discoverable; no behaviour change at the route layer (still gated by `?mode=replace`).
- The `_preview_snapshot` key inside `cv_import_run.error_log` is the spec wording (§6.4) — the column name is misleading but renaming it now would touch 3 sub-projects' code. Defer to a post-#7c cleanup.
- All pytest counts include the prior #7a baseline. After #7b: expect roughly **334 + 33 = ~367 passing** (5 RBAC + 10 parser + 8 resolver + 15 routes − some shared fixture overhead).


## Implementation plan — 7c cut floor

### Implementation Plan — Cabinet Vision Integration #7c (CutPlan / CutSchedule + Board tab)

> **Status: shipped.** Migration `0019`. Current state lives in
> `## Cut Floor — CutPlan + CutSchedule + Board tab (sub-project #7c)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/archive/README.md`).

> **Later change:** The optimiser it reserves `POST /projects/{pid}/optimise` for shipped
> later, in #9.

> **Later change — extended by Plan V1 (see `docs/plan-v1/`).** `part_slot` and
> `parts` dimensions become the basis for **apportioning shared cutlist labour**
> to individual Joinery Items, weighted by each item's share of the parts on a
> cutlist (Q549) — since Plan V1 moves production stage completions onto the
> cutlist (Q445) while costs stay at item level (Q492).

**Spec:** `docs/archive/2026-05-05-cabinet-vision.md` (§1, §3.2, §4.3, §4.4, §7.3, §7.4, §8 — `0019_cut_floor.py`)
**Branch base:** `feat/foundation` (HEAD ahead of `cd4c57d` — #7b shipped).
**Migration introduced:** `0019_cut_floor.py`.
**RBAC module:** `cut_floor` (already in matrix from #7b).

---

#### 0. Context summary

Existing schema (migration 0003):

- `cut_plan(id, workspace_id, project_id, name, created_at)`
- `cut_sheet(id, cut_plan_id, sheet_no, material_sku)` — UNIQUE `(cut_plan_id, sheet_no)`
- `part_slot(id, cut_sheet_id, x, y, w, h, label)`
- `cut_schedule(id, cut_plan_id, scheduled_for, status)` — status CHECK already covers `planned|running|done|cancelled`

The PKs use `id`, not `cut_plan_id`. The plan respects that.

#7c additions:

- `part_slot.part_id` (nullable FK → `parts(part_id)` ON DELETE SET NULL)
- `cut_schedule.priority` (NOT NULL default 0), `assigned_to` (FK → `app_user`), `created_at`, `created_by`, `updated_at`
- `cut_plan.created_by`, `cut_plan.notes`
- Indexes: `idx_part_slot_part`, `idx_cut_schedule_date_priority`

Backend module `apps/api/app/cut_floor/` ships **CutPlan** + **CutSchedule** routes only — CV-import lives in `apps/api/app/cv/`. Both gate on `("cut_floor", action)`.

Web ships **Board tab** (item editor) and **/cut-floor** page (top-level Machine team daily view).

---

#### 1. Tasks

##### Backend

1. **Migration `0019_cut_floor.py`** — apply all column adds + indexes from §8.
2. **Schemas** at `apps/api/app/cut_floor/schemas.py`: `PartSlotIn`, `CutSheetIn`, `CutPlanIn`, `CutPlanOut`, `CutPlanSummary`, `CutSheetOut`, `PartSlotOut`, `ItemCutPlanOut`, `CutScheduleIn`, `CutSchedulePatchIn`, `ReorderIn`, `CutScheduleOut`. Pydantic v2.
3. **Queries** at `apps/api/app/cut_floor/queries.py` — `text()` SQL, workspace-isolated everywhere via `cut_plan.workspace_id`.
4. **Routes** at `apps/api/app/cut_floor/routes.py`:
   - `POST /projects/{pid}/cut-plans` — single transaction; insert `cut_plan` + `cut_sheet`s + `part_slot`s. Audit `cut_plan.create`.
   - `GET /projects/{pid}/cut-plans` — list newest first.
   - `GET /cut-plans/{plan_id}` — full plan + sheets + slots.
   - `GET /items/{iid}/cut-plan` — pick latest `cut_plan` for the item's project; return only sheets that contain ≥1 slot for this item; flag foreign slots `is_foreign=true`.
   - `DELETE /cut-plans/{plan_id}` — 409 when any non-cancelled `cut_schedule` references the plan; otherwise hard delete (CASCADE).
   - `GET /cut-schedules?date=YYYY-MM-DD&project_id=&status=` — daily list ordered by `priority ASC`. `project_id` is optional; defaults to all projects in workspace.
   - `GET /cut-schedules/{sid}` — single row with embedded plan summary.
   - `POST /cut-schedules` — body `{cut_plan_id, scheduled_for, assigned_to?}`. Auto `priority = MAX(priority WHERE same date) + 100` (or `100` if no rows). Audit `cut_schedule.create`.
   - `PATCH /cut-schedules/{sid}` — partial update. Status transitions enforced: `planned→running`, `running→done`, `planned→cancelled`, `running→cancelled`. Anything else 409. Audit `cut_schedule.update` + `cut_schedule.status_change` when status changes.
   - `POST /cut-schedules/reorder` — body `{scheduled_for, ordered_ids}`. Server rewrites priorities `100, 200, …`. Audit `cut_schedule.reorder`.
   - `DELETE /cut-schedules/{sid}` — soft-cancel (sets `status='cancelled'`). Audit `cut_schedule.cancel`.
5. **Mount router** in `apps/api/app/main.py`.

##### Tests

6. **Pytest** at `apps/api/tests/test_cut_floor_routes.py`:
   - CutPlan create transaction (sheets + slots inserted; rollback when invalid).
   - `GET /items/{iid}/cut-plan` returns only relevant sheets, marks foreign slots.
   - CutPlan delete with active schedule → 409; with cancelled-only schedule → succeeds.
   - CutSchedule auto-priority on create.
   - CutSchedule status transition matrix (allowed + denied).
   - CutSchedule reorder rewrites dense `100, 200, 300`.
   - Workspace isolation: cross-workspace GET → 404.
   - RBAC: viewer 403 on POST; purchase_officer 403 on POST.

##### Web

7. **Item editor — Board tab**:
   - Add `'board'` between `'hardware'` and `'log'` in `EditorTabs.tsx` `TABS` + `TAB_LABELS`.
   - New `BoardTab.tsx` fetches `/api/items/{id}/cut-plan` and renders one SVG per sheet. Slots from this item highlighted; foreign slots dimmed. Header line + empty state per spec §7.3.
   - Wire from `apps/web/app/(app)/items/[id]/page.tsx`.
8. **/cut-floor page**:
   - `apps/web/app/(app)/cut-floor/page.tsx` (server component) renders `CutFloorClient` with role-gated actions.
   - `_components/ScheduleList.tsx` — date picker (forward/back), project filter chip, sortable list.
   - `_components/ScheduleRow.tsx` — status pill + plan name + assigned-to + Start/Done/Cancel buttons. HTML5 drag-reorder.
   - `_components/AddPlanDialog.tsx` — pick CutPlan (newest 50, all workspace projects) + assigned-to (workspace users) + scheduled_for.
   - Server proxies through existing `app/api/[...proxy]/route.ts`.
9. **SideBar entry** — add `Cut Floor` link visible to `cut_floor.read` users.

##### Seed + docs

10. **Seed** (`seed/hartwood_joinery.py`): one `cut_plan` "ALF-001 v1 nest" with 1 sheet of 2440×1220 + 8 part_slots covering 6 of the 9 imported parts; 2 `cut_schedule` rows (one `running` for today, one `planned` for tomorrow). Idempotent — `DELETE FROM cut_plan WHERE project_id = …` first.
11. **CLAUDE.md** — add a `## Cabinet Vision integration — CutPlan + CutSchedule (sub-project #7c)` section summarising: migration 0019, the two new top-level + tab surfaces, the route table, status machine, soft-cancel semantics, foreign-slot rendering.

##### Verification

12. `make migrate` (apply 0019) + `make test` (Docker pytest) + `make e2e-docker` smoke (existing specs unaffected).

---

#### 2. Status transitions (binding)

```
planned   ──► running  ──► done
   │             │
   └──► cancelled └──► cancelled
```

Any other transition (e.g. `done → running`, `cancelled → running`) returns 409 with `{code: "BAD_TRANSITION"}`.

`DELETE /cut-schedules/{sid}` is **soft-cancel** — sets status to `cancelled`. A second DELETE on an already-cancelled row is a 409.

---

#### 3. Foreign-slot rendering rules

For `GET /items/{iid}/cut-plan`:

1. Find `cut_plan_id = MAX(id) WHERE project_id = (SELECT project_id FROM items WHERE item_id = :iid)` (workspace-scoped).
2. If none, return `{plan: null, sheets: []}`.
3. Find every `cut_sheet` that has ≥1 `part_slot.part_id IN (SELECT part_id FROM parts JOIN modules USING(module_id) WHERE item_id = :iid)`.
4. Return all slots on those sheets — flag `is_foreign=true` for slots whose `part_id` is not for this item (or null).
5. Slot label fallback: `slot.label` when set, else `part_name` joined from `parts`, else `"slot {id}"`.

UI: foreign slots `--h-line` 30%, this-item slots `--h-accent` 60%. Tooltip = label.

---

#### 4. Out of scope (deferred)

- Bin-packing optimiser (POST `/projects/{pid}/optimise`) — separate sub-project.
- CutPlan edit UI — v1 is create + delete + replace by creating a new plan.
- Real-time WebSocket schedule updates.
- @dnd-kit/core — start with HTML5 DnD; revisit only if QA flags UX.
- Mobile UI for `/cut-floor`.
- `cut_plan.is_current` flag — defer; Board tab uses `MAX(id)`.
- Export CutSchedule to PDF — defer.

---

#### 5. Audit events shipped

- `cut_plan.create`, `cut_plan.delete`
- `cut_schedule.create`, `cut_schedule.update`, `cut_schedule.status_change`, `cut_schedule.reorder`, `cut_schedule.cancel`

All routed through `apps/api/app/auth/audit.py::write_audit`.

---

#### 6. Exit criteria

- 0019 applies cleanly on top of 0018; downgrade is the no-op pattern matching prior migrations.
- ≥6 new pytest cases pass; existing #7b CV-import tests still pass.
- `/cut-floor?date=today` lists the 1 running + 1 planned seed schedules in priority order.
- Board tab on ALF-001 item 1 renders the seeded sheet with 6 highlighted + 2 foreign slots.
- RBAC: viewer/purchase_officer can read but cannot mutate `/cut-floor`; drafter/manager/admin can.

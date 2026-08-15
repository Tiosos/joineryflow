# JoineryFlow CV Import Wizard Implementation Plan

> **Status: shipped.** Migration `0018`. Current state lives in
> `## CV Import wizard (sub-project #7b)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/superpowers/plans/README.md`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Date:** 2026-05-05
**Sub-project:** #7b — CV Import wizard (the second slice of #7 Cabinet Vision Integration)
**Spec:** `docs/superpowers/specs/2026-05-05-cabinet-vision-design.md` — read §1 (scope items 1, 4, 8), §2.1 (backend layout — `apps/api/app/cv/`), §3.1 (`cv_import_run`), §4.2 (CV import routes), §5 (RBAC — `cut_floor` row), §6 (CSV import workflow detail end-to-end), §7.2 (Cutlist tab Import dialog), §8 (migration 0018 portion only), §9 (seed updates limited to cv_import_run + import demo), §10.1 (test plan — `test_cv_parser.py`, `test_cv_resolver.py`, `test_cv_routes.py`).
**Branch base:** `feat/foundation` after #7a merge (HEAD `83fe558`; latest migration on disk is `0017_catalog_enrichment.py`).
**Baseline:** 334 passed, 1 skipped, 0 failed (verified 2026-05-07).

---

## Goal

Ship the **CV CSV import wizard** that turns a Cabinet Vision part-list export into Modules + Parts under a Drafter Editor item, in one transaction, with a 3-phase preview / resolve / commit UX. By the end of this slice, a Drafter (or any drafter+/manager+/admin) can:

1. Open `/items/{id}?tab=cutlist`, click **"Import from CV"** in the Cutlist toolbar.
2. **Phase A (Upload):** Paste CSV text *or* pick a file ≤ 1 MB, click **Preview**. Backend parses headers, normalises rows, resolves every `material_code` through `cv_material_mapping` → catalog `synonyms[]` → catalog `sku`, and returns a `CvPreviewOut` payload listing every row classified as `mapped` / `synonym_match` / `unknown` / `invalid`. A `cv_import_run` row with `status='preview'` is persisted.
3. **Phase B (Resolve unknowns):** UI lists every `unknown` row with three inline actions — **Use existing** (typeahead across all 6 catalog tables), **Create new** (5 simple tables only — equipment_hire disabled with a tooltip linking to `/catalog`), **Skip**. Picks of "Use existing" auto-write a `cv_material_mapping` row on commit.
4. **Phase C (Commit):** Confirmation panel "Import {n} parts in {m} modules under Item ALF-001-ITEM-1." When the item already has modules, the panel shows a **"Replace existing modules"** checkbox; unchecked + existing data → 409, checked → wipes modules (CASCADE) before commit. On commit, single transaction: insert new catalog rows from "Create new" picks, write `cv_material_mapping` rows for each "Use existing" pick, insert Modules + Parts, set `cv_import_run.status='committed'`, write audit + item_edit_log.
5. View import history via `GET /items/{iid}/cv-imports` (rendered later in #7c — for #7b the route exists but is consumed only by tests).

#7b does **not** ship: catalog enrichment / Mappings UI (already in #7a), CutPlan / CutSchedule / Board tab / `/cut-floor` page (deferred to **#7c**), bin-packing optimiser (indefinite), three-way merge re-import UI (indefinite), Cabinet Vision API integration (indefinite — CV is closed).

---

## Outcome

- One DB migration (`0018_cv_import.py`) creates `cv_import_run` per spec §3.1 with the two indexes (`idx_cv_import_run_item`, `idx_cv_import_run_status`).
- One new `cut_floor` module is added to the RBAC matrix in `apps/api/app/auth/permissions.py`. Drafter / manager / admin get `{read, write, approve, comment}`. Editor gets `{read, write, comment}`. Purchase officer gets `{read}`. Viewer gets `{read}`. (Spec §5.) #7b adds the row, ships **no** UI for `cut_floor` yet — the row is consumed only by the CV import routes here, then reused by #7c without redeclaration.
- One new backend module `apps/api/app/cv/` (parser + resolver + queries + routes + schemas) — 4 routes wired into `apps/api/app/main.py` after the catalog router.
- One new client component `CvImportDialog.tsx` mounted in the Cutlist tab toolbar, plus a small `UnknownCodeRow.tsx` and `CreateCatalogRowMiniForm.tsx`. URL state: `/items/{id}?tab=cutlist&import=cv` opens the dialog deep-linkably.
- Seed extension: adds 1 demo `cv_import_run` (committed) on ALF-001 item 1. Idempotent.
- Tests: `test_cv_parser.py` (~10 cases), `test_cv_resolver.py` (~8 cases), `test_cv_routes.py` (~15 cases), and 5 new `cut_floor`-row entries appended to `test_permissions.py`. Plus a Playwright `tests/e2e/cv_import.spec.ts` happy-path (Scenario A from spec §10.2).
- CLAUDE.md gets a new "CV Import wizard (sub-project #7b)" subsection mirroring the prior sub-project entries.

## Risks

- **Unknown vs. invalid classification ambiguity.** A row with a mistyped numeric (`len_mm = "abc"`) AND an unknown `material_code` is classified as `invalid` — invalid wins. The parser produces structured errors first; the resolver only sees rows that parsed cleanly. Mitigation: parser returns `(parsed_parts, errors, row_count)`; the resolver is a pure function over the parsed-parts stream.
- **Phase B "Create new" mini-form scope creep.** Each of the 5 simple catalog tables has slightly different required columns (`board_materials.code`, `custom_made.internal_ref`, `benchtop_materials.slab_id`, `appliances.model_number`, `hardware_materials.sku`). Mitigation: the mini-form auto-derives the legacy NOT NULL UNIQUE column from the entered `sku` (mirrors the catalog routes' insert behaviour). `equipment_hire` requires a `project_id` FK and is *disabled* in the mini-form — the row text says **"Open `/catalog` to add an Equipment Hire row, then return."**
- **Preview snapshot storage location.** Per spec §6.4 the full `CvPreviewOut` lives in `cv_import_run.error_log['_preview_snapshot']`. This conflates "errors" with "preview cache" but matches the spec; the column name is misleading rather than the schema being wrong. We keep the spec wording. (Future cleanup: rename column to `state_snapshot jsonb` after #7c.)
- **Re-import 409 semantics.** Default behaviour: 409 if the item already has any modules or parts. `?mode=replace` wipes via DELETE-CASCADE. The web confirm dialog shows the "Replace existing modules" checkbox **only when** the preview detects the item has existing modules, so the drafter cannot accidentally wipe. The check is evaluated server-side, not client-side, on every commit.
- **CSV size cap = 1 MB / 10 000 logical rows.** A real Hartwood item rarely exceeds 100 parts; 1 MB is generous. Files above the cap return 415 with `code=FILE_TOO_LARGE`. Counted *before* parsing to avoid OOM.
- **`cut_floor` module landing in #7b before its UI ships in #7c.** The module appears in the matrix with no top-level `/cut-floor` page yet. Test guard: `test_permissions.py` asserts the `cut_floor` row in every role; integration test `test_cv_routes.py::test_drafter_can_preview_and_commit` exercises the gate.
- **Synonym lookup must use `:code = ANY(synonyms)`** (NOT `synonyms @> ARRAY[:code]`, which Postgres does not push down through ANY() in older planner versions). The resolver SQL uses `WHERE :code = ANY(synonyms) AND archived_at IS NULL`.

---

## Pre-flight checklist

- [ ] Confirm clean working tree: `git status` shows only `.gitignore`, `.claude/`, `.pnpm-store/`, and `docs/superpowers/specs/2026-05-05-shop-floor-design.md` (the parallel Shop Floor spec — untouched by #7b).
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

## File structure (locked)

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

docs/superpowers/plans/
  2026-05-05-cabinet-vision-7b-cv-import.md  # this file

CLAUDE.md                     # MODIFY: append "CV Import wizard (sub-project #7b)" subsection
```

---

## Phase 1 — Schema + RBAC (3 tasks)

### Task 1: Migration 0018 — `cv_import_run`

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

### Task 2: Add `cv_import_run` to `TRUNCATE_TABLES`

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

### Task 3: RBAC matrix — add `cut_floor` module

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

## Phase 2 — Backend parser + resolver (3 tasks)

### Task 4: `apps/api/app/cv/schemas.py`

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

### Task 5: `apps/api/app/cv/parser.py`

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

### Task 6: `apps/api/app/cv/resolver.py`

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

## Phase 3 — Backend queries + routes (3 tasks)

### Task 7: `apps/api/app/cv/queries.py`

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

### Task 8: `apps/api/app/cv/routes.py` — preview + commit

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

### Task 9: `apps/api/app/cv/routes.py` — history GET endpoints

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

## Phase 4 — Tests (3 tasks)

### Task 10: `apps/api/tests/test_cv_parser.py`

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

### Task 11: `apps/api/tests/test_cv_resolver.py`

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

### Task 12: `apps/api/tests/test_cv_routes.py`

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

## Phase 5 — Web UI (4 tasks)

### Task 13: `apps/web/lib/cv-types.ts` + `apps/web/lib/cv-fetch.ts`

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

### Task 14: `CvImportDialog.tsx` — Phase A (Upload) + dialog shell

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

### Task 15: `CvImportDialog.tsx` — Phase B (Resolve)

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

### Task 16: `CvImportDialog.tsx` — Phase C (Commit) + done

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

## Phase 6 — Seed + E2E + Docs (3 tasks)

### Task 17: Seed — add 1 committed `cv_import_run` for ALF-001 item 1

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

### Task 18: E2E happy-path — `tests/e2e/cv_import.spec.ts`

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

### Task 19: CLAUDE.md update

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

## Verification — full sweep

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

## Out of scope for #7b (verbatim from spec)

- **Real bin-packing optimiser.** v1 ships manual CutPlan creation in #7c.
- **Automatic re-sync from Cabinet Vision.** Every CV import is manually triggered.
- **Push-back into Cabinet Vision.** CV is closed. JoineryFlow never writes back.
- **Three-way merge of imports.** Re-importing onto an item with existing modules/parts is a 409 unless the Drafter passes `?mode=replace`.
- **CV API integration.** There is no CV server-side API to call.
- **`/cut-floor` page + Drafter Board tab + CutPlan/CutSchedule routes.** All deferred to **#7c**.
- **Sheet stock inventory.** Belongs to Shop Floor (#8).
- **Async / queued render of large CSVs.** Synchronous in v1; the 1 MB / 10k row caps keep latency under 5 seconds.

---

## Review notes (for the reviewer of the resulting PR)

- The `cut_floor` RBAC row landing here (rather than in #7c) is intentional — see Risks and the spec ambiguity flagged in plan-prep. Removing the row in #7c to "rejoin the spec" would force a backwards-incompatible permission change on a public route. Leave it.
- The "Replace existing modules" checkbox in Phase C is the only UI difference from spec §7.2 (the spec showed an "existing data warning" with no inline toggle). The toggle is strictly more discoverable; no behaviour change at the route layer (still gated by `?mode=replace`).
- The `_preview_snapshot` key inside `cv_import_run.error_log` is the spec wording (§6.4) — the column name is misleading but renaming it now would touch 3 sub-projects' code. Defer to a post-#7c cleanup.
- All pytest counts include the prior #7a baseline. After #7b: expect roughly **334 + 33 = ~367 passing** (5 RBAC + 10 parser + 8 resolver + 15 routes − some shared fixture overhead).

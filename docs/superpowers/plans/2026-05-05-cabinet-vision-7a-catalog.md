# JoineryFlow Catalog Enrichment + CV Mappings UI Implementation Plan

> **Status: shipped.** Migration `0017`. Current state lives in
> `## Catalog enrichment + CV Mappings (sub-project #7a)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/superpowers/plans/README.md`).

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
**Spec:** `docs/superpowers/specs/2026-05-05-cabinet-vision-design.md` — read §1 (scope), §2.1 (backend layout), §3.1–3.4 (catalog enrichment + `cv_material_mapping`), §4.1 (catalog routes incl. CV mappings), §5 (RBAC), §7.1 (`/catalog` page UI), §8 (migration 0017 portion only), §9 (seed updates limited to catalog enrichment + 2 cv_material_mapping rows).
**Branch base:** `feat/foundation` (HEAD `2f72c89`; latest migration on disk is `0016_sample.py`).

---

## Goal

Ship the **catalog write-side** that everything else in #7 depends on. By the end of this slice, a Drafter (or any drafter+/manager+/admin) can:

1. Open `/catalog` and see a 7-tab strip (Board · Hardware · Custom · Benchtop · Appliances · Equipment Hire · CV Mappings).
2. Edit a row inline (description / sku / supplier / lead time / synonyms) — saves on blur.
3. Add new rows via a per-tab "+ New" button. Equipment-hire requires a project picker; the other five do not.
4. Bulk-import a CSV (3-line preview) — single-transaction all-or-nothing — and see `{created, errors}` in the dialog.
5. Soft-archive a row (sets `archived_at` + `archived_by`); the archived toggle in the filter strip controls visibility.
6. Open the **CV Mappings** subtab and CRUD `cv_material_mapping` rows that translate freeform CV codes (e.g. `18-PB`, `700.0KC2.054.00`) to a `(target_material_table, target_material_id)` pair. Hard-delete here is fine; the table has no downstream references in #7a.

#7a does **not** ship: the CV CSV preview/commit wizard (deferred to **#7b**), `cv_import_run` register (deferred to **#7b**), CutPlan/CutSchedule + Board tab + `/cut-floor` page (deferred to **#7c**), or the bin-packing optimiser (indefinite).

---

## Outcome

- One DB migration (`0017_catalog_enrichment.py`) adds five enrichment columns to all six catalog tables (`synonyms text[]`, `default_supplier varchar(128)`, `default_lead_time_days int`, `archived_at timestamptz`, `archived_by bigint REFERENCES app_user(id)`), plus a GIN index on `synonyms` and a partial active-row index, on each. It also CREATEs `cv_material_mapping` with its UNIQUE + index per spec §3.1.
- One new `catalog` module is added to the RBAC matrix in `apps/api/app/auth/permissions.py`. Drafter/manager/admin get `{read, write, approve, comment}`. Editor gets `{read, write, comment}`. Purchase officer gets `{read, comment}`. Viewer gets `{read}`. (See spec §5 + §5.1 + §5.2.)
- One new backend module `apps/api/app/catalog/` (routes + queries + schemas) — 7 sub-routers (one per material type + one for `cv-mappings`) wired into `apps/api/app/main.py`.
- One new web page `/catalog` with 7 tabs + filter strip + editable grid + bulk-import dialog + Mappings panel; one new SideBar entry; two new lib helpers (`catalog-types.ts`, `catalog-fetch.ts`).
- Seed extension: enriches the existing 2 `board_materials` + 4 `hardware_materials` rows with `synonyms[]` + `default_supplier`, adds 4 more `board_materials` demo rows, and inserts 2 demo `cv_material_mapping` rows. Idempotent.
- Tests: `test_catalog_routes.py` (~25 cases), `test_cv_mapping_routes.py` (~10 cases), `test_catalog_workspace_isolation.py` (~6 cases), and 5 new `isample`-style entries appended to `test_permissions.py` for the new module. Plus a Playwright `tests/e2e/catalog.spec.ts` happy-path.
- CLAUDE.md gets a new "Catalog enrichment + CV Mappings (sub-project #7a)" subsection mirroring the iSample/PDF/Procurement entries.

## Risks

- **Per-table column shape divergence.** Each of the six catalog tables has a different legacy NOT NULL UNIQUE column from migration 0007 (`code` on board, `internal_ref` on custom_made, `slab_id` on benchtop, `model_number` on appliance, `contract_ref` on equipment_hire; hardware natively uses `sku`). The enrichment columns are the *same* across all six, but the per-table CRUD must continue to honour the legacy NOT NULL constraints. Mitigation: a single `REGISTRY` dict (mirroring `apps/api/app/procurement_v1/catalogs/queries.py` lines 19–56) drives every sub-router. The plan reuses the existing `(table, id_col, select_cols, insertable_cols)` shape and **extends** `select_cols` + `insertable_cols` with the five new enrichment columns per row.
- **`equipment_hire` is special.** Its PK is `hire_id` (not `material_id`) and it requires a `project_id` FK on insert. The web bulk-import + "+ New" UI must show a project picker only on this tab.
- **Procurement-side `/catalogs/*` already exists.** The existing module at `apps/api/app/procurement_v1/catalogs/` is gated by `("orderbook", *)`; it stays untouched. The new `/catalog/*` (singular) routes are a parallel surface gated by `("catalog", *)`. **Do not** rewire procurement to the new module — the procurement queue UI still depends on its current path. (The two surfaces will converge in a future cleanup; that is out of scope for #7a.)
- **GIN index on `synonyms`.** Postgres GIN over `text[]` requires `ANY(:code) ILIKE` style lookups in #7b's resolver. We add the index now to keep #7b cheap; it has zero impact on #7a write paths but does cost ~200 ms of migration time on a fresh seed.
- **Workspace isolation regression.** All six catalog tables already have `workspace_id`. The new `cv_material_mapping` table is workspace-scoped via `workspace_id` FK. Every read + write path must filter on `workspace_id = :w` from `AuthUser`. Mitigation: `test_catalog_workspace_isolation.py` covers cross-workspace 404 on every sub-router.

---

## Pre-flight checklist

- [ ] Confirm working tree is clean: `git status` shows only `.gitignore`, `.claude/`, and `.pnpm-store/` (per the conversation start snapshot).
- [ ] Confirm branch: `git rev-parse --abbrev-ref HEAD` → `feat/foundation`.
- [ ] Confirm latest migration on disk: `ls db/alembic/versions/ | sort | tail -3` → `0014_*`, `0015_*`, `0016_sample.py`.
- [ ] Confirm baseline pytest: `docker compose exec api pytest -q` → expected pass count from CLAUDE.md (≥ 261 passing).
- [ ] Confirm `make up` is current: `docker compose ps` shows `api`, `db`, `web` all `Up`.
- [ ] Read spec §1, §3.1–3.4, §4.1, §5, §7.1, §8, §9 once before starting.
- [ ] Read sibling code: `apps/api/app/procurement_v1/catalogs/{queries.py,routes.py}` (the structural template), `apps/api/app/samples/queries.py` (workspace-isolation pattern), and `apps/api/app/samples/routes.py` (RBAC + error mapping).

---

## File structure (locked)

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

docs/superpowers/plans/
  2026-05-05-cabinet-vision-7a-catalog.md  # this file

CLAUDE.md                               # MODIFY: append Catalog (#7a) subsection
```

---

## Phase 1 — Schema + RBAC (3 tasks)

### Task 1: Migration 0017 — catalog enrichment + `cv_material_mapping`

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

### Task 2: Add `cv_material_mapping` to `TRUNCATE_TABLES`

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

### Task 3: RBAC matrix — add `catalog` module

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

## Phase 2 — Backend module (6 tasks)

### Task 4: Pydantic schemas (`apps/api/app/catalog/schemas.py`)

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

### Task 5: Queries layer (`apps/api/app/catalog/queries.py`)

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

### Task 6: Routes layer (`apps/api/app/catalog/routes.py`)

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

### Task 7: Pytest — `test_catalog_routes.py`

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

### Task 8: Pytest — `test_cv_mapping_routes.py`

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

### Task 9: Pytest — `test_catalog_workspace_isolation.py`

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

## Phase 3 — Web layer (5 tasks)

### Task 10: Lib helpers (`catalog-types.ts` + `catalog-fetch.ts`)

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

### Task 11: `/catalog` page shell + tabs + grid

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

### Task 12: Bulk import dialog

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

### Task 13: Mappings panel

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

## Phase 4 — Seed + e2e + docs (2 tasks)

### Task 14: Seed extension

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

### Task 15: Playwright e2e + CLAUDE.md

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
- `docs/superpowers/specs/2026-05-05-cabinet-vision-design.md` — Cabinet Vision Integration spec (sub-projects #7a + #7b + #7c).
- `docs/superpowers/plans/2026-05-05-cabinet-vision-7a-catalog.md` — 15-task implementation plan for sub-project #7a.
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

## Definition of done

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

## Risks + mitigations recap

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

## Out-of-band follow-ups (deferred to #7b/#7c)

- **#7b — CV Import wizard:** migration 0018 (`cv_import_run`), `apps/api/app/cv/{routes,queries,parser,resolver,schemas}.py`, the 3-phase preview/commit dialog inside the Cutlist tab, the Phase B unknown-codes UI that auto-writes new `cv_material_mapping` rows on resolve. Depends on #7a's `cv_material_mapping` register + `synonyms[]` columns.
- **#7c — CutPlan / CutSchedule + Board tab:** migration 0019 (`part_slot.part_id`, `cut_schedule` enrichment, `cut_plan` metadata), `apps/api/app/cut_floor/`, the `/cut-floor` page, the Drafter Editor Board tab, the `cut_floor` RBAC module. Independent of #7a/#7b mechanically; sequenced after for review bandwidth.
- **Procurement-side `/catalogs/*` retirement:** future cleanup pass to converge the two parallel catalog surfaces. Not blocked by #7a.

**End of plan.**

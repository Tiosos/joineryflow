# JoineryFlow Procurement Workbench v1 Implementation Plan

> **Status: shipped.** Migration `0012`. Current state lives in
> `## Procurement Workbench (sub-project #4)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/superpowers/plans/README.md`).

> **Later change — Phase 4 is retired.** The `/catalogs/{type}` surface it specifies was
> removed in `64ef89e` — it duplicated the six catalog tables under the
> `orderbook` gate, without workspace scoping, and hard-deleted rows. Those
> tables are served only by `/catalog/*` (#7a).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Later change — superseded in part by Plan V1 (see `docs/plan-v1/`).** An
> **order layer is added above batches**: orders carry the commercial record
> (supplier, PO number, cost) and `procurement_batches` + `batch_allocations`
> remain beneath as the allocation mechanism (Q504), covering **all**
> procurement rather than just related parts (Q507). The legacy `/procurement/*`
> namespace this plan left untouched is **revived and converged** for that work
> (Q502) — which requires adding workspace scoping to its 9 tables, since they
> have none. **Supplier becomes a real entity** and the catalog tables' free-text
> supplier columns repoint to it (Q506).

**Goal:** Ship sub-project #4 — the Procurement Workbench v1 — on top of the merged PM Workbench branch. A PM (or Drafter, who is elevated to PM-parity for `orderbook` in this sub-project) clicks the "0 ready / 2 blocked" availability chip on a tracking row, opens an item-scoped drawer, and either allocates from an existing batch or orders more — all in three clicks. A Procurement officer (`purchase_officer`) gets a cross-project queue at `/orderbook` for working across projects, and every project gets a `/projects/[id]/procurement` page with Materials, Batches, and Catalog tabs. End-to-end verifiable via one new Playwright spec.

**Spec:** `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md`. Read it before starting; this plan only sequences the implementation. The spec resolves all open product/RBAC questions.

**Architecture:** No new infrastructure. Same three-container docker-compose. One small migration (0012) adds `procurement_batches.cancelled_at` and two indexes. New backend module `apps/api/app/procurement_v1/` with five sub-routers — mounted at top-level paths to avoid colliding with the legacy `/procurement/*` namespace, which is left untouched and unused. New Next.js routes under `apps/web/app/(app)/{orderbook,projects/[id]/procurement}/` plus a client `AvailabilityDrawer` over `/tracking`. State management is raw `fetch()` + URL search params + controlled inputs — **no TanStack Query / React Hook Form / Zustand in v1.**

**Tech stack additions:** none. Reuses Foundation + PM Workbench stack (FastAPI + SQLAlchemy Core `text()` + Pydantic v2; Next.js 16 App Router + Tailwind v4; argon2-cffi; pytest; Playwright).

---

## File Structure (locked)

```
apps/api/app/
  procurement_v1/
    __init__.py
    materials/
      __init__.py
      routes.py            # GET /projects/{pid}/materials  +  GET /items/{iid}/availability
      queries.py
      schemas.py
    batches/
      __init__.py
      routes.py            # GET/POST /batches  +  GET/PATCH/DELETE /batches/{bid}
      queries.py
      schemas.py
    allocations/
      __init__.py
      routes.py            # GET/POST /batches/{bid}/allocations  +  PATCH/DELETE /allocations/{aid}
      queries.py
      schemas.py
    catalogs/
      __init__.py
      routes.py            # GET/POST /catalogs/{type}  +  GET/PATCH/DELETE /catalogs/{type}/{mid}
      queries.py
      schemas.py
    queue/
      __init__.py
      routes.py            # GET /procurement-queue
      queries.py
      schemas.py
  auth/
    permissions.py         # drafter row gains write+approve on orderbook
  main.py                  # mount 5 new routers
apps/api/tests/
  conftest.py              # extend TRUNCATE_TABLES with batches + allocations
  test_proc_v1_materials.py
  test_proc_v1_batches.py
  test_proc_v1_allocations.py
  test_proc_v1_catalogs.py
  test_proc_v1_queue.py
  test_permissions.py      # extend with elevated drafter on orderbook
  test_rbac_drafter.py     # extend matrix
db/alembic/versions/
  0012_proc_v1_supports.py # cancelled_at + indexes
seed/
  hartwood_joinery.py      # + procurement_batches + batch_allocations covering the demo
apps/web/app/(app)/
  orderbook/page.tsx                          # replaces stub: cross-project queue
  orderbook/_components/QueueClient.tsx
  projects/[id]/procurement/
    page.tsx                                  # tabs: Materials | Batches | Catalog
    _components/
      ProcurementTabs.tsx
      ProjectMaterialsTable.tsx
      BatchesTable.tsx
      BatchDrawer.tsx
      AllocationEditor.tsx
      CatalogTabs.tsx
  tracking/page.tsx                           # adds AvailabilityDrawer mount + chip handler
  tracking/_components/TrackingClient.tsx
apps/web/components/procurement/
  AvailabilityDrawer.tsx
  EtaPill.tsx
  ShortfallPill.tsx
  BatchStatusPill.tsx
  MaterialTypeTag.tsx
apps/web/components/pm/
  TrackingGrid.tsx                            # wrap availability cell in a button → drawer
apps/web/lib/
  procurement-types.ts
  procurement-fetch.ts
  tokens.ts                                   # + h-mono token mirror
apps/web/app/
  globals.css                                 # + .h-mono utility
tests/e2e/
  procurement.spec.ts                         # NEW
docs/superpowers/plans/
  2026-04-28-procurement-workbench.md         # this file
CLAUDE.md                                     # Procurement Workbench dev notes appended
```

---

## Phase 1 — Schema + RBAC + token (3 tasks)

### Task 1: Migration 0012 — `cancelled_at` + indexes

**Files:**
- Create: `db/alembic/versions/0012_proc_v1_supports.py`

- [ ] **Step 1: Write the migration**

Create `db/alembic/versions/0012_proc_v1_supports.py`:

```python
"""procurement_v1 supports: cancelled_at + supplier/allocation indexes

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-28
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    ALTER TABLE procurement_batches
      ADD COLUMN cancelled_at timestamptz;

    CREATE INDEX IF NOT EXISTS idx_batches_supplier
      ON procurement_batches (supplier);

    CREATE INDEX IF NOT EXISTS idx_alloc_batch
      ON batch_allocations (batch_id);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-procurement-v1 schema is recoverable from migrations 0001-0011 only")
```

- [ ] **Step 2: Apply the migration**

```bash
docker compose exec -w /db api alembic upgrade head
```

Expected output ends with `INFO  [alembic.runtime.migration] Running upgrade 0011 -> 0012`.

- [ ] **Step 3: Verify the column and indexes exist**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -c "\d+ procurement_batches" | grep -E "cancelled_at|idx_batches_supplier"
docker compose exec -T db psql -U postgres -d joineryflow -c "\di+ idx_alloc_batch"
```

Expected: `cancelled_at | timestamp with time zone`, `idx_batches_supplier`, `idx_alloc_batch` all printed.

- [ ] **Step 4: Re-seed and re-run pytest to confirm no regressions**

```bash
docker compose exec api python -m seed.hartwood_joinery
docker compose exec api pytest -q
```

Expected: `116 passed`.

- [ ] **Step 5: Commit**

```bash
git add db/alembic/versions/0012_proc_v1_supports.py
git commit -m "feat(db): migration 0012 — procurement_batches.cancelled_at + supplier/allocation indexes"
```

---

### Task 2: Elevate `drafter` on `orderbook` in the permissions matrix

**Files:**
- Modify: `apps/api/app/auth/permissions.py`
- Modify: `apps/api/tests/test_permissions.py`
- Modify: `apps/api/tests/test_rbac_drafter.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_permissions.py`:

```python
def test_drafter_orderbook_full_access():
    """Drafter is elevated to PM parity for the orderbook module in
    Procurement Workbench v1."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["orderbook"] == {"read", "write", "approve", "comment"}
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_permissions.py::test_drafter_orderbook_full_access -v
```

Expected: FAIL — currently `MATRIX["drafter"]["orderbook"] == {"read"}`.

- [ ] **Step 3: Update the matrix**

In `apps/api/app/auth/permissions.py`, change the `drafter` block (around line 44) so the `orderbook` row has the full action set:

```python
    "drafter": {
        "dashboard":     {"read"},
        "tracking":      {"read", "write", "approve", "comment"},
        "list":          {"read", "write", "approve", "comment"},
        "shop_dwgs":     {"read"},
        "isample":       {"read"},
        "orderbook":     {"read", "write", "approve", "comment"},
        "it_management": set(),
    },
```

- [ ] **Step 4: Run new test, confirm pass**

```bash
docker compose exec api pytest tests/test_permissions.py::test_drafter_orderbook_full_access -v
```

Expected: PASS.

- [ ] **Step 5: Extend `test_rbac_drafter.py`**

Append to `apps/api/tests/test_rbac_drafter.py`:

```python
def test_drafter_matrix_orderbook_write_and_approve():
    from app.auth.permissions import MATRIX
    assert "write"   in MATRIX["drafter"]["orderbook"]
    assert "approve" in MATRIX["drafter"]["orderbook"]
```

- [ ] **Step 6: Run the full suite to confirm no regressions**

```bash
docker compose exec api pytest -q
```

Expected: `118 passed` (116 prior + 2 new).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/auth/permissions.py apps/api/tests/test_permissions.py apps/api/tests/test_rbac_drafter.py
git commit -m "feat(rbac): elevate drafter to PM-parity on orderbook (procurement v1)"
```

---

### Task 3: Wire `.h-mono` utility for PO/date/$ columns

**Files:**
- Modify: `apps/web/app/globals.css`
- Modify: `apps/web/lib/tokens.ts`

- [ ] **Step 1: Add the utility class to globals.css**

In `apps/web/app/globals.css`, inside the existing `@layer utilities { … }` block (or append a new one if there is none), add:

```css
@layer utilities {
  .h-mono {
    font-family: var(--font-mono, ui-monospace, SFMono-Regular, "Roboto Mono", Menlo, Consolas, monospace);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.005em;
  }
}
```

- [ ] **Step 2: Mirror the token name in tokens.ts**

In `apps/web/lib/tokens.ts`, append a `mono` entry to the exported `H` object:

```ts
export const H = {
  // ...existing entries...
  mono: "h-mono",
} as const;
```

- [ ] **Step 3: Smoke-test the build**

```bash
docker compose exec web pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/globals.css apps/web/lib/tokens.ts
git commit -m "feat(web): add .h-mono utility for PO/date/money columns"
```

---

## Phase 2 — Material rollup API (3 tasks)

### Task 4: `procurement_v1` package skeleton + extend test fixtures

**Files:**
- Create: `apps/api/app/procurement_v1/__init__.py` (empty)
- Create: `apps/api/app/procurement_v1/{materials,batches,allocations,catalogs,queue}/__init__.py` (each empty)
- Modify: `apps/api/tests/conftest.py`

- [ ] **Step 1: Create the empty package tree**

```bash
mkdir -p apps/api/app/procurement_v1/{materials,batches,allocations,catalogs,queue}
for d in apps/api/app/procurement_v1 apps/api/app/procurement_v1/{materials,batches,allocations,catalogs,queue}; do
  : > "$d/__init__.py"
done
```

- [ ] **Step 2: Extend `TRUNCATE_TABLES`**

In `apps/api/tests/conftest.py`, replace the `TRUNCATE_TABLES` tuple with the following (FK-safe order — dependents before parents):

```python
TRUNCATE_TABLES = (
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
    "audit_log",
    "session",
    "app_user",
    "workspace",
)
```

- [ ] **Step 3: Verify**

```bash
docker compose exec api pytest -q
```

Expected: `118 passed`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/procurement_v1 apps/api/tests/conftest.py
git commit -m "chore(api): procurement_v1 package skeleton + truncate batches/allocations in tests"
```

---

### Task 5: `/projects/{pid}/materials` rollup endpoint

**Files:**
- Create: `apps/api/app/procurement_v1/materials/schemas.py`
- Create: `apps/api/app/procurement_v1/materials/queries.py`
- Create: `apps/api/app/procurement_v1/materials/routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_proc_v1_materials.py`

- [ ] **Step 1: Schemas**

Create `apps/api/app/procurement_v1/materials/schemas.py`:

```python
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel

MaterialType = Literal["BOARD", "HARDWARE", "CUSTOM", "BENCHTOP", "APPLIANCE", "HIRE"]
MaterialStatus = Literal["OK", "SHORT", "OVERDUE"]


class MaterialRow(BaseModel):
    material_type: MaterialType
    material_id: int
    name: str
    sku: str | None = None
    qty_demand: Decimal
    qty_on_order: Decimal
    qty_received: Decimal
    qty_allocated: Decimal
    shortfall: Decimal
    earliest_eta: date | None = None
    status: MaterialStatus


class ProjectMaterialsOut(BaseModel):
    project_id: int
    rows: list[MaterialRow]
```

- [ ] **Step 2: Write the failing tests**

Create `apps/api/tests/test_proc_v1_materials.py`:

```python
"""Tests for the project material rollup endpoint."""
import pytest
from sqlalchemy import text


@pytest.fixture
def golden_project(db, workspace_id):
    """3 items, 1 hardware catalog SKU, 2 batches with partial allocation.

    Demand:    item_hardware_lines.qty = 5  (one line, qty=5)
    Received:  batch A qty_received=3, batch B qty_received=0 (in transit, qty_ordered=4)
    Allocated: 2 of A's 3 received → line
    Expected rollup row:
      qty_demand=5, qty_on_order=4, qty_received=3, qty_allocated=2,
      shortfall = max(0, 5 - 3 - 4) = 0
    """
    pm_id = db.execute(text(
        "INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role,jtbd_role) "
        "VALUES(:w,'pm@t.test','PM','x','manager','PM') RETURNING id"
    ), {"w": workspace_id}).scalar()

    pid = db.execute(text(
        "INSERT INTO projects(workspace_id,project_code,name,pm_id) "
        "VALUES(:w,'P1','Project 1',:p) RETURNING project_id"
    ), {"w": workspace_id, "p": pm_id}).scalar()

    mat_id = db.execute(text(
        "INSERT INTO hardware_materials(material_name,sku) VALUES('Drawer slide 500mm','DS-500') RETURNING material_id"
    )).scalar()

    cat_id = db.execute(text(
        "INSERT INTO project_hardware_catalog(project_id,material_type,material_id,added_by) "
        "VALUES(:p,'HARDWARE',:m,:u) RETURNING catalog_id"
    ), {"p": pid, "m": mat_id, "u": pm_id}).scalar()

    item_id = db.execute(text(
        "INSERT INTO items(project_id,item_number,description,owner_id) "
        "VALUES(:p,1,'Test item',:u) RETURNING item_id"
    ), {"p": pid, "u": pm_id}).scalar()

    line_id = db.execute(text(
        "INSERT INTO item_hardware_lines(item_id,seq,qty,catalog_id) "
        "VALUES(:i,1,5,:c) RETURNING line_id"
    ), {"i": item_id, "c": cat_id}).scalar()

    bid_a = db.execute(text(
        "INSERT INTO procurement_batches(project_id,material_type,material_id,qty_ordered,qty_received,received_date) "
        "VALUES(:p,'HARDWARE',:m,3,3,CURRENT_DATE) RETURNING batch_id"
    ), {"p": pid, "m": mat_id}).scalar()

    db.execute(text(
        "INSERT INTO procurement_batches(project_id,material_type,material_id,qty_ordered,eta_date) "
        "VALUES(:p,'HARDWARE',:m,4,CURRENT_DATE + INTERVAL '7 days')"
    ), {"p": pid, "m": mat_id})

    db.execute(text(
        "INSERT INTO batch_allocations(batch_id,item_hardware_line_id,qty_allocated) "
        "VALUES(:b,:l,2)"
    ), {"b": bid_a, "l": line_id})

    db.commit()
    return {
        "workspace_id": workspace_id,
        "project_id":   pid,
        "user_id":      pm_id,
        "material_id":  mat_id,
        "item_id":      item_id,
        "line_id":      line_id,
    }


def test_project_materials_rollup(client, golden_project, login_as):
    login_as(golden_project["user_id"])
    r = client.get(f"/projects/{golden_project['project_id']}/materials")
    assert r.status_code == 200
    data = r.json()
    rows = data["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["material_type"] == "HARDWARE"
    assert row["name"] == "Drawer slide 500mm"
    assert row["sku"] == "DS-500"
    assert float(row["qty_demand"])    == 5
    assert float(row["qty_on_order"])  == 4
    assert float(row["qty_received"])  == 3
    assert float(row["qty_allocated"]) == 2
    assert float(row["shortfall"])     == 0
    assert row["status"] == "OK"
```

> `client` and `login_as` are existing fixtures in the conftest used by PM Workbench tests (e.g. `tests/test_items_routes.py`). If they have different names in your branch, mirror whatever those tests use — same idea: a TestClient + a helper that sets a session cookie for a given app_user id.

- [ ] **Step 3: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_proc_v1_materials.py -v
```

Expected: FAIL — endpoint does not exist (404).

- [ ] **Step 4: Implement the rollup query**

Create `apps/api/app/procurement_v1/materials/queries.py`:

```python
"""Project material rollup query.

ONE CTE-based SQL hits demand (hardware + board), batches, and allocations,
returning one row per (material_type, material_id). Catalog-name enrichment
is a per-type lookup against the 6 catalog tables.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

_ROLLUP_SQL = text(
    """
    WITH demand AS (
      SELECT phc.material_type, phc.material_id,
             SUM(ihl.qty) AS qty_demand
        FROM item_hardware_lines ihl
        JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
        JOIN items i                      ON i.item_id      = ihl.item_id
       WHERE i.project_id = :pid
       GROUP BY phc.material_type, phc.material_id

      UNION ALL

      SELECT 'BOARD', p.board_material_id, SUM(p.qty)
        FROM parts p
        JOIN modules m ON m.module_id = p.module_id
        JOIN items   i ON i.item_id   = m.item_id
       WHERE i.project_id = :pid
         AND p.board_material_id IS NOT NULL
       GROUP BY p.board_material_id
    ),
    batches AS (
      SELECT material_type, material_id,
             SUM(qty_ordered)
               FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS qty_on_order,
             SUM(qty_received)                                               AS qty_received,
             MIN(eta_date)
               FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS earliest_eta
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
      LEFT JOIN allocations a USING (material_type, material_id)
    """
)

# Catalog table per material_type → (table_name, id_col, name_col, sku_col-or-None)
_CATALOG_LOOKUP = {
    "BOARD":     ("board_materials",    "material_id", "material_name", "sku"),
    "HARDWARE":  ("hardware_materials", "material_id", "material_name", "sku"),
    "CUSTOM":    ("custom_made",        "material_id", "description",   "sku"),
    "BENCHTOP":  ("benchtop_materials", "material_id", "material_name", "sku"),
    "APPLIANCE": ("appliances",         "material_id", "model_name",    "sku"),
    "HIRE":      ("equipment_hire",     "material_id", "description",   None),
}


def project_material_rollup(db: Session, project_id: int) -> list[dict]:
    rows = db.execute(_ROLLUP_SQL, {"pid": project_id}).mappings().all()
    by_type: dict[str, list[int]] = {}
    for r in rows:
        by_type.setdefault(r["material_type"], []).append(r["material_id"])

    name_map: dict[tuple[str, int], tuple[str, str | None]] = {}
    for mt, ids in by_type.items():
        if not ids:
            continue
        table, id_col, name_col, sku_col = _CATALOG_LOOKUP[mt]
        sku_select = f", {sku_col}" if sku_col else ", NULL AS sku"
        sql = text(
            f"SELECT {id_col} AS material_id, {name_col} AS name {sku_select} "
            f"FROM {table} WHERE {id_col} = ANY(:ids)"
        )
        for row in db.execute(sql, {"ids": ids}).mappings():
            name_map[(mt, row["material_id"])] = (row["name"], row["sku"])

    today = db.execute(text("SELECT CURRENT_DATE")).scalar()

    out: list[dict] = []
    for r in rows:
        name, sku = name_map.get((r["material_type"], r["material_id"]), ("(unknown)", None))
        shortfall = float(r["shortfall"])
        eta = r["earliest_eta"]
        if shortfall > 0 and eta is not None and eta < today:
            status = "OVERDUE"
        elif shortfall > 0:
            status = "SHORT"
        else:
            status = "OK"
        out.append(
            {
                "material_type": r["material_type"],
                "material_id":   r["material_id"],
                "name":          name,
                "sku":           sku,
                "qty_demand":    r["qty_demand"],
                "qty_on_order":  r["qty_on_order"],
                "qty_received":  r["qty_received"],
                "qty_allocated": r["qty_allocated"],
                "shortfall":     r["shortfall"],
                "earliest_eta":  eta,
                "status":        status,
            }
        )
    return out
```

- [ ] **Step 5: Implement the route**

Create `apps/api/app/procurement_v1/materials/routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from ...projects.queries import get_project
from .queries import project_material_rollup
from .schemas import ProjectMaterialsOut

router = APIRouter(prefix="", tags=["procurement-v1"])


@router.get("/projects/{pid}/materials", response_model=ProjectMaterialsOut)
def get_project_materials(
    pid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    proj = get_project(db, project_id=pid, workspace_id=user.workspace_id)
    if proj is None:
        raise HTTPException(404, "Project not found")
    rows = project_material_rollup(db, project_id=pid)
    return {"project_id": pid, "rows": rows}
```

- [ ] **Step 6: Mount the router**

In `apps/api/app/main.py`, add the import and `include_router` call (preserve the existing imports/mounts):

```python
from .procurement_v1.materials.routes import router as proc_v1_materials_router
# ...
app.include_router(proc_v1_materials_router)
```

- [ ] **Step 7: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_materials.py -v
```

Expected: PASS.

- [ ] **Step 8: Add 404 + cross-workspace tests**

Append to `tests/test_proc_v1_materials.py`:

```python
def test_project_materials_404_for_unknown_project(client, login_as, golden_project):
    login_as(golden_project["user_id"])
    r = client.get("/projects/999999/materials")
    assert r.status_code == 404


def test_project_materials_workspace_isolated(db, client, login_as, golden_project):
    other_ws = db.execute(text(
        "INSERT INTO workspace(slug,name) VALUES('o','Other') RETURNING id"
    )).scalar()
    other_user = db.execute(text(
        "INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role,jtbd_role) "
        "VALUES(:w,'o@t.test','O','x','manager','PM') RETURNING id"
    ), {"w": other_ws}).scalar()
    db.commit()
    login_as(other_user)
    r = client.get(f"/projects/{golden_project['project_id']}/materials")
    assert r.status_code == 404
```

Run: `docker compose exec api pytest tests/test_proc_v1_materials.py -v`. Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/procurement_v1/materials apps/api/app/main.py apps/api/tests/test_proc_v1_materials.py
git commit -m "feat(api): GET /projects/{pid}/materials rollup endpoint"
```

---

### Task 6: `/items/{iid}/availability` per-line view

The endpoint already exists from PM Workbench (Task 12). This task **extends** the response with per-line procurement metadata so the AvailabilityDrawer renders without a second round-trip.

**Files:**
- Modify: `apps/api/app/items/queries.py` (function `get_item_availability`)
- Modify: `apps/api/app/items/schemas.py` (`AvailabilityLine`)
- Modify: `apps/api/tests/test_proc_v1_materials.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_proc_v1_materials.py`:

```python
def test_item_availability_includes_per_line_procurement(client, golden_project, login_as):
    login_as(golden_project["user_id"])
    r = client.get(f"/items/{golden_project['item_id']}/availability")
    assert r.status_code == 200
    data = r.json()
    assert "lines" in data
    assert len(data["lines"]) == 1
    line = data["lines"][0]
    assert float(line["qty_needed"])            == 5
    assert float(line["qty_received"])          == 3
    assert float(line["qty_on_order"])          == 4
    assert float(line["qty_allocated_to_line"]) == 2
    assert line["material_type"] == "HARDWARE"
    assert line["material_id"]   == golden_project["material_id"]
```

- [ ] **Step 2: Confirm fail**

```bash
docker compose exec api pytest tests/test_proc_v1_materials.py::test_item_availability_includes_per_line_procurement -v
```

Expected: FAIL — `qty_received` / `qty_on_order` / `qty_allocated_to_line` keys missing.

- [ ] **Step 3: Extend the schema**

In `apps/api/app/items/schemas.py`, find the existing `AvailabilityLine` model and add the four new fields. Final shape:

```python
class AvailabilityLine(BaseModel):
    line_id: int
    seq: int | None
    catalog_id: int
    material_type: Literal["BOARD","HARDWARE","CUSTOM","BENCHTOP","APPLIANCE","HIRE"]
    material_id: int
    qty_needed: Decimal
    qty_received: Decimal
    qty_on_order: Decimal
    qty_allocated_to_line: Decimal
    earliest_eta: date | None = None
    status: Literal["ready", "blocked"]
```

(If the existing schema doesn't have `material_type` / `material_id` / `seq` / `catalog_id` — add them too. They're useful regardless.)

- [ ] **Step 4: Extend the query**

In `apps/api/app/items/queries.py`, replace the body of `get_item_availability` with a query that joins to `procurement_batches` and `batch_allocations` via two `LATERAL` subqueries:

```python
_AVAIL_SQL = text(
    """
    SELECT ihl.line_id, ihl.seq, ihl.catalog_id, ihl.qty AS qty_needed,
           phc.material_type, phc.material_id,
           COALESCE(b.qty_received, 0) AS qty_received,
           COALESCE(b.qty_on_order, 0) AS qty_on_order,
           COALESCE(la.qty_allocated_to_line, 0) AS qty_allocated_to_line,
           b.earliest_eta,
           CASE
             WHEN COALESCE(la.qty_allocated_to_line,0) >= ihl.qty THEN 'ready'
             ELSE 'blocked'
           END AS status
      FROM item_hardware_lines ihl
      JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
      JOIN items i ON i.item_id = ihl.item_id
      LEFT JOIN LATERAL (
            SELECT
              SUM(qty_received) AS qty_received,
              SUM(qty_ordered) FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS qty_on_order,
              MIN(eta_date)    FILTER (WHERE received_date IS NULL AND cancelled_at IS NULL) AS earliest_eta
            FROM procurement_batches pb
            WHERE pb.project_id    = i.project_id
              AND pb.material_type = phc.material_type
              AND pb.material_id   = phc.material_id
      ) b ON TRUE
      LEFT JOIN LATERAL (
            SELECT SUM(ba.qty_allocated) AS qty_allocated_to_line
            FROM batch_allocations ba
            WHERE ba.item_hardware_line_id = ihl.line_id
      ) la ON TRUE
      WHERE ihl.item_id = :iid
      ORDER BY ihl.seq NULLS LAST, ihl.line_id
    """
)


def get_item_availability(db: Session, item_id: int) -> list[dict]:
    return [dict(r) for r in db.execute(_AVAIL_SQL, {"iid": item_id}).mappings()]
```

If the existing route currently aggregates `(ready, blocked)` counts on the side, leave that in place — it's still correct because every line now reports a `status` field with the same values.

- [ ] **Step 5: Confirm pass + no regressions**

```bash
docker compose exec api pytest tests/test_proc_v1_materials.py -v
docker compose exec api pytest -q
```

Expected: per-file 4 passed; overall green.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/items/queries.py apps/api/app/items/schemas.py apps/api/tests/test_proc_v1_materials.py
git commit -m "feat(api): item availability includes per-line procurement metadata"
```

---

## Phase 3 — Batches + Allocations API (4 tasks)

### Task 7: `/batches` CRUD

**Files:**
- Create: `apps/api/app/procurement_v1/batches/schemas.py`
- Create: `apps/api/app/procurement_v1/batches/queries.py`
- Create: `apps/api/app/procurement_v1/batches/routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_proc_v1_batches.py`

- [ ] **Step 1: Schemas**

Create `apps/api/app/procurement_v1/batches/schemas.py`:

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

MaterialType = Literal["BOARD","HARDWARE","CUSTOM","BENCHTOP","APPLIANCE","HIRE"]
BatchStatus  = Literal["OPEN","IN_TRANSIT","DELIVERED","CANCELLED"]


class BatchOut(BaseModel):
    batch_id: int
    project_id: int
    material_type: MaterialType
    material_id: int
    supplier: str | None = None
    po_ref: str | None = None
    qty_ordered: Decimal
    qty_received: Decimal
    cost_per_unit: Decimal | None = None
    ordered_date: date | None = None
    eta_date: date | None = None
    received_date: date | None = None
    cancelled_at: datetime | None = None
    notes: str | None = None
    status: BatchStatus
    qty_allocated: Decimal


class BatchListOut(BaseModel):
    batches: list[BatchOut]


class CreateBatchIn(BaseModel):
    project_id: int
    material_type: MaterialType
    material_id: int
    supplier: str | None = None
    po_ref: str | None = None
    qty_ordered: Decimal = Field(ge=0)
    qty_received: Decimal = Field(default=Decimal("0"), ge=0)
    cost_per_unit: Decimal | None = None
    ordered_date: date | None = None
    eta_date: date | None = None
    received_date: date | None = None
    notes: str | None = None


class PatchBatchIn(BaseModel):
    supplier: str | None = None
    po_ref: str | None = None
    qty_ordered: Decimal | None = None
    qty_received: Decimal | None = None
    cost_per_unit: Decimal | None = None
    ordered_date: date | None = None
    eta_date: date | None = None
    received_date: date | None = None
    notes: str | None = None
```

- [ ] **Step 2: Queries**

Create `apps/api/app/procurement_v1/batches/queries.py`:

```python
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session

_STATUS_CASE = (
    "CASE "
    "  WHEN cancelled_at  IS NOT NULL THEN 'CANCELLED' "
    "  WHEN received_date IS NOT NULL THEN 'DELIVERED' "
    "  WHEN ordered_date  IS NOT NULL THEN 'IN_TRANSIT' "
    "  ELSE 'OPEN' "
    "END"
)

_BATCH_COLS = (
    "batch_id, project_id, material_type, material_id, supplier, po_ref, "
    "qty_ordered, qty_received, cost_per_unit, "
    "ordered_date, eta_date, received_date, cancelled_at, notes, "
    f"{_STATUS_CASE} AS status, "
    "(SELECT COALESCE(SUM(qty_allocated),0) FROM batch_allocations a "
    "  WHERE a.batch_id = procurement_batches.batch_id) AS qty_allocated"
)


def list_batches(
    db: Session,
    *,
    workspace_id: int,
    project_id: int | None = None,
    supplier: str | None = None,
    status: str | None = None,
) -> list[dict]:
    sql = (
        f"SELECT {_BATCH_COLS} FROM procurement_batches "
        "JOIN projects p ON p.project_id = procurement_batches.project_id "
        "WHERE p.workspace_id = :w "
    )
    params: dict[str, Any] = {"w": workspace_id}
    if project_id is not None:
        sql += " AND procurement_batches.project_id = :pid"
        params["pid"] = project_id
    if supplier:
        sql += " AND procurement_batches.supplier ILIKE :s"
        params["s"] = supplier
    if status:
        sql += f" AND {_STATUS_CASE} = :st"
        params["st"] = status
    sql += (
        " ORDER BY COALESCE(procurement_batches.eta_date, procurement_batches.ordered_date,"
        "                   procurement_batches.created_at::date) ASC, batch_id ASC"
    )
    return [dict(r) for r in db.execute(text(sql), params).mappings()]


def get_batch(db: Session, *, batch_id: int, workspace_id: int) -> dict | None:
    sql = text(
        f"SELECT {_BATCH_COLS} FROM procurement_batches "
        "JOIN projects p ON p.project_id = procurement_batches.project_id "
        "WHERE batch_id = :bid AND p.workspace_id = :w"
    )
    row = db.execute(sql, {"bid": batch_id, "w": workspace_id}).mappings().first()
    return dict(row) if row else None


def create_batch(db: Session, *, payload: dict, project_id: int) -> int:
    sql = text(
        """
        INSERT INTO procurement_batches
          (project_id, material_type, material_id, supplier, po_ref,
           qty_ordered, qty_received, cost_per_unit,
           ordered_date, eta_date, received_date, notes)
        VALUES
          (:project_id, :material_type, :material_id, :supplier, :po_ref,
           :qty_ordered, :qty_received, :cost_per_unit,
           :ordered_date, :eta_date, :received_date, :notes)
        RETURNING batch_id
        """
    )
    return db.execute(sql, {**payload, "project_id": project_id}).scalar()


def patch_batch(db: Session, *, batch_id: int, fields: dict) -> int:
    if not fields:
        return batch_id
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    sql = text(
        f"UPDATE procurement_batches SET {sets}, updated_at = now() "
        "WHERE batch_id = :bid RETURNING batch_id"
    )
    return db.execute(sql, {**fields, "bid": batch_id}).scalar()


def soft_cancel_batch(db: Session, *, batch_id: int) -> int:
    return db.execute(
        text(
            "UPDATE procurement_batches SET cancelled_at = now(), updated_at = now() "
            "WHERE batch_id = :bid AND cancelled_at IS NULL RETURNING batch_id"
        ),
        {"bid": batch_id},
    ).scalar()


def batch_has_allocations(db: Session, *, batch_id: int) -> bool:
    sql = text(
        "SELECT EXISTS(SELECT 1 FROM batch_allocations "
        "  WHERE batch_id = :bid AND qty_allocated > 0)"
    )
    return bool(db.execute(sql, {"bid": batch_id}).scalar())
```

- [ ] **Step 3: Routes**

Create `apps/api/app/procurement_v1/batches/routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.audit import write_audit
from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from ...projects.queries import get_project
from .queries import (
    batch_has_allocations,
    create_batch,
    get_batch,
    list_batches,
    patch_batch,
    soft_cancel_batch,
)
from .schemas import BatchListOut, BatchOut, CreateBatchIn, PatchBatchIn

router = APIRouter(prefix="", tags=["procurement-v1"])


@router.get("/batches", response_model=BatchListOut)
def get_batches(
    project_id: int | None = None,
    supplier: str | None = None,
    status: str | None = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    rows = list_batches(
        db,
        workspace_id=user.workspace_id,
        project_id=project_id,
        supplier=supplier,
        status=status,
    )
    return {"batches": rows}


@router.post("/batches", response_model=BatchOut, status_code=201)
def post_batch(
    payload: CreateBatchIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    proj = get_project(db, project_id=payload.project_id, workspace_id=user.workspace_id)
    if proj is None:
        raise HTTPException(404, "Project not found")
    bid = create_batch(
        db,
        payload=payload.model_dump(exclude={"project_id"}),
        project_id=payload.project_id,
    )
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="batch.create", target_kind="batch", target_id=bid,
    )
    db.commit()
    out = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if out is None:
        raise HTTPException(500, "Created batch not visible")
    return out


@router.get("/batches/{bid}", response_model=BatchOut)
def get_one(
    bid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    row = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if row is None:
        raise HTTPException(404, "Batch not found")
    return row


@router.patch("/batches/{bid}", response_model=BatchOut)
def patch_one(
    bid: int,
    payload: PatchBatchIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if get_batch(db, batch_id=bid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Batch not found")
    fields = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if fields:
        patch_batch(db, batch_id=bid, fields=fields)
        write_audit(
            db, user_id=user.id, workspace_id=user.workspace_id,
            event="batch.update", target_kind="batch", target_id=bid,
        )
        db.commit()
    return get_batch(db, batch_id=bid, workspace_id=user.workspace_id)


@router.delete("/batches/{bid}", status_code=204)
def cancel_one(
    bid: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    existing = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if existing is None:
        raise HTTPException(404, "Batch not found")
    if existing["cancelled_at"] is not None:
        raise HTTPException(409, "Batch already cancelled")
    if batch_has_allocations(db, batch_id=bid):
        raise HTTPException(409, "Remove allocations before cancelling this batch")
    soft_cancel_batch(db, batch_id=bid)
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="batch.cancel", target_kind="batch", target_id=bid,
    )
    db.commit()
    return None
```

- [ ] **Step 4: Mount the router**

In `apps/api/app/main.py`:

```python
from .procurement_v1.batches.routes import router as proc_v1_batches_router
app.include_router(proc_v1_batches_router)
```

- [ ] **Step 5: Tests**

Create `apps/api/tests/test_proc_v1_batches.py`:

```python
import pytest
from sqlalchemy import text


@pytest.fixture
def project_setup(db, workspace_id):
    pm_id = db.execute(text(
        "INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role,jtbd_role) "
        "VALUES(:w,'pm@t.test','PM','x','manager','PM') RETURNING id"
    ), {"w": workspace_id}).scalar()
    pid = db.execute(text(
        "INSERT INTO projects(workspace_id,project_code,name,pm_id) "
        "VALUES(:w,'P1','P',:p) RETURNING project_id"
    ), {"w": workspace_id, "p": pm_id}).scalar()
    mat_id = db.execute(text(
        "INSERT INTO hardware_materials(material_name,sku) VALUES('Hinge','H-100') RETURNING material_id"
    )).scalar()
    db.commit()
    return {"workspace_id": workspace_id, "project_id": pid, "user_id": pm_id, "material_id": mat_id}


def test_create_batch(client, project_setup, login_as):
    login_as(project_setup["user_id"])
    r = client.post("/batches", json={
        "project_id":    project_setup["project_id"],
        "material_type": "HARDWARE",
        "material_id":   project_setup["material_id"],
        "supplier":      "Acme",
        "po_ref":        "PO-001",
        "qty_ordered":   10,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"]   == "OPEN"
    assert body["supplier"] == "Acme"


def test_patch_batch_marks_in_transit(client, project_setup, login_as):
    login_as(project_setup["user_id"])
    bid = client.post("/batches", json={
        "project_id":    project_setup["project_id"],
        "material_type": "HARDWARE",
        "material_id":   project_setup["material_id"],
        "qty_ordered":   10,
    }).json()["batch_id"]
    r = client.patch(f"/batches/{bid}", json={"ordered_date": "2026-04-01"})
    assert r.status_code == 200
    assert r.json()["status"] == "IN_TRANSIT"


def test_soft_cancel_batch(client, project_setup, login_as):
    login_as(project_setup["user_id"])
    bid = client.post("/batches", json={
        "project_id":    project_setup["project_id"],
        "material_type": "HARDWARE",
        "material_id":   project_setup["material_id"],
        "qty_ordered":   10,
    }).json()["batch_id"]
    r = client.delete(f"/batches/{bid}")
    assert r.status_code == 204
    g = client.get(f"/batches/{bid}").json()
    assert g["status"] == "CANCELLED"


def test_create_batch_404_for_unknown_project(client, project_setup, login_as):
    login_as(project_setup["user_id"])
    r = client.post("/batches", json={
        "project_id":    999999,
        "material_type": "HARDWARE",
        "material_id":   project_setup["material_id"],
        "qty_ordered":   1,
    })
    assert r.status_code == 404
```

- [ ] **Step 6: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_batches.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/procurement_v1/batches apps/api/app/main.py apps/api/tests/test_proc_v1_batches.py
git commit -m "feat(api): /batches CRUD with derived status + soft-cancel"
```

---

### Task 8: Soft-cancel guard regression

**Files:**
- Modify: `apps/api/tests/test_proc_v1_batches.py`

- [ ] **Step 1: Add the test**

Append:

```python
def test_soft_cancel_blocked_when_allocations_exist(db, client, project_setup, login_as):
    login_as(project_setup["user_id"])
    bid = client.post("/batches", json={
        "project_id":    project_setup["project_id"],
        "material_type": "HARDWARE",
        "material_id":   project_setup["material_id"],
        "qty_ordered":   5,
        "qty_received":  5,
        "received_date": "2026-04-01",
    }).json()["batch_id"]

    cat_id = db.execute(text(
        "INSERT INTO project_hardware_catalog(project_id,material_type,material_id,added_by) "
        "VALUES(:p,'HARDWARE',:m,:u) RETURNING catalog_id"
    ), {"p": project_setup["project_id"], "m": project_setup["material_id"],
        "u": project_setup["user_id"]}).scalar()
    item_id = db.execute(text(
        "INSERT INTO items(project_id,item_number,description,owner_id) "
        "VALUES(:p,1,'X',:u) RETURNING item_id"
    ), {"p": project_setup["project_id"], "u": project_setup["user_id"]}).scalar()
    line_id = db.execute(text(
        "INSERT INTO item_hardware_lines(item_id,seq,qty,catalog_id) "
        "VALUES(:i,1,3,:c) RETURNING line_id"
    ), {"i": item_id, "c": cat_id}).scalar()
    db.execute(text(
        "INSERT INTO batch_allocations(batch_id,item_hardware_line_id,qty_allocated) "
        "VALUES(:b,:l,3)"
    ), {"b": bid, "l": line_id})
    db.commit()

    r = client.delete(f"/batches/{bid}")
    assert r.status_code == 409
    assert "alloc" in r.json()["detail"].lower()
```

- [ ] **Step 2: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_batches.py::test_soft_cancel_blocked_when_allocations_exist -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_proc_v1_batches.py
git commit -m "test(api): regression guard for soft-cancel-with-allocations"
```

---

### Task 9: `/batches/{bid}/allocations` CRUD

**Files:**
- Create: `apps/api/app/procurement_v1/allocations/schemas.py`
- Create: `apps/api/app/procurement_v1/allocations/queries.py`
- Create: `apps/api/app/procurement_v1/allocations/routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_proc_v1_allocations.py`

- [ ] **Step 1: Schemas**

Create `apps/api/app/procurement_v1/allocations/schemas.py`:

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class AllocationOut(BaseModel):
    allocation_id: int
    batch_id: int
    item_hardware_line_id: int
    qty_allocated: Decimal
    created_at: datetime
    item_code: str | None = None
    item_description: str | None = None


class AllocationListOut(BaseModel):
    allocations: list[AllocationOut]
    qty_received: Decimal
    qty_allocated_total: Decimal
    qty_remaining: Decimal


class CreateAllocationIn(BaseModel):
    item_hardware_line_id: int
    qty_allocated: Decimal = Field(gt=0)


class PatchAllocationIn(BaseModel):
    qty_allocated: Decimal = Field(gt=0)
```

- [ ] **Step 2: Queries**

Create `apps/api/app/procurement_v1/allocations/queries.py`:

```python
from sqlalchemy import text
from sqlalchemy.orm import Session


def list_allocations_for_batch(db: Session, *, batch_id: int) -> list[dict]:
    sql = text(
        """
        SELECT ba.allocation_id, ba.batch_id, ba.item_hardware_line_id,
               ba.qty_allocated, ba.created_at,
               i.code AS item_code, i.description AS item_description
          FROM batch_allocations ba
          JOIN item_hardware_lines ihl ON ihl.line_id = ba.item_hardware_line_id
          JOIN items i ON i.item_id = ihl.item_id
         WHERE ba.batch_id = :bid
         ORDER BY ba.allocation_id
        """
    )
    return [dict(r) for r in db.execute(sql, {"bid": batch_id}).mappings()]


def batch_capacity(db: Session, *, batch_id: int) -> tuple:
    """Returns (qty_received, qty_allocated_total, qty_ordered)."""
    sql = text(
        """
        SELECT pb.qty_received, pb.qty_ordered,
               (SELECT COALESCE(SUM(qty_allocated),0) FROM batch_allocations a
                  WHERE a.batch_id = pb.batch_id) AS qty_alloc
          FROM procurement_batches pb
         WHERE pb.batch_id = :bid
        """
    )
    r = db.execute(sql, {"bid": batch_id}).mappings().first()
    return (r["qty_received"], r["qty_alloc"], r["qty_ordered"]) if r else (0, 0, 0)


def line_belongs_to_batch_project(db: Session, *, batch_id: int, line_id: int) -> bool:
    sql = text(
        """
        SELECT EXISTS(
          SELECT 1
            FROM item_hardware_lines ihl
            JOIN items i ON i.item_id = ihl.item_id
            JOIN procurement_batches pb ON pb.project_id = i.project_id
           WHERE pb.batch_id = :bid AND ihl.line_id = :lid
        )
        """
    )
    return bool(db.execute(sql, {"bid": batch_id, "lid": line_id}).scalar())


def create_allocation(db: Session, *, batch_id: int, line_id: int, qty: float) -> int:
    return db.execute(
        text(
            "INSERT INTO batch_allocations(batch_id,item_hardware_line_id,qty_allocated) "
            "VALUES(:b,:l,:q) RETURNING allocation_id"
        ),
        {"b": batch_id, "l": line_id, "q": qty},
    ).scalar()


def patch_allocation(db: Session, *, allocation_id: int, qty: float) -> int:
    return db.execute(
        text(
            "UPDATE batch_allocations SET qty_allocated = :q "
            "WHERE allocation_id = :aid RETURNING allocation_id"
        ),
        {"q": qty, "aid": allocation_id},
    ).scalar()


def get_allocation(db: Session, *, allocation_id: int, workspace_id: int) -> dict | None:
    sql = text(
        """
        SELECT ba.allocation_id, ba.batch_id, ba.item_hardware_line_id,
               ba.qty_allocated, ba.created_at,
               i.code AS item_code, i.description AS item_description
          FROM batch_allocations ba
          JOIN procurement_batches pb ON pb.batch_id = ba.batch_id
          JOIN projects p              ON p.project_id = pb.project_id
          JOIN item_hardware_lines ihl ON ihl.line_id  = ba.item_hardware_line_id
          JOIN items i                 ON i.item_id    = ihl.item_id
         WHERE ba.allocation_id = :aid AND p.workspace_id = :w
        """
    )
    r = db.execute(sql, {"aid": allocation_id, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def delete_allocation(db: Session, *, allocation_id: int) -> int:
    return db.execute(
        text("DELETE FROM batch_allocations WHERE allocation_id = :aid RETURNING allocation_id"),
        {"aid": allocation_id},
    ).scalar()
```

- [ ] **Step 3: Routes**

Create `apps/api/app/procurement_v1/allocations/routes.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.audit import write_audit
from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from ..batches.queries import get_batch
from .queries import (
    batch_capacity,
    create_allocation,
    delete_allocation,
    get_allocation,
    line_belongs_to_batch_project,
    list_allocations_for_batch,
    patch_allocation,
)
from .schemas import (
    AllocationListOut,
    AllocationOut,
    CreateAllocationIn,
    PatchAllocationIn,
)

router = APIRouter(prefix="", tags=["procurement-v1"])


def _capacity(qty_received, qty_ordered):
    return qty_received if qty_received and qty_received > 0 else qty_ordered


@router.get("/batches/{bid}/allocations", response_model=AllocationListOut)
def list_for_batch(
    bid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    batch = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    rows = list_allocations_for_batch(db, batch_id=bid)
    qty_alloc = sum((float(r["qty_allocated"]) for r in rows), 0.0)
    return {
        "allocations":         rows,
        "qty_received":        batch["qty_received"],
        "qty_allocated_total": qty_alloc,
        "qty_remaining":       float(batch["qty_received"]) - qty_alloc,
    }


@router.post("/batches/{bid}/allocations", response_model=AllocationOut, status_code=201)
def create_for_batch(
    bid: int,
    payload: CreateAllocationIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    batch = get_batch(db, batch_id=bid, workspace_id=user.workspace_id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    if not line_belongs_to_batch_project(db, batch_id=bid, line_id=payload.item_hardware_line_id):
        raise HTTPException(400, "Line does not belong to this batch's project")
    new_total = float(batch["qty_allocated"]) + float(payload.qty_allocated)
    cap = _capacity(batch["qty_received"], batch["qty_ordered"])
    if new_total > float(cap):
        raise HTTPException(409, f"Allocation would exceed capacity ({new_total} > {cap})")

    aid = create_allocation(
        db, batch_id=bid,
        line_id=payload.item_hardware_line_id,
        qty=float(payload.qty_allocated),
    )
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="allocation.create", target_kind="allocation", target_id=aid,
    )
    db.commit()
    out = get_allocation(db, allocation_id=aid, workspace_id=user.workspace_id)
    if out is None:
        raise HTTPException(500, "Created allocation not visible")
    return out


@router.patch("/allocations/{aid}", response_model=AllocationOut)
def patch_one(
    aid: int,
    payload: PatchAllocationIn,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    existing = get_allocation(db, allocation_id=aid, workspace_id=user.workspace_id)
    if existing is None:
        raise HTTPException(404, "Allocation not found")
    bid = existing["batch_id"]
    qty_received, qty_alloc_total, qty_ordered = batch_capacity(db, batch_id=bid)
    new_total = float(qty_alloc_total) - float(existing["qty_allocated"]) + float(payload.qty_allocated)
    cap = _capacity(qty_received, qty_ordered)
    if new_total > float(cap):
        raise HTTPException(409, f"Allocation would exceed capacity ({new_total} > {cap})")
    patch_allocation(db, allocation_id=aid, qty=float(payload.qty_allocated))
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="allocation.update", target_kind="allocation", target_id=aid,
    )
    db.commit()
    return get_allocation(db, allocation_id=aid, workspace_id=user.workspace_id)


@router.delete("/allocations/{aid}", status_code=204)
def delete_one(
    aid: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    if get_allocation(db, allocation_id=aid, workspace_id=user.workspace_id) is None:
        raise HTTPException(404, "Allocation not found")
    delete_allocation(db, allocation_id=aid)
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="allocation.delete", target_kind="allocation", target_id=aid,
    )
    db.commit()
    return None
```

- [ ] **Step 4: Mount the router**

```python
# main.py
from .procurement_v1.allocations.routes import router as proc_v1_alloc_router
app.include_router(proc_v1_alloc_router)
```

- [ ] **Step 5: Tests**

Create `apps/api/tests/test_proc_v1_allocations.py`:

```python
import pytest
from sqlalchemy import text


@pytest.fixture
def alloc_setup(db, workspace_id):
    pm = db.execute(text(
        "INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role,jtbd_role) "
        "VALUES(:w,'pm@t.test','PM','x','manager','PM') RETURNING id"
    ), {"w": workspace_id}).scalar()
    pid = db.execute(text(
        "INSERT INTO projects(workspace_id,project_code,name,pm_id) "
        "VALUES(:w,'P','P',:p) RETURNING project_id"
    ), {"w": workspace_id, "p": pm}).scalar()
    mat = db.execute(text(
        "INSERT INTO hardware_materials(material_name,sku) VALUES('X','X') RETURNING material_id"
    )).scalar()
    cat = db.execute(text(
        "INSERT INTO project_hardware_catalog(project_id,material_type,material_id,added_by) "
        "VALUES(:p,'HARDWARE',:m,:u) RETURNING catalog_id"
    ), {"p": pid, "m": mat, "u": pm}).scalar()
    item = db.execute(text(
        "INSERT INTO items(project_id,item_number,description,owner_id) "
        "VALUES(:p,1,'X',:u) RETURNING item_id"
    ), {"p": pid, "u": pm}).scalar()
    line = db.execute(text(
        "INSERT INTO item_hardware_lines(item_id,seq,qty,catalog_id) "
        "VALUES(:i,1,5,:c) RETURNING line_id"
    ), {"i": item, "c": cat}).scalar()
    bid = db.execute(text(
        "INSERT INTO procurement_batches(project_id,material_type,material_id,qty_ordered,qty_received,received_date) "
        "VALUES(:p,'HARDWARE',:m,5,5,CURRENT_DATE) RETURNING batch_id"
    ), {"p": pid, "m": mat}).scalar()
    db.commit()
    return {
        "workspace_id": workspace_id, "user_id": pm, "project_id": pid,
        "material_id": mat, "line_id": line, "batch_id": bid,
    }


def test_create_allocation_within_capacity(client, alloc_setup, login_as):
    login_as(alloc_setup["user_id"])
    r = client.post(
        f"/batches/{alloc_setup['batch_id']}/allocations",
        json={"item_hardware_line_id": alloc_setup["line_id"], "qty_allocated": 3},
    )
    assert r.status_code == 201
    assert float(r.json()["qty_allocated"]) == 3


def test_over_commit_returns_409(client, alloc_setup, login_as):
    login_as(alloc_setup["user_id"])
    client.post(f"/batches/{alloc_setup['batch_id']}/allocations",
                json={"item_hardware_line_id": alloc_setup["line_id"], "qty_allocated": 4})
    r = client.post(f"/batches/{alloc_setup['batch_id']}/allocations",
                    json={"item_hardware_line_id": alloc_setup["line_id"], "qty_allocated": 2})
    assert r.status_code == 409
    assert "exceed" in r.json()["detail"].lower()


def test_patch_allocation_capacity_check(client, alloc_setup, login_as):
    login_as(alloc_setup["user_id"])
    aid = client.post(
        f"/batches/{alloc_setup['batch_id']}/allocations",
        json={"item_hardware_line_id": alloc_setup["line_id"], "qty_allocated": 2},
    ).json()["allocation_id"]
    r = client.patch(f"/allocations/{aid}", json={"qty_allocated": 99})
    assert r.status_code == 409


def test_delete_allocation_releases_capacity(client, alloc_setup, login_as):
    login_as(alloc_setup["user_id"])
    aid = client.post(
        f"/batches/{alloc_setup['batch_id']}/allocations",
        json={"item_hardware_line_id": alloc_setup["line_id"], "qty_allocated": 5},
    ).json()["allocation_id"]
    assert client.delete(f"/allocations/{aid}").status_code == 204
    r = client.post(
        f"/batches/{alloc_setup['batch_id']}/allocations",
        json={"item_hardware_line_id": alloc_setup["line_id"], "qty_allocated": 5},
    )
    assert r.status_code == 201


def test_cross_project_line_rejected(db, client, alloc_setup, login_as, workspace_id):
    """A line from a different project cannot be allocated to this batch."""
    login_as(alloc_setup["user_id"])
    other_pid = db.execute(text(
        "INSERT INTO projects(workspace_id,project_code,name,pm_id) "
        "VALUES(:w,'P2','P2',:u) RETURNING project_id"
    ), {"w": workspace_id, "u": alloc_setup["user_id"]}).scalar()
    other_cat = db.execute(text(
        "INSERT INTO project_hardware_catalog(project_id,material_type,material_id,added_by) "
        "VALUES(:p,'HARDWARE',:m,:u) RETURNING catalog_id"
    ), {"p": other_pid, "m": alloc_setup["material_id"], "u": alloc_setup["user_id"]}).scalar()
    other_item = db.execute(text(
        "INSERT INTO items(project_id,item_number,description,owner_id) "
        "VALUES(:p,1,'O',:u) RETURNING item_id"
    ), {"p": other_pid, "u": alloc_setup["user_id"]}).scalar()
    other_line = db.execute(text(
        "INSERT INTO item_hardware_lines(item_id,seq,qty,catalog_id) "
        "VALUES(:i,1,1,:c) RETURNING line_id"
    ), {"i": other_item, "c": other_cat}).scalar()
    db.commit()

    r = client.post(
        f"/batches/{alloc_setup['batch_id']}/allocations",
        json={"item_hardware_line_id": other_line, "qty_allocated": 1},
    )
    assert r.status_code == 400
```

- [ ] **Step 6: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_allocations.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/procurement_v1/allocations apps/api/app/main.py apps/api/tests/test_proc_v1_allocations.py
git commit -m "feat(api): /batches/{bid}/allocations CRUD with over-commit + cross-project guards"
```

---

### Task 10: Allocation list summary acceptance

**Files:**
- Modify: `apps/api/tests/test_proc_v1_allocations.py`

- [ ] **Step 1: Add the test**

Append:

```python
def test_allocation_list_summary(client, alloc_setup, login_as):
    login_as(alloc_setup["user_id"])
    client.post(
        f"/batches/{alloc_setup['batch_id']}/allocations",
        json={"item_hardware_line_id": alloc_setup["line_id"], "qty_allocated": 3},
    )
    r = client.get(f"/batches/{alloc_setup['batch_id']}/allocations")
    assert r.status_code == 200
    body = r.json()
    assert float(body["qty_received"])         == 5
    assert float(body["qty_allocated_total"])  == 3
    assert float(body["qty_remaining"])        == 2
    assert len(body["allocations"]) == 1
    assert body["allocations"][0]["item_description"] == "X"
```

- [ ] **Step 2: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_allocations.py::test_allocation_list_summary -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_proc_v1_allocations.py
git commit -m "test(api): allocation list summary (qty_received/allocated_total/remaining)"
```

---

## Phase 4 — Catalogs API (2 tasks)

### Task 11: `/catalogs/{type}` GET/POST/PATCH/DELETE

**Files:**
- Create: `apps/api/app/procurement_v1/catalogs/queries.py`
- Create: `apps/api/app/procurement_v1/catalogs/routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_proc_v1_catalogs.py`

> Catalogs differ enough per type that the simplest path is a small registry mapping the type string to its `(table, id_col, select_cols, insertable_cols)`. Pydantic v2 type-discriminated payloads add boilerplate without much safety here — we accept `dict[str, Any]` and let Postgres reject bad columns. This is justified because writes go only to `manager/admin/drafter/purchase_officer` (per the elevated matrix), all already authenticated and audited.

- [ ] **Step 1: Queries**

Create `apps/api/app/procurement_v1/catalogs/queries.py`:

```python
"""Catalog CRUD across the 6 material catalog tables."""
from sqlalchemy import text
from sqlalchemy.orm import Session

# (table, id_col, select_cols_csv, insertable_cols_tuple)
#
# Adjust select_cols_csv to include EVERY public column from migration 0001
# for each table (e.g., board_materials has thickness_mm, colour, finish).
# insertable_cols_tuple matches what's actually nullable / has defaults.
REGISTRY: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "board": (
        "board_materials", "material_id",
        "material_id, material_name, sku",
        ("material_name", "sku"),
    ),
    "hardware": (
        "hardware_materials", "material_id",
        "material_id, material_name, sku",
        ("material_name", "sku"),
    ),
    "custom_made": (
        "custom_made", "material_id",
        "material_id, description, sku",
        ("description", "sku"),
    ),
    "benchtop": (
        "benchtop_materials", "material_id",
        "material_id, material_name, sku",
        ("material_name", "sku"),
    ),
    "appliance": (
        "appliances", "material_id",
        "material_id, model_name, sku",
        ("model_name", "sku"),
    ),
    "hire": (
        "equipment_hire", "material_id",
        "material_id, description",
        ("description",),
    ),
}


def list_catalog(db: Session, *, type_: str) -> list[dict]:
    table, _, cols, _ = REGISTRY[type_]
    sql = text(f"SELECT {cols} FROM {table} ORDER BY 1")
    return [dict(r) | {"type": type_} for r in db.execute(sql).mappings()]


def create_catalog_row(db: Session, *, type_: str, fields: dict) -> int:
    table, id_col, _, insert_cols = REGISTRY[type_]
    cols = [c for c in insert_cols if c in fields]
    if not cols:
        raise ValueError("no insertable fields supplied")
    sql = text(
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':'+c for c in cols)}) RETURNING {id_col}"
    )
    return db.execute(sql, fields).scalar()


def get_catalog_row(db: Session, *, type_: str, mid: int) -> dict | None:
    table, id_col, cols, _ = REGISTRY[type_]
    sql = text(f"SELECT {cols} FROM {table} WHERE {id_col} = :id")
    r = db.execute(sql, {"id": mid}).mappings().first()
    return (dict(r) | {"type": type_}) if r else None


def patch_catalog_row(db: Session, *, type_: str, mid: int, fields: dict) -> int:
    if not fields:
        return mid
    table, id_col, _, insert_cols = REGISTRY[type_]
    use = {k: v for k, v in fields.items() if k in insert_cols}
    if not use:
        return mid
    sets = ", ".join(f"{c} = :{c}" for c in use.keys())
    sql = text(f"UPDATE {table} SET {sets} WHERE {id_col} = :id RETURNING {id_col}")
    return db.execute(sql, {**use, "id": mid}).scalar()


def delete_catalog_row(db: Session, *, type_: str, mid: int) -> int:
    table, id_col, _, _ = REGISTRY[type_]
    return db.execute(
        text(f"DELETE FROM {table} WHERE {id_col} = :id RETURNING {id_col}"),
        {"id": mid},
    ).scalar()
```

- [ ] **Step 2: Routes**

Create `apps/api/app/procurement_v1/catalogs/routes.py`:

```python
from typing import Any
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.audit import write_audit
from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from .queries import (
    REGISTRY,
    create_catalog_row,
    delete_catalog_row,
    get_catalog_row,
    list_catalog,
    patch_catalog_row,
)

router = APIRouter(prefix="", tags=["procurement-v1"])

VALID_TYPES = tuple(REGISTRY.keys())


def _validate_type(type_: str) -> None:
    if type_ not in VALID_TYPES:
        raise HTTPException(404, f"Unknown catalog type: {type_}")


@router.get("/catalogs/{type_}")
def list_(
    type_: str,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    return {"type": type_, "rows": list_catalog(db, type_=type_)}


@router.post("/catalogs/{type_}", status_code=201)
def create(
    type_: str,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    try:
        mid = create_catalog_row(db, type_=type_, fields=payload)
    except ValueError as e:
        raise HTTPException(422, str(e))
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="catalog.create", target_kind=f"catalog.{type_}", target_id=mid,
    )
    db.commit()
    out = get_catalog_row(db, type_=type_, mid=mid)
    if out is None:
        raise HTTPException(500, "Created row not visible")
    return out


@router.get("/catalogs/{type_}/{mid}")
def get_one(
    type_: str,
    mid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    row = get_catalog_row(db, type_=type_, mid=mid)
    if row is None:
        raise HTTPException(404, "Catalog row not found")
    return row


@router.patch("/catalogs/{type_}/{mid}")
def patch_one(
    type_: str,
    mid: int,
    payload: dict[str, Any] = Body(...),
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    if get_catalog_row(db, type_=type_, mid=mid) is None:
        raise HTTPException(404, "Catalog row not found")
    patch_catalog_row(db, type_=type_, mid=mid, fields=payload)
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="catalog.update", target_kind=f"catalog.{type_}", target_id=mid,
    )
    db.commit()
    return get_catalog_row(db, type_=type_, mid=mid)


@router.delete("/catalogs/{type_}/{mid}", status_code=204)
def delete_one(
    type_: str,
    mid: int,
    user: AuthUser = Depends(require_permission("orderbook", "write")),
    db: Session = Depends(get_db),
):
    _validate_type(type_)
    if get_catalog_row(db, type_=type_, mid=mid) is None:
        raise HTTPException(404, "Catalog row not found")
    delete_catalog_row(db, type_=type_, mid=mid)
    write_audit(
        db, user_id=user.id, workspace_id=user.workspace_id,
        event="catalog.delete", target_kind=f"catalog.{type_}", target_id=mid,
    )
    db.commit()
    return None
```

- [ ] **Step 3: Mount**

```python
# main.py
from .procurement_v1.catalogs.routes import router as proc_v1_catalogs_router
app.include_router(proc_v1_catalogs_router)
```

- [ ] **Step 4: Tests**

Create `apps/api/tests/test_proc_v1_catalogs.py`:

```python
import pytest
from sqlalchemy import text


@pytest.fixture
def admin_user(db, workspace_id):
    uid = db.execute(text(
        "INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role,jtbd_role) "
        "VALUES(:w,'a@t.test','A','x','admin','CEO') RETURNING id"
    ), {"w": workspace_id}).scalar()
    db.commit()
    return uid


def test_list_hardware_catalog(client, admin_user, login_as, db):
    db.execute(text("INSERT INTO hardware_materials(material_name,sku) VALUES('X','X')"))
    db.commit()
    login_as(admin_user)
    r = client.get("/catalogs/hardware")
    assert r.status_code == 200
    assert r.json()["type"] == "hardware"
    assert any(row["material_name"] == "X" for row in r.json()["rows"])


def test_create_hardware(client, admin_user, login_as):
    login_as(admin_user)
    r = client.post("/catalogs/hardware", json={"material_name": "Hinge 90deg", "sku": "H-90"})
    assert r.status_code == 201
    assert r.json()["material_name"] == "Hinge 90deg"


def test_unknown_type_404(client, admin_user, login_as):
    login_as(admin_user)
    assert client.get("/catalogs/bogus").status_code == 404


def test_patch_hardware(client, admin_user, login_as):
    login_as(admin_user)
    mid = client.post("/catalogs/hardware", json={"material_name": "A"}).json()["material_id"]
    r = client.patch(f"/catalogs/hardware/{mid}", json={"material_name": "B"})
    assert r.status_code == 200
    assert r.json()["material_name"] == "B"


def test_delete_hardware(client, admin_user, login_as):
    login_as(admin_user)
    mid = client.post("/catalogs/hardware", json={"material_name": "Z"}).json()["material_id"]
    assert client.delete(f"/catalogs/hardware/{mid}").status_code == 204
    assert client.get(f"/catalogs/hardware/{mid}").status_code == 404


def test_no_insertable_fields_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    r = client.post("/catalogs/hardware", json={"bogus": "x"})
    assert r.status_code == 422
```

- [ ] **Step 5: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_catalogs.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/procurement_v1/catalogs apps/api/app/main.py apps/api/tests/test_proc_v1_catalogs.py
git commit -m "feat(api): /catalogs/{type} CRUD for the 6 material catalog tables"
```

---

### Task 12: Per-type smoke

**Files:**
- Modify: `apps/api/tests/test_proc_v1_catalogs.py`

- [ ] **Step 1: Append parametrised smoke**

```python
@pytest.mark.parametrize("type_,payload", [
    ("board",       {"material_name": "MDF 18"}),
    ("hardware",    {"material_name": "Hinge"}),
    ("custom_made", {"description":   "Custom panel"}),
    ("benchtop",    {"material_name": "Caesarstone"}),
    ("appliance",   {"model_name":    "Bosch SMS"}),
    ("hire",        {"description":   "Scissor lift 1 day"}),
])
def test_each_catalog_type_supports_create_list(client, admin_user, login_as, type_, payload):
    login_as(admin_user)
    r = client.post(f"/catalogs/{type_}", json=payload)
    assert r.status_code == 201
    listing = client.get(f"/catalogs/{type_}").json()["rows"]
    found = any(
        row.get("material_name") or row.get("description") or row.get("model_name")
        for row in listing
    )
    assert found
```

- [ ] **Step 2: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_catalogs.py -v
```

Expected: 12 passed (6 + 6 parametrised).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_proc_v1_catalogs.py
git commit -m "test(api): parametrised smoke for all 6 catalog types"
```

---

## Phase 5 — Cross-project queue API (1 task)

### Task 13: `/procurement-queue`

**Files:**
- Create: `apps/api/app/procurement_v1/queue/schemas.py`
- Create: `apps/api/app/procurement_v1/queue/queries.py`
- Create: `apps/api/app/procurement_v1/queue/routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_proc_v1_queue.py`

- [ ] **Step 1: Schemas**

Create `apps/api/app/procurement_v1/queue/schemas.py`:

```python
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel

QueueStatus = Literal["OPEN","IN_TRANSIT","DELIVERED","CANCELLED"]


class QueueRow(BaseModel):
    batch_id: int
    project_id: int
    project_code: str
    project_name: str
    supplier: str | None = None
    po_ref: str | None = None
    material_type: str
    material_id: int
    material_name: str | None = None
    qty_ordered: Decimal
    qty_received: Decimal
    eta_date: date | None = None
    status: QueueStatus


class QueueOut(BaseModel):
    rows: list[QueueRow]
```

- [ ] **Step 2: Queries**

Create `apps/api/app/procurement_v1/queue/queries.py`:

```python
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session

_NAME_LOOKUP = {
    "BOARD":     ("board_materials",    "material_id", "material_name"),
    "HARDWARE":  ("hardware_materials", "material_id", "material_name"),
    "CUSTOM":    ("custom_made",        "material_id", "description"),
    "BENCHTOP":  ("benchtop_materials", "material_id", "material_name"),
    "APPLIANCE": ("appliances",         "material_id", "model_name"),
    "HIRE":      ("equipment_hire",     "material_id", "description"),
}

_STATUS_CASE = (
    "CASE "
    "  WHEN pb.cancelled_at  IS NOT NULL THEN 'CANCELLED' "
    "  WHEN pb.received_date IS NOT NULL THEN 'DELIVERED' "
    "  WHEN pb.ordered_date  IS NOT NULL THEN 'IN_TRANSIT' "
    "  ELSE 'OPEN' "
    "END"
)


def _enrich_names(db: Session, rows: list[dict]) -> list[dict]:
    by_type: dict[str, list[int]] = {}
    for r in rows:
        by_type.setdefault(r["material_type"], []).append(r["material_id"])
    name_map: dict[tuple, str] = {}
    for mt, ids in by_type.items():
        table, id_col, name_col = _NAME_LOOKUP[mt]
        for r in db.execute(
            text(f"SELECT {id_col} AS id, {name_col} AS name FROM {table} WHERE {id_col} = ANY(:ids)"),
            {"ids": ids},
        ).mappings():
            name_map[(mt, r["id"])] = r["name"]
    for r in rows:
        r["material_name"] = name_map.get((r["material_type"], r["material_id"]))
    return rows


def queue(
    db: Session,
    *,
    workspace_id: int,
    status: str | None = None,
    supplier: str | None = None,
    project_id: int | None = None,
) -> list[dict]:
    sql = (
        "SELECT pb.batch_id, pb.project_id, p.project_code, p.name AS project_name, "
        "       pb.supplier, pb.po_ref, pb.material_type, pb.material_id, "
        "       pb.qty_ordered, pb.qty_received, pb.eta_date, "
        f"      {_STATUS_CASE} AS status "
        "  FROM procurement_batches pb "
        "  JOIN projects p ON p.project_id = pb.project_id "
        " WHERE p.workspace_id = :w "
    )
    params: dict[str, Any] = {"w": workspace_id}
    if status:
        sql += f" AND {_STATUS_CASE} = :st"
        params["st"] = status
    if supplier:
        sql += " AND pb.supplier ILIKE :sup"
        params["sup"] = supplier
    if project_id:
        sql += " AND pb.project_id = :pid"
        params["pid"] = project_id
    sql += (
        " ORDER BY pb.supplier NULLS LAST, "
        "         COALESCE(pb.eta_date, pb.ordered_date, pb.created_at::date)"
    )
    rows = [dict(r) for r in db.execute(text(sql), params).mappings()]
    return _enrich_names(db, rows)
```

- [ ] **Step 3: Routes**

Create `apps/api/app/procurement_v1/queue/routes.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from .queries import queue
from .schemas import QueueOut

router = APIRouter(prefix="", tags=["procurement-v1"])


@router.get("/procurement-queue", response_model=QueueOut)
def get_queue(
    status: str | None = None,
    supplier: str | None = None,
    project_id: int | None = None,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    return {"rows": queue(
        db,
        workspace_id=user.workspace_id,
        status=status, supplier=supplier, project_id=project_id,
    )}
```

- [ ] **Step 4: Mount**

```python
# main.py
from .procurement_v1.queue.routes import router as proc_v1_queue_router
app.include_router(proc_v1_queue_router)
```

- [ ] **Step 5: Tests**

Create `apps/api/tests/test_proc_v1_queue.py`:

```python
import pytest
from sqlalchemy import text


@pytest.fixture
def queue_setup(db, workspace_id):
    pm = db.execute(text(
        "INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role,jtbd_role) "
        "VALUES(:w,'pm@t.test','PM','x','manager','PM') RETURNING id"
    ), {"w": workspace_id}).scalar()
    p1 = db.execute(text(
        "INSERT INTO projects(workspace_id,project_code,name,pm_id) "
        "VALUES(:w,'P1','P1',:p) RETURNING project_id"
    ), {"w": workspace_id, "p": pm}).scalar()
    p2 = db.execute(text(
        "INSERT INTO projects(workspace_id,project_code,name,pm_id) "
        "VALUES(:w,'P2','P2',:p) RETURNING project_id"
    ), {"w": workspace_id, "p": pm}).scalar()
    mat = db.execute(text(
        "INSERT INTO hardware_materials(material_name,sku) VALUES('X','X') RETURNING material_id"
    )).scalar()
    db.execute(text(
        "INSERT INTO procurement_batches(project_id,material_type,material_id,supplier,qty_ordered,ordered_date,eta_date) "
        "VALUES(:p1,'HARDWARE',:m,'Acme',5,CURRENT_DATE,CURRENT_DATE + 7), "
        "      (:p2,'HARDWARE',:m,'Bravo',3,CURRENT_DATE,CURRENT_DATE + 14)"
    ), {"p1": p1, "p2": p2, "m": mat})
    db.commit()
    return {"workspace_id": workspace_id, "user_id": pm, "p1": p1, "p2": p2}


def test_queue_lists_both_projects(client, queue_setup, login_as):
    login_as(queue_setup["user_id"])
    body = client.get("/procurement-queue").json()
    assert len(body["rows"]) == 2
    assert {r["supplier"] for r in body["rows"]} == {"Acme", "Bravo"}


def test_queue_filter_by_supplier(client, queue_setup, login_as):
    login_as(queue_setup["user_id"])
    body = client.get("/procurement-queue?supplier=Acme").json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["supplier"] == "Acme"


def test_queue_filter_by_status(client, queue_setup, login_as):
    login_as(queue_setup["user_id"])
    body = client.get("/procurement-queue?status=IN_TRANSIT").json()
    assert all(r["status"] == "IN_TRANSIT" for r in body["rows"])
```

- [ ] **Step 6: Run, confirm pass**

```bash
docker compose exec api pytest tests/test_proc_v1_queue.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Final API regression check**

```bash
docker compose exec api pytest -q
```

Expected: ~145 passed (118 prior + ~27 new across batches/allocations/catalogs/queue/materials).

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/procurement_v1/queue apps/api/app/main.py apps/api/tests/test_proc_v1_queue.py
git commit -m "feat(api): GET /procurement-queue cross-project rollup"
```

---

## Phase 6 — Web: AvailabilityDrawer on tracking (3 tasks)

### Task 14: Procurement TS types + fetch helpers

**Files:**
- Create: `apps/web/lib/procurement-types.ts`
- Create: `apps/web/lib/procurement-fetch.ts`

- [ ] **Step 1: Types**

Create `apps/web/lib/procurement-types.ts`:

```ts
export type MaterialType   = "BOARD"|"HARDWARE"|"CUSTOM"|"BENCHTOP"|"APPLIANCE"|"HIRE";
export type BatchStatus    = "OPEN"|"IN_TRANSIT"|"DELIVERED"|"CANCELLED";
export type MaterialStatus = "OK"|"SHORT"|"OVERDUE";

// numeric() comes back from Pydantic as a string
export interface MaterialRow {
  material_type: MaterialType;
  material_id: number;
  name: string;
  sku: string | null;
  qty_demand: string;
  qty_on_order: string;
  qty_received: string;
  qty_allocated: string;
  shortfall: string;
  earliest_eta: string | null;
  status: MaterialStatus;
}

export interface ProjectMaterialsOut {
  project_id: number;
  rows: MaterialRow[];
}

export interface BatchOut {
  batch_id: number;
  project_id: number;
  material_type: MaterialType;
  material_id: number;
  supplier: string | null;
  po_ref: string | null;
  qty_ordered: string;
  qty_received: string;
  cost_per_unit: string | null;
  ordered_date: string | null;
  eta_date: string | null;
  received_date: string | null;
  cancelled_at: string | null;
  notes: string | null;
  status: BatchStatus;
  qty_allocated: string;
}

export interface BatchListOut { batches: BatchOut[]; }

export interface AllocationOut {
  allocation_id: number;
  batch_id: number;
  item_hardware_line_id: number;
  qty_allocated: string;
  created_at: string;
  item_code: string | null;
  item_description: string | null;
}

export interface AllocationListOut {
  allocations: AllocationOut[];
  qty_received: string;
  qty_allocated_total: string;
  qty_remaining: string;
}

export interface AvailabilityLine {
  line_id: number;
  seq: number | null;
  catalog_id: number;
  material_type: MaterialType;
  material_id: number;
  qty_needed: string;
  qty_received: string;
  qty_on_order: string;
  qty_allocated_to_line: string;
  earliest_eta: string | null;
  status: "ready"|"blocked";
}

export interface AvailabilityOut {
  item_id: number;
  ready: number;
  blocked: number;
  lines: AvailabilityLine[];
}

export interface QueueRow {
  batch_id: number;
  project_id: number;
  project_code: string;
  project_name: string;
  supplier: string | null;
  po_ref: string | null;
  material_type: string;
  material_id: number;
  material_name: string | null;
  qty_ordered: string;
  qty_received: string;
  eta_date: string | null;
  status: BatchStatus;
}

export interface QueueOut { rows: QueueRow[]; }
```

- [ ] **Step 2: Fetch helpers**

Create `apps/web/lib/procurement-fetch.ts`:

```ts
import type {
  AllocationListOut, AllocationOut,
  AvailabilityOut, BatchListOut, BatchOut,
  ProjectMaterialsOut, QueueOut,
} from "./procurement-types";

async function http<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const r = await fetch(input, { credentials: "include", ...init });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${r.status} ${r.statusText}: ${text}`);
  }
  return r.json() as Promise<T>;
}

export const ProcFetch = {
  projectMaterials: (pid: number) =>
    http<ProjectMaterialsOut>(`/api/projects/${pid}/materials`),
  itemAvailability: (iid: number) =>
    http<AvailabilityOut>(`/api/items/${iid}/availability`),
  listBatches: (qs: URLSearchParams) =>
    http<BatchListOut>(`/api/batches${qs.toString() ? `?${qs}` : ""}`),
  createBatch: (body: object) =>
    http<BatchOut>(`/api/batches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  patchBatch: (bid: number, body: object) =>
    http<BatchOut>(`/api/batches/${bid}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cancelBatch: (bid: number) =>
    fetch(`/api/batches/${bid}`, { method: "DELETE", credentials: "include" }),
  listAllocations: (bid: number) =>
    http<AllocationListOut>(`/api/batches/${bid}/allocations`),
  createAllocation: (bid: number, body: object) =>
    http<AllocationOut>(`/api/batches/${bid}/allocations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteAllocation: (aid: number) =>
    fetch(`/api/allocations/${aid}`, { method: "DELETE", credentials: "include" }),
  queue: (qs: URLSearchParams) =>
    http<QueueOut>(`/api/procurement-queue${qs.toString() ? `?${qs}` : ""}`),
};
```

- [ ] **Step 3: Typecheck**

```bash
docker compose exec web pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/lib/procurement-types.ts apps/web/lib/procurement-fetch.ts
git commit -m "feat(web): procurement TS types + fetch helpers"
```

---

### Task 15: Pills + type tag components

**Files:**
- Create: `apps/web/components/procurement/EtaPill.tsx`
- Create: `apps/web/components/procurement/ShortfallPill.tsx`
- Create: `apps/web/components/procurement/BatchStatusPill.tsx`
- Create: `apps/web/components/procurement/MaterialTypeTag.tsx`

- [ ] **Step 1: EtaPill**

```tsx
"use client";

interface Props { eta: string | null; }

export function EtaPill({ eta }: Props) {
  if (!eta) return <span className="text-h-muted">—</span>;
  const d = new Date(eta);
  const today = new Date(); today.setHours(0,0,0,0);
  const overdue = d < today;
  return (
    <span className={["h-mono text-xs", overdue ? "text-h-bad" : "text-h-ink"].join(" ")}>
      {eta}
    </span>
  );
}
```

- [ ] **Step 2: ShortfallPill**

```tsx
"use client";

interface Props { qty: number; }

export function ShortfallPill({ qty }: Props) {
  if (qty <= 0) {
    return <span className="rounded bg-h-good/20 px-1.5 py-0.5 text-xs text-h-good">OK</span>;
  }
  return (
    <span className="rounded bg-h-bad/20 px-1.5 py-0.5 text-xs text-h-bad">Short {qty}</span>
  );
}
```

- [ ] **Step 3: BatchStatusPill**

```tsx
"use client";
import type { BatchStatus } from "@/lib/procurement-types";

const COPY: Record<BatchStatus, { label: string; cls: string }> = {
  OPEN:       { label: "Open",       cls: "bg-h-muted/20 text-h-muted" },
  IN_TRANSIT: { label: "In transit", cls: "bg-h-warn/20 text-h-warn" },
  DELIVERED:  { label: "Delivered",  cls: "bg-h-good/20 text-h-good" },
  CANCELLED:  { label: "Cancelled",  cls: "bg-h-bad/20 text-h-bad" },
};

export function BatchStatusPill({ status }: { status: BatchStatus }) {
  const c = COPY[status];
  return <span className={`rounded px-1.5 py-0.5 text-xs ${c.cls}`}>{c.label}</span>;
}
```

- [ ] **Step 4: MaterialTypeTag**

```tsx
"use client";
import type { MaterialType } from "@/lib/procurement-types";

const LABEL: Record<MaterialType, string> = {
  BOARD:"Board", HARDWARE:"Hardware", CUSTOM:"Custom",
  BENCHTOP:"Benchtop", APPLIANCE:"Appliance", HIRE:"Hire",
};

export function MaterialTypeTag({ type }: { type: MaterialType }) {
  return <span className="rounded border border-h-line px-1.5 py-0.5 text-xs text-h-muted">{LABEL[type]}</span>;
}
```

- [ ] **Step 5: Typecheck**

```bash
docker compose exec web pnpm tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/procurement
git commit -m "feat(web): procurement pills + material type tag"
```

---

### Task 16: AvailabilityDrawer + tracking integration

**Files:**
- Create: `apps/web/components/procurement/AvailabilityDrawer.tsx`
- Create: `apps/web/app/(app)/tracking/_components/TrackingClient.tsx`
- Modify: `apps/web/components/pm/TrackingGrid.tsx`
- Modify: `apps/web/app/(app)/tracking/page.tsx`

- [ ] **Step 1: Drawer component**

Create `apps/web/components/procurement/AvailabilityDrawer.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { AvailabilityOut } from "@/lib/procurement-types";
import { ProcFetch } from "@/lib/procurement-fetch";
import { ShortfallPill } from "./ShortfallPill";
import { EtaPill } from "./EtaPill";
import { MaterialTypeTag } from "./MaterialTypeTag";

interface Props { itemId: number | null; projectId: number; }

export function AvailabilityDrawer({ itemId, projectId }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const [data, setData] = useState<AvailabilityOut | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (itemId == null) { setData(null); return; }
    let alive = true;
    ProcFetch.itemAvailability(itemId)
      .then(d => { if (alive) setData(d); })
      .catch(e => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, [itemId]);

  function close() {
    const next = new URLSearchParams(params.toString());
    next.delete("drawer");
    next.delete("itemId");
    router.push(`?${next.toString()}`);
  }

  if (itemId == null) return null;

  return (
    <aside
      data-testid="availability-drawer"
      role="dialog"
      aria-label="Item availability"
      className="fixed inset-y-0 right-0 z-30 w-[480px] overflow-y-auto border-l border-h-line bg-h-surface p-4 shadow-xl"
    >
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-h-ink">Item availability</h2>
        <button onClick={close} aria-label="Close drawer" className="text-h-muted hover:text-h-ink">✕</button>
      </header>

      {err && <p className="text-sm text-h-bad">{err}</p>}
      {!data && !err && <p className="text-sm text-h-muted">Loading…</p>}

      {data && (
        <>
          <p className="mb-2 text-sm text-h-muted">
            Item #{data.item_id} · {data.ready} ready / {data.blocked} blocked
          </p>
          <ul className="grid gap-2">
            {data.lines.map(l => {
              const need  = Number(l.qty_needed);
              const alloc = Number(l.qty_allocated_to_line);
              const short = Math.max(0, need - alloc);
              return (
                <li
                  key={l.line_id}
                  data-testid="availability-line"
                  className="rounded-lg border border-h-line bg-h-bg p-3"
                >
                  <div className="flex items-center justify-between">
                    <MaterialTypeTag type={l.material_type} />
                    <ShortfallPill qty={short} />
                  </div>
                  <dl className="mt-2 grid grid-cols-4 gap-2 text-xs">
                    <div><dt className="text-h-muted">Need</dt><dd className="h-mono">{need}</dd></div>
                    <div><dt className="text-h-muted">Allocated</dt><dd className="h-mono">{alloc}</dd></div>
                    <div><dt className="text-h-muted">On order</dt><dd className="h-mono">{Number(l.qty_on_order)}</dd></div>
                    <div><dt className="text-h-muted">ETA</dt><dd><EtaPill eta={l.earliest_eta} /></dd></div>
                  </dl>
                  <div className="mt-2 flex gap-2">
                    <a
                      href={`/projects/${projectId}/procurement?tab=batches&action=order&material_type=${l.material_type}&material_id=${l.material_id}&line_id=${l.line_id}`}
                      data-testid="order-more"
                      className="rounded bg-h-accent px-2 py-1 text-xs text-white hover:opacity-90"
                    >Order more</a>
                    <a
                      href={`/projects/${projectId}/procurement?tab=batches&action=allocate&material_type=${l.material_type}&material_id=${l.material_id}&line_id=${l.line_id}`}
                      className="rounded border border-h-line px-2 py-1 text-xs text-h-ink hover:bg-h-surface"
                    >Allocate</a>
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </aside>
  );
}
```

- [ ] **Step 2: Wrap availability cell in TrackingGrid**

In `apps/web/components/pm/TrackingGrid.tsx`, add a new prop and replace the availability `<td>`:

```tsx
interface Props {
  items: TrackingItemRow[];
  canEdit: boolean;
  onOpenAvailability?: (itemId: number) => void;  // NEW
}
```

Replace the cell that currently renders `<AvailabilityChip ... />`:

```tsx
<td className="px-2 py-1.5">
  {props.onOpenAvailability ? (
    <button
      type="button"
      data-testid="open-availability"
      aria-label="Open item availability"
      onClick={() => props.onOpenAvailability!(it.id)}
      className="rounded px-1 py-0.5 hover:bg-h-bg"
    >
      <AvailabilityChip ready={it.availability.ready} blocked={it.availability.blocked} />
    </button>
  ) : (
    <AvailabilityChip ready={it.availability.ready} blocked={it.availability.blocked} />
  )}
</td>
```

(Adjust to whatever destructuring/parameter style the existing component uses.)

- [ ] **Step 3: TrackingClient wrapper**

Create `apps/web/app/(app)/tracking/_components/TrackingClient.tsx`:

```tsx
"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { TrackingGrid } from "@/components/pm/TrackingGrid";
import { AvailabilityDrawer } from "@/components/procurement/AvailabilityDrawer";
import type { TrackingItemRow } from "@/lib/pm-types";

interface Props {
  items: TrackingItemRow[];
  canEdit: boolean;
  projectId: number;
}

export function TrackingClient({ items, canEdit, projectId }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  function openAvailability(id: number) {
    const next = new URLSearchParams(params.toString());
    next.set("drawer", "item-availability");
    next.set("itemId", String(id));
    router.push(`${pathname}?${next.toString()}`);
  }

  const drawerItem =
    params.get("drawer") === "item-availability"
      ? Number(params.get("itemId") ?? "0") || null
      : null;

  return (
    <>
      <TrackingGrid items={items} canEdit={canEdit} onOpenAvailability={openAvailability} />
      <AvailabilityDrawer itemId={drawerItem} projectId={projectId} />
    </>
  );
}
```

- [ ] **Step 4: Wire it on the tracking page**

In `apps/web/app/(app)/tracking/page.tsx`, replace the direct `<TrackingGrid items={...} canEdit={canEdit} />` render with:

```tsx
<TrackingClient items={grid?.items ?? []} canEdit={canEdit} projectId={pid} />
```

(Add the import: `import { TrackingClient } from "./_components/TrackingClient";`.)

- [ ] **Step 5: Manual smoke**

```bash
docker compose exec api python -m seed.hartwood_joinery
docker compose restart web
```

Open `http://localhost:3000/tracking?project_id=1`. Click on the availability cell of the first row. Drawer opens; URL gains `?...&drawer=item-availability&itemId=1`. ✕ closes; URL params drop.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/procurement/AvailabilityDrawer.tsx \
        apps/web/components/pm/TrackingGrid.tsx \
        apps/web/app/\(app\)/tracking
git commit -m "feat(web): AvailabilityDrawer over /tracking, opened by clicking the chip"
```

---

## Phase 7 — Web: project Procurement page (4 tasks)

### Task 17: `/projects/[id]/procurement` shell + tabs

**Files:**
- Create: `apps/web/app/(app)/projects/[id]/procurement/page.tsx`
- Create: `apps/web/app/(app)/projects/[id]/procurement/_components/ProcurementTabs.tsx`
- Create: `apps/web/app/(app)/projects/[id]/procurement/_components/ProjectMaterialsTable.tsx` (stub)
- Create: `apps/web/app/(app)/projects/[id]/procurement/_components/BatchesTable.tsx` (stub)
- Create: `apps/web/app/(app)/projects/[id]/procurement/_components/CatalogTabs.tsx` (stub)

- [ ] **Step 1: Page shell**

```tsx
// apps/web/app/(app)/projects/[id]/procurement/page.tsx
import { fetchMe } from "@/lib/session";
import { ProcurementTabs } from "./_components/ProcurementTabs";

interface Search {
  tab?: "materials"|"batches"|"catalog";
  catalog_type?: string;
  material_type?: string;
  material_id?: string;
  batch_id?: string;
  action?: "order"|"allocate";
  line_id?: string;
}

export default async function ProjectProcurementPage({
  params, searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const me = await fetchMe();
  const tab = sp.tab ?? "materials";
  const pid = Number(id);
  const canWrite = !!me && (
    me.auth_role === "admin" ||
    me.auth_role === "manager" ||
    me.auth_role === "drafter" ||
    me.auth_role === "purchase_officer"
  );
  return (
    <div className="grid gap-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-h-ink">Procurement</h1>
        <p className="text-xs text-h-muted">Project #{pid}</p>
      </header>
      <ProcurementTabs projectId={pid} tab={tab} canWrite={canWrite} sp={sp} />
    </div>
  );
}
```

- [ ] **Step 2: Tabs**

```tsx
// apps/web/app/(app)/projects/[id]/procurement/_components/ProcurementTabs.tsx
"use client";

import Link from "next/link";
import { ProjectMaterialsTable } from "./ProjectMaterialsTable";
import { BatchesTable } from "./BatchesTable";
import { CatalogTabs } from "./CatalogTabs";

const TABS = ["materials","batches","catalog"] as const;
type Tab = (typeof TABS)[number];

interface Props {
  projectId: number;
  tab: Tab;
  canWrite: boolean;
  sp: Record<string, string | undefined>;
}

export function ProcurementTabs({ projectId, tab, canWrite, sp }: Props) {
  return (
    <>
      <nav role="tablist" className="flex gap-1 border-b border-h-line">
        {TABS.map(t => (
          <Link
            key={t}
            role="tab"
            aria-selected={tab === t}
            href={`/projects/${projectId}/procurement?tab=${t}`}
            className={[
              "px-3 py-2 text-sm capitalize",
              tab === t ? "border-b-2 border-h-accent text-h-ink" : "text-h-muted hover:text-h-ink",
            ].join(" ")}
          >{t}</Link>
        ))}
      </nav>
      <div className="pt-4">
        {tab === "materials" && <ProjectMaterialsTable projectId={projectId} canWrite={canWrite} sp={sp} />}
        {tab === "batches"   && <BatchesTable          projectId={projectId} canWrite={canWrite} sp={sp} />}
        {tab === "catalog"   && <CatalogTabs           canWrite={canWrite} catalogType={sp.catalog_type} />}
      </div>
    </>
  );
}
```

- [ ] **Step 3: Three placeholder stubs**

Create three sibling files in `_components/`:

```tsx
// ProjectMaterialsTable.tsx
"use client";
export function ProjectMaterialsTable(_: { projectId: number; canWrite: boolean; sp: Record<string,string|undefined> }) {
  return <p className="text-sm text-h-muted">Materials table — Task 18</p>;
}
```

```tsx
// BatchesTable.tsx
"use client";
export function BatchesTable(_: { projectId: number; canWrite: boolean; sp: Record<string,string|undefined> }) {
  return <p className="text-sm text-h-muted">Batches table — Task 19</p>;
}
```

```tsx
// CatalogTabs.tsx
"use client";
export function CatalogTabs(_: { canWrite: boolean; catalogType?: string }) {
  return <p className="text-sm text-h-muted">Catalog tabs — Task 20</p>;
}
```

- [ ] **Step 4: Typecheck + manual smoke**

```bash
docker compose exec web pnpm tsc --noEmit
```

Open `http://localhost:3000/projects/1/procurement`. Tabs render; clicking changes URL; placeholder text shown.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/\(app\)/projects/\[id\]/procurement
git commit -m "feat(web): /projects/[id]/procurement shell with three tabs (stubs)"
```

---

### Task 18: ProjectMaterialsTable (real)

**Files:**
- Modify: `apps/web/app/(app)/projects/[id]/procurement/_components/ProjectMaterialsTable.tsx`

- [ ] **Step 1: Replace the stub**

```tsx
"use client";

import { useEffect, useState } from "react";
import type { ProjectMaterialsOut, MaterialType } from "@/lib/procurement-types";
import { ProcFetch } from "@/lib/procurement-fetch";
import { ShortfallPill } from "@/components/procurement/ShortfallPill";
import { EtaPill } from "@/components/procurement/EtaPill";
import { MaterialTypeTag } from "@/components/procurement/MaterialTypeTag";

const TYPES: MaterialType[] = ["BOARD","HARDWARE","CUSTOM","BENCHTOP","APPLIANCE","HIRE"];

interface Props {
  projectId: number;
  canWrite: boolean;
  sp: Record<string, string | undefined>;
}

export function ProjectMaterialsTable({ projectId }: Props) {
  const [data, setData] = useState<ProjectMaterialsOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<MaterialType>>(new Set(TYPES));

  useEffect(() => {
    let alive = true;
    ProcFetch.projectMaterials(projectId)
      .then(d => { if (alive) setData(d); })
      .catch(e => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, [projectId]);

  if (err)   return <p className="text-sm text-h-bad">{err}</p>;
  if (!data) return <p className="text-sm text-h-muted">Loading…</p>;

  const grouped = Object.fromEntries(
    TYPES.map(t => [t, data.rows.filter(r => r.material_type === t)])
  ) as Record<MaterialType, ProjectMaterialsOut["rows"]>;

  function toggle(t: MaterialType) {
    const next = new Set(open);
    next.has(t) ? next.delete(t) : next.add(t);
    setOpen(next);
  }

  return (
    <div className="grid gap-4">
      {TYPES.map(t => {
        const rows = grouped[t];
        if (rows.length === 0) return null;
        const isOpen = open.has(t);
        return (
          <section key={t} className="rounded-lg border border-h-line bg-h-surface">
            <button
              type="button"
              onClick={() => toggle(t)}
              className="flex w-full items-center justify-between border-b border-h-line px-3 py-2 text-left"
            >
              <span className="flex items-center gap-2">
                <MaterialTypeTag type={t} />
                <span className="text-sm text-h-muted">{rows.length} item(s)</span>
              </span>
              <span className="text-h-muted">{isOpen ? "▾" : "▸"}</span>
            </button>
            {isOpen && (
              <table className="w-full text-sm">
                <thead className="bg-h-bg text-xs uppercase text-h-muted">
                  <tr>
                    <th className="px-2 py-1 text-left">Material</th>
                    <th className="px-2 py-1 text-right">Demand</th>
                    <th className="px-2 py-1 text-right">On order</th>
                    <th className="px-2 py-1 text-right">Received</th>
                    <th className="px-2 py-1 text-right">Allocated</th>
                    <th className="px-2 py-1 text-left">Shortfall</th>
                    <th className="px-2 py-1 text-left">ETA</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={`${r.material_type}-${r.material_id}`} className="border-t border-h-line">
                      <td className="px-2 py-1">
                        {r.name}
                        {r.sku ? <span className="ml-2 h-mono text-xs text-h-muted">{r.sku}</span> : null}
                      </td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_demand)}</td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_on_order)}</td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_received)}</td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_allocated)}</td>
                      <td className="px-2 py-1"><ShortfallPill qty={Number(r.shortfall)} /></td>
                      <td className="px-2 py-1"><EtaPill eta={r.earliest_eta} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Smoke test**

After Task 22 expands the seed, this view shows real data. For now, manually create a batch (see Task 18 step 2 in the spec); open `http://localhost:3000/projects/1/procurement?tab=materials`; the Hardware section shows the batch.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/\(app\)/projects/\[id\]/procurement/_components/ProjectMaterialsTable.tsx
git commit -m "feat(web): ProjectMaterialsTable with collapsible sections + ETA/shortfall pills"
```

---

### Task 19: BatchesTable + BatchDrawer + AllocationEditor

**Files:**
- Create: `apps/web/app/(app)/projects/[id]/procurement/_components/AllocationEditor.tsx`
- Create: `apps/web/app/(app)/projects/[id]/procurement/_components/BatchDrawer.tsx`
- Modify: `apps/web/app/(app)/projects/[id]/procurement/_components/BatchesTable.tsx`

- [ ] **Step 1: AllocationEditor**

```tsx
"use client";

import { useEffect, useState } from "react";
import { ProcFetch } from "@/lib/procurement-fetch";
import type { AllocationListOut, AllocationOut } from "@/lib/procurement-types";

interface Props { batchId: number; canWrite: boolean; }

export function AllocationEditor({ batchId, canWrite }: Props) {
  const [data, setData]   = useState<AllocationListOut | null>(null);
  const [lineId, setLine] = useState("");
  const [qty, setQty]     = useState("1");
  const [err, setErr]     = useState<string | null>(null);

  async function refresh() {
    try { setData(await ProcFetch.listAllocations(batchId)); }
    catch (e) { setErr(String(e)); }
  }
  useEffect(() => { refresh(); }, [batchId]);

  async function add() {
    setErr(null);
    try {
      await ProcFetch.createAllocation(batchId, {
        item_hardware_line_id: Number(lineId),
        qty_allocated: Number(qty),
      });
      setLine(""); setQty("1");
      await refresh();
    } catch (e) { setErr(String(e)); }
  }

  async function del(a: AllocationOut) {
    await ProcFetch.deleteAllocation(a.allocation_id);
    await refresh();
  }

  if (!data) return <p className="text-sm text-h-muted">Loading allocations…</p>;
  const remaining = Number(data.qty_remaining);

  return (
    <div className="grid gap-2">
      <p className="text-xs text-h-muted">
        Allocated <span className="h-mono">{data.qty_allocated_total}</span> /
        received <span className="h-mono">{data.qty_received}</span> ·
        remaining <span className={["h-mono", remaining > 0 ? "text-h-warn" : "text-h-good"].join(" ")}>{remaining}</span>
      </p>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase text-h-muted">
          <tr><th className="text-left">Item</th><th className="text-right">Qty</th><th /></tr>
        </thead>
        <tbody>
          {data.allocations.map(a => (
            <tr key={a.allocation_id} className="border-t border-h-line">
              <td className="py-1">{a.item_code ?? "—"} · {a.item_description ?? ""}</td>
              <td className="text-right h-mono">{Number(a.qty_allocated)}</td>
              <td className="text-right">
                {canWrite && (
                  <button onClick={() => del(a)} className="text-h-bad hover:underline" aria-label="Delete allocation">
                    remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {canWrite && (
        <div className="flex gap-2">
          <input
            type="number"
            value={lineId}
            onChange={e => setLine(e.target.value)}
            placeholder="line_id"
            className="w-32 rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
            data-testid="alloc-line-id"
          />
          <input
            type="number"
            value={qty}
            onChange={e => setQty(e.target.value)}
            placeholder="qty"
            className="w-24 rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
            data-testid="alloc-qty"
          />
          <button
            onClick={add}
            data-testid="alloc-add"
            className="rounded bg-h-accent px-2 py-1 text-sm text-white"
          >+ Allocate</button>
          {err && <span className="text-xs text-h-bad">{err}</span>}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: BatchDrawer**

```tsx
"use client";

import { useEffect, useState } from "react";
import type { BatchOut } from "@/lib/procurement-types";
import { ProcFetch } from "@/lib/procurement-fetch";
import { AllocationEditor } from "./AllocationEditor";
import { BatchStatusPill } from "@/components/procurement/BatchStatusPill";

interface Props {
  projectId: number;
  initial?: Partial<BatchOut>;
  batchId: number | null;
  canWrite: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function BatchDrawer({ projectId, initial, batchId, canWrite, onClose, onSaved }: Props) {
  const [batch, setBatch] = useState<Partial<BatchOut>>(initial ?? {});
  const [err, setErr]     = useState<string | null>(null);

  useEffect(() => {
    if (batchId == null) return;
    fetch(`/api/batches/${batchId}`, { credentials: "include" })
      .then(r => r.json())
      .then(setBatch)
      .catch(e => setErr(String(e)));
  }, [batchId]);

  async function save() {
    setErr(null);
    try {
      if (batchId == null) {
        await ProcFetch.createBatch({ ...batch, project_id: projectId });
      } else {
        await ProcFetch.patchBatch(batchId, batch);
      }
      onSaved();
      onClose();
    } catch (e) { setErr(String(e)); }
  }

  function field<K extends keyof BatchOut>(k: K, v: BatchOut[K]) {
    setBatch(prev => ({ ...prev, [k]: v }));
  }

  return (
    <aside
      role="dialog" data-testid="batch-drawer"
      className="fixed inset-y-0 right-0 z-30 w-[520px] overflow-y-auto border-l border-h-line bg-h-surface p-4 shadow-xl"
    >
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-h-ink">
          {batchId == null ? "New batch" : `Batch #${batchId}`}
          {batch.status && <span className="ml-2"><BatchStatusPill status={batch.status} /></span>}
        </h2>
        <button onClick={onClose} aria-label="Close drawer" className="text-h-muted hover:text-h-ink">✕</button>
      </header>

      {err && <p className="text-sm text-h-bad">{err}</p>}

      <div className="grid gap-2">
        <label className="grid gap-1 text-sm">
          <span className="text-h-muted">Material type</span>
          <select
            value={batch.material_type ?? ""}
            onChange={e => field("material_type", e.target.value as BatchOut["material_type"])}
            disabled={!canWrite || batchId != null}
            data-testid="batch-material-type"
            className="rounded border border-h-line bg-h-bg px-2 py-1"
          >
            <option value="">—</option>
            {["BOARD","HARDWARE","CUSTOM","BENCHTOP","APPLIANCE","HIRE"].map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          <span className="text-h-muted">Material id</span>
          <input
            type="number"
            value={String(batch.material_id ?? "")}
            onChange={e => field("material_id", Number(e.target.value))}
            disabled={!canWrite || batchId != null}
            data-testid="batch-material-id"
            className="rounded border border-h-line bg-h-bg px-2 py-1 h-mono"
          />
        </label>
        {(["supplier","po_ref"] as const).map(k => (
          <label key={k} className="grid gap-1 text-sm">
            <span className="text-h-muted">{k.replace("_"," ")}</span>
            <input
              value={String(batch[k] ?? "")}
              onChange={e => field(k, e.target.value)}
              disabled={!canWrite}
              data-testid={`batch-${k}`}
              className="rounded border border-h-line bg-h-bg px-2 py-1"
            />
          </label>
        ))}
        <div className="grid grid-cols-2 gap-2">
          {(["qty_ordered","qty_received"] as const).map(k => (
            <label key={k} className="grid gap-1 text-sm">
              <span className="text-h-muted">{k.replace("_"," ")}</span>
              <input
                type="number"
                value={String(batch[k] ?? "")}
                onChange={e => field(k, e.target.value as never)}
                disabled={!canWrite}
                data-testid={`batch-${k}`}
                className="rounded border border-h-line bg-h-bg px-2 py-1 h-mono"
              />
            </label>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {(["ordered_date","eta_date","received_date"] as const).map(k => (
            <label key={k} className="grid gap-1 text-sm">
              <span className="text-h-muted">{k.replace("_date","")}</span>
              <input
                type="date"
                value={String(batch[k] ?? "")}
                onChange={e => field(k, e.target.value as never)}
                disabled={!canWrite}
                data-testid={`batch-${k}`}
                className="rounded border border-h-line bg-h-bg px-2 py-1 h-mono"
              />
            </label>
          ))}
        </div>
        <label className="grid gap-1 text-sm">
          <span className="text-h-muted">Notes</span>
          <textarea
            value={String(batch.notes ?? "")}
            onChange={e => field("notes", e.target.value)}
            disabled={!canWrite}
            data-testid="batch-notes"
            className="rounded border border-h-line bg-h-bg px-2 py-1"
          />
        </label>

        {canWrite && (
          <div className="flex gap-2">
            <button onClick={save} data-testid="save-batch" className="rounded bg-h-accent px-3 py-1 text-sm text-white">
              Save
            </button>
            {batchId != null && batch.status !== "CANCELLED" && (
              <button
                onClick={async () => {
                  if (!confirm("Cancel this batch?")) return;
                  const r = await ProcFetch.cancelBatch(batchId);
                  if (!r.ok) setErr(await r.text());
                  else { onSaved(); onClose(); }
                }}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-bad"
              >Cancel batch</button>
            )}
          </div>
        )}
      </div>

      {batchId != null && (
        <section className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-h-ink">Allocations</h3>
          <AllocationEditor batchId={batchId} canWrite={canWrite} />
        </section>
      )}
    </aside>
  );
}
```

- [ ] **Step 3: BatchesTable (real)**

Replace the stub:

```tsx
"use client";

import { useEffect, useState } from "react";
import type { BatchOut } from "@/lib/procurement-types";
import { ProcFetch } from "@/lib/procurement-fetch";
import { BatchStatusPill } from "@/components/procurement/BatchStatusPill";
import { EtaPill } from "@/components/procurement/EtaPill";
import { BatchDrawer } from "./BatchDrawer";

interface Props {
  projectId: number;
  canWrite: boolean;
  sp: Record<string, string | undefined>;
}

export function BatchesTable({ projectId, canWrite, sp }: Props) {
  const [rows, setRows] = useState<BatchOut[]>([]);
  const [editId, setEditId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  const orderInitial = sp.action === "order" && sp.material_type && sp.material_id
    ? {
        material_type: sp.material_type as BatchOut["material_type"],
        material_id:   Number(sp.material_id),
      }
    : undefined;

  async function refresh() {
    const qs = new URLSearchParams({ project_id: String(projectId) });
    setRows((await ProcFetch.listBatches(qs)).batches);
  }
  useEffect(() => { refresh(); }, [projectId]);
  // Auto-open the create drawer if we landed via "Order more"
  useEffect(() => { if (orderInitial) setCreating(true); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  return (
    <>
      <div className="mb-3 flex justify-end">
        {canWrite && (
          <button
            data-testid="new-batch"
            onClick={() => setCreating(true)}
            className="rounded bg-h-accent px-3 py-1 text-sm text-white"
          >+ New batch</button>
        )}
      </div>
      <table className="w-full text-sm">
        <thead className="bg-h-bg text-xs uppercase text-h-muted">
          <tr>
            <th className="px-2 py-1 text-left">PO</th>
            <th className="px-2 py-1 text-left">Supplier</th>
            <th className="px-2 py-1 text-left">Material</th>
            <th className="px-2 py-1 text-right">Ordered</th>
            <th className="px-2 py-1 text-right">Received</th>
            <th className="px-2 py-1 text-right">Allocated</th>
            <th className="px-2 py-1 text-left">ETA</th>
            <th className="px-2 py-1 text-left">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(b => (
            <tr
              key={b.batch_id}
              className="border-t border-h-line cursor-pointer hover:bg-h-bg"
              onClick={() => setEditId(b.batch_id)}
              data-testid="batch-row"
            >
              <td className="px-2 py-1 h-mono">{b.po_ref ?? "—"}</td>
              <td className="px-2 py-1">{b.supplier ?? "—"}</td>
              <td className="px-2 py-1">{b.material_type} #{b.material_id}</td>
              <td className="px-2 py-1 text-right h-mono">{Number(b.qty_ordered)}</td>
              <td className="px-2 py-1 text-right h-mono">{Number(b.qty_received)}</td>
              <td className="px-2 py-1 text-right h-mono">{Number(b.qty_allocated)}</td>
              <td className="px-2 py-1"><EtaPill eta={b.eta_date} /></td>
              <td className="px-2 py-1"><BatchStatusPill status={b.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {(editId != null || creating) && (
        <BatchDrawer
          projectId={projectId}
          batchId={editId}
          initial={creating ? orderInitial : undefined}
          canWrite={canWrite}
          onClose={() => { setEditId(null); setCreating(false); }}
          onSaved={refresh}
        />
      )}
    </>
  );
}
```

- [ ] **Step 4: Smoke test**

Open `http://localhost:3000/projects/1/procurement?tab=batches`. Click "+ New batch" → drawer opens. Material type HARDWARE / id 1 / supplier "Acme" / qty_ordered 5 → Save. Drawer closes; row appears with status `OPEN`. Click row → drawer re-opens; fill `ordered_date` → status flips to `IN_TRANSIT`.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/\(app\)/projects/\[id\]/procurement/_components
git commit -m "feat(web): BatchesTable + BatchDrawer + AllocationEditor"
```

---

### Task 20: CatalogTabs (real)

**Files:**
- Modify: `apps/web/app/(app)/projects/[id]/procurement/_components/CatalogTabs.tsx`

- [ ] **Step 1: Replace stub**

```tsx
"use client";

import { useEffect, useState } from "react";

const TYPES = ["board","hardware","custom_made","benchtop","appliance","hire"] as const;
type CatType = typeof TYPES[number];

const CREATE_FIELDS: Record<CatType, string[]> = {
  board:       ["material_name","sku"],
  hardware:    ["material_name","sku"],
  custom_made: ["description","sku"],
  benchtop:    ["material_name","sku"],
  appliance:   ["model_name","sku"],
  hire:        ["description"],
};

interface Props { canWrite: boolean; catalogType?: string; }

export function CatalogTabs({ canWrite, catalogType }: Props) {
  const initial = (TYPES as readonly string[]).includes(catalogType ?? "")
    ? (catalogType as CatType) : "hardware";
  const [type, setType] = useState<CatType>(initial);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    try {
      const r = await fetch(`/api/catalogs/${type}`, { credentials: "include" });
      if (!r.ok) throw new Error(await r.text());
      setRows((await r.json()).rows);
    } catch (e) { setErr(String(e)); }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [type]);

  async function create() {
    const r = await fetch(`/api/catalogs/${type}`, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draft),
    });
    if (!r.ok) { setErr(await r.text()); return; }
    setDraft({});
    refresh();
  }

  return (
    <div className="grid gap-3">
      <nav className="flex gap-1 border-b border-h-line">
        {TYPES.map(t => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={[
              "px-3 py-2 text-sm capitalize",
              t === type ? "border-b-2 border-h-accent text-h-ink" : "text-h-muted hover:text-h-ink",
            ].join(" ")}
          >{t.replace("_"," ")}</button>
        ))}
      </nav>

      {err && <p className="text-sm text-h-bad">{err}</p>}

      <table className="w-full text-sm">
        <thead className="bg-h-bg text-xs uppercase text-h-muted">
          <tr>
            {Object.keys(rows[0] ?? {}).filter(k => k !== "type").map(k => (
              <th key={k} className="px-2 py-1 text-left">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-h-line">
              {Object.entries(r).filter(([k]) => k !== "type").map(([k,v]) => (
                <td key={k} className="px-2 py-1">{String(v ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {canWrite && (
        <div className="flex gap-2">
          {CREATE_FIELDS[type].map(f => (
            <input
              key={f}
              value={draft[f] ?? ""}
              onChange={e => setDraft(d => ({ ...d, [f]: e.target.value }))}
              placeholder={f}
              className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
            />
          ))}
          <button onClick={create} className="rounded bg-h-accent px-3 py-1 text-sm text-white">+ Add</button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Smoke**

Open `http://localhost:3000/projects/1/procurement?tab=catalog`. Tabs render; selecting `hardware` shows seeded entries; adding a new row appears in the list.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/\(app\)/projects/\[id\]/procurement/_components/CatalogTabs.tsx
git commit -m "feat(web): CatalogTabs CRUD for the 6 material catalogs"
```

---

## Phase 8 — Web: Orderbook cross-project queue (1 task)

### Task 21: Replace `/orderbook` stub

**Files:**
- Modify: `apps/web/app/(app)/orderbook/page.tsx`
- Create: `apps/web/app/(app)/orderbook/_components/QueueClient.tsx`

- [ ] **Step 1: Server page**

```tsx
// apps/web/app/(app)/orderbook/page.tsx
import { QueueClient } from "./_components/QueueClient";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; supplier?: string; project_id?: string }>;
}) {
  const sp = await searchParams;
  return (
    <div className="grid gap-4">
      <header><h1 className="text-2xl font-semibold text-h-ink">Orderbook</h1></header>
      <QueueClient initial={sp} />
    </div>
  );
}
```

- [ ] **Step 2: QueueClient**

```tsx
// apps/web/app/(app)/orderbook/_components/QueueClient.tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { BatchStatusPill } from "@/components/procurement/BatchStatusPill";
import { EtaPill } from "@/components/procurement/EtaPill";
import { ProcFetch } from "@/lib/procurement-fetch";
import type { QueueRow } from "@/lib/procurement-types";

const STATUSES = ["OPEN","IN_TRANSIT","DELIVERED","CANCELLED"] as const;

interface Props { initial: { status?: string; supplier?: string; project_id?: string; }; }

export function QueueClient({ initial }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const [rows, setRows] = useState<QueueRow[]>([]);
  const [err, setErr]   = useState<string | null>(null);
  const status   = params.get("status")   ?? initial.status   ?? "";
  const supplier = params.get("supplier") ?? initial.supplier ?? "";

  useEffect(() => {
    const qs = new URLSearchParams();
    if (status)   qs.set("status", status);
    if (supplier) qs.set("supplier", supplier);
    ProcFetch.queue(qs)
      .then(b => setRows(b.rows))
      .catch(e => setErr(String(e)));
  }, [status, supplier]);

  function setParam(k: string, v: string) {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v); else next.delete(k);
    router.push(`?${next.toString()}`);
  }

  const grouped = new Map<string, QueueRow[]>();
  for (const r of rows) {
    const key = r.supplier ?? "(no supplier)";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(r);
  }

  return (
    <>
      <div className="flex flex-wrap gap-2 rounded-lg border border-h-line bg-h-surface p-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-h-muted">Status</span>
          <select
            value={status}
            onChange={e => setParam("status", e.target.value)}
            className="rounded border border-h-line bg-h-bg px-2 py-1"
          >
            <option value="">All</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <input
          type="search"
          value={supplier}
          onChange={e => setParam("supplier", e.target.value)}
          placeholder="Supplier"
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
        />
      </div>

      {err && <p className="text-sm text-h-bad">{err}</p>}

      {[...grouped.entries()].map(([sup, batches]) => (
        <section key={sup} className="rounded-lg border border-h-line bg-h-surface">
          <h2 className="border-b border-h-line px-3 py-2 text-sm font-semibold text-h-ink">{sup}</h2>
          <table className="w-full text-sm">
            <thead className="bg-h-bg text-xs uppercase text-h-muted">
              <tr>
                <th className="px-2 py-1 text-left">PO</th>
                <th className="px-2 py-1 text-left">Project</th>
                <th className="px-2 py-1 text-left">Material</th>
                <th className="px-2 py-1 text-right">Ordered</th>
                <th className="px-2 py-1 text-right">Received</th>
                <th className="px-2 py-1 text-left">ETA</th>
                <th className="px-2 py-1 text-left">Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {batches.map(b => (
                <tr key={b.batch_id} className="border-t border-h-line">
                  <td className="px-2 py-1 h-mono">{b.po_ref ?? "—"}</td>
                  <td className="px-2 py-1">{b.project_code} · {b.project_name}</td>
                  <td className="px-2 py-1">{b.material_name ?? `${b.material_type} #${b.material_id}`}</td>
                  <td className="px-2 py-1 text-right h-mono">{Number(b.qty_ordered)}</td>
                  <td className="px-2 py-1 text-right h-mono">{Number(b.qty_received)}</td>
                  <td className="px-2 py-1"><EtaPill eta={b.eta_date} /></td>
                  <td className="px-2 py-1"><BatchStatusPill status={b.status} /></td>
                  <td className="px-2 py-1 text-right">
                    <Link
                      href={`/projects/${b.project_id}/procurement?tab=batches&batch_id=${b.batch_id}`}
                      className="text-h-accent hover:underline"
                    >Open</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}
```

- [ ] **Step 3: Smoke**

Open `http://localhost:3000/orderbook` as `rin.park`. Should show rows grouped by supplier (after Task 22 expands the seed; today, only manually-created batches will appear).

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/\(app\)/orderbook
git commit -m "feat(web): /orderbook cross-project queue grouped by supplier"
```

---

## Phase 9 — Polish, seed expansion, CLAUDE.md (3 tasks)

### Task 22: Seed extension — batches + allocations covering the demo

**Files:**
- Modify: `seed/hartwood_joinery.py`

- [ ] **Step 1: Add the seed block**

In `seed/hartwood_joinery.py`, **after** the existing block that creates `item_hardware_lines`, append:

```python
# --- procurement_v1 demo: 1 delivered + 1 in-transit batch + 1 allocation ---
proj_alfred_id = db.execute(
    text("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")
).scalar()

catalog_first = db.execute(text(
    "SELECT phc.catalog_id, phc.material_type, phc.material_id "
    "  FROM project_hardware_catalog phc "
    " WHERE phc.project_id = :p ORDER BY phc.catalog_id LIMIT 1"
), {"p": proj_alfred_id}).mappings().first()

if catalog_first:
    line_first = db.execute(text(
        "SELECT ihl.line_id, ihl.qty FROM item_hardware_lines ihl "
        "  JOIN items i ON i.item_id = ihl.item_id "
        " WHERE i.project_id = :p AND ihl.catalog_id = :c "
        " ORDER BY ihl.line_id LIMIT 1"
    ), {"p": proj_alfred_id, "c": catalog_first["catalog_id"]}).mappings().first()

    if line_first:
        delivered_id = db.execute(text(
            "INSERT INTO procurement_batches "
            "  (project_id, material_type, material_id, supplier, po_ref, "
            "   qty_ordered, qty_received, ordered_date, received_date) "
            "VALUES (:p, :mt, :mid, 'Acme Hardware', 'PO-ALF-001', "
            "        :qty, :qty, CURRENT_DATE - 14, CURRENT_DATE - 1) "
            "ON CONFLICT DO NOTHING "
            "RETURNING batch_id"
        ), {
            "p":   proj_alfred_id,
            "mt":  catalog_first["material_type"],
            "mid": catalog_first["material_id"],
            "qty": int(line_first["qty"]) - 1 if int(line_first["qty"]) > 1 else int(line_first["qty"]),
        }).scalar()

        db.execute(text(
            "INSERT INTO procurement_batches "
            "  (project_id, material_type, material_id, supplier, po_ref, "
            "   qty_ordered, ordered_date, eta_date) "
            "VALUES (:p, :mt, :mid, 'Acme Hardware', 'PO-ALF-002', "
            "        10, CURRENT_DATE - 2, CURRENT_DATE + 7) "
            "ON CONFLICT DO NOTHING"
        ), {
            "p":   proj_alfred_id,
            "mt":  catalog_first["material_type"],
            "mid": catalog_first["material_id"],
        })

        if delivered_id:
            db.execute(text(
                "INSERT INTO batch_allocations(batch_id, item_hardware_line_id, qty_allocated) "
                "VALUES (:b, :l, 1) "
                "ON CONFLICT (batch_id, item_hardware_line_id) DO NOTHING"
            ), {"b": delivered_id, "l": line_first["line_id"]})
```

- [ ] **Step 2: Re-seed**

```bash
docker compose exec api python -m seed.hartwood_joinery
```

Expected: same final summary line + no errors. Project ALF-001 now has 1 delivered + 1 in-transit batch + 1 allocation.

- [ ] **Step 3: Smoke the data**

```bash
cookie=$(mktemp)
curl -s -c "$cookie" -X POST http://localhost:3000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"rin.park@hartwood.test","password":"hartwood-dev","workspace_slug":"hartwood-joinery"}' >/dev/null
curl -s -b "$cookie" http://localhost:3000/api/procurement-queue | python -m json.tool | head -40
```

Expected: ≥2 rows with supplier `Acme Hardware`, statuses `DELIVERED` and `IN_TRANSIT`.

- [ ] **Step 4: Commit**

```bash
git add seed/hartwood_joinery.py
git commit -m "feat(seed): demo procurement batches + allocation for Alfred project"
```

---

### Task 23: Playwright E2E `procurement.spec.ts`

**Files:**
- Create: `tests/e2e/procurement.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "@playwright/test";

test("Procurement resolution flow", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]',    "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });

  await page.goto("/tracking?project_id=1");
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();

  // Click availability chip on first row → drawer opens
  await page.locator('[data-testid="open-availability"]').first().click();
  await expect(page).toHaveURL(/drawer=item-availability/, { timeout: 10_000 });
  await expect(page.locator('[data-testid="availability-drawer"]')).toBeVisible();
  await expect(page.locator('[data-testid="availability-line"]').first()).toBeVisible();

  // "Order more" → routes to project procurement page with create-batch drawer auto-open
  await page.locator('[data-testid="order-more"]').first().click();
  await expect(page).toHaveURL(/\/projects\/1\/procurement\?.*action=order/, { timeout: 30_000 });
  await expect(page.locator('[data-testid="batch-drawer"]')).toBeVisible();

  // Fill the batch form and save
  await page.locator('[data-testid="batch-supplier"]').fill("Test Supplier");
  await page.locator('[data-testid="batch-qty_ordered"]').fill("10");
  await page.locator('[data-testid="batch-eta_date"]').fill("2026-06-01");
  await page.locator('[data-testid="save-batch"]').click();

  await expect(page.locator('[data-testid="batch-drawer"]')).not.toBeVisible({ timeout: 10_000 });

  // Confirm the new row exists
  await page.goto("/projects/1/procurement?tab=batches");
  await expect(page.getByText("Test Supplier")).toBeVisible({ timeout: 10_000 });
});
```

- [ ] **Step 2: Re-seed and run the suite**

```bash
docker compose exec api python -m seed.hartwood_joinery
docker compose restart web
```

Wait for `/api/health` to return 200, then:

```bash
docker run --rm --ipc=host --add-host=host.docker.internal:host-gateway \
  -v "$(pwd)":/work -w /work/apps/web \
  -e PW_BASE_URL=http://host.docker.internal:3000 \
  -e NODE_PATH=/work/apps/web/node_modules \
  mcr.microsoft.com/playwright:v1.59.1-noble \
  bash -c "node_modules/.bin/playwright test --reporter=list"
```

Expected: 4 passed (smoke + drafter_editor + pm_workbench + procurement).

> If the spec is flaky in `next dev`, restart the `web` container before each run — Turbopack Fast Refresh can race with navigation (this is documented in the PM Workbench post-mortem).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/procurement.spec.ts
git commit -m "test(e2e): procurement resolution flow"
```

---

### Task 24: CLAUDE.md note + final acceptance + merge

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append the Procurement Workbench section to `CLAUDE.md`**

```markdown

## Procurement Workbench (sub-project #4)

- New backend module `apps/api/app/procurement_v1/` mounted at top-level paths
  (`/projects/{pid}/materials`, `/batches`, `/batches/{bid}/allocations`,
  `/catalogs/{type}`, `/procurement-queue`). The legacy `/procurement/*`
  namespace (orders, vendors, budget, approvals) is **left untouched** and is
  not used by the v1 product surface.
- Migration 0012 adds `procurement_batches.cancelled_at` and two indexes
  (`idx_batches_supplier`, `idx_alloc_batch`).
- `drafter` auth_role is **elevated to PM-parity** on the `orderbook` module
  (read+write+approve+comment) — this widens the matrix narrowed in 0008.
- Web routes:
  - `/orderbook` — cross-project queue grouped by supplier.
  - `/projects/[id]/procurement?tab=materials|batches|catalog` — project
    Procurement page.
  - `/tracking` adds an item-scoped `AvailabilityDrawer` triggered by
    clicking the availability chip; URL state
    `?drawer=item-availability&itemId=N`.
- Soft-cancel semantics: DELETE on `/batches/{bid}` sets `cancelled_at`. A
  batch with non-zero allocations returns 409 — the user must remove
  allocations first.
- Allocation over-commit: POST/PATCH on `/allocations` returns 409 when
  `sum(allocated) > qty_received` (or `qty_ordered` if not yet received).
- Status pill is **derived in SQL** via `CASE`; never persisted.
- Seed (`make seed`) inserts one delivered batch + one in-transit batch +
  one allocation on project ALF-001 so the resolution-flow demo works
  out of the box.
```

Also add, in the "Reference docs" section near the top, this line near the existing PM Workbench reference:

```markdown
- `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md` — Procurement Workbench v1 spec.
- `docs/superpowers/plans/2026-04-28-procurement-workbench.md` — 24-task implementation plan for sub-project #4.
```

- [ ] **Step 2: Run the full verification loop**

```bash
docker compose exec -w /db api alembic current
docker compose exec api python -m seed.hartwood_joinery
docker compose exec api pytest -q
```

Expected: alembic at `0012 (head)`. Seed succeeds. pytest reports `~145 passed` (118 prior + ~27 new).

```bash
docker compose exec api python -m seed.hartwood_joinery
docker compose restart web
docker run --rm --ipc=host --add-host=host.docker.internal:host-gateway \
  -v "$(pwd)":/work -w /work/apps/web \
  -e PW_BASE_URL=http://host.docker.internal:3000 \
  -e NODE_PATH=/work/apps/web/node_modules \
  mcr.microsoft.com/playwright:v1.59.1-noble \
  bash -c "node_modules/.bin/playwright test --reporter=list"
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): Procurement Workbench dev notes + final acceptance"
```

- [ ] **Step 4: Merge into `feat/foundation`** (only if you've been working on a separate branch)

If you started this plan from a `feat/procurement-workbench` branch:

```bash
git checkout feat/foundation
git merge --no-ff feat/procurement-workbench -m "Merge feat/procurement-workbench: Procurement Workbench v1 (sub-project #4)"
```

If you committed directly on `feat/foundation`, skip the merge step — the linear history serves as its own merge.

---

## Plan completion criteria

- [ ] All 24 tasks committed in order.
- [ ] Migration 0012 applied; `procurement_batches.cancelled_at` column visible.
- [ ] `drafter` matrix shows `orderbook: {read, write, approve, comment}`.
- [ ] Pytest suite green, including the ~27 new procurement_v1 tests.
- [ ] Playwright suite green: smoke + pm_workbench + drafter_editor + procurement.
- [ ] `make seed` produces a workspace where `/orderbook` shows ≥2 batches and `/projects/1/procurement?tab=materials` shows the rollup with shortfall.
- [ ] Branch merged into `feat/foundation` with `--no-ff` (or linear if you skipped branching).
- [ ] CLAUDE.md updated.

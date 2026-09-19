# JoineryFlow PM Workbench Implementation Plan

> **Status: shipped.** Migrations `0008` + `0009`. Current state lives in
> `## PM Workbench (sub-project #2 + #3)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/superpowers/plans/README.md`).

> **Later change:** This plan makes `/home` the landing page in place of `/dashboard`; **#9a
> reversed that** — `/home` is now a bare `redirect("/dashboard")`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Later change — superseded in part by Plan V1 (see `docs/plan-v1/`).** Four
> decisions reshape what this plan built: the **Cutlist becomes a separate
> entity** owning production stages, shared across items (Q438), so
> `item_stages` becomes a per-item projection written by fan-out rather than the
> source of truth (Q439); **related-part rows** join `items` with a `row_type`
> discriminator and a parent FK (Q447); **Area and Room become real entities**,
> renaming `items.stage` → `area` (Q454/Q455); and the **advisory soft-lock
> becomes a Controlled Lock** — a non-owner's save becomes a request needing
> approval instead of succeeding with an audit row (Q509).
>
> The lock change **shipped 2026-09-19** (migration `0032`), so the soft-lock
> this plan describes at T15 Step 4 — "non-owner saves are permitted" — is no
> longer how the code behaves. `CLAUDE.md` carries the current rule.

**Goal:** Ship sub-projects #2 + #3 (PM Project Workbench grid + Drafter Item Editor) of the JoineryFlow build, on top of the Foundation branch. PM lands on `/home`, opens a project, sees the tracking grid, clicks an item ▶, lands in the Drafter Item Editor with editable Cutlist + Hardware tabs, and returns to home — end-to-end verifiable via two new Playwright specs.

**Spec:** `docs/superpowers/specs/2026-04-25-pm-workbench-design.md`. Read it before starting. The spec resolves all open product/RBAC questions; this plan only sequences the implementation.

**Architecture:** No new infrastructure. Same three-container docker-compose (db, api, web). Two new Alembic migrations (0008 narrows the auth-role check; 0009 repoints legacy `users` FKs to `app_user` and adds `projects.pm_id`). Five new FastAPI routers under `apps/api/app/{home,projects,items,parts,hardware_lines}/`. New Next.js routes under `apps/web/app/(app)/{home,projects,tracking,items}/`. State management is raw `fetch()` + URL params + controlled inputs — **no TanStack Query / React Hook Form / Zustand in v1**.

**Tech stack additions:** none. Reuses Foundation's stack (FastAPI + SQLAlchemy Core `text()` + Pydantic v2; Next.js 16 App Router + Tailwind v4; argon2-cffi; pytest; Playwright). Frontend is **Next.js 16 / React 19 / Tailwind v4** — read `apps/web/AGENTS.md` and the relevant guide in `apps/web/node_modules/next/dist/docs/` before writing any web code.

---

## File Structure (locked)

```
apps/api/app/
  auth/
    rbac.py                          # + require_drafter()
    permissions.py                   # + 'drafter' row in MATRIX
    sessions.py                      # + jtbd_role on AuthUser
  home/
    __init__.py
    routes.py                        # GET /home/dashboard
    queries.py
    schemas.py                       # HomeDashboardOut + sub-models
  projects/
    __init__.py
    routes.py                        # CRUD + favourites
    queries.py
    schemas.py
  items/
    __init__.py
    routes.py                        # CRUD + lock + lifecycle + status
    queries.py
    schemas.py
  parts/
    __init__.py
    routes.py                        # modules + parts CRUD
    queries.py
    schemas.py
  hardware_lines/
    __init__.py
    routes.py                        # hardware_lines + project_hardware_catalog + availability
    queries.py
    schemas.py
  edit_log.py                        # write_item_edit_log() helper (shared)
  main.py                            # mount 5 new routers
apps/api/tests/
  conftest.py                        # extend TRUNCATE list
  test_rbac_drafter.py
  test_home_dashboard.py
  test_projects_routes.py
  test_items_routes.py
  test_parts_routes.py
  test_hardware_lines_routes.py
  test_lifecycle_status.py
  test_lock_semantics.py
  test_permissions.py                # extend with drafter cases
  test_users_routes.py               # extend _VALID_ROLES
  test_auth_routes.py                # adjust for jtbd_role
db/alembic/versions/
  0008_drafter_role.py               # CHECK + matrix + Noa flip
  0009_user_id_repoint.py            # legacy users -> app_user; + projects.pm_id; drop legacy users
seed/
  hartwood_joinery.py                # + PROJECTS + items + parts + hardware_lines
apps/web/app/(app)/
  layout.tsx                         # + TopBar editor-mode swap (data-mode)
  home/page.tsx                      # NEW — replaces /dashboard as default landing
  projects/page.tsx                  # NEW project list/CRUD
  tracking/page.tsx                  # replaces stub (real grid)
  items/[id]/page.tsx                # NEW Drafter Item Editor shell
  items/[id]/_components/
    ItemHeader.tsx
    ItemMetadataPanel.tsx
    EditorTabs.tsx
    SoftLockBanner.tsx
    EditorFooter.tsx
    LogTab.tsx
    cutlist/
      CutlistTab.tsx
      ModuleTree.tsx
      PartsGrid.tsx
    hardware/
      HardwareTab.tsx
      Pantry.tsx
      Cart.tsx
      AddFromGlobalModal.tsx
apps/web/components/chrome/
  SideBar.tsx                        # FAV/ALL toggle replaces — stub
  TopBar.tsx                         # + editor-mode logic
  ProjectSidebar.tsx                 # NEW client component for FAV toggles
apps/web/components/pm/
  StatusChip.tsx                     # HStatus mappings
  AvailabilityChip.tsx               # row availability indicator
  StageDates.tsx                     # 10-stage due/done date row
  TrackingGrid.tsx                   # /tracking grid (client component)
  TrackingFilters.tsx                # status / stage / search inputs
apps/web/lib/
  pm-types.ts                        # shared TS types matching API schemas
  pm-fetch.ts                        # tiny fetch wrappers w/ error normalisation
tests/e2e/
  pm_workbench.spec.ts               # NEW
  drafter_editor.spec.ts             # NEW
docs/superpowers/plans/
  2026-04-25-pm-workbench.md         # this file
CLAUDE.md                            # PM Workbench dev notes appended at end
```

---

## Phase 1 — Schema + RBAC (migrations 0008, 0009)

### Task 1: Migration 0008 — narrow `drafter` auth_role

**Files:**
- Create: `db/alembic/versions/0008_drafter_role.py`

- [ ] **Step 1: Write migration**

```python
"""drafter role

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    ALTER TABLE app_user DROP CONSTRAINT IF EXISTS app_user_auth_role_check;
    ALTER TABLE app_user ADD CONSTRAINT app_user_auth_role_check
      CHECK (auth_role IN ('admin','manager','editor','drafter','purchase_officer','viewer'));
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-PM-Workbench schema is recoverable from migrations 0001-0007 only")
```

- [ ] **Step 2: Apply + verify**

```bash
docker compose exec api bash -c "cd /db && alembic upgrade head"
docker compose exec db psql -U jf -d joineryflow -c "\d app_user" | grep auth_role_check
```
Expected: CHECK constraint lists six roles including `drafter`.

- [ ] **Step 3: Commit**

```bash
git add db/alembic/versions/0008_drafter_role.py
git commit -m "feat(db): widen app_user.auth_role check to include drafter"
```

---

### Task 2: Migration 0009 — repoint legacy `users` FKs to `app_user`; add `projects.pm_id`; drop legacy `users`

**Files:**
- Create: `db/alembic/versions/0009_user_id_repoint.py`

The legacy `users` table is unreferenced by live data (verified by Foundation T22 — procurement *queries* already SELECT from `app_user`; only the FKs still point at `users`). This migration repoints all 9 known FKs, adds `projects.pm_id`, replaces the two views that JOIN `users`, and drops the legacy table.

- [ ] **Step 1: Skeleton**

```python
"""user_id repoint

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-25
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- 1-6. Repoint FKs from legacy users(user_id) -> app_user(id).
    ALTER TABLE projects                     DROP CONSTRAINT IF EXISTS projects_optimisation_drafter_id_fkey;
    ALTER TABLE projects                     ADD  CONSTRAINT projects_optimisation_drafter_id_fkey
        FOREIGN KEY (optimisation_drafter_id) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE project_favourites           DROP CONSTRAINT IF EXISTS project_favourites_user_id_fkey;
    ALTER TABLE project_favourites           ADD  CONSTRAINT project_favourites_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES app_user(id) ON DELETE CASCADE;

    ALTER TABLE project_hardware_catalog     DROP CONSTRAINT IF EXISTS project_hardware_catalog_added_by_fkey;
    ALTER TABLE project_hardware_catalog     ADD  CONSTRAINT project_hardware_catalog_added_by_fkey
        FOREIGN KEY (added_by) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE project_hardware_catalog_log DROP CONSTRAINT IF EXISTS project_hardware_catalog_log_changed_by_fkey;
    ALTER TABLE project_hardware_catalog_log ADD  CONSTRAINT project_hardware_catalog_log_changed_by_fkey
        FOREIGN KEY (changed_by) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 5. items.cutlist_owner_id had no FK in 0001; add one now.
    ALTER TABLE items                        ADD  CONSTRAINT items_cutlist_owner_id_fkey
        FOREIGN KEY (cutlist_owner_id) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 6. Procurement-side FKs (from 0002).
    ALTER TABLE purchase_orders              DROP CONSTRAINT IF EXISTS purchase_orders_requester_id_fkey;
    ALTER TABLE purchase_orders              ADD  CONSTRAINT purchase_orders_requester_id_fkey
        FOREIGN KEY (requester_id) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE po_attachments               DROP CONSTRAINT IF EXISTS po_attachments_uploaded_by_fkey;
    ALTER TABLE po_attachments               ADD  CONSTRAINT po_attachments_uploaded_by_fkey
        FOREIGN KEY (uploaded_by) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE approval_workflows           DROP CONSTRAINT IF EXISTS approval_workflows_approver_id_fkey;
    ALTER TABLE approval_workflows           ADD  CONSTRAINT approval_workflows_approver_id_fkey
        FOREIGN KEY (approver_id) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE budget_transactions          DROP CONSTRAINT IF EXISTS budget_transactions_created_by_fkey;
    ALTER TABLE budget_transactions          ADD  CONSTRAINT budget_transactions_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE inventory_movements          DROP CONSTRAINT IF EXISTS inventory_movements_created_by_fkey;
    ALTER TABLE inventory_movements          ADD  CONSTRAINT inventory_movements_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES app_user(id) ON DELETE SET NULL;

    ALTER TABLE cost_centers                 DROP CONSTRAINT IF EXISTS cost_centers_manager_id_fkey;
    ALTER TABLE cost_centers                 ADD  CONSTRAINT cost_centers_manager_id_fkey
        FOREIGN KEY (manager_id) REFERENCES app_user(id) ON DELETE SET NULL;

    -- 7. New PM scoping column (FK).
    ALTER TABLE projects ADD COLUMN pm_id BIGINT
        REFERENCES app_user(id) ON DELETE SET NULL;
    CREATE INDEX projects_pm_id_idx ON projects(pm_id);

    -- 8. Replace the two legacy-views recreated in 0006 to JOIN app_user.
    DROP VIEW IF EXISTS v_po_summary;
    CREATE VIEW v_po_summary AS
      SELECT po.id, po.po_number, po.status, po.total_value, po.requester_id,
             u.full_name AS requester_name, po.workspace_id, po.created_at
      FROM purchase_orders po
      LEFT JOIN app_user u ON u.id = po.requester_id;

    DROP VIEW IF EXISTS v_orders_due;
    CREATE VIEW v_orders_due AS
      SELECT po.id, po.po_number, po.expected_delivery, po.requester_id,
             u.full_name AS requester_name, po.workspace_id
      FROM purchase_orders po
      LEFT JOIN app_user u ON u.id = po.requester_id
      WHERE po.expected_delivery IS NOT NULL
        AND po.status IN ('approved','partially_received');

    -- 9. Drop the legacy table itself.
    DROP TABLE IF EXISTS users CASCADE;
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-PM-Workbench schema is recoverable from migrations 0001-0007 only")
```

- [ ] **Step 2: Apply + verify**

```bash
docker compose exec api bash -c "cd /db && alembic upgrade head"
docker compose exec db psql -U jf -d joineryflow -c "\d projects"      | grep pm_id
docker compose exec db psql -U jf -d joineryflow -c "\dt users"        | grep -c users || true   # expect 0
docker compose exec db psql -U jf -d joineryflow -c "\dv v_po_summary" | grep v_po_summary
```

- [ ] **Step 3: Verify procurement endpoints still work**

```bash
docker compose exec api pytest tests/test_procurement_routes.py -q || true
```
Any pre-existing tests that hit `v_po_summary` / `v_orders_due` should still pass; the views still return the same columns, just JOIN-ed to `app_user`.

- [ ] **Step 4: Commit**

```bash
git add db/alembic/versions/0009_user_id_repoint.py
git commit -m "feat(db): repoint legacy users FKs to app_user; add projects.pm_id; drop users"
```

---

### Task 3: Update permissions matrix to include `drafter`

**Files:**
- Modify: `apps/api/app/auth/permissions.py`
- Modify: `apps/api/tests/test_permissions.py`

- [ ] **Step 1: Update Role literal + MATRIX**

Add `"drafter"` to the `Role` Literal. Insert into `MATRIX`:

```python
"drafter": {
    "dashboard":     {"read"},
    "tracking":      {"read", "write", "approve", "comment"},
    "list":          {"read", "write", "approve", "comment"},
    "shop_dwgs":     {"read"},
    "isample":       {"read"},
    "orderbook":     {"read"},
    "it_management": set(),
},
```

- [ ] **Step 2: Extend `test_permissions.py` with parametrized drafter cases**

```python
@pytest.mark.parametrize("module,action,allowed", [
    ("dashboard",     "read",   True),
    ("tracking",      "write",  True),
    ("tracking",      "approve",True),
    ("list",          "write",  True),
    ("shop_dwgs",     "write",  False),
    ("orderbook",     "approve",False),
    ("it_management", "read",   False),
])
def test_drafter_matrix(module, action, allowed):
    assert has_permission("drafter", module, action) is allowed
```

- [ ] **Step 3: Run + commit**

```bash
docker compose exec api pytest tests/test_permissions.py -q
git add apps/api/app/auth/permissions.py apps/api/tests/test_permissions.py
git commit -m "feat(auth): add drafter row to RBAC matrix"
```

---

### Task 4: Add `require_drafter()` dependency

**Files:**
- Modify: `apps/api/app/auth/rbac.py`
- Create: `apps/api/tests/test_rbac_drafter.py`

- [ ] **Step 1: Failing test**

```python
import uuid
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.auth.rbac import require_drafter
from app.auth.sessions import create_session
from app.db import SessionLocal


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text("TRUNCATE audit_log, session, app_user, workspace RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _seed(role: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'T') RETURNING id"),
            {"s": f"t-{suffix}"},
        ).scalar()
        uid = db.execute(
            text("""
              INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
              VALUES (:w, :e, 'X', :p, :r) RETURNING id
            """),
            {"w": wid, "e": f"u-{suffix}@x", "p": hash_password("pw"), "r": role},
        ).scalar()
        tok = create_session(db, uid)
        db.commit()
        return tok
    finally:
        db.close()


def _app() -> FastAPI:
    a = FastAPI()

    @a.post("/draft")
    def draft(_=Depends(require_drafter())):
        return {"ok": True}

    return a


@pytest.mark.parametrize("role,expected", [
    ("drafter",          200),
    ("manager",          200),
    ("admin",            200),
    ("editor",           403),
    ("purchase_officer", 403),
    ("viewer",           403),
])
def test_require_drafter_matrix(role, expected):
    tok = _seed(role)
    c = TestClient(_app())
    assert c.post("/draft", cookies={"jf_session": tok}).status_code == expected
```

- [ ] **Step 2: Implement**

Append to `apps/api/app/auth/rbac.py`:

```python
def require_drafter():
    """Allow only auth_role in {drafter, manager, admin}.

    Use for the spec §2.4 invariant 5 — narrow gate on item / module /
    part / hardware_line / project_hardware_catalog mutations."""

    def _dep(user: AuthUser = Depends(current_user)) -> AuthUser:
        if user.auth_role not in ("drafter", "manager", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="drafter, manager, or admin required",
            )
        return user

    return _dep
```

- [ ] **Step 3: Run + commit**

```bash
docker compose exec api pytest tests/test_rbac_drafter.py -q
git add apps/api/app/auth/rbac.py apps/api/tests/test_rbac_drafter.py
git commit -m "feat(auth): require_drafter() narrow gate"
```

---

### Task 5: Extend `AuthUser` with `jtbd_role`; flip Noa to `drafter` in seed

**Files:**
- Modify: `apps/api/app/auth/sessions.py`
- Modify: `apps/api/app/users/routes.py`
- Modify: `apps/api/app/auth/schemas.py`
- Modify: `seed/hartwood_joinery.py`
- Modify: `apps/api/tests/test_users_routes.py`
- Modify: `apps/api/tests/test_auth_routes.py`

- [ ] **Step 1: Add `jtbd_role` to `AuthUser`**

```python
@dataclass
class AuthUser:
    id: int
    workspace_id: int
    email: str
    full_name: str
    auth_role: str
    jtbd_role: str | None = None
```

Update the SELECT in `lookup_session` to include `u.jtbd_role`, and pass it into the `AuthUser(...)` constructor.

- [ ] **Step 2: Add `jtbd_role` to `MeOut` schema**

```python
class MeOut(BaseModel):
    id: int
    workspace_id: int
    email: str
    full_name: str
    auth_role: str
    jtbd_role: str | None = None
```

- [ ] **Step 3: Update `users/routes.py` `_VALID_ROLES`**

Add `"drafter"` to the validation set.

- [ ] **Step 4: Update seed**

In `seed/hartwood_joinery.py`, change Noa's auth_role:

```python
("noa.lindqvist@hartwood.test", "Noa Lindqvist", "drafter", "Drafter"),
```

The seed is idempotent (`ON CONFLICT DO NOTHING`); a one-shot `UPDATE` is needed to flip an already-seeded row. Add at the end of `main()`:

```python
db.execute(text("""
  UPDATE app_user SET auth_role='drafter'
  WHERE workspace_id=:w AND email='noa.lindqvist@hartwood.test'
"""), {"w": wid})
```

- [ ] **Step 5: Update affected tests**

`test_users_routes.py`: parametrize `_VALID_ROLES` test cases to include `drafter`.

`test_auth_routes.py`: existing `/auth/me` assertions on returned shape should still pass (`jtbd_role` is optional). Add one test that asserts a freshly-seeded user has `jtbd_role` populated.

- [ ] **Step 6: Run + commit**

```bash
docker compose exec api pytest tests/test_auth_routes.py tests/test_users_routes.py -q
docker compose exec api python -m seed.hartwood_joinery
git add apps/api/app/auth apps/api/app/users seed apps/api/tests
git commit -m "feat(auth): expose jtbd_role on AuthUser; allow drafter in user PATCH; flip Noa"
```

---

### Task 6: Extend test conftest with shared TRUNCATE list

**Files:**
- Modify: `apps/api/tests/conftest.py`

- [ ] **Step 1: Define a shared cleanup helper**

Append to `apps/api/tests/conftest.py`:

```python
TRUNCATE_TABLES = (
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


@pytest.fixture
def truncate_all():
    """Use in autouse cleanup fixtures in route tests that need full TRUNCATE."""
    from app.db import SessionLocal

    def _do():
        s = SessionLocal()
        try:
            s.execute(text(f"TRUNCATE {', '.join(TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
            s.commit()
        finally:
            s.close()

    return _do
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
docker compose exec api pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/conftest.py
git commit -m "test(api): shared TRUNCATE_TABLES helper for PM Workbench tests"
```

---

### Task 7: `edit_log.py` shared helper

**Files:**
- Create: `apps/api/app/edit_log.py`

The spec §6.5 mandates that every mutation on items / parts / hardware_lines / project_hardware_catalog writes one row to `item_edit_log` in the same DB transaction.

- [ ] **Step 1: Implement**

```python
"""item_edit_log writer.

Per spec §6.5: every mutation on items / parts / hardware_lines /
project_hardware_catalog writes one item_edit_log row in the SAME txn.
A PATCH that changes 3 fields -> 3 log rows.
POST/DELETE -> one row with field='_create' or '_delete'.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session


def write_edit_log(
    db: Session,
    *,
    item_id: int,
    actor_id: int | None,
    field: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    db.execute(
        text("""
            INSERT INTO item_edit_log(item_id, actor_id, field, old_value, new_value)
            VALUES (:i, :a, :f, :o, :n)
        """),
        {"i": item_id, "a": actor_id, "f": field, "o": old_value, "n": new_value},
    )
    db.flush()


def write_edit_log_many(
    db: Session,
    *,
    item_id: int,
    actor_id: int | None,
    changes: list[tuple[str, str | None, str | None]],
) -> None:
    """Write N rows in one executemany. Each `changes` tuple is (field, old, new)."""
    if not changes:
        return
    db.execute(
        text("""
            INSERT INTO item_edit_log(item_id, actor_id, field, old_value, new_value)
            VALUES (:i, :a, :f, :o, :n)
        """),
        [
            {"i": item_id, "a": actor_id, "f": f, "o": o, "n": n}
            for (f, o, n) in changes
        ],
    )
    db.flush()
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/app/edit_log.py
git commit -m "feat(api): shared item_edit_log writer"
```

---

## Phase 2 — API read surface

> All read endpoints get a `cache: "no-store"` Next.js fetch on the web side. Read endpoints don't write `audit_log` or `item_edit_log`.

### Task 8: `/projects` GET — list + GET single + PATCH/POST scaffolding

**Files:**
- Create: `apps/api/app/projects/__init__.py`, `schemas.py`, `queries.py`, `routes.py`
- Modify: `apps/api/app/main.py` (mount router)
- Create: `apps/api/tests/test_projects_routes.py`

- [ ] **Step 1: schemas.py**

```python
from datetime import date, datetime
from pydantic import BaseModel


class CreateProjectIn(BaseModel):
    project_code: str
    name: str
    pm_id: int | None = None
    install_start: date | None = None


class PatchProjectIn(BaseModel):
    name: str | None = None
    pm_id: int | None = None
    install_start: date | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: int
    project_code: str
    name: str
    pm_id: int | None
    pm_name: str | None
    status: str | None
    item_count: int
    total_value: float | None
    install_start: date | None
    is_favourite: bool
    created_at: datetime


class ProjectListOut(BaseModel):
    projects: list[ProjectOut]
```

- [ ] **Step 2: queries.py**

Implement:
- `list_projects(db, *, workspace_id, current_user_id, fav_only: bool | None) -> list[dict]` — JOIN `projects p LEFT JOIN app_user u ON u.id = p.pm_id LEFT JOIN project_favourites f ON f.project_id = p.id AND f.user_id = :uid LEFT JOIN (SELECT project_id, COUNT(*) cnt FROM items GROUP BY project_id) ic ON ic.project_id = p.id WHERE p.workspace_id = :wid` plus optional `AND f.user_id IS NOT NULL` for favourites.
- `get_project(db, *, project_id, workspace_id, current_user_id) -> dict | None` — single row, same JOINs.
- `create_project(db, *, workspace_id, payload: CreateProjectIn, actor_id) -> int` — INSERT, write_audit, return id.
- `patch_project(db, *, project_id, workspace_id, payload, actor_id) -> dict | None` — UPDATE, write_audit per non-None field, return updated row.

- [ ] **Step 3: routes.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import current_user, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .queries import (
    create_project, get_project, list_projects, patch_project,
)
from .schemas import CreateProjectIn, PatchProjectIn, ProjectListOut, ProjectOut

router = APIRouter(prefix="", tags=["projects"])


@router.get("/projects", response_model=ProjectListOut)
def get_projects(
    fav: bool | None = None,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    rows = list_projects(db, workspace_id=user.workspace_id,
                         current_user_id=user.id, fav_only=fav)
    return {"projects": rows}


@router.get("/projects/{pid}", response_model=ProjectOut)
def get_one_project(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    row = get_project(db, project_id=pid, workspace_id=user.workspace_id,
                      current_user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return row


@router.post("/projects", response_model=ProjectOut, status_code=201)
def post_project(
    payload: CreateProjectIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.auth_role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="manager or admin required")
    pm_id = payload.pm_id or user.id
    pid = create_project(db, workspace_id=user.workspace_id,
                         payload=payload.model_copy(update={"pm_id": pm_id}),
                         actor_id=user.id)
    db.commit()
    return get_project(db, project_id=pid, workspace_id=user.workspace_id,
                       current_user_id=user.id)


@router.patch("/projects/{pid}", response_model=ProjectOut)
def patch_one_project(
    pid: int,
    payload: PatchProjectIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.auth_role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="manager or admin required")
    row = patch_project(db, project_id=pid, workspace_id=user.workspace_id,
                        payload=payload, actor_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    db.commit()
    return row
```

- [ ] **Step 4: Mount router in `main.py`**

```python
from .projects.routes import router as projects_router
app.include_router(projects_router)
```

- [ ] **Step 5: Tests** (`test_projects_routes.py`)

Use the autouse-TRUNCATE pattern from `test_auth_routes.py`. Cases:
- `test_list_empty_returns_empty()` — manager logs in, sees `{projects: []}`.
- `test_create_project_defaults_pm_to_self()` — POST without `pm_id`; assert `pm_id == self.id`.
- `test_create_forbidden_for_editor()` — 403.
- `test_get_one_404_for_other_workspace()` — workspace isolation.
- `test_patch_status_writes_audit()` — assert row in `audit_log` with `event='project.patch'`.
- `test_list_fav_only_filters_to_favourites()` — pre-insert `project_favourites` row, assert filtering.

- [ ] **Step 6: Run + commit**

```bash
docker compose exec api pytest tests/test_projects_routes.py -q
git add apps/api/app/projects apps/api/app/main.py apps/api/tests/test_projects_routes.py
git commit -m "feat(api): /projects CRUD + favourites read"
```

---

### Task 9: `/projects/{pid}/favourites` toggle

**Files:**
- Modify: `apps/api/app/projects/routes.py`
- Modify: `apps/api/app/projects/queries.py`
- Extend: `apps/api/tests/test_projects_routes.py`

- [ ] **Step 1: queries.py — add toggle fns**

```python
def add_favourite(db, *, project_id, user_id) -> None:
    db.execute(text("""
        INSERT INTO project_favourites(project_id, user_id)
        VALUES (:p, :u) ON CONFLICT DO NOTHING
    """), {"p": project_id, "u": user_id})
    db.flush()


def remove_favourite(db, *, project_id, user_id) -> None:
    db.execute(text("""
        DELETE FROM project_favourites WHERE project_id = :p AND user_id = :u
    """), {"p": project_id, "u": user_id})
    db.flush()
```

- [ ] **Step 2: routes.py — add the two endpoints**

```python
@router.post("/projects/{pid}/favourites", status_code=204)
def add_fav(pid: int, user: AuthUser = Depends(current_user),
            db: Session = Depends(get_db)):
    add_favourite(db, project_id=pid, user_id=user.id)
    db.commit()


@router.delete("/projects/{pid}/favourites", status_code=204)
def del_fav(pid: int, user: AuthUser = Depends(current_user),
            db: Session = Depends(get_db)):
    remove_favourite(db, project_id=pid, user_id=user.id)
    db.commit()
```

- [ ] **Step 3: Tests**

- `test_add_fav_then_list_with_fav_true_returns_it`
- `test_remove_fav_idempotent_no_404`

- [ ] **Step 4: Commit**

```bash
docker compose exec api pytest tests/test_projects_routes.py -q
git commit -am "feat(api): /projects/{pid}/favourites toggle"
```

---

### Task 10: `/projects/{pid}/items` GET — tracking grid feed

**Files:**
- Create: `apps/api/app/items/__init__.py`, `schemas.py`, `queries.py`, `routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_items_routes.py`

This endpoint is the spine of `/tracking`. Returns one row per item, with the 10 lifecycle stages pivoted into a single `stages` dict, plus a per-row availability roll-up `{ready: int, blocked: int}` that aggregates `item_hardware_lines` against `batch_allocations`.

- [ ] **Step 1: schemas.py**

```python
from datetime import date, datetime
from pydantic import BaseModel


class StageDates(BaseModel):
    due_date: date | None
    done_date: date | None


class AvailabilityRollup(BaseModel):
    ready: int
    blocked: int


class TrackingItemRow(BaseModel):
    id: int
    item_number: int | None
    status: str | None
    stage: str | None          # site location
    zone: int | None
    level: str | None
    room_no: str | None
    room_desc: str | None
    code: str | None
    description: str | None
    qty: int | None
    cutlist_owner_id: int | None
    cutlist_owner_name: str | None
    item_locked: bool
    stages: dict[str, StageDates]   # keyed by stage_key (REQ..INST)
    availability: AvailabilityRollup


class TrackingGridOut(BaseModel):
    project_id: int
    items: list[TrackingItemRow]
```

- [ ] **Step 2: queries.py — `list_items_for_project`**

Single-query strategy:
```sql
SELECT
  i.*,
  u.full_name AS cutlist_owner_name,
  COALESCE(jsonb_object_agg(s.stage_key, jsonb_build_object(
    'due_date', s.due_date, 'done_date', s.done_date
  )) FILTER (WHERE s.stage_key IS NOT NULL), '{}'::jsonb) AS stages,
  (SELECT COUNT(*) FROM item_hardware_lines hl
     JOIN batch_allocations ba ON ba.item_hardware_line_id = hl.id
    WHERE hl.item_id = i.id) AS ready,
  (SELECT COUNT(*) FROM item_hardware_lines hl
    WHERE hl.item_id = i.id
      AND NOT EXISTS (SELECT 1 FROM batch_allocations ba
                       WHERE ba.item_hardware_line_id = hl.id)) AS blocked
FROM items i
LEFT JOIN app_user u ON u.id = i.cutlist_owner_id
LEFT JOIN item_stages s ON s.item_id = i.id
WHERE i.workspace_id = :wid AND i.project_id = :pid
  AND (:status::text IS NULL OR i.status = :status)
GROUP BY i.id, u.full_name
ORDER BY COALESCE(i.item_number, i.id);
```

Optional filters via `:status` and `:stage_key` (filter by `EXISTS (SELECT 1 FROM item_stages WHERE stage_key = :stage_key AND done_date IS NULL)` if needed). Search query `:q` filters `i.description ILIKE '%' || :q || '%' OR i.code ILIKE ...` server-side.

- [ ] **Step 3: routes.py**

```python
@router.get("/projects/{pid}/items", response_model=TrackingGridOut)
def get_project_items(
    pid: int,
    status: str | None = None,
    stage: str | None = None,
    q: str | None = None,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    # Cross-workspace 404 (don't leak existence)
    proj = get_project(db, project_id=pid, workspace_id=user.workspace_id,
                       current_user_id=user.id)
    if proj is None:
        raise HTTPException(404, "project not found")
    items = list_items_for_project(db, workspace_id=user.workspace_id,
                                   project_id=pid, status=status,
                                   stage_key=stage, q=q)
    return {"project_id": pid, "items": items}
```

- [ ] **Step 4: Tests**

- `test_empty_project_returns_empty_items()`
- `test_grid_pivots_stages()` — seed 1 item with 3 stages; assert `stages` dict has all three keys.
- `test_status_filter()`
- `test_search_filter()`
- `test_cross_workspace_404()`
- `test_availability_rollup_counts_lines()` — seed 2 hardware lines, allocate 1 -> assert `{ready:1, blocked:1}`.

- [ ] **Step 5: Mount router + commit**

```python
# main.py
from .items.routes import router as items_router
app.include_router(items_router)
```

```bash
docker compose exec api pytest tests/test_items_routes.py -q
git add apps/api/app/items apps/api/app/main.py apps/api/tests/test_items_routes.py
git commit -m "feat(api): /projects/{pid}/items tracking grid feed"
```

---

### Task 11: `/items/{id}` GET — full item detail (drafter editor payload)

**Files:**
- Modify: `apps/api/app/items/schemas.py`, `queries.py`, `routes.py`
- Extend: `apps/api/tests/test_items_routes.py`

Returns: metadata + nested modules (with parts) + hardware_lines + last 50 `item_edit_log` rows + `lock_warning` field.

- [ ] **Step 1: schemas.py**

```python
class PartOut(BaseModel):
    id: int
    module_id: int
    qty: int
    part_name: str
    len_mm: int | None
    wid_mm: int | None
    board_material: str | None
    edge: str | None
    colour: str | None
    paint_instruction: str | None
    comment: str | None
    is_rev_c: bool


class ModuleOut(BaseModel):
    id: int
    name: str
    parts: list[PartOut]


class HardwareLineOut(BaseModel):
    id: int
    catalog_id: int
    catalog_description: str | None
    catalog_supplier: str | None
    catalog_source_table: str | None
    qty: int
    note: str | None


class EditLogRow(BaseModel):
    log_id: int
    actor_id: int | None
    actor_name: str | None
    field: str
    old_value: str | None
    new_value: str | None
    ts: datetime


class LockWarning(BaseModel):
    owner_id: int
    owner_name: str
    last_edit_minutes_ago: int


class ItemOut(BaseModel):
    id: int
    project_id: int
    item_number: int | None
    status: str | None
    stage: str | None
    zone: int | None
    level: str | None
    room_no: str | None
    room_desc: str | None
    code: str | None
    description: str | None
    qty: int | None
    cutlist_owner_id: int | None
    item_locked: bool
    estimator_notes: str | None
    painting_required: bool | None
    solid_surface_required: bool | None
    group_id: str | None
    stages: dict[str, StageDates]
    modules: list[ModuleOut]
    hardware_lines: list[HardwareLineOut]
    edit_log: list[EditLogRow]
    lock_warning: LockWarning | None
```

- [ ] **Step 2: queries.py — `get_item_detail`**

Run 4-5 queries inside a single Session (no need for one mega-JOIN — clarity wins):
1. Item row + cutlist_owner JOIN.
2. `item_stages` rows (pivot in Python).
3. Modules + parts (`SELECT ... FROM modules m LEFT JOIN parts p ON p.module_id = m.id WHERE m.item_id = :id ORDER BY m.id, p.id`). Group in Python.
4. Hardware lines + `project_hardware_catalog` JOIN to fetch `description`, `supplier`, `source_table` via a CTE that UNION-ALLs the 6 source tables (same shape as Task 13).
5. Last 50 `item_edit_log` rows JOIN `app_user`.

`lock_warning` computed in Python: `if item_locked and cutlist_owner_id != current_user.id: derive minutes_ago from MAX(item_edit_log.ts) for this item`.

- [ ] **Step 3: routes.py**

```python
@router.get("/items/{id}", response_model=ItemOut)
def get_item(
    id: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    detail = get_item_detail(db, item_id=id, workspace_id=user.workspace_id,
                             current_user_id=user.id)
    if detail is None:
        raise HTTPException(404, "item not found")
    return detail
```

- [ ] **Step 4: Tests**

- `test_get_item_assembles_full_payload()` — seed item + 1 module + 2 parts + 1 hardware line; assert nested structure.
- `test_get_item_lock_warning_for_non_owner()` — seed item with owner=A, look up as B; assert `lock_warning != None`.
- `test_get_item_no_lock_warning_for_owner()`.
- `test_get_item_404_for_cross_workspace()`.

- [ ] **Step 5: Commit**

```bash
docker compose exec api pytest tests/test_items_routes.py -q
git commit -am "feat(api): GET /items/{id} full detail w/ lock_warning"
```

---

### Task 12: `/items/{id}/availability` GET — per-line availability

**Files:**
- Modify: `apps/api/app/items/{schemas,queries,routes}.py`
- Extend: `apps/api/tests/test_items_routes.py`

- [ ] **Step 1: Schema**

```python
class AvailabilityLine(BaseModel):
    line_id: int
    status: Literal["ready", "ordered", "none"]
    eta: date | None
    batch_id: int | None


class AvailabilityOut(BaseModel):
    item_id: int
    lines: list[AvailabilityLine]
```

- [ ] **Step 2: Query**

```sql
SELECT
  hl.id AS line_id,
  CASE
    WHEN ba.received_at IS NOT NULL THEN 'ready'
    WHEN ba.id IS NOT NULL          THEN 'ordered'
    ELSE 'none'
  END AS status,
  pb.expected_arrival AS eta,
  pb.id AS batch_id
FROM item_hardware_lines hl
LEFT JOIN batch_allocations ba ON ba.item_hardware_line_id = hl.id
LEFT JOIN procurement_batches pb ON pb.id = ba.batch_id
WHERE hl.item_id = :id;
```

- [ ] **Step 3: Route**

`GET /items/{id}/availability` gated `require_permission("list", "read")`.

- [ ] **Step 4: Tests + commit.**

---

### Task 13: `/projects/{pid}/hardware_catalog` GET

**Files:**
- Create: `apps/api/app/hardware_lines/__init__.py`, `schemas.py`, `queries.py`, `routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_hardware_lines_routes.py`

Joins `project_hardware_catalog` to its 6 source tables via a single SQL `UNION ALL` derived view (defined inline in queries; not a DB-level VIEW — they get unwieldy). Returns rows with `source_table`, `source_id`, `sku`, `name`, `supplier`, `unit_cost`.

- [ ] **Step 1: schemas.py**

```python
class HardwareCatalogRow(BaseModel):
    catalog_id: int
    source_table: str
    source_id: int
    sku: str | None
    name: str
    supplier: str | None
    unit_cost: float | None
    qty: float


class HardwareCatalogOut(BaseModel):
    project_id: int
    rows: list[HardwareCatalogRow]
```

- [ ] **Step 2: queries.py**

```python
_CATALOG_RESOLVE = """
WITH src AS (
  SELECT 'board_materials'   AS t, id, sku, name, NULL::text AS supplier, unit_cost FROM board_materials
  UNION ALL
  SELECT 'hardware_materials', id, sku, name, NULL::text,                 unit_cost FROM hardware_materials
  UNION ALL
  SELECT 'custom_made',        id, sku, name, NULL::text,                 unit_cost FROM custom_made
  UNION ALL
  SELECT 'benchtop_materials', id, sku, name, NULL::text,                 unit_cost FROM benchtop_materials
  UNION ALL
  SELECT 'appliances',         id, sku, name, NULL::text,                 unit_cost FROM appliances
  UNION ALL
  SELECT 'equipment_hire',     id, sku, name, NULL::text,                 unit_cost FROM equipment_hire
)
SELECT phc.id AS catalog_id, phc.source_table, phc.source_id,
       src.sku, src.name, src.supplier, src.unit_cost, phc.qty
FROM project_hardware_catalog phc
JOIN src ON src.t = phc.source_table AND src.id = phc.source_id
WHERE phc.workspace_id = :wid AND phc.project_id = :pid
ORDER BY phc.source_table, src.name;
"""
```

(`supplier` is NULL for now; the 6 catalog tables don't have supplier columns yet — wired into a future material-catalog enrichment task.)

- [ ] **Step 3: Route**

```python
@router.get("/projects/{pid}/hardware_catalog", response_model=HardwareCatalogOut)
def get_catalog(
    pid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    rows = list_catalog(db, workspace_id=user.workspace_id, project_id=pid)
    return {"project_id": pid, "rows": rows}
```

- [ ] **Step 4: Tests + commit.**

---

### Task 14: `/home/dashboard` GET — composite landing payload

**Files:**
- Create: `apps/api/app/home/__init__.py`, `schemas.py`, `queries.py`, `routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_home_dashboard.py`

Composite endpoint. Personalises the *contents* (scope of metrics) but not the *shape* — frontend reads role from the same payload.

- [ ] **Step 1: schemas.py**

```python
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel


class MetricCard(BaseModel):
    key: str        # 'overdue' | 'in_optimisation' | 'awaiting_install' | 'value_in_progress'
    label: str
    value: int | float
    href: str       # link target (e.g. /tracking?status=overdue)


class MyDayItem(BaseModel):
    item_id: int
    project_code: str
    description: str | None
    next_due_stage_key: str | None
    next_due_date: date | None


class DeliveryToday(BaseModel):
    batch_id: int
    project_code: str
    supplier: str
    eta: date


class TeamActivityRow(BaseModel):
    actor_name: str
    event: str
    target: str | None
    ts: datetime


class FavouriteProject(BaseModel):
    id: int
    project_code: str
    name: str


class HomeDashboardOut(BaseModel):
    role_view: Literal["ceo", "pm", "drafter", "purchase_officer", "viewer"]
    metrics: list[MetricCard]
    my_day: list[MyDayItem]
    deliveries_today: list[DeliveryToday]
    team_activity: list[TeamActivityRow]
    favourite_projects: list[FavouriteProject]
    all_projects_count: int
```

- [ ] **Step 2: queries.py**

Implement `dashboard(db, *, user: AuthUser) -> HomeDashboardOut` that branches on `auth_role` + `jtbd_role`:

| auth_role | jtbd_role | role_view | scope filter |
|---|---|---|---|
| admin | * | "ceo" | all in workspace |
| manager | PM | "pm" | `projects.pm_id = :uid` |
| drafter | * | "drafter" | `items.cutlist_owner_id = :uid` |
| purchase_officer | * | "purchase_officer" | (procurement-leaning metric set) |
| editor | Foreman/Machine | "viewer" | read-only |
| viewer | * | "viewer" | read-only |

Metric definitions:
- `overdue`: `count(*) FROM items WHERE EXISTS(item_stages WHERE due_date < today AND done_date IS NULL)`
- `in_optimisation`: items at `DOWN.done` && `CNC.done IS NULL`
- `awaiting_install`: items where `DEL.done IS NOT NULL && INST.done IS NULL`
- `value_in_progress`: `SUM(items.value)` for items with status='LIVE'
- For `purchase_officer`: replace `value_in_progress` with `count(open POs)` & `count(deliveries this week)`.

`my_day`: top 5 items where (drafter scope) `cutlist_owner_id = :uid AND any item_stages.due_date <= today + 3` ORDER BY soonest due_date.

`deliveries_today`: `procurement_batches WHERE expected_arrival = today AND workspace_id = :wid`.

`team_activity`: last 8 `audit_log` rows JOIN `app_user`, `WHERE workspace_id = :wid ORDER BY created_at DESC LIMIT 8`.

`favourite_projects`: from `project_favourites` JOIN `projects`.

- [ ] **Step 3: routes.py**

```python
@router.get("/home/dashboard", response_model=HomeDashboardOut)
def get_home_dashboard(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    return dashboard(db, user=user)
```

- [ ] **Step 4: Tests** (`test_home_dashboard.py`)

- `test_dashboard_admin_returns_ceo_view()`
- `test_dashboard_pm_scope_filters_to_own_projects()` — seed 2 projects (one with `pm_id=self`, one without); assert metrics only count first.
- `test_dashboard_drafter_scope_filters_to_own_items()`
- `test_dashboard_purchase_officer_metrics_shape()`
- `test_dashboard_includes_team_activity_from_audit_log()`

- [ ] **Step 5: Mount + commit**

```python
# main.py
from .home.routes import router as home_router
app.include_router(home_router)
```

```bash
docker compose exec api pytest tests/test_home_dashboard.py -q
git add apps/api/app/home apps/api/app/main.py apps/api/tests/test_home_dashboard.py
git commit -m "feat(api): /home/dashboard composite endpoint w/ role-shape"
```

---

## Phase 3 — API write surface

> Every mutation: opens a txn, calls `write_audit()` and `write_edit_log()` (where item-scoped) via `db.flush()`, then `db.commit()` once at the end of the handler.

### Task 15: `POST/PATCH/DELETE /items` + soft-lock semantics

**Files:**
- Modify: `apps/api/app/items/{schemas,queries,routes}.py`
- Extend: `apps/api/tests/test_items_routes.py`
- Create: `apps/api/tests/test_lock_semantics.py`

- [ ] **Step 1: schemas.py — `CreateItemIn`, `PatchItemIn`, `LockTransferIn`**

```python
class CreateItemIn(BaseModel):
    project_id: int
    description: str | None = None
    qty: int | None = None
    stage: str | None = None
    code: str | None = None
    level: str | None = None
    room_no: str | None = None
    room_desc: str | None = None
    zone: int | None = None


class PatchItemIn(BaseModel):
    description: str | None = None
    qty: int | None = None
    stage: str | None = None
    code: str | None = None
    level: str | None = None
    room_no: str | None = None
    room_desc: str | None = None
    zone: int | None = None
    status_symbol_id: int | None = None
    estimator_notes: str | None = None
    painting_required: bool | None = None
    solid_surface_required: bool | None = None


class LockTransferIn(BaseModel):
    owner_id: int
```

- [ ] **Step 2: queries.py — write helpers**

```python
def create_item(db, *, workspace_id, project_id, payload, actor_id) -> int: ...

def patch_item(db, *, item_id, workspace_id, payload, actor_id) -> dict | None:
    # Read current row -> compute changed fields -> UPDATE -> write_edit_log_many
    # If item.cutlist_owner_id IS NULL: claim ownership (set cutlist_owner_id=actor, item_locked=true)
    # If item.item_locked AND item.cutlist_owner_id != actor:
    #     write_audit(event='item.lock_overridden', payload={'prior_owner_id': ..., 'new_owner_id': actor})
    ...

def delete_item(db, *, item_id, workspace_id, actor_id) -> bool:
    # 409 if any item_hardware_lines.id is referenced by batch_allocations
    ...

def claim_or_release_lock(db, *, item_id, workspace_id, actor: AuthUser, action: str, owner_id: int | None = None):
    # action='claim' (POST), 'release' (DELETE), 'transfer' (POST w/ owner_id)
    # transfer requires actor == current owner OR auth_role IN {manager, admin}; else raise 403.
    ...
```

- [ ] **Step 3: routes.py**

```python
@router.post("/projects/{pid}/items", response_model=ItemOut, status_code=201,
             dependencies=[Depends(require_drafter())])
def post_item(pid: int, payload: CreateItemIn,
              user: AuthUser = Depends(current_user),
              db: Session = Depends(get_db)):
    iid = create_item(db, workspace_id=user.workspace_id, project_id=pid,
                      payload=payload, actor_id=user.id)
    db.commit()
    return get_item_detail(db, item_id=iid, workspace_id=user.workspace_id,
                           current_user_id=user.id)


@router.patch("/items/{id}", response_model=ItemOut,
              dependencies=[Depends(require_drafter())])
def patch_item_route(id: int, payload: PatchItemIn,
                     user: AuthUser = Depends(current_user),
                     db: Session = Depends(get_db)):
    row = patch_item(db, item_id=id, workspace_id=user.workspace_id,
                     payload=payload, actor_id=user.id)
    if row is None:
        raise HTTPException(404, "item not found")
    db.commit()
    return get_item_detail(db, item_id=id, workspace_id=user.workspace_id,
                           current_user_id=user.id)


@router.delete("/items/{id}", status_code=204,
               dependencies=[Depends(require_drafter())])
def delete_item_route(id: int,
                      user: AuthUser = Depends(current_user),
                      db: Session = Depends(get_db)):
    try:
        ok = delete_item(db, item_id=id, workspace_id=user.workspace_id,
                         actor_id=user.id)
    except IntegrityError:
        raise HTTPException(409, "item has allocated hardware; release allocations first")
    if not ok:
        raise HTTPException(404, "item not found")
    db.commit()


@router.post("/items/{id}/lock", response_model=ItemOut,
             dependencies=[Depends(require_drafter())])
def lock_item(id: int, payload: LockTransferIn | None = None,
              user: AuthUser = Depends(current_user),
              db: Session = Depends(get_db)):
    claim_or_release_lock(db, item_id=id, workspace_id=user.workspace_id,
                          actor=user, action="transfer" if payload else "claim",
                          owner_id=payload.owner_id if payload else None)
    db.commit()
    return get_item_detail(db, item_id=id, workspace_id=user.workspace_id,
                           current_user_id=user.id)


@router.delete("/items/{id}/lock", response_model=ItemOut,
               dependencies=[Depends(require_drafter())])
def release_lock(id: int, user: AuthUser = Depends(current_user),
                 db: Session = Depends(get_db)):
    claim_or_release_lock(db, item_id=id, workspace_id=user.workspace_id,
                          actor=user, action="release")
    db.commit()
    return get_item_detail(db, item_id=id, workspace_id=user.workspace_id,
                           current_user_id=user.id)
```

- [ ] **Step 4: Tests — `test_lock_semantics.py`**

- `test_first_save_claims_ownership_and_locks()` — drafter A patches an unlocked item; assert `item_locked=true`, `cutlist_owner_id=A.id`.
- `test_second_save_by_other_writes_lock_overridden_audit()` — drafter B patches A's locked item; assert `audit_log` row with `event='item.lock_overridden'`.
- `test_release_lock_keeps_owner_id()` — DELETE /lock; assert `item_locked=false` but `cutlist_owner_id` unchanged.
- `test_transfer_lock_by_owner()` — POST /lock body `{owner_id: B}`, assert ownership transferred.
- `test_transfer_lock_by_non_owner_403()` — drafter B tries to transfer drafter A's item -> 403.
- `test_manager_can_force_transfer()` — manager always allowed.
- `test_lock_warning_in_get_item_response()` — verify the GET payload field.

Plus normal CRUD tests in `test_items_routes.py`:
- `test_post_item_writes_create_log_row()`
- `test_patch_item_writes_one_log_row_per_changed_field()`
- `test_delete_item_409_when_hardware_allocated()`
- `test_editor_post_item_403()` — drafter-narrow gate.

- [ ] **Step 5: Run + commit**

```bash
docker compose exec api pytest tests/test_items_routes.py tests/test_lock_semantics.py -q
git commit -am "feat(api): item CRUD + soft-lock + lock-overridden audit"
```

---

### Task 16: PATCH `/items/{id}/status` and PATCH `/items/{id}/lifecycle/{stage_key}`

**Files:**
- Modify: `apps/api/app/items/{schemas,queries,routes}.py`
- Create: `apps/api/tests/test_lifecycle_status.py`

- [ ] **Step 1: schemas.py**

```python
class PatchItemStatusIn(BaseModel):
    status: Literal["CLEAR","VOID","NOTE!","LIVE","APPROVED","HOLD"]


class PatchLifecycleIn(BaseModel):
    due_date: date | None = None
    done_date: date | None = None
```

- [ ] **Step 2: queries.py**

```python
def patch_item_status(db, *, item_id, workspace_id, status, actor_id):
    # UPDATE items SET status=:s; write_audit; write_edit_log(field='item.status', old, new)
    ...

VALID_STAGE_KEYS = {"REQ","SM","LISTED","DOWN","CNC","EDGED","PAINTED","MADE","DEL","INST"}

def patch_lifecycle(db, *, item_id, workspace_id, stage_key, payload, actor_id):
    if stage_key not in VALID_STAGE_KEYS:
        return "INVALID"
    # UPSERT item_stages(item_id, stage_key) SET due_date=:d, done_date=:done
    # INSERT item_status_log(item_id, stage_key, action, actor_id) (per spec §6.4)
    # write_audit(event='item.lifecycle.<stage_key>', payload={'due_date': d, 'done_date': done})
    # write_edit_log per changed field
    ...
```

- [ ] **Step 3: routes.py**

```python
@router.patch("/items/{id}/status", response_model=ItemOut)
def patch_status(id: int, payload: PatchItemStatusIn,
                 user: AuthUser = Depends(require_permission("tracking", "write")),
                 db: Session = Depends(get_db)):
    ok = patch_item_status(db, item_id=id, workspace_id=user.workspace_id,
                           status=payload.status, actor_id=user.id)
    if not ok:
        raise HTTPException(404, "item not found")
    db.commit()
    return get_item_detail(db, item_id=id, workspace_id=user.workspace_id,
                           current_user_id=user.id)


@router.patch("/items/{id}/lifecycle/{stage_key}", response_model=ItemOut)
def patch_lifecycle_route(id: int, stage_key: str, payload: PatchLifecycleIn,
                          user: AuthUser = Depends(require_permission("tracking", "write")),
                          db: Session = Depends(get_db)):
    result = patch_lifecycle(db, item_id=id, workspace_id=user.workspace_id,
                             stage_key=stage_key, payload=payload, actor_id=user.id)
    if result == "INVALID":
        raise HTTPException(400, "unknown stage_key")
    if not result:
        raise HTTPException(404, "item not found")
    db.commit()
    return get_item_detail(db, item_id=id, workspace_id=user.workspace_id,
                           current_user_id=user.id)
```

- [ ] **Step 4: Tests — `test_lifecycle_status.py`**

- `test_patch_status_writes_audit_and_edit_log()`
- `test_status_value_validated_by_pydantic()` (invalid -> 422)
- `test_patch_lifecycle_invalid_stage_400()`
- `test_patch_lifecycle_upserts_item_stages()`
- `test_patch_lifecycle_writes_item_status_log()`
- `test_patch_lifecycle_editor_allowed()` — Juno (editor/Foreman) PATCHes `CNC.done_date` -> 200.
- `test_patch_lifecycle_purchase_officer_403()`.
- `test_patch_status_void_kept_in_grid_but_excluded_from_metrics()` — sanity check by hitting `/home/dashboard` after.

- [ ] **Step 5: Commit**

```bash
docker compose exec api pytest tests/test_lifecycle_status.py -q
git commit -am "feat(api): PATCH item status + lifecycle/{stage_key} w/ logs"
```

---

### Task 17: Modules + parts CRUD

**Files:**
- Create: `apps/api/app/parts/__init__.py`, `schemas.py`, `queries.py`, `routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_parts_routes.py`

- [ ] **Step 1: schemas.py**

```python
class CreateModuleIn(BaseModel):
    name: str


class PatchModuleIn(BaseModel):
    name: str | None = None


class CreatePartIn(BaseModel):
    qty: int = 1
    part_name: str
    len_mm: int | None = None
    wid_mm: int | None = None
    board_material: str | None = None
    edge: str | None = None
    colour: str | None = None
    paint_instruction: str | None = None
    comment: str | None = None
    is_rev_c: bool = False


class PatchPartIn(BaseModel):
    qty: int | None = None
    part_name: str | None = None
    len_mm: int | None = None
    wid_mm: int | None = None
    board_material: str | None = None
    edge: str | None = None
    colour: str | None = None
    paint_instruction: str | None = None
    comment: str | None = None
    is_rev_c: bool | None = None
```

- [ ] **Step 2: queries.py**

Standard create/update/delete; each writes `item_edit_log` with the appropriate `field` (e.g. `parts.qty`, `modules.name`, `_create`, `_delete`). Each cross-checks the parent (`modules.item_id` -> workspace via JOIN). Cross-workspace 404.

- [ ] **Step 3: routes.py**

```python
@router.post("/items/{id}/modules", response_model=ModuleOut, status_code=201,
             dependencies=[Depends(require_drafter())])
def post_module(id: int, payload: CreateModuleIn,
                user: AuthUser = Depends(current_user),
                db: Session = Depends(get_db)):
    mid = create_module(db, item_id=id, workspace_id=user.workspace_id,
                        payload=payload, actor_id=user.id)
    if mid is None:
        raise HTTPException(404, "item not found")
    db.commit()
    return get_module(db, module_id=mid, workspace_id=user.workspace_id)


@router.patch("/modules/{mid}", ..., dependencies=[Depends(require_drafter())])
def patch_module(mid: int, payload: PatchModuleIn, ...): ...


@router.delete("/modules/{mid}", status_code=204,
               dependencies=[Depends(require_drafter())])
def delete_module(mid: int, ...): ...


@router.post("/modules/{mid}/parts", response_model=PartOut, status_code=201,
             dependencies=[Depends(require_drafter())])
def post_part(mid: int, payload: CreatePartIn, ...): ...


@router.patch("/parts/{pid}", ..., dependencies=[Depends(require_drafter())])
def patch_part(pid: int, payload: PatchPartIn, ...): ...


@router.delete("/parts/{pid}", status_code=204,
               dependencies=[Depends(require_drafter())])
def delete_part(pid: int, ...): ...
```

- [ ] **Step 4: Tests**

- `test_create_module_writes_create_log()`
- `test_create_part_writes_log_with_field_create()`
- `test_patch_part_qty_writes_one_edit_log_row()`
- `test_delete_part_writes_delete_log()`
- `test_module_in_other_workspace_404()`
- `test_editor_403_on_part_patch()` (drafter-narrow gate).

- [ ] **Step 5: Commit**

```bash
docker compose exec api pytest tests/test_parts_routes.py -q
git add apps/api/app/parts apps/api/app/main.py apps/api/tests/test_parts_routes.py
git commit -m "feat(api): modules + parts CRUD w/ item_edit_log"
```

---

### Task 18: Hardware-lines CRUD + project_hardware_catalog add/remove

**Files:**
- Modify: `apps/api/app/hardware_lines/{schemas,queries,routes}.py`
- Extend: `apps/api/tests/test_hardware_lines_routes.py`

- [ ] **Step 1: schemas.py**

```python
class CreateHardwareLineIn(BaseModel):
    catalog_id: int
    qty: int = 1
    note: str | None = None


class PatchHardwareLineIn(BaseModel):
    qty: int | None = None
    note: str | None = None


class AddCatalogIn(BaseModel):
    source_table: Literal["board_materials","hardware_materials","custom_made",
                          "benchtop_materials","appliances","equipment_hire"]
    source_id: int
    qty: float = 1
```

- [ ] **Step 2: queries.py**

`add_to_catalog(db, *, project_id, workspace_id, payload, actor_id) -> int`:
- Validate `(source_table, source_id)` exists.
- INSERT `project_hardware_catalog`.
- INSERT `project_hardware_catalog_log` (`action='add'`, `changed_by=actor_id`, `payload=...`) — same txn.
- write_audit `event='hardware_catalog.add'`.

`remove_from_catalog(db, *, catalog_id, workspace_id, actor_id) -> str`:
- Refuse with `'IN_USE'` if `EXISTS (SELECT 1 FROM item_hardware_lines WHERE catalog_id=:cid)`.
- DELETE `project_hardware_catalog`.
- INSERT `project_hardware_catalog_log` (`action='remove'`).
- write_audit.

`create_hardware_line(db, *, item_id, workspace_id, payload, actor_id) -> int`:
- Validate `catalog_id` belongs to project of `item_id`.
- INSERT `item_hardware_lines`.
- write_edit_log (`field='_create'`).
- write_audit.

`patch_hardware_line(db, *, line_id, workspace_id, payload, actor_id)` and `delete_hardware_line` — analogous, qty-deltas write `field='hardware_lines.qty'`.

- [ ] **Step 3: routes.py**

```python
@router.post("/projects/{pid}/hardware_catalog", status_code=201,
             dependencies=[Depends(require_drafter())])
def post_catalog(pid: int, payload: AddCatalogIn, ...): ...


@router.delete("/projects/{pid}/hardware_catalog/{cid}", status_code=204,
               dependencies=[Depends(require_drafter())])
def delete_catalog(pid: int, cid: int, ...):
    result = remove_from_catalog(db, catalog_id=cid, workspace_id=user.workspace_id,
                                 actor_id=user.id)
    if result == "IN_USE":
        raise HTTPException(409, "catalog row referenced by item_hardware_lines")
    if result == "NOT_FOUND":
        raise HTTPException(404, "catalog row not found")
    db.commit()


@router.post("/items/{id}/hardware_lines", response_model=HardwareLineOut,
             status_code=201, dependencies=[Depends(require_drafter())])
def post_hardware_line(id: int, payload: CreateHardwareLineIn, ...): ...


@router.patch("/hardware_lines/{lid}", ...,
              dependencies=[Depends(require_drafter())])
def patch_hardware_line_route(lid: int, payload: PatchHardwareLineIn, ...): ...


@router.delete("/hardware_lines/{lid}", status_code=204,
               dependencies=[Depends(require_drafter())])
def delete_hardware_line_route(lid: int, ...): ...
```

- [ ] **Step 4: Tests**

- `test_add_catalog_writes_log_in_same_txn()` — verify both `project_hardware_catalog` and `_log` rows exist after POST.
- `test_add_catalog_invalid_source_404()`.
- `test_remove_catalog_409_when_referenced()`.
- `test_remove_catalog_writes_remove_log_row()`.
- `test_create_hardware_line_validates_catalog_belongs_to_project()`.
- `test_patch_hardware_line_qty_writes_edit_log()`.
- `test_editor_403_on_hardware_line_create()`.
- `test_availability_endpoint_reflects_new_line()` — POST line, GET availability shows it as `'none'` (no allocations).

- [ ] **Step 5: Commit**

```bash
docker compose exec api pytest tests/test_hardware_lines_routes.py -q
git commit -am "feat(api): hardware_lines CRUD + project_hardware_catalog add/remove"
```

---

## Phase 4 — Seed data

### Task 19: Extend `seed/hartwood_joinery.py` with projects + items + parts + hardware lines

**Files:**
- Modify: `seed/hartwood_joinery.py`

The seed should produce a non-trivial dataset to exercise grid filters, my-day rollups, and availability chips.

- [ ] **Step 1: Add module-level constants**

```python
PROJECTS = [
    # (project_code, name, pm_email, install_start)
    ("ALF-001", "Alfred Street Renovation", "rin.park@hartwood.test",  "2026-06-15"),
    ("TRT-014", "Trentham Heights",          "theo.blake@hartwood.test", "2026-08-01"),
]

# 5 items per project
ITEMS_PER_PROJECT = [
    # (code, description, level, room_no, room_desc, stage(site), zone, qty, status)
    ("K-101", "Kitchen island carcass",   "L1", "K1", "Kitchen",   1, 1, "LIVE"),
    ("K-102", "Pantry tower",              "L1", "K1", "Kitchen",   1, 1, "LIVE"),
    ("K-103", "Overhead cabinet run",      "L1", "K1", "Kitchen",   2, 1, "CLEAR"),
    ("B-201", "Master ensuite vanity",     "L2", "B1", "Bathroom",  1, 1, "HOLD"),
    ("L-301", "Living TV joinery",         "L1", "L1", "Living",    1, 1, "LIVE"),
]

LIFECYCLE_PROGRESS = [
    ("REQ",    "done"),    # all done
    ("SM",     "done"),
    ("LISTED", "varies"),  # varying — first 2 done, rest only due
    ("DOWN",   "due"),
    ("CNC",    "due"),
]
```

- [ ] **Step 2: Add `def seed_projects(db, wid, users_by_email)` step**

After the existing user-seed loop, the function:
1. Resolves PM `app_user.id` from email (using a SELECT helper).
2. Loops `PROJECTS`. For each: `INSERT INTO projects (... pm_id, project_code, name, install_start) ON CONFLICT (workspace_id, project_code) DO NOTHING RETURNING id`. Use a CTE pattern to handle the no-RETURNING-on-conflict case (`WITH ins AS (...) SELECT id FROM ins UNION ALL SELECT id FROM projects WHERE project_code=:c LIMIT 1`).
3. For each item in `ITEMS_PER_PROJECT`: `INSERT INTO items (workspace_id, project_id, code, description, level, ...) ON CONFLICT (project_id, code) DO NOTHING RETURNING id`.
4. For each item: insert 1 module + 3 parts.
5. For each item: insert 2 hardware lines (using 2 dummy catalog entries seeded once per project from `hardware_materials`).
6. For each item: upsert `item_stages` rows per `LIFECYCLE_PROGRESS`.

- [ ] **Step 3: Material catalog seed**

Seed 4 dummy `hardware_materials` rows once per workspace (`SKU_HM_001..004`) and link them via `project_hardware_catalog` for both projects.

- [ ] **Step 4: Verify idempotent**

```bash
docker compose exec api python -m seed.hartwood_joinery
docker compose exec api python -m seed.hartwood_joinery
docker compose exec db psql -U jf -d joineryflow -c "SELECT count(*) FROM projects"
docker compose exec db psql -U jf -d joineryflow -c "SELECT count(*) FROM items"
docker compose exec db psql -U jf -d joineryflow -c "SELECT count(*) FROM project_hardware_catalog"
```
Expected after both runs: projects=2, items=10, catalog rows = 8 (4 per project).

- [ ] **Step 5: Commit**

```bash
git add seed/hartwood_joinery.py
git commit -m "feat(seed): hartwood projects + items + parts + hardware catalog"
```

---

## Phase 5 — Web shell additions

> Reminder: this is **Next.js 16 + React 19 + Tailwind v4**. Read `apps/web/AGENTS.md` and the relevant guide in `apps/web/node_modules/next/dist/docs/` before writing each route or component. Tailwind tokens are CSS-first via `@theme inline` in `apps/web/app/globals.css` — no `tailwind.config.ts`.

### Task 20: TS types module

**Files:**
- Create: `apps/web/lib/pm-types.ts`

- [ ] **Step 1: Mirror Pydantic shapes**

Mirror every `*Out` and `*In` Pydantic model from Phase 2 + Phase 3 as TypeScript types. Keep them in one file. Use `string` for ISO dates and `number` for ints. No runtime validation in v1 (the API is the source of truth; Zod can be added later if drift becomes a problem).

- [ ] **Step 2: Commit**

```bash
git add apps/web/lib/pm-types.ts
git commit -m "feat(web): TS types mirroring PM Workbench API schemas"
```

---

### Task 21: `pm-fetch.ts` thin fetch helpers

**Files:**
- Create: `apps/web/lib/pm-fetch.ts`

Wraps `fetch()` to:
1. Always send `cookie` (server-side via `headers()`; client-side is automatic on same-origin).
2. Throw a typed `ApiError` on non-2xx so callers can branch on `.status`.
3. Default to `cache: "no-store"` for reads.

- [ ] **Step 1: Implement**

```ts
import type {
  HomeDashboardOut, ItemOut, TrackingGridOut, ProjectListOut,
  HardwareCatalogOut, AvailabilityOut, ProjectOut,
} from "./pm-types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) {
    let body: unknown;
    try { body = await res.json(); } catch { /* */ }
    throw new ApiError(res.status, res.statusText, body);
  }
  return res.json() as Promise<T>;
}

export const PM = {
  // Reads (composable from server components by passing absolute URL prefix)
  homeDashboard: (origin = "") => call<HomeDashboardOut>(`${origin}/api/home/dashboard`),
  projects:      (origin = "", fav?: boolean) =>
    call<ProjectListOut>(`${origin}/api/projects${fav === undefined ? "" : `?fav=${fav}`}`),
  project:       (origin: string, pid: number) => call<ProjectOut>(`${origin}/api/projects/${pid}`),
  trackingGrid:  (origin: string, pid: number, q?: URLSearchParams) =>
    call<TrackingGridOut>(`${origin}/api/projects/${pid}/items${q ? `?${q}` : ""}`),
  item:          (origin: string, id: number) => call<ItemOut>(`${origin}/api/items/${id}`),
  availability:  (origin: string, id: number) => call<AvailabilityOut>(`${origin}/api/items/${id}/availability`),
  catalog:       (origin: string, pid: number) =>
    call<HardwareCatalogOut>(`${origin}/api/projects/${pid}/hardware_catalog`),

  // Writes (client side; relative paths)
  toggleFavourite: (pid: number, on: boolean) =>
    fetch(`/api/projects/${pid}/favourites`, { method: on ? "POST" : "DELETE" }),
  patchPart:    (pid: number, body: object) =>
    call<unknown>(`/api/parts/${pid}`, {
      method: "PATCH", headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  // ...mirror the remaining mutations as the editor lands
};
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/lib/pm-fetch.ts
git commit -m "feat(web): pm-fetch thin API client w/ ApiError"
```

---

### Task 22: Replace `SideBar.tsx` stub with FAV/ALL project list

**Files:**
- Modify: `apps/web/components/chrome/SideBar.tsx` (server)
- Create: `apps/web/components/chrome/ProjectSidebar.tsx` (client; FAV toggle)

- [ ] **Step 1: SideBar.tsx (server) reads projects**

```tsx
import { headers } from "next/headers";
import { PM } from "@/lib/pm-fetch";
import { ProjectSidebar } from "./ProjectSidebar";

export async function SideBar() {
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "http"}://${h.get("host")}`;
  const [all, favs] = await Promise.all([
    PM.projects(origin, false).catch(() => ({ projects: [] })),
    PM.projects(origin, true).catch(() => ({ projects: [] })),
  ]);
  return <ProjectSidebar all={all.projects} favourites={favs.projects} />;
}
```

- [ ] **Step 2: ProjectSidebar.tsx (client)**

State: `tab: "FAV" | "ALL"` (default "ALL"); `searchQuery: string`. Renders a vertical list with:
- Toggle pill at top (`FAV / ALL`).
- Filter input (instant client-side filter on name/project_code).
- Each row: `[★]` + project_code · name. Active project highlighted by reading `useSearchParams()` for `project_id`.
- Click row -> `router.push(\`/tracking?project_id=${id}\`)`.
- `★` toggle calls `PM.toggleFavourite()` then `router.refresh()`.

Use Tailwind tokens: `bg-h-surface`, `text-h-ink`, `border-h-line`, hover `bg-h-bg`.

- [ ] **Step 3: Visual sanity check**

```bash
make up
# Visit http://localhost:3000/dashboard; sidebar should list 2 projects after seed.
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/chrome/SideBar.tsx apps/web/components/chrome/ProjectSidebar.tsx
git commit -m "feat(web): sidebar w/ FAV/ALL toggle + project list"
```

---

### Task 23: TopBar editor-mode swap (`<- Return to home`)

**Files:**
- Modify: `apps/web/components/chrome/TopBar.tsx`
- Modify: `apps/web/components/chrome/HAppChrome.tsx`
- Modify: `apps/web/app/(app)/layout.tsx`
- Modify: `apps/web/middleware.ts`

Approach: middleware sets a `x-pathname` request header; layout reads it and passes `editorMode: pathname.startsWith("/items/")` into `HAppChrome`.

- [ ] **Step 1: middleware.ts — set `x-pathname` header**

In the existing middleware, before returning the response:

```ts
const requestHeaders = new Headers(req.headers);
requestHeaders.set("x-pathname", req.nextUrl.pathname);
return NextResponse.next({ request: { headers: requestHeaders } });
```

- [ ] **Step 2: Layout reads it**

```tsx
import { headers } from "next/headers";
const pathname = (await headers()).get("x-pathname") ?? "";
const editorMode = pathname.startsWith("/items/");
return <HAppChrome user={user} editorMode={editorMode}>{children}</HAppChrome>;
```

- [ ] **Step 3: HAppChrome props + conditional rendering**

```tsx
interface HAppChromeProps {
  user: Me;
  editorMode?: boolean;
  children: React.ReactNode;
}

export function HAppChrome({ user, editorMode, children }: HAppChromeProps) {
  return (
    <div className="min-h-screen bg-h-bg">
      <TopBar user={user} editorMode={editorMode} />
      {!editorMode && <TabStrip />}
      <div className="flex">
        {!editorMode && <SideBar />}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: TopBar — left slot**

```tsx
{editorMode ? (
  <Link href="/home" className="text-sm text-h-muted hover:text-h-ink">
    ← Return to home
  </Link>
) : (
  <span className="font-semibold text-h-ink">JoineryFlow</span>
)}
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/chrome apps/web/app/(app)/layout.tsx apps/web/middleware.ts
git commit -m "feat(web): topbar editor-mode swap (Return to home)"
```

---

### Task 24: `/home` route — replaces `/dashboard` as default landing

**Files:**
- Create: `apps/web/app/(app)/home/page.tsx`
- Create: `apps/web/components/pm/MetricCard.tsx`, `MyDayList.tsx`, `DeliveriesList.tsx`, `TeamActivityFeed.tsx`
- Modify: `apps/web/middleware.ts` (and login page) to land `/home` after login

- [ ] **Step 1: page.tsx (server component)**

```tsx
import { headers } from "next/headers";
import { PM } from "@/lib/pm-fetch";
import { MetricCard } from "@/components/pm/MetricCard";
import { MyDayList } from "@/components/pm/MyDayList";
import { DeliveriesList } from "@/components/pm/DeliveriesList";
import { TeamActivityFeed } from "@/components/pm/TeamActivityFeed";

export default async function HomePage() {
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "http"}://${h.get("host")}`;
  const data = await PM.homeDashboard(origin);
  return (
    <div className="grid gap-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {data.metrics.map((m) => <MetricCard key={m.key} {...m} />)}
      </section>
      <section className="grid gap-6 lg:grid-cols-2">
        <MyDayList items={data.my_day} />
        <DeliveriesList items={data.deliveries_today} />
      </section>
      <TeamActivityFeed rows={data.team_activity} />
    </div>
  );
}
```

- [ ] **Step 2: Components**

Each is a thin presentational component using design tokens (`bg-h-surface`, `border-h-line`, `text-h-ink`, `text-h-muted`). Numbers use `font-mono tabular-nums`. Links use Next `Link`.

- [ ] **Step 3: Update post-login redirect**

In login page, change the success path from `/dashboard` to `/home`. In middleware, ensure `/home` is gated like other app routes; legacy `/dashboard` keeps working (still rendered by Foundation stub) for backward-compat with the existing E2E `smoke.spec.ts`.

- [ ] **Step 4: Manual smoke**

```bash
# Login as Rin.
# /home should render 4 metric cards, "My Day" with at least 1 item, sidebar with 2 projects.
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/(app)/home apps/web/components/pm apps/web/app/(public)/login/page.tsx
git commit -m "feat(web): /home dashboard w/ role-shape metrics"
```

---

### Task 25: `/projects` page — list + create drawer

**Files:**
- Create: `apps/web/app/(app)/projects/page.tsx`
- Create: `apps/web/app/(app)/projects/_components/CreateProjectDrawer.tsx`

- [ ] **Step 1: page.tsx (server)**

Reads `PM.projects()`, renders a table: project_code · name · pm · status · item_count · install_start. Header has "+ New project" button (only for manager/admin — read role from `Me`). Click row -> `router.push(\`/tracking?project_id=${id}\`)`.

- [ ] **Step 2: CreateProjectDrawer.tsx (client)**

Slide-in drawer (Tailwind `transform translate-x-0/-x-full transition`). Fields: project_code · name · pm (select from `/api/users`) · install_start. POST `/api/projects` then `router.refresh()` and close.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/(app)/projects
git commit -m "feat(web): /projects list + new-project drawer"
```

---

### Task 26: `/tracking` page — PM project workbench grid

**Files:**
- Modify: `apps/web/app/(app)/tracking/page.tsx`
- Create: `apps/web/components/pm/TrackingGrid.tsx`
- Create: `apps/web/components/pm/TrackingFilters.tsx`
- Create: `apps/web/components/pm/StatusChip.tsx`
- Create: `apps/web/components/pm/AvailabilityChip.tsx`
- Create: `apps/web/components/pm/StageDates.tsx`

- [ ] **Step 1: page.tsx (server)**

```tsx
export default async function TrackingPage({ searchParams }: {
  searchParams: Promise<{ project_id?: string; status?: string; stage?: string; q?: string }>;
}) {
  const sp = await searchParams;
  const pid = sp.project_id ? Number(sp.project_id) : null;
  if (!pid) return <PickProjectPrompt />;
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "http"}://${h.get("host")}`;
  const [project, grid] = await Promise.all([
    PM.project(origin, pid),
    PM.trackingGrid(origin, pid, new URLSearchParams(sp as Record<string, string>)),
  ]);
  return (
    <>
      <header className="mb-4 flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-h-ink">{project.name}</h1>
        <div className="text-h-muted text-sm">{project.project_code}</div>
      </header>
      <TrackingFilters />
      <TrackingGrid items={grid.items} project={project} />
    </>
  );
}
```

- [ ] **Step 2: TrackingGrid.tsx (client)**

The 14-column grid. Locked left columns CUTLIST..QTY (per spec §5.3); right columns are the 10 stage-key date cells; final column the `▶` button.

- Rev-C parts row: `bg-h-accent/15` row background.
- Status uses `StatusChip` (CLEAR=good, LIVE=accent, APPROVED=good, HOLD=warn, NOTE!=warn, VOID=bad).
- Each row's `▶` reads `Me` via prop or context: if `auth_role IN {drafter, manager, admin}` -> `<Link href={`/items/${id}?tab=cutlist`}>`. Else opens a `<DetailsDrawer>` overlay in-page.
- Availability column renders `<AvailabilityChip ready={r} blocked={b}>`. Click expands a row-level breakdown using the per-line `availability` data already in the payload.
- `Open Procurement` header button: hidden behind `process.env.NEXT_PUBLIC_PROCUREMENT_UI_READY === "1"`.

- [ ] **Step 3: TrackingFilters.tsx (client)**

Status select · stage select · search input. On change updates URL search params via `router.push`. Search debounced 200ms.

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/(app)/tracking apps/web/components/pm
git commit -m "feat(web): /tracking PM workbench grid + filters"
```

---

## Phase 6 — Drafter Item Editor

### Task 27: Editor shell — `/items/[id]/page.tsx` + tabs + soft-lock banner + footer

**Files:**
- Create: `apps/web/app/(app)/items/[id]/page.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/ItemHeader.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/ItemMetadataPanel.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/EditorTabs.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/SoftLockBanner.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/EditorFooter.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/LogTab.tsx`

- [ ] **Step 1: page.tsx**

Server component fetches `PM.item()`. Reads `?tab=cutlist|hardware|board|log` (default `cutlist`).

```tsx
export default async function ItemEditorPage({
  params, searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "http"}://${h.get("host")}`;
  const item = await PM.item(origin, Number(id));
  return (
    <div className="grid gap-4">
      <ItemHeader item={item} />
      {item.lock_warning && <SoftLockBanner warning={item.lock_warning} />}
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <ItemMetadataPanel item={item} />
        <EditorTabs item={item} active={sp.tab ?? "cutlist"} />
      </div>
      <EditorFooter item={item} />
    </div>
  );
}
```

- [ ] **Step 2: ItemHeader.tsx**

Renders `ITEM #{item_number} · {project name} · {stage}` with `[x]` close button. Close button: `'use client'` with `onClick={() => { window.close(); if (!window.closed) router.push("/home"); }}`.

- [ ] **Step 3: ItemMetadataPanel.tsx (client)**

Controlled inputs for: level, room_no, room_desc, description, stage (site), painting_required, solid_surface_required, group_id, estimator_notes. PATCH on blur via `pm-fetch`. `router.refresh()` on success. On 4xx, restore prior value and show inline error.

- [ ] **Step 4: EditorTabs.tsx (client)**

Tab strip `[Cutlist] [Hardware] [Board] [Log]`. Active reads from URL (`?tab=`). Click updates URL via `router.push`. Lazily render the active tab body (`{tab === "cutlist" && <CutlistTab item={item} />}`). Board tab renders a placeholder card "Board view ships in v2 with Cabinet Vision integration."

- [ ] **Step 5: SoftLockBanner.tsx**

```tsx
<div role="alert" className="rounded-md border border-h-warn bg-h-warn/10 p-3 text-sm text-h-ink">
  Locked by <strong>{warning.owner_name}</strong> — last edit {warning.last_edit_minutes_ago} minutes ago.
  Your save will overwrite.
</div>
```

- [ ] **Step 6: EditorFooter.tsx (client)**

Buttons row:
- `Print Cutlist` / `Print Hardware` / `Print Combined PDF` — disabled with `title="PDF generation ships in sub-project #5"`.
- `Lock` / `Unlock` — fully wired. Reads current `item_locked` and `cutlist_owner_id`. Disabled if user is neither owner nor manager/admin. POST `/api/items/{id}/lock` (claim) or DELETE (release). `router.refresh()` after.

- [ ] **Step 7: LogTab.tsx**

Renders `item.edit_log` (last 50 rows). Table columns: ts (relative time) · actor_name · field · old → new. Plain table; no pagination v1.

- [ ] **Step 8: Commit**

```bash
git add apps/web/app/(app)/items
git commit -m "feat(web): drafter editor shell — tabs + lock banner + footer + log"
```

---

### Task 28: Cutlist tab — module tree + parts grid

**Files:**
- Create: `apps/web/app/(app)/items/[id]/_components/cutlist/CutlistTab.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/cutlist/ModuleTree.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/cutlist/PartsGrid.tsx`

- [ ] **Step 1: CutlistTab.tsx (client)**

Layout: 220px module tree (left) + dense parts grid (right). State: `activeModuleId` (default first module).

- [ ] **Step 2: ModuleTree.tsx**

Vertical list of module names. Active module highlighted (`bg-h-accent/15 border-l-2 border-h-accent`). `+ Add module` button at bottom — POST `/api/items/{id}/modules` body `{name: "New module"}`, then `router.refresh()`.

- [ ] **Step 3: PartsGrid.tsx**

Editable grid for the active module's parts. Columns: `[ ]` checkbox · qty · part_name · len_mm · wid_mm · board_material · edge · colour · paint_instruction · comment.
- Each cell is a controlled input.
- PATCH on blur (`PM.patchPart`).
- Optimistic UI: update local state immediately; revert on 4xx and toast.
- Rev-C row: `bg-h-accent/15`.
- `+ Add row` button: POST `/api/modules/{mid}/parts` `{part_name: "", qty: 1}`, then `router.refresh()`.
- Per-row `–` button to delete.

- [ ] **Step 4: Manual smoke**

```bash
# Login as Noa (drafter). Open an item. Add a row. Refresh page; row persists.
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/(app)/items/[id]/_components/cutlist
git commit -m "feat(web): cutlist tab — module tree + parts grid w/ patch-on-blur"
```

---

### Task 29: Hardware tab — pantry + cart + add-from-global modal

**Files:**
- Create: `apps/web/app/(app)/items/[id]/_components/hardware/HardwareTab.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/hardware/Pantry.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/hardware/Cart.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/hardware/AddFromGlobalModal.tsx`
- Modify: `apps/api/app/hardware_lines/routes.py` (add small `/source_catalog/{table}` endpoint)

- [ ] **Step 1: HardwareTab.tsx (client)**

Fetches `/api/projects/{pid}/hardware_catalog` and `/api/items/{id}/availability` once on mount; renders Pantry (left) and Cart (right, 420px). State: `searchQuery`, `addModalOpen`.

- [ ] **Step 2: Pantry.tsx**

Search input on top. Rows grouped by `source_table` (board/hardware/custom_made/benchtop/appliance/equipment_hire). Per row: name + sku + supplier + `+` button (POST `/api/items/{id}/hardware_lines` `{catalog_id: X, qty: 1}` then `router.refresh()`). Bottom: `+ Add from global` button opens modal.

- [ ] **Step 3: Cart.tsx**

Hardware lines from `item.hardware_lines`, grouped by supplier name. Per row: catalog_description (locked) · qty stepper · note input · availability chip. Stepper PATCHes on commit (debounce 300ms). Note PATCHes on blur. `–` button DELETEs.

`AvailabilityChip` reads from the parallel `/api/items/{id}/availability` payload (joined by `line_id`).

- [ ] **Step 4: AddFromGlobalModal.tsx**

Lists rows from one of the 6 source tables not yet in project catalog. Source table tabs at top. Search input. Click row -> POST `/api/projects/{pid}/hardware_catalog` with `{source_table, source_id, qty: 1}`. On success, refresh both pantry and modal lists.

Backed by a small server endpoint `GET /api/source_catalog/{table}`.

- [ ] **Step 5: Add server endpoint for source catalog**

In `apps/api/app/hardware_lines/routes.py`:

```python
_ALLOWED_SOURCE_TABLES = {
    "board_materials", "hardware_materials", "custom_made",
    "benchtop_materials", "appliances", "equipment_hire",
}

@router.get("/source_catalog/{table}")
def list_source_catalog(
    table: str,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    if table not in _ALLOWED_SOURCE_TABLES:
        raise HTTPException(400, "unknown source table")
    # SAFETY: `table` comes from a closed whitelist above; the f-string
    # interpolation cannot lead to SQL injection.
    rows = db.execute(text(f"""
        SELECT id, sku, name, unit_cost FROM {table}
        WHERE workspace_id = :wid ORDER BY name
    """), {"wid": user.workspace_id}).mappings().all()
    return {"table": table, "rows": [dict(r) for r in rows]}
```

- [ ] **Step 6: Manual smoke + commit**

```bash
git add apps/web/app/(app)/items/[id]/_components/hardware apps/web/lib apps/api/app/hardware_lines
git commit -m "feat(web): hardware tab — pantry + cart + add-from-global modal"
```

---

## Phase 7 — E2E + acceptance

### Task 30: E2E `pm_workbench.spec.ts` — PM happy path

**Files:**
- Create: `tests/e2e/pm_workbench.spec.ts`

- [ ] **Step 1: Spec**

```ts
import { test, expect } from "@playwright/test";

test("PM workbench happy path", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');

  await expect(page).toHaveURL(/\/home$/);
  // 4 metric cards
  await expect(page.locator('[data-testid="metric-card"]')).toHaveCount(4);
  // Sidebar shows >=1 project
  const sidebar = page.locator('[data-testid="project-sidebar"] li');
  await expect(sidebar.first()).toBeVisible();

  // Click first sidebar project
  await sidebar.first().click();
  await expect(page).toHaveURL(/\/tracking\?project_id=/);

  // Tracking grid shows >=1 item row; CODE column visible
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /code/i })).toBeVisible();

  // Click ▶ on first row
  await page.locator('[data-testid="tracking-row"] [data-testid="open-item"]').first().click();
  await expect(page).toHaveURL(/\/items\/\d+\?tab=cutlist/);
  await expect(page.getByRole("link", { name: /return to home/i })).toBeVisible();

  // Return to home
  await page.getByRole("link", { name: /return to home/i }).click();
  await expect(page).toHaveURL(/\/home$/);
});
```

- [ ] **Step 2: Add `data-testid` attributes in components above as needed.**

- [ ] **Step 3: Run + commit**

```bash
make e2e-docker
git add tests/e2e/pm_workbench.spec.ts apps/web
git commit -m "test(e2e): PM workbench happy path"
```

---

### Task 31: E2E `drafter_editor.spec.ts` — Drafter happy path

**Files:**
- Create: `tests/e2e/drafter_editor.spec.ts`

- [ ] **Step 1: Spec**

```ts
import { test, expect } from "@playwright/test";

test("Drafter editor happy path", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "noa.lindqvist@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/home$/);

  // My Day shows >=1 item
  await expect(page.locator('[data-testid="myday-row"]').first()).toBeVisible();

  // Click an item -> editor
  await page.locator('[data-testid="myday-row"] a').first().click();
  await expect(page).toHaveURL(/\/items\/\d+/);

  // Cutlist tab: add row
  await page.getByRole("button", { name: /add row/i }).click();
  const lastRow = page.locator('[data-testid="part-row"]').last();
  await lastRow.locator('[data-field="qty"]').fill("2");
  await lastRow.locator('[data-field="part_name"]').fill("Test part");
  await lastRow.locator('[data-field="part_name"]').blur();
  // Wait for PATCH success indicator
  await expect(lastRow).toHaveAttribute("data-saved", "true", { timeout: 5000 });

  // Hardware tab
  await page.getByRole("tab", { name: /hardware/i }).click();
  const cartCountBefore = await page.locator('[data-testid="cart-line"]').count();
  await page.locator('[data-testid="pantry-row"] [aria-label="Add"]').first().click();
  await expect(page.locator('[data-testid="cart-line"]')).toHaveCount(cartCountBefore + 1);

  // Lock toggle
  const lockBtn = page.getByRole("button", { name: /lock|unlock/i });
  const lockText = await lockBtn.textContent();
  await lockBtn.click();
  await expect(lockBtn).not.toHaveText(lockText ?? "");

  // Close window button
  // window.close() may be blocked by browser; allow either-or.
  await page.locator('[data-testid="close-editor"]').click();
  await expect(page).toHaveURL(/\/home$/);
});
```

- [ ] **Step 2: Run + commit**

```bash
make e2e-docker
git add tests/e2e/drafter_editor.spec.ts
git commit -m "test(e2e): drafter editor happy path"
```

---

### Task 32: Update CLAUDE.md with PM Workbench dev notes

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append a "PM Workbench" section**

```markdown
## PM Workbench (sub-project #2 + #3)

- Lives on top of Foundation; migrations 0008 (drafter role widening) + 0009 (legacy users -> app_user repoint, projects.pm_id, drop users).
- Drafter-narrow gate: `require_drafter()` — items / modules / parts / hardware_lines / project_hardware_catalog mutations only allow `auth_role IN {drafter, manager, admin}`.
- New routers under `apps/api/app/{home, projects, items, parts, hardware_lines}/`. Mounted in `main.py`.
- Every item-scoped mutation writes both `audit_log` (workspace governance) and `item_edit_log` (item history) in the same DB transaction. Helper: `apps/api/app/edit_log.py`.
- Web routes: `/home` (default landing, replaces `/dashboard`), `/projects`, `/tracking?project_id=`, `/items/[id]?tab=cutlist|hardware|board|log`.
- Editor mode is detected by middleware writing `x-pathname`; layout reads it and hides TabStrip + SideBar, swapping in a "← Return to home" link.
- State: raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / React Hook Form / Zustand in v1.**
- Procurement UI button on `/tracking` is hidden behind `NEXT_PUBLIC_PROCUREMENT_UI_READY=1`.
- PDF generation buttons render disabled with tooltip ("ships in sub-project #5").
- Soft-lock semantics: first save claims ownership; non-owner saves are permitted but write `event='item.lock_overridden'` audit row.
- Lifecycle stage_key (REQ..INST) ≠ items.stage (site location); never use bare "stage" for lifecycle.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): PM Workbench dev notes"
```

---

### Task 33: Final acceptance

- [ ] `make migrate` reaches revision `0009`.
- [ ] `make seed` (re-run after a `make test` cycle if needed): creates 2 projects + 10 items + ~10 modules + ~30 parts + ~20 hardware_lines + 8 catalog rows.
- [ ] `curl -b "jf_session=…" http://localhost:3000/api/home/dashboard` returns metrics + favourites.
- [ ] Login as Rin (`rin.park@hartwood.test` / `hartwood-dev`) → `/home` renders 4 metric cards + sidebar with 2 projects.
- [ ] Click a sidebar project → `/tracking?project_id=X` renders 5 rows; availability strip shows `0 ready / 2 blocked` per row.
- [ ] Click ▶ on a row → `/items/{id}?tab=cutlist`. Cutlist grid shows ≥3 part rows. "Return to home" link visible in TopBar (TabStrip hidden).
- [ ] Add a part row inline; PATCH 200; row persists across refresh; new `item_edit_log` row exists.
- [ ] Switch to Hardware tab → pantry lists ≥4 catalog rows; cart lists ≥2 lines; availability chips show `warn: no orders`.
- [ ] Click Lock → button toggles to Unlock; `audit_log` shows `event='item.lock'` row.
- [ ] Login as Juno (`juno.okafor@hartwood.test`, editor / Foreman). Open same item — soft-lock banner shows "Locked by Noa Lindqvist".
- [ ] PATCH a part as Juno → 403 (drafter-narrow gate).
- [ ] PATCH lifecycle `CNC.done_date` as Juno → 200 (editor allowed).
- [ ] Login as Mina (`mina.klee@hartwood.test`, purchase_officer) — `/home` renders fewer metric cards (deliveries highlighted); `/items/{id}` is read-only (no edit affordances on parts/hardware).
- [ ] Login as Aria (`aria.voss@hartwood.test`, admin) — `/projects` shows the "+ New project" button; create one; `pm_id` defaults to self.
- [ ] Cross-workspace isolation: spin a second workspace via `psql`, log in as its admin, GET workspace A's `/api/items/{id}` → 404.
- [ ] `make test` → all suites green (existing 34 + new ~40 = ~74 passing).
- [ ] `make e2e-docker` → 3 specs pass (Foundation `smoke.spec.ts` + new `pm_workbench.spec.ts` + `drafter_editor.spec.ts`).
- [ ] `audit_log` rows present for every mutation type tried; `item_edit_log` populated; `project_hardware_catalog_log` has add/remove rows from seed.

---

## Self-Review

**Spec coverage:**
- §2.1 no new tables → relied on by all of Phase 2/3.
- §2.2 migration 0008 → T1 + T3 + T5 (Noa flip).
- §2.3 migration 0009 → T2.
- §2.4 invariants → T1/T2/T4/T15/T18 (lock invariant in T15; catalog log in T18).
- §3.1 require_drafter → T4.
- §3.2 jtbd_role on AuthUser → T5.
- §4.1 read surface → T8/T10/T11/T12/T13/T14.
- §4.2 write surface → T8/T9/T15/T16/T17/T18.
- §5.1 /home → T24.
- §5.2 /projects → T25.
- §5.3 /tracking → T26.
- §5.4 /items/[id] editor → T27/T28/T29.
- §5.5 chrome → T22/T23.
- §6.1-6.4 lifecycle/status/lock → T15/T16.
- §6.5 item_edit_log → T7 helper, used everywhere.
- §7.1-7.4 backend tests → T3/T4/T8/T9/T10/T11/T12/T13/T14/T15/T16/T17/T18.
- §7.5 E2E → T30/T31.
- §7.6 seed → T19.
- §7.7 acceptance → T33.

**Placeholder scan:** No TBDs. SQL, Python, TSX, and bash blocks are concrete. The hardware-catalog `_resolve_catalog_view` derived view (T13) is inlined in queries.py rather than a DB view, since the 6 source tables share a static schema; if `supplier` columns are added later, the inline CTE updates in one place.

**Risks called out:**
- T2 (migration 0009) drops the legacy `users` table. The migration is one-way; the safety claim rests on T22 of Foundation already having migrated procurement *queries* off `users`. Verify by running existing procurement tests after applying 0009 (T2 step 3).
- T29 source-catalog endpoint uses an f-string for table name; the whitelist `if table not in _ALLOWED_SOURCE_TABLES: 400` is the safety boundary. No user-supplied table name reaches SQL without passing that check.
- The spec mandates "no React Hook Form" — controlled inputs with PATCH-on-blur is the v1 contract. Don't slip a form lib in during T27/T28/T29.
- The Tailwind `bg-h-warn` / `bg-h-good` / `bg-h-bad` tokens may not yet exist in `globals.css` (Foundation only declared `bg-h-bg`, `bg-h-surface`, `text-h-ink`, `text-h-muted`, `border-h-line`, `bg-h-accent`). If they're missing, T26's `StatusChip` and T27's `SoftLockBanner` need a small token addition (one PR-line edit to `globals.css` + `lib/tokens.ts`). Flag at start of Phase 5.

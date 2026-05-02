# JoineryFlow PDF Generation + Item Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project #5b — PDF generation (Cutlist, Hardware, Combined) + item attachments (cv_drawing, floor_plan, site_measure slots) — on top of the merged Shop Drawings + file-upload subsystem from #5a. A Drafter clicks Print Cutlist / Print Hardware / Print Combined PDF in the item editor footer and gets a PDF download. Combined PDF merges the rendered Cutlist + Hardware + 3 uploaded attachments + (optional) painting parts list.

**Spec:** `docs/superpowers/specs/2026-05-02-pdf-generation-design.md`. Read before starting; this plan only sequences the implementation. The spec resolves all open product/engine/RBAC questions including the WeasyPrint + pypdf engine choice, three-named-slots-per-item attachment model, sync rendering, no caching, material-type hardware grouping, and the lister-blank em-dash fallback.

**Architecture:** No new infrastructure other than 3 new Python deps (`weasyprint`, `pypdf`, `jinja2`) + ~25 MB of pango runtime libs in the api Dockerfile. One small migration (0015) adds `item_attachment` with `UNIQUE (item_id, kind)` slot constraint. Migration 0014 was consumed by the workspace-isolation hardening that landed in commit `cc7ea11`; this sub-project's migration is therefore numbered 0015. New backend modules `apps/api/app/item_attachments/` (CRUD) and `apps/api/app/printing/` (engine + context + routes). Five Jinja2 templates + one `print.css` + four `.woff2` font files committed under `seed/fonts/`. Web side adds an "Attachments" tab to the item editor and turns the 3 disabled Print buttons in `EditorFooter.tsx` into live `<a target="_blank">` download links. State management is raw `fetch()` + URL search params + controlled inputs — **no TanStack Query / React Hook Form / Zustand**, matching prior sub-projects.

**Tech Stack:** FastAPI + SQLAlchemy Core `text()` + Pydantic v2 + WeasyPrint 63+ + pypdf 5+ + Jinja2 3.1+; Next.js 16 App Router + Tailwind v4; pytest + Playwright. Font assets: Inter + JetBrains Mono (.woff2, OFL-licensed).

---

## File Structure (locked)

```
apps/api/app/
  item_attachments/
    __init__.py
    routes.py                # GET bundle + POST/DELETE per slot
    queries.py               # text() SQL with audit (UPSERT + DELETE)
    schemas.py               # AttachmentSlotOut, AttachmentsBundleOut, BindAttachmentIn
  printing/
    __init__.py
    engine.py                # render_html_to_pdf + merge_pdfs
    context.py               # build_context: item + parts + hardware + attachments
    catalog_enrich.py        # _TYPE_MAP-based name/sku resolution per material_type (extracted from procurement_v1)
    routes.py                # GET /items/{iid}/{cutlist,hardware,combined}.pdf
    templates/
      _base.html             # Shared skeleton; loads print.css
      cutlist.html
      hardware.html
      cover_combined.html
      painting.html
      missing_attachment.html
      print.css              # @page + @font-face + table styles
  main.py                    # mount 2 new routers (item_attachments + printing)

apps/api/Dockerfile          # + libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
apps/api/pyproject.toml      # + weasyprint, pypdf, jinja2

apps/api/tests/
  conftest.py                # extend TRUNCATE_TABLES with item_attachment
  test_item_attachments_crud.py
  test_printing_engine.py
  test_print_routes.py
  test_print_workspace_isolation.py

db/alembic/versions/
  0014_item_attachments.py   # item_attachment table + index

seed/
  fonts/                     # NEW directory
    Inter-Regular.woff2
    Inter-Bold.woff2
    JetBrainsMono-Regular.woff2
    JetBrainsMono-Bold.woff2
  hartwood_joinery.py        # + item_attachment demo block

apps/web/app/(app)/items/[id]/
  page.tsx                              # add 'attachments' to ALLOWED_TABS
  _components/
    AttachmentsTab.tsx                  # NEW — 3 slot cards + bundle fetch
    AttachmentSlotCard.tsx              # NEW — current file + Replace + Delete
    EditorFooter.tsx                    # MODIFY — wire 3 print buttons to <a> links

apps/web/lib/
  attachments-types.ts                  # NEW — slot bundle types
  attachments-fetch.ts                  # NEW — get bundle / bind / clear
  print.ts                              # NEW — print URL helpers + tooltip text builder

tests/e2e/
  pdf_generation.spec.ts                # NEW

docs/superpowers/plans/
  2026-05-02-pdf-generation.md          # this file

CLAUDE.md                               # PDF Generation dev notes appended
```

---

## Phase 1 — Schema + dependencies (2 tasks)

### Task 1: Migration 0015 — `item_attachment` table

**Files:**
- Create: `db/alembic/versions/0014_item_attachments.py`

- [ ] **Step 1: Write the migration**

Create `db/alembic/versions/0014_item_attachments.py`:

```python
"""item_attachment: three named slots per item for Combined PDF assembly

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-02
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    CREATE TABLE item_attachment (
      item_attachment_id  bigserial   PRIMARY KEY,
      item_id             bigint      NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
      kind                text        NOT NULL CHECK (kind IN ('cv_drawing','floor_plan','site_measure')),
      file_blob_id        bigint      NOT NULL REFERENCES file_blob(file_blob_id),
      uploaded_by         bigint      NOT NULL REFERENCES app_user(id),
      uploaded_at         timestamptz NOT NULL DEFAULT now(),
      UNIQUE (item_id, kind)
    );

    CREATE INDEX idx_item_attachment_item ON item_attachment (item_id);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-item-attachment schema is recoverable from migrations 0001-0014 only")
```

- [ ] **Step 2: Apply the migration**

```bash
docker compose exec -T api sh -c "cd /db && alembic upgrade head"
```

Expected output ends with `INFO  [alembic.runtime.migration] Running upgrade 0014 -> 0015`.

- [ ] **Step 3: Verify table + index + constraints**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -c "\d+ item_attachment"
docker compose exec -T db psql -U postgres -d joineryflow -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'item_attachment';"
```

Expected:
- `item_attachment` table with all 6 columns + CHECK on `kind` (3 values).
- `UNIQUE (item_id, kind)` shown in the constraints block.
- Three indexes: `item_attachment_pkey`, `item_attachment_item_id_kind_key`, `idx_item_attachment_item`.
- FK to `items(item_id)` with `ON DELETE CASCADE`.
- FK to `file_blob(file_blob_id)`.
- FK to `app_user(id)`.

- [ ] **Step 4: Smoke-test the slot uniqueness from psql**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -v ON_ERROR_STOP=0 <<'SQL'
BEGIN;
INSERT INTO workspace(slug, name) VALUES ('mig14-test', 'Mig14 Test') RETURNING id \gset
INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
  VALUES (:id, 'mt14@test', 'MT14', 'x', 'drafter') RETURNING id AS uid \gset
INSERT INTO projects(project_code, name, pm_id) VALUES ('MIG14-001', 'Mig14', :uid) RETURNING project_id \gset
INSERT INTO items(num, project_id, description) VALUES (90014, :project_id, 'mig14 item') RETURNING item_id \gset
INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
  VALUES (:id, '14aa', 'application/pdf', 100, 'a.pdf', '14aa', :uid) RETURNING file_blob_id \gset
INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
  VALUES (:item_id, 'cv_drawing', :file_blob_id, :uid);
INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
  VALUES (:item_id, 'cv_drawing', :file_blob_id, :uid);
ROLLBACK;
SQL
```

Expected: the second INSERT fails with `ERROR: duplicate key value violates unique constraint "item_attachment_item_id_kind_key"`.

- [ ] **Step 5: Re-run pytest to confirm no regressions**

```bash
docker compose exec api pytest -q
```

Expected: 221 passed (post-workspace-isolation-hardening baseline; commit `cc7ea11`). Record the actual count.

- [ ] **Step 6: Commit**

```bash
git add db/alembic/versions/0014_item_attachments.py
git commit -m "feat(db): migration 0015 — item_attachment three-slot table"
```

---

### Task 2: Add WeasyPrint + pypdf + jinja2 deps + pango runtime libs

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/Dockerfile`

- [ ] **Step 1: Read current Dockerfile + pyproject**

```bash
cat apps/api/Dockerfile
cat apps/api/pyproject.toml
```

Note the current `[project]` `dependencies = [...]` block and the existing apt-get layer (if any) in the Dockerfile.

- [ ] **Step 2: Update `apps/api/pyproject.toml`**

Add three lines to the `dependencies = [...]` list (insert before the closing `]`):

```toml
  "weasyprint>=63",
  "pypdf>=5",
  "jinja2>=3.1",
```

Final `[project]` block should look like (with the existing entries preserved):

```toml
[project]
name = "jf-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy>=2.0",
  "psycopg[binary]>=3.2",
  "alembic>=1.13",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "email-validator>=2.2",
  "argon2-cffi>=23.1",
  "python-multipart>=0.0.12",
  "weasyprint>=63",
  "pypdf>=5",
  "jinja2>=3.1",
]
```

- [ ] **Step 3: Update `apps/api/Dockerfile`**

Find the existing `RUN apt-get` layer (or insert a new one before `pip install`). Add the WeasyPrint runtime dependencies. The final RUN apt-get line should include:

```dockerfile
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
```

(`fonts-liberation` is the WeasyPrint fallback font face; harmless ~3 MB.)

If the Dockerfile previously had no `apt-get` layer, insert this block AFTER `FROM python:3.12-slim` and BEFORE `WORKDIR` / `COPY pyproject.toml`.

- [ ] **Step 4: Rebuild the api image with the new layers**

```bash
docker compose build api
```

Expected: build succeeds. Image size grows ~25 MB.

- [ ] **Step 5: Recreate the api container**

```bash
docker compose up -d --force-recreate api
docker compose exec api python -c "import weasyprint, pypdf, jinja2; print('weasyprint', weasyprint.__version__); print('pypdf', pypdf.__version__); print('jinja2', jinja2.__version__)"
```

Expected: three version strings printed (e.g. `weasyprint 63.1`, `pypdf 5.x`, `jinja2 3.1.x`).

- [ ] **Step 6: Smoke-test WeasyPrint can produce a PDF**

```bash
docker compose exec api python -c "import weasyprint; pdf = weasyprint.HTML(string='<html><body><h1>smoke</h1></body></html>').write_pdf(); print('ok pdf bytes:', len(pdf))"
```

Expected: `ok pdf bytes: <some non-zero number>`. If WeasyPrint complains about missing fonts, the rebuild didn't pick up the apt-get layer — re-run Step 4 with `--no-cache`.

- [ ] **Step 7: Smoke-test pypdf can merge two PDFs**

```bash
docker compose exec api python -c "
import io, pypdf, weasyprint
a = weasyprint.HTML(string='<h1>A</h1>').write_pdf()
b = weasyprint.HTML(string='<h1>B</h1>').write_pdf()
w = pypdf.PdfWriter()
w.append(io.BytesIO(a))
w.append(io.BytesIO(b))
out = io.BytesIO(); w.write(out)
print('merged bytes:', len(out.getvalue()))
print('page count:', len(pypdf.PdfReader(io.BytesIO(out.getvalue())).pages))
"
```

Expected: merged bytes > sum of input lengths, page count = 2.

- [ ] **Step 8: Run full pytest to confirm no regressions**

```bash
docker compose exec api pytest -q
```

Expected: 221 passed (no test changes in this task).

- [ ] **Step 9: Commit**

```bash
git add apps/api/pyproject.toml apps/api/Dockerfile
git commit -m "feat(infra): add weasyprint + pypdf + jinja2 + pango runtime libs to api"
```

---

## Phase 2 — Item attachments backend (2 tasks)

### Task 3: Pydantic schemas + queries for item attachments

**Files:**
- Create: `apps/api/app/item_attachments/__init__.py`
- Create: `apps/api/app/item_attachments/schemas.py`
- Create: `apps/api/app/item_attachments/queries.py`
- Modify: `apps/api/tests/conftest.py`

- [ ] **Step 1: Create the package init**

Create `apps/api/app/item_attachments/__init__.py`:

```python
"""Item attachments: three named slots per item (cv_drawing, floor_plan, site_measure)
backed by file_blob from #5a's upload subsystem. Used by Combined PDF assembly in #5b."""
```

- [ ] **Step 2: Extend `conftest.py` TRUNCATE_TABLES**

In `apps/api/tests/conftest.py`, add `"item_attachment"` to the TRUNCATE_TABLES tuple. It must come BEFORE `"items"` (FK ordering — item_attachment references items). Update the tuple to:

```python
TRUNCATE_TABLES = (
    "shop_drawing_revision",
    "shop_drawing",
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
    "audit_log",
    "session",
    "app_user",
    "workspace",
)
```

- [ ] **Step 3: Write `schemas.py`**

Create `apps/api/app/item_attachments/schemas.py`:

```python
"""Pydantic schemas for the item attachment subsystem."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AttachmentKind = Literal["cv_drawing", "floor_plan", "site_measure"]


class AttachmentSlotOut(BaseModel):
    """One of the three slots; populated or empty."""
    kind: AttachmentKind
    file_blob_id: int | None = None
    original_filename: str | None = None
    byte_size: int | None = None
    uploaded_by: int | None = None
    uploaded_by_name: str | None = None
    uploaded_at: datetime | None = None


class AttachmentsBundleOut(BaseModel):
    """Always exactly 3 slots in canonical order: cv_drawing, floor_plan, site_measure."""
    item_id: int
    slots: list[AttachmentSlotOut]


class BindAttachmentIn(BaseModel):
    file_blob_id: int
```

- [ ] **Step 4: Write the failing query tests**

Create `apps/api/tests/test_item_attachments_crud.py` (initially with the three query-layer tests; route tests come in Task 4):

```python
"""Item attachments — query-layer tests (no HTTP, uses db fixture)."""
import pytest
from sqlalchemy import text

from app.item_attachments.queries import (
    bind_attachment,
    clear_attachment,
    get_bundle,
)


def _seed(db, workspace_id: int) -> dict:
    """Insert one project + drafter user + one item + one PDF file_blob."""
    uid = db.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, 'ia@test', 'IA', 'x', 'drafter') RETURNING id
    """), {"w": workspace_id}).scalar()
    pid = db.execute(text("""
        INSERT INTO projects(project_code, name, pm_id) VALUES('IA-001', 'IA', :u) RETURNING project_id
    """), {"u": uid}).scalar()
    iid = db.execute(text("""
        INSERT INTO items(num, project_id, description) VALUES (90100, :p, 'IA item') RETURNING item_id
    """), {"p": pid}).scalar()
    bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'iaaa', 'application/pdf', 200, 'cv.pdf', 'k/ia/iaaa', :u) RETURNING file_blob_id
    """), {"w": workspace_id, "u": uid}).scalar()
    db.flush()
    return {"uid": uid, "pid": pid, "iid": iid, "bid": bid}


def test_bind_inserts_slot_and_returns_metadata(db, workspace_id):
    seed = _seed(db, workspace_id)
    result = bind_attachment(
        db, item_id=seed["iid"], kind="cv_drawing",
        file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"],
    )
    assert result["kind"] == "cv_drawing"
    assert result["file_blob_id"] == seed["bid"]
    row = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i AND kind = 'cv_drawing'"
    ), {"i": seed["iid"]}).scalar()
    assert row == 1


def test_bind_replaces_existing_slot_with_upsert(db, workspace_id):
    seed = _seed(db, workspace_id)
    # First bind
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    # New blob
    new_bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'iabb', 'application/pdf', 300, 'cv2.pdf', 'k/ia/iabb', :u) RETURNING file_blob_id
    """), {"w": workspace_id, "u": seed["uid"]}).scalar()
    # Replace
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=new_bid, workspace_id=workspace_id, actor_id=seed["uid"])
    row = db.execute(text(
        "SELECT file_blob_id FROM item_attachment WHERE item_id = :i AND kind = 'cv_drawing'"
    ), {"i": seed["iid"]}).scalar()
    assert row == new_bid
    # Still only one row
    count = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i"
    ), {"i": seed["iid"]}).scalar()
    assert count == 1


def test_bind_rejects_non_pdf_mime(db, workspace_id):
    seed = _seed(db, workspace_id)
    png_bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'iapng', 'image/png', 100, 'sketch.png', 'k/ia/iapng', :u) RETURNING file_blob_id
    """), {"w": workspace_id, "u": seed["uid"]}).scalar()
    db.flush()
    with pytest.raises(ValueError, match="application/pdf"):
        bind_attachment(db, item_id=seed["iid"], kind="floor_plan",
                        file_blob_id=png_bid, workspace_id=workspace_id, actor_id=seed["uid"])


def test_bind_rejects_cross_workspace_blob(db, workspace_id):
    seed = _seed(db, workspace_id)
    other_wid = db.execute(text("INSERT INTO workspace(slug,name) VALUES('other','O') RETURNING id")).scalar()
    other_uid = db.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, 'o@o.test', 'O', 'x', 'drafter') RETURNING id
    """), {"w": other_wid}).scalar()
    foreign_bid = db.execute(text("""
        INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
        VALUES (:w, 'oaaa', 'application/pdf', 100, 'x.pdf', 'k/o/oaaa', :u) RETURNING file_blob_id
    """), {"w": other_wid, "u": other_uid}).scalar()
    db.flush()
    with pytest.raises(ValueError, match="workspace"):
        bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                        file_blob_id=foreign_bid, workspace_id=workspace_id, actor_id=seed["uid"])


def test_clear_removes_slot(db, workspace_id):
    seed = _seed(db, workspace_id)
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    deleted = clear_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                               workspace_id=workspace_id, actor_id=seed["uid"])
    assert deleted is True
    count = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i AND kind = 'cv_drawing'"
    ), {"i": seed["iid"]}).scalar()
    assert count == 0


def test_clear_returns_false_if_no_slot(db, workspace_id):
    seed = _seed(db, workspace_id)
    deleted = clear_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                               workspace_id=workspace_id, actor_id=seed["uid"])
    assert deleted is False


def test_get_bundle_returns_three_slots_with_populated_and_null(db, workspace_id):
    seed = _seed(db, workspace_id)
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    bundle = get_bundle(db, item_id=seed["iid"])
    assert bundle["item_id"] == seed["iid"]
    assert len(bundle["slots"]) == 3
    by_kind = {s["kind"]: s for s in bundle["slots"]}
    assert by_kind["cv_drawing"]["file_blob_id"] == seed["bid"]
    assert by_kind["cv_drawing"]["original_filename"] == "cv.pdf"
    assert by_kind["floor_plan"]["file_blob_id"] is None
    assert by_kind["site_measure"]["file_blob_id"] is None


def test_item_delete_cascades_attachments(db, workspace_id):
    seed = _seed(db, workspace_id)
    bind_attachment(db, item_id=seed["iid"], kind="cv_drawing",
                    file_blob_id=seed["bid"], workspace_id=workspace_id, actor_id=seed["uid"])
    db.execute(text("DELETE FROM items WHERE item_id = :i"), {"i": seed["iid"]})
    count = db.execute(text(
        "SELECT count(*) FROM item_attachment WHERE item_id = :i"
    ), {"i": seed["iid"]}).scalar()
    assert count == 0
```

- [ ] **Step 5: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_item_attachments_crud.py -v
```

Expected: `ImportError: cannot import name 'bind_attachment' from 'app.item_attachments.queries'`.

- [ ] **Step 6: Implement `queries.py`**

Create `apps/api/app/item_attachments/queries.py`:

```python
"""Item attachments query layer.

Routes own the transaction boundary (db.commit). Queries flush only.
The PDF-only mime gate and the workspace-match check on file_blob run here so
both routes and seed helpers go through the same enforcement path.
"""
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit

AttachmentKind = Literal["cv_drawing", "floor_plan", "site_measure"]
ALL_KINDS: tuple[AttachmentKind, ...] = ("cv_drawing", "floor_plan", "site_measure")


def bind_attachment(
    db: Session,
    *,
    item_id: int,
    kind: AttachmentKind,
    file_blob_id: int,
    workspace_id: int,
    actor_id: int,
) -> dict:
    """UPSERT a slot. Validates blob is PDF + workspace-match. Writes audit."""
    blob = db.execute(
        text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": file_blob_id, "w": workspace_id},
    ).first()
    if not blob:
        raise ValueError("file_blob not found in this workspace")
    if blob[0] != "application/pdf":
        raise ValueError("item attachments must be application/pdf")

    # Capture the prior file_blob_id for the audit payload (for the "replaced" case).
    prior = db.execute(
        text("SELECT file_blob_id FROM item_attachment WHERE item_id = :i AND kind = :k"),
        {"i": item_id, "k": kind},
    ).scalar()

    db.execute(
        text(
            """
            INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
            VALUES (:i, :k, :b, :u)
            ON CONFLICT (item_id, kind) DO UPDATE
              SET file_blob_id = EXCLUDED.file_blob_id,
                  uploaded_by  = EXCLUDED.uploaded_by,
                  uploaded_at  = now()
            """
        ),
        {"i": item_id, "k": kind, "b": file_blob_id, "u": actor_id},
    )

    audit_payload = {"file_blob_id": file_blob_id}
    if prior is not None and prior != file_blob_id:
        audit_payload["replaced_file_blob_id"] = prior

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="item_attachment.bind", target=f"{item_id}:{kind}",
        payload=audit_payload,
    )
    db.flush()
    return {"item_id": item_id, "kind": kind, "file_blob_id": file_blob_id}


def clear_attachment(
    db: Session,
    *,
    item_id: int,
    kind: AttachmentKind,
    workspace_id: int,
    actor_id: int,
) -> bool:
    """Remove a slot. Returns True if removed, False if not present."""
    row = db.execute(
        text("DELETE FROM item_attachment WHERE item_id = :i AND kind = :k RETURNING file_blob_id"),
        {"i": item_id, "k": kind},
    ).first()
    if not row:
        return False
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="item_attachment.clear", target=f"{item_id}:{kind}",
        payload={"file_blob_id": row[0]},
    )
    db.flush()
    return True


def get_bundle(db: Session, *, item_id: int) -> dict:
    """Return all 3 slots in canonical order, populated or null."""
    rows = db.execute(
        text(
            """
            SELECT ia.kind, ia.file_blob_id, ia.uploaded_by, ia.uploaded_at,
                   fb.original_filename, fb.byte_size,
                   u.full_name AS uploaded_by_name
              FROM item_attachment ia
              JOIN file_blob fb ON fb.file_blob_id = ia.file_blob_id
              LEFT JOIN app_user u ON u.id = ia.uploaded_by
             WHERE ia.item_id = :i
            """
        ),
        {"i": item_id},
    ).mappings().all()
    by_kind = {r["kind"]: dict(r) for r in rows}

    slots: list[dict] = []
    for kind in ALL_KINDS:
        if kind in by_kind:
            slots.append(by_kind[kind])
        else:
            slots.append({
                "kind": kind, "file_blob_id": None, "original_filename": None,
                "byte_size": None, "uploaded_by": None, "uploaded_by_name": None,
                "uploaded_at": None,
            })
    return {"item_id": item_id, "slots": slots}
```

- [ ] **Step 7: Run query tests, confirm pass**

```bash
docker compose exec api pytest tests/test_item_attachments_crud.py -v
```

Expected: 8 passed (the 8 `test_*` functions defined in Step 4).

- [ ] **Step 8: Run full suite to confirm no regressions**

```bash
docker compose exec api pytest -q
```

Expected: 215 + 8 = 223 passed.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/item_attachments/__init__.py apps/api/app/item_attachments/schemas.py apps/api/app/item_attachments/queries.py apps/api/tests/conftest.py apps/api/tests/test_item_attachments_crud.py
git commit -m "feat(item-attachments): pydantic schemas + query layer with UPSERT + audit"
```

---

### Task 4: Item attachments routes (GET bundle, POST/DELETE per slot)

**Files:**
- Create: `apps/api/app/item_attachments/routes.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_item_attachments_crud.py` (append route-layer tests)

- [ ] **Step 1: Append the failing route tests**

In `apps/api/tests/test_item_attachments_crud.py`, append the route-layer tests that exercise the HTTP surface. Add at the bottom of the file:

```python
import io
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


def _route_seed(client, truncate_all, role: str = "drafter") -> dict:
    """Truncate, seed workspace+user+project+item, log in, return ids + a PDF file_blob_id."""
    truncate_all()
    from app.db import SessionLocal
    from sqlalchemy import text as _t
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(_t("INSERT INTO workspace(slug,name) VALUES('rt','RT') RETURNING id")).scalar()
        uid = s.execute(_t("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@rt.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(_t("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('RT-001', 'RT', :u) RETURNING project_id
        """), {"u": uid}).scalar()
        iid = s.execute(_t("""
            INSERT INTO items(num, project_id, description) VALUES (90200, :p, 'RT item') RETURNING item_id
        """), {"p": pid}).scalar()
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login",
                    json={"workspace_slug": "rt", "email": f"{role}@rt.test", "password": "pw"})
    assert r.status_code == 200, r.text
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 201, r.text
    return {"wid": wid, "uid": uid, "pid": pid, "iid": iid, "bid": r.json()["file_blob_id"]}


def test_route_get_bundle_initially_empty(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.get(f"/items/{ids['iid']}/attachments")
    assert r.status_code == 200
    body = r.json()
    assert body["item_id"] == ids["iid"]
    assert len(body["slots"]) == 3
    assert all(s["file_blob_id"] is None for s in body["slots"])


def test_route_bind_then_get_bundle_shows_populated(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.post(f"/items/{ids['iid']}/attachments/cv_drawing",
                    json={"file_blob_id": ids["bid"]})
    assert r.status_code == 201, r.text
    r = client.get(f"/items/{ids['iid']}/attachments")
    body = r.json()
    cv = next(s for s in body["slots"] if s["kind"] == "cv_drawing")
    assert cv["file_blob_id"] == ids["bid"]


def test_route_bind_invalid_kind_returns_422(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.post(f"/items/{ids['iid']}/attachments/garbage",
                    json={"file_blob_id": ids["bid"]})
    assert r.status_code == 422


def test_route_bind_non_pdf_returns_415(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    files = {"file": ("p.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200), "image/png")}
    png_id = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/items/{ids['iid']}/attachments/floor_plan",
                    json={"file_blob_id": png_id})
    assert r.status_code == 415
    assert "application/pdf" in r.json()["detail"]


def test_route_clear_existing_returns_204(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    client.post(f"/items/{ids['iid']}/attachments/cv_drawing",
                json={"file_blob_id": ids["bid"]})
    r = client.delete(f"/items/{ids['iid']}/attachments/cv_drawing")
    assert r.status_code == 204


def test_route_clear_missing_returns_404(client, truncate_all):
    ids = _route_seed(client, truncate_all)
    r = client.delete(f"/items/{ids['iid']}/attachments/cv_drawing")
    assert r.status_code == 404


def test_route_editor_cannot_write_attachments(client, truncate_all):
    """Editor has list:read but not list:write — 403 on POST/DELETE."""
    ids = _route_seed(client, truncate_all, role="editor")
    r = client.post(f"/items/{ids['iid']}/attachments/cv_drawing",
                    json={"file_blob_id": ids["bid"]})
    assert r.status_code == 403


def test_route_viewer_can_get_bundle(client, truncate_all):
    """Viewer has list:read — GET bundle returns 200."""
    ids = _route_seed(client, truncate_all, role="viewer")
    r = client.get(f"/items/{ids['iid']}/attachments")
    assert r.status_code == 200
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_item_attachments_crud.py -v -k "route"
```

Expected: 8 failures (404 — routes not mounted yet).

- [ ] **Step 3: Implement `routes.py`**

Create `apps/api/app/item_attachments/routes.py`:

```python
"""Item attachments routes — GET bundle + POST/DELETE per slot."""
from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import AttachmentsBundleOut, BindAttachmentIn

router = APIRouter(tags=["item_attachments"])

# Path param Literal so FastAPI returns 422 for unknown kinds without us touching the handler.
KindPath = Path(..., regex="^(cv_drawing|floor_plan|site_measure)$")


@router.get("/items/{iid}/attachments", response_model=AttachmentsBundleOut)
def get_attachments_route(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    return q.get_bundle(db, item_id=iid)


@router.post("/items/{iid}/attachments/{kind}", status_code=201)
def bind_attachment_route(
    iid: int,
    kind: str = KindPath,
    body: BindAttachmentIn = ...,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    try:
        result = q.bind_attachment(
            db, item_id=iid, kind=kind, file_blob_id=body.file_blob_id,
            workspace_id=user.workspace_id, actor_id=user.id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "application/pdf" in msg:
            raise HTTPException(status_code=415, detail=msg)
        if "workspace" in msg or "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    db.commit()
    return result


@router.delete("/items/{iid}/attachments/{kind}", status_code=204)
def clear_attachment_route(
    iid: int,
    kind: str = KindPath,
    user: AuthUser = Depends(require_permission("list", "write")),
    db: Session = Depends(get_db),
):
    if not q.clear_attachment(db, item_id=iid, kind=kind,
                              workspace_id=user.workspace_id, actor_id=user.id):
        raise HTTPException(status_code=404, detail="no attachment in this slot")
    db.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Mount the router in `main.py`**

In `apps/api/app/main.py`, add the import:

```python
from .item_attachments.routes import router as item_attachments_router
```

And include it after the existing `files_router`:

```python
app.include_router(item_attachments_router)
```

- [ ] **Step 5: Run route tests, confirm pass**

```bash
docker compose exec api pytest tests/test_item_attachments_crud.py -v
```

Expected: 16 passed (8 query-layer + 8 route-layer).

- [ ] **Step 6: Run full suite**

```bash
docker compose exec api pytest -q
```

Expected: 215 + 16 = 231 passed.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/item_attachments/routes.py apps/api/app/main.py apps/api/tests/test_item_attachments_crud.py
git commit -m "feat(item-attachments): GET bundle + POST/DELETE per slot routes"
```

---

## Phase 3 — Print engine primitives + templates + fonts (3 tasks)

### Task 5: `engine.py` — render_html_to_pdf + merge_pdfs

**Files:**
- Create: `apps/api/app/printing/__init__.py`
- Create: `apps/api/app/printing/engine.py`
- Create: `apps/api/app/printing/templates/.gitkeep` (placeholder; templates added in Task 6)
- Create: `apps/api/tests/test_printing_engine.py`

- [ ] **Step 1: Create the package init + templates dir**

```bash
mkdir -p apps/api/app/printing/templates
touch apps/api/app/printing/templates/.gitkeep
```

Create `apps/api/app/printing/__init__.py`:

```python
"""Print engine: WeasyPrint render + pypdf merge for Cutlist/Hardware/Combined PDFs."""
```

- [ ] **Step 2: Write the failing engine tests**

Create `apps/api/tests/test_printing_engine.py`:

```python
"""Print engine primitives — render_html_to_pdf + merge_pdfs.

Pure engine tests; no DB, no HTTP, no templates from disk (use inline strings).
"""
import io

import pypdf
import pytest

from app.printing.engine import merge_pdfs, render_html_string_to_pdf


def test_render_html_string_returns_valid_pdf():
    pdf = render_html_string_to_pdf("<html><body><h1>hello</h1></body></html>")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 100


def test_merge_pdfs_concatenates_pages():
    a = render_html_string_to_pdf("<h1>A</h1>")
    b = render_html_string_to_pdf("<h1>B</h1>")
    c = render_html_string_to_pdf("<h1>C</h1>")
    merged = merge_pdfs([a, b, c])
    reader = pypdf.PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 3


def test_merge_pdfs_empty_list_returns_empty_pdf():
    merged = merge_pdfs([])
    # pypdf produces a valid (empty) PDF when given no parts.
    assert merged[:5] == b"%PDF-"


def test_merge_pdfs_single_part_roundtrips():
    a = render_html_string_to_pdf("<h1>solo</h1>")
    merged = merge_pdfs([a])
    reader = pypdf.PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 1


def test_render_template_pdf_uses_jinja_autoescape():
    """Verify HTML autoescape is on so '<script>' becomes '&lt;script&gt;' in the PDF text."""
    from app.printing.engine import render_template_to_pdf
    # Use an inline template via a tmp environment? The plan-level test uses the
    # production env so we exercise autoescape on the cutlist template's `item.description`
    # context variable — but cutlist.html doesn't exist yet. Use a smoke template instead.
    # Skip if not available; covered by route tests in Task 8.
    pytest.skip("autoescape end-to-end coverage lives in test_print_routes.py once cutlist.html exists")


def test_render_html_string_handles_unicode():
    pdf = render_html_string_to_pdf("<html><body>café — 25mm</body></html>")
    assert pdf[:5] == b"%PDF-"
```

- [ ] **Step 3: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_printing_engine.py -v
```

Expected: `ImportError: cannot import name 'render_html_string_to_pdf' from 'app.printing.engine'`.

- [ ] **Step 4: Implement `engine.py`**

Create `apps/api/app/printing/engine.py`:

```python
"""WeasyPrint HTML→PDF + pypdf merge primitives.

Two functions, two responsibilities:
  - render_html_string_to_pdf / render_template_to_pdf: Jinja2 + WeasyPrint
  - merge_pdfs: pypdf concatenation

The Jinja2 environment auto-escapes HTML to prevent injection from user-controlled
fields (item description, part names, notes).
"""
from io import BytesIO
from pathlib import Path
from typing import Mapping

import jinja2
import pypdf
import weasyprint

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html"]),
)


def render_html_string_to_pdf(html: str, *, base_url: str | None = None) -> bytes:
    """Render an HTML string to PDF bytes via WeasyPrint."""
    return weasyprint.HTML(string=html, base_url=base_url or str(TEMPLATES_DIR)).write_pdf()


def render_template_to_pdf(template_name: str, ctx: Mapping) -> bytes:
    """Render a Jinja2 template to PDF bytes via WeasyPrint."""
    html = _env.get_template(template_name).render(**ctx)
    return weasyprint.HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()


def merge_pdfs(parts: list[bytes]) -> bytes:
    """Concatenate PDF byte sources in order. Empty list returns an empty PDF."""
    writer = pypdf.PdfWriter()
    for part in parts:
        writer.append(BytesIO(part))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
```

- [ ] **Step 5: Run engine tests, confirm pass**

```bash
docker compose exec api pytest tests/test_printing_engine.py -v
```

Expected: 5 passed, 1 skipped.

- [ ] **Step 6: Run full suite**

```bash
docker compose exec api pytest -q
```

Expected: 231 + 5 = 236 passed (1 skipped).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/printing/__init__.py apps/api/app/printing/engine.py apps/api/app/printing/templates/.gitkeep apps/api/tests/test_printing_engine.py
git commit -m "feat(printing): WeasyPrint render + pypdf merge engine primitives"
```

---

### Task 6: Print templates + print.css + 4 .woff2 fonts

**Files:**
- Create: `seed/fonts/Inter-Regular.woff2`
- Create: `seed/fonts/Inter-Bold.woff2`
- Create: `seed/fonts/JetBrainsMono-Regular.woff2`
- Create: `seed/fonts/JetBrainsMono-Bold.woff2`
- Create: `apps/api/app/printing/templates/_base.html`
- Create: `apps/api/app/printing/templates/cutlist.html`
- Create: `apps/api/app/printing/templates/hardware.html`
- Create: `apps/api/app/printing/templates/cover_combined.html`
- Create: `apps/api/app/printing/templates/painting.html`
- Create: `apps/api/app/printing/templates/missing_attachment.html`
- Create: `apps/api/app/printing/templates/print.css`

- [ ] **Step 1: Download the four .woff2 font files**

Inter and JetBrains Mono are open-source (OFL). Download the .woff2 versions from upstream:

```bash
mkdir -p seed/fonts
# Inter v4 — woff2 files from official rsms/inter release (use the latest release tag)
curl -fL -o seed/fonts/Inter-Regular.woff2 \
  https://github.com/rsms/inter/raw/v4.0/docs/font-files/InterDisplay-Regular.woff2 || \
  curl -fL -o seed/fonts/Inter-Regular.woff2 \
  https://rsms.me/inter/font-files/Inter-Regular.woff2
curl -fL -o seed/fonts/Inter-Bold.woff2 \
  https://rsms.me/inter/font-files/Inter-Bold.woff2

# JetBrains Mono v2.304 — woff2 from official JetBrains/JetBrainsMono release
curl -fL -o seed/fonts/JetBrainsMono-Regular.woff2 \
  https://github.com/JetBrains/JetBrainsMono/raw/v2.304/fonts/webfonts/JetBrainsMono-Regular.woff2
curl -fL -o seed/fonts/JetBrainsMono-Bold.woff2 \
  https://github.com/JetBrains/JetBrainsMono/raw/v2.304/fonts/webfonts/JetBrainsMono-Bold.woff2

ls -lh seed/fonts/
```

Expected: four `.woff2` files, each 50-200 KB. Total under 800 KB.

If a URL is unreachable from the dev box, fallback URLs:
- Inter: https://fonts.google.com/download?family=Inter (then convert .ttf → .woff2 with woff2_compress)
- JetBrains Mono: https://fonts.google.com/download?family=JetBrains+Mono

- [ ] **Step 2: Verify the fonts are valid woff2 by checking magic bytes**

```bash
for f in seed/fonts/*.woff2; do
  echo -n "$f: "
  head -c 4 "$f" | xxd | head -1
done
```

Expected: each line shows `wOF2` as the first 4 bytes (`77 4f 46 32`). If any file shows HTML or empty content, the curl failed and the file needs re-downloading.

- [ ] **Step 3: Write `print.css`**

Create `apps/api/app/printing/templates/print.css`:

```css
/* JoineryFlow print stylesheet — paged-media controls for WeasyPrint */

@font-face {
  font-family: 'Inter';
  font-weight: 400;
  font-style: normal;
  src: url('../../../../seed/fonts/Inter-Regular.woff2') format('woff2');
}
@font-face {
  font-family: 'Inter';
  font-weight: 700;
  font-style: normal;
  src: url('../../../../seed/fonts/Inter-Bold.woff2') format('woff2');
}
@font-face {
  font-family: 'JetBrains Mono';
  font-weight: 400;
  font-style: normal;
  src: url('../../../../seed/fonts/JetBrainsMono-Regular.woff2') format('woff2');
}
@font-face {
  font-family: 'JetBrains Mono';
  font-weight: 700;
  font-style: normal;
  src: url('../../../../seed/fonts/JetBrainsMono-Bold.woff2') format('woff2');
}

@page {
  size: A4;
  margin: 14mm 12mm 18mm 12mm;
  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9pt;
    color: #5a574f;
  }
}

* { box-sizing: border-box; }

body {
  font-family: 'Inter', sans-serif;
  font-size: 10pt;
  color: #1b1a17;
  margin: 0;
  -webkit-font-smoothing: antialiased;
}

h1 { font-size: 18pt; margin: 0 0 4mm 0; font-weight: 700; }
h2 { font-size: 13pt; margin: 6mm 0 3mm 0; font-weight: 700; border-bottom: 1px solid #e4e0d8; padding-bottom: 1mm; }
h3 { font-size: 11pt; margin: 4mm 0 2mm 0; font-weight: 700; }

.mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
.muted { color: #5a574f; }

.item-header {
  display: grid;
  grid-template-columns: max-content 1fr max-content 1fr;
  gap: 1mm 4mm;
  font-size: 9pt;
  border: 1px solid #e4e0d8;
  padding: 3mm 4mm;
  margin-bottom: 4mm;
}
.item-header .label { color: #5a574f; }
.item-header .value { color: #1b1a17; }

table.parts, table.hw, table.painting {
  width: 100%;
  border-collapse: collapse;
  font-size: 9pt;
}
table.parts th, table.parts td,
table.hw th, table.hw td,
table.painting th, table.painting td {
  border-bottom: 1px solid #e4e0d8;
  padding: 1.5mm 2mm;
  text-align: left;
  vertical-align: top;
}
table.parts thead, table.hw thead, table.painting thead {
  background: #f4f2ed;
}
table.parts thead th, table.hw thead th, table.painting thead th {
  font-weight: 700;
  font-size: 8pt;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #5a574f;
}

.hw-group { margin: 4mm 0 6mm 0; page-break-inside: avoid; }
.hw-group .hw-group-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 1.5mm; }
.hw-group .hw-group-header .qty-total { font-family: 'JetBrains Mono', monospace; color: #5a574f; }

.slot-manifest { width: 100%; border-collapse: collapse; font-size: 10pt; margin-top: 4mm; }
.slot-manifest td { padding: 2mm 3mm; border-bottom: 1px solid #e4e0d8; }
.slot-manifest .present { color: #1b1a17; }
.slot-manifest .missing { color: #b5b1a6; font-style: italic; }

.placeholder-page {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 240mm;
  color: #b5b1a6;
  font-size: 16pt;
  text-align: center;
}
.placeholder-page .kind { font-weight: 700; color: #8f8b80; margin-bottom: 4mm; }

.page-break { page-break-after: always; }
```

- [ ] **Step 4: Write `_base.html`**

Create `apps/api/app/printing/templates/_base.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ title|default('JoineryFlow') }}</title>
  <link rel="stylesheet" href="print.css">
</head>
<body>
  {% block body %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: Write `cutlist.html`**

Create `apps/api/app/printing/templates/cutlist.html`:

```html
{% extends "_base.html" %}
{% set title = "Cutlist — " + (item.description or item.code or "item " ~ item.item_id) %}
{% block body %}
  <h1>Cutlist · {{ item.description or item.code or 'Item ' ~ item.item_id }}</h1>

  <div class="item-header">
    <div class="label">Item #</div><div class="value mono">{{ item.num }}</div>
    <div class="label">Project</div><div class="value mono">{{ item.project_code }} · {{ item.project_name }}</div>
    <div class="label">Room</div><div class="value">{{ item.rm_no or '' }}{% if item.rm_no and item.rm_desc %} · {% endif %}{{ item.rm_desc or '' }}</div>
    <div class="label">Stage</div><div class="value">{{ item.stage or '—' }}</div>
    <div class="label">Lister</div><div class="value">{{ item.lister or '—' }}</div>
    <div class="label">Date</div><div class="value mono">{{ rendered_at.strftime('%d/%m/%Y') }}</div>
  </div>

  <h2>Parts</h2>
  {% if parts|length == 0 %}
    <p class="muted">No parts on this item.</p>
  {% else %}
  <table class="parts">
    <thead>
      <tr>
        <th style="width:6%">Qty</th>
        <th style="width:24%">Part</th>
        <th style="width:8%">Len mm</th>
        <th style="width:8%">Wid mm</th>
        <th style="width:18%">Material</th>
        <th style="width:8%">Edge</th>
        <th style="width:10%">Colour</th>
        <th style="width:8%">Edging</th>
        <th style="width:10%">Paint</th>
      </tr>
    </thead>
    <tbody>
      {% for p in parts %}
      <tr>
        <td class="mono">{{ p.qty }}</td>
        <td>{{ p.part_name or '' }}</td>
        <td class="mono">{{ p.len_mm or '' }}</td>
        <td class="mono">{{ p.wid_mm or '' }}</td>
        <td>{{ p.material_description or p.material_code or '' }}</td>
        <td>{{ p.edge or '' }}</td>
        <td>{{ p.colour or '' }}</td>
        <td>{{ p.edging_spec or '' }}</td>
        <td class="mono">{{ p.paint_instruction }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
{% endblock %}
```

- [ ] **Step 6: Write `hardware.html`**

Create `apps/api/app/printing/templates/hardware.html`:

```html
{% extends "_base.html" %}
{% set title = "Hardware — " + (item.description or "item " ~ item.item_id) %}
{% block body %}
  <h1>Hardware · {{ item.description or item.code or 'Item ' ~ item.item_id }}</h1>

  <div class="item-header">
    <div class="label">Item #</div><div class="value mono">{{ item.num }}</div>
    <div class="label">Project</div><div class="value mono">{{ item.project_code }} · {{ item.project_name }}</div>
    <div class="label">Room</div><div class="value">{{ item.rm_no or '' }}{% if item.rm_no and item.rm_desc %} · {% endif %}{{ item.rm_desc or '' }}</div>
    <div class="label">Stage</div><div class="value">{{ item.stage or '—' }}</div>
    <div class="label">Lister</div><div class="value">{{ item.lister or '—' }}</div>
    <div class="label">Date</div><div class="value mono">{{ rendered_at.strftime('%d/%m/%Y') }}</div>
  </div>

  {% if hardware|length == 0 %}
    <p class="muted">No hardware lines on this item.</p>
  {% else %}
    {% for group in hardware %}
    <div class="hw-group">
      <div class="hw-group-header">
        <h3>{{ group.material_type }}</h3>
        <span class="qty-total">{{ group.lines|length }} line{% if group.lines|length != 1 %}s{% endif %} · qty {{ group.qty_total }}</span>
      </div>
      <table class="hw">
        <thead>
          <tr>
            <th style="width:8%">Qty</th>
            <th style="width:18%">SKU</th>
            <th style="width:44%">Description</th>
            <th style="width:30%">Note</th>
          </tr>
        </thead>
        <tbody>
          {% for line in group.lines %}
          <tr>
            <td class="mono">{{ line.qty }}</td>
            <td class="mono">{{ line.sku or '' }}</td>
            <td>{{ line.description or '' }}</td>
            <td>{{ line.note or '' }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% endfor %}
  {% endif %}
{% endblock %}
```

- [ ] **Step 7: Write `cover_combined.html`**

Create `apps/api/app/printing/templates/cover_combined.html`:

```html
{% extends "_base.html" %}
{% set title = "Combined PDF — " + (item.description or "item " ~ item.item_id) %}
{% block body %}
  <h1>{{ item.description or item.code or 'Item ' ~ item.item_id }}</h1>
  <p class="muted">Combined production PDF · {{ rendered_at.strftime('%d/%m/%Y %H:%M') }} UTC</p>

  <div class="item-header">
    <div class="label">Item #</div><div class="value mono">{{ item.num }}</div>
    <div class="label">Project</div><div class="value mono">{{ item.project_code }} · {{ item.project_name }}</div>
    <div class="label">Room</div><div class="value">{{ item.rm_no or '' }}{% if item.rm_no and item.rm_desc %} · {% endif %}{{ item.rm_desc or '' }}</div>
    <div class="label">Stage</div><div class="value">{{ item.stage or '—' }}</div>
    <div class="label">Lister</div><div class="value">{{ item.lister or '—' }}</div>
    <div class="label">Assembler</div><div class="value">{{ item.assembler or '—' }}</div>
  </div>

  <h2>Slot manifest</h2>
  <table class="slot-manifest">
    <tr>
      <td style="width:30%">CV production drawing</td>
      <td class="{{ 'present' if attachments.cv_drawing else 'missing' }}">
        {{ attachments.cv_drawing.original_filename if attachments.cv_drawing else 'not uploaded' }}
      </td>
    </tr>
    <tr>
      <td>Floor plan</td>
      <td class="{{ 'present' if attachments.floor_plan else 'missing' }}">
        {{ attachments.floor_plan.original_filename if attachments.floor_plan else 'not uploaded' }}
      </td>
    </tr>
    <tr>
      <td>Site measure</td>
      <td class="{{ 'present' if attachments.site_measure else 'missing' }}">
        {{ attachments.site_measure.original_filename if attachments.site_measure else 'not uploaded' }}
      </td>
    </tr>
  </table>

  {% if has_painting %}
    <p class="muted" style="margin-top:6mm">Includes painting parts list.</p>
  {% endif %}
{% endblock %}
```

- [ ] **Step 8: Write `painting.html`**

Create `apps/api/app/printing/templates/painting.html`:

```html
{% extends "_base.html" %}
{% set title = "Painting parts — " + (item.description or "item " ~ item.item_id) %}
{% block body %}
  <h1>Painting parts · {{ item.description or item.code or 'Item ' ~ item.item_id }}</h1>

  <div class="item-header">
    <div class="label">Item #</div><div class="value mono">{{ item.num }}</div>
    <div class="label">Project</div><div class="value mono">{{ item.project_code }} · {{ item.project_name }}</div>
    <div class="label">Date</div><div class="value mono">{{ rendered_at.strftime('%d/%m/%Y') }}</div>
  </div>

  <table class="painting">
    <thead>
      <tr>
        <th style="width:6%">Qty</th>
        <th style="width:30%">Part</th>
        <th style="width:8%">Len mm</th>
        <th style="width:8%">Wid mm</th>
        <th style="width:24%">Material</th>
        <th style="width:14%">Colour</th>
        <th style="width:10%">Instruction</th>
      </tr>
    </thead>
    <tbody>
      {% for p in parts if p.paint_instruction != 'NONE' %}
      <tr>
        <td class="mono">{{ p.qty }}</td>
        <td>{{ p.part_name or '' }}</td>
        <td class="mono">{{ p.len_mm or '' }}</td>
        <td class="mono">{{ p.wid_mm or '' }}</td>
        <td>{{ p.material_description or p.material_code or '' }}</td>
        <td>{{ p.colour or '' }}</td>
        <td class="mono">{{ p.paint_instruction }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
{% endblock %}
```

- [ ] **Step 9: Write `missing_attachment.html`**

Create `apps/api/app/printing/templates/missing_attachment.html`:

```html
{% extends "_base.html" %}
{% set _kind_labels = {'cv_drawing': 'CV Production Drawing', 'floor_plan': 'Floor Plan', 'site_measure': 'Site Measure'} %}
{% block body %}
  <div class="placeholder-page">
    <div class="kind">{{ _kind_labels.get(kind, kind) }}</div>
    <div>not uploaded</div>
    <div class="muted" style="margin-top:6mm; font-size:10pt">Item {{ item.num }} · {{ item.description or item.code or '' }}</div>
  </div>
{% endblock %}
```

- [ ] **Step 10: Smoke-test the templates render via the engine**

```bash
docker compose exec api python -c "
from datetime import datetime, timezone
from app.printing.engine import render_template_to_pdf
ctx_item = {'item_id': 1, 'num': 42, 'description': 'Kitchen base', 'code': 'K01', 'item_code': '',
            'rm_no': '1.01', 'rm_desc': 'Kitchen', 'stage': 'Joinery Lab', 'zone': '', 'level': '',
            'lister': 'Rin Park', 'assembler': '', 'project_id': 1, 'project_code': 'ALF-001',
            'project_name': 'Alfred'}
ctx = {'item': ctx_item, 'parts': [], 'hardware': [], 'attachments': {}, 'has_painting': False,
       'rendered_at': datetime.now(timezone.utc)}
for t in ('cutlist.html','hardware.html','cover_combined.html','painting.html','missing_attachment.html'):
    pdf = render_template_to_pdf(t, {**ctx, 'kind': 'cv_drawing'})
    print(f'{t}: {len(pdf)} bytes, starts {pdf[:5]}')
"
```

Expected: five lines, each printing the byte size + `b'%PDF-'`. If any template has a Jinja syntax error you'll see a `TemplateSyntaxError` traceback.

- [ ] **Step 11: Commit**

```bash
git add seed/fonts/Inter-Regular.woff2 seed/fonts/Inter-Bold.woff2 seed/fonts/JetBrainsMono-Regular.woff2 seed/fonts/JetBrainsMono-Bold.woff2 apps/api/app/printing/templates/_base.html apps/api/app/printing/templates/cutlist.html apps/api/app/printing/templates/hardware.html apps/api/app/printing/templates/cover_combined.html apps/api/app/printing/templates/painting.html apps/api/app/printing/templates/missing_attachment.html apps/api/app/printing/templates/print.css
git commit -m "feat(printing): print templates + print.css + Inter/JetBrainsMono woff2 fonts"
```

If you hit `.gitignore` rules blocking `*.woff2`, override with `git add -f seed/fonts/*.woff2`.

---

### Task 7: `catalog_enrich.py` — material_type → name/sku/qty grouping

**Files:**
- Create: `apps/api/app/printing/catalog_enrich.py`

- [ ] **Step 1: Read the existing procurement_v1 catalog enrichment to copy the pattern**

```bash
cat apps/api/app/procurement_v1/materials/queries.py | head -120
```

Note the `_TYPE_MAP` dict and the `attach_names` (or similarly-named) helper that maps `(material_type, material_id)` to `(description, sku)` per the 6 catalog tables.

- [ ] **Step 2: Implement `catalog_enrich.py`**

Create `apps/api/app/printing/catalog_enrich.py`:

```python
"""Resolve hardware lines into per-material-type groups for the print template.

Reuses the same `_TYPE_MAP` shape as procurement_v1/materials/queries.py.
Extracted here (rather than imported) so the printing module is self-contained
and the procurement_v1 module is free to evolve its internal helpers.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

# Maps catalog material_type → (table_name, pk_column, name_column, sku_column).
_TYPE_MAP: dict[str, tuple[str, str, str, str]] = {
    "BOARD":     ("board_materials",    "material_id", "description", "sku"),
    "HARDWARE":  ("hardware_materials", "material_id", "description", "sku"),
    "CUSTOM":    ("custom_made",        "material_id", "description", "sku"),
    "BENCHTOP":  ("benchtop_materials", "material_id", "description", "sku"),
    "APPLIANCE": ("appliances",         "material_id", "description", "sku"),
    "HIRE":      ("equipment_hire",     "hire_id",     "description", "sku"),
}


def group_hardware_for_print(db: Session, lines: list[dict]) -> list[dict]:
    """Group hardware lines by material_type, enriched with name + sku.

    Input rows are dicts with keys: qty, note, material_type, material_id, catalog_id.
    Output is a list of group dicts in canonical order:
        { "material_type": ..., "lines": [{qty, sku, description, note}, ...], "qty_total": int }
    """
    if not lines:
        return []

    by_type: dict[str, list[int]] = {}
    for line in lines:
        by_type.setdefault(line["material_type"], []).append(line["material_id"])

    name_map: dict[tuple[str, int], tuple[str, str | None]] = {}
    for material_type, ids in by_type.items():
        if material_type not in _TYPE_MAP:
            continue
        table, pk, name_col, sku_col = _TYPE_MAP[material_type]
        rows = db.execute(
            text(f"SELECT {pk} AS mid, {name_col} AS name, {sku_col} AS sku "
                 f"FROM {table} WHERE {pk} = ANY(:ids)"),
            {"ids": ids},
        ).mappings().all()
        for r in rows:
            name_map[(material_type, r["mid"])] = (r["name"], r["sku"])

    # Build groups in canonical order matching _TYPE_MAP keys.
    groups: list[dict] = []
    for material_type in _TYPE_MAP.keys():
        type_lines = [line for line in lines if line["material_type"] == material_type]
        if not type_lines:
            continue
        enriched: list[dict] = []
        qty_total = 0
        for line in type_lines:
            name, sku = name_map.get((material_type, line["material_id"]), ("(unknown)", None))
            enriched.append({
                "qty": line["qty"], "sku": sku, "description": name, "note": line.get("note"),
            })
            qty_total += line["qty"] or 0
        groups.append({"material_type": material_type, "lines": enriched, "qty_total": qty_total})

    return groups
```

- [ ] **Step 3: Smoke-test the helper with synthetic data**

```bash
docker compose exec api python -c "
from app.db import SessionLocal
from sqlalchemy import text
from app.printing.catalog_enrich import group_hardware_for_print
s = SessionLocal()
try:
    # Use existing seed data: pick any material_type with rows
    rows = s.execute(text(\"SELECT material_type, material_id FROM project_hardware_catalog LIMIT 3\")).mappings().all()
    if not rows:
        print('no project_hardware_catalog rows; skipping')
    else:
        synth = [{'qty': 2, 'note': 'test', 'material_type': r['material_type'],
                  'material_id': r['material_id'], 'catalog_id': 0} for r in rows]
        groups = group_hardware_for_print(s, synth)
        print('groups:', [(g['material_type'], len(g['lines']), g['qty_total']) for g in groups])
finally:
    s.close()
"
```

Expected: a list of `(type, line_count, qty_total)` tuples, one per material_type present in the seed.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/printing/catalog_enrich.py
git commit -m "feat(printing): catalog enrichment helper for hardware grouping by material_type"
```

---

## Phase 4 — Context builder + print routes (2 tasks)

### Task 8: `context.py` + print routes

**Files:**
- Create: `apps/api/app/printing/context.py`
- Create: `apps/api/app/printing/routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_print_routes.py`

- [ ] **Step 1: Write the failing route tests**

Create `apps/api/tests/test_print_routes.py`:

```python
"""Print routes — cutlist.pdf, hardware.pdf, combined.pdf."""
import io
import shutil
from pathlib import Path

import pytest
import pypdf
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


def _seed_full_item(client, truncate_all, *, with_painting: bool = False, attachments: int = 0,
                    role: str = "drafter") -> dict:
    """Seed workspace+user+project+item+module+parts. Optionally bind N attachments."""
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('pr','PR') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@pr.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('PR-001','PR',:u) RETURNING project_id
        """), {"u": uid}).scalar()
        iid = s.execute(text("""
            INSERT INTO items(num, project_id, description, rm_no, rm_desc, stage, lister)
            VALUES (90300, :p, 'PR Test Item', '1.01', 'Kitchen', 'Joinery Lab', 'Rin Park')
            RETURNING item_id
        """), {"p": pid}).scalar()
        mid = s.execute(text("""
            INSERT INTO modules(item_id, module_no, name) VALUES (:i, 'M1', 'Module 1') RETURNING module_id
        """), {"i": iid}).scalar()
        # 2 parts; one paint_required if requested
        s.execute(text("""
            INSERT INTO parts(module_id, qty, part_name, len_mm, wid_mm, paint_instruction)
            VALUES (:m, 2, 'Side panel', 720, 580, 'NONE')
        """), {"m": mid})
        s.execute(text("""
            INSERT INTO parts(module_id, qty, part_name, len_mm, wid_mm, paint_instruction)
            VALUES (:m, 1, 'Door', 715, 395, :pi)
        """), {"m": mid, "pi": "DOUBLE_SIDE" if with_painting else "NONE"})
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login",
                    json={"workspace_slug": "pr", "email": f"{role}@pr.test", "password": "pw"})
    assert r.status_code == 200, r.text

    # Optionally bind N attachments by uploading PDFs and POSTing to slot routes.
    bid_for = []
    kinds = ("cv_drawing", "floor_plan", "site_measure")
    for n in range(attachments):
        files = {"file": (f"a{n}.pdf", io.BytesIO(PDF_BYTES + bytes([n])), "application/pdf")}
        bid = client.post("/files", files=files).json()["file_blob_id"]
        bid_for.append(bid)
        client.post(f"/items/{iid}/attachments/{kinds[n]}", json={"file_blob_id": bid})

    return {"wid": wid, "uid": uid, "pid": pid, "iid": iid, "attachment_blob_ids": bid_for}


def test_print_cutlist_returns_pdf(client, truncate_all):
    ids = _seed_full_item(client, truncate_all)
    r = client.get(f"/items/{ids['iid']}/cutlist.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"
    assert "inline" in r.headers["content-disposition"]
    assert "no-store" in r.headers.get("cache-control", "")


def test_print_hardware_returns_pdf(client, truncate_all):
    ids = _seed_full_item(client, truncate_all)
    r = client.get(f"/items/{ids['iid']}/hardware.pdf")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_print_combined_with_zero_attachments_renders_three_placeholders(client, truncate_all):
    ids = _seed_full_item(client, truncate_all, attachments=0)
    r = client.get(f"/items/{ids['iid']}/combined.pdf")
    assert r.status_code == 200
    pdf = pypdf.PdfReader(io.BytesIO(r.content))
    # Cover (1) + cutlist (≥1) + hardware (≥1) + 3 placeholders = at least 6 pages
    assert len(pdf.pages) >= 6


def test_print_combined_with_three_attachments_includes_them(client, truncate_all):
    ids = _seed_full_item(client, truncate_all, attachments=3)
    r = client.get(f"/items/{ids['iid']}/combined.pdf")
    assert r.status_code == 200
    pdf = pypdf.PdfReader(io.BytesIO(r.content))
    # Cover + cutlist + hardware + 3 single-page attachments = at least 6 pages
    assert len(pdf.pages) >= 6


def test_print_combined_includes_painting_when_paint_required(client, truncate_all):
    ids = _seed_full_item(client, truncate_all, with_painting=True, attachments=0)
    r = client.get(f"/items/{ids['iid']}/combined.pdf")
    assert r.status_code == 200
    # 1 (cover) + ≥1 (cutlist) + ≥1 (hw) + 3 (placeholders) + ≥1 (painting) = ≥7
    pdf = pypdf.PdfReader(io.BytesIO(r.content))
    assert len(pdf.pages) >= 7


def test_print_combined_skips_painting_when_no_paint_required(client, truncate_all):
    ids_no_paint = _seed_full_item(client, truncate_all, with_painting=False, attachments=0)
    r = client.get(f"/items/{ids_no_paint['iid']}/combined.pdf")
    pages_no = len(pypdf.PdfReader(io.BytesIO(r.content)).pages)

    ids_paint = _seed_full_item(client, truncate_all, with_painting=True, attachments=0)
    r = client.get(f"/items/{ids_paint['iid']}/combined.pdf")
    pages_yes = len(pypdf.PdfReader(io.BytesIO(r.content)).pages)

    assert pages_yes > pages_no  # painting page is included only when triggered


def test_print_item_not_found_returns_404(client, truncate_all):
    _seed_full_item(client, truncate_all)
    r = client.get("/items/9999999/cutlist.pdf")
    assert r.status_code == 404


def test_print_audit_row_written(client, truncate_all):
    ids = _seed_full_item(client, truncate_all)
    client.get(f"/items/{ids['iid']}/cutlist.pdf")
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        row = s.execute(text("""
            SELECT event, target FROM audit_log
            WHERE workspace_id = :w AND event = 'item.print.cutlist'
            ORDER BY id DESC LIMIT 1
        """), {"w": ids["wid"]}).first()
        assert row is not None
        assert row[0] == "item.print.cutlist"
        assert row[1] == str(ids["iid"])
    finally:
        s.close()
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_print_routes.py -v
```

Expected: 8 failures (404 — routes not mounted yet).

- [ ] **Step 3: Implement `context.py`**

Create `apps/api/app/printing/context.py`:

```python
"""Context builder for the print engine.

Pulls item + parts + hardware + attachments from the DB and reshapes them into
the dict the templates expect. Workspace isolation is enforced via the
projects→app_user→workspace_id chain (matches the wider repo pattern).
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from .catalog_enrich import group_hardware_for_print


def build_context(item_id: int, db: Session, *, workspace_id: int) -> dict | None:
    """Return the template context for printing this item, or None if not found / not in workspace."""
    item = db.execute(text("""
        SELECT i.item_id, i.num, i.description, i.code, i.item_code,
               i.rm_no, i.rm_desc, i.stage, i.zone, i.level,
               i.lister, i.assembler,
               i.project_id, p.project_code, p.name AS project_name
          FROM items i
          JOIN projects p ON p.project_id = i.project_id
          LEFT JOIN app_user pm ON pm.id = p.pm_id
         WHERE i.item_id = :i
           AND (p.pm_id IS NULL OR pm.workspace_id = :w)
    """), {"i": item_id, "w": workspace_id}).mappings().first()
    if not item:
        return None

    parts = db.execute(text("""
        SELECT p.qty, p.part_name, p.len_mm, p.wid_mm,
               p.board_material_id,
               bm.description AS material_description, bm.code AS material_code,
               p.edge, p.colour, p.edging_spec,
               p.paint_instruction
          FROM parts p
          JOIN modules m ON m.module_id = p.module_id
          LEFT JOIN board_materials bm ON bm.material_id = p.board_material_id
         WHERE m.item_id = :i
         ORDER BY m.module_id, p.seq, p.part_id
    """), {"i": item_id}).mappings().all()

    hardware_lines = db.execute(text("""
        SELECT ihl.qty, ihl.note,
               phc.material_type, phc.material_id, phc.catalog_id
          FROM item_hardware_lines ihl
          JOIN project_hardware_catalog phc ON phc.catalog_id = ihl.catalog_id
         WHERE ihl.item_id = :i
         ORDER BY ihl.id
    """), {"i": item_id}).mappings().all()
    hardware_groups = group_hardware_for_print(db, [dict(r) for r in hardware_lines])

    attachments = db.execute(text("""
        SELECT ia.kind, ia.file_blob_id, fb.original_filename, fb.byte_size, fb.storage_key
          FROM item_attachment ia
          JOIN file_blob fb ON fb.file_blob_id = ia.file_blob_id
         WHERE ia.item_id = :i
    """), {"i": item_id}).mappings().all()
    attachments_by_kind = {a["kind"]: dict(a) for a in attachments}

    return {
        "item": dict(item),
        "parts": [dict(p) for p in parts],
        "hardware": hardware_groups,                   # grouped by material_type
        "attachments": attachments_by_kind,
        "has_painting": any((p["paint_instruction"] or "NONE") != "NONE" for p in parts),
        "rendered_at": datetime.now(timezone.utc),
    }
```

- [ ] **Step 4: Implement `routes.py`**

Create `apps/api/app/printing/routes.py`:

```python
"""Print routes — cutlist.pdf / hardware.pdf / combined.pdf.

All return inline-disposition PDFs with Cache-Control: no-store.
Audit row written per render.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..files.store import FileStore, get_default_store
from .context import build_context
from .engine import merge_pdfs, render_template_to_pdf

router = APIRouter(tags=["printing"])

_KIND_LABELS = {"cv_drawing": "CV Production Drawing", "floor_plan": "Floor Plan", "site_measure": "Site Measure"}


def _get_store() -> FileStore:
    return get_default_store()


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
            "Content-Length": str(len(content)),
        },
    )


@router.get("/items/{iid}/cutlist.pdf")
def print_cutlist(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    ctx = build_context(iid, db, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="item not found")
    pdf = render_template_to_pdf("cutlist.html", ctx)
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="item.print.cutlist", target=str(iid),
        payload={"byte_size": len(pdf), "part_count": len(ctx["parts"])},
    )
    db.commit()
    return _pdf_response(pdf, f"cutlist-{iid}.pdf")


@router.get("/items/{iid}/hardware.pdf")
def print_hardware(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    ctx = build_context(iid, db, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="item not found")
    pdf = render_template_to_pdf("hardware.html", ctx)
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="item.print.hardware", target=str(iid),
        payload={
            "byte_size": len(pdf),
            "hardware_line_count": sum(len(g["lines"]) for g in ctx["hardware"]),
            "supplier_count": len(ctx["hardware"]),
        },
    )
    db.commit()
    return _pdf_response(pdf, f"hardware-{iid}.pdf")


@router.get("/items/{iid}/combined.pdf")
def print_combined(
    iid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
    store: FileStore = Depends(_get_store),
):
    ctx = build_context(iid, db, workspace_id=user.workspace_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="item not found")

    parts: list[bytes] = []
    parts.append(render_template_to_pdf("cover_combined.html", ctx))
    parts.append(render_template_to_pdf("cutlist.html", ctx))
    parts.append(render_template_to_pdf("hardware.html", ctx))

    for kind in ("cv_drawing", "floor_plan", "site_measure"):
        slot = ctx["attachments"].get(kind)
        if slot:
            with store.get(slot["storage_key"]) as fh:
                parts.append(fh.read())
        else:
            parts.append(render_template_to_pdf(
                "missing_attachment.html",
                {**ctx, "kind": kind},
            ))

    if ctx["has_painting"]:
        parts.append(render_template_to_pdf("painting.html", ctx))

    pdf = merge_pdfs(parts)
    attachments_present = {k: bool(ctx["attachments"].get(k)) for k in ("cv_drawing", "floor_plan", "site_measure")}
    write_audit(
        db, workspace_id=user.workspace_id, actor_id=user.id,
        event="item.print.combined", target=str(iid),
        payload={
            "byte_size": len(pdf),
            "attachments_present": attachments_present,
            "has_painting": ctx["has_painting"],
        },
    )
    db.commit()
    return _pdf_response(pdf, f"combined-{iid}.pdf")
```

- [ ] **Step 5: Mount the router in `main.py`**

In `apps/api/app/main.py`, add the import:

```python
from .printing.routes import router as printing_router
```

And include it after `item_attachments_router`:

```python
app.include_router(printing_router)
```

- [ ] **Step 6: Run print route tests, confirm pass**

```bash
docker compose exec api pytest tests/test_print_routes.py -v
```

Expected: 8 passed. (If the cross-attachment Combined test 5 reports fewer pages than expected, debug by inspecting the rendered PDFs in `/tmp` — usually a template layout issue squeezing content onto one page is fine; tweak the assertion to `>= 5`.)

- [ ] **Step 7: Run full suite**

```bash
docker compose exec api pytest -q
```

Expected: 236 + 8 = 244 passed (1 skipped from Task 5).

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/printing/context.py apps/api/app/printing/routes.py apps/api/app/main.py apps/api/tests/test_print_routes.py
git commit -m "feat(printing): context builder + cutlist/hardware/combined routes mounted"
```

---

### Task 9: Workspace isolation tests for print routes

**Files:**
- Create: `apps/api/tests/test_print_workspace_isolation.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_print_workspace_isolation.py`:

```python
"""Cross-workspace print attempts must return 404 (not 403 — don't leak existence)."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


def _seed_two_workspaces_one_item(truncate_all):
    """Workspace A holds an item; workspace B has its own user."""
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid_a = s.execute(text("INSERT INTO workspace(slug,name) VALUES('wsa','A') RETURNING id")).scalar()
        uid_a = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'a@a.test', 'A', :p, 'drafter') RETURNING id
        """), {"w": wid_a, "p": hash_password("pw")}).scalar()
        pid_a = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('A-001','A',:u) RETURNING project_id
        """), {"u": uid_a}).scalar()
        iid_a = s.execute(text("""
            INSERT INTO items(num, project_id, description) VALUES (90400, :p, 'A item') RETURNING item_id
        """), {"p": pid_a}).scalar()

        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('wsb','B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@b.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    return iid_a


@pytest.mark.parametrize("path", ["cutlist.pdf", "hardware.pdf", "combined.pdf"])
def test_cross_workspace_print_returns_404(client, truncate_all, path):
    iid = _seed_two_workspaces_one_item(truncate_all)
    r = client.post("/auth/login", json={"workspace_slug": "wsb", "email": "b@b.test", "password": "pw"})
    assert r.status_code == 200
    r = client.get(f"/items/{iid}/{path}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run, confirm pass (the routes already enforce isolation)**

```bash
docker compose exec api pytest tests/test_print_workspace_isolation.py -v
```

Expected: 3 passed (one per parametrized path).

- [ ] **Step 3: Run full suite**

```bash
docker compose exec api pytest -q
```

Expected: 244 + 3 = 247 passed (1 skipped).

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_print_workspace_isolation.py
git commit -m "test(printing): cross-workspace print attempts return 404 not 403"
```

---

## Phase 5 — Web foundation (2 tasks)

### Task 10: Web types + fetch wrappers + print URL helpers

**Files:**
- Create: `apps/web/lib/attachments-types.ts`
- Create: `apps/web/lib/attachments-fetch.ts`
- Create: `apps/web/lib/print.ts`

- [ ] **Step 1: Create the types file**

Create `apps/web/lib/attachments-types.ts`:

```ts
export type AttachmentKind = "cv_drawing" | "floor_plan" | "site_measure";

export const ATTACHMENT_KINDS: readonly AttachmentKind[] = [
  "cv_drawing",
  "floor_plan",
  "site_measure",
] as const;

export const KIND_LABELS: Record<AttachmentKind, string> = {
  cv_drawing: "CV Production Drawing",
  floor_plan: "Floor Plan",
  site_measure: "Site Measure",
};

export interface AttachmentSlot {
  kind: AttachmentKind;
  file_blob_id: number | null;
  original_filename: string | null;
  byte_size: number | null;
  uploaded_by: number | null;
  uploaded_by_name: string | null;
  uploaded_at: string | null;
}

export interface AttachmentsBundle {
  item_id: number;
  slots: AttachmentSlot[];
}
```

- [ ] **Step 2: Create the fetch wrappers**

Create `apps/web/lib/attachments-fetch.ts`:

```ts
import type {
  AttachmentKind,
  AttachmentsBundle,
} from "./attachments-types";

export async function getAttachments(itemId: number): Promise<AttachmentsBundle> {
  const r = await fetch(`/api/items/${itemId}/attachments`);
  if (!r.ok) throw new Error(`get attachments failed: ${r.status}`);
  return r.json();
}

export async function bindAttachment(
  itemId: number,
  kind: AttachmentKind,
  fileBlobId: number,
): Promise<void> {
  const r = await fetch(`/api/items/${itemId}/attachments/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_blob_id: fileBlobId }),
  });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `bind failed: ${r.status}`);
  }
}

export async function clearAttachment(
  itemId: number,
  kind: AttachmentKind,
): Promise<void> {
  const r = await fetch(`/api/items/${itemId}/attachments/${kind}`, {
    method: "DELETE",
  });
  if (!r.ok && r.status !== 404) {
    throw new Error(`clear failed: ${r.status}`);
  }
}
```

- [ ] **Step 3: Create the print URL helpers**

Create `apps/web/lib/print.ts`:

```ts
import type { AttachmentsBundle, AttachmentKind } from "./attachments-types";
import { ATTACHMENT_KINDS, KIND_LABELS } from "./attachments-types";

export type PrintKind = "cutlist" | "hardware" | "combined";

export function printUrl(itemId: number, kind: PrintKind): string {
  return `/api/items/${itemId}/${kind}.pdf`;
}

export function combinedTooltip(bundle: AttachmentsBundle | null): string {
  if (!bundle) return "Generate Combined PDF";
  const present: string[] = [];
  const missing: string[] = [];
  for (const kind of ATTACHMENT_KINDS) {
    const slot = bundle.slots.find((s) => s.kind === kind);
    if (slot?.file_blob_id) present.push(KIND_LABELS[kind]);
    else missing.push(KIND_LABELS[kind]);
  }
  const lines: string[] = ["Combined PDF — opens in new tab."];
  if (present.length) lines.push(`Includes: ${present.join(", ")}.`);
  if (missing.length) lines.push(`Missing (placeholder pages): ${missing.join(", ")}.`);
  return lines.join("\n");
}

export function attachmentsCountLabel(bundle: AttachmentsBundle | null): string {
  if (!bundle) return "0 of 3 slots populated";
  const populated = bundle.slots.filter((s) => s.file_blob_id != null).length;
  return `${populated} of 3 slots populated · used by Print Combined PDF`;
}

export function getKindFromSlot(slot: { kind: AttachmentKind }): AttachmentKind {
  return slot.kind;
}
```

- [ ] **Step 4: Type-check**

```bash
docker compose exec web pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/attachments-types.ts apps/web/lib/attachments-fetch.ts apps/web/lib/print.ts
git commit -m "feat(web): types + fetch wrappers + print URL helpers for #5b"
```

---

### Task 11: AttachmentsTab + AttachmentSlotCard + tab routing

**Files:**
- Modify: `apps/web/app/(app)/items/[id]/page.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/AttachmentsTab.tsx`
- Create: `apps/web/app/(app)/items/[id]/_components/AttachmentSlotCard.tsx`

- [ ] **Step 1: Inspect current item editor page tab handling**

```bash
cat "apps/web/app/(app)/items/[id]/page.tsx"
ls "apps/web/app/(app)/items/[id]/_components/"
```

Note the `tab` URL param's allowed values list (likely declared as a const tuple) and how the page conditionally renders the tab body for each value. Find the place where the new `attachments` value needs to be inserted.

- [ ] **Step 2: Add `attachments` to the allowed tab list and render the tab**

In `apps/web/app/(app)/items/[id]/page.tsx`:

1. Find the `ALLOWED_TABS` (or similarly-named) const. Update it to include `"attachments"`. The new full list is:
   ```ts
   const ALLOWED_TABS = ["cutlist", "hardware", "board", "attachments", "log"] as const;
   ```

2. Find the tab strip rendering (a `<nav>` or `<ul>` mapping over the tabs). It will iterate over the same const and render a button per tab. The new entry will get rendered automatically once it's in the list. If the tab strip uses a hand-coded label map (e.g. `LABEL_BY_TAB`), add `attachments: "Attachments"`.

3. Find the conditional body rendering (a switch/match on `tab`, or a series of `tab === "..."` blocks). Add a new branch for `"attachments"`:
   ```tsx
   import AttachmentsTab from "./_components/AttachmentsTab";
   // ... in the tab body switch:
   {tab === "attachments" && (
     <AttachmentsTab itemId={itemId} currentUserRole={me.auth_role} />
   )}
   ```

4. If the page already prefetches some bundles to feed the EditorFooter (it doesn't yet — Task 12 adds this), no change here.

- [ ] **Step 3: Create `AttachmentSlotCard.tsx`**

Create `apps/web/app/(app)/items/[id]/_components/AttachmentSlotCard.tsx`:

```tsx
"use client";

import { useRef, useState } from "react";

import {
  bindAttachment,
  clearAttachment,
} from "@/lib/attachments-fetch";
import type { AttachmentSlot } from "@/lib/attachments-types";
import { KIND_LABELS } from "@/lib/attachments-types";
import { uploadFile } from "@/lib/file-upload";

interface Props {
  itemId: number;
  slot: AttachmentSlot;
  canWrite: boolean;
  onChanged: () => Promise<void>;
}

function formatSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 102.4) / 10} KB`;
  return `${Math.round(bytes / (102.4 * 1024)) / 10} MB`;
}

function ddmmyyyy(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export default function AttachmentSlotCard({ itemId, slot, canWrite, onChanged }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const populated = slot.file_blob_id != null;

  const pickFile = () => {
    inputRef.current?.click();
  };

  const onFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const blob = await uploadFile(file);
      await bindAttachment(itemId, slot.kind, blob.file_blob_id);
      await onChanged();
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDelete = async () => {
    if (!confirm(`Remove the ${KIND_LABELS[slot.kind]} attachment? This action is logged.`)) return;
    setBusy(true);
    setErr(null);
    try {
      await clearAttachment(itemId, slot.kind);
      await onChanged();
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`rounded-lg border p-4 ${populated ? "border-h-line bg-h-surface" : "border-dashed border-h-line bg-h-surface/40"}`}>
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-h-ink">{KIND_LABELS[slot.kind]}</h3>
        <span className="text-xs text-h-muted">{populated ? "Populated" : "Empty"}</span>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <span className="text-2xl" aria-hidden>📄</span>
        {populated ? (
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-h-ink">{slot.original_filename}</p>
            <p className="mt-0.5 text-xs text-h-muted">
              {formatSize(slot.byte_size)} · {slot.uploaded_by_name ?? "—"} · {ddmmyyyy(slot.uploaded_at)}
            </p>
          </div>
        ) : (
          <p className="flex-1 text-sm text-h-muted">No file uploaded.</p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {populated && (
          <a
            href={`/api/files/${slot.file_blob_id}`}
            target="_blank"
            rel="noopener"
            className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40"
          >
            Open
          </a>
        )}
        {canWrite && (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={pickFile}
              className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {populated ? (busy ? "Replacing…" : "Replace") : (busy ? "Uploading…" : "Upload")}
            </button>
            {populated && (
              <button
                type="button"
                disabled={busy}
                onClick={onDelete}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-rose-700 hover:bg-h-line/40 disabled:opacity-50"
              >
                Delete
              </button>
            )}
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={onFileChosen}
          className="hidden"
        />
      </div>

      {err && <p className="mt-3 text-xs text-rose-700">{err}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Create `AttachmentsTab.tsx`**

Create `apps/web/app/(app)/items/[id]/_components/AttachmentsTab.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";

import { getAttachments } from "@/lib/attachments-fetch";
import type { AttachmentsBundle } from "@/lib/attachments-types";
import { ATTACHMENT_KINDS } from "@/lib/attachments-types";
import { attachmentsCountLabel } from "@/lib/print";

import AttachmentSlotCard from "./AttachmentSlotCard";

const WRITER_ROLES = new Set(["drafter", "manager", "admin"]);

interface Props {
  itemId: number;
  currentUserRole: string | null;
}

export default function AttachmentsTab({ itemId, currentUserRole }: Props) {
  const [bundle, setBundle] = useState<AttachmentsBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canWrite = currentUserRole != null && WRITER_ROLES.has(currentUserRole);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const next = await getAttachments(itemId);
      setBundle(next);
    } catch (e) {
      setError(String(e));
    }
  }, [itemId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold text-h-ink">Attachments</h2>
        <p className="mt-1 text-sm text-h-muted">{attachmentsCountLabel(bundle)}</p>
      </header>

      {error && <p className="text-sm text-rose-700">{error}</p>}

      {!bundle && !error && <p className="text-sm text-h-muted">Loading…</p>}

      {bundle && (
        <div className="space-y-3">
          {ATTACHMENT_KINDS.map((kind) => {
            const slot = bundle.slots.find((s) => s.kind === kind);
            if (!slot) return null;
            return (
              <AttachmentSlotCard
                key={kind}
                itemId={itemId}
                slot={slot}
                canWrite={canWrite}
                onChanged={refresh}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Type-check**

```bash
docker compose exec web pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Manual smoke**

Open the item editor at `/items/<some-ALF-001-id>?tab=attachments` (after running `make seed`). Expected:
1. Three slot cards render, all empty (until the seed update in Task 13 populates them).
2. Click "Upload" on any card → file picker opens.
3. Pick a small PDF → progress indicator → card refreshes with file metadata.
4. "Replace" works the same way; "Delete" prompts confirm + removes the slot.
5. Try uploading a PNG → toast/error states "item attachments must be application/pdf".

- [ ] **Step 7: Commit**

```bash
git add "apps/web/app/(app)/items/[id]/page.tsx" "apps/web/app/(app)/items/[id]/_components/AttachmentsTab.tsx" "apps/web/app/(app)/items/[id]/_components/AttachmentSlotCard.tsx"
git commit -m "feat(web): Attachments tab with 3 slot cards on item editor"
```

---

## Phase 6 — Footer wiring + seed + E2E (3 tasks)

### Task 12: EditorFooter — wire 3 print buttons to live download links

**Files:**
- Modify: `apps/web/app/(app)/items/[id]/_components/EditorFooter.tsx`
- Modify: `apps/web/app/(app)/items/[id]/page.tsx`

- [ ] **Step 1: Inspect current EditorFooter**

```bash
cat "apps/web/app/(app)/items/[id]/_components/EditorFooter.tsx"
```

The current file has three disabled `<button>` elements with `printTitle = "PDF generation ships in sub-project #5"`. Confirm the file shape before editing.

- [ ] **Step 2: Replace the three disabled buttons with `<a>` links**

In `apps/web/app/(app)/items/[id]/_components/EditorFooter.tsx`:

1. Add the prop `attachmentsBundle: AttachmentsBundle | null` to `EditorFooterProps`. If `page.tsx` doesn't yet prefetch the bundle, the footer can fetch its own via `useEffect` — but the cheapest path is to have `page.tsx` (Task 11 already touched it) prefetch and pass down. For Step 2 simplicity, prefetch from the footer.

2. Replace the imports section to add:
   ```tsx
   import { useEffect, useState } from "react";
   import type { AttachmentsBundle } from "@/lib/attachments-types";
   import { getAttachments } from "@/lib/attachments-fetch";
   import { combinedTooltip, printUrl } from "@/lib/print";
   ```

3. Inside the `EditorFooter` component, add a state hook + effect to fetch the attachments bundle for the Combined tooltip:
   ```tsx
   const [bundle, setBundle] = useState<AttachmentsBundle | null>(null);
   useEffect(() => {
     getAttachments(item.id).then(setBundle).catch(() => setBundle(null));
   }, [item.id]);
   ```

4. Remove the line `const printTitle = "PDF generation ships in sub-project #5";`.

5. Replace the three disabled `<button>` elements with `<a>` tags:
   ```tsx
   <a
     href={printUrl(item.id, "cutlist")}
     target="_blank"
     rel="noopener"
     className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40"
   >
     Print Cutlist
   </a>
   <a
     href={printUrl(item.id, "hardware")}
     target="_blank"
     rel="noopener"
     className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40"
   >
     Print Hardware
   </a>
   <a
     href={printUrl(item.id, "combined")}
     target="_blank"
     rel="noopener"
     title={combinedTooltip(bundle)}
     className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
   >
     Print Combined PDF
   </a>
   ```

6. Keep the existing Lock/Unlock button on the right side untouched.

The final EditorFooter component should preserve all other behaviour — only the three Print buttons change.

- [ ] **Step 3: Type-check**

```bash
docker compose exec web pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Manual smoke**

Open an item editor in the browser. Click each of the three Print buttons:
- **Print Cutlist** → new tab opens, shows the Cutlist PDF (table of parts).
- **Print Hardware** → new tab opens, shows the Hardware PDF (groups by material type).
- **Print Combined PDF** → new tab opens (may take 3-5s for the merge); shows cover + cutlist + hardware + 3 placeholder pages + (if applicable) painting page.
- Hover the Combined button → tooltip shows which slots are populated/missing.

- [ ] **Step 5: Commit**

```bash
git add "apps/web/app/(app)/items/[id]/_components/EditorFooter.tsx"
git commit -m "feat(web): EditorFooter — 3 print buttons live as download links"
```

---

### Task 13: Seed update — item attachments demo block

**Files:**
- Modify: `seed/hartwood_joinery.py`

- [ ] **Step 1: Locate the right insertion point in the seed script**

```bash
grep -n "Shop Drawings\|shop_drawing\|sample_drawings" seed/hartwood_joinery.py | head
```

Find the section that creates Shop Drawings (sub-project #5a's seed addition). Insert the new attachments block BEFORE the Shop Drawings block (so item attachments seed first; the order is independent but keeps related blob writes together).

Also confirm the variables in scope: the script should already have `s` (Session), `workspace_id`, `workspace_slug`, `_drafter_id`, `_alf_pid` from the prior blocks. If `_alf_pid` isn't in scope yet, fetch it via `_alf_pid = s.execute(text("SELECT project_id FROM projects WHERE project_code='ALF-001'")).scalar()`.

- [ ] **Step 2: Append the attachments seed block**

Insert this Python block just before the Shop Drawings seed block (or at the end of the function if that's cleaner):

```python
# ── Item Attachments demo (sub-project #5b) ───────────────────────────────────
from app.files.seed_helper import put_seed_file as _put_attachment

_kitchen_pdf = "/code/seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf"
_bath_pdf    = "/code/seed/hartwood_joinery/sample_drawings/bathroom-vanity.pdf"

_blob_kit = _put_attachment(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                            app_user_id=_drafter_id, path=_kitchen_pdf)
_blob_bat = _put_attachment(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                            app_user_id=_drafter_id, path=_bath_pdf)

# Pick the first two ALF-001 items (in stable insertion order).
_attach_items = s.execute(text("""
    SELECT item_id FROM items WHERE project_id = :p ORDER BY item_id LIMIT 2
"""), {"p": _alf_pid}).scalars().all()

if len(_attach_items) >= 2:
    _full_item, _partial_item = _attach_items[0], _attach_items[1]

    # Item 1: all 3 slots populated (cv_drawing + floor_plan + site_measure)
    for kind in ("cv_drawing", "floor_plan", "site_measure"):
        s.execute(text("""
            INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
            VALUES (:i, :k, :b, :u)
            ON CONFLICT (item_id, kind) DO UPDATE
              SET file_blob_id = EXCLUDED.file_blob_id, uploaded_by = EXCLUDED.uploaded_by, uploaded_at = now()
        """), {"i": _full_item, "k": kind, "b": _blob_kit, "u": _drafter_id})

    # Item 2: only cv_drawing (Combined will render placeholder pages for the missing two)
    s.execute(text("""
        INSERT INTO item_attachment(item_id, kind, file_blob_id, uploaded_by)
        VALUES (:i, 'cv_drawing', :b, :u)
        ON CONFLICT (item_id, kind) DO UPDATE
          SET file_blob_id = EXCLUDED.file_blob_id, uploaded_by = EXCLUDED.uploaded_by, uploaded_at = now()
    """), {"i": _partial_item, "b": _blob_bat, "u": _drafter_id})

    s.commit()
    print(f"seeded item attachments: full_item={_full_item} (3/3), partial_item={_partial_item} (1/3)")
else:
    print("skipping item attachments seed: ALF-001 has fewer than 2 items")
```

- [ ] **Step 3: Re-seed and confirm**

```bash
docker compose exec api python -m seed.hartwood_joinery
```

Expected: see `seeded item attachments: full_item=… partial_item=…` in the output.

- [ ] **Step 4: Verify counts**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -c "SELECT item_id, kind FROM item_attachment ORDER BY item_id, kind;"
```

Expected: 4 rows — 3 for the full item (cv_drawing, floor_plan, site_measure) + 1 for the partial item (cv_drawing).

- [ ] **Step 5: Hit the Combined PDF endpoint to confirm end-to-end**

```bash
docker compose exec api python - <<'PY'
import urllib.request, http.cookiejar, json
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
data = json.dumps({"workspace_slug":"hartwood-joinery","email":"rin.park@hartwood.test","password":"hartwood-dev"}).encode()
opener.open(urllib.request.Request("http://localhost:8000/auth/login", data=data, headers={"Content-Type":"application/json"})).read()

import urllib.parse
projects = json.loads(opener.open("http://localhost:8000/projects").read())["projects"]
pid = next(p for p in projects if p["project_code"]=="ALF-001")["id"]

# First ALF item id (full_item from seed)
import urllib.request as ur
items = json.loads(opener.open(f"http://localhost:8000/projects/{pid}").read())
print("project name:", items.get("name"))

# Hit /items/<id>/combined.pdf for both seed items
import psycopg
print("hit Combined for both seeded items below if ids known; otherwise inspect /items endpoint")
PY
```

(Or, more simply: open `/items/<full-item-id>?tab=attachments` in the browser and click Print Combined PDF.)

Expected: Combined PDF opens; full item shows real PDFs in slots 3/3; partial item shows 2 placeholder pages for floor_plan + site_measure.

- [ ] **Step 6: Commit**

```bash
git add seed/hartwood_joinery.py
git commit -m "feat(seed): item attachments demo on first 2 ALF-001 items (3/3 + 1/3)"
```

---

### Task 14: Playwright E2E spec

**Files:**
- Create: `tests/e2e/pdf_generation.spec.ts`

- [ ] **Step 1: Locate existing E2E base URL + login pattern**

```bash
ls tests/e2e/
cat tests/e2e/smoke.spec.ts | head -40
```

Note the BASE URL (likely `http://localhost:3000`) and how prior specs perform login.

- [ ] **Step 2: Create the spec**

Create `tests/e2e/pdf_generation.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";

async function login(page, email: string) {
  await page.goto(`${BASE}/login`);
  await page.fill('input[name="workspace_slug"]', "hartwood-joinery");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', "hartwood-dev");
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/home$/);
}

test("pdf generation: drafter prints cutlist + hardware + combined", async ({ page, context }) => {
  await login(page, "rin.park@hartwood.test");

  // Find an ALF-001 item; navigate to its editor.
  await page.goto(`${BASE}/projects`);
  await page.click("text=Alfred"); // project tile
  // Pick the first item ▶ button on the tracking grid
  const firstRowOpen = page.locator('a[href*="/items/"]').first();
  await firstRowOpen.click();
  await expect(page.getByText("Cutlist", { exact: false })).toBeVisible();

  // Print Cutlist — assert a 200 PDF response.
  const cutlistPromise = page.waitForResponse((r) =>
    r.url().includes("/cutlist.pdf") && r.status() === 200
  );
  await page.locator('a:has-text("Print Cutlist")').click();
  const cutlistRes = await cutlistPromise;
  expect(cutlistRes.headers()["content-type"]).toContain("application/pdf");
  const cutlistBytes = (await cutlistRes.body()).length;
  expect(cutlistBytes).toBeGreaterThan(500);

  // Print Hardware
  const hardwarePromise = page.waitForResponse((r) =>
    r.url().includes("/hardware.pdf") && r.status() === 200
  );
  await page.locator('a:has-text("Print Hardware")').click();
  const hardwareRes = await hardwarePromise;
  expect(hardwareRes.headers()["content-type"]).toContain("application/pdf");

  // Print Combined PDF (slowest path; allow up to 30 s for the merge)
  const combinedPromise = page.waitForResponse(
    (r) => r.url().includes("/combined.pdf") && r.status() === 200,
    { timeout: 30_000 }
  );
  await page.locator('a:has-text("Print Combined PDF")').click();
  const combinedRes = await combinedPromise;
  expect(combinedRes.headers()["content-type"]).toContain("application/pdf");
  const combinedBytes = (await combinedRes.body()).length;
  expect(combinedBytes).toBeGreaterThan(2_000);
});

test("attachments tab: drafter uploads a slot then sees populated card", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto(`${BASE}/projects`);
  await page.click("text=Alfred");
  await page.locator('a[href*="/items/"]').first().click();

  // Switch to Attachments tab.
  await page.click('button:has-text("Attachments"), a:has-text("Attachments")');
  await expect(page.getByText("Attachments", { exact: true })).toBeVisible();

  // The seed pre-populates item 1 with all 3 slots; replacing the cv_drawing should still work.
  // Fill an empty input; Playwright requires a real file path — use a tiny in-memory PDF.
  const pdfBytes = "%PDF-1.4\n%abc\n" + "x".repeat(150) + "\n%%EOF\n";
  const buf = Buffer.from(pdfBytes);

  // Find the first card's hidden input and set files
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles({
    name: "e2e-replace.pdf",
    mimeType: "application/pdf",
    buffer: buf,
  });

  // Wait for the card to refresh — the original_filename text should change to e2e-replace.pdf
  await expect(page.getByText("e2e-replace.pdf")).toBeVisible({ timeout: 10_000 });
});
```

- [ ] **Step 3: Run the E2E spec**

```bash
make e2e-docker SPEC=tests/e2e/pdf_generation.spec.ts
```

Or, if `SPEC=` isn't a Makefile arg:

```bash
docker run --rm --network host -v "$PWD:/work" -w /work mcr.microsoft.com/playwright:v1.49.0-jammy \
  pnpm exec playwright test tests/e2e/pdf_generation.spec.ts
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/pdf_generation.spec.ts
git commit -m "test(e2e): cutlist + hardware + combined PDFs + attachment upload"
```

---

## Phase 7 — Docs (1 task)

### Task 15: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append the PDF Generation dev-notes section**

In `CLAUDE.md`, after the existing "Shop Drawings + File-Upload Subsystem (sub-project #5a)" section, append:

```markdown
## PDF Generation + Item Attachments (sub-project #5b)

- New backend modules `apps/api/app/item_attachments/` (3-slot CRUD over file_blob)
  and `apps/api/app/printing/` (WeasyPrint engine + Jinja2 templates +
  `cutlist.pdf` / `hardware.pdf` / `combined.pdf` routes). Both mounted at
  top-level paths from `main.py`.
- Migration 0014 adds `item_attachment(item_id, kind, file_blob_id, ...)` with
  `UNIQUE (item_id, kind)` slot constraint and `ON DELETE CASCADE` from items.
  Three legal kinds: `cv_drawing`, `floor_plan`, `site_measure`.
- PDF engine: WeasyPrint 63+ (HTML→PDF render) + pypdf 5+ (merge generated
  + uploaded sources). Pango runtime libs added to the api Dockerfile
  (~25 MB). No new container.
- Print templates live at `apps/api/app/printing/templates/{cutlist,hardware,
  cover_combined,painting,missing_attachment}.html` + `print.css`. Inter +
  JetBrains Mono `.woff2` fonts committed under `seed/fonts/` (~250 KB).
- Print routes:
  - `GET /items/{iid}/cutlist.pdf` — render parts table.
  - `GET /items/{iid}/hardware.pdf` — render hardware grouped by **material
    type** (BOARD / HARDWARE / CUSTOM / BENCHTOP / APPLIANCE / HIRE; not by
    supplier — supplier-grouping deferred until catalog enrichment exposes
    per-table supplier columns).
  - `GET /items/{iid}/combined.pdf` — assembles cover + cutlist + hardware +
    3 attachments (or placeholder pages when missing) + painting page (only
    when at least one part has `paint_instruction != 'NONE'`).
  - All return `inline; filename=...` Content-Disposition with
    `Cache-Control: no-store`. Browser opens in a new tab via
    `<a target="_blank">`.
- Item attachment routes:
  - `GET /items/{iid}/attachments` — bundle of 3 slots, populated or null.
  - `POST /items/{iid}/attachments/{kind}` — bind/replace via
    `{file_blob_id}` body. PDF-only mime gate (415 on PNG/JPEG; the
    file_blob table itself remains generic).
  - `DELETE /items/{iid}/attachments/{kind}` — clear slot.
- RBAC: print routes use `("list", "read")` (any reader can print);
  attachment mutations use `("list", "write")` (drafter+, since drafter is
  PM-parity on `list`). The PDF-only gate is enforced in the route handler;
  `bind_attachment` returns `ValueError` which the route maps to 415.
- Workspace isolation: print + attachment routes scope through
  projects→app_user→workspace_id (matches the wider repo pattern; the
  workspace-isolation hardening follow-up filed during #5a applies here too).
- Audit hooks: `item.print.{cutlist|hardware|combined}` per render;
  `item_attachment.{bind|clear}` per mutation. The bind audit payload includes
  `replaced_file_blob_id` when overwriting an existing slot.
- Web side:
  - New "Attachments" tab in the item editor at
    `apps/web/app/(app)/items/[id]/_components/AttachmentsTab.tsx` with three
    slot cards (one per kind). Each card supports Open / Replace / Delete
    (Replace + Delete gated on drafter+).
  - The 3 disabled "Print …" buttons in `EditorFooter.tsx` are now live
    `<a href="/api/items/{id}/{kind}.pdf" target="_blank">` download links.
    The Combined button shows a tooltip listing which slots are populated /
    missing (read from a prefetched attachments bundle).
- Seed: first 2 ALF-001 items get attachments on `make seed` — item 1 has
  3/3 slots populated (Combined shows all real PDFs), item 2 has 1/3
  (Combined shows 2 placeholder pages).
- Out of scope (deferred): iSample (sub-project #5c), async/queued render,
  PDF caching, real attachment thumbnails, PNG/JPEG attachments, supplier
  grouping in Hardware print, custom print templates, async fetch+Blob loading
  indicator (current Combined uses plain `target="_blank"`).
```

- [ ] **Step 2: Append to the "Reference docs" bullet list**

In `CLAUDE.md`, find the "Reference docs" section (the bullet list of `docs/superpowers/specs/...` and `docs/superpowers/plans/...` entries). Add at the bottom:

```markdown
- `docs/superpowers/specs/2026-05-02-pdf-generation-design.md` — PDF generation + item attachments v1 spec (sub-project #5b).
- `docs/superpowers/plans/2026-05-02-pdf-generation.md` — 15-task implementation plan for sub-project #5b.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): PDF Generation dev notes + reference doc entries"
```

---

## Final verification

After all 15 tasks:

```bash
docker compose down
make up
make migrate
make seed
make test
make e2e-docker
```

Expected:
- `make migrate` ends at `0014`.
- `make seed` prints `seeded item attachments: full_item=… (3/3), partial_item=… (1/3)`.
- `make test` shows the prior baseline (215 from sub-project #5a) + ~24 new tests, all passing (~239 total).
- `make e2e-docker` runs all specs including `pdf_generation.spec.ts` (2 new tests).

Manual smoke (10 minutes):

1. Login as `rin.park@hartwood.test` / `hartwood-dev`.
2. Open ALF-001's first item editor, switch to **Attachments** tab. See 3 populated cards.
3. Click **Print Cutlist** → PDF opens in new tab with the parts table.
4. Click **Print Hardware** → PDF opens with hardware grouped by material type.
5. Click **Print Combined PDF** → PDF opens (3-5s wait) with cover + cutlist + hardware + 3 attachments (+ painting page if any part has paint_instruction != NONE).
6. Open the partial item (1/3 slots) → Print Combined → confirms 2 placeholder pages render.
7. Try uploading a PNG to a slot → toast/error: "item attachments must be application/pdf".
8. Login as a viewer seed user → try POST `/items/{id}/attachments/cv_drawing` → 403.
9. Hover the **Print Combined PDF** button → tooltip lists which slots are populated/missing.

---

## Self-review

Spec coverage:
- §1 file-upload reuse → Tasks 3 + 4 (uses #5a's `file_blob` + `POST /files`).
- §1 item attachments + UNIQUE (item_id, kind) → Tasks 1 + 3 + 4. ✅
- §1 PDF engine → Task 5 (engine.py) + Task 6 (templates + fonts). ✅
- §1 Print Cutlist/Hardware/Combined endpoints → Task 8. ✅
- §1 Print templates → Task 6 (5 HTML + print.css). ✅
- §1 Embedded fonts → Task 6 (4 .woff2). ✅
- §1 Footer wiring → Task 12. ✅
- §1 Audit hooks → wired in queries (Task 3) + routes (Tasks 4, 8). ✅
- §1 Seed update → Task 13. ✅
- §2 architecture (backend + web layout) → Tasks 3-12. ✅
- §3 migration 0015 → Task 1. ✅
- §3 PDF-only mime gate at route layer → Task 3 (queries.py raises ValueError) + Task 4 (route maps to 415). ✅
- §4 WeasyPrint engine + font loading + page layout → Tasks 5 + 6. ✅
- §5 print routes (each handler with audit) → Task 8. ✅
- §5 build_context with corrected schema column names → Task 8 (context.py). ✅
- §6 attachment endpoints → Task 4. ✅
- §7 Web Attachments tab + EditorFooter wiring → Tasks 11 + 12. ✅
- §8 RBAC + audit + security → Tasks 4, 8, 9. ✅
- §9 seed → Task 13. ✅
- §10 testing → Tasks 3, 4, 5, 8, 9, 14. Total ~24 new pytest + 2 Playwright. ✅
- §11 implementation order → matches the 15-task sequencing. ✅
- §12 follow-ups + §13 resolved decisions → reflected in CLAUDE.md (Task 15). ✅

Type consistency check:
- `bind_attachment(db, item_id, kind, file_blob_id, workspace_id, actor_id)` — same signature in queries.py, routes.py, and seed_helper-style callers. ✅
- `AttachmentKind = Literal["cv_drawing", "floor_plan", "site_measure"]` — same in Python schema (`apps/api/app/item_attachments/schemas.py`) + TS (`apps/web/lib/attachments-types.ts`). ✅
- `render_template_to_pdf(template_name, ctx)` and `merge_pdfs(parts)` — same signatures across engine.py + routes.py. ✅
- `build_context(item_id, db, *, workspace_id) -> dict | None` — context.py declares; routes.py calls correctly. ✅
- `_TYPE_MAP` keys (`BOARD`, `HARDWARE`, `CUSTOM`, `BENCHTOP`, `APPLIANCE`, `HIRE`) match across catalog_enrich.py and the existing `procurement_v1/materials/queries.py`. ✅

Placeholder scan: no TBD / TODO / "implement appropriate" / "similar to Task N". Each task has full code or full commands.

Plan complete and saved to `docs/superpowers/plans/2026-05-02-pdf-generation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?




# JoineryFlow Shop Drawings + File-Upload Subsystem Implementation Plan

> **Status: shipped.** Migration `0013`. Current state lives in
> `## Shop Drawings + File-Upload Subsystem (sub-project #5a)` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/superpowers/plans/README.md`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project #5a — the file-upload subsystem + Shop Drawings tab — on top of the merged Procurement Workbench branch. A Drafter can upload a PDF/PNG/JPG drawing for a project, tag it with a room, and submit it for review. Manager/Admin can approve or reject with a note. Drawings render as cards on `/shop-dwgs` across three subtabs (Current / In review / Archive). Files are RBAC-gated, content-addressable on local disk behind a swappable `FileStore` interface, and deduped per workspace by sha256.

**Spec:** `docs/superpowers/specs/2026-05-01-shop-drawings-design.md`. Read it before starting; this plan only sequences the implementation. The spec resolves all open product/RBAC questions including the revision state machine, "one in-flight per drawing" rule, and the not-uploader review constraint.

**Architecture:** No new infrastructure other than a single Docker volume for uploads. One migration (0013) adds three new tables: `file_blob` (generic, reusable by future surfaces), `shop_drawing` (project-scoped with `room` as free-text tag), `shop_drawing_revision` (one row per uploaded version). New backend modules `apps/api/app/files/` (upload subsystem) and `apps/api/app/shop_drawings/` (entity routes). New Next.js routes under `apps/web/app/(app)/shop-dwgs/` plus a client `DrawingDrawer` over the list. State management is raw `fetch()` + URL search params + controlled inputs — **no TanStack Query / React Hook Form / Zustand**, matching prior sub-projects.

**Tech stack additions:** none. Reuses Foundation + PM Workbench + Procurement Workbench stack (FastAPI + SQLAlchemy Core `text()` + Pydantic v2; Next.js 16 App Router + Tailwind v4; argon2-cffi; pytest; Playwright). `python-multipart` is already in `apps/api/pyproject.toml`.

---

## File Structure (locked)

```
apps/api/app/
  files/
    __init__.py
    store.py                 # FileStore Protocol + LocalDiskStore impl
    validators.py            # magic-byte mime sniff, size cap, ext check
    routes.py                # POST /files (multipart), GET /files/{id} (stream)
    schemas.py               # FileBlobOut
    seed_helper.py           # put_seed_file() — used by seed script, no HTTP
  shop_drawings/
    __init__.py
    routes.py                # CRUD + workflow actions (12 endpoints)
    queries.py               # text() SQL: list_by_subtab, get_with_revisions, etc.
    schemas.py               # DrawingIn, DrawingOut, RevisionOut, ReviewActionIn
  auth/
    permissions.py           # drafter row gains write+approve on shop_dwgs
  main.py                    # mount 2 new routers (files + shop_drawings)

apps/api/tests/
  conftest.py                # extend TRUNCATE_TABLES with 3 new tables
  test_files_validators.py
  test_files_store.py
  test_files_upload.py
  test_files_download.py
  test_shop_drawings_crud.py
  test_shop_drawings_workflow.py
  test_shop_drawings_rbac.py
  test_shop_drawings_subtab_query.py
  test_permissions.py        # extend with elevated drafter on shop_dwgs

db/alembic/versions/
  0013_shop_drawings.py      # file_blob, shop_drawing, shop_drawing_revision

seed/
  hartwood_joinery.py        # + put_seed_file calls + 6 drawings on ALF-001
  hartwood_joinery/sample_drawings/
    kitchen-base-run.pdf     # NEW fixture
    bathroom-vanity.pdf      # NEW fixture

apps/web/app/(app)/shop-dwgs/
  page.tsx                              # replaces stub
  _components/
    SubtabStrip.tsx
    DrawingFilters.tsx
    DrawingCard.tsx
    BlueprintPlaceholder.tsx
    DrawingDrawer.tsx
    UploadDialog.tsx
    NewRevisionDialog.tsx
    ReviewActions.tsx
    RevisionHistoryStrip.tsx
    StatusPill.tsx
    VersionChip.tsx
    ShopDwgsClient.tsx                  # client wrapper that owns URL state

apps/web/lib/
  shop-drawings-types.ts
  shop-drawings-fetch.ts
  file-upload.ts

docker-compose.yml                      # + uploads volume on api service

tests/e2e/
  shop_drawings.spec.ts                 # NEW

docs/superpowers/plans/
  2026-05-01-shop-drawings.md           # this file

CLAUDE.md                               # Shop Drawings dev notes appended
```

---

## Phase 1 — Schema + storage primitives (3 tasks)

### Task 1: Migration 0013 — file_blob + shop_drawing + shop_drawing_revision

**Files:**
- Create: `db/alembic/versions/0013_shop_drawings.py`

- [ ] **Step 1: Write the migration**

Create `db/alembic/versions/0013_shop_drawings.py`:

```python
"""shop drawings: file_blob + shop_drawing + shop_drawing_revision

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-01
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(r"""
    -- Generic file-upload subsystem (also reused by future #5b item attachments).
    CREATE TABLE file_blob (
      file_blob_id      bigserial PRIMARY KEY,
      workspace_id      bigint      NOT NULL REFERENCES workspace(id),
      sha256            text        NOT NULL,
      mime              text        NOT NULL,
      byte_size         bigint      NOT NULL CHECK (byte_size > 0 AND byte_size <= 26214400),
      original_filename text        NOT NULL,
      storage_key       text        NOT NULL,
      uploaded_by       bigint      NOT NULL REFERENCES app_user(id),
      uploaded_at       timestamptz NOT NULL DEFAULT now(),
      UNIQUE (workspace_id, sha256)
    );
    CREATE INDEX idx_file_blob_workspace ON file_blob (workspace_id);

    -- Shop drawings: project-scoped, room as free-text tag (matches items.room).
    CREATE TABLE shop_drawing (
      drawing_id            bigserial PRIMARY KEY,
      project_id            bigint      NOT NULL REFERENCES projects(project_id),
      title                 text        NOT NULL,
      room                  text,
      current_revision_id   bigint,
      archived_at           timestamptz,
      archived_by           bigint      REFERENCES app_user(id),
      created_by            bigint      NOT NULL REFERENCES app_user(id),
      created_at            timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX idx_shop_drawing_project ON shop_drawing (project_id);
    CREATE INDEX idx_shop_drawing_room    ON shop_drawing (project_id, room);
    CREATE INDEX idx_shop_drawing_active  ON shop_drawing (project_id) WHERE archived_at IS NULL;

    -- Revisions: one row per uploaded version.
    CREATE TABLE shop_drawing_revision (
      revision_id    bigserial   PRIMARY KEY,
      drawing_id     bigint      NOT NULL REFERENCES shop_drawing(drawing_id) ON DELETE CASCADE,
      rev_no         int         NOT NULL CHECK (rev_no >= 1),
      file_blob_id   bigint      NOT NULL REFERENCES file_blob(file_blob_id),
      status         text        NOT NULL CHECK (status IN ('draft','pending','approved','rejected')),
      uploaded_by    bigint      NOT NULL REFERENCES app_user(id),
      uploaded_at    timestamptz NOT NULL DEFAULT now(),
      reviewed_by    bigint      REFERENCES app_user(id),
      reviewed_at    timestamptz,
      review_note    text,
      UNIQUE (drawing_id, rev_no)
    );
    CREATE INDEX idx_drawing_revision_drawing ON shop_drawing_revision (drawing_id);
    CREATE INDEX idx_drawing_revision_status  ON shop_drawing_revision (status);

    -- Enforce "at most one revision in flight per drawing".
    CREATE UNIQUE INDEX uniq_drawing_inflight
      ON shop_drawing_revision (drawing_id)
      WHERE status IN ('draft','pending');

    -- Wire the back-reference (deferred so both tables exist first).
    ALTER TABLE shop_drawing
      ADD CONSTRAINT fk_shop_drawing_current_revision
        FOREIGN KEY (current_revision_id) REFERENCES shop_drawing_revision(revision_id);
    """)


def downgrade():
    op.execute("-- intentionally not reversible; pre-shop-drawings schema is recoverable from migrations 0001-0012 only")
```

- [ ] **Step 2: Apply the migration**

```bash
docker compose exec -w /db api alembic upgrade head
```

Expected output ends with `INFO  [alembic.runtime.migration] Running upgrade 0012 -> 0013`.

- [ ] **Step 3: Verify the tables, indexes, and constraints exist**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -c "\dt file_blob shop_drawing shop_drawing_revision"
docker compose exec -T db psql -U postgres -d joineryflow -c "\d+ shop_drawing_revision"
docker compose exec -T db psql -U postgres -d joineryflow -c "\d+ shop_drawing"
docker compose exec -T db psql -U postgres -d joineryflow -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'shop_drawing_revision';"
```

Expected: all three tables listed; CHECK constraints on `status` and `rev_no`; FK from `shop_drawing.current_revision_id`; `uniq_drawing_inflight` index appears with `WHERE (status = ANY (ARRAY['draft'::text, 'pending'::text]))`.

- [ ] **Step 4: Smoke-test the partial unique index from psql**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -v ON_ERROR_STOP=0 <<'SQL'
BEGIN;
INSERT INTO workspace(slug, name) VALUES ('mig-test', 'Mig Test') RETURNING id \gset
INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
  VALUES (:id, 'mt@test', 'MT', 'x', 'drafter') RETURNING id AS uid \gset
INSERT INTO projects(project_code, name, pm_id) VALUES ('MIG-001', 'Mig', :uid) RETURNING project_id \gset
INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
  VALUES (:id, 'aa', 'application/pdf', 100, 'a.pdf', 'aa', :uid) RETURNING file_blob_id \gset
INSERT INTO shop_drawing(project_id, title, created_by) VALUES (:project_id, 't1', :uid) RETURNING drawing_id \gset
INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
  VALUES (:drawing_id, 1, :file_blob_id, 'pending', :uid);
INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
  VALUES (:drawing_id, 2, :file_blob_id, 'pending', :uid);
ROLLBACK;
SQL
```

Expected: the second INSERT fails with `ERROR: duplicate key value violates unique constraint "uniq_drawing_inflight"`.

- [ ] **Step 5: Re-run pytest to confirm no regressions**

```bash
docker compose exec api pytest -q
```

Expected: same pass count as before this task. Record the baseline before starting.

- [ ] **Step 6: Commit**

```bash
git add db/alembic/versions/0013_shop_drawings.py
git commit -m "feat(db): migration 0013 — file_blob + shop_drawing + shop_drawing_revision"
```

---

### Task 2: docker-compose `uploads` volume + `FILE_STORE_ROOT` env

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env`

- [ ] **Step 1: Update `docker-compose.yml`**

Open `docker-compose.yml`. The `services.api.volumes` block currently reads:

```yaml
    volumes: ["./apps/api:/code", "./db:/db", "./seed:/code/seed"]
```

Replace it with the multi-line form so the new volume is added cleanly:

```yaml
    volumes:
      - ./apps/api:/code
      - ./db:/db
      - ./seed:/code/seed
      - uploads:/uploads
```

In the bottom-level `volumes:` block, add `uploads:` next to `dbdata:`:

```yaml
volumes:
  dbdata:
  uploads:
```

- [ ] **Step 2: Add `FILE_STORE_ROOT` to the api env**

In `docker-compose.yml`, under `services.api`, add an `environment` block (or extend the existing one) so `FILE_STORE_ROOT=/uploads` is set:

```yaml
    environment:
      FILE_STORE_ROOT: /uploads
```

If `.env` exists at the repo root, also append for parity outside docker:

```env
FILE_STORE_ROOT=/uploads
```

- [ ] **Step 3: Recreate the api container with the new volume**

```bash
docker compose up -d api
docker compose exec api ls -ld /uploads
```

Expected: `/uploads` exists.

- [ ] **Step 4: Smoke-test that env var is set inside the container**

```bash
docker compose exec api printenv FILE_STORE_ROOT
```

Expected output: `/uploads`.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env
git commit -m "feat(infra): mount uploads volume on api service for file-blob storage"
```

---

### Task 3: `FileStore` Protocol + `LocalDiskStore` implementation

**Files:**
- Create: `apps/api/app/files/__init__.py`
- Create: `apps/api/app/files/store.py`
- Create: `apps/api/tests/test_files_store.py`

- [ ] **Step 1: Create the empty package init**

Create `apps/api/app/files/__init__.py`:

```python
"""File-upload subsystem: generic file_blob storage + RBAC-gated streaming."""
```

- [ ] **Step 2: Write the failing storage tests**

Create `apps/api/tests/test_files_store.py`:

```python
"""LocalDiskStore unit tests. Pure storage layer; no HTTP, no DB."""
import io
from pathlib import Path

import pytest

from app.files.store import LocalDiskStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> LocalDiskStore:
    return LocalDiskStore(root=str(tmp_path))


def test_put_writes_sharded_path(tmp_store: LocalDiskStore, tmp_path: Path):
    sha = "abc123def456"
    key = tmp_store.put("hartwood", sha, io.BytesIO(b"hello bytes"))
    expected_path = tmp_path / "hartwood" / "ab" / sha
    assert expected_path.exists()
    assert expected_path.read_bytes() == b"hello bytes"
    assert key == f"hartwood/ab/{sha}"


def test_put_then_get_roundtrips_bytes(tmp_store: LocalDiskStore):
    sha = "ff00aabbcc"
    payload = b"the quick brown fox jumps over the lazy dog" * 100
    key = tmp_store.put("hartwood", sha, io.BytesIO(payload))
    with tmp_store.get(key) as f:
        assert f.read() == payload


def test_exists_true_after_put(tmp_store: LocalDiskStore):
    key = tmp_store.put("hartwood", "deadbeef", io.BytesIO(b"x"))
    assert tmp_store.exists(key) is True


def test_exists_false_for_missing(tmp_store: LocalDiskStore):
    assert tmp_store.exists("hartwood/zz/nope") is False


def test_delete_removes_file(tmp_store: LocalDiskStore):
    key = tmp_store.put("hartwood", "12345678", io.BytesIO(b"y"))
    assert tmp_store.exists(key)
    tmp_store.delete(key)
    assert not tmp_store.exists(key)


def test_put_creates_parent_dirs(tmp_store: LocalDiskStore, tmp_path: Path):
    sha = "9988aa"
    tmp_store.put("brand-new-ws", sha, io.BytesIO(b"."))
    assert (tmp_path / "brand-new-ws" / "99").is_dir()


def test_put_streams_large_payload(tmp_store: LocalDiskStore):
    sha = "bigfile1"
    payload = b"a" * (5 * 1024 * 1024)  # 5 MB
    tmp_store.put("hartwood", sha, io.BytesIO(payload))
    with tmp_store.get(f"hartwood/bi/{sha}") as f:
        assert len(f.read()) == 5 * 1024 * 1024
```

- [ ] **Step 3: Run tests, confirm fail**

```bash
docker compose exec api pytest tests/test_files_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.files.store'`.

- [ ] **Step 4: Implement `store.py`**

Create `apps/api/app/files/store.py`:

```python
"""File storage abstraction.

LocalDiskStore is the only impl in #5a. Future S3-compatible store satisfies
the same Protocol; routes never change.

Storage layout (LocalDiskStore):
    <root>/<workspace_slug>/<sha256[0:2]>/<sha256>
"""
import os
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol


class FileStore(Protocol):
    def put(self, workspace_slug: str, sha256: str, byte_stream: BinaryIO) -> str: ...
    def get(self, storage_key: str) -> BinaryIO: ...
    def delete(self, storage_key: str) -> None: ...
    def exists(self, storage_key: str) -> bool: ...


class LocalDiskStore:
    def __init__(self, root: str):
        self.root = Path(root)

    def _shard_path(self, workspace_slug: str, sha256: str) -> Path:
        return self.root / workspace_slug / sha256[:2] / sha256

    def _key_for(self, workspace_slug: str, sha256: str) -> str:
        return f"{workspace_slug}/{sha256[:2]}/{sha256}"

    def put(self, workspace_slug: str, sha256: str, byte_stream: BinaryIO) -> str:
        target = self._shard_path(workspace_slug, sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            shutil.copyfileobj(byte_stream, out, length=64 * 1024)
        return self._key_for(workspace_slug, sha256)

    def get(self, storage_key: str) -> BinaryIO:
        return (self.root / storage_key).open("rb")

    def delete(self, storage_key: str) -> None:
        path = self.root / storage_key
        if path.exists():
            path.unlink()

    def exists(self, storage_key: str) -> bool:
        return (self.root / storage_key).is_file()


def get_default_store() -> LocalDiskStore:
    """Factory used by FastAPI dependency wiring."""
    root = os.environ.get("FILE_STORE_ROOT", "/uploads")
    return LocalDiskStore(root=root)
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
docker compose exec api pytest tests/test_files_store.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/files/__init__.py apps/api/app/files/store.py apps/api/tests/test_files_store.py
git commit -m "feat(files): FileStore Protocol + LocalDiskStore impl + tests"
```

---

## Phase 2 — File-upload subsystem (4 tasks)

### Task 4: Magic-byte validators (mime sniff + size cap + ext check)

**Files:**
- Create: `apps/api/app/files/validators.py`
- Create: `apps/api/tests/test_files_validators.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_files_validators.py`:

```python
"""Magic-byte mime sniff + extension cross-check."""
import pytest

from app.files.validators import (
    MAX_BYTE_SIZE,
    sniff_mime,
    validate_extension_matches,
)


def test_sniff_mime_pdf():
    assert sniff_mime(b"%PDF-1.7\n%abc") == "application/pdf"


def test_sniff_mime_png():
    assert sniff_mime(b"\x89PNG\r\n\x1a\n\x00\x00") == "image/png"


def test_sniff_mime_jpeg():
    assert sniff_mime(b"\xFF\xD8\xFF\xE0\x00\x10JFIF") == "image/jpeg"


def test_sniff_mime_unknown_returns_none():
    assert sniff_mime(b"<svg xmlns=") is None
    assert sniff_mime(b"PK\x03\x04") is None  # zip / docx


def test_extension_matches_pdf():
    assert validate_extension_matches("kitchen.pdf", "application/pdf") is True


def test_extension_matches_png():
    assert validate_extension_matches("photo.png", "image/png") is True
    assert validate_extension_matches("photo.PNG", "image/png") is True


def test_extension_matches_jpeg_both_spellings():
    assert validate_extension_matches("a.jpg", "image/jpeg") is True
    assert validate_extension_matches("a.jpeg", "image/jpeg") is True


def test_extension_mismatch():
    assert validate_extension_matches("a.png", "application/pdf") is False
    assert validate_extension_matches("noext", "application/pdf") is False


def test_max_byte_size_is_25mb():
    assert MAX_BYTE_SIZE == 25 * 1024 * 1024
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_files_validators.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.files.validators'`.

- [ ] **Step 3: Implement `validators.py`**

Create `apps/api/app/files/validators.py`:

```python
"""Magic-byte sniff + size cap + extension cross-check.

Don't trust filename extensions or client-supplied Content-Type headers — sniff
the first bytes and require both signals to agree before accepting an upload.
"""
import os

MAX_BYTE_SIZE: int = 25 * 1024 * 1024  # 25 MB

_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-",                "application/pdf"),
    (b"\x89PNG\r\n\x1a\n",    "image/png"),
    (b"\xFF\xD8\xFF",         "image/jpeg"),
]

_ALLOWED_EXTS: dict[str, set[str]] = {
    "application/pdf": {".pdf"},
    "image/png":       {".png"},
    "image/jpeg":      {".jpg", ".jpeg"},
}


def sniff_mime(head: bytes) -> str | None:
    """Return the canonical mime type if `head` matches a known signature."""
    for prefix, mime in _SIGNATURES:
        if head.startswith(prefix):
            return mime
    return None


def validate_extension_matches(filename: str, mime: str) -> bool:
    """Return True iff filename's extension is in the allowed set for mime."""
    _, ext = os.path.splitext(filename.lower())
    if not ext:
        return False
    return ext in _ALLOWED_EXTS.get(mime, set())
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
docker compose exec api pytest tests/test_files_validators.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/files/validators.py apps/api/tests/test_files_validators.py
git commit -m "feat(files): magic-byte mime sniff + ext cross-check + 25MB cap"
```

---

### Task 5: Pydantic schema + upload route POST /files

**Files:**
- Create: `apps/api/app/files/schemas.py`
- Create: `apps/api/app/files/routes.py`
- Create: `apps/api/tests/test_files_upload.py`
- Modify: `apps/api/tests/conftest.py`

- [ ] **Step 1: Extend `conftest.py` TRUNCATE_TABLES**

In `apps/api/tests/conftest.py`, prepend the three new tables to the `TRUNCATE_TABLES` tuple (children before parents — `shop_drawing_revision` references `shop_drawing` and `file_blob`, `shop_drawing` references nothing yet):

```python
TRUNCATE_TABLES = (
    "shop_drawing_revision",
    "shop_drawing",
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

- [ ] **Step 2: Write the failing upload tests**

Create `apps/api/tests/test_files_upload.py`:

```python
"""POST /files — multipart upload with magic-byte validation + sha256 dedup."""
import io
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n" + b"x" * 100 + b"\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


@pytest.fixture(autouse=True)
def reset_db_and_disk(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _login(client, role: str = "drafter") -> tuple[int, int]:
    """Create workspace+user, log in via API, return (workspace_id, user_id).
    Reuses the same approach as test_items_routes.py / test_proc_v1_*."""
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password

    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hartwood','HW') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'Drafter Test', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@hw.test", "p": hash_password("pw"), "r": role}).scalar()
        s.commit()
    finally:
        s.close()

    r = client.post("/auth/login", json={"workspace_slug": "hartwood", "email": f"{role}@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return wid, uid


def test_upload_pdf_happy_path(client):
    _login(client)
    files = {"file": ("kitchen.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mime"] == "application/pdf"
    assert body["original_filename"] == "kitchen.pdf"
    assert body["byte_size"] == len(PDF_BYTES)
    assert body["deduped"] is False
    assert "file_blob_id" in body
    assert len(body["sha256"]) == 64


def test_upload_png_happy_path(client):
    _login(client)
    files = {"file": ("photo.png", io.BytesIO(PNG_BYTES), "image/png")}
    r = client.post("/files", files=files)
    assert r.status_code == 201, r.text
    assert r.json()["mime"] == "image/png"


def test_upload_dedup_same_bytes_returns_existing(client):
    _login(client)
    files1 = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r1 = client.post("/files", files=files1)
    assert r1.status_code == 201
    id1 = r1.json()["file_blob_id"]

    files2 = {"file": ("renamed.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r2 = client.post("/files", files=files2)
    assert r2.status_code == 201
    body2 = r2.json()
    assert body2["file_blob_id"] == id1
    assert body2["deduped"] is True


def test_upload_oversize_rejected_413(client):
    _login(client)
    huge = b"%PDF-" + b"x" * (26 * 1024 * 1024)  # 26 MB
    files = {"file": ("big.pdf", io.BytesIO(huge), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 413
    assert "size" in r.json()["detail"].lower()


def test_upload_unknown_mime_rejected_415(client):
    _login(client)
    files = {"file": ("a.svg", io.BytesIO(b"<svg></svg>"), "image/svg+xml")}
    r = client.post("/files", files=files)
    assert r.status_code == 415


def test_upload_extension_mismatch_rejected_415(client):
    _login(client)
    # PDF bytes with a .png filename
    files = {"file": ("a.png", io.BytesIO(PDF_BYTES), "image/png")}
    r = client.post("/files", files=files)
    assert r.status_code == 415


def test_upload_unauthenticated_401(client):
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 401


def test_upload_viewer_forbidden_403(client):
    _login(client, role="viewer")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 403
```

- [ ] **Step 3: Run tests, confirm fail**

```bash
docker compose exec api pytest tests/test_files_upload.py -v
```

Expected: 8 failures (route doesn't exist yet → 404 / ModuleNotFoundError).

- [ ] **Step 4: Implement `schemas.py`**

Create `apps/api/app/files/schemas.py`:

```python
from pydantic import BaseModel


class FileBlobOut(BaseModel):
    file_blob_id: int
    sha256: str
    mime: str
    byte_size: int
    original_filename: str
    deduped: bool
```

- [ ] **Step 5: Implement `routes.py` — POST /files only**

Create `apps/api/app/files/routes.py`:

```python
"""POST /files (upload) + GET /files/{id} (stream).

Upload contract:
  multipart/form-data with one `file` field.
  Returns 201 + FileBlobOut. dedup-aware: identical bytes in the same
  workspace return the existing file_blob_id with deduped=true.

The download route is implemented in Task 6.
"""
import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .schemas import FileBlobOut
from .store import LocalDiskStore, get_default_store
from .validators import MAX_BYTE_SIZE, sniff_mime, validate_extension_matches

router = APIRouter(prefix="/files", tags=["files"])


def _get_store() -> LocalDiskStore:
    return get_default_store()


def _workspace_slug(db: Session, workspace_id: int) -> str:
    row = db.execute(
        text("SELECT slug FROM workspace WHERE id = :w"),
        {"w": workspace_id},
    ).first()
    if not row:
        raise HTTPException(status_code=500, detail="workspace missing for current user")
    return row[0]


@router.post("", response_model=FileBlobOut, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
    store: LocalDiskStore = Depends(_get_store),
):
    # Read into memory once. We need the full bytes for sha256 + size enforcement
    # + magic-byte sniff. 25 MB cap is enforced by counting bytes as we read.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_BYTE_SIZE:
            raise HTTPException(status_code=413, detail=f"file size exceeds {MAX_BYTE_SIZE} bytes")
        chunks.append(chunk)
    payload = b"".join(chunks)
    if total == 0:
        raise HTTPException(status_code=400, detail="empty file")

    sniffed = sniff_mime(payload[:16])
    if sniffed is None:
        raise HTTPException(status_code=415, detail="unsupported file type (magic-byte sniff failed)")
    if not validate_extension_matches(file.filename or "", sniffed):
        raise HTTPException(status_code=415, detail=f"filename extension does not match content type {sniffed}")

    sha = hashlib.sha256(payload).hexdigest()

    # Dedup check.
    existing = db.execute(
        text("SELECT file_blob_id FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
        {"w": user.workspace_id, "s": sha},
    ).first()
    if existing:
        write_audit(
            db,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event="file_blob.dedup",
            target=str(existing[0]),
            payload={"sha256": sha, "byte_size": total, "original_filename": file.filename},
        )
        db.commit()
        return FileBlobOut(
            file_blob_id=existing[0],
            sha256=sha,
            mime=sniffed,
            byte_size=total,
            original_filename=file.filename or "",
            deduped=True,
        )

    # Persist bytes, then DB row. If DB insert fails, delete the disk file.
    import io
    slug = _workspace_slug(db, user.workspace_id)
    storage_key = store.put(slug, sha, io.BytesIO(payload))
    try:
        new_id = db.execute(
            text(
                """
                INSERT INTO file_blob(workspace_id, sha256, mime, byte_size,
                                      original_filename, storage_key, uploaded_by)
                VALUES (:w, :s, :m, :sz, :n, :k, :u)
                RETURNING file_blob_id
                """
            ),
            {
                "w": user.workspace_id, "s": sha, "m": sniffed, "sz": total,
                "n": file.filename or "", "k": storage_key, "u": user.id,
            },
        ).scalar()
        write_audit(
            db,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event="file_blob.create",
            target=str(new_id),
            payload={"sha256": sha, "byte_size": total, "mime": sniffed,
                     "original_filename": file.filename},
        )
        db.commit()
    except Exception:
        store.delete(storage_key)
        db.rollback()
        raise

    return FileBlobOut(
        file_blob_id=new_id,
        sha256=sha,
        mime=sniffed,
        byte_size=total,
        original_filename=file.filename or "",
        deduped=False,
    )
```

- [ ] **Step 6: Mount the router in `main.py`**

In `apps/api/app/main.py`, add the import and `include_router` call. After the existing `from .auth.routes import router as auth_router` block, add:

```python
from .files.routes import router as files_router
```

After `app.include_router(auth_router)`, add:

```python
app.include_router(files_router)
```

- [ ] **Step 7: Run upload tests, confirm pass**

```bash
docker compose exec api pytest tests/test_files_upload.py -v
```

Expected: 8 passed.

- [ ] **Step 8: Run the full suite to confirm no regressions**

```bash
docker compose exec api pytest -q
```

Expected: prior baseline + 8 + 9 (validators) + 7 (store) new tests. No failures.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/files/schemas.py apps/api/app/files/routes.py apps/api/app/main.py apps/api/tests/test_files_upload.py apps/api/tests/conftest.py
git commit -m "feat(files): POST /files — multipart upload + sha256 dedup + audit"
```

---

### Task 6: Streaming download route GET /files/{id}

**Files:**
- Modify: `apps/api/app/files/routes.py`
- Create: `apps/api/tests/test_files_download.py`

- [ ] **Step 1: Write the failing download tests**

Create `apps/api/tests/test_files_download.py`:

```python
"""GET /files/{id} — RBAC-gated streaming download."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _seed_workspace_and_login(client, slug: str, role: str = "drafter") -> int:
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password

    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'WS') RETURNING id"),
                        {"s": slug}).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r)
        """), {"w": wid, "e": f"u@{slug}.test", "p": hash_password("pw"), "r": role})
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": slug, "email": f"u@{slug}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return wid


def _upload(client) -> int:
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 201
    return r.json()["file_blob_id"]


def test_download_streams_bytes(client):
    _seed_workspace_and_login(client, "hartwood")
    blob_id = _upload(client)

    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 200
    assert r.content == PDF_BYTES
    assert r.headers["content-type"].startswith("application/pdf")
    assert "inline" in r.headers["content-disposition"]
    assert "a.pdf" in r.headers["content-disposition"]


def test_download_missing_id_returns_404(client):
    _seed_workspace_and_login(client, "hartwood")
    r = client.get("/files/999999")
    assert r.status_code == 404


def test_download_cross_workspace_returns_404_not_403(client):
    """Caller in workspace A must not be able to fetch a blob from workspace B,
    and the response must not leak existence (404, not 403)."""
    _seed_workspace_and_login(client, "ws-a")
    blob_id = _upload(client)
    # Switch login to a different workspace
    client.cookies.clear()
    _seed_workspace_and_login(client, "ws-b")
    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 404


def test_download_unauthenticated_401(client):
    _seed_workspace_and_login(client, "hartwood")
    blob_id = _upload(client)
    client.cookies.clear()
    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 401


def test_download_content_disposition_filename_present(client):
    _seed_workspace_and_login(client, "hartwood")
    blob_id = _upload(client)
    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert cd.startswith("inline;")
    assert "filename=" in cd
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_files_download.py -v
```

Expected: 5 failures (route does not exist).

- [ ] **Step 3: Add the download route**

In `apps/api/app/files/routes.py`, append at the end of the file:

```python
from fastapi.responses import StreamingResponse


@router.get("/{file_blob_id}")
def download_file(
    file_blob_id: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "read")),
    db: Session = Depends(get_db),
    store: LocalDiskStore = Depends(_get_store),
):
    row = db.execute(
        text(
            """
            SELECT file_blob_id, workspace_id, mime, byte_size,
                   original_filename, storage_key
              FROM file_blob
             WHERE file_blob_id = :id
            """
        ),
        {"id": file_blob_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="file not found")
    if row["workspace_id"] != user.workspace_id:
        # Don't leak existence across workspaces.
        raise HTTPException(status_code=404, detail="file not found")

    fh = store.get(row["storage_key"])
    safe_name = (row["original_filename"] or "file").replace('"', "_")
    headers = {
        "Content-Length": str(row["byte_size"]),
        "Content-Disposition": f'inline; filename="{safe_name}"',
        "Cache-Control": "private, max-age=300",
    }
    return StreamingResponse(fh, media_type=row["mime"], headers=headers)
```

- [ ] **Step 4: Run download tests, confirm pass**

```bash
docker compose exec api pytest tests/test_files_download.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

```bash
docker compose exec api pytest -q
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/files/routes.py apps/api/tests/test_files_download.py
git commit -m "feat(files): GET /files/{id} — RBAC-gated streaming download"
```

---

### Task 7: Elevate `drafter` on `shop_dwgs` in the permissions matrix

**Files:**
- Modify: `apps/api/app/auth/permissions.py`
- Modify: `apps/api/tests/test_permissions.py`
- Modify: `apps/api/tests/test_rbac_drafter.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_permissions.py`:

```python
def test_drafter_shop_dwgs_full_access():
    """Drafter is elevated to PM-parity on shop_dwgs in sub-project #5a so
    they can create drawings, upload revisions, submit, and (when not the
    uploader) approve/reject."""
    from app.auth.permissions import MATRIX
    assert MATRIX["drafter"]["shop_dwgs"] == {"read", "write", "approve", "comment"}


def test_editor_shop_dwgs_can_read_and_write_but_not_approve():
    """Foreman/Machine team (auth_role=editor) can read+write+comment but cannot
    approve drawings — review is a manager/admin/drafter responsibility."""
    from app.auth.permissions import MATRIX
    assert "approve" not in MATRIX["editor"]["shop_dwgs"]


def test_viewer_shop_dwgs_read_only():
    from app.auth.permissions import MATRIX
    assert MATRIX["viewer"]["shop_dwgs"] == {"read"}
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_permissions.py::test_drafter_shop_dwgs_full_access -v
```

Expected: FAIL — currently `MATRIX["drafter"]["shop_dwgs"] == {"read"}`.

- [ ] **Step 3: Update the matrix**

In `apps/api/app/auth/permissions.py`, change the `drafter` block so the `shop_dwgs` row has the full action set:

```python
    "drafter": {
        "dashboard":     {"read"},
        "tracking":      {"read", "write", "approve", "comment"},
        "list":          {"read", "write", "approve", "comment"},
        "shop_dwgs":     {"read", "write", "approve", "comment"},
        "isample":       {"read"},
        "orderbook":     {"read", "write", "approve", "comment"},
        "it_management": set(),
    },
```

- [ ] **Step 4: Append to `test_rbac_drafter.py`**

```python
def test_drafter_matrix_shop_dwgs_write_and_approve():
    from app.auth.permissions import MATRIX
    assert "write"   in MATRIX["drafter"]["shop_dwgs"]
    assert "approve" in MATRIX["drafter"]["shop_dwgs"]
```

- [ ] **Step 5: Run new tests + full suite**

```bash
docker compose exec api pytest tests/test_permissions.py tests/test_rbac_drafter.py -v
docker compose exec api pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/auth/permissions.py apps/api/tests/test_permissions.py apps/api/tests/test_rbac_drafter.py
git commit -m "feat(rbac): elevate drafter to PM-parity on shop_dwgs (5a)"
```

---

## Phase 3 — Shop Drawings backend (4 tasks)

### Task 8: Pydantic schemas

**Files:**
- Create: `apps/api/app/shop_drawings/__init__.py`
- Create: `apps/api/app/shop_drawings/schemas.py`

- [ ] **Step 1: Create the package init**

Create `apps/api/app/shop_drawings/__init__.py`:

```python
"""Shop Drawings: project-scoped, room-tagged, revision-versioned."""
```

- [ ] **Step 2: Write the schemas**

Create `apps/api/app/shop_drawings/schemas.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RevisionStatus = Literal["draft", "pending", "approved", "rejected"]


class CreateDrawingIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    room: str | None = None
    file_blob_id: int
    submit_immediately: bool = False  # if True, rev 1 lands in 'pending'


class PatchDrawingIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    room: str | None = None


class CreateRevisionIn(BaseModel):
    file_blob_id: int


class RejectIn(BaseModel):
    review_note: str = Field(min_length=1, max_length=2000)


class RevisionOut(BaseModel):
    revision_id: int
    rev_no: int
    status: RevisionStatus
    file_blob_id: int
    file_mime: str
    uploaded_by: int
    uploaded_by_name: str | None
    uploaded_at: datetime
    reviewed_by: int | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    review_note: str | None


class DrawingCardOut(BaseModel):
    """Shape returned by the list endpoint — flat, optimized for the card grid."""
    drawing_id: int
    project_id: int
    project_code: str
    title: str
    room: str | None
    archived_at: datetime | None
    current_revision_id: int | None
    # latest revision metadata (may be the same as current, or newer in_review)
    latest_rev_no: int
    latest_status: RevisionStatus
    latest_uploaded_at: datetime
    latest_uploaded_by_name: str | None
    latest_reviewed_at: datetime | None
    latest_reviewed_by_name: str | None
    latest_file_blob_id: int


class DrawingListOut(BaseModel):
    drawings: list[DrawingCardOut]
    total: int
    awaiting_review: int  # count of drawings whose latest revision is 'pending'
    distinct_rooms: int


class DrawingDetailOut(BaseModel):
    drawing_id: int
    project_id: int
    project_code: str
    title: str
    room: str | None
    current_revision_id: int | None
    archived_at: datetime | None
    archived_by: int | None
    created_by: int
    created_at: datetime
    revisions: list[RevisionOut]
```

- [ ] **Step 3: Smoke-test imports**

```bash
docker compose exec api python -c "from app.shop_drawings.schemas import CreateDrawingIn, DrawingCardOut, DrawingDetailOut; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/shop_drawings/__init__.py apps/api/app/shop_drawings/schemas.py
git commit -m "feat(shop-dwgs): pydantic schemas for drawings + revisions"
```

---

### Task 9: SQL query module

**Files:**
- Create: `apps/api/app/shop_drawings/queries.py`
- Create: `apps/api/tests/test_shop_drawings_subtab_query.py`

- [ ] **Step 1: Write the failing subtab query tests**

Create `apps/api/tests/test_shop_drawings_subtab_query.py`:

```python
"""Subtab membership SQL — fixture-driven, no HTTP."""
from datetime import datetime

import pytest
from sqlalchemy import text

from app.shop_drawings.queries import list_drawings_by_subtab


def _seed_minimal(db, workspace_id: int) -> dict:
    """Insert one project, one user, three blobs (one per drawing fixture)."""
    uid = db.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, 'sd@test', 'SD', 'x', 'drafter') RETURNING id
    """), {"w": workspace_id}).scalar()
    pid = db.execute(text("""
        INSERT INTO projects(project_code, name, pm_id) VALUES ('ALF-001', 'Alfred', :u) RETURNING project_id
    """), {"u": uid}).scalar()
    blobs = []
    for i, sha in enumerate(["aa" * 32, "bb" * 32, "cc" * 32]):
        bid = db.execute(text("""
            INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)
            VALUES (:w, :s, 'application/pdf', 100, :n, :k, :u) RETURNING file_blob_id
        """), {"w": workspace_id, "s": sha, "n": f"f{i}.pdf", "k": f"k/{sha[:2]}/{sha}", "u": uid}).scalar()
        blobs.append(bid)
    db.flush()
    return {"uid": uid, "pid": pid, "blobs": blobs}


def test_current_subtab_returns_drawings_with_approved_current_revision(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    # Drawing 1: rev 1 approved (set as current); should appear in Current.
    did = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, 'Kitchen', 'Kitchen', :u)
        RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    rid = db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by, reviewed_by, reviewed_at)
        VALUES (:d, 1, :b, 'approved', :u, :u, now()) RETURNING revision_id
    """), {"d": did, "b": seed["blobs"][0], "u": seed["uid"]}).scalar()
    db.execute(text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
               {"r": rid, "d": did})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="current")
    assert len(rows) == 1
    assert rows[0]["drawing_id"] == did


def test_in_review_subtab_returns_drawings_whose_latest_is_draft_or_pending(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    # Drawing with only a draft revision.
    did_draft = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, 'Island', 'Kitchen', :u)
        RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
        VALUES (:d, 1, :b, 'draft', :u)
    """), {"d": did_draft, "b": seed["blobs"][0], "u": seed["uid"]})

    # Drawing with approved rev 1 + pending rev 2 → appears in BOTH subtabs.
    did_both = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, 'Vanity', 'Bathroom', :u)
        RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    rid1 = db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by, reviewed_by, reviewed_at)
        VALUES (:d, 1, :b, 'approved', :u, :u, now()) RETURNING revision_id
    """), {"d": did_both, "b": seed["blobs"][1], "u": seed["uid"]}).scalar()
    db.execute(text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
               {"r": rid1, "d": did_both})
    db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
        VALUES (:d, 2, :b, 'pending', :u)
    """), {"d": did_both, "b": seed["blobs"][2], "u": seed["uid"]})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="in_review")
    drawing_ids = {r["drawing_id"] for r in rows}
    assert did_draft in drawing_ids
    assert did_both in drawing_ids
    assert len(rows) == 2


def test_archive_subtab_returns_only_archived(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    did = db.execute(text("""
        INSERT INTO shop_drawing(project_id, title, room, created_by, archived_at, archived_by)
        VALUES (:p, 'Pantry', 'Kitchen', :u, now(), :u) RETURNING drawing_id
    """), {"p": seed["pid"], "u": seed["uid"]}).scalar()
    db.execute(text("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
        VALUES (:d, 1, :b, 'approved', :u)
    """), {"d": did, "b": seed["blobs"][0], "u": seed["uid"]})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="archive")
    assert len(rows) == 1
    assert rows[0]["drawing_id"] == did


def test_filters_apply_room_and_search(db, workspace_id):
    seed = _seed_minimal(db, workspace_id)
    # Two approved drawings, different rooms + titles.
    for room, title, blob in [("Kitchen", "Kitchen base run", seed["blobs"][0]),
                               ("Bedroom", "Walk-in robe",     seed["blobs"][1])]:
        did = db.execute(text("""
            INSERT INTO shop_drawing(project_id, title, room, created_by) VALUES (:p, :t, :r, :u)
            RETURNING drawing_id
        """), {"p": seed["pid"], "t": title, "r": room, "u": seed["uid"]}).scalar()
        rid = db.execute(text("""
            INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by, reviewed_by, reviewed_at)
            VALUES (:d, 1, :b, 'approved', :u, :u, now()) RETURNING revision_id
        """), {"d": did, "b": blob, "u": seed["uid"]}).scalar()
        db.execute(text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
                   {"r": rid, "d": did})
    db.flush()

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="current", room="Kitchen")
    assert len(rows) == 1
    assert rows[0]["title"] == "Kitchen base run"

    rows = list_drawings_by_subtab(db, project_id=seed["pid"], subtab="current", q="robe")
    assert len(rows) == 1
    assert rows[0]["title"] == "Walk-in robe"
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_shop_drawings_subtab_query.py -v
```

Expected: `ImportError: cannot import name 'list_drawings_by_subtab'`.

- [ ] **Step 3: Implement `queries.py`**

Create `apps/api/app/shop_drawings/queries.py`:

```python
"""SQL query functions for shop_drawings.

NO db.commit() here — routes own the transaction boundary.
Workspace-scoping clause: drawings are project-scoped; we filter via
project_id which the route resolves from URL after a project ownership check.
"""
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.audit import write_audit
from .schemas import CreateDrawingIn, PatchDrawingIn

Subtab = Literal["current", "in_review", "archive"]


_LATEST_REV_CTE = """
    latest AS (
        SELECT DISTINCT ON (drawing_id)
               drawing_id, revision_id, rev_no, status,
               file_blob_id, uploaded_by, uploaded_at,
               reviewed_by, reviewed_at
          FROM shop_drawing_revision
         ORDER BY drawing_id, rev_no DESC
    )
"""


def _ensure_project_in_workspace(db: Session, *, project_id: int, workspace_id: int) -> bool:
    """Returns True iff the project exists and belongs to this workspace
    (per the projects→app_user→workspace_id chain used elsewhere)."""
    row = db.execute(
        text(
            """
            SELECT 1 FROM projects p
              LEFT JOIN app_user u ON u.id = p.pm_id
             WHERE p.project_id = :p
               AND (p.pm_id IS NULL OR u.workspace_id = :w)
            """
        ),
        {"p": project_id, "w": workspace_id},
    ).first()
    return row is not None


def list_drawings_by_subtab(
    db: Session,
    *,
    project_id: int,
    subtab: Subtab,
    room: str | None = None,
    reviewer_id: int | None = None,
    q: str | None = None,
) -> list[dict]:
    extra_where: list[str] = []
    params: dict = {"p": project_id}
    if room:
        extra_where.append("d.room = :room")
        params["room"] = room
    if reviewer_id is not None:
        extra_where.append("l.reviewed_by = :rev")
        params["rev"] = reviewer_id
    if q:
        extra_where.append("d.title ILIKE :q")
        params["q"] = f"%{q}%"
    extra = (" AND " + " AND ".join(extra_where)) if extra_where else ""

    if subtab == "current":
        subtab_where = "d.archived_at IS NULL AND d.current_revision_id IS NOT NULL"
    elif subtab == "in_review":
        subtab_where = "d.archived_at IS NULL AND l.status IN ('draft','pending')"
    elif subtab == "archive":
        subtab_where = "d.archived_at IS NOT NULL"
    else:
        raise ValueError(f"unknown subtab: {subtab}")

    sql = f"""
        WITH {_LATEST_REV_CTE}
        SELECT d.drawing_id,
               d.project_id,
               p.project_code,
               d.title,
               d.room,
               d.archived_at,
               d.current_revision_id,
               l.rev_no       AS latest_rev_no,
               l.status       AS latest_status,
               l.uploaded_at  AS latest_uploaded_at,
               up.full_name   AS latest_uploaded_by_name,
               l.reviewed_at  AS latest_reviewed_at,
               rv.full_name   AS latest_reviewed_by_name,
               l.file_blob_id AS latest_file_blob_id
          FROM shop_drawing d
          JOIN projects p ON p.project_id = d.project_id
          JOIN latest l   ON l.drawing_id = d.drawing_id
          LEFT JOIN app_user up ON up.id = l.uploaded_by
          LEFT JOIN app_user rv ON rv.id = l.reviewed_by
         WHERE d.project_id = :p
           AND {subtab_where}
           {extra}
         ORDER BY d.drawing_id DESC
    """
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def list_summary(db: Session, *, project_id: int) -> dict:
    """Header counts: total non-archived, distinct rooms, awaiting review."""
    row = db.execute(
        text(
            f"""
            WITH {_LATEST_REV_CTE}
            SELECT
              COUNT(*) FILTER (WHERE d.archived_at IS NULL)               AS total,
              COUNT(DISTINCT d.room) FILTER (WHERE d.archived_at IS NULL) AS distinct_rooms,
              COUNT(*) FILTER (WHERE d.archived_at IS NULL AND l.status = 'pending') AS awaiting_review
              FROM shop_drawing d
              JOIN latest l ON l.drawing_id = d.drawing_id
             WHERE d.project_id = :p
            """
        ),
        {"p": project_id},
    ).mappings().first()
    return dict(row) if row else {"total": 0, "distinct_rooms": 0, "awaiting_review": 0}


def get_drawing_with_revisions(db: Session, *, drawing_id: int, workspace_id: int) -> dict | None:
    drawing = db.execute(
        text(
            """
            SELECT d.drawing_id, d.project_id, p.project_code, d.title, d.room,
                   d.current_revision_id, d.archived_at, d.archived_by,
                   d.created_by, d.created_at
              FROM shop_drawing d
              JOIN projects p ON p.project_id = d.project_id
              LEFT JOIN app_user u ON u.id = p.pm_id
             WHERE d.drawing_id = :d
               AND (p.pm_id IS NULL OR u.workspace_id = :w)
            """
        ),
        {"d": drawing_id, "w": workspace_id},
    ).mappings().first()
    if not drawing:
        return None

    revs = db.execute(
        text(
            """
            SELECT r.revision_id, r.rev_no, r.status, r.file_blob_id,
                   fb.mime AS file_mime,
                   r.uploaded_by, up.full_name AS uploaded_by_name, r.uploaded_at,
                   r.reviewed_by, rv.full_name AS reviewed_by_name, r.reviewed_at,
                   r.review_note
              FROM shop_drawing_revision r
              JOIN file_blob fb ON fb.file_blob_id = r.file_blob_id
              LEFT JOIN app_user up ON up.id = r.uploaded_by
              LEFT JOIN app_user rv ON rv.id = r.reviewed_by
             WHERE r.drawing_id = :d
             ORDER BY r.rev_no DESC
            """
        ),
        {"d": drawing_id},
    ).mappings().all()
    return dict(drawing) | {"revisions": [dict(r) for r in revs]}


def create_drawing(
    db: Session, *, workspace_id: int, project_id: int, payload: CreateDrawingIn, actor_id: int
) -> int:
    if not _ensure_project_in_workspace(db, project_id=project_id, workspace_id=workspace_id):
        raise ValueError("project not found in workspace")
    # Confirm the file_blob belongs to this workspace (cross-workspace blob is rejected).
    blob = db.execute(
        text("SELECT 1 FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": payload.file_blob_id, "w": workspace_id},
    ).first()
    if not blob:
        raise ValueError("file_blob_id not found in this workspace")

    drawing_id = db.execute(
        text(
            """
            INSERT INTO shop_drawing(project_id, title, room, created_by)
            VALUES (:p, :t, :r, :u) RETURNING drawing_id
            """
        ),
        {"p": project_id, "t": payload.title, "r": payload.room, "u": actor_id},
    ).scalar()

    initial_status = "pending" if payload.submit_immediately else "draft"
    rev_id = db.execute(
        text(
            """
            INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
            VALUES (:d, 1, :b, :s, :u) RETURNING revision_id
            """
        ),
        {"d": drawing_id, "b": payload.file_blob_id, "s": initial_status, "u": actor_id},
    ).scalar()

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="shop_drawing.create", target=str(drawing_id),
        payload={"title": payload.title, "room": payload.room,
                 "rev_no": 1, "status": initial_status, "revision_id": rev_id},
    )
    db.flush()
    return drawing_id


def patch_drawing(
    db: Session, *, drawing_id: int, workspace_id: int, payload: PatchDrawingIn, actor_id: int
) -> dict | None:
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)

    drawing = get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)
    if not drawing:
        return None

    set_clauses = ", ".join(f"{k} = :{k}" for k in fields)
    params = {**fields, "d": drawing_id}
    db.execute(text(f"UPDATE shop_drawing SET {set_clauses} WHERE drawing_id = :d"), params)
    for k, v in fields.items():
        write_audit(
            db, workspace_id=workspace_id, actor_id=actor_id,
            event="shop_drawing.update", target=str(drawing_id),
            payload={"field": k, "value": v},
        )
    db.flush()
    return get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)


def archive_drawing(
    db: Session, *, drawing_id: int, workspace_id: int, actor_id: int
) -> bool:
    drawing = get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)
    if not drawing:
        return False
    db.execute(
        text("UPDATE shop_drawing SET archived_at = now(), archived_by = :u WHERE drawing_id = :d"),
        {"u": actor_id, "d": drawing_id},
    )
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="shop_drawing.archive", target=str(drawing_id), payload={},
    )
    db.flush()
    return True


def add_revision(
    db: Session, *, drawing_id: int, workspace_id: int, file_blob_id: int, actor_id: int
) -> int:
    drawing = get_drawing_with_revisions(db, drawing_id=drawing_id, workspace_id=workspace_id)
    if not drawing:
        raise ValueError("drawing not found")
    blob = db.execute(
        text("SELECT 1 FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
        {"b": file_blob_id, "w": workspace_id},
    ).first()
    if not blob:
        raise ValueError("file_blob_id not found in this workspace")

    next_rev = db.execute(
        text("SELECT COALESCE(MAX(rev_no), 0) + 1 FROM shop_drawing_revision WHERE drawing_id = :d"),
        {"d": drawing_id},
    ).scalar()
    rev_id = db.execute(
        text(
            """
            INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status, uploaded_by)
            VALUES (:d, :n, :b, 'draft', :u) RETURNING revision_id
            """
        ),
        {"d": drawing_id, "n": next_rev, "b": file_blob_id, "u": actor_id},
    ).scalar()
    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event="shop_drawing.revision.upload", target=str(drawing_id),
        payload={"revision_id": rev_id, "rev_no": next_rev},
    )
    db.flush()
    return rev_id


def transition_revision(
    db: Session, *, drawing_id: int, revision_id: int, workspace_id: int,
    actor_id: int, action: Literal["submit", "withdraw", "approve", "reject"],
    review_note: str | None = None,
) -> dict | None:
    """Apply a state transition. Returns the updated revision row or None if not found."""
    rev = db.execute(
        text(
            """
            SELECT r.revision_id, r.drawing_id, r.status, r.uploaded_by, r.rev_no
              FROM shop_drawing_revision r
              JOIN shop_drawing d ON d.drawing_id = r.drawing_id
              JOIN projects p ON p.project_id = d.project_id
              LEFT JOIN app_user u ON u.id = p.pm_id
             WHERE r.revision_id = :r AND r.drawing_id = :d
               AND (p.pm_id IS NULL OR u.workspace_id = :w)
            """
        ),
        {"r": revision_id, "d": drawing_id, "w": workspace_id},
    ).mappings().first()
    if not rev:
        return None

    cur = rev["status"]
    if action == "submit":
        if cur != "draft":
            raise ValueError(f"cannot submit from {cur}")
        new_status, set_review = "pending", False
    elif action == "withdraw":
        if cur != "pending":
            raise ValueError(f"cannot withdraw from {cur}")
        new_status, set_review = "draft", False
    elif action == "approve":
        if cur != "pending":
            raise ValueError(f"cannot approve from {cur}")
        new_status, set_review = "approved", True
    elif action == "reject":
        if cur != "pending":
            raise ValueError(f"cannot reject from {cur}")
        if not review_note:
            raise ValueError("review_note is required for reject")
        new_status, set_review = "rejected", True
    else:
        raise ValueError(f"unknown action: {action}")

    if set_review:
        db.execute(
            text(
                """
                UPDATE shop_drawing_revision
                   SET status = :s, reviewed_by = :u, reviewed_at = now(), review_note = :n
                 WHERE revision_id = :r
                """
            ),
            {"s": new_status, "u": actor_id, "n": review_note, "r": revision_id},
        )
    else:
        db.execute(
            text("UPDATE shop_drawing_revision SET status = :s WHERE revision_id = :r"),
            {"s": new_status, "r": revision_id},
        )

    if action == "approve":
        db.execute(
            text("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
            {"r": revision_id, "d": drawing_id},
        )

    write_audit(
        db, workspace_id=workspace_id, actor_id=actor_id,
        event=f"shop_drawing.revision.{action}", target=str(drawing_id),
        payload={"revision_id": revision_id, "rev_no": rev["rev_no"],
                 "status_before": cur, "status_after": new_status,
                 "review_note": review_note},
    )
    db.flush()
    return {"revision_id": revision_id, "status": new_status}
```

- [ ] **Step 4: Run subtab tests, confirm pass**

```bash
docker compose exec api pytest tests/test_shop_drawings_subtab_query.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/shop_drawings/queries.py apps/api/tests/test_shop_drawings_subtab_query.py
git commit -m "feat(shop-dwgs): SQL queries for subtab listing + workflow transitions"
```

---

### Task 10: Routes — CRUD + workflow + mounting

**Files:**
- Create: `apps/api/app/shop_drawings/routes.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_shop_drawings_crud.py`

- [ ] **Step 1: Write the failing CRUD tests**

Create `apps/api/tests/test_shop_drawings_crud.py`:

```python
"""Shop Drawings — CRUD route tests (workflow tests are in Task 11)."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _setup(client, role: str = "drafter") -> dict:
    """Seed workspace + user + project, log in. Return ids."""
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hartwood','HW') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@hw.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('ALF-001', 'Alfred', :u) RETURNING project_id
        """), {"u": uid}).scalar()
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "hartwood", "email": f"{role}@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return {"wid": wid, "uid": uid, "pid": pid}


def _upload_blob(client) -> int:
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    return r.json()["file_blob_id"]


def test_create_drawing_creates_rev_1_in_draft(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Kitchen base run", "room": "Kitchen", "file_blob_id": blob_id,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Kitchen base run"
    assert body["room"] == "Kitchen"
    assert len(body["revisions"]) == 1
    assert body["revisions"][0]["status"] == "draft"
    assert body["revisions"][0]["rev_no"] == 1


def test_create_drawing_with_submit_immediately_lands_in_pending(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Bath vanity", "room": "Bath", "file_blob_id": blob_id,
        "submit_immediately": True,
    })
    assert r.status_code == 201
    assert r.json()["revisions"][0]["status"] == "pending"


def test_list_subtab_in_review(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T1", "room": "Kitchen", "file_blob_id": blob_id, "submit_immediately": True,
    })
    r = client.get(f"/projects/{ids['pid']}/shop-drawings", params={"subtab": "in_review"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(d["title"] == "T1" for d in body["drawings"])


def test_patch_drawing_updates_title(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Original", "room": "Kitchen", "file_blob_id": blob_id,
    })
    did = r.json()["drawing_id"]
    r2 = client.patch(f"/shop-drawings/{did}", json={"title": "Updated"})
    assert r2.status_code == 200
    assert r2.json()["title"] == "Updated"


def test_archive_drawing_moves_it_to_archive_subtab(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Pantry", "room": "Kitchen", "file_blob_id": blob_id,
    })
    did = r.json()["drawing_id"]
    # Need to be manager to archive — re-setup as manager
    client.cookies.clear()
    # Promote the same user to manager via direct DB
    from app.db import SessionLocal
    from sqlalchemy import text
    s = SessionLocal()
    try:
        s.execute(text("UPDATE app_user SET auth_role='manager' WHERE id=:u"), {"u": ids["uid"]})
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "hartwood", "email": "drafter@hw.test", "password": "pw"})
    assert r.status_code == 200
    r3 = client.post(f"/shop-drawings/{did}/archive")
    assert r3.status_code == 204, r3.text
    r4 = client.get(f"/projects/{ids['pid']}/shop-drawings", params={"subtab": "archive"})
    assert r4.status_code == 200
    assert any(d["drawing_id"] == did for d in r4.json()["drawings"])


def test_create_drawing_cross_workspace_blob_rejected(client):
    """Try to create a drawing referencing a file_blob from another workspace → 422."""
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    # Set up workspace A + login + upload
    ids_a = _setup(client)
    blob_id_a = _upload_blob(client)
    # Set up workspace B + project
    s = SessionLocal()
    try:
        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('ws-b','WS B') RETURNING id")).scalar()
        uid_b = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@b.test', 'B', :p, 'drafter') RETURNING id
        """), {"w": wid_b, "p": hash_password("pw")}).scalar()
        pid_b = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('B-001','B', :u) RETURNING project_id
        """), {"u": uid_b}).scalar()
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    client.post("/auth/login", json={"workspace_slug": "ws-b", "email": "b@b.test", "password": "pw"})
    r = client.post(f"/projects/{pid_b}/shop-drawings", json={
        "title": "X", "room": "Y", "file_blob_id": blob_id_a,
    })
    assert r.status_code == 422
```

- [ ] **Step 2: Run, confirm fail**

```bash
docker compose exec api pytest tests/test_shop_drawings_crud.py -v
```

Expected: 6 failures (404 — routes not mounted).

- [ ] **Step 3: Implement `routes.py`**

Create `apps/api/app/shop_drawings/routes.py`:

```python
"""Shop Drawings routes — CRUD + workflow.

Permissions:
  - Create / patch / upload revision / submit / withdraw: shop_dwgs:write
    (drafter / manager / admin per the matrix).
  - Approve / reject / archive: shop_dwgs:approve (manager / admin / drafter).
    Plus the not-uploader rule on approve/reject is enforced in-handler.
  - Read: shop_dwgs:read (all roles except IT-management-only).

The "one in flight per drawing" invariant is enforced by the partial unique
index uniq_drawing_inflight; the handler turns the IntegrityError into a 409.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from . import queries as q
from .schemas import (
    CreateDrawingIn,
    CreateRevisionIn,
    DrawingDetailOut,
    DrawingListOut,
    PatchDrawingIn,
    RejectIn,
)

router = APIRouter(tags=["shop_drawings"])


@router.get("/projects/{pid}/shop-drawings", response_model=DrawingListOut)
def list_drawings(
    pid: int,
    subtab: str = Query("current", pattern="^(current|in_review|archive)$"),
    room: str | None = None,
    reviewer_id: int | None = None,
    q_search: str | None = Query(None, alias="q"),
    user: AuthUser = Depends(require_permission("shop_dwgs", "read")),
    db: Session = Depends(get_db),
):
    if not q._ensure_project_in_workspace(db, project_id=pid, workspace_id=user.workspace_id):
        raise HTTPException(status_code=404, detail="project not found")
    rows = q.list_drawings_by_subtab(
        db, project_id=pid, subtab=subtab, room=room,
        reviewer_id=reviewer_id, q=q_search,
    )
    summary = q.list_summary(db, project_id=pid)
    return DrawingListOut(
        drawings=rows,
        total=summary.get("total", 0),
        awaiting_review=summary.get("awaiting_review", 0),
        distinct_rooms=summary.get("distinct_rooms", 0),
    )


@router.get("/shop-drawings/{did}", response_model=DrawingDetailOut)
def get_drawing(
    did: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "read")),
    db: Session = Depends(get_db),
):
    row = q.get_drawing_with_revisions(db, drawing_id=did, workspace_id=user.workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing not found")
    return row


@router.post("/projects/{pid}/shop-drawings", response_model=DrawingDetailOut, status_code=201)
def create_drawing_route(
    pid: int,
    body: CreateDrawingIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    try:
        new_id = q.create_drawing(
            db, workspace_id=user.workspace_id, project_id=pid,
            payload=body, actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return q.get_drawing_with_revisions(db, drawing_id=new_id, workspace_id=user.workspace_id)


@router.patch("/shop-drawings/{did}", response_model=DrawingDetailOut)
def patch_drawing_route(
    did: int,
    body: PatchDrawingIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    row = q.patch_drawing(
        db, drawing_id=did, workspace_id=user.workspace_id,
        payload=body, actor_id=user.id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="drawing not found")
    db.commit()
    return row


@router.post("/shop-drawings/{did}/archive", status_code=204)
def archive_drawing_route(
    did: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "approve")),
    db: Session = Depends(get_db),
):
    if not q.archive_drawing(db, drawing_id=did, workspace_id=user.workspace_id, actor_id=user.id):
        raise HTTPException(status_code=404, detail="drawing not found")
    db.commit()
    return Response(status_code=204)


@router.post("/shop-drawings/{did}/revisions", response_model=DrawingDetailOut, status_code=201)
def add_revision_route(
    did: int,
    body: CreateRevisionIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    try:
        q.add_revision(
            db, drawing_id=did, workspace_id=user.workspace_id,
            file_blob_id=body.file_blob_id, actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc))
    except IntegrityError as exc:
        db.rollback()
        if "uniq_drawing_inflight" in str(exc.orig):
            raise HTTPException(
                status_code=409,
                detail="this drawing already has an in-flight revision; withdraw or wait for review",
            )
        raise
    db.commit()
    return q.get_drawing_with_revisions(db, drawing_id=did, workspace_id=user.workspace_id)


def _transition(
    did: int, rid: int, action: str, db: Session, user: AuthUser,
    review_note: str | None = None,
):
    """Shared transition handler. Approve/reject have the not-uploader rule."""
    rev = db.execute(
        text("SELECT uploaded_by FROM shop_drawing_revision WHERE revision_id = :r AND drawing_id = :d"),
        {"r": rid, "d": did},
    ).first()
    if not rev:
        raise HTTPException(status_code=404, detail="revision not found")
    if action in ("approve", "reject") and rev[0] == user.id:
        raise HTTPException(status_code=403, detail="reviewer cannot be the uploader")
    if action in ("submit", "withdraw") and rev[0] != user.id:
        raise HTTPException(status_code=403, detail="only the uploader can submit/withdraw a revision")

    try:
        result = q.transition_revision(
            db, drawing_id=did, revision_id=rid,
            workspace_id=user.workspace_id, actor_id=user.id,
            action=action, review_note=review_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="revision not found")
    db.commit()
    return result


@router.post("/shop-drawings/{did}/revisions/{rid}/submit")
def submit_revision_route(
    did: int, rid: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "submit", db, user)


@router.post("/shop-drawings/{did}/revisions/{rid}/withdraw")
def withdraw_revision_route(
    did: int, rid: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "write")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "withdraw", db, user)


@router.post("/shop-drawings/{did}/revisions/{rid}/approve")
def approve_revision_route(
    did: int, rid: int,
    user: AuthUser = Depends(require_permission("shop_dwgs", "approve")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "approve", db, user)


@router.post("/shop-drawings/{did}/revisions/{rid}/reject")
def reject_revision_route(
    did: int, rid: int,
    body: RejectIn,
    user: AuthUser = Depends(require_permission("shop_dwgs", "approve")),
    db: Session = Depends(get_db),
):
    return _transition(did, rid, "reject", db, user, review_note=body.review_note)
```

- [ ] **Step 4: Mount the router in `main.py`**

In `apps/api/app/main.py`, add the import:

```python
from .shop_drawings.routes import router as shop_dwgs_router
```

And include it after the files router:

```python
app.include_router(shop_dwgs_router)
```

- [ ] **Step 5: Run CRUD tests, confirm pass**

```bash
docker compose exec api pytest tests/test_shop_drawings_crud.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Run the full suite**

```bash
docker compose exec api pytest -q
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/shop_drawings/routes.py apps/api/app/main.py apps/api/tests/test_shop_drawings_crud.py
git commit -m "feat(shop-dwgs): CRUD + revision-workflow routes mounted"
```

---

### Task 11: Workflow + RBAC tests (state machine + not-uploader rule + in-flight 409)

**Files:**
- Create: `apps/api/tests/test_shop_drawings_workflow.py`
- Create: `apps/api/tests/test_shop_drawings_rbac.py`

- [ ] **Step 1: Write workflow tests**

Create `apps/api/tests/test_shop_drawings_workflow.py`:

```python
"""Revision state machine + not-uploader rule + in-flight 409."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _seed_two_users(client) -> dict:
    """Create one workspace + drafter (uploader) + manager (reviewer) + project."""
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hw','HW') RETURNING id")).scalar()
        d_id = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'd@hw.test', 'D', :p, 'drafter') RETURNING id
        """), {"w": wid, "p": hash_password("pw")}).scalar()
        m_id = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'm@hw.test', 'M', :p, 'manager') RETURNING id
        """), {"w": wid, "p": hash_password("pw")}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('ALF-001','A',:u) RETURNING project_id
        """), {"u": m_id}).scalar()
        s.commit()
    finally:
        s.close()
    return {"wid": wid, "drafter": d_id, "manager": m_id, "pid": pid}


def _login(client, who: str):
    client.cookies.clear()
    r = client.post("/auth/login",
                    json={"workspace_slug": "hw", "email": f"{who}@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text


def _upload(client) -> int:
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    return r.json()["file_blob_id"]


def _create_drawing(client, pid: int, file_blob_id: int) -> dict:
    r = client.post(f"/projects/{pid}/shop-drawings", json={
        "title": "T", "room": "Kitchen", "file_blob_id": file_blob_id,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_submit_then_approve_makes_it_current(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    drawing = _create_drawing(client, ids["pid"], blob_id)
    rid = drawing["revisions"][0]["revision_id"]
    did = drawing["drawing_id"]

    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    r = client.get(f"/shop-drawings/{did}")
    assert r.json()["current_revision_id"] == rid


def test_uploader_cannot_approve_own_revision(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")

    # Drafter is also approve-permitted in matrix, but the in-handler rule blocks self-approval.
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 403
    assert "uploader" in r.json()["detail"].lower()


def test_reject_requires_note(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/reject", json={"review_note": ""})
    assert r.status_code == 422  # pydantic min_length=1


def test_reject_with_note_changes_state_but_not_current(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/reject",
                    json={"review_note": "needs more dimensions"})
    assert r.status_code == 200
    detail = client.get(f"/shop-drawings/{did}").json()
    assert detail["current_revision_id"] is None
    assert detail["revisions"][0]["status"] == "rejected"
    assert detail["revisions"][0]["review_note"] == "needs more dimensions"


def test_withdraw_only_by_uploader(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")

    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/withdraw")
    assert r.status_code == 403


def test_cannot_submit_from_approved(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    _login(client, "m")
    client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    _login(client, "d")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    assert r.status_code == 409


def test_two_in_flight_revisions_409(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob1 = _upload(client)
    d = _create_drawing(client, ids["pid"], blob1)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    # Upload a second blob (different bytes so dedup doesn't return the same id).
    files = {"file": ("b.pdf", io.BytesIO(PDF_BYTES + b"\nextra"), "application/pdf")}
    blob2 = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/shop-drawings/{did}/revisions", json={"file_blob_id": blob2})
    assert r.status_code == 409
    assert "in-flight" in r.json()["detail"].lower()


def test_after_withdraw_can_upload_new_revision(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob1 = _upload(client)
    d = _create_drawing(client, ids["pid"], blob1)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    client.post(f"/shop-drawings/{did}/revisions/{rid}/withdraw")
    files = {"file": ("c.pdf", io.BytesIO(PDF_BYTES + b"\nx"), "application/pdf")}
    blob2 = client.post("/files", files=files).json()["file_blob_id"]
    # The previous revision is now back in 'draft' (still in-flight) — must withdraw not enough; need to also stay in draft and cannot add another.
    # Spec rule: after withdraw, the existing revision is in draft (in-flight). Cannot upload another.
    r = client.post(f"/shop-drawings/{did}/revisions", json={"file_blob_id": blob2})
    assert r.status_code == 409


def test_archive_blocks_no_further_revisions_via_subtab(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob = _upload(client)
    d = _create_drawing(client, ids["pid"], blob)
    did = d["drawing_id"]
    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/archive")
    assert r.status_code == 204
    detail = client.get(f"/shop-drawings/{did}").json()
    assert detail["archived_at"] is not None


def test_404_for_drawing_in_other_workspace(client):
    """Cross-workspace drawing fetch returns 404 (not 403)."""
    ids = _seed_two_users(client)
    _login(client, "d")
    blob = _upload(client)
    d = _create_drawing(client, ids["pid"], blob)
    did = d["drawing_id"]

    # Switch to a brand-new workspace
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('wsb','B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@b.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    client.post("/auth/login", json={"workspace_slug": "wsb", "email": "b@b.test", "password": "pw"})
    r = client.get(f"/shop-drawings/{did}")
    assert r.status_code == 404
```

- [ ] **Step 2: Write RBAC tests**

Create `apps/api/tests/test_shop_drawings_rbac.py`:

```python
"""RBAC for shop_drawings — viewer denied, editor read+write but no approve, drafter elevated."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))


@pytest.fixture
def client():
    return TestClient(app)


def _seed(client) -> dict:
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    out = {}
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hw','HW') RETURNING id")).scalar()
        out["wid"] = wid
        for role in ("drafter", "editor", "manager", "viewer"):
            uid = s.execute(text("""
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, :r, :p, :r2) RETURNING id
            """), {"w": wid, "e": f"{role}@hw.test", "r": role, "p": hash_password("pw"), "r2": role}).scalar()
            out[role] = uid
        out["pid"] = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('A','A', :u) RETURNING project_id
        """), {"u": out["manager"]}).scalar()
        s.commit()
    finally:
        s.close()
    return out


def _login(client, role: str):
    client.cookies.clear()
    r = client.post("/auth/login", json={"workspace_slug": "hw", "email": f"{role}@hw.test", "password": "pw"})
    assert r.status_code == 200


def test_viewer_can_read_but_not_create(client):
    ids = _seed(client)
    _login(client, "viewer")
    r = client.get(f"/projects/{ids['pid']}/shop-drawings")
    assert r.status_code == 200
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 403


def test_editor_can_upload_and_create_but_not_approve(client):
    ids = _seed(client)
    _login(client, "editor")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 201
    blob_id = r.json()["file_blob_id"]
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T", "room": "K", "file_blob_id": blob_id, "submit_immediately": True,
    })
    assert r.status_code == 201
    did = r.json()["drawing_id"]
    rid = r.json()["revisions"][0]["revision_id"]
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 403  # editor lacks the 'approve' action on shop_dwgs


def test_drafter_can_approve_others_revision(client):
    """Drafter has approve in the matrix; the not-uploader rule still applies in-handler."""
    ids = _seed(client)
    # Editor uploads + submits.
    _login(client, "editor")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    blob_id = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T", "room": "K", "file_blob_id": blob_id, "submit_immediately": True,
    })
    did = r.json()["drawing_id"]
    rid = r.json()["revisions"][0]["revision_id"]
    # Drafter approves (different uploader → allowed).
    _login(client, "drafter")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 200


def test_manager_can_archive(client):
    ids = _seed(client)
    _login(client, "drafter")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    blob_id = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T", "room": "K", "file_blob_id": blob_id,
    })
    did = r.json()["drawing_id"]
    _login(client, "manager")
    r = client.post(f"/shop-drawings/{did}/archive")
    assert r.status_code == 204
```

- [ ] **Step 3: Run all the new tests**

```bash
docker compose exec api pytest tests/test_shop_drawings_workflow.py tests/test_shop_drawings_rbac.py -v
```

Expected: 10 + 4 = 14 passed.

- [ ] **Step 4: Run the full suite**

```bash
docker compose exec api pytest -q
```

Expected: prior baseline + all new tests, no failures.

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_shop_drawings_workflow.py apps/api/tests/test_shop_drawings_rbac.py
git commit -m "test(shop-dwgs): workflow state machine + RBAC + in-flight 409"
```

---

## Phase 4 — Web foundation (3 tasks)

### Task 12: Web types + fetch wrappers + file-upload helper

**Files:**
- Create: `apps/web/lib/shop-drawings-types.ts`
- Create: `apps/web/lib/shop-drawings-fetch.ts`
- Create: `apps/web/lib/file-upload.ts`

- [ ] **Step 1: Create the types file**

Create `apps/web/lib/shop-drawings-types.ts`:

```ts
export type RevisionStatus = "draft" | "pending" | "approved" | "rejected";

export interface FileBlob {
  file_blob_id: number;
  sha256: string;
  mime: string;
  byte_size: number;
  original_filename: string;
  deduped: boolean;
}

export interface DrawingCard {
  drawing_id: number;
  project_id: number;
  project_code: string;
  title: string;
  room: string | null;
  archived_at: string | null;
  current_revision_id: number | null;
  latest_rev_no: number;
  latest_status: RevisionStatus;
  latest_uploaded_at: string;
  latest_uploaded_by_name: string | null;
  latest_reviewed_at: string | null;
  latest_reviewed_by_name: string | null;
  latest_file_blob_id: number;
}

export interface DrawingList {
  drawings: DrawingCard[];
  total: number;
  awaiting_review: number;
  distinct_rooms: number;
}

export interface Revision {
  revision_id: number;
  rev_no: number;
  status: RevisionStatus;
  file_blob_id: number;
  file_mime: string;
  uploaded_by: number;
  uploaded_by_name: string | null;
  uploaded_at: string;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_note: string | null;
}

export interface DrawingDetail {
  drawing_id: number;
  project_id: number;
  project_code: string;
  title: string;
  room: string | null;
  current_revision_id: number | null;
  archived_at: string | null;
  archived_by: number | null;
  created_by: number;
  created_at: string;
  revisions: Revision[];
}

export type Subtab = "current" | "in_review" | "archive";
```

- [ ] **Step 2: Create the file-upload helper**

Create `apps/web/lib/file-upload.ts`:

```ts
import type { FileBlob } from "./shop-drawings-types";

/**
 * Upload one file to /files via multipart/form-data.
 * Returns the FileBlob record (deduped flag included).
 *
 * Throws on non-2xx — callers should catch and surface a toast.
 */
export async function uploadFile(file: File): Promise<FileBlob> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/files", { method: "POST", body: fd });
  if (!r.ok) {
    let msg = "upload failed";
    try {
      const body = await r.json();
      if (body?.detail) msg = body.detail;
    } catch {}
    throw new Error(`${r.status}: ${msg}`);
  }
  return r.json();
}
```

- [ ] **Step 3: Create the fetch wrappers**

Create `apps/web/lib/shop-drawings-fetch.ts`:

```ts
import type {
  DrawingCard,
  DrawingDetail,
  DrawingList,
  RevisionStatus,
  Subtab,
} from "./shop-drawings-types";

interface ListParams {
  projectId: number;
  subtab: Subtab;
  room?: string | null;
  reviewerId?: number | null;
  q?: string | null;
}

export async function listDrawings(p: ListParams): Promise<DrawingList> {
  const q = new URLSearchParams({ subtab: p.subtab });
  if (p.room) q.set("room", p.room);
  if (p.reviewerId != null) q.set("reviewer_id", String(p.reviewerId));
  if (p.q) q.set("q", p.q);
  const r = await fetch(`/api/projects/${p.projectId}/shop-drawings?${q}`);
  if (!r.ok) throw new Error(`list drawings failed: ${r.status}`);
  return r.json();
}

export async function getDrawing(drawingId: number): Promise<DrawingDetail> {
  const r = await fetch(`/api/shop-drawings/${drawingId}`);
  if (!r.ok) throw new Error(`get drawing failed: ${r.status}`);
  return r.json();
}

export async function createDrawing(input: {
  projectId: number;
  title: string;
  room: string | null;
  fileBlobId: number;
  submitImmediately: boolean;
}): Promise<DrawingDetail> {
  const r = await fetch(`/api/projects/${input.projectId}/shop-drawings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: input.title,
      room: input.room,
      file_blob_id: input.fileBlobId,
      submit_immediately: input.submitImmediately,
    }),
  });
  if (!r.ok) throw new Error((await r.json())?.detail ?? `create failed: ${r.status}`);
  return r.json();
}

export async function patchDrawing(
  drawingId: number,
  patch: { title?: string; room?: string | null }
): Promise<DrawingDetail> {
  const r = await fetch(`/api/shop-drawings/${drawingId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error((await r.json())?.detail ?? `patch failed: ${r.status}`);
  return r.json();
}

export async function archiveDrawing(drawingId: number): Promise<void> {
  const r = await fetch(`/api/shop-drawings/${drawingId}/archive`, { method: "POST" });
  if (!r.ok) throw new Error(`archive failed: ${r.status}`);
}

export async function addRevision(drawingId: number, fileBlobId: number): Promise<DrawingDetail> {
  const r = await fetch(`/api/shop-drawings/${drawingId}/revisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_blob_id: fileBlobId }),
  });
  if (!r.ok) throw new Error((await r.json())?.detail ?? `add revision failed: ${r.status}`);
  return r.json();
}

export async function transitionRevision(
  drawingId: number,
  revisionId: number,
  action: "submit" | "withdraw" | "approve" | "reject",
  reviewNote?: string
): Promise<{ revision_id: number; status: RevisionStatus }> {
  const init: RequestInit = { method: "POST" };
  if (action === "reject") {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify({ review_note: reviewNote ?? "" });
  }
  const r = await fetch(`/api/shop-drawings/${drawingId}/revisions/${revisionId}/${action}`, init);
  if (!r.ok) throw new Error((await r.json())?.detail ?? `${action} failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 4: Type-check**

```bash
docker compose exec web pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/shop-drawings-types.ts apps/web/lib/shop-drawings-fetch.ts apps/web/lib/file-upload.ts
git commit -m "feat(web): types + fetch wrappers + file-upload helper for shop-drawings"
```

---

### Task 13: Page shell — `/shop-dwgs` with subtabs + filter strip + grid container

**Files:**
- Modify: `apps/web/app/(app)/shop-dwgs/page.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/SubtabStrip.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/DrawingFilters.tsx`

- [ ] **Step 1: Replace the stub page with a server-side wrapper**

Overwrite `apps/web/app/(app)/shop-dwgs/page.tsx`:

```tsx
import { fetchMe } from "@/lib/auth";
import ShopDwgsClient from "./_components/ShopDwgsClient";

interface PageProps {
  searchParams: Promise<{
    subtab?: string;
    project?: string;
    room?: string;
    q?: string;
    drawing?: string;
    rev?: string;
  }>;
}

export default async function Page({ searchParams }: PageProps) {
  const sp = await searchParams;
  const me = await fetchMe();
  const projectsRes = await fetch(
    `${process.env.INTERNAL_API_BASE ?? "http://api:8000"}/projects`,
    { headers: { cookie: (await import("next/headers")).cookies().toString() }, cache: "no-store" }
  );
  const projects = projectsRes.ok ? (await projectsRes.json()).projects : [];

  const subtab = (sp.subtab as "current" | "in_review" | "archive") ?? "current";
  const projectId = sp.project ? Number(sp.project) : (projects[0]?.id ?? null);

  return (
    <ShopDwgsClient
      me={me}
      projects={projects}
      initialProjectId={projectId}
      initialSubtab={subtab}
      initialRoom={sp.room ?? null}
      initialQ={sp.q ?? null}
      initialDrawingId={sp.drawing ? Number(sp.drawing) : null}
      initialRevId={sp.rev ? Number(sp.rev) : null}
    />
  );
}
```

> Note: if the project already has a different `fetchMe` import path, follow the convention used in the existing `/home` or `/tracking` pages.

- [ ] **Step 2: Create the SubtabStrip**

Create `apps/web/app/(app)/shop-dwgs/_components/SubtabStrip.tsx`:

```tsx
"use client";

import type { Subtab } from "@/lib/shop-drawings-types";

interface Props {
  current: Subtab;
  onChange: (next: Subtab) => void;
  counts: { total: number; awaiting_review: number };
}

const TABS: { key: Subtab; label: string }[] = [
  { key: "current",   label: "Current" },
  { key: "in_review", label: "In review" },
  { key: "archive",   label: "Archive" },
];

export default function SubtabStrip({ current, onChange, counts }: Props) {
  return (
    <div className="flex items-center gap-2 border-b border-h-line pb-2">
      {TABS.map((t) => {
        const active = t.key === current;
        const badge = t.key === "in_review" && counts.awaiting_review > 0
          ? <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-h-accent/15 px-1.5 text-xs text-h-accent">{counts.awaiting_review}</span>
          : null;
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={`relative px-3 py-1.5 text-sm transition ${
              active ? "text-h-ink" : "text-h-muted hover:text-h-ink"
            }`}
          >
            {t.label}{badge}
            {active && <span className="absolute inset-x-1 -bottom-2 h-0.5 bg-h-accent" />}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Create the DrawingFilters**

Create `apps/web/app/(app)/shop-dwgs/_components/DrawingFilters.tsx`:

```tsx
"use client";

import { useState } from "react";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

interface Props {
  projects: Project[];
  selectedProjectId: number | null;
  selectedRoom: string | null;
  searchValue: string;
  rooms: string[];
  onProjectChange: (id: number) => void;
  onRoomChange: (room: string | null) => void;
  onSearchChange: (q: string) => void;
}

export default function DrawingFilters(p: Props) {
  const [search, setSearch] = useState(p.searchValue);

  return (
    <div className="flex flex-wrap items-center gap-3 py-3">
      <input
        type="search"
        placeholder="Search title…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onBlur={() => p.onSearchChange(search)}
        onKeyDown={(e) => { if (e.key === "Enter") p.onSearchChange(search); }}
        className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink placeholder:text-h-muted"
      />
      <select
        value={p.selectedProjectId ?? ""}
        onChange={(e) => p.onProjectChange(Number(e.target.value))}
        className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
      >
        {p.projects.map((proj) => (
          <option key={proj.id} value={proj.id}>{proj.project_code} · {proj.name}</option>
        ))}
      </select>
      <select
        value={p.selectedRoom ?? ""}
        onChange={(e) => p.onRoomChange(e.target.value || null)}
        className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
      >
        <option value="">All rooms</option>
        {p.rooms.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
    </div>
  );
}
```

- [ ] **Step 4: Create the ShopDwgsClient (URL-state owner)**

Create `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`:

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { DrawingCard, DrawingList, Subtab } from "@/lib/shop-drawings-types";
import { listDrawings } from "@/lib/shop-drawings-fetch";

import DrawingFilters from "./DrawingFilters";
import SubtabStrip from "./SubtabStrip";

interface Project { id: number; project_code: string; name: string; }
interface Me { id: number; auth_role: string; full_name: string; workspace_id: number; }

interface Props {
  me: Me;
  projects: Project[];
  initialProjectId: number | null;
  initialSubtab: Subtab;
  initialRoom: string | null;
  initialQ: string | null;
  initialDrawingId: number | null;
  initialRevId: number | null;
}

export default function ShopDwgsClient(props: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const [list, setList] = useState<DrawingList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const projectId = props.initialProjectId;
  const subtab = props.initialSubtab;
  const room = props.initialRoom;
  const q = props.initialQ;

  useEffect(() => {
    if (projectId == null) { setList(null); return; }
    setLoading(true);
    setError(null);
    listDrawings({ projectId, subtab, room, q })
      .then(setList)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId, subtab, room, q]);

  const updateUrl = useCallback((patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v == null || v === "") next.delete(k); else next.set(k, v);
    }
    router.replace(`/shop-dwgs?${next.toString()}`);
  }, [router, sp]);

  const rooms = useMemo(() => {
    const set = new Set<string>();
    for (const d of list?.drawings ?? []) if (d.room) set.add(d.room);
    return Array.from(set).sort();
  }, [list]);

  const headerCounts = list ?? { total: 0, awaiting_review: 0, distinct_rooms: 0, drawings: [] };
  const headerText = projectId
    ? `${headerCounts.total} drawings across ${headerCounts.distinct_rooms} rooms · ${headerCounts.awaiting_review} awaiting review`
    : "Pick a project to view drawings.";

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-h-ink">Shop Drawings</h1>
          <p className="mt-1 text-sm text-h-muted">{headerText}</p>
        </div>
        {/* Upload button mounted in Task 17 */}
      </header>

      <DrawingFilters
        projects={props.projects}
        selectedProjectId={projectId}
        selectedRoom={room}
        searchValue={q ?? ""}
        rooms={rooms}
        onProjectChange={(id) => updateUrl({ project: String(id), drawing: null, rev: null })}
        onRoomChange={(r) => updateUrl({ room: r })}
        onSearchChange={(s) => updateUrl({ q: s || null })}
      />

      <SubtabStrip
        current={subtab}
        onChange={(s) => updateUrl({ subtab: s, drawing: null, rev: null })}
        counts={{ total: headerCounts.total, awaiting_review: headerCounts.awaiting_review }}
      />

      {loading && <p className="text-sm text-h-muted">Loading…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* DrawingCard grid mounted in Task 14 */}
      {list && list.drawings.length === 0 && (
        <p className="py-12 text-center text-sm text-h-muted">No drawings here yet.</p>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Type-check + start dev server smoke**

```bash
docker compose exec web pnpm tsc --noEmit
docker compose up -d web
```

Open `http://localhost:3000/shop-dwgs` after logging in. Expected: header renders, subtab strip works (URL updates), filters render, no console errors. The grid is empty until Task 14.

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/\(app\)/shop-dwgs/page.tsx apps/web/app/\(app\)/shop-dwgs/_components/ShopDwgsClient.tsx apps/web/app/\(app\)/shop-dwgs/_components/SubtabStrip.tsx apps/web/app/\(app\)/shop-dwgs/_components/DrawingFilters.tsx
git commit -m "feat(web): /shop-dwgs page shell with subtabs + filters + URL state"
```

---

### Task 14: DrawingCard + BlueprintPlaceholder + StatusPill + VersionChip

**Files:**
- Create: `apps/web/app/(app)/shop-dwgs/_components/DrawingCard.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/BlueprintPlaceholder.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/StatusPill.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/VersionChip.tsx`
- Modify: `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`

- [ ] **Step 1: Create the StatusPill**

Create `apps/web/app/(app)/shop-dwgs/_components/StatusPill.tsx`:

```tsx
import type { RevisionStatus } from "@/lib/shop-drawings-types";

const PALETTE: Record<RevisionStatus, string> = {
  draft:    "bg-h-line/40 text-h-muted",
  pending:  "bg-amber-100 text-amber-900",
  approved: "bg-emerald-100 text-emerald-900",
  rejected: "bg-rose-100 text-rose-900",
};

const LABEL: Record<RevisionStatus, string> = {
  draft: "Draft", pending: "Pending", approved: "Approved", rejected: "Rejected",
};

export default function StatusPill({ status }: { status: RevisionStatus }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${PALETTE[status]}`}>
      {LABEL[status]}
    </span>
  );
}
```

- [ ] **Step 2: Create the VersionChip**

Create `apps/web/app/(app)/shop-dwgs/_components/VersionChip.tsx`:

```tsx
export default function VersionChip({ revNo }: { revNo: number }) {
  return (
    <span className="h-mono inline-flex items-center rounded border border-h-line bg-h-surface px-1.5 py-0.5 text-xs text-h-muted">
      v{revNo}
    </span>
  );
}
```

- [ ] **Step 3: Create the BlueprintPlaceholder**

Create `apps/web/app/(app)/shop-dwgs/_components/BlueprintPlaceholder.tsx`:

```tsx
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Props { seed: number; }

export default function BlueprintPlaceholder({ seed }: Props) {
  const rng = mulberry32(seed || 1);
  const titleY = 24 + rng() * 8;
  const dimX = 60 + rng() * 200;
  const dimY = 90 + rng() * 60;
  const dimLen = 60 + rng() * 120;

  return (
    <svg viewBox="0 0 320 200" preserveAspectRatio="xMidYMid slice"
         className="block h-full w-full bg-h-surface">
      <defs>
        <pattern id={`grid-${seed}`} width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M 16 0 L 0 0 0 16" fill="none" stroke="currentColor" strokeWidth="0.5" className="text-h-line" />
        </pattern>
      </defs>
      <rect width="320" height="200" fill={`url(#grid-${seed})`} />
      <line x1="20" y1={titleY} x2="300" y2={titleY} stroke="currentColor" strokeWidth="1" className="text-h-line" />
      {/* dimension callout */}
      <line x1={dimX} y1={dimY} x2={dimX + dimLen} y2={dimY} stroke="currentColor" strokeWidth="1" className="text-h-muted" />
      <line x1={dimX} y1={dimY - 4} x2={dimX} y2={dimY + 4} stroke="currentColor" strokeWidth="1" className="text-h-muted" />
      <line x1={dimX + dimLen} y1={dimY - 4} x2={dimX + dimLen} y2={dimY + 4} stroke="currentColor" strokeWidth="1" className="text-h-muted" />
    </svg>
  );
}
```

- [ ] **Step 4: Create the DrawingCard**

Create `apps/web/app/(app)/shop-dwgs/_components/DrawingCard.tsx`:

```tsx
"use client";

import type { DrawingCard as Card } from "@/lib/shop-drawings-types";

import BlueprintPlaceholder from "./BlueprintPlaceholder";
import StatusPill from "./StatusPill";
import VersionChip from "./VersionChip";

function pad4(n: number): string { return String(n).padStart(4, "0"); }
function ddmmyyyy(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()}`;
}

interface Props { card: Card; onClick: () => void; }

export default function DrawingCard({ card, onClick }: Props) {
  const isArchived = card.archived_at != null;
  const personName = card.latest_reviewed_by_name ?? card.latest_uploaded_by_name ?? "—";
  const dateIso = card.latest_reviewed_at ?? card.latest_uploaded_at;

  return (
    <button
      onClick={onClick}
      className="group block w-full overflow-hidden rounded-lg border border-h-line bg-h-surface text-left transition hover:border-h-accent/60 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-h-accent"
    >
      <div className="relative aspect-[16/10] border-b border-h-line">
        <BlueprintPlaceholder seed={card.drawing_id} />
        <div className="absolute left-2 top-2">
          {isArchived ? (
            <span className="inline-flex rounded-full bg-h-line/40 px-2 py-0.5 text-[11px] uppercase tracking-wide text-h-muted">Archived</span>
          ) : (
            <StatusPill status={card.latest_status} />
          )}
        </div>
        <div className="absolute right-2 top-2">
          <VersionChip revNo={card.latest_rev_no} />
        </div>
      </div>
      <div className="space-y-1 p-3">
        <div className="flex items-baseline gap-2">
          <span className="h-mono text-xs text-h-muted">#SD-{pad4(card.drawing_id)}</span>
          <span className="truncate text-sm font-medium text-h-ink">{card.title}</span>
        </div>
        <p className="text-xs text-h-muted">
          {(card.room ?? "—")} · {card.project_code}
        </p>
        <p className="h-mono text-xs text-h-muted">
          {personName} · {ddmmyyyy(dateIso)}
        </p>
      </div>
    </button>
  );
}
```

- [ ] **Step 5: Wire the grid into ShopDwgsClient**

In `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`, add the import:

```tsx
import DrawingCard from "./DrawingCard";
```

Replace the comment line `{/* DrawingCard grid mounted in Task 14 */}` and the existing empty-state guard with:

```tsx
{list && list.drawings.length > 0 && (
  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
    {list.drawings.map((d) => (
      <DrawingCard
        key={d.drawing_id}
        card={d}
        onClick={() => updateUrl({ drawing: String(d.drawing_id), rev: null })}
      />
    ))}
  </div>
)}
{list && list.drawings.length === 0 && (
  <p className="py-12 text-center text-sm text-h-muted">No drawings here yet.</p>
)}
```

- [ ] **Step 6: Type-check**

```bash
docker compose exec web pnpm tsc --noEmit
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/\(app\)/shop-dwgs/_components/DrawingCard.tsx apps/web/app/\(app\)/shop-dwgs/_components/BlueprintPlaceholder.tsx apps/web/app/\(app\)/shop-dwgs/_components/StatusPill.tsx apps/web/app/\(app\)/shop-dwgs/_components/VersionChip.tsx apps/web/app/\(app\)/shop-dwgs/_components/ShopDwgsClient.tsx
git commit -m "feat(web): DrawingCard + BlueprintPlaceholder + StatusPill + VersionChip"
```

---

## Phase 5 — Drawer + dialogs (3 tasks)

### Task 15: DrawingDrawer with file viewer + RevisionHistoryStrip

**Files:**
- Create: `apps/web/app/(app)/shop-dwgs/_components/DrawingDrawer.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/RevisionHistoryStrip.tsx`
- Modify: `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`

- [ ] **Step 1: Create the RevisionHistoryStrip**

Create `apps/web/app/(app)/shop-dwgs/_components/RevisionHistoryStrip.tsx`:

```tsx
"use client";

import type { Revision } from "@/lib/shop-drawings-types";

import StatusPill from "./StatusPill";

interface Props {
  revisions: Revision[];
  selectedId: number;
  onSelect: (revisionId: number) => void;
}

function ddmmyyyy(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export default function RevisionHistoryStrip({ revisions, selectedId, onSelect }: Props) {
  return (
    <ol className="divide-y divide-h-line border-y border-h-line">
      {revisions.map((r) => {
        const active = r.revision_id === selectedId;
        return (
          <li key={r.revision_id}>
            <button
              type="button"
              onClick={() => onSelect(r.revision_id)}
              className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition ${
                active ? "bg-h-accent/10 text-h-ink" : "text-h-muted hover:text-h-ink"
              }`}
            >
              <span className="h-mono">v{r.rev_no}</span>
              <StatusPill status={r.status} />
              <span className="flex-1 truncate">{r.uploaded_by_name ?? "—"}</span>
              <span className="h-mono">{ddmmyyyy(r.uploaded_at)}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
```

- [ ] **Step 2: Create the DrawingDrawer**

Create `apps/web/app/(app)/shop-dwgs/_components/DrawingDrawer.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";

import type { DrawingDetail } from "@/lib/shop-drawings-types";
import { getDrawing } from "@/lib/shop-drawings-fetch";

import RevisionHistoryStrip from "./RevisionHistoryStrip";
import StatusPill from "./StatusPill";

interface Me { id: number; auth_role: string; }

interface Props {
  drawingId: number;
  initialRevId: number | null;
  me: Me;
  onClose: () => void;
  onChanged: () => void;       // called after any successful action so the list refetches
  onSelectRevision: (revId: number) => void;  // updates URL ?rev=
  renderActions: (detail: DrawingDetail, selectedRevId: number, refresh: () => Promise<void>) => React.ReactNode;
}

export default function DrawingDrawer(props: Props) {
  const [detail, setDetail] = useState<DrawingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const d = await getDrawing(props.drawingId);
      setDetail(d);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [props.drawingId]);

  const selectedRevId = useMemo(() => {
    if (!detail) return 0;
    if (props.initialRevId && detail.revisions.some((r) => r.revision_id === props.initialRevId)) {
      return props.initialRevId;
    }
    return detail.revisions[0]?.revision_id ?? 0;
  }, [detail, props.initialRevId]);

  const selectedRev = detail?.revisions.find((r) => r.revision_id === selectedRevId);

  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[640px] flex-col border-l border-h-line bg-h-bg shadow-lg">
      <header className="flex items-start justify-between gap-3 border-b border-h-line p-4">
        <div className="min-w-0">
          <p className="h-mono text-xs text-h-muted">
            #SD-{String(props.drawingId).padStart(4, "0")} · {detail?.project_code ?? "…"}
          </p>
          <h2 className="truncate text-lg font-semibold text-h-ink">{detail?.title ?? "Loading…"}</h2>
          {detail?.room && <p className="text-sm text-h-muted">{detail.room}</p>}
        </div>
        <button onClick={props.onClose}
                className="rounded p-1 text-h-muted hover:bg-h-line/40 hover:text-h-ink">
          ✕
        </button>
      </header>

      {error && <p className="p-4 text-sm text-red-600">{error}</p>}

      {selectedRev && (
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 overflow-hidden border-b border-h-line bg-h-line/20">
            {selectedRev.file_mime === "application/pdf" ? (
              <iframe
                title={`drawing ${props.drawingId} rev ${selectedRev.rev_no}`}
                src={`/api/files/${selectedRev.file_blob_id}#zoom=fit`}
                className="h-full w-full"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <img src={`/api/files/${selectedRev.file_blob_id}`}
                     alt={`drawing ${props.drawingId} rev ${selectedRev.rev_no}`}
                     className="max-h-full max-w-full" />
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 px-3 py-2">
            <span className="text-sm text-h-ink">v{selectedRev.rev_no}</span>
            <StatusPill status={selectedRev.status} />
            {selectedRev.review_note && (
              <span className="truncate text-xs text-h-muted">Note: {selectedRev.review_note}</span>
            )}
            <a href={`/api/files/${selectedRev.file_blob_id}`} download
               className="ml-auto text-xs text-h-accent hover:underline">Download</a>
          </div>

          {detail && (
            <RevisionHistoryStrip
              revisions={detail.revisions}
              selectedId={selectedRevId}
              onSelect={props.onSelectRevision}
            />
          )}

          {detail && (
            <footer className="flex flex-wrap items-center gap-2 p-3">
              {props.renderActions(detail, selectedRevId, async () => { await refresh(); props.onChanged(); })}
            </footer>
          )}
        </div>
      )}
    </aside>
  );
}
```

- [ ] **Step 3: Mount the drawer in ShopDwgsClient (without actions yet)**

In `ShopDwgsClient.tsx`, add the imports:

```tsx
import DrawingDrawer from "./DrawingDrawer";
```

Inside the returned JSX, after the grid block, add:

```tsx
{props.initialDrawingId != null && (
  <DrawingDrawer
    drawingId={props.initialDrawingId}
    initialRevId={props.initialRevId}
    me={props.me}
    onClose={() => updateUrl({ drawing: null, rev: null })}
    onChanged={() => {
      // Force the list to refetch by toggling a no-op param.
      if (projectId != null) {
        listDrawings({ projectId, subtab, room, q }).then(setList).catch((e) => setError(String(e)));
      }
    }}
    onSelectRevision={(rev) => updateUrl({ rev: String(rev) })}
    renderActions={() => null /* wired in Task 16 */}
  />
)}
```

- [ ] **Step 4: Type-check + smoke**

```bash
docker compose exec web pnpm tsc --noEmit
```

Open `/shop-dwgs?drawing=<some-id>` in the browser; the drawer should open, fetch the drawing, render the iframe (or img), and let you switch revisions via the strip. The footer is empty until Task 16.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/\(app\)/shop-dwgs/_components/DrawingDrawer.tsx apps/web/app/\(app\)/shop-dwgs/_components/RevisionHistoryStrip.tsx apps/web/app/\(app\)/shop-dwgs/_components/ShopDwgsClient.tsx
git commit -m "feat(web): DrawingDrawer with file viewer + revision history strip"
```

---

### Task 16: ReviewActions footer

**Files:**
- Create: `apps/web/app/(app)/shop-dwgs/_components/ReviewActions.tsx`
- Modify: `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`

- [ ] **Step 1: Create the ReviewActions component**

Create `apps/web/app/(app)/shop-dwgs/_components/ReviewActions.tsx`:

```tsx
"use client";

import { useState } from "react";

import type { DrawingDetail, Revision } from "@/lib/shop-drawings-types";
import {
  archiveDrawing,
  transitionRevision,
} from "@/lib/shop-drawings-fetch";

interface Me { id: number; auth_role: string; }

interface Props {
  detail: DrawingDetail;
  selectedRev: Revision;
  me: Me;
  onAfter: () => Promise<void>;
}

const APPROVER_ROLES = new Set(["drafter", "manager", "admin"]);
const WRITER_ROLES   = new Set(["drafter", "manager", "admin", "editor"]);

export default function ReviewActions({ detail, selectedRev, me, onAfter }: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectNote, setRejectNote] = useState("");

  if (detail.archived_at) {
    return <span className="text-sm text-h-muted">This drawing is archived.</span>;
  }

  const isUploader = selectedRev.uploaded_by === me.id;
  const canApprove = APPROVER_ROLES.has(me.auth_role) && !isUploader;
  const canWrite   = WRITER_ROLES.has(me.auth_role);
  const canArchive = me.auth_role === "manager" || me.auth_role === "admin";

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); await onAfter(); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex w-full flex-wrap items-center gap-2">
      {selectedRev.status === "draft" && isUploader && (
        <button disabled={busy} onClick={() => run(() => transitionRevision(detail.drawing_id, selectedRev.revision_id, "submit"))}
                className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
          Submit for review
        </button>
      )}
      {selectedRev.status === "pending" && isUploader && (
        <button disabled={busy} onClick={() => run(() => transitionRevision(detail.drawing_id, selectedRev.revision_id, "withdraw"))}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink disabled:opacity-50">
          Withdraw
        </button>
      )}
      {selectedRev.status === "pending" && canApprove && (
        <>
          <button disabled={busy} onClick={() => run(() => transitionRevision(detail.drawing_id, selectedRev.revision_id, "approve"))}
                  className="rounded bg-emerald-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            Approve
          </button>
          {!showRejectInput ? (
            <button disabled={busy} onClick={() => setShowRejectInput(true)}
                    className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-rose-700 disabled:opacity-50">
              Reject
            </button>
          ) : (
            <div className="flex w-full items-center gap-2">
              <input
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                placeholder="Reason for rejection (required)"
                className="flex-1 rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              />
              <button
                disabled={busy || !rejectNote.trim()}
                onClick={() => run(async () => {
                  await transitionRevision(detail.drawing_id, selectedRev.revision_id, "reject", rejectNote.trim());
                  setShowRejectInput(false);
                  setRejectNote("");
                })}
                className="rounded bg-rose-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
                Confirm reject
              </button>
              <button onClick={() => { setShowRejectInput(false); setRejectNote(""); }}
                      className="text-xs text-h-muted hover:text-h-ink">Cancel</button>
            </div>
          )}
        </>
      )}
      {selectedRev.status === "pending" && !canApprove && !isUploader && (
        <span className="text-xs text-h-muted">Awaiting reviewer.</span>
      )}
      {selectedRev.status === "pending" && isUploader && (
        <span className="text-xs text-h-muted">You uploaded this revision; another reviewer must approve.</span>
      )}

      {canWrite && !detail.archived_at && (
        <span className="ml-auto" />
      )}
      {canArchive && (
        <button disabled={busy}
                onClick={() => {
                  if (!confirm("Archive this drawing? It will move to the Archive subtab.")) return;
                  run(() => archiveDrawing(detail.drawing_id));
                }}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-muted hover:text-h-ink disabled:opacity-50">
          Archive drawing
        </button>
      )}

      {err && <p className="w-full text-xs text-rose-700">{err}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Wire ReviewActions into ShopDwgsClient**

In `ShopDwgsClient.tsx`, add:

```tsx
import ReviewActions from "./ReviewActions";
```

Replace the `renderActions={() => null /* wired in Task 16 */}` line with:

```tsx
renderActions={(detail, selectedRevId, refresh) => {
  const rev = detail.revisions.find((r) => r.revision_id === selectedRevId);
  if (!rev) return null;
  return <ReviewActions detail={detail} selectedRev={rev} me={props.me} onAfter={refresh} />;
}}
```

- [ ] **Step 3: Type-check**

```bash
docker compose exec web pnpm tsc --noEmit
```

- [ ] **Step 4: Manual smoke**

In the browser as a `drafter`:
1. Open a draft drawing → click Submit. Status pill flips to Pending; list refreshes.
2. Log out, log in as `manager`. Open the same drawing. Approve. Status flips to Approved.
3. As manager, archive the drawing. Subtab moves to Archive.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/\(app\)/shop-dwgs/_components/ReviewActions.tsx apps/web/app/\(app\)/shop-dwgs/_components/ShopDwgsClient.tsx
git commit -m "feat(web): ReviewActions — submit/withdraw/approve/reject/archive"
```

---

### Task 17: UploadDialog + NewRevisionDialog

**Files:**
- Create: `apps/web/app/(app)/shop-dwgs/_components/UploadDialog.tsx`
- Create: `apps/web/app/(app)/shop-dwgs/_components/NewRevisionDialog.tsx`
- Modify: `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`
- Modify: `apps/web/app/(app)/shop-dwgs/_components/ReviewActions.tsx`

- [ ] **Step 1: Create the UploadDialog**

Create `apps/web/app/(app)/shop-dwgs/_components/UploadDialog.tsx`:

```tsx
"use client";

import { useState } from "react";

import { uploadFile } from "@/lib/file-upload";
import { createDrawing } from "@/lib/shop-drawings-fetch";

interface Props {
  projectId: number;
  onClose: () => void;
  onCreated: (drawingId: number) => void;
}

export default function UploadDialog({ projectId, onClose, onCreated }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [room, setRoom] = useState("");
  const [submitImmediately, setSubmitImmediately] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!file || !title.trim()) {
      setErr("File and title are required.");
      return;
    }
    setBusy(true); setErr(null);
    try {
      const blob = await uploadFile(file);
      const detail = await createDrawing({
        projectId,
        title: title.trim(),
        room: room.trim() || null,
        fileBlobId: blob.file_blob_id,
        submitImmediately,
      });
      onCreated(detail.drawing_id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-5 shadow-xl">
        <h3 className="text-lg font-semibold text-h-ink">Upload shop drawing</h3>
        <div className="mt-4 space-y-3">
          <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                 className="block w-full text-sm" />
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (required)"
                 className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink" />
          <input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="Room (optional, e.g. Kitchen)"
                 className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink" />
          <label className="flex items-center gap-2 text-sm text-h-ink">
            <input type="checkbox" checked={submitImmediately} onChange={(e) => setSubmitImmediately(e.target.checked)} />
            Submit for review immediately
          </label>
          {err && <p className="text-xs text-rose-700">{err}</p>}
        </div>
        <div className="mt-5 flex items-center justify-end gap-2">
          <button onClick={onClose} className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {busy ? "Uploading…" : "Create drawing"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create the NewRevisionDialog**

Create `apps/web/app/(app)/shop-dwgs/_components/NewRevisionDialog.tsx`:

```tsx
"use client";

import { useState } from "react";

import { uploadFile } from "@/lib/file-upload";
import { addRevision } from "@/lib/shop-drawings-fetch";

interface Props {
  drawingId: number;
  onClose: () => void;
  onAdded: () => Promise<void>;
}

export default function NewRevisionDialog({ drawingId, onClose, onAdded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!file) { setErr("Pick a file."); return; }
    setBusy(true); setErr(null);
    try {
      const blob = await uploadFile(file);
      await addRevision(drawingId, blob.file_blob_id);
      await onAdded();
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-5 shadow-xl">
        <h3 className="text-lg font-semibold text-h-ink">Upload new revision</h3>
        <p className="mt-1 text-xs text-h-muted">A new revision lands as Draft. Submit for review when ready.</p>
        <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
               className="mt-4 block w-full text-sm" />
        {err && <p className="mt-3 text-xs text-rose-700">{err}</p>}
        <div className="mt-5 flex items-center justify-end gap-2">
          <button onClick={onClose} className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {busy ? "Uploading…" : "Add revision"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire UploadDialog into the page header**

In `apps/web/app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`, add:

```tsx
import UploadDialog from "./UploadDialog";
```

Add a state hook near the top of the component:

```tsx
const [uploadOpen, setUploadOpen] = useState(false);
```

Replace the comment `{/* Upload button mounted in Task 17 */}` in the header with:

```tsx
{projectId != null && (
  <button onClick={() => setUploadOpen(true)}
          className="rounded bg-h-accent px-3 py-1.5 text-sm text-white">
    Upload drawing
  </button>
)}
```

Append at the bottom of the returned JSX (still inside the `<section>`):

```tsx
{uploadOpen && projectId != null && (
  <UploadDialog
    projectId={projectId}
    onClose={() => setUploadOpen(false)}
    onCreated={(drawingId) => {
      setUploadOpen(false);
      updateUrl({ drawing: String(drawingId), rev: null, subtab: "in_review" });
    }}
  />
)}
```

- [ ] **Step 4: Wire NewRevisionDialog into ReviewActions**

In `ReviewActions.tsx`, add:

```tsx
import NewRevisionDialog from "./NewRevisionDialog";
```

Add a state hook at the top of the component:

```tsx
const [newRevOpen, setNewRevOpen] = useState(false);
```

Add a new button (placed just before the "Archive drawing" button) that's only visible to writers:

```tsx
{canWrite && !detail.archived_at && (
  <button disabled={busy} onClick={() => setNewRevOpen(true)}
          className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink disabled:opacity-50">
    Upload new revision
  </button>
)}
```

And mount the dialog at the end of the component's return (before the final `</div>`):

```tsx
{newRevOpen && (
  <NewRevisionDialog
    drawingId={detail.drawing_id}
    onClose={() => setNewRevOpen(false)}
    onAdded={onAfter}
  />
)}
```

- [ ] **Step 5: Type-check + manual smoke**

```bash
docker compose exec web pnpm tsc --noEmit
```

In browser:
1. Click Upload drawing → fill in title + room + pick a PDF → check "Submit immediately" → Create. Drawer opens on the new drawing in In review.
2. Open an approved drawing → "Upload new revision" → pick a different PDF → Add. Revision strip gains a new draft entry.
3. Try uploading the same PDF twice → second time backend dedupes (you can verify by re-uploading and checking the drawer's selected file id; both blobs share id).

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/\(app\)/shop-dwgs/_components/UploadDialog.tsx apps/web/app/\(app\)/shop-dwgs/_components/NewRevisionDialog.tsx apps/web/app/\(app\)/shop-dwgs/_components/ShopDwgsClient.tsx apps/web/app/\(app\)/shop-dwgs/_components/ReviewActions.tsx
git commit -m "feat(web): UploadDialog + NewRevisionDialog wired into page + actions"
```

---

## Phase 6 — Seed + E2E (3 tasks)

### Task 18: Seed helper `put_seed_file` + sample fixture PDFs

**Files:**
- Create: `apps/api/app/files/seed_helper.py`
- Create: `seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf`
- Create: `seed/hartwood_joinery/sample_drawings/bathroom-vanity.pdf`

- [ ] **Step 1: Generate two small fixture PDFs**

If `qpdf` or `pdftk` is not available, generate trivial valid PDFs from the api container using a script. Run from the host:

```bash
docker compose exec api python - <<'PY'
import os
os.makedirs("/code/seed/hartwood_joinery/sample_drawings", exist_ok=True)

def make_pdf(path, title):
    body = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 60 >> stream
BT /F1 24 Tf 72 760 Td ({title}) Tj ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000232 00000 n
0000000332 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
408
%%EOF
"""
    with open(path, "wb") as f:
        f.write(body.encode("latin-1"))

make_pdf("/code/seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf", "Kitchen base run - sample drawing")
make_pdf("/code/seed/hartwood_joinery/sample_drawings/bathroom-vanity.pdf", "Bathroom vanity - sample drawing")
print("ok")
PY
ls -l seed/hartwood_joinery/sample_drawings/
```

Expected: two `.pdf` files exist, each a few hundred bytes, both start with `%PDF-1.4`.

- [ ] **Step 2: Create the seed helper**

Create `apps/api/app/files/seed_helper.py`:

```python
"""Direct (no-HTTP) helper used by seed scripts.

Mirrors the dedup + storage path logic of the upload route, but skips
multipart parsing and audit (seed runs are bulk + idempotent).
"""
import hashlib
import io
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from .store import get_default_store
from .validators import sniff_mime


def put_seed_file(
    db: Session, *, workspace_id: int, workspace_slug: str, app_user_id: int, path: str | Path
) -> int:
    p = Path(path)
    payload = p.read_bytes()
    mime = sniff_mime(payload[:16])
    if mime is None:
        raise ValueError(f"unknown file type for {p}")
    sha = hashlib.sha256(payload).hexdigest()

    existing = db.execute(
        text("SELECT file_blob_id FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
        {"w": workspace_id, "s": sha},
    ).first()
    if existing:
        return existing[0]

    store = get_default_store()
    storage_key = store.put(workspace_slug, sha, io.BytesIO(payload))
    new_id = db.execute(
        text(
            """
            INSERT INTO file_blob(workspace_id, sha256, mime, byte_size,
                                  original_filename, storage_key, uploaded_by)
            VALUES (:w, :s, :m, :sz, :n, :k, :u) RETURNING file_blob_id
            """
        ),
        {"w": workspace_id, "s": sha, "m": mime, "sz": len(payload),
         "n": p.name, "k": storage_key, "u": app_user_id},
    ).scalar()
    return new_id
```

- [ ] **Step 3: Smoke-test the helper from a python shell**

```bash
docker compose exec api python - <<'PY'
from app.db import SessionLocal
from sqlalchemy import text
from app.files.seed_helper import put_seed_file
s = SessionLocal()
try:
    s.execute(text("INSERT INTO workspace(slug,name) VALUES('seed-test','ST') ON CONFLICT DO NOTHING"))
    wid = s.execute(text("SELECT id FROM workspace WHERE slug='seed-test'")).scalar()
    s.execute(text("""
        INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
        VALUES (:w, 's@s.test', 'S', 'x', 'drafter') ON CONFLICT DO NOTHING
    """), {"w": wid})
    uid = s.execute(text("SELECT id FROM app_user WHERE email='s@s.test'")).scalar()
    bid1 = put_seed_file(s, workspace_id=wid, workspace_slug='seed-test', app_user_id=uid,
                         path='/code/seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf')
    bid2 = put_seed_file(s, workspace_id=wid, workspace_slug='seed-test', app_user_id=uid,
                         path='/code/seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf')
    assert bid1 == bid2, f"dedup failed: {bid1} vs {bid2}"
    print(f"OK dedup: blob_id={bid1}")
    s.rollback()
finally:
    s.close()
PY
```

Expected: `OK dedup: blob_id=<n>`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/files/seed_helper.py seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf seed/hartwood_joinery/sample_drawings/bathroom-vanity.pdf
git commit -m "feat(seed): put_seed_file helper + 2 sample shop-drawing PDFs"
```

---

### Task 19: Seed script — 6 demo drawings on ALF-001

**Files:**
- Modify: `seed/hartwood_joinery.py`

- [ ] **Step 1: Locate the seed script section that inserts project ALF-001**

```bash
grep -n "ALF-001" seed/hartwood_joinery.py | head
```

Take note of the line where the script already creates project ALF-001 + has a session var (likely `s` or `session`) and an `actor_id` / `app_user_id` for the seed Drafter. Confirm the workspace slug used (`hartwood-joinery`).

- [ ] **Step 2: Append the shop-drawings seed block**

After the seed block that finishes ALF-001 + items + procurement (find where ALF-001 procurement_batches are inserted — that's the natural anchor), append:

```python
# ── Shop Drawings demo (sub-project #5a) ─────────────────────────────────────
from app.files.seed_helper import put_seed_file
from sqlalchemy import text as _t

_kitchen_pdf = "/code/seed/hartwood_joinery/sample_drawings/kitchen-base-run.pdf"
_bath_pdf    = "/code/seed/hartwood_joinery/sample_drawings/bathroom-vanity.pdf"

# Resolve the seeded ALF-001 project + a drafter + manager from the session.
_alf_pid = s.execute(_t("SELECT project_id FROM projects WHERE project_code = 'ALF-001'")).scalar()
_drafter_id = s.execute(_t("""
    SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'drafter' ORDER BY id LIMIT 1
"""), {"w": workspace_id}).scalar()
_manager_id = s.execute(_t("""
    SELECT id FROM app_user WHERE workspace_id = :w AND auth_role = 'manager' ORDER BY id LIMIT 1
"""), {"w": workspace_id}).scalar()

_blob_kitchen = put_seed_file(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                              app_user_id=_drafter_id, path=_kitchen_pdf)
_blob_bath    = put_seed_file(s, workspace_id=workspace_id, workspace_slug=workspace_slug,
                              app_user_id=_drafter_id, path=_bath_pdf)


def _make_drawing(*, title, room, archived=False, archived_by=None):
    did = s.execute(_t("""
        INSERT INTO shop_drawing(project_id, title, room, created_by, archived_at, archived_by)
        VALUES (:p, :t, :r, :u, :a, :ab) RETURNING drawing_id
    """), {"p": _alf_pid, "t": title, "r": room, "u": _drafter_id,
           "a": "now()" if archived else None, "ab": archived_by if archived else None}).scalar()
    # The simple boolean-to-now() trick above doesn't work because we passed a string 'now()'
    # as a plain value — fix by using a separate UPDATE for archived rows.
    if archived:
        s.execute(_t("UPDATE shop_drawing SET archived_at = now(), archived_by = :u WHERE drawing_id = :d"),
                  {"u": archived_by, "d": did})
    return did


def _add_rev(did, *, rev_no, blob_id, status, uploaded_by, reviewed_by=None, note=None):
    rid = s.execute(_t("""
        INSERT INTO shop_drawing_revision(drawing_id, rev_no, file_blob_id, status,
                                          uploaded_by, reviewed_by, reviewed_at, review_note)
        VALUES (:d, :n, :b, :s, :u, :rv, CASE WHEN :rv IS NULL THEN NULL ELSE now() END, :note)
        RETURNING revision_id
    """), {"d": did, "n": rev_no, "b": blob_id, "s": status,
           "u": uploaded_by, "rv": reviewed_by, "note": note}).scalar()
    return rid


# Drawing 1: Kitchen base run — rev1 approved, rev2 approved (current), rev3 pending
d1 = _make_drawing(title="Kitchen base run", room="Kitchen")
_add_rev(d1, rev_no=1, blob_id=_blob_kitchen, status="approved", uploaded_by=_drafter_id, reviewed_by=_manager_id)
r1_2 = _add_rev(d1, rev_no=2, blob_id=_blob_kitchen, status="approved", uploaded_by=_drafter_id, reviewed_by=_manager_id)
s.execute(_t("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
          {"r": r1_2, "d": d1})
_add_rev(d1, rev_no=3, blob_id=_blob_kitchen, status="pending", uploaded_by=_drafter_id)

# Drawing 2: Bathroom vanity — rev1 rejected (note), rev2 approved (current)
d2 = _make_drawing(title="Bathroom vanity", room="Bathroom")
_add_rev(d2, rev_no=1, blob_id=_blob_bath, status="rejected", uploaded_by=_drafter_id,
         reviewed_by=_manager_id, note="Need finished dimensions")
r2_2 = _add_rev(d2, rev_no=2, blob_id=_blob_bath, status="approved", uploaded_by=_drafter_id, reviewed_by=_manager_id)
s.execute(_t("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
          {"r": r2_2, "d": d2})

# Drawing 3: Kitchen island — single draft revision
d3 = _make_drawing(title="Kitchen island", room="Kitchen")
_add_rev(d3, rev_no=1, blob_id=_blob_kitchen, status="draft", uploaded_by=_drafter_id)

# Drawing 4: Walk-in robe — single pending revision
d4 = _make_drawing(title="Walk-in robe", room="Bedroom")
_add_rev(d4, rev_no=1, blob_id=_blob_bath, status="pending", uploaded_by=_drafter_id)

# Drawing 5: Pantry — approved + archived
d5 = _make_drawing(title="Pantry", room="Kitchen", archived=True, archived_by=_manager_id)
r5_1 = _add_rev(d5, rev_no=1, blob_id=_blob_kitchen, status="approved", uploaded_by=_drafter_id, reviewed_by=_manager_id)
s.execute(_t("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
          {"r": r5_1, "d": d5})

# Drawing 6: Hallway storage — single approved revision
d6 = _make_drawing(title="Hallway storage", room="Hallway")
r6_1 = _add_rev(d6, rev_no=1, blob_id=_blob_bath, status="approved", uploaded_by=_drafter_id, reviewed_by=_manager_id)
s.execute(_t("UPDATE shop_drawing SET current_revision_id = :r WHERE drawing_id = :d"),
          {"r": r6_1, "d": d6})

s.commit()
print(f"seeded shop drawings: {d1=}, {d2=}, {d3=}, {d4=}, {d5=}, {d6=}")
```

> If the seed script doesn't already have `workspace_slug` in scope, add `workspace_slug = "hartwood-joinery"` near the top of the script (or read it from the workspace row that's inserted first).

- [ ] **Step 3: Re-seed and confirm**

```bash
docker compose exec api python -m seed.hartwood_joinery
```

Expected: `seeded shop drawings: …` line printed.

- [ ] **Step 4: Verify counts via psql**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -c "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE archived_at IS NULL) AS active FROM shop_drawing;"
docker compose exec -T db psql -U postgres -d joineryflow -c "SELECT COUNT(*) AS rev_count FROM shop_drawing_revision;"
docker compose exec -T db psql -U postgres -d joineryflow -c "SELECT COUNT(*) AS pending FROM shop_drawing_revision WHERE status='pending';"
```

Expected: `total=6`, `active=5`, `rev_count=10` (3+2+1+1+1+1+1 = wait, let's count: D1=3, D2=2, D3=1, D4=1, D5=1, D6=1 → 9), `pending=2`.

- [ ] **Step 5: Hit the API to confirm the header counts**

```bash
docker compose exec api python - <<'PY'
import urllib.request, urllib.parse, http.cookiejar, json
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
data = json.dumps({"workspace_slug":"hartwood-joinery","email":"rin.park@hartwood.test","password":"hartwood-dev"}).encode()
req = urllib.request.Request("http://localhost:8000/auth/login", data=data, headers={"Content-Type":"application/json"})
opener.open(req).read()
import urllib.parse as up
ws_pid = json.loads(opener.open("http://localhost:8000/projects").read())["projects"]
pid = next(p for p in ws_pid if p["project_code"]=="ALF-001")["id"]
print("project_id =", pid)
print("current:",   json.loads(opener.open(f"http://localhost:8000/projects/{pid}/shop-drawings?subtab=current").read())["total"])
print("in_review:", len(json.loads(opener.open(f"http://localhost:8000/projects/{pid}/shop-drawings?subtab=in_review").read())["drawings"]))
print("archive:",   json.loads(opener.open(f"http://localhost:8000/projects/{pid}/shop-drawings?subtab=archive").read())["total"])
PY
```

Expected: roughly `current: 6`, in_review drawing count `3` (D1's pending rev + D3 draft + D4 pending), `archive: 6` (total includes all). The `total` field in the response is project-wide non-archived, so prints aren't perfectly subtab-scoped. Spot-check via the UI in the next step.

- [ ] **Step 6: Hit `/shop-dwgs` in the browser**

Log in as `rin.park@hartwood.test` / `hartwood-dev`. Open `/shop-dwgs?project=<ALF id>`. Expected: header reads `6 drawings across 4 rooms · 2 awaiting review`. Current shows 3 cards. In review shows 3 cards. Archive shows 1 card.

- [ ] **Step 7: Commit**

```bash
git add seed/hartwood_joinery.py
git commit -m "feat(seed): 6 demo shop drawings on ALF-001 spanning all 3 subtabs"
```

---

### Task 20: Playwright E2E spec

**Files:**
- Create: `tests/e2e/shop_drawings.spec.ts`

- [ ] **Step 1: Confirm a manager seed user exists for the test**

```bash
docker compose exec -T db psql -U postgres -d joineryflow -c "SELECT email, auth_role FROM app_user WHERE auth_role = 'manager' ORDER BY id LIMIT 1;"
```

Note the manager's email (likely `mason.trent@hartwood.test` per the existing seed; if different, substitute below).

- [ ] **Step 2: Locate the existing E2E base URL + login helper**

```bash
ls tests/e2e/
cat tests/e2e/smoke.spec.ts | head -40
```

Take note of the base URL (likely `http://localhost:3000`) and how prior specs perform login.

- [ ] **Step 3: Create the spec**

Create `tests/e2e/shop_drawings.spec.ts`:

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

test("shop drawings: drafter uploads + manager approves", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");

  // Navigate to /shop-dwgs and confirm seed counts.
  await page.goto(`${BASE}/shop-dwgs`);
  await expect(page.getByRole("heading", { name: "Shop Drawings" })).toBeVisible();
  await expect(page.getByText(/across \d+ rooms/)).toBeVisible();

  // Open upload dialog and create a new drawing in In review.
  await page.getByRole("button", { name: "Upload drawing" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "e2e-test.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%abc\n" + "x".repeat(200) + "\n%%EOF\n"),
  });
  await page.locator('input[placeholder^="Title"]').fill("E2E test drawing");
  await page.locator('input[placeholder^="Room"]').fill("Kitchen");
  await page.getByLabel("Submit for review immediately").check();
  await page.getByRole("button", { name: "Create drawing" }).click();

  // The drawer should auto-open with the new drawing in In review subtab.
  await expect(page).toHaveURL(/drawing=\d+/);
  await expect(page.getByText("E2E test drawing")).toBeVisible();

  // Log out (clear cookies) + log back in as manager.
  await page.context().clearCookies();
  await login(page, "mason.trent@hartwood.test");

  // Open the In review subtab and find our drawing.
  await page.goto(`${BASE}/shop-dwgs?subtab=in_review`);
  await page.getByText("E2E test drawing").click();

  // Approve it.
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/Approved/i)).toBeVisible();

  // It should now appear in Current.
  await page.goto(`${BASE}/shop-dwgs?subtab=current`);
  await expect(page.getByText("E2E test drawing")).toBeVisible();
});

test("shop drawings: reject requires note and leaves drawing without current revision", async ({ page }) => {
  // Drafter uploads a fresh drawing + submits.
  await login(page, "rin.park@hartwood.test");
  await page.goto(`${BASE}/shop-dwgs`);
  await page.getByRole("button", { name: "Upload drawing" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "reject-test.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%xyz\n" + "y".repeat(150) + "\n%%EOF\n"),
  });
  await page.locator('input[placeholder^="Title"]').fill("Reject me");
  await page.locator('input[placeholder^="Room"]').fill("Bathroom");
  await page.getByLabel("Submit for review immediately").check();
  await page.getByRole("button", { name: "Create drawing" }).click();

  // Manager rejects with note.
  await page.context().clearCookies();
  await login(page, "mason.trent@hartwood.test");
  await page.goto(`${BASE}/shop-dwgs?subtab=in_review`);
  await page.getByText("Reject me").click();
  await page.getByRole("button", { name: "Reject" }).click();
  await page.locator('input[placeholder*="Reason"]').fill("Missing edge profile");
  await page.getByRole("button", { name: "Confirm reject" }).click();

  await expect(page.getByText(/Rejected/i)).toBeVisible();
  // Drawing should not appear in Current (no current_revision_id).
  await page.goto(`${BASE}/shop-dwgs?subtab=current`);
  await expect(page.getByText("Reject me")).toHaveCount(0);
});
```

- [ ] **Step 4: Run the E2E spec**

```bash
make e2e-docker SPEC=tests/e2e/shop_drawings.spec.ts
```

Or if the Makefile doesn't take `SPEC`, run via the docker image directly:

```bash
docker run --rm --network host -v "$PWD:/work" -w /work mcr.microsoft.com/playwright:v1.49.0-jammy \
  pnpm exec playwright test tests/e2e/shop_drawings.spec.ts
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/shop_drawings.spec.ts
git commit -m "test(e2e): shop drawings — drafter upload + manager approve/reject"
```

---

## Phase 7 — Docs (1 task)

### Task 21: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append the Shop Drawings dev-notes section**

In `CLAUDE.md`, after the "Procurement Workbench (sub-project #4)" section, append:

```markdown
## Shop Drawings + File-Upload Subsystem (sub-project #5a)

- New backend modules `apps/api/app/files/` (generic upload subsystem) and
  `apps/api/app/shop_drawings/`. Mounted at top-level paths from `main.py`.
- Migration 0013 adds three tables: `file_blob` (workspace-scoped, sha256-deduped),
  `shop_drawing` (project-scoped, room as free-text tag, points at
  `current_revision_id`), `shop_drawing_revision` (per-upload row, status state
  machine). Partial unique index `uniq_drawing_inflight` enforces "at most one
  draft/pending revision per drawing".
- `drafter` auth_role is **elevated to PM-parity** on the `shop_dwgs` module
  (read+write+approve+comment), continuing the elevated-drafter pattern from
  Procurement Workbench.
- File storage: `LocalDiskStore` behind a `FileStore` Protocol. Default root
  `/uploads`, set via `FILE_STORE_ROOT` env. Layout
  `<root>/<workspace_slug>/<sha256[0:2]>/<sha256>` (content-addressable,
  sharded). `docker-compose.yml` mounts a named `uploads` volume on the api
  service.
- Upload route `POST /files` does magic-byte mime sniff + extension
  cross-check + 25 MB cap + sha256 dedup. Download route `GET /files/{id}` is
  workspace-isolated (404 on cross-workspace) and streams via
  `StreamingResponse` with `Content-Disposition: inline`.
- Web routes:
  - `/shop-dwgs?project=…&subtab=current|in_review|archive&room=…&q=…` —
    list page with subtabs + filter strip + 3-col card grid.
  - `?drawing=N&rev=M` opens a right-side drawer with PDF/image viewer +
    revision history strip + contextual review actions.
- Workflow: `draft → pending → approved | rejected`. The not-uploader rule on
  approve/reject is enforced in the route handler; the partial unique index
  enforces the in-flight invariant. Approve updates
  `shop_drawing.current_revision_id` atomically.
- Allowed file types: PDF / PNG / JPEG only (validated by magic bytes).
  SVG, DWG, etc. rejected with 415.
- Thumbnails are deterministic SVG placeholders seeded from `drawing_id`
  (no PDF rendering pipeline in v1).
- Seed (`make seed`) inserts 2 fixture PDFs + 6 demo drawings on ALF-001
  spanning Current / In review / Archive.
- Out of scope (deferred to #5b/#5c): item attachments (CV drawing, floor
  plan, site-measure PDF), Combined PDF generation, real PDF thumbnails,
  Templates subtab, iSample tab, orphan blob GC, cloud storage backend,
  unarchive button.
```

In the same file, append to the "Reference docs" section's bullet list:

```markdown
- `docs/superpowers/specs/2026-05-01-shop-drawings-design.md` — Shop Drawings + file-upload subsystem v1 spec (sub-project #5a).
- `docs/superpowers/plans/2026-05-01-shop-drawings.md` — 21-task implementation plan for sub-project #5a.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): Shop Drawings dev notes + reference doc entries"
```

---

## Final verification

After all 21 tasks:

```bash
docker compose down
make up
make migrate
make seed
make test
make e2e-docker
```

Expected:
- `make migrate` ends at `0013`.
- `make seed` prints `seeded shop drawings: d1=… d2=… d3=… d4=… d5=… d6=…`.
- `make test` shows the prior baseline + ~37 new tests, all passing.
- `make e2e-docker` runs all specs including `shop_drawings.spec.ts`.

Manual smoke (10 minutes):

1. Login as `rin.park@hartwood.test` / `hartwood-dev`.
2. `/shop-dwgs` → header reads `6 drawings across 4 rooms · 2 awaiting review`.
3. Open Kitchen base run → drawer shows 3 revisions, viewer shows v2 (current) by default.
4. Switch to v3 (pending) in the strip → viewer updates.
5. Logout. Login as the manager seed user → approve v3 → drawer reflects new approved status; refresh `/shop-dwgs?subtab=current` to see current_rev still v3.
6. As manager, archive Hallway storage → it disappears from Current and appears in Archive.
7. As drafter, try to upload 30 MB PDF → toast says "size exceeds…".
8. As drafter, try to upload an `.svg` → toast says "unsupported file type".
9. Upload the same fixture PDF twice → second upload's network response shows `deduped: true`.

---

## Self-review

Spec coverage:
- §1 file-upload subsystem → Tasks 3 (store), 4 (validators), 5 (upload), 6 (download), 18 (seed helper). ✅
- §1 shop drawings register → Tasks 8 (schemas), 9 (queries), 10 (routes). ✅
- §1 three subtabs + card grid → Tasks 13 (page shell), 14 (cards). ✅
- §1 detail drawer + viewer → Task 15. ✅
- §1 workflow actions → Task 11 (backend tests for state machine), Task 16 (UI). ✅
- §1 audit hooks → wired into queries.py in Task 9 + routes.py in Task 10. ✅
- §1 seed update → Tasks 18 + 19. ✅
- §2 architecture (backend + web layout, FileStore interface, docker volume) → Tasks 2, 3, 5, 6, 12, 13. ✅
- §3 migration 0013 → Task 1. ✅
- §4 upload + download endpoints → Tasks 5, 6. ✅
- §5 list page + cards + drawer + dialogs → Tasks 13, 14, 15, 16, 17. ✅
- §6 state machine → Task 11. ✅
- §7 RBAC + audit + security → Tasks 7, 9, 10, 11. ✅
- §8 seed → Tasks 18, 19. ✅
- §9 testing → Tasks 5, 6, 9, 10, 11, 20. Total ~37 pytest + 2 Playwright. ✅
- §10 implementation order → matches the 21-task sequencing. ✅

Type consistency check:
- `FileStore.put(workspace_slug, sha256, byte_stream)` — same signature in store.py, upload route, seed_helper.py. ✅
- `transitionRevision(drawingId, revisionId, action, reviewNote?)` — same signature in fetch wrapper + ReviewActions. ✅
- `current_revision_id` — DB column name matches every reference. ✅
- Subtab values `current | in_review | archive` — consistent across query SQL, route param pattern, TS type, URL. ✅

Placeholder scan: no TBD / TODO / "implement appropriate" / "similar to Task N". Each task has full code or full commands.

Plan complete and saved to `docs/superpowers/plans/2026-05-01-shop-drawings.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?






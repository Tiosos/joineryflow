# JoineryFlow Shop Drawings + File-Upload Subsystem — Design Spec

**Date:** 2026-05-01
**Sub-project:** #5a (first slice of sub-project #5; sibling slices #5b PDF generation and #5c iSample are independent and follow)
**Branch base:** `feat/foundation` (post Procurement Workbench merge)
**Prior context:** `docs/superpowers/specs/2026-04-22-foundation-design.md`, `docs/superpowers/specs/2026-04-25-pm-workbench-design.md`, `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md`, `legacy/product_spec.md` §10.6, `legacy/trackingv2.md` §11

---

## 0. Goal

A Drafter can upload a PDF (or PNG/JPG) shop drawing for a project, tag it with a room, and submit it for review. A Manager or Admin can approve or reject with a note. Drawings render as cards on `/shop-dwgs` across three subtabs (Current / In review / Archive), filterable by room/status/reviewer/project. Uploaded files are RBAC-gated, content-addressable, deduped per workspace, and stored on local disk behind a swappable `FileStore` interface so cloud migration later is a one-file change.

This sub-project also lays down the **file-upload subsystem** that #5b (Combined PDF generation) and any future attachment surface will reuse — `file_blob` table, `FileStore` interface, multipart upload endpoint, RBAC-gated streaming download endpoint.

---

## 1. Scope

### In scope

1. **File-upload subsystem** — generic `file_blob` table, `FileStore` Python interface with `LocalDiskStore` impl, multipart upload endpoint, streaming download endpoint with RBAC.
2. **Shop Drawings register** — project-scoped drawings with room tag, revision history, review workflow.
3. **Three subtabs** on `/shop-dwgs`: Current (latest revision approved, drawing not archived), In review (latest revision is `draft` or `pending`), Archive (drawing has `archived_at`).
4. **Card grid UI** — 3-col layout with deterministic SVG blueprint placeholder, status pill, version chip, mono drawing id, room caption, reviewer avatar, mono date.
5. **Detail drawer** — embedded file viewer (iframe for PDF, img for image), revision history strip, contextual actions per role + state.
6. **Workflow actions** — upload, submit, withdraw, approve (manager+, not the uploader), reject with note (manager+, not the uploader), archive whole drawing.
7. **Audit hooks** — every mutation writes to `audit_log` with `entity='shop_drawing'`.
8. **Seed update** — 2 sample PDFs committed as fixtures, ~6 drawings on ALF-001 spanning all three subtabs.

### Out of scope (deferred to #5b, #5c, or later)

- **Templates subtab** — workspace-scoped reusable drawings, clone-into-project flow. Pure speculation; defer until a real Hartwood request lands.
- **Real PDF thumbnails** — rendering page 1 of a PDF requires `poppler-utils` in the api image (+50 MB) and a fallible pipeline. Use deterministic SVG placeholders for v1.
- **Item attachments** (CV production drawing, floor plan, site-measure PDF per item) — needed by the Combined PDF in #5b. Will reuse the file-upload subsystem from #5a but add an `item_attachment(item_id, kind, file_blob_id)` table.
- **iSample tab** — independent surface, entirely in #5c.
- **PDF generation** (Cutlist, Hardware, Combined) — entirely in #5b.
- **Orphan blob garbage collection** — disk is cheap; punt until disk pressure is real.
- **Multi-file revisions** — one file per revision; PDF can already be multi-page.
- **Cloud storage backend** — `FileStore` interface is in place but only `LocalDiskStore` ships. S3-compatible impl is one file, added when deployment shape changes.
- **Real-time review notifications** — reviewer learns about pending work by visiting `/shop-dwgs?subtab=in_review`. No email, no push.
- **DWG (AutoCAD) uploads** — never makes it past the drafting tool stage in practice; reviewers want PDF.

---

## 2. Architecture

### 2.1 Backend layout

Two new modules. Both follow repo convention (SQLAlchemy Core `text()` queries, Pydantic v2 schemas, `require_permission` deps).

```
apps/api/app/files/
  __init__.py
  store.py                    # FileStore Protocol + LocalDiskStore impl
  validators.py               # mime sniff (magic bytes), size cap, ext check
  routes.py                   # POST /files, GET /files/{id}
  schemas.py                  # FileBlobOut

apps/api/app/shop_drawings/
  __init__.py
  routes.py                   # CRUD + workflow actions
  schemas.py                  # DrawingIn, DrawingOut, RevisionOut, ReviewActionIn
  queries.py                  # text() SQL, one function per query
```

Both routers mounted from `apps/api/app/main.py`. Auth via `require_permission("shop_dwgs", action)` for shop-drawings routes; file routes use `require_permission("shop_dwgs", "read")` for download and `require_permission("shop_dwgs", "write")` for upload (since shop drawings are the only consumer in #5a).

### 2.2 Web layout

```
apps/web/app/(app)/shop-dwgs/
  page.tsx                          # subtabs + filter strip + 3-col grid
  _components/
    SubtabStrip.tsx                 # Current / In review / Archive
    DrawingFilters.tsx              # search, room, reviewer, project
    DrawingCard.tsx                 # card body
    BlueprintPlaceholder.tsx        # deterministic SVG seeded from drawing.id
    DrawingDrawer.tsx               # right-side drawer: revisions, file viewer, actions
    UploadDialog.tsx                # file picker + title + room + submit-on-create option
    NewRevisionDialog.tsx           # file picker only; reuses parent drawing's title/room
    ReviewActions.tsx               # approve / reject (with note) — manager+ only
    RevisionHistoryStrip.tsx        # vertical list of revisions in drawer
    StatusPill.tsx                  # pending / approved / rejected / draft
    VersionChip.tsx                 # mono "v4" chip
apps/web/lib/
  shop-drawings-types.ts            # mirrors API schemas
  shop-drawings-fetch.ts            # tiny fetch wrappers
  file-upload.ts                    # POST /files multipart wrapper, returns file_blob_id
```

State management: same approach as PM Workbench and Procurement Workbench — raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / RHF / Zustand.** Subtab, filters, expanded drawing all live in URL.

### 2.3 Two-level interaction (list → drawer)

The card grid is the primary surface. Clicking a card opens a right-side drawer over the list:

1. User clicks card → `<DrawingDrawer drawingId={id}>` opens with URL gaining `?drawing=N`.
2. Drawer fetches `GET /shop-drawings/{did}` (returns drawing + full revision history).
3. Top of drawer: file viewer for the **selected** revision (defaults to latest). PDF via `<iframe src="/api/files/{id}#zoom=fit" />`. Image via `<img>`.
4. Below viewer: revision history strip (vertical list, latest at top, click to switch viewer to that revision).
5. Footer: contextual actions based on caller role + selected revision state (see §6 state machine).
6. Drawer survives refresh and is deep-linkable.

### 2.4 File serving

Files are **never** on a public URL. The API endpoint `GET /files/{id}` performs:

1. Resolve `file_blob` row.
2. Verify caller's `workspace_id` matches blob's `workspace_id`.
3. Verify caller has `read` on `shop_dwgs` module.
4. Stream bytes via `StreamingResponse` from `FileStore.get(storage_key)`. Set `Content-Type` from `file_blob.mime`, `Content-Length` from `byte_size`, `Content-Disposition: inline; filename="<original_filename>"`.
5. The browser sees a normal cookie-authenticated GET (proxied via Next.js `/api/[...proxy]` like every other call), so embedding in `<iframe>` and `<img>` works without extra plumbing.

### 2.5 FileStore interface

```python
# apps/api/app/files/store.py
from typing import Protocol, BinaryIO

class FileStore(Protocol):
    def put(self, workspace_slug: str, sha256: str, byte_stream: BinaryIO) -> str:
        """Persist bytes; return storage_key (relative path or opaque handle)."""
    def get(self, storage_key: str) -> BinaryIO:
        """Open bytes for reading. Caller is responsible for closing."""
    def delete(self, storage_key: str) -> None: ...
    def exists(self, storage_key: str) -> bool: ...

class LocalDiskStore:
    def __init__(self, root: str): self.root = root
    # storage layout: <root>/<workspace_slug>/<sha256[0:2]>/<sha256>
```

Only `LocalDiskStore` ships in #5a. Future `S3Store` impl satisfies the same Protocol; routes never change. Bound via FastAPI dependency in `apps/api/app/files/__init__.py` reading `FILE_STORE_ROOT` env var (default `/uploads`).

`docker-compose.yml` gains:

```yaml
services:
  api:
    volumes:
      - ./apps/api:/code
      - ./db:/db
      - ./seed:/code/seed
      - uploads:/uploads          # NEW
volumes:
  dbdata:
  uploads:                        # NEW
```

---

## 3. Data model

### 3.1 Migration 0013 — three new tables

```sql
-- file-upload subsystem (generic; future attachments reuse this)
CREATE TABLE file_blob (
  file_blob_id      bigserial PRIMARY KEY,
  workspace_id      bigint      NOT NULL REFERENCES workspace(workspace_id),
  sha256            text        NOT NULL,
  mime              text        NOT NULL,
  byte_size         bigint      NOT NULL CHECK (byte_size > 0 AND byte_size <= 26214400),  -- 25 MB
  original_filename text        NOT NULL,
  storage_key       text        NOT NULL,
  uploaded_by       bigint      NOT NULL REFERENCES app_user(app_user_id),
  uploaded_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, sha256)
);

CREATE INDEX idx_file_blob_workspace ON file_blob (workspace_id);

-- shop drawings: project-scoped, room as free-text tag
CREATE TABLE shop_drawing (
  drawing_id            bigserial PRIMARY KEY,
  project_id            bigint      NOT NULL REFERENCES projects(project_id),
  title                 text        NOT NULL,
  room                  text,
  current_revision_id   bigint,                                              -- FK added below
  archived_at           timestamptz,
  archived_by           bigint      REFERENCES app_user(app_user_id),
  created_by            bigint      NOT NULL REFERENCES app_user(app_user_id),
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_shop_drawing_project ON shop_drawing (project_id);
CREATE INDEX idx_shop_drawing_room    ON shop_drawing (project_id, room);
CREATE INDEX idx_shop_drawing_active  ON shop_drawing (project_id) WHERE archived_at IS NULL;

-- revisions: one row per uploaded version
CREATE TABLE shop_drawing_revision (
  revision_id    bigserial   PRIMARY KEY,
  drawing_id     bigint      NOT NULL REFERENCES shop_drawing(drawing_id) ON DELETE CASCADE,
  rev_no         int         NOT NULL CHECK (rev_no >= 1),
  file_blob_id   bigint      NOT NULL REFERENCES file_blob(file_blob_id),
  status         text        NOT NULL CHECK (status IN ('draft','pending','approved','rejected')),
  uploaded_by    bigint      NOT NULL REFERENCES app_user(app_user_id),
  uploaded_at    timestamptz NOT NULL DEFAULT now(),
  reviewed_by    bigint      REFERENCES app_user(app_user_id),
  reviewed_at    timestamptz,
  review_note    text,
  UNIQUE (drawing_id, rev_no)
);

CREATE INDEX idx_drawing_revision_drawing ON shop_drawing_revision (drawing_id);
CREATE INDEX idx_drawing_revision_status  ON shop_drawing_revision (status);

-- "one revision in flight per drawing" — enforced at the index level
CREATE UNIQUE INDEX uniq_drawing_inflight
  ON shop_drawing_revision (drawing_id)
  WHERE status IN ('draft','pending');

-- now wire the back-reference (deferred so both tables exist first)
ALTER TABLE shop_drawing
  ADD CONSTRAINT fk_shop_drawing_current_revision
    FOREIGN KEY (current_revision_id) REFERENCES shop_drawing_revision(revision_id);
```

### 3.2 Invariants enforced by the schema

- **Dedup per workspace.** Same bytes uploaded twice → same `file_blob` row (`UNIQUE (workspace_id, sha256)`). The upload endpoint detects this and returns the existing `file_blob_id` instead of writing duplicate bytes to disk.
- **Size cap at the row level.** `byte_size CHECK (...)` belt-and-braces with the multipart parser cap. Defense in depth.
- **One revision in flight.** Partial unique index `uniq_drawing_inflight` makes it impossible for a drawing to have two simultaneously-in-flight revisions. Drafter must approve, reject, or withdraw before uploading another.
- **Sequential rev_no.** `UNIQUE (drawing_id, rev_no)` per drawing. Backend computes `next_rev_no = max(rev_no)+1` inside the same transaction as the insert.
- **`current_revision_id` always points to an approved revision** (or NULL if no revision has ever been approved). Updated atomically by the approve handler.

### 3.3 Status semantics — the subtab membership query

```sql
-- "Current": drawings with at least one approved revision and not archived
SELECT d.*, r.rev_no AS current_rev_no, r.uploaded_at, r.reviewed_at, r.reviewed_by
  FROM shop_drawing d
  JOIN shop_drawing_revision r ON r.revision_id = d.current_revision_id
 WHERE d.project_id = :pid
   AND d.archived_at IS NULL
   AND d.current_revision_id IS NOT NULL;

-- "In review": drawings whose latest revision is draft or pending
WITH latest AS (
  SELECT DISTINCT ON (drawing_id) *
    FROM shop_drawing_revision
   ORDER BY drawing_id, rev_no DESC
)
SELECT d.*, l.rev_no AS latest_rev_no, l.status, l.uploaded_at
  FROM shop_drawing d
  JOIN latest l ON l.drawing_id = d.drawing_id
 WHERE d.project_id = :pid
   AND d.archived_at IS NULL
   AND l.status IN ('draft','pending');

-- "Archive": archived drawings (regardless of last revision status)
SELECT d.*
  FROM shop_drawing d
 WHERE d.project_id = :pid
   AND d.archived_at IS NOT NULL;
```

Filters (`room`, `reviewer`, `q` for title search) are AND'd onto each query.

---

## 4. File-upload subsystem

### 4.1 Upload endpoint

`POST /files` — multipart/form-data with one `file` field.

Flow:

1. Read multipart stream into a temp buffer (FastAPI `UploadFile`), capped at 25 MB. Reject early with 413 if exceeded.
2. Sniff first 8 bytes for magic-byte mime detection (`%PDF-` for PDF, `\x89PNG` for PNG, `\xFF\xD8\xFF` for JPEG). Cross-check against extension. Reject with 415 on mismatch.
3. Compute sha256 in a single pass over the buffer.
4. **Dedup check.** `SELECT file_blob_id FROM file_blob WHERE workspace_id = :wid AND sha256 = :sha;` If found, return existing `file_blob_id` without touching disk.
5. Otherwise: `FileStore.put(workspace_slug, sha256, byte_stream)` writes to disk; `INSERT INTO file_blob (...)` records metadata. Both inside one transaction; if disk write fails, DB row is rolled back.
6. Return `{ file_blob_id, sha256, mime, byte_size, original_filename, deduped: bool }`.

Storage path on disk: `<FILE_STORE_ROOT>/<workspace_slug>/<sha256[0:2]>/<sha256>`. Sharded by first two hex chars so no single directory grows past ~256 entries × workspace count even at scale. No file extension on disk — mime/extension live only in the DB row.

### 4.2 Download endpoint

`GET /files/{file_blob_id}` — RBAC + stream.

1. `SELECT * FROM file_blob WHERE file_blob_id = :id;` → 404 if missing.
2. Verify `blob.workspace_id == current_user.workspace_id`. Otherwise 404 (not 403 — don't leak existence).
3. Verify `current_user` has `read` on `shop_dwgs`.
4. `StreamingResponse(FileStore.get(blob.storage_key), media_type=blob.mime, headers={...})`.
5. Headers: `Content-Length: {byte_size}`, `Content-Disposition: inline; filename="{escaped original_filename}"`, `Cache-Control: private, max-age=300` (short cache so the same iframe doesn't re-fetch on every action).

The browser hits this via `/api/files/{id}` which the existing Next.js `/api/[...proxy]` route forwards to FastAPI with the `jf_session` cookie attached. No new web-side plumbing.

### 4.3 Validators

```python
# apps/api/app/files/validators.py
ALLOWED_MIME_BY_MAGIC = {
    b'%PDF-':           'application/pdf',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'\xFF\xD8\xFF':    'image/jpeg',
}
MAX_BYTE_SIZE = 25 * 1024 * 1024  # 25 MB

def sniff_mime(head: bytes) -> str | None: ...
def validate_extension_matches(filename: str, mime: str) -> bool: ...
```

### 4.4 Why not polymorphic association

Future consumers (item attachments in #5b, possibly iSample swatches in #5c) will reference `file_blob` via their own dedicated FK column (`item_attachment.file_blob_id`, `sample_revision.file_blob_id`, etc.). No `(entity_type, entity_id)` polymorphic tuple. Reasoning:

- The repo uses SQLAlchemy Core `text()` queries with explicit FKs. Polymorphic refs make joins cumbersome and break referential integrity.
- Each consumer has different cascade and lifecycle requirements that polymorphism would muddle.
- One extra column on each consumer table costs almost nothing.

---

## 5. Shop Drawings tab

### 5.1 List page (`/shop-dwgs`)

Workspace-wide by default; project filter chip in the header narrows. Three subtabs in the canonical IA position (under the top tab strip, right-aligned `chromeExtra` slot for the upload button).

- **Header:** `{N} drawings across {M} rooms · {K} awaiting review` (live counts; reuses the legacy hi-fi caption). `K` counts revisions in `pending` status only — drafts are still with the drafter and not yet "awaiting" anyone.
- **Filter strip:** search (title prefix) · Project (chip selector if multiple) · Room (dropdown populated from distinct `shop_drawing.room` values for the current project) · Reviewer (dropdown of users with manager/admin role).
- **Subtabs:** Current (default) · In review · Archive.
- **Card grid:** 3-col CSS grid (`grid-template-columns: repeat(3, minmax(0, 1fr))`), gap = `--space-section / 4`.

### 5.2 Card layout

Each card (`DrawingCard.tsx`):

```
┌──────────────────────────────────────┐
│ [PILL]                       [v4]    │   ← status pill top-left, version chip top-right
│                                      │
│      <BlueprintPlaceholder />        │   ← 16:10 deterministic SVG
│                                      │
├──────────────────────────────────────┤
│ #SD-0042  Kitchen base run           │
│ Kitchen · ALF-001                    │
│ ◷ Rin Park · 28/04/2026              │
└──────────────────────────────────────┘
```

- Status pill uses `HStatus` mappings from the design system (Pending = warn, Approved = good, Rejected = bad, Draft = neutral). Archived cards in the Archive subtab show no status pill, only a muted "Archived" footer chip.
- Version chip: `.h-mono`, surface background, shows `v{rev_no}` of the **selected** revision (latest by default).
- Drawing id rendered `.h-mono` with `tnum`, formatted as `#SD-{drawing_id padded to 4}`.
- Reviewer avatar comes from `current_revision.reviewed_by` if approved, else `current_revision.uploaded_by`. Date is `reviewed_at` for approved, `uploaded_at` otherwise. `DD/MM/YYYY` format throughout.

### 5.3 BlueprintPlaceholder

```tsx
function BlueprintPlaceholder({ seed }: { seed: number }) {
  // Deterministic: same seed → same SVG. PRNG = mulberry32(seed).
  // Renders: subtle grid pattern, one title rule (horizontal line near top),
  // 1–2 dimension callouts (random positions), all in --h-line on --h-surface-alt.
  // Pure SVG, no canvas, no rendering pipeline.
}
```

Matches the legacy hi-fi description: "16:10 SVG blueprint placeholder with grid pattern + title rule + dim callout (deterministic from seed so thumbs stay stable across renders)". Seed = `drawing_id`.

### 5.4 Detail drawer (`DrawingDrawer.tsx`)

Right-side drawer (~640 px wide). URL state: `?drawing=N&rev=M` (rev defaults to latest if omitted).

Layout top to bottom:

1. **Header:** drawing id + title, room, project. Close button (X) in corner.
2. **File viewer:** `<iframe src="/api/files/{file_blob_id}#zoom=fit" />` for PDFs; `<img src="/api/files/{file_blob_id}" />` for PNG/JPG. Fixed height (~480 px) with the file scaled to fit.
3. **RevisionHistoryStrip:** vertical list, latest at top. Each row: `v{rev_no} · {status pill} · {uploaded_by} · {uploaded_at}`. Click switches the viewer to that revision (URL gains `&rev=M`).
4. **ReviewActions footer** (contextual; see §6):
   - Drafter on a `draft` revision they uploaded: `Submit for review` button.
   - Drafter on a `pending` revision they uploaded: `Withdraw` button.
   - Manager+ on a `pending` revision they did not upload: `Approve` and `Reject` buttons. Reject opens an inline note input.
   - Drafter on any revision they uploaded (always): `Upload new revision` button (replaces the in-flight if any, after explicit confirm).
   - Manager+ on a non-archived drawing: `Archive drawing` button (with confirm).
   - Anyone: `Download` link.

### 5.5 Upload dialogs

- **`UploadDialog.tsx`** (new drawing): file picker, title, room, optional "Submit for review immediately" checkbox. Two-step submit:
  1. POST `/files` with the file → get `file_blob_id`.
  2. POST `/projects/{pid}/shop-drawings` with `{ title, room, file_blob_id, submit_immediately }`. Backend creates drawing + rev 1 in single transaction; if `submit_immediately`, status = `pending`, otherwise `draft`.
- **`NewRevisionDialog.tsx`** (existing drawing): file picker only (title/room come from parent drawing). Same two-step flow → POST `/shop-drawings/{did}/revisions`. Always lands in `draft`. If a `draft` or `pending` revision already exists, backend returns 409 with a message asking to withdraw or wait for review.

### 5.6 Empty / error states

- Empty Current subtab: "No approved drawings yet. Upload one to get started." with the upload button highlighted.
- Empty In review subtab: "Nothing awaiting review." muted.
- Empty Archive subtab: "No archived drawings." muted.
- Upload error (size/mime): toast in `--h-bad` with the specific reason.
- Approve/reject by uploader: button is disabled with tooltip "Reviewer cannot be the uploader".

---

## 6. Workflow & state machine

### 6.1 Revision states

```
   ┌─────────┐  submit   ┌──────────┐  approve  ┌──────────┐
   │  draft  ├──────────►│ pending  ├──────────►│ approved │
   └────┬────┘           └────┬─────┘           └──────────┘
        │ withdraw◄─────────  │ reject (with note)
        │                     ▼
        │                ┌──────────┐
        │                │ rejected │
        │                └──────────┘
        │                     │
        │                     │ (terminal; new revision required)
        ▼
   (uploader can replace by uploading again, but schema enforces
    no other in-flight revision exists)
```

Transitions:
- `draft → pending`: uploader clicks Submit. No other actor can submit.
- `pending → draft`: uploader clicks Withdraw. No other actor can withdraw.
- `pending → approved`: any user with `auth_role IN ('manager','admin')` AND user is not the uploader. Updates `shop_drawing.current_revision_id = revision_id` in the same transaction.
- `pending → rejected`: same actor rule as approved. Requires `review_note` (non-empty). Drawing's `current_revision_id` is unchanged (so the previously-approved revision, if any, stays "current").
- `approved`, `rejected`: terminal.

Drawing-level transition:
- `archived_at IS NULL → archived_at = now()`: any user with `auth_role IN ('manager','admin')`. Confirm dialog warns this hides the drawing from Current. Reversible only via DB intervention in v1 (no unarchive button — keep the surface small; can add later if anyone asks).

### 6.2 Permission rules summary

| Action | Required auth_role | Additional rule |
|---|---|---|
| Create drawing + rev 1 | `drafter`, `manager`, `admin` | — |
| Upload new revision | `drafter`, `manager`, `admin` | No other in-flight revision (enforced by DB index + 409 from backend) |
| Submit (draft → pending) | `drafter`, `manager`, `admin` | Caller is the uploader of that revision |
| Withdraw (pending → draft) | `drafter`, `manager`, `admin` | Caller is the uploader |
| Approve / reject | `manager`, `admin` | Caller is **not** the uploader |
| Archive drawing | `manager`, `admin` | — |
| Edit title/room | `drafter`, `manager`, `admin` | Caller created the drawing OR is `manager`/`admin` |
| Read (list, detail, file) | any role with `shop_dwgs:read` | Workspace match on file fetch |

`drafter` is included in writes because the elevated-drafter pattern from PM Workbench (migration 0008/0009) treats Drafter as the authoritative content creator. Same module-action gate (`require_permission("shop_dwgs", "write")`) plus the elevated rule.

### 6.3 Permission matrix update

`apps/api/app/auth/permissions.py` — `shop_dwgs` module gains:

```python
# write: drafter, manager, admin
# approve: manager, admin (the not-uploader rule is enforced in the route handler, not the matrix)
# read: all roles
# comment: not used in #5a (kept for symmetry)
```

No migration needed for permissions (matrix is static Python). The elevated-drafter pattern continues — `drafter` keeps PM-parity on `shop_dwgs` module same as it has on `orderbook` (post-Procurement Workbench migration 0011).

### 6.4 Why one-in-flight at a time

Two competing pending revisions on the same drawing creates ambiguity for reviewers ("which one is the real submission?"). The partial unique index makes the data model unambiguous. The Drafter UX is: if you want to revise a pending submission, withdraw it first. Cheap rule, eliminates a class of edge cases.

---

## 7. RBAC, audit, and security

### 7.1 RBAC

All shop-drawings routes gated by `require_permission("shop_dwgs", action)`. The not-uploader rule for approve/reject is checked inside the handler:

```python
if revision.uploaded_by == current_user.app_user_id:
    raise HTTPException(403, "Reviewer cannot be the uploader")
```

File download enforces:
1. `require_permission("shop_dwgs", "read")` (since shop drawings are #5a's only file consumer).
2. `blob.workspace_id == current_user.workspace_id` (404 on mismatch — don't leak existence).

When #5b adds item attachments, the file route adds a second permission check OR the routes split. Either is fine; defer until #5b.

### 7.2 Audit

Every state-changing action writes one `audit_log` row with `entity='shop_drawing'`:

| Action | `event` |
|---|---|
| Create drawing | `shop_drawing.create` |
| Edit title/room | `shop_drawing.update` |
| Upload revision | `shop_drawing.revision.upload` |
| Submit | `shop_drawing.revision.submit` |
| Withdraw | `shop_drawing.revision.withdraw` |
| Approve | `shop_drawing.revision.approve` |
| Reject | `shop_drawing.revision.reject` |
| Archive | `shop_drawing.archive` |

`detail` JSON column carries `{ revision_id, rev_no, status_before, status_after, review_note? }` as relevant.

File operations write audit too (upload, but not download — too noisy):

| Action | `event` |
|---|---|
| Upload (new blob) | `file_blob.create` |
| Upload (deduped) | `file_blob.dedup` |

### 7.3 Security checklist

- **No public file URLs.** Every download goes through RBAC.
- **Magic-byte mime sniffing.** Don't trust filename extension or `Content-Type` header from the client.
- **Size cap enforced twice.** Once at multipart parser, once at DB CHECK constraint.
- **Filename sanitization.** Original filename stored as-is in DB (display only); never used in disk path. Disk path is the sha256 hex string. Eliminates path traversal entirely.
- **`Content-Disposition: inline`** with the filename quoted/escaped per RFC 6266. Browser handles PDF inline; image inline.
- **No SVG uploads.** SVG can carry script. Allowlist is PDF/PNG/JPEG only.
- **Workspace isolation.** Every blob and drawing scoped by `workspace_id`; cross-workspace reads return 404.

---

## 8. Seed updates

`seed/hartwood_joinery/`:

1. **Sample fixture files** — commit two small PDFs (~50–100 KB each, real CV-export-style multi-page) under `seed/hartwood_joinery/sample_drawings/`:
   - `kitchen-base-run.pdf`
   - `bathroom-vanity.pdf`
2. **Seed inserts** on project ALF-001:
   - Drawing 1: "Kitchen base run", room=Kitchen → 3 revisions (rev 1 approved, rev 2 approved, rev 3 in `pending`). `current_revision_id` = rev 2.
   - Drawing 2: "Bathroom vanity", room=Bathroom → 2 revisions (rev 1 rejected w/ note, rev 2 approved). `current_revision_id` = rev 2.
   - Drawing 3: "Kitchen island", room=Kitchen → 1 revision in `draft`.
   - Drawing 4: "Walk-in robe", room=Bedroom → 1 revision in `pending`.
   - Drawing 5: "Pantry", room=Kitchen → 1 revision approved, `archived_at` set.
   - Drawing 6: "Hallway storage", room=Hallway → 1 revision approved.

   Result:
   - **Current subtab** = 3 drawings (kitchen base run @ rev 2, bathroom vanity @ rev 2, hallway storage @ rev 1). Note: kitchen base run **also** appears in In review because its latest revision (rev 3) is pending — drawings with both an approved revision and a newer in-flight revision are intentionally surfaced in both subtabs (the approved version remains consumable while the new one is reviewed).
   - **In review** = 3 drawings (kitchen base run's latest rev 3 = pending, kitchen island = draft, walk-in robe = pending).
   - **Archive** = 1 drawing (pantry).
   - **Header counts:** `N=6` total drawings, `M=4` distinct rooms (Kitchen / Bathroom / Bedroom / Hallway — pantry is in Kitchen but archived; archived drawings excluded from room count), `K=2` revisions in `pending` status (kitchen base run's rev 3 + walk-in robe's only rev).
   - Header reads: `6 drawings across 4 rooms · 2 awaiting review`.

3. **Hash-deduped insert.** Seed re-runs don't write duplicate blobs because `(workspace_id, sha256)` is unique. Re-seeding works idempotently.

Seed runs in the api container as part of `make seed`. It calls the same upload logic via a direct Python helper (not over HTTP) — `apps/api/app/files/seed_helper.py` exposes `put_seed_file(session, workspace_id, app_user_id, path) -> file_blob_id`. Reuses the same dedup + storage path logic, no duplication.

---

## 9. Testing

### 9.1 Pytest suite

New files under `tests/api/`:

| File | Cases (~) | Focus |
|---|---|---|
| `test_files_upload.py` | 8 | Multipart upload happy path, size cap (over and under), mime sniff, ext mismatch, dedup, RBAC on upload |
| `test_files_download.py` | 5 | Streamed download, RBAC (workspace mismatch → 404), missing id → 404, `Content-Disposition` correctness, image vs PDF |
| `test_shop_drawings_crud.py` | 6 | Create drawing, list by subtab, edit title/room, archive, FK integrity |
| `test_shop_drawings_workflow.py` | 10 | Full state machine: submit, withdraw, approve, reject, all the not-uploader checks, one-in-flight check (409), terminal transitions |
| `test_shop_drawings_rbac.py` | 4 | Drafter elevated to write/approve gating, viewer denied, manager/admin can approve, drafter can't approve own |
| `test_shop_drawings_subtab_query.py` | 4 | Subtab membership SQL across the seeded fixtures |

Total: ~37 new pytest cases. Following repo convention, every test gets a fresh DB transaction rolled back at the end; the workspace truncation in `make test` continues to apply.

### 9.2 Playwright spec

`tests/e2e/shop_drawings.spec.ts` — single happy-path journey covering both roles:

1. Login as `rin.park@hartwood.test` (drafter).
2. Navigate to `/shop-dwgs`. Verify header count + 3 cards in Current subtab.
3. Click upload, select a small fixture PDF, fill title + room, check "Submit for review immediately", submit.
4. Verify drawing now appears in In review subtab.
5. Logout. Login as a manager seed user.
6. Navigate to `/shop-dwgs?subtab=in_review`. Open the new drawing.
7. Click Approve. Verify drawing moves to Current subtab on refresh.
8. Reject path: open another in-review drawing, click Reject, type note, submit. Verify drawing's Current state is unchanged (because previously-approved revision still pointed to by `current_revision_id`).

Runs via `make e2e-docker` like existing specs.

### 9.3 Manual smoke after merge

1. `make up && make migrate && make seed`.
2. Hit `/shop-dwgs`, see 3 cards in Current, 3 in In review, 1 in Archive.
3. Open Kitchen base run drawing → drawer shows 3 revisions, viewer shows rev 2 (current) by default.
4. As manager, approve the pending rev 3 → verify viewer now shows rev 3 and `current_revision_id` updated.
5. Try uploading 30 MB file → 413.
6. Try uploading `.exe` → 415.
7. Upload identical PDF twice → second upload returns same `file_blob_id` with `deduped: true`.

---

## 10. Implementation order

This will become the sub-project plan; keeping sequencing here for spec-level clarity.

1. **Migration 0013** (file_blob, shop_drawing, shop_drawing_revision, all indexes including partial unique). Plus `docker-compose.yml` `uploads` volume.
2. **`FileStore` interface + `LocalDiskStore`** + tests for the storage layer alone (no HTTP).
3. **File upload + download routes** + validators + tests.
4. **Permissions matrix update** (`shop_dwgs` module entries; drafter elevated).
5. **Shop drawings backend**: schemas, queries, routes (CRUD + workflow). Tests.
6. **Web `lib/`**: types, fetch wrappers, file-upload helper.
7. **`/shop-dwgs` page**: subtab strip, filter strip, card grid, BlueprintPlaceholder.
8. **DrawingDrawer**: file viewer, revision history strip, ReviewActions.
9. **UploadDialog + NewRevisionDialog**.
10. **Seed fixtures + seed helper** (idempotent, dedup-aware).
11. **Playwright spec**.
12. **Audit log entries** wired into every mutation.

---

## 11. Open follow-ups (not blocking #5a)

These are deliberately deferred:

- **Item attachments table** for Combined PDF — defined in #5b spec.
- **Real PDF thumbnails** — would require `poppler-utils`. Add when card grid feels sparse with placeholders.
- **Templates subtab** — workspace-scoped library + clone-into-project flow. Defer until requested.
- **Unarchive button** — DB has the column; UI just doesn't surface it. Trivial to add later.
- **Comment thread on a revision** — `shop_dwgs:comment` action exists in the matrix but is unused in #5a. Add a comments table when reviewers ask for back-and-forth beyond a single review note.
- **Bulk ops** (archive multiple, approve multiple) — wait for evidence anyone needs this.
- **Orphan blob GC** — write a `cleanup_orphan_blobs.py` script when disk pressure is real.
- **Workspace storage quota** — sum `file_blob.byte_size`, surface in IT Management. Easy add post-launch.

---

## 12. Resolved decisions

- **Storage strategy.** Local disk in named Docker volume, behind `FileStore` Protocol so S3-compatible swap is one new file.
- **Entity scope.** Project-scoped, room as free-text tag. Matches the legacy "22 drawings across 7 rooms" caption.
- **Versioning.** Parent `shop_drawing` + child `shop_drawing_revision` with `rev_no`. Each upload creates a new revision row; old revisions stay queryable.
- **Workflow.** `draft → pending → approved | rejected`. Reviewer = manager/admin, never the uploader. One revision in flight at a time, enforced by partial unique index.
- **Subtabs.** Current / In review / Archive. Templates dropped (YAGNI).
- **File types.** PDF / PNG / JPEG only, validated by magic bytes. 25 MB cap.
- **Files per revision.** Exactly one. PDF can be multi-page.
- **Thumbnails.** Deterministic SVG placeholder seeded from `drawing_id`.
- **Dedup.** Per-workspace SHA-256 dedup; same bytes → same blob row.
- **Polymorphism.** None. Each consumer adds its own FK column to `file_blob`.
- **Storage layout.** `<root>/<workspace_slug>/<sha256[0:2]>/<sha256>` — content-addressable, sharded.
- **Cleanup.** None in v1. Soft-delete drawings via `archived_at`. No orphan blob GC.
- **Audit.** Every state change writes `audit_log`; uploads write `file_blob.create` or `file_blob.dedup`. Downloads not audited.

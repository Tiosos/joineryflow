# JoineryFlow iSample (Sample Wall) — Design Spec

**Date:** 2026-05-02
**Sub-project:** #5c (final slice of sub-project #5; #5a Shop Drawings + #5b PDF generation already shipped)
**Branch base:** `feat/foundation` (post #5b merge)
**Prior context:** `docs/superpowers/specs/2026-04-22-foundation-design.md`, `docs/superpowers/specs/2026-04-25-pm-workbench-design.md`, `docs/superpowers/specs/2026-04-28-procurement-workbench-design.md`, `docs/superpowers/specs/2026-05-01-shop-drawings-design.md`, `docs/superpowers/specs/2026-05-02-pdf-generation-design.md`, `legacy/product_spec.md` §10.7, `legacy/hi-order-dwg-sample.jsx`

---

## 0. Goal

A Drafter creates a material sample on a project (title + hex swatch + optional supplier + optional photo upload). Status lands in `pending`. A Manager / Admin / other Drafter approves or rejects with a review note. Approved samples render on the **Board** subtab; rejected/archived samples on **Archive**; **Approval ledger** shows the audit timeline filtered to sample events. UI is a 5-column swatch grid matching the legacy `HiSamplebook` hi-fi: square swatch with sheen overlay, status pill top-left, mono `#SAM-####` chip top-right, footer with title · project·room · reviewer avatar · decision caption.

This sub-project also retires the `/isample` stub page from Foundation.

---

## 1. Scope

### In scope

1. **`sample` register** — workspace-isolated via `projects.workspace_id` (post-hardening). Project-scoped. Fields: title, room (free-text), hex_swatch (#RRGGBB regex CHECK), supplier (free-text optional), status enum, review_note, reviewer/timestamps, optional photo via `file_blob_id`, archive timestamps, audit timestamps.
2. **Three subtabs:** Board (active = pending OR approved, not archived) · Approval ledger (audit_log filtered) · Archive (archived OR rejected).
3. **5-column swatch card grid** — square swatch with hex_swatch background + 135° sheen overlay (or photo background if uploaded, with hex shown as a small chip). Status pill TL, mono `#SAM-{padded}` chip TR. Footer with title, `project_code · room`, reviewer avatar + decision caption.
4. **Workflow:** `pending → approved | rejected`. Reject requires `review_note`. Reviewer cannot be the creator. Archive transition (creator-on-own OR manager+) sets `archived_at`. Rejected samples auto-show in Archive.
5. **Optional photo** — single PNG/JPEG via `file_blob_id` FK to #5a's `file_blob`. Reuses `POST /files` upload endpoint. PDF rejected at the photo route layer (analogous to the PDF-only gate on item attachments in #5b).
6. **Filter strip:** All · Awaiting client (pending count) · Approved (approved count) · Rejected (rejected count) · search by title · project filter chip (when multi-project).
7. **Detail drawer** with full metadata, large photo if uploaded, contextual action buttons.
8. **Audit hooks** on every mutation. `entity='sample'` with events `sample.create`, `sample.update`, `sample.approve`, `sample.reject`, `sample.archive`, `sample.upload_photo`, `sample.clear_photo`.
9. **Permissions matrix update** — `isample` row gains the same elevated-drafter pattern from `shop_dwgs` and `list`.
10. **Seed** — 6 demo samples on ALF-001 spanning all three subtabs + 1 PNG fixture for photo demo.

### Out of scope (deferred to v2 or later)

- **Suppliers as a real registry** — free-text `supplier varchar(128)` only. The legacy "Suppliers" subtab is dropped (no separate aggregation view).
- **Clients tab** — no client-facing surface in v1. The legacy "Clients" subtab is dropped.
- **Sample revisions** — when a client rejects a sample, the Drafter creates a *new sample*, not a revision. No `sample_revision` parent/child table.
- **Print Sample Board to PDF** — the legacy hi-fi has a "Print board" button. Defer until anyone asks; the print pipeline from #5b could be reused for it.
- **Real-time client signoff via shareable link** — no public URL; everything is internal.
- **Bulk approve / bulk archive** — UI ships single-sample actions only.
- **Sample categories** (board / hardware / stone / etc.) — single flat list. Filter by supplier covers most discoverability needs.
- **Item linking** (which items use this sample?) — useful but YAGNI in v1.
- **Item-attachment-style PDF inclusion** — samples aren't part of the Combined PDF in #5b; defer until requested.
- **Sample-id custom prefix scheme** (legacy "A-21" / "M-12" alpha-prefix) — uses plain `#SAM-{padded id}` instead, matching the existing `#SD-{padded}` convention from #5a Shop Drawings.

---

## 2. Architecture

### 2.1 Backend layout

One new module. Follows repo convention (SQLAlchemy Core `text()` queries, Pydantic v2, `require_permission`).

```
apps/api/app/samples/
  __init__.py
  routes.py        # CRUD + workflow + photo bind/clear + ledger
  queries.py       # text() SQL with audit
  schemas.py       # SampleIn, PatchSampleIn, SampleOut, RejectIn, BindPhotoIn, LedgerOut

apps/api/app/auth/permissions.py    # MODIFY: isample matrix entries (elevated drafter)
apps/api/app/main.py                # MODIFY: mount samples_router
apps/api/tests/conftest.py          # MODIFY: extend TRUNCATE_TABLES with `sample`
```

Auth via `require_permission("isample", action)` for all routes. Workspace isolation via `projects.workspace_id = :w` direct join (post-hardening from `cc7ea11`).

### 2.2 Web layout

```
apps/web/app/(app)/isample/
  page.tsx                              # replaces stub: subtabs + filter strip + grid
  _components/
    ISampleClient.tsx                   # client wrapper that owns URL state
    SubtabStrip.tsx                     # Board | Approval ledger | Archive
    SampleFilters.tsx                   # search + project + supplier dropdown + status chips
    SampleCard.tsx                      # 5-col card body
    SampleSwatch.tsx                    # square swatch (hex bg + sheen, or photo bg)
    SampleStatusPill.tsx                # pending/approved/rejected/archived (HStatus mapping)
    SampleIdChip.tsx                    # #SAM-{padded} mono chip
    SampleDrawer.tsx                    # right-side detail drawer + actions
    NewSampleDialog.tsx                 # create + initial photo (optional)
    PhotoUploadDialog.tsx               # bind/replace/clear photo on existing sample
    ReviewActions.tsx                   # approve/reject (with note) + archive
    ApprovalLedger.tsx                  # audit log timeline view (3rd subtab)

apps/web/lib/
  samples-types.ts
  samples-fetch.ts
```

State management: same as PM Workbench, Procurement Workbench, Shop Drawings, PDF gen — raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / RHF / Zustand.**

### 2.3 Two-level interaction (grid → drawer)

Card grid is the primary surface. Clicking a card opens a right-side drawer over the grid:

1. User clicks card → `<SampleDrawer sampleId={id}>` opens with URL gaining `?sample=N`.
2. Drawer fetches `GET /samples/{sid}` (returns full sample + reviewer name).
3. Drawer body: large swatch (or photo) + metadata block (title, room, supplier, hex code as `.h-mono`, project code, created_by + created_at, reviewer + reviewed_at + review_note when present).
4. Action footer: contextual based on caller role + state (see §6 state machine).
5. Drawer survives refresh, deep-linkable.

### 2.4 Approval ledger subtab

Read-only timeline view. Backed by a single endpoint that filters `audit_log` to `entity='sample'` for samples belonging to the current project. Each row shows: timestamp, actor name, event (humanized: "Approved sample #SAM-0042"), payload summary (review note when present, photo filename when relevant). Paginated 50 at a time.

Same shape as the existing audit-log read patterns in the codebase, but scoped to one project + one entity.

---

## 3. Data model

### 3.1 Migration 0016 — `sample`

```sql
CREATE TABLE sample (
  sample_id          bigserial    PRIMARY KEY,
  project_id         bigint       NOT NULL REFERENCES projects(project_id),
  title              varchar(200) NOT NULL,
  room               varchar(64),
  hex_swatch         varchar(7)   NOT NULL CHECK (hex_swatch ~ '^#[0-9A-Fa-f]{6}$'),
  supplier           varchar(128),
  status             text         NOT NULL CHECK (status IN ('pending','approved','rejected'))
                                  DEFAULT 'pending',
  review_note        text,
  reviewed_by        bigint       REFERENCES app_user(id),
  reviewed_at        timestamptz,
  photo_file_blob_id bigint       REFERENCES file_blob(file_blob_id),
  archived_at        timestamptz,
  archived_by        bigint       REFERENCES app_user(id),
  created_by         bigint       NOT NULL REFERENCES app_user(id),
  created_at         timestamptz  NOT NULL DEFAULT now(),
  updated_at         timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX idx_sample_project ON sample (project_id);
CREATE INDEX idx_sample_status  ON sample (project_id, status);
CREATE INDEX idx_sample_active  ON sample (project_id) WHERE archived_at IS NULL;
```

### 3.2 Invariants enforced by the schema

- **Hex regex CHECK** rejects any swatch that's not `#[0-9A-Fa-f]{6}`. Application can't insert "red" or "#fff".
- **Status enum CHECK** locks the workflow to 3 values. No silent additions.
- **Project FK** ties workspace isolation through `projects.workspace_id`.
- **Photo nullable** with FK to `file_blob` — if the blob is deleted via cascade in some future GC pass, the FK fires.
- **No CASCADE on `project_id`** — deleting a project shouldn't silently nuke its samples. Same convention as `shop_drawing`.
- **Composite index `(project_id, status)`** serves both subtab queries (Board needs `status IN ('pending','approved')`, Archive needs `status='rejected'` or `archived_at IS NOT NULL`).

### 3.3 Photo mime constraint at the route layer

The `file_blob` table from #5a allows PDF/PNG/JPEG. Sample photos must be PNG or JPEG (not PDF). Enforced in the route handler exactly like #5b's PDF-only gate, but inverted (image-only):

```python
blob_mime = db.execute(
    text("SELECT mime FROM file_blob WHERE file_blob_id = :b AND workspace_id = :w"),
    {"b": payload.file_blob_id, "w": user.workspace_id},
).scalar()
if blob_mime not in ("image/png", "image/jpeg"):
    raise HTTPException(status_code=415, detail="sample photos must be PNG or JPEG")
```

---

## 4. RBAC + audit + security

### 4.1 RBAC matrix update

`apps/api/app/auth/permissions.py` — `isample` row currently allows only `read` for most roles. Update to:

| Role             | isample actions                       |
|------------------|---------------------------------------|
| viewer           | `{read}`                              |
| editor           | `{read, write}`  *(no approve)*       |
| drafter          | `{read, write, approve, comment}`     |
| manager          | `{read, write, approve, comment}`     |
| admin            | full                                  |
| purchase_officer | `{read}`                              |

Drafter elevation matches the established `shop_dwgs` and `list` pattern. Editor can create samples but not approve them. The not-creator rule for approve/reject is enforced in the route handler (analogous to the not-uploader rule on Shop Drawings revisions).

### 4.2 Audit events

| Action | `event` | `target` | `payload` |
|---|---|---|---|
| Create sample | `sample.create` | `sample_id` | `{title, room, hex_swatch, supplier, status}` |
| Edit sample | `sample.update` | `sample_id` | `{field, value}` per field |
| Approve | `sample.approve` | `sample_id` | `{reviewed_by, review_note?}` |
| Reject | `sample.reject` | `sample_id` | `{reviewed_by, review_note}` |
| Archive | `sample.archive` | `sample_id` | `{archived_by, status_at_archive}` |
| Upload photo (new bind) | `sample.upload_photo` | `sample_id` | `{file_blob_id}` |
| Replace photo | `sample.upload_photo` | `sample_id` | `{file_blob_id, replaced_file_blob_id}` |
| Clear photo | `sample.clear_photo` | `sample_id` | `{file_blob_id}` |

The Approval ledger subtab IS this `audit_log` filtered.

### 4.3 Security checklist

- **Workspace isolation** via `projects.workspace_id = :w` on every query (matches post-hardening pattern).
- **Photo mime gate** at the route layer (PNG/JPEG only). PDF blobs cannot be bound to a sample even though the file_blob table itself is generic.
- **Hex regex CHECK** prevents injection via swatch field (only valid hex passes).
- **No public photo URLs** — photos served via `GET /files/{id}` with the existing #5a RBAC (`shop_dwgs:read`). Note: this means a viewer with `isample:read` but no `shop_dwgs:read` could see sample metadata but not photos. Acceptable for v1; if it becomes an issue, the file route's permission gate widens or the sample-photo route gets its own image-streaming endpoint. **Resolved decision: accept the cross-permission dependency for v1.**
- **Workspace isolation tests** mirror the #5b pattern — cross-workspace GET single + GET list + GET ledger all return 404.

---

## 5. Workflow & state machine

### 5.1 Sample states

```
   ┌─────────┐  approve  ┌──────────┐
   │ pending ├──────────►│ approved │
   └────┬────┘           └────┬─────┘
        │ reject (req note)   │
        ▼                     │
   ┌──────────┐               │
   │ rejected │               │
   └────┬─────┘               │
        │                     │
        ▼ (auto: in Archive)  │
                              ▼ archive
                         ┌──────────┐
                         │ archived │ (status preserved; archived_at set)
                         └──────────┘
```

Key behaviors:

- **No `draft` state.** Samples are created complete in one go (Drafter has the swatch + title + supplier ready). Lands in `pending` directly. (Different from Shop Drawings which has draft because revisions iterate.)
- **`pending → approved`** — `reviewed_by`, `reviewed_at`, optional `review_note` set. Reviewer must not be the creator (in-handler check). Status updates atomically.
- **`pending → rejected`** — same as approve but `review_note` is REQUIRED (Pydantic `min_length=1`).
- **`approved/rejected → archived`** — sets `archived_at = now()`, `archived_by`. Status field preserved (so we can tell `archived from approved` vs `archived from rejected`). Allowed by: creator (can archive own samples) OR manager+ (can archive any).
- **`pending → archived`** — also allowed (Drafter abandoned a pending sample).
- **Rejected stays out of Board** — the Board query filters `status IN ('pending', 'approved') AND archived_at IS NULL`. Rejected samples auto-appear in Archive without needing explicit archive action.
- **Terminal: archived** — once archived, no transitions. Unarchive is deferred.

### 5.2 Permission rules summary

| Action | Required `isample` action | Additional rule |
|---|---|---|
| Create sample | `write` | — |
| Edit title/room/hex_swatch/supplier | `write` | Creator OR manager+ |
| Approve | `approve` | Caller is **not** the creator |
| Reject | `approve` | Caller is **not** the creator; `review_note` required |
| Archive | `write` | Creator on own samples OR manager+ on any |
| Upload/replace/clear photo | `write` | Creator OR manager+ (matches Edit rule) |
| Read (list, single, ledger) | `read` | Workspace match |

The not-creator rule for approve/reject mirrors the not-uploader rule on Shop Drawings revisions.

---

## 6. Subtab semantics — SQL

```sql
-- Board: active samples (pending OR approved, not archived)
SELECT s.*, u.full_name AS reviewed_by_name, c.full_name AS created_by_name,
       fb.original_filename AS photo_filename
  FROM sample s
  JOIN projects p ON p.project_id = s.project_id
  LEFT JOIN app_user u ON u.id = s.reviewed_by
  LEFT JOIN app_user c ON c.id = s.created_by
  LEFT JOIN file_blob fb ON fb.file_blob_id = s.photo_file_blob_id
 WHERE s.project_id = :pid
   AND p.workspace_id = :wid
   AND s.archived_at IS NULL
   AND s.status IN ('pending', 'approved')
 ORDER BY s.sample_id DESC;

-- Archive: archived OR rejected
SELECT s.*, u.full_name AS reviewed_by_name, c.full_name AS created_by_name,
       fb.original_filename AS photo_filename
  FROM sample s
  JOIN projects p ON p.project_id = s.project_id
  LEFT JOIN app_user u ON u.id = s.reviewed_by
  LEFT JOIN app_user c ON c.id = s.created_by
  LEFT JOIN file_blob fb ON fb.file_blob_id = s.photo_file_blob_id
 WHERE s.project_id = :pid
   AND p.workspace_id = :wid
   AND (s.archived_at IS NOT NULL OR s.status = 'rejected')
 ORDER BY s.sample_id DESC;

-- Approval ledger: audit log filtered
SELECT a.id, a.actor_id, u.full_name AS actor_name, a.event,
       a.target AS sample_id, a.payload, a.created_at
  FROM audit_log a
  LEFT JOIN app_user u ON u.id = a.actor_id
 WHERE a.workspace_id = :wid
   AND a.entity = 'sample'
   AND a.target::int IN (SELECT s.sample_id FROM sample s
                           JOIN projects p ON p.project_id = s.project_id
                          WHERE p.project_id = :pid AND p.workspace_id = :wid)
 ORDER BY a.created_at DESC
 LIMIT :limit OFFSET :offset;
```

Filters (`q` for title, `supplier` exact match, status chip) are AND'd onto Board and Archive queries.

---

## 7. API surface

| Verb | Path | Purpose | Permission |
|---|---|---|---|
| GET | `/projects/{pid}/samples?subtab=board\|archive&q=&status=&supplier=` | List samples for project subtab (NOT ledger — see below) | `isample:read` |
| GET | `/projects/{pid}/samples/ledger?limit=50&offset=0` | Approval ledger (audit timeline) | `isample:read` |
| GET | `/samples/{sid}` | Single sample detail | `isample:read` |
| POST | `/projects/{pid}/samples` | Create sample (lands `pending`) | `isample:write` |
| PATCH | `/samples/{sid}` | Edit title/room/hex_swatch/supplier | `isample:write` (creator or manager+) |
| POST | `/samples/{sid}/approve` | `pending → approved` | `isample:approve` (not creator) |
| POST | `/samples/{sid}/reject` | `pending → rejected` (review_note required) | `isample:approve` (not creator) |
| POST | `/samples/{sid}/archive` | Sets `archived_at` | `isample:write` (creator or manager+) |
| POST | `/samples/{sid}/photo` | Bind/replace photo (PNG/JPEG; 415 on PDF) | `isample:write` |
| DELETE | `/samples/{sid}/photo` | Clear photo | `isample:write` |

10 endpoints. The list endpoint splits subtabs Board/Archive (one query shape with subtab param). Ledger is separate because the result shape is fundamentally different (audit rows, not sample rows).

### 7.1 Pydantic schemas

```python
# apps/api/app/samples/schemas.py
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator
import re

SampleStatus = Literal["pending", "approved", "rejected"]
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CreateSampleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    room: str | None = Field(default=None, max_length=64)
    hex_swatch: str
    supplier: str | None = Field(default=None, max_length=128)
    photo_file_blob_id: int | None = None

    @field_validator("hex_swatch")
    @classmethod
    def validate_hex(cls, v: str) -> str:
        if not HEX_RE.match(v):
            raise ValueError("hex_swatch must match ^#[0-9A-Fa-f]{6}$")
        return v


class PatchSampleIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    room: str | None = Field(default=None, max_length=64)
    hex_swatch: str | None = None
    supplier: str | None = Field(default=None, max_length=128)

    @field_validator("hex_swatch")
    @classmethod
    def validate_hex(cls, v: str | None) -> str | None:
        if v is not None and not HEX_RE.match(v):
            raise ValueError("hex_swatch must match ^#[0-9A-Fa-f]{6}$")
        return v


class RejectIn(BaseModel):
    review_note: str = Field(min_length=1, max_length=2000)


class ApproveIn(BaseModel):
    review_note: str | None = Field(default=None, max_length=2000)


class BindPhotoIn(BaseModel):
    file_blob_id: int


class SampleOut(BaseModel):
    sample_id: int
    project_id: int
    project_code: str
    title: str
    room: str | None
    hex_swatch: str
    supplier: str | None
    status: SampleStatus
    review_note: str | None
    reviewed_by: int | None
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    photo_file_blob_id: int | None
    photo_filename: str | None
    archived_at: datetime | None
    archived_by: int | None
    created_by: int
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class SampleListOut(BaseModel):
    samples: list[SampleOut]
    total: int
    counts: dict[str, int]   # {pending: 6, approved: 18, rejected: 2}


class LedgerEntry(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    event: str
    sample_id: int
    payload: dict
    created_at: datetime


class LedgerOut(BaseModel):
    entries: list[LedgerEntry]
    total: int
    limit: int
    offset: int
```

---

## 8. Web — UI components

### 8.1 List page (`/isample`)

Workspace-wide by default; project filter chip in the header narrows to one project (samples are project-scoped, so multi-project view shows a flat union when no project chip is active).

- **Header:** `{N} samples across {M} projects · {pending} awaiting client · {approved} approved · {rejected} rejected`. Live counts.
- **Subtabs:** Board (default) · Approval ledger · Archive (right-aligned `chromeExtra` slot for "+ New sample" button).
- **Filter strip:** search by title (prefix), project chip selector, supplier dropdown (populated from distinct `sample.supplier` values), status chip filter (All / Awaiting client / Approved / Rejected — chip-style, single-select).
- **Card grid:** 5-column CSS grid (`grid-template-columns: repeat(5, minmax(0, 1fr))`), gap `--space-section / 6`. The grid drops to 4 / 3 / 2 columns at smaller widths via media queries (Tailwind responsive variants).

### 8.2 Card layout (`SampleCard.tsx`)

```
┌──────────────────────────┐
│ [PILL]          [#SAM]   │  ← status pill TL, mono id chip TR
│                          │
│   ████████████████       │  ← square swatch (hex_swatch background
│   ████████████████       │     OR photo background if uploaded;
│   ████████████████       │     hex chip overlaid bottom-right when photo present)
├──────────────────────────┤
│ Oak veneer — Briggs 0412 │
│ ALF-001 · L3 / Reception │
│ ◷ JR · Signed 18 Apr     │
└──────────────────────────┘
```

- **Swatch area:** `aspect-square`. Background:
  - If `photo_file_blob_id IS NOT NULL`: `background-image: url(/api/files/{photo_file_blob_id})`, `background-size: cover`, plus a small `12px × 12px` chip in the bottom-right corner with `background: ${hex_swatch}` and `border: 2px solid white` for hex reference.
  - Else: `background: ${hex_swatch}` plus a 135° repeating-linear-gradient sheen overlay: `background-image: repeating-linear-gradient(135deg, rgba(255,255,255,0.04) 0 2px, transparent 2px 6px)`.
- **Status pill** top-left: uses `HStatus` mappings (pending = warn, approved = good, rejected = bad, archived = muted with strikethrough). Translucent surface `bg-white/90`.
- **Mono id chip** top-right: `#SAM-{padded(sample_id, 4)}` in `.h-mono`, on translucent surface.
- **Footer:** title (single-line truncate) · `{project_code} · {room}` muted (room may be empty) · reviewer avatar + decision caption mono.
- **Decision caption:** `review_note` (truncated to ~30 chars) when reviewed, else `{created_by_name} · {DD/MM/YYYY created_at}` for unreviewed.

### 8.3 Detail drawer (`SampleDrawer.tsx`)

Right-side drawer, ~640 px wide. URL state `?sample=N`.

Sections top to bottom:
1. **Header:** sample id chip + title, project · room. Close button.
2. **Large swatch / photo:** `aspect-square` (max ~520 px). If photo, full image (max-width: 100%, max-height: 520px, object-fit: contain). Hex code shown as mono caption: `Hex: #c29075`.
3. **Metadata block:** Status pill, supplier (if present), created_by + created_at, reviewed_by + reviewed_at + review_note (if reviewed).
4. **Action footer (contextual per §5.2):**
   - Drafter+ on own pending sample: `Edit`, `Upload photo` / `Replace photo`, `Archive`.
   - Drafter+/Manager+ on someone else's pending sample: `Approve`, `Reject` (with note), `Edit` (manager+ only).
   - Manager+ on any non-archived sample: `Archive`.
   - Anyone: `Open photo` (opens `/api/files/{photo_file_blob_id}` in new tab).
5. **Edit form (inline, expand on click):** Editable fields (title, room, hex_swatch with color picker, supplier). Save / Cancel.

### 8.4 NewSampleDialog (`NewSampleDialog.tsx`)

Modal triggered by "+ New sample" button:
- Project dropdown (locked to current project if filter chip is active).
- Title input (required).
- Room input (optional).
- Hex swatch color picker (`<input type="color">` falling back to text input, with live preview swatch).
- Supplier text input (optional).
- Photo upload (optional file input, PNG/JPEG accept).
- Submit → POST `/files` (if photo) → POST `/projects/{pid}/samples` with body including `photo_file_blob_id` if uploaded → drawer opens on the new sample.

### 8.5 PhotoUploadDialog (`PhotoUploadDialog.tsx`)

Reused from existing samples whose owner wants to add/replace a photo. File input + Submit. Same flow as NewSampleDialog's photo step.

### 8.6 ApprovalLedger (`ApprovalLedger.tsx`)

Vertical timeline view in the 3rd subtab. Each row:
- Timestamp (`DD/MM/YYYY HH:MM` mono)
- Actor avatar + name
- Event humanized:
  - `sample.create` → "Created sample #SAM-0042 (Oak veneer)"
  - `sample.approve` → "Approved sample #SAM-0042"
  - `sample.reject` → "Rejected sample #SAM-0042 — *{review_note}*"
  - `sample.archive` → "Archived sample #SAM-0042"
  - `sample.upload_photo` → "Uploaded photo for sample #SAM-0042"
  - etc.
- Pagination controls bottom (Previous / Next, 50 per page).

Click on any sample id link in the ledger → opens the SampleDrawer for that sample.

---

## 9. Seed updates

`seed/hartwood_joinery.py` — add 6 demo samples on ALF-001:

| # | Title | Room | Swatch | Supplier | Status | Reviewer | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Oak veneer — Briggs 0412 | L3 / Reception | #c29075 | Briggs | approved | manager seed user | review_note "Signed", reviewed_at = (now -2d) |
| 2 | Walnut banding | L3 / Reception | #6b6256 | Briggs | approved | manager seed user | reviewed |
| 3 | Laminate — Polytec Oxide | L3 / Meeting Rm | #8a4434 | Polytec | pending | — | created_by drafter |
| 4 | Stone — Corian Deep Black | L3 / Kitchen | #2d2b27 | Corian | pending | — | with photo (PNG fixture) |
| 5 | Timber edge 3mm walnut | L3 / Kitchen | #3c3028 | Briggs | rejected | manager seed user | review_note "Too dark for finish spec" |
| 6 | Acoustic panel grey | L3 / Workzone | #7a7366 | (null) | approved-then-archived | manager seed user | reviewed approved, then archived 1d later |

That's 2 approved active + 2 pending + 1 rejected (auto-Archive) + 1 archived = 6 total. Board = 4, Archive = 2 (rejected + archived), Ledger = ~10 audit rows.

**Photo fixture:** commit one tiny PNG (~3 KB) at `seed/hartwood_joinery/sample_photos/stone-corian.png` for sample #4. Generated as a minimal solid-color PNG via Python (no real photo needed for the demo).

Idempotent via `WHERE NOT EXISTS (SELECT 1 FROM sample WHERE project_id = :p AND title = :t)` check on each insert. Re-seeding is safe.

---

## 10. Testing

### 10.1 Pytest suite

| File | Cases (~) | Focus |
|---|---|---|
| `test_samples_crud.py` | 8 | Create with valid hex; hex regex CHECK rejects "red"/"#fff"/lowercase OK; create requires title; room nullable; edit fields; list by subtab (Board) returns expected counts; GET single; PATCH by non-creator non-manager → 403 |
| `test_samples_workflow.py` | 8 | Pending→approved (not creator); approve-own-sample 403; reject without note 422; reject with note transitions; approved→archived; archived stays out of Board; rejected auto-shows in Archive; full state machine terminal check |
| `test_samples_photo.py` | 5 | Bind PNG via existing /files; bind PDF rejected 415; replace photo (audit captures replaced_file_blob_id); clear photo; viewer cannot upload |
| `test_samples_ledger.py` | 3 | Returns audit rows for entity='sample' on this project; pagination respects limit+offset; cross-workspace returns empty |
| `test_samples_workspace_isolation.py` | 3 | Cross-workspace GET single + GET list + GET ledger all return 404 (or empty for ledger) |

Total ~27 new pytest cases. Workspace truncation in `make test` continues to apply; `sample` is added to TRUNCATE_TABLES in conftest (between `shop_drawing` and `item_attachment` per FK ordering — `sample` references `app_user`, `projects`, and optionally `file_blob`, all of which TRUNCATE later).

Following the lessons from #5b: **route-layer tests live in their own file** (`test_samples_routes.py` if needed) to avoid lock contention with rollback `db` fixture. For now, all the above tests are route-layer (use `truncate_all` + `TestClient`); no separate file needed unless a query-layer rollback test is added.

### 10.2 Playwright E2E

`tests/e2e/isample.spec.ts` — single happy-path:

1. Login as `rin.park@hartwood.test` (drafter).
2. Navigate to `/isample`. Confirm Board subtab shows seed samples (4 cards on ALF-001).
3. Click "+ New sample". Fill title + hex (text input fallback), submit without photo.
4. Drawer opens on new sample (status: pending).
5. Logout. Login as `mason.trent@hartwood.test` (manager).
6. Navigate to `/isample`, find the new sample, click to open drawer, click Approve.
7. Confirm the card now shows status approved.
8. Reject path: open another pending sample, click Reject, type note, submit. Confirm card moves to Archive (since rejected auto-archives).

### 10.3 Manual smoke

1. `make up && make migrate && make seed`.
2. `/isample?project=<ALF id>` — header reads `6 samples across 1 project · 2 awaiting client · 2 approved · 1 rejected`.
3. Board shows 4 cards (2 approved + 2 pending). Archive shows 2 (1 rejected + 1 archived).
4. Open Approval ledger — see chronological audit rows.
5. As drafter, create new sample with photo upload → cards update.
6. As manager, approve a pending sample → moves between subtabs.
7. Try to approve own sample → 403.
8. Try to upload PDF as photo → 415 toast.
9. Try cross-workspace `/isample?project=<other-ws-id>` → 404.

---

## 11. Implementation order

This becomes the sub-project plan; keeping sequencing here for spec-level clarity.

1. **Migration 0016** (`sample` table + 3 indexes).
2. **RBAC matrix update** — `isample` row gains write/approve/comment for drafter+, write for editor.
3. **Pydantic schemas** + **queries.py** (CRUD with audit + UPSERT on photo bind + subtab queries + ledger query).
4. **Routes** (10 endpoints) + mount in `main.py` + tests.
5. **Workspace isolation tests** (cross-workspace 404).
6. **Web `lib/`** types + fetch wrappers.
7. **Page shell** — subtab strip + filter strip + grid container.
8. **SampleCard + SampleSwatch + SampleStatusPill + SampleIdChip**.
9. **SampleDrawer + ReviewActions + edit form**.
10. **NewSampleDialog + PhotoUploadDialog**.
11. **ApprovalLedger** view.
12. **Seed update** (6 samples + 1 PNG fixture).
13. **Playwright E2E spec**.
14. **CLAUDE.md update** + reference doc entries.

That's 14 tasks, similar to #5b. May split task 4 into (a) routes scaffold + first 5 endpoints (b) workflow + photo endpoints if it's getting too big.

---

## 12. Open follow-ups (not blocking #5c)

- **Suppliers as a real registry** — separate table with FK from sample. Adds the Suppliers subtab.
- **Clients tab** — public/external surface for client signoff via shareable link. Significant scope.
- **Sample categories** (BOARD / HARDWARE / STONE / etc.) — add if discovery becomes painful.
- **Item linking** — `sample_item_use(sample_id, item_id)` table. Surfaces "this sample is used by X items".
- **Print Sample Board to PDF** — reuses #5b print pipeline. Defer until requested.
- **Bulk actions** — multi-select + bulk approve/archive.
- **Unarchive** — DB has `archived_at` so column exists; UI just doesn't expose. Trivial to add later.
- **Rich review history** — currently only one `review_note` (latest). Adding a `sample_decision_log` for full back-and-forth.

---

## 13. Resolved decisions

- **Scope.** Lean + Approval ledger (Board / Approval ledger / Archive). Suppliers + Clients subtabs dropped.
- **Status taxonomy.** Sample-specific enum (`pending / approved / rejected`), not the `status_options` table. `archived_at` is a side-state.
- **Sample ID display.** `#SAM-{padded id}` matching #5a's `#SD-{padded}` convention. No alpha-prefix scheme.
- **Reviewer model.** Internal user (drafter+/manager+/admin). Not creator. Not-creator rule enforced in handler.
- **Workflow.** No draft state. Created samples land directly in `pending`. Reject requires note.
- **Photo.** Optional. PNG/JPEG only. Single `file_blob_id` (nullable). PDF rejected at route layer (415).
- **Hex swatch.** Required. CHECK regex `^#[0-9A-Fa-f]{6}$`. Color picker in UI with text fallback.
- **Supplier.** Free-text optional. No separate registry table.
- **RBAC.** Editor write but not approve. Drafter at PM-parity (`approve` granted). Matches the elevated-drafter pattern from `shop_dwgs` and `list`.
- **Audit.** Every state change writes `audit_log` with `entity='sample'`. The Approval ledger subtab is a filtered view of these rows.
- **Subtab semantics.** Board = active (pending+approved, not archived). Archive = archived OR rejected. Ledger = audit log.
- **Photo serving.** Reuses #5a's `GET /files/{id}` endpoint (with `shop_dwgs:read` permission). Cross-permission dependency accepted for v1.
- **Sample creation.** No revision history. Rejected sample → Drafter creates a new sample.
- **Subtab queries.** Composite index `(project_id, status)` + partial index `(project_id) WHERE archived_at IS NULL` cover both Board and Archive.

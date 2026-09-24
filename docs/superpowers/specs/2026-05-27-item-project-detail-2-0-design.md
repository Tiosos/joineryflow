# Item & Project Detail 2.0 — Design (sub-project #11)

**Status:** Draft
**Date:** 2026-05-27
**Plan:** `docs/superpowers/plans/2026-05-27-item-project-detail-2-0.md`
**Driver:** Bill — legacy-parity roadmap from `pictures attached/`.

## 1. Why

Sub-project #10 landed Tracking 2.0 (legacy-parity grid). The detail surfaces it links to are still light: the **Item editor** has cutlist/hardware/board/log/attachments but no **Actions** or **Query** tab, and stores `sketchup_file` / `cab_vision_file` as varchar paths instead of typed file_blob slots. The **Project page** at `/projects/[id]` doesn't exist as a standalone page (only a small read-only modal in tracking); legacy reference screenshots (`pictures attached/ProjectDetails_260417070953.jpeg`, `Dashboard_project*.jpeg`) show a much denser surface: site address, office vs site contacts, builder, classification, status pill, install date, total value, close-out button, lift access notes + sketch, and an accumulated labour-hours block.

#11 closes those gaps. Importantly, **most of the project-level fields already exist** on the `projects` table from the original FileMaker port (`0001_tracking_port.py`): `builder`, `classification`, `site_street`, `site_suburb`, `site_postcode`, `site_state`, `tg_project_manager`, `tg_coordinator`, `status`, `installation_start`, `total_value`, `total_line_items`, `tg_solid`, `carell_pid`. They simply aren't surfaced in `ProjectOut` yet. Item enrichment fields (`floor_plan`, `rls`, `joiery_details`, `cutlist_printed`) similarly exist and need exposing.

What's new (true additions):

- **`projects.closed_at`** + **`projects.closed_by`** for close-out tracking.
- **`project_contact(project_id, kind, position, name, email, mobile, notes)`** with `kind IN (office, site)`.
- **`project_lift_access(project_id, notes, sketch_file_blob_id)`** — one row per project, optional sketch.
- **`item_query(item_id, asked_by, answered_by, asked_at, answered_at, question, answer)`** for the Query tab.
- **`item_document(item_id, file_blob_id, label, ordering)`** for the open Document Register.
- Attachment kinds extended from `{cv_drawing, floor_plan, site_measure}` to `{sketchup, cabvision, floor_plan, site_measure}`. **`cv_drawing` stays in the CHECK as a legacy synonym** so existing rows + tests aren't broken.

## 2. Confirmed scope

### Item detail

- New tab **Actions** — collection of one-click buttons:
  - Print combined PDF (links to `/items/{id}/combined.pdf` — already exists).
  - Print cutlist / hardware PDFs (already exist).
  - Set status (opens existing `StatusPopup`).
  - Mark REQ (writes `item_stages.REQ.done_date = today` via existing lifecycle endpoint).
  - Jump to orderbook.
  - Toggle Painting Req / Solid Surface Req / Cutlist Printed (calls existing PATCH).
- New tab **Query** — free-text Q&A per item.
  - List of all queries (newest first) with question, asker, asked_at; answer, answerer, answered_at.
  - "Ask a question" form (any role with `list:read`).
  - "Answer" button on each question (drafter+ / manager+).
- Header flags: **Painting Req** / **Solid Surface Req** / **Cutlist Printed** — already booleans; expose as toggleable chips.
- Reference fields: **Floor Plan** / **RLS** / **Joinery Details** — already varchar(64); expose via PATCH + a small "Refs" panel.
- **AttachmentsTab** restructured:
  - Slots: **SketchUp** (new), **CabVision** (new), **Floor Plan**, **Site Measure**.
  - New **Document Register** below the named slots — open list via `POST /items/{iid}/documents`.
  - PDF gate stays for named slots; Document Register accepts PDF/PNG/JPEG.

### Project detail

- New page `/projects/[id]` (was: only `/projects/[id]/procurement/...` existed).
- **Header strip**: project_code · name · status pill · builder · classification · install_start · total_value · close-out button (admin/manager only).
- **Details panel** (left): site address (4 fields) + TG team + flags.
- **Contacts panel** (centre): office + site contacts; "Add contact" link.
- **Lift & access panel** (right): notes textarea + sketch upload (single file_blob slot).
- **Labour hours card** (bottom): view returns zero today; wires live in #14.
- Tracking modal gains "Open full project page →" footer link.

### RBAC

No new modules. Reuse existing matrix:
- `project_contact` + `project_lift_access`: `tracking:write` (manager/admin/drafter) for writes; `tracking:read` for reads.
- `item_query`: `list:read` to ask + read; `list:write` to answer.
- `item_document`: `list:write` for bind/unbind; `list:read` for list.
- Close-out: admin/manager only.

### Workspace isolation

All new tables join through `projects.workspace_id = :wid` per the post-`cc7ea11` pattern. Cross-workspace 404.

## 3. Schema changes — migration 0025

```sql
-- Project close-out
ALTER TABLE projects
  ADD COLUMN closed_at TIMESTAMPTZ NULL,
  ADD COLUMN closed_by BIGINT NULL REFERENCES app_user(id) ON DELETE SET NULL;

-- Project contacts (office + site)
CREATE TABLE project_contact (
  contact_id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  kind       VARCHAR(8) NOT NULL CHECK (kind IN ('office','site')),
  position   VARCHAR(64),
  name       VARCHAR(128) NOT NULL,
  email      VARCHAR(255),
  mobile     VARCHAR(32),
  notes      TEXT,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by BIGINT REFERENCES app_user(id) ON DELETE SET NULL
);
CREATE INDEX idx_project_contact_project ON project_contact (project_id, kind, sort_order);

-- Project lift access (1 row per project)
CREATE TABLE project_lift_access (
  project_id           BIGINT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
  notes                TEXT,
  sketch_file_blob_id  BIGINT REFERENCES file_blob(file_blob_id) ON DELETE SET NULL,
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by           BIGINT REFERENCES app_user(id) ON DELETE SET NULL
);

-- Item Query Q&A
CREATE TABLE item_query (
  query_id      BIGSERIAL PRIMARY KEY,
  item_id       BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  asked_by      BIGINT NOT NULL REFERENCES app_user(id) ON DELETE SET NULL,
  asked_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  question      TEXT NOT NULL,
  answered_by   BIGINT REFERENCES app_user(id) ON DELETE SET NULL,
  answered_at   TIMESTAMPTZ,
  answer        TEXT
);
CREATE INDEX idx_item_query_item ON item_query (item_id, asked_at DESC);

-- Item Document Register
CREATE TABLE item_document (
  document_id   BIGSERIAL PRIMARY KEY,
  item_id       BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  file_blob_id  BIGINT NOT NULL REFERENCES file_blob(file_blob_id),
  label         VARCHAR(128),
  sort_order    INT NOT NULL DEFAULT 0,
  uploaded_by   BIGINT NOT NULL REFERENCES app_user(id) ON DELETE SET NULL,
  uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_item_document_item ON item_document (item_id, sort_order);

-- Extend attachment kinds
ALTER TABLE item_attachment DROP CONSTRAINT IF EXISTS item_attachment_kind_check;
ALTER TABLE item_attachment
  ADD CONSTRAINT item_attachment_kind_check
  CHECK (kind IN ('cv_drawing','sketchup','cabvision','floor_plan','site_measure'));

-- Labour hours placeholder view (zero today)
CREATE OR REPLACE VIEW project_labour_hours_view AS
SELECT
  p.project_id,
  0::numeric AS site_install,
  0::numeric AS assembly,
  0::numeric AS administration
FROM projects p;
```

## 4. API surface

### 4.1 Project

`GET /projects/{id}` — extend `ProjectOut` additively with builder, classification, address, TG team, flags, close-out fields, contacts, lift_access, labour_hours.

`PATCH /projects/{id}` — extend with the new metadata fields.

`POST /projects/{id}/close-out` — admin/manager only. Sets `closed_at = now()`, `closed_by = caller`, `status = 'Closed'`. 409 if already closed.

`POST /projects/{id}/contacts` / `PATCH /contacts/{cid}` / `DELETE /contacts/{cid}`.

`PUT /projects/{id}/lift-access` — upsert. `DELETE` to clear.

### 4.2 Item

`GET /items/{iid}/queries`, `POST /items/{iid}/queries`, `POST /queries/{qid}/answer`, `PATCH /queries/{qid}/answer`.

`GET /items/{iid}/documents`, `POST /items/{iid}/documents`, `DELETE /documents/{did}`, `PATCH /documents/{did}`.

Item attachment `kind` path constraint expands to accept `sketchup`/`cabvision`.

`PATCH /items/{iid}` extended to accept `floor_plan`, `rls`, `joiery_details`, `cutlist_printed`.

### 4.3 Audit events (new)

- `project.close_out`
- `project.contact.create|update|delete`
- `project.lift_access.update`
- `item.query.create|answer|edit_answer`
- `item.document.bind|unbind|update`

## 5. Frontend

### Item editor

- `EditorTabs.tsx`: add `actions` and `query`.
- New `ActionsTab.tsx`: 6 large action buttons (print combined / cutlist / hardware, set status, mark REQ, jump to orderbook, flag toggles).
- New `QueryTab.tsx`: Q&A list + "Ask" form.
- `AttachmentsTab.tsx`: 4 slots in 2×2 grid + Document Register list below.
- Header chips: Painting Req / Solid Surface Req / Cutlist Printed (click-to-toggle).
- Refs panel: Floor Plan / RLS / Joinery Details (click-to-edit).

### Project page (new)

- `/projects/[id]/page.tsx` — server component, 3-column layout.
- Header strip with close-out button (gated).
- Left: address + TG team.
- Centre: contacts.
- Right: lift access.
- Footer: labour hours card.

### Tracking modal

- Footer link "Open full project page →".

## 6. Seed

- ALF-001 gets:
  - Builder + classification + Melbourne site address.
  - 4 office contacts + 2 site contacts.
  - Lift access notes + a deterministic SVG-PDF sketch (reuses #5a helper).
  - 2 item queries on item 1 (one answered, one open).
  - 2 documents on item 1.
- Idempotent.

## 7. Verification

- `make migrate` clean.
- `make test` — new files: `test_project_enrichment.py`, `test_project_contacts.py`, `test_item_queries.py`, `test_item_documents.py`. Happy path + RBAC deny + cross-workspace 404.
- `make seed` idempotent.
- Manual: `/projects/1` shows the 3-column layout; item editor's new tabs render; close-out works once.

## 8. Out of scope

- Labour hours data is zero until MyHours (#14).
- Threaded conversations on Query (v1 = single Q + single A).
- Variations driven by `var_boq` (lands with #13).
- Existing varchar(255) `sketchup_file` / `cab_vision_file` columns stay; future migration backfills + drops.
- `cv_drawing` legacy kind stays as a synonym.

## 9. Open questions (defaults noted)

- Close-out reversible? **Default: no in v1; manager+ can flip `status` via PATCH which auto-clears `closed_at/by`.**
- Lift access — single sketch or multi-image? **Default: single sketch.**
- Item documents — "category" field? **Default: free-text label only.**

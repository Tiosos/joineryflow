# Early Sub Projects

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## PM Workbench (sub-project #2 + #3)

- Lives on top of Foundation; migrations 0008 (drafter role widening) + 0009 (legacy users -> app_user repoint, projects.pm_id, drop users).
- Drafter-narrow gate: `require_drafter()` — items / modules / parts / hardware_lines / project_hardware_catalog mutations only allow `auth_role IN {drafter, manager, admin}`.
- New routers under `apps/api/app/{home, projects, items, parts, hardware_lines}/`. Mounted in `main.py`.
- Every item-scoped mutation writes both `audit_log` (workspace governance) and `item_edit_log` (item history) in the same DB transaction. Helper: `apps/api/app/edit_log.py`.
- Web routes: `/home`, `/projects`, `/tracking?project_id=`, `/items/[id]?tab=cutlist|hardware|board|log`. (#2 made `/home` the landing page in place of `/dashboard`; **#9a reversed that** — `/home` is now a bare `redirect("/dashboard")` and `/dashboard` is the real landing page.)
- Editor mode is detected by `proxy.ts` writing `x-pathname`; layout reads it and hides TabStrip + SideBar, swapping in a "← Return to home" link.
- State: raw `fetch()` + URL search params + controlled inputs. **No TanStack Query / React Hook Form / Zustand in v1.**
- Procurement UI button on `/tracking` is hidden behind `NEXT_PUBLIC_PROCUREMENT_UI_READY=1`, now defaulted to `1` in `.env.example` (it was absent, so the button was off in every fresh dev setup even though #4 shipped). A `.env` copied before that fix won't have it.
- PDF generation buttons render disabled with tooltip ("ships in sub-project #5").
- **Controlled Lock** (migration `0032`, Q509 — replaces the advisory
  soft-lock). First save still claims ownership. A non-owner's save on a locked
  item is **no longer applied**: `PATCH /items/{id}` answers
  `409 {code: "LOCK_REQUEST_CREATED", …}` and the body is held as an
  `item_lock_request` row. `GET /items/{id}/lock-requests` lists them;
  `POST /lock-requests/{rid}/{approve,reject}` decides, restricted to the lock
  owner or a manager/admin. Approval replays the stored body through the
  ordinary save path — the **edit log credits the requester**, the audit row
  names the approver. Saving again revises your own pending request rather than
  queueing a second (`uniq_pending_lock_request`).
  `event='item.lock_overridden'` is **retired**: nothing emits it, and existing
  rows are history only. Scope is `PATCH /items/{id}` alone, **and there is no
  project-level lock** (Q566: `projects` has no lock column). **Exceptions since
  *Lock checks on module delete* and *Lock checks on the other module and part
  writes*:** every module and part write, and the CV import commit and every
  hardware line write, now answer to the item's locks too (Hard, Approval,
  Controlled). **Since *Lock checks on status and lifecycle*:** `/status`,
  `/items/bulk-status` and `/lifecycle/{stage_key}` answer to the **Hard and
  Controlled** locks — **not the Approval Lock**, which is cleared by a status
  change and so cannot gate one. **Since *Lock checks on attachments and the
  document register*:** every attachment-slot write and every Document Register
  write answers to all three (Hard, Approval, Controlled). **Since *Lock checks on
  item queries and material takes*:** answering a query and every material-take
  write answer to Hard + Controlled (no Approval Lock), and *asking* a query to the
  Hard Lock only. QC records and comments are deliberately not lock-checked.
- Lifecycle stage_key (REQ..INST) ≠ items.stage (site location); never use bare "stage" for lifecycle.

## Procurement Workbench (sub-project #4)

- New backend module `apps/api/app/procurement_v1/` mounted at top-level paths
  (`/projects/{pid}/materials`, `/batches`, `/batches/{bid}/allocations`,
  `/procurement-queue`; it also shipped `/catalogs/{type}`, since retired —
  see #7a). The legacy `/procurement/*`
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
- All 6 catalog tables use `description` as the readable name and `sku` as
  the SKU (added by migration 0007). Each also has a legacy NOT NULL UNIQUE
  column: `code` (board), `internal_ref` (custom_made), `slab_id`
  (benchtop), `model_number` (appliance), `contract_ref` (equipment_hire).
  `equipment_hire` PK is `hire_id`, not `material_id`, and requires a
  `project_id` FK on insert.
- Seed (`make seed`) inserts one delivered batch + one in-transit batch +
  one allocation on project ALF-001 so the resolution-flow demo works
  out of the box.

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
  `StreamingResponse` with `Content-Disposition: inline` (RFC 8187 dual
  filename for non-ASCII names).
- Web routes (**superseded by *Shop Drawings register redesign* below** — the card
  grid, drawer and subtabs described here were replaced by a register table, a
  details panel and a full-screen viewer; the API and workflow notes stand):
  - `/shop-dwgs?project=…&subtab=current|in_review|archive&room=…&q=…` —
    list page with subtabs + filter strip + 3-col card grid.
  - `?drawing=N&rev=M` opens a right-side drawer with PDF/image viewer +
    revision history strip + contextual review actions.
- Workflow: `draft → pending → approved | rejected`. The not-uploader rule on
  approve/reject is enforced in the route handler; the partial unique index
  enforces the in-flight invariant. Approve updates
  `shop_drawing.current_revision_id` atomically. Archive 409s on already-
  archived (no silent re-archive); patch enforces creator-or-manager rule.
- Allowed file types: PDF / PNG / JPEG (validated by magic bytes), plus —
  since the 0036 attachment slots — SketchUp `.skp` and Cabinet Vision `.cvj`
  (see *Item & Project Detail 2.0*). SVG, DWG, etc. rejected with 415.
  **Shop drawings themselves still take PDF / PNG / JPEG only**: both bind
  paths check the blob's mime (422 otherwise), because `/files` no longer
  enforces that on its own.
- Thumbnails are deterministic SVG placeholders seeded from `drawing_id`
  (no PDF rendering pipeline in v1).
- Seed (`make seed`) inserts 2 fixture PDFs + 6 demo drawings on ALF-001
  spanning Current / In review / Archive. Re-runnable: the seed block does
  `DELETE FROM shop_drawing WHERE project_id = ALF-001` before inserts so
  it's idempotent.
- Out of scope (deferred to #5b/#5c): item attachments (CV drawing, floor
  plan, site-measure PDF), Combined PDF generation, real PDF thumbnails,
  Templates subtab, iSample tab, orphan blob GC, cloud storage backend,
  unarchive button.

## PDF Generation + Item Attachments (sub-project #5b)

- New backend modules `apps/api/app/item_attachments/` (3-slot CRUD over file_blob)
  and `apps/api/app/printing/` (WeasyPrint engine + Jinja2 templates +
  `cutlist.pdf` / `hardware.pdf` / `combined.pdf` routes). Both mounted at
  top-level paths from `main.py`.
- Migration 0015 adds `item_attachment(item_id, kind, file_blob_id, ...)` with
  `UNIQUE (item_id, kind)` slot constraint and `ON DELETE CASCADE` from items.
  Three legal kinds: `cv_drawing`, `floor_plan`, `site_measure` (**since
  `0036` there are five** — `sketchup` and `cabvision` added beside them; the
  Combined PDF still uses only these three. See *Item & Project Detail 2.0*).
  (Migration
  0014 was the workspace-isolation hardening that landed alongside this
  sub-project — `projects.workspace_id` direct FK + the `(p.pm_id IS NULL OR
  …)` predicate retired.)
- PDF engine: WeasyPrint 63+ (HTML→PDF render) + pypdf 5+ (merge generated
  + uploaded sources). Pango runtime libs added to the api Dockerfile
  (~25 MB). No new container.
- Print templates live at `apps/api/app/printing/templates/{cutlist,hardware,
  cover_combined,painting,missing_attachment}.html` + `print.css`. Inter +
  JetBrains Mono `.woff2` fonts committed under `seed/fonts/` (~400 KB).
- Print routes:
  - `GET /items/{iid}/cutlist.pdf` — render parts table.
  - `GET /items/{iid}/hardware.pdf` — render hardware grouped by **material
    type** (BOARD / HARDWARE / CUSTOM / BENCHTOP / APPLIANCE / HIRE; not by
    supplier — supplier-grouping deferred until catalog enrichment exposes
    per-table supplier columns).
  - `GET /items/{iid}/combined.pdf` — assembles cover + cutlist + hardware +
    3 attachments (or placeholder pages when missing or unparseable) +
    painting page (only when at least one part has `paint_instruction != 'NONE'`).
  - All return `inline; filename=...` Content-Disposition with
    `Cache-Control: no-store`. Browser opens in a new tab via
    `<a target="_blank">`.
- Item attachment routes:
  - `GET /items/{iid}/attachments` — bundle of 3 slots (5 since `0036`),
    populated or null.
  - `POST /items/{iid}/attachments/{kind}` — bind/replace via
    `{file_blob_id}` body. PDF-only mime gate (415 on PNG/JPEG; the
    file_blob table itself remains generic). Since `0036` the gate is per
    slot — `sketchup` / `cabvision` take `.skp` / `.cvj` instead.
  - `DELETE /items/{iid}/attachments/{kind}` — clear slot.
- RBAC: print routes use `("list", "read")` (any reader can print);
  attachment mutations use `("list", "write")` (drafter+, since drafter is
  PM-parity on `list`). The PDF-only gate is enforced in the route handler;
  `bind_attachment` returns `ValueError` which the route maps to 415.
- Workspace isolation: print + attachment routes scope through
  `projects.workspace_id = :w` directly (the workspace-isolation hardening
  in commit `cc7ea11` retired the legacy pm_id chain).
- Audit hooks: `item.print.{cutlist|hardware|combined}` per render;
  `item_attachment.{bind|clear}` per mutation. The bind audit payload includes
  `replaced_file_blob_id` when overwriting an existing slot.
- Web side:
  - New "Attachments" tab in the item editor at
    `apps/web/app/(app)/items/[id]/_components/AttachmentsTab.tsx` with three
    slot cards (one per kind). Each card supports Open / Replace / Delete
    (Replace + Delete gated on drafter+). Wired into `EditorTabs.tsx` via the
    `TABS` const + `TAB_LABELS` map; page.tsx threads `me?.auth_role` through
    as a new prop.
  - The 3 disabled "Print …" buttons in `EditorFooter.tsx` are now live
    `<a href="/api/items/{id}/{kind}.pdf" target="_blank">` download links.
    The Combined button shows a tooltip listing which slots are populated /
    missing (read from a prefetched attachments bundle).
- Seed: first 2 ALF-001 items get attachments on `make seed` — item 1 has
  3/3 slots populated (Combined shows all real PDFs), item 2 has 1/3
  (Combined shows 2 placeholder pages).
- Defensive PDF-merge fallback: `routes.py` validates each attachment's
  bytes via `pypdf.PdfReader` before merging. Unparseable PDFs (corrupt or
  fixture stubs) substitute the `missing_attachment.html` placeholder so the
  Combined render never crashes. Test fixtures benefit from this.
- Out of scope (deferred): iSample (sub-project #5c), async/queued render,
  PDF caching, real attachment thumbnails, PNG/JPEG attachments, supplier
  grouping in Hardware print, custom print templates, async fetch+Blob loading
  indicator (current Combined uses plain `target="_blank"`).

## iSample — Sample Wall (sub-project #5c)

- New backend module `apps/api/app/samples/` (CRUD + workflow + photo bind/clear
  + ledger). Mounted at top-level paths from `main.py`.
- Migration 0016 adds `sample(sample_id, project_id, title, room, hex_swatch,
  supplier, status, review_note, reviewed_by/at, photo_file_blob_id,
  archived_at/by, created_by/at, updated_at)` with hex regex CHECK
  (`^#[0-9A-Fa-f]{6}$`), 3-value status CHECK, and 3 indexes
  (project, project+status composite, partial WHERE archived_at IS NULL).
- RBAC: `isample` row in the matrix gives drafter/manager/admin
  `{read, write, approve, comment}` (PM-parity elevation pattern).
  Editor gets `{read, write}` (no approve). Viewer/purchase_officer get `{read}`.
- Workflow: `pending → approved | rejected`. Reject requires `review_note`.
  Reviewer cannot be the creator (in-handler check). Archive transition
  (creator on own OR manager+) sets `archived_at`. Rejected samples
  auto-show in Archive subtab.
- Subtabs:
  - **Board** = `archived_at IS NULL AND status IN ('pending','approved')`
  - **Approval ledger** = `audit_log` filtered to `event LIKE 'sample.%'`
    for samples in this project, paginated (50/page)
  - **Archive** = `archived_at IS NOT NULL OR status = 'rejected'`
- API endpoints (10):
  - `GET /projects/{pid}/samples?subtab=board|archive&q=&status=&supplier=`
  - `GET /projects/{pid}/samples/ledger?limit=50&offset=0`
  - `GET /samples/{sid}`
  - `POST /projects/{pid}/samples`
  - `PATCH /samples/{sid}` (creator-or-manager+)
  - `POST /samples/{sid}/approve`, `.../reject`, `.../archive`
  - `POST /samples/{sid}/photo`, `DELETE /samples/{sid}/photo`
- Photo handling: optional, single `file_blob_id` (PNG/JPEG only — PDF blobs
  rejected at the route layer with 415). Reuses #5a's `POST /files` upload
  endpoint and `GET /files/{id}` streaming download. Photo-as-background on
  card swatch when present, with hex chip overlay in bottom-right corner.
- Sample IDs displayed as `#SAM-{padded id}` matching #5a's `#SD-{padded}`
  convention. No alpha-prefix scheme.
- Web routes:
  - `/isample?project=…&subtab=board|ledger|archive&q=&status=&supplier=&sample=N&new=1`
  - 5-column responsive grid (drops to 4/3/2/1 columns at smaller widths)
  - Drawer opens on `?sample=N`, deep-linkable
  - "+ New sample" dialog with color picker + optional photo
- Workspace isolation: all queries gate via `projects.workspace_id = :w`
  (post-hardening pattern from `cc7ea11`). Cross-workspace returns 404.
- Audit hooks: `sample.{create|update|approve|reject|archive|upload_photo|clear_photo}`.
  The Approval ledger view IS this audit_log filtered.
- Seed: `make seed` adds 6 demo samples on ALF-001 — 2 approved + 2 pending
  (one with photo) + 1 rejected + 1 archived. Header reads
  `6 samples · 2 awaiting client · 3 approved · 1 rejected`.
- Out of scope (deferred): Suppliers as a real registry (free-text only),
  Clients tab (no client-facing surface), sample revisions (rejected =
  create new), Print Sample Board to PDF, real-time client signoff via link,
  bulk actions, sample categories, item linking, unarchive UI.

## Catalog enrichment + CV Mappings (sub-project #7a)

- New backend module `apps/api/app/catalog/` mounted at `/catalog/*`
  (singular). 7 sub-routers: 6 per
  material type (`board-materials`, `hardware-materials`, `custom-made`,
  `benchtop-materials`, `appliances`, `equipment-hire`) plus
  `/catalog/cv-mappings`. RBAC gate `("catalog", action)`.
- Migration 0017 adds 5 enrichment columns (`synonyms text[]`,
  `default_supplier`, `default_lead_time_days`, `archived_at`, `archived_by`)
  to all 6 catalog tables, plus a GIN index on `synonyms` and a partial
  active-row index. Also CREATEs `cv_material_mapping` (workspace-scoped
  UNIQUE on `(workspace_id, cv_code)`).
- New `catalog` row in the RBAC matrix. Drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`;
  purchase_officer `{read,comment}`; viewer `{read}`. Editor gets `write` so
  Foreman/Machine team can propose catalog edits.
- Soft-archive only — POST `/catalog/{slug}/{mid}/archive` sets
  `archived_at`+`archived_by`; 409 on already-archived. Hard delete is
  reserved for `cv_material_mapping`.
- Bulk import is all-or-nothing. POST `/catalog/{slug}/bulk` validates every
  row first; if any row fails Pydantic, returns `{created: 0, errors: [...]}`
  without inserting. Audit: one `catalog.{table}.csv_import` row per import
  (not per row).
- Web routes:
  - `/catalog?tab=board|hardware|custom_made|benchtop|appliance|hire|stock|cv-mappings`
    (`stock` added by 0025; `stock` and `cv-mappings` are self-contained
    panels — the six catalog-table tabs are typed as `MaterialTab`)
  - Reached from the `Catalog` entry on the TabStrip secondary row (it was a
    SideBar link when #7a shipped; #9a moved it). Not permission-gated.
- Workspace isolation enforced on every read + write via `workspace_id`
  column (already on the 6 catalog tables from migration 0007;
  added to `cv_material_mapping` by 0017). Cross-workspace returns 404.
- Route ordering caveat: cv-mapping routes (`/catalog/cv-mappings*`) are
  declared BEFORE the parameterised `/catalog/{slug}` routes in
  `apps/api/app/catalog/routes.py` so the literal path wins.
- **`/catalog/*` is the only surface for these six tables.** The parallel
  `/catalogs/*` (plural) module that Procurement Workbench v1 shipped —
  gated on `orderbook`, unscoped by workspace, and hard-deleting on DELETE —
  has been **retired**; the convergence #7a deferred is done. The project
  Procurement page's Catalog tab reads and writes through `/catalog/{slug}`.
  Guards in `test_catalog_routes.py` fail if the plural namespace returns.
  Removal is soft-archive only: there is no DELETE route on a catalog row.
  (Hard delete remains legal for `cv_material_mapping` alone.)
- **Supplier link (shipped later):** each row also carries the real `default_supplier_id` FK, editable
  from the grid's *Supplier link* column — see *Catalog supplier link* at the end of this file.
- Seed (`make seed`) enriches the existing 2 board_materials + 4
  hardware_materials with synonyms/supplier/lead-time, adds 4 new demo
  boards (BM-101..BM-104), and inserts 2 demo cv_material_mapping rows
  (`'18-PB' → board_materials.BM-001`, `'700.0KC2.054.00' →
  hardware_materials.HM-002`). Idempotent.
- Out of scope (deferred to #7b): `cv_import_run`, the Cutlist tab CV
  import wizard, the synonym-fuzzy resolver. (Deferred to #7c): Board tab,
  `/cut-floor` page, CutPlan, CutSchedule.

## CV Import wizard (sub-project #7b)

- New backend module `apps/api/app/cv/` — `parser.py` (CSV header
  normalisation + row coercion), `resolver.py` (mapping → synonyms[] →
  exact-sku → unknown), `queries.py` (run lifecycle + commit transaction),
  `routes.py` (4 routes mounted at top-level paths).
- Migration 0018 adds `cv_import_run(cv_import_run_id, project_id, item_id,
  source_filename, sha256, row_count, status, started_at, completed_at,
  error_log jsonb, created_by)` with status CHECK
  ('preview','committed','failed') and 2 indexes
  (`idx_cv_import_run_item`, `idx_cv_import_run_status`).
- New `cut_floor` row in the RBAC matrix (sits between `catalog` and
  `it_management` in `_ALL_MODULES`). Drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`;
  purchase_officer/viewer `{read}`. The full `/cut-floor` page + CutPlan +
  Board tab arrive in #7c — #7b only consumes the row from the CV import
  routes here.
- 5 routes:
  - `POST /items/{iid}/cv-imports/preview` — multipart `file` OR form
    field `body`. Parses, resolves, persists `cv_import_run` with
    `status='preview'` and the full snapshot in `error_log`.
  - `POST /items/{iid}/cv-imports/{run_id}/commit` — body `CvCommitIn`,
    optional `?mode=replace`. Single transaction inserts modules + parts +
    catalog rows + mappings + audit/edit log; flips run to `committed`.
  - `GET /items/{iid}/cv-imports` — history (newest first).
  - `GET /items/{iid}/cv-imports/replace-impact` (`cut_floor:write`, the
    commit's own gate; *added later, see below*) — `{modules, live_comments}`.
  - `GET /cv-imports/{run_id}` — single run + cached preview snapshot.
- 3-phase wizard mounted in the Drafter Editor Cutlist tab via
  `?tab=cutlist&import=cv`. Phase A (paste/upload), Phase B (resolve
  unknown codes inline — `Use existing` is disabled in v1; `Create new`
  ships for the 5 simple catalog tables; `Skip` always available),
  Phase C (confirm + optional **Replace existing modules** checkbox when
  the item already has modules — and, when those modules carry comments, an
  amber warning naming how many will be deleted with them).
- **Replace warns about the comments it deletes** (*added later; the user chose
  a **wizard warning only**, asked before building*). A comment cascades with the
  module it is on (migration `0043`), so `?mode=replace` deleted every module
  thread of the item without saying so. Now: Phase C fetches
  `GET /items/{iid}/cv-imports/replace-impact` **fresh when the step opens** (not
  from the preview, whose snapshot can be minutes old) and shows
  "**N comments** on these modules will be permanently deleted…" when N > 0; if
  the check itself fails it says so rather than stay silent. **The count is live
  comments, replies included** (`deleted_at IS NULL`, user's choice) — the
  cascade also removes soft-deleted rows, which are already gone from every
  screen, so the true row count can be higher. **The API is unchanged in what it
  allows**: `replace` is still an explicit opt-in and is *not* refused or gated
  on an acknowledgement (the user declined that). What changed is that the loss is
  now visible afterwards: `CvCommitOut.replaced_comment_count`, the
  `cv.import.replace_wipe` audit payload (`deleted_comment_count`) and the
  `cv.import.commit` payload (`replaced_comment_count`) carry the number, counted
  **before** the DELETE. The wizard's done message repeats it. Tests:
  five new in `test_cv_routes.py` (live-only count scoped to this item; zero
  case; 403 for a viewer / 404 for another workspace's item; the response and both
  audit rows; a first import reports 0) — **all five fail against the unfixed
  source**; `tests/e2e/cv_replace_comments.spec.ts` (3), re-runnable and run three
  times back to back beside `cv_import.spec.ts` (which shares `JO-TP01`).
- File caps enforced server-side: 1 MB hard cap (`MAX_CSV_BYTES`),
  10 000 logical rows (`MAX_LOGICAL_ROWS`). 415 with
  `code='FILE_TOO_LARGE'` or `code='TOO_MANY_ROWS'` if exceeded.
- Resolver order (per spec §6.2): `cv_material_mapping` → catalog
  `synonyms[]` (single-table hit) → catalog `sku` exact match → unknown.
  Multiple-table hit returns `unknown` with hint
  `multiple_synonym_matches`. Workspace-isolated everywhere via
  `WHERE workspace_id = :w`.
- Re-import: default 409 with `code='ITEM_NOT_EMPTY'` if the item already
  has modules. `?mode=replace` (or `body.replace=true`) wipes via
  DELETE-CASCADE and re-imports; audit emits `cv.import.replace_wipe`
  with `deleted_module_ids`.
- Commit transaction (per spec §6.6): inserts new catalog rows from
  `create_new` resolutions (legacy NOT NULL UNIQUE column derived from
  `sku`), writes `cv_material_mapping` for `use_existing`/`create_new`
  resolutions without a prior mapping, inserts modules + parts (parts
  with `paint_instruction='NONE'`), writes audit (`cv.import.commit` +
  per-part `part.create` + per-module `module.create`) and item_edit_log
  (per module `_create_module`, per part `_create_part`, one summary
  `_cv_import` row). Rollback on error sets `status='failed'` and emits
  `cv.import.fail`.
- **Schema constraint**: `parts` only has `board_material_id` (not a
  generic material FK), so non-board CV codes persist with
  `board_material_id=NULL`; the resolution trace is preserved in the
  `cv.import.commit` audit payload + `cv_import_run.error_log` snapshot
  + the part's `comment` field (`[material: {table}#{id}]`).
- Preview snapshot: full `CvPreviewOut` is stored in
  `cv_import_run.error_log` under key `_preview_snapshot`. The commit
  endpoint also reads `_parsed_parts` and `_resolutions` from the same
  jsonb column to rehydrate without re-parsing.
- "Create new" mini-form ships for the 5 simple catalog tables
  (board / hardware / custom_made / benchtop / appliances). Equipment
  Hire is disabled with a tooltip linking to `/catalog?tab=hire` (it
  requires a project_id FK on insert).
- Seed (`make seed`) writes 1 committed `cv_import_run` row on ALF-001
  item 1 (no real modules/parts inserted — they already exist from the
  PM Workbench seed). Idempotent: deletes existing rows for the item
  before inserting.
- Out of scope (deferred to #7c): CutPlan / CutSchedule / Board tab /
  `/cut-floor` page, Phase B `Use existing` typeahead. (Indefinite):
  bin-packing optimiser, three-way merge re-import UI, Cabinet Vision
  API integration.

## Cut Floor — CutPlan + CutSchedule + Board tab (sub-project #7c)

- New backend module `apps/api/app/cut_floor/` (schemas / queries /
  routes). All routes gated by `("cut_floor", action)`. The RBAC row
  itself was added in #7b — drafter/manager/admin
  `{read,write,approve,comment}`; editor `{read,write,comment}`
  (Machine team can mutate but not approve); purchase_officer / viewer
  `{read}` only.
- Migration 0019 adds `part_slot.part_id` (nullable FK →
  `parts(part_id)` ON DELETE SET NULL), `cut_schedule.{priority,
  assigned_to, created_at, created_by, updated_at}`, and
  `cut_plan.{created_by, notes}`. Two new indexes: `idx_part_slot_part`
  + `idx_cut_schedule_date_priority`.
- Note: existing `cut_plan` / `cut_sheet` / `part_slot` /
  `cut_schedule` PKs are named `id`, not `cut_plan_id` etc. Code
  follows the actual column names.
- Routes:
  - **CutPlan**: `POST /projects/{pid}/cut-plans` (single transaction
    creates plan + sheets + slots), `GET /projects/{pid}/cut-plans`
    (newest first), `GET /cut-plans/{plan_id}` (full nested),
    `GET /items/{iid}/cut-plan` (latest plan filtered to sheets that
    contain ≥1 slot for this item; foreign slots flagged `is_foreign`),
    `DELETE /cut-plans/{plan_id}` (409 with code `PLAN_HAS_SCHEDULES`
    when any non-cancelled `cut_schedule` references it; else hard
    delete + CASCADE).
  - **CutSchedule**: `GET /cut-schedules?date=&project_id=&status=`,
    `GET /cut-schedules/{sid}`, `POST /cut-schedules` (auto
    `priority = MAX + 100` for the day, or `100`),
    `PATCH /cut-schedules/{sid}` (transitions enforced — see below),
    `POST /cut-schedules/reorder` (rewrites priorities densely as
    `100, 200, 300 …` for an ordered id list of one date),
    `DELETE /cut-schedules/{sid}` (soft-cancel; second cancel is 409).
- Status transition matrix (binding):
  `planned → running → done`, plus `planned/running → cancelled`. Any
  other transition (e.g. `done → running`, `cancelled → *`) returns
  409 `{code: "BAD_TRANSITION", from, to}`.
- Workspace isolation everywhere via `cut_plan.workspace_id`. Cut
  schedules join through cut_plan; cut sheets and part slots join
  through cut_plan. Cross-workspace reads return 404.
- **Fixed later.** `cut_schedule.assigned_to` is a plain FK to `app_user`
  with no workspace check of its own, and `list_cut_schedules` /
  `get_cut_schedule` join it to `full_name` for display — unlike its sibling
  `shop_floor`, which validates every `worker_id` against
  `(workspace_id, is_shop_worker)`, `POST /cut-schedules` and
  `PATCH /cut-schedules/{sid}` accepted any `app_user.id` in the whole
  database, so a caller could assign (and thereby leak the name of) a user
  from a different workspace. `queries.user_in_workspace()` (same shape as
  `items/queries.py::_user_in_workspace` for `contractor_id`) now guards
  both routes; unvalidated ids get `422`. Pinned by
  `test_create_cut_schedule_rejects_foreign_assigned_to` /
  `test_patch_cut_schedule_rejects_foreign_assigned_to`.
- **Fixed later.** `has_active_schedules()` (the guard behind
  `DELETE /cut-plans/{plan_id}`'s `PLAN_HAS_SCHEDULES` 409, above) only
  blocked `planned`/`running` schedules — contradicting this file's own
  "non-cancelled" wording and letting a plan with a **`done`** schedule
  (a record that a nest was actually cut) hard-delete via `CASCADE`, taking
  that production record with it. `DELETE /cut-plans/{plan_id}` now blocks
  on any status other than `cancelled`, matching the documented rule; only
  a cancelled schedule no longer blocks deletion. Pinned by
  `test_delete_cut_plan_blocks_when_done_schedule_exists`, confirmed to
  fail (204 instead of 409) against the pre-fix code.
- Foreign-slot rule: `GET /items/{iid}/cut-plan` returns only sheets
  that contain ≥1 slot for the item (or its modules' parts). Slots
  whose `part_id` is null or belongs to *other* items in the project
  carry `is_foreign=true`. Slot label fallback order: `slot.label` →
  joined `parts.part_name` → `"slot {id}"`.
- Web routes:
  - **`/cut-floor?date=YYYY-MM-DD&project=`** — Machine team daily
    list. Date picker + back/forward arrows + project filter chip
    (defaults to "All projects"). `mutator` roles drag-reorder rows
    via HTML5 DnD. Each row: status pill + priority + plan name +
    assignee + Start / Mark done / Cancel.
  - **Item editor `/items/{id}?tab=board`** — `BoardTab.tsx` fetches
    `/api/items/{id}/cut-plan` and renders one SVG per sheet at
    800-px viewport, scaled to sheet dimensions. This-item slots fill
    `--h-accent` 60%; foreign slots fill `--h-line` 30%. Tooltip on
    hover. Empty state: "No CutPlan yet for this project."
  - Reached from the `Cut Floor` entry on the TabStrip secondary row
    (a SideBar link when #7c shipped; #9a moved it).
- Audit events: `cut_plan.{create,delete}`,
  `cut_schedule.{create,update,status_change,reorder,cancel}`. All
  routed through `apps/api/app/auth/audit.py::write_audit`.
- Seed (`make seed`) on ALF-001: 1 cut_plan "ALF-001 v1 nest", 1
  sheet (18-PB), **5 part_slots** (3 own + 2 foreign, for the Board-tab
  demo), and 2 cut_schedule rows (`running` today + `planned`
  tomorrow). Idempotent — `DELETE FROM cut_plan WHERE project_id =
  ALF-001` runs first.
- Out of scope **for #7c** (the optimiser it reserved
  `POST /projects/{pid}/optimise` for shipped later, in #9): CutPlan edit
  UI (v1 = create + delete + replace by creating a new plan),
  WebSocket schedule updates, `@dnd-kit/core`, mobile UI for
  `/cut-floor`, `cut_plan.is_current` flag (Board tab uses
  `MAX(id)`), CutSchedule export to PDF.

## Shop Floor Ops (sub-project #8)

> **Re-keyed by migration `0030` (B3).** `worker_assignment` and
> `stage_completion_log` now key on **`(cutlist_id, stage_key)`**, not the
> item — the production workflow belongs to the cutlist (Plan V1 Q412).
> `worker_assignment.item_id` is **gone**; `stage_completion_log.item_id`
> survives nullable as pre-`0030` provenance only. Completing a stage fans
> `item_stages.done_date` out to every linked item whose own order contains it
> (Q439 + Q562), and undo reverses the whole cutlist (Q446). Scope was the
> five production stages only when B3 shipped — **DEL and INST are still not
> assignable** (Q561) — but migration `0039` added **Packing** as a real 6th
> assignable stage (Q519); see *QC / Rework / Packing* further down. The
> notes below otherwise stand.

- Migration 0020 adds `app_user.is_shop_worker` (bool default false),
  `items.paint_after_assembly` (bool default false; when true the
  lifecycle order becomes DOWN → CNC → EDGED → MADE → PAINTED),
  `worker_assignment` (mutable assignment state with the partial
  unique index `uniq_active_assignment` on `(item_id, stage_key)
  WHERE status IN ('assigned','in_progress')`), and
  `stage_completion_log` (append-only history with `undone_at` soft-
  undo marker).
- New 10th IA module **`shop_floor`**. Foreman + Machine team both
  map to `editor` (`{read, write, comment}`); admin/manager get
  approve too; drafter `{read, comment}`; viewer / purchase_officer
  `{read}` only. Restrictions on who can override an in-progress
  assignment held by another worker are enforced in route handlers,
  not the matrix.
- Backend module `apps/api/app/shop_floor/` — `schemas.py`,
  `lifecycle.py` (pure helpers — `shop_floor_order`,
  `prior_stages`, `is_within_undo_window`), `queries.py`
  (workspace-isolated text() SQL, FOR UPDATE on mark-done +
  undo paths), `routes.py` mounting 10 endpoints:
  - `GET /projects/{pid}/shop-floor/board`
  - `GET /projects/{pid}/shop-floor/workers`
  - `GET /workers/{wid}/queue`
  - `GET /workers/{wid}/recent-completions`
  - `POST /projects/{pid}/items/{iid}/assignments`
  - `PATCH /assignments/{aid}` (reassign clears `started_at` and
    resets status to `assigned` per user decision)
  - `DELETE /assignments/{aid}` (soft-cancel)
  - `POST /assignments/{aid}/start` (idempotent)
  - `POST /assignments/{aid}/complete` (single transaction:
    `stage_completion_log` + `item_stages.done_date` +
    `worker_assignment.status='done'` + audit)
  - `POST /completions/{log_id}/undo` (worker <5 min via
    `is_within_undo_window`; supervisor any time)
- Status machine binding: `assigned → in_progress → done`, plus
  `assigned/in_progress → cancelled`. `done → in_progress` only via
  the undo path. `done → cancelled` is rejected at both DELETE and
  PATCH layers.
- Duplicate-active-assignment 409 surfaces the existing
  `assignment_id`, `worker_id`, `worker_name`, `status` so the UI
  can redirect to reassign instead of pleading retry (per user
  decision).
- Stage ordering enforced by `prior_stages_done()` reading
  `items.painting_req` AND `items.paint_after_assembly`. Mark-done
  for `CNC` before `DOWN` returns `409 STAGE_OUT_OF_ORDER` with the
  `missing` list. PAINTED is skipped from the order entirely when
  `painting_req = false`.
- Workspace isolation: every read/write joins `items.project_id ->
  projects.workspace_id`. Cross-workspace GETs and POSTs return 404.
- Worker-toggle endpoint at `PATCH /users/{uid}/shop-worker` (gated
  `("it_management", "write")` — admin-only). Audit event
  `it.worker_toggle`.
- Deactivating (`PATCH /users/{uid}` `is_active=false`) or un-flagging
  (`PATCH /users/{uid}/shop-worker` `is_shop_worker=false`) a worker who
  still holds `assigned`/`in_progress` assignments returns
  `409 HAS_ACTIVE_ASSIGNMENTS` (listing them) and changes nothing — reassign
  or cancel first (spec §15 Q3). `shop_floor.queries.active_assignments_for_worker`
  + `users.routes._guard_active_assignments`.
- Web routes:
  - **`/shop-floor?project=…`** — Foreman office board. Kanban
    DOWN | CNC | EDGED | PAINTED | MADE (**+ PACKING, a 6th column
    since migration `0039`** — see *QC / Rework / Packing* below).
    Per-card status pill + worker chip + reassign select + cancel
    button. Inline `AssignDialog`. 15-second polling.
  - **`/shop-floor/station/[worker_id]`** — kiosk display. Active
    card prominent (~70% viewport), big emerald Mark-done button on
    the in-progress card; the worker's own browser session sees the
    `UndoBannerStack` for completions in the last 5 minutes.
  - `/it` — admin-only `WorkerRosterPanel` listing every workspace
    user with a checkbox to toggle `is_shop_worker`. Optimistic
    update with revert on failure.
  - Reached from the `Shop Floor` entry on the TabStrip secondary row
    (a SideBar link when #8 shipped; #9a moved it).
- Audit hooks: `shop_floor.{assign|reassign|unassign|stage_start|
  stage_complete|stage_undo}` plus `shop_floor.assign_note_update`
  for note-only PATCH and `it.worker_toggle` for the admin roster
  panel.
- Seed (`make seed`) adds 4 shop workers to the staff roster and
  inserts **5 demo assignments** on ALF-001, one per item (one
  `in_progress`, one `done` with matching `stage_completion_log` and
  yesterday's `item_stages.done_date`, three `assigned`). The block asks
  for up to 6 (`LIMIT 6` items) but the demo project yields 5. Idempotent
  — wipes the ALF-001 shop-floor demo state before re-seeding.
- Out of scope (deferred): mobile-first responsive UI, real-time
  pub/sub (15-s poll instead), efficiency analytics dashboards,
  per-part painting tracking, `time_record` table for payroll,
  worker self-assignment, quality / rework loop, cross-project
  worker view, per-worker login (kiosk URL = pseudo-auth), PM
  "today's completions" widget on `/tracking`.

## Estimating (sub-project #9a)

> **Built without a spec or plan.** #9a shipped directly (commit `a7b8d3d`
> + follow-ups); the design record was backfilled afterwards as
> `docs/superpowers/plans/2026-05-26-estimating.md`, which explains *why*
> the schema and workflow read as they do. **This section stays the
> statement of current state.** #9 (CutPlan optimiser) is a *different*
> sub-project; it shipped after #9a, which is why estimating holds
> migration slots 0021–0023 and the optimiser's `grain_locked` landed
> as 0024.

> **Superseded by Plan V1 §I (migration `0038`).** The six-state
> `draft → sent → accepted/rejected/expired/withdrawn` workflow described
> below is **replaced**, not extended, by the 12-stage tender lifecycle —
> see *Tender Lifecycle + Financials* further down for the current state
> machine, Convert behaviour and endpoint list. The schema (`estimate`,
> `estimate_revision`, lines, snapshot columns), migrations 0021–0023, the
> `estimator` role and the RBAC/module points below all still stand
> unchanged; only the status enum, `_LEGAL_TRANSITIONS`, and the
> send/convert routes were rewritten. Kept here for the parts that are
> still accurate; don't read the "Revision workflow" or "Convert-to-Project"
> bullets below as current.

- New backend module `apps/api/app/estimating/` (`schemas.py`,
  `queries.py`, `routes.py`, `pdf.py` + `templates/quote.html`).
  Mounted at top-level paths from `main.py` (no path prefix — routes
  live at `/customers`, `/estimates`, `/revisions/{rid}/…`,
  `/lines/{lid}/…`, `/it/labour-rates`). All gated by
  `require_permission("estimating", action)` except `/it/labour-rates`
  (gated `("it_management", …)` — admin-only).
- **New 7th auth role `estimator`** (migration 0021 widens the
  `app_user.auth_role` CHECK). RBAC matrix (`apps/api/app/auth/permissions.py`):
  estimator gets `{read,write,approve,comment}` on `estimating`, plus
  read/comment across the other modules; `it_management` empty. All
  other roles get `estimating` read-only except drafter (`read,comment`).
  This is the first role added since drafter — the matrix now has
  **7 roles × 11 modules** (`estimating` is the 10th operational
  module, `it_management` the admin-only 11th).
- **New `estimating` IA module** in `_ALL_MODULES` (between
  `shop_floor` and `it_management`).
- Migrations:
  - **0021 `estimating_core`** — widens auth_role CHECK; creates
    `customer`, `estimate`, `estimate_revision`, `estimate_line`,
    `estimate_line_part` / `_hardware` / `_labour`,
    `workspace_labour_rate`; adds `projects.customer_id` +
    `projects.estimate_revision_id` (both nullable FKs, set on
    Convert). **Downgrade is a no-op** (irreversible; recover from
    0001–0020).
  - **0022 `estimate_expires_at`** — nullable `estimate_revision.expires_at`
    date (quote validity window).
  - **0023 `team_status`** — adds `app_user.work_status`
    (`IN|ON_SITE|SHOP|WFH|OFF`, nullable) + `location_label`. Backs the
    dashboard Team card, not estimating per se.
- **Data model.** `estimate` is the root (one per quoted job);
  `estimate_revision` is revisioned (`rev_no`, immutable once it leaves
  `draft`). Cost columns on lines/parts/hardware/labour are
  **snapshotted** (`*_snapshot`, `cost_extended` GENERATED) so a locked
  quote's numbers never drift when the live catalog changes; the live
  `material_id` ref is retained alongside for traceability. Partial
  unique index `uniq_estimate_draft` enforces at most one `draft`
  revision per estimate. `estimate_line_labour` snapshots the
  per-stage `workspace_labour_rate` on insert (UNIQUE on
  `(line_id, stage_key)`).
  - **Equipment hire is excluded** from `estimate_line_hardware`
    (`material_type IN ('HARDWARE','APPLIANCE')` only) — hire rows are
    project-scoped (`project_id` FK on the catalog row) and can't be
    referenced from a pre-project quote.
  - `estimate_line_part.material_type IN ('BOARD','CUSTOM','BENCHTOP')`.
- **Fixed later.** `create_line()` computed `SELECT COALESCE(MAX(seq), 0) + 1`
  against `estimate_line` and inserted without locking the parent revision —
  the `(revision_id, seq)` index (`0021`) is a plain index, not unique, so two
  concurrent `POST /revisions/{rid}/lines` calls on the same draft (a
  double-click, two tabs) could both read the same `MAX(seq)` and insert a
  duplicate. `create_line()` now calls the existing `lock_revision_for_update()`
  helper (already used by the status-transition and Convert paths) instead of
  the unlocked `_assert_draft()`, so a concurrent create on the same revision
  serializes instead of racing. No migration — `reorder_lines`/`patch_line`/
  `delete_line` never generate a new `seq`, so they weren't exposed. Pinned by
  `test_concurrent_create_line_serializes_instead_of_duplicating_seq`
  (`test_estimating_line_seq_race.py`), which reproduces the race with two
  real DB sessions on separate threads and confirms it fails against the
  pre-fix code (`[1, 1]` instead of `[1, 2]`).
- **Revision workflow (superseded — see *Tender Lifecycle + Financials*).**
  `_LEGAL_TRANSITIONS` in `queries.py` was the six-state
  `draft → sent|withdrawn`; `sent → accepted|rejected|expired|withdrawn`
  graph. Migration `0038` replaced it with the 12-stage lifecycle;
  `send` no longer exists as an action (folded into `advance`).
- **Convert-to-Project (superseded — see *Tender Lifecycle + Financials*).**
  `POST /revisions/{rid}/convert` still requires status `WON`
  (`409 BAD_STATUS` otherwise) and still rejects already-converted
  (`409 ALREADY_CONVERTED`) and archived-customer, but now also takes a
  body selecting which lines convert (Q490) and creates a
  `project_contract` row (Q491) alongside the project.
- **Endpoint count changed** — `/revisions/{rid}/send` was retired in
  favour of `/revisions/{rid}/advance`, and `/revisions/{rid}/handover-preview`
  was added; see *Tender Lifecycle + Financials* for the current list.
  Otherwise unchanged: Customers CRUD + archive; estimates list/detail/
  create/patch/revise; revision detail + patch + status transitions;
  line CRUD + reorder; per-line part / hardware / labour add/patch/delete;
  `GET /it/labour-rates` + `PATCH /it/labour-rates`;
  `GET /revisions/{rid}/quote.pdf` (WeasyPrint, `inline` with RFC 8187
  dual filename).
- Audit hooks: `customer.create` (+ patch/archive via queries),
  `estimate.{create|update|revise|line_add|line_edit|line_delete|
  line_reorder|part_add|part_edit|part_remove|hardware_add|hardware_edit|
  hardware_remove|labour_set|labour_clear|send|accept|reject|expire|
  withdraw|convert|print}`.
- Web routes:
  - `/estimating?subtab=active|archive&q=&customer=&status=` — list +
    `/estimating/[eid]` detail editor (`EstimatingClient` /
    `EstimateDetailClient`).
  - `/customers?q=&include_archived=` — customer registry
    (`/customers/[cid]` detail).
  - Both are new **secondary** TabStrip entries (see chrome changes
    below), not top-6 IA tabs.
- Seed (`make seed`): adds a 9th staff user
  (`kai.ngata@hartwood.test`, role `estimator`), 10 `workspace_labour_rate`
  rows (one per stage), 2 customers, and 3 demo `EST-2026-*` estimates.
  Idempotent — wipes `EST-2026-*` for the workspace before reinserting.
- Out of scope (deferred): ~~PO/supplier-order generation from a won quote~~
  **built, see *PO Generation from a Won Quote* below** (Convert still stops
  at project + contract creation — see *Tender Lifecycle + Financials* for
  what Convert gained), multi-currency, client
  e-signature / portal, estimate templates, per-line margin overrides
  beyond `unit_sell_override`, revision diff UI.

### Cross-cutting changes that shipped with #9a

These landed in the same batch (commits `a7b8d3d`, `620930e`,
`b910ab1`) and touch shared chrome — note them before editing those
surfaces:

- **`/home` → `/dashboard` rename.** `/home` now just
  `redirect("/dashboard")`. The real landing page is `/dashboard` (Team
  card + live workspace stats).
- **Public stats endpoint** `GET /public/stats` (`app/public/routes.py`,
  no auth) feeds the dashboard + the login page's stats block (no more
  hardcoded numbers).
- **Team-status feature.** `PATCH /me/status` (`work_status` +
  `location_label`, audit `user.status`) and
  `GET /workspace/team` (`team_router`, prefix `/workspace`) power the
  dashboard Team card.
- **TabStrip secondary row.** Beyond the fixed 6 top tabs, a secondary
  strip now carries `Catalog · Shop Floor · Cut Floor · Estimating ·
  Customers` (`apps/web/components/chrome/TabStrip.tsx`).
- **Design tokens expanded** to the full hi-fi palette
  (`ink2/3/4`, `surfaceAlt`, `accentSoft`, `info`) in `globals.css` —
  the previously-deferred richer palette from `legacy/` is now wired.
- **Tracking overhaul.** `TrackingClient` refactored into quick-filter
  chips + sub-tabs + search; new `ItemsTable`, `ItemDetailModal`,
  `ProjectDetailModal`, `StatusPopup`, `ProjectInfoBar`,
  `TrackingMetrics`. CUTLIST number links to `/items/[id]`; the ▶
  triangle opens `ItemDetailModal`. Status change accepts an optional
  note. The `/list` route is now wired (project switcher + search +
  the shared `ItemsTable`).

## CutPlan Optimiser (sub-project #9 + engine)

- Ships the wire contract + UI flow **and** a real nesting engine. The
  original naive shelf packer is kept as a selectable fallback / A/B
  baseline. Spec source: cabinet-vision design §8.1.
- Migration **0024 `grain_locked`** adds `grain_locked boolean NOT NULL
  DEFAULT false` to `board_materials` + `benchtop_materials`. Grain-locked
  parts are never rotated by the optimiser. (This is the migration the
  `2026-05-09` plan originally reserved as 0021 — renumbered after #9a
  consumed 0021–0023.)
- **`apps/api/app/cut_floor/optimiser.py`** — pure stdlib module (no DB, no
  Pydantic; unit-tested against deterministic inputs). Dataclasses
  `PackPart` (now carries a `uid` for multi-sheet tracking) / `PlacedSlot` /
  `Skip` / `PackResult` / `MultiPackResult`. Three packers:
  - `pack_naive` — shelf next-fit-decreasing (the original stub; baseline).
  - `pack_maxrects` — **MaxRects** nester. Places parts largest-first; runs
    three free-rect choice heuristics (Best-Short-Side-Fit,
    Best-Area-Fit, Bottom-Left) and keeps the best-yielding sheet. Splits
    free space against the part inflated by `kerf` so neighbours keep a saw
    gap; rotates non grain-locked parts. Robustly ≥ `pack_naive` on mixed
    parts, matches it on uniform grids.
  - `pack_sheets(parts, …, strategy, max_sheets)` — **multi-sheet** wrapper:
    overflow (`no_room`) parts roll onto a fresh sheet until placed or
    `max_sheets` is hit; `too_large` parts (bigger than the sheet) are never
    retried. Returns `MultiPackResult { sheets: [PackResult], skipped }`.
- **`POST /projects/{pid}/optimise`** (gated `("cut_floor","write")`) —
  pulls candidate parts (`candidate_parts_for_optimise`: parts → modules →
  items → project, with real dims, joined to their board material's
  `grain_locked`), expands each by `qty` (assigning a `uid`), calls
  `pack_sheets`, and returns `OptimiseOut { proposal: CutPlanIn, summary }`
  with **N** `CutSheetIn`. **Pure function: no DB writes, no audit, no
  commit.** The user reviews the proposal then forwards it to the existing
  `POST /projects/{pid}/cut-plans` (#7c), which owns persistence + the
  `cut_plan.create` audit. `OptimiseIn` gains `strategy` (`maxrects` default
  | `naive`) + `max_sheets` (default 20); `OptimiseSummary` gains
  `sheet_utilization[]` (per sheet) and `utilization_pct` is the mean across
  sheets used. Empty / all-oversized input → zero sheets in the proposal.
- Sheet stock is a **per-optimisation override** — `sheet_len_mm`,
  `sheet_wid_mm`, `kerf_mm` come in the request body (no
  `board_inventory` table yet).
- `grain_locked` round-trips through the catalog: added to the `board` +
  `benchtop` REGISTRY select/insert columns in
  `apps/api/app/catalog/queries.py` and to `PatchBoardIn` / `PatchBenchtopIn`.
- Web:
  - Shared **`SheetCanvas.tsx`** (`cut-floor/_components/`) — the SVG
    sheet renderer extracted from `BoardTab.tsx`; both surfaces import it.
    Known sheet dims pass `extent`; the Board tab infers extent from slots.
  - **`OptimiseDialog.tsx`** — two-phase: a form (project · plan name ·
    material SKU · sheet dims · kerf · **Algorithm** selector) → a preview
    (summary + one `SheetCanvas` **per sheet** + skipped-parts list) →
    **Save as plan** forwards the multi-sheet proposal to `createCutPlan`.
    Opened by an **Optimise…** button on the `/cut-floor` header (mutator
    roles only).
  - `/catalog?tab=board|benchtop` grid gains a **Grain** checkbox column
    that PATCHes `grain_locked`.
- Seed (`make seed`): grain-locks the walnut veneer demo board
  (`BM-103`) on ALF-001. Idempotent (an `UPDATE` after the DO-NOTHING
  insert).
- Dialog UX (shipped later): material-SKU **typeahead** (a `datalist` fed by
  `listCatalog`; the field stays free-text) and an **item picker** — a checkbox
  list of the project's items wired to `include_only_item_ids`. An empty
  `include_only_item_ids` means *no items*, not *no filter*
  (`candidate_parts_for_optimise` short-circuits); the dialog also disables
  **Optimise** when nothing is selected.
- Out of scope (still deferred): non-rectangular parts, grain-direction SVG
  visualisation, saving draft proposals, stock **consumption** (see below —
  `/optimise` reads stock but never reserves or decrements it).

## Board inventory — sheet stock (migration 0025)

- Migration **0025 `board_inventory`** — one row per (workspace, board
  material, sheet size): `len_mm`, `wid_mm`, `qty_on_hand`, `location`,
  `notes`. UNIQUE on `(workspace_id, material_id, len_mm, wid_mm)`, so
  adjusting stock is an UPDATE of `qty_on_hand`, not a second row. Indexes on
  `(workspace_id, material_id)` plus a partial one `WHERE qty_on_hand > 0`
  for the optimiser's hot path.
- **`/optimise` reads stock; it never writes it.** The pure-function invariant
  from #9 holds — no reserving, no decrementing. Consumption on cut-plan
  completion is a deliberate later decision, not an oversight.
- `OptimiseIn.sheet_len_mm` / `sheet_wid_mm` are now **optional**:
  - omitted → the server picks the **largest in-stock sheet** for
    `material_sku` (by area, tie-broken by quantity) and sets
    `sheet_dims_from_stock=true`;
  - omitted with no stock on hand → `422 {code: "NO_SHEET_SIZE"}`;
  - supplied → explicit dims win, so ad-hoc stock the catalog doesn't know
    about can still be nested against.
- `OptimiseSummary` gains `sheet_len_mm`, `sheet_wid_mm`,
  `sheet_dims_from_stock`, `sheets_available`, `sheet_shortfall`.
  **`sheets_available` is `null` when no stock is recorded at that size** —
  that means *unknown*, not zero, so the UI must not claim a shortfall
  against it.
- Routes (`apps/api/app/cut_floor/`, queries in `inventory_queries.py`),
  reads gated `("cut_floor","read")`, writes `("cut_floor","write")`:
  - `GET /board-inventory?material_sku=&in_stock_only=`
  - `POST /board-inventory` — **upsert** by (material, size); posting the same
    size again sets the quantity instead of duplicating. Omitted `location` /
    `notes` are preserved, not clobbered. `404 UNKNOWN_MATERIAL` for an
    unknown SKU.
  - `PATCH /board-inventory/{id}` (qty / location / notes),
    `DELETE /board-inventory/{id}`.
- Audit: `board_inventory.{upsert|update|delete}`.
- Web: a **Sheet Stock** tab on `/catalog` (`StockPanel`) lists stock by
  material + size with inline qty/location editing, remove, and a
  set-stock form (the same upsert, so re-entering a size updates it).
  `OptimiseDialog` defaults to **Use sheet size from stock** (the dim
  inputs grey out; kerf stays editable since it's a saw property, not a stock
  one), lists what's on hand under the SKU field, and shows a shortfall
  banner when a nest needs more sheets than exist. Saving is still allowed —
  a short nest is a purchasing signal, not an error.
- Seed (`make seed`): 6 stock rows across 5 boards on the demo workspace —
  BM-101 deliberately stocked in **two** sizes (2440×1220 and 3600×1800) to
  exercise the largest-sheet pick, and BM-104 at **zero** to exercise the
  out-of-stock path. Idempotent via the same upsert.

## Shop Drawings register redesign (migration `0044`) — shipped

> Chosen by the user: "use https://tgsdr.com/ as reference for the shop drawing",
> then screenshots of the customer's own **Tg Register** (the site itself is
> blocked by the environment's egress proxy, so the screenshots are the only
> reference seen). The request was under-specified, so the user was asked before
> any code was written; the answers below are **settled decisions**, not
> assumptions. It supersedes the *web* half of *Shop Drawings + File-Upload
> Subsystem (#5a)* (the card grid + drawer); that section's backend, workflow and
> RBAC still stand. No spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **Layout + new fields, not a new workflow.** The four revision statuses
     (`draft / pending / approved / rejected`), the not-uploader rule and the
     in-flight index are untouched. Tg's own statuses are shown as **queues
     derived from them** (below), never stored.
  2. **Keep our light design tokens.** Nothing was added to `globals.css`; the
     Tg screenshots are dark navy and that was declined. Existing tokens only
     (`h-good/warn/bad/info/accent-soft`, with `/15` tints for chips).
  3. **Four screens:** register table, full-screen viewer, details panel, left
     queue rail.
  4. **Replaces `/shop-dwgs` in place.** Old links still land somewhere sensible:
     `?subtab=current|in_review|archive` map to the Completed / Internal Review /
     Archive queues (`page.tsx::LEGACY_SUBTAB`).
  5. **No link to Joinery Items.** `joinery_id` is free text; drawings are still
     project-scoped and unlinked to items (the gap Q497 waits on).
- **Migration `0044`** — additive columns on `shop_drawing`: `drawing_no`,
  `type` (`IFA | IFC`, default `IFA`), `level`, `joinery_id`, `zone`, `room_no`,
  `assigned_to` (FK `app_user`), `due_date`, `submitted_at`; `UNIQUE (project_id,
  drawing_no)`. **`drawing_no` is nullable on purpose**: the seed and ~10 test
  fixtures INSERT drawings with raw SQL, and the API allocates the number on
  create. It reads `{project_code}-{seq:03d}` (`COLES-001`) from
  `workspace_counter` name `sd:{project_id}` — the first real caller of
  `counters.next_value` — never `MAX+1`. Existing rows are numbered per project in
  `drawing_id` order and the counters advanced past them. **`type` allows only
  IFA / IFC** (the two in the screenshots); a third value needs a migration.
- **Queues are derived, not stored** (`shop_drawings/schemas.py::Queue`): the
  drawing's **latest revision** decides — `being_drawn` (draft),
  `internal_review` (pending), `update_required` (rejected), `completed`
  (approved) — and `awaiting_submission` (approved, no `submitted_at`),
  `submitted` (`submitted_at` set) and `archive` (`archived_at` set) are filters
  over those. They overlap by design (a submitted drawing is also completed), so
  the per-queue counts do **not** sum to the total. `GET
  /projects/{pid}/shop-drawings` gained `queue=`, `assigned_to=` and `queues`
  (project-wide counts, unaffected by the room / search filters);
  `?subtab=` still works and `queue` overrides it. `q` now also matches
  `drawing_no` and `joinery_id`. Each card carries its `queue` and a
  `comment_count` (live comments on any of its revisions).
- **New endpoint** `GET /shop-drawings/{did}/history` (`shop_dwgs:read`) — the
  drawing's `shop_drawing.*` audit rows, newest first. The details panel's
  **Status History** tab shows the create / revision / archive events and
  **Audit Log** shows all of them, including field edits.
- **Editing** stays the existing rule — creator or manager / admin
  (`PATCH /shop-drawings/{id}`, 403 otherwise) — and now covers every register
  field plus `submitted_at`. `assigned_to` is **validated against the caller's
  workspace** (422; an unchecked FK would leak a foreign user's name through the
  `full_name` join — the `cut_schedule.assigned_to` lesson), an explicit `null`
  for `title` / `type` is a 422 (both NOT NULL), and audit payload dates are
  ISO strings. The web hides the inputs for anyone else; the API decides.
- **Web** — `shop-dwgs/_components/`: `RegisterTable` (sortable, blanks last
  either way, client-side paging at 25, an "Overdue" tag when `due_date` is past
  and the drawing is not completed / archived), `QueueRail` (progress donut, "My
  drawings" = `assigned_to = me`, one entry per queue), `DetailsPanel` (docked to
  the right of the table; commit-on-blur fields that resync and skip unchanged
  values; Revisions / Notes / Attachments / Status History / Audit Log tabs; the
  revision comment thread keeps `data-testid="revision-comments"` and its
  collapsed-by-default toggle), `DrawingViewer` (full screen, `?viewer=1`; zoom /
  Fit / download, a versions list, the revision's comment thread as
  *Communication*, drawing info and the review actions). Removed as orphaned:
  `DrawingCard`, `DrawingDrawer`, `SubtabStrip`, `BlueprintPlaceholder`,
  `VersionChip`, `RevisionHistoryStrip`. **URL state**: `project`, `queue`,
  `mine`, `room`, `q`, `drawing`, `rev`, `viewer`, `comments`. The notification
  link (`…&drawing=&rev=&comments=1`) still opens the details panel with the
  thread expanded.
- **Viewer page thumbnails** (`ThumbnailStrip.tsx`, added after the redesign
  merged; the user asked for it once its gap had been named). **pdf.js renders the
  thumbnails only** (`pdfjs-dist`, dynamic import, so it never runs in SSR); the
  drawing itself is still the browser's own PDF viewer, which a thumbnail click
  re-points at `#page=N` (the iframe remounts). Consequences: the highlighted page
  is the **last one clicked**, not the page scrolled to inside the embedded viewer
  (the app cannot see that); Chrome's own thumbnail panel is hidden with
  `&navpanes=0` so two strips don't sit side by side; PDFs only (images have no
  pages); shown from `lg` up. **It uses pdf.js's `legacy/` build on purpose**: the
  modern build calls `Map.getOrInsertComputed`, which most browsers in use
  (including the Chromium here) lack, and it then *silently draws blank
  thumbnails* — the count and paging still work, which is what made it easy to
  miss. `useSystemFonts` is on so a PDF naming a standard font without embedding it
  still draws its text. A page that fails to render leaves a blank thumbnail and
  logs `thumbnail render failed`; an unreadable file hides the strip. Verified by
  `shop_drawings.spec.ts` with a generated 3-page PDF: the count, three
  thumbnails, **non-white pixels in each canvas** (the check that caught the blank
  render), and `#page=3` after a click.
- **Deliberately not built, and why.** *Annotate* and *Coordinator references* (the screenshots' viewer) have nothing
  behind them here. *Bulk row selection*. The **Attachments tab lists each
  revision's file**: a drawing has no other attachments. *"Upload drawing" is now
  hidden without `shop_dwgs:write`* (it was shown to everyone and 403'd).
- **Seed.** ALF-001's six drawings get numbers `ALF-001-001…006` (counter reset
  with the drawings on re-run), a type, level, Joinery ID, an assignee and
  due / submitted dates **relative to today** so the overdue flag is right
  whenever the seed runs: *Kitchen island* is an overdue draft; *Bathroom vanity*
  is approved and submitted; *Hallway storage* is approved and awaiting
  submission.
- **Search** — a drawing's `drawing_no` and `joinery_id` are now search codes
  (`app/search/documents.py`).
- **Tests.** `test_shop_drawings_register.py` (9): sequential numbering,
  round-trip, bad `type` 422, foreign `assigned_to` 422 on create *and* patch
  (nothing written), patch + audit + null-title 422, every queue's membership and
  the counts, search / assigned filters, comment count, history 404. The existing
  47 shop-drawing / search-document tests pass unchanged.
  `tests/e2e/shop_drawings.spec.ts` (+3): the register columns, queue filter
  (URL + reload), overdue flag and sort; details panel → viewer → zoom → back; a
  viewer sees the details read-only. Both existing specs were kept and only the
  drawer's `#SD-` click became a register-row click
  (`comments_module_revision.spec.ts`). The new e2e tests are read-only against
  the seed, so they re-run without re-seeding.
- **Known gaps, recorded.**
  - The queue counts are computed per project; there is no cross-project
    "My Drawings" number (the count next to the rail's toggle is on/off, not a
    total).
  - Sorting and paging are client-side over the whole project's list, which is
    fine for hundreds of drawings and is the thing to revisit at thousands.
  - Rev shows the revision **number** (`v3`), not Tg's letters (`A`, `B`).
  - `type`, `level`, `zone` and `room_no` are not searchable filters yet, only
    `q` over title / number / Joinery ID.
- **Out of scope (deferred):** linking a drawing to a Joinery Item; Tg's own
  status names as stored states; a dark theme; rendering the drawing itself with
  pdf.js (only the thumbnails use it).

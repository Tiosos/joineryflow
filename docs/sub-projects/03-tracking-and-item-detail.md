# Tracking And Item Detail

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## Tracking 2.0 (migration `0035`) — shipped

> Design: `docs/archive/specs/2026-05-27-tracking-2-0-design.md`; plan:
> `docs/archive/plans/2026-05-27-tracking-2-0.md`. Authored 2026-05-27 on
> a separate branch, merged into `main` 2026-09-24 (commit `8ac99d5`) —
> *after* #12, out of migration-number order relative to its own title.
> **Numbering collision, noted once here for both this and the next
> section:** both docs call themselves sub-projects "#10" and "(#11)"; those
> numbers were free when written in May but are now held by Cutlist +
> Orderbook and Global Search, which were built and merged first. Go by
> migration number or date, never by the label inside either doc.

- **Migration `0035`** adds `workspace_counter(workspace_id, name,
  next_value)` — an atomic per-workspace counter, `apps/api/app/counters/
  next_value()` — plus six `items` columns: `jid_code`, `jid_color` (hex,
  CHECKed), `var_boq` (`BOQ`/`VAR`, default `BOQ`), `contractor_id` (FK →
  `app_user`, workspace-validated on write), `total_amount`,
  `site_measure_notes`.
- **Closes the legacy-parity gap on `/tracking`.** The grid gained JID code +
  colour swatch, a VAR/BOQ pill, Contractor, Total $, and exposure of
  columns that already existed on `items` but weren't in the API response
  (`floor_plan`, `rls`, `joiery_details`, `painting_req`,
  `solid_surface_req`, `cutlist_printed`, `group_id`, `item_code`,
  `assembler`, `lister`). Stage cells switched from checkmark to
  `done_date` (`DD.MM.YY`).
- **Subtabs** (`ItemsTable.tsx`'s `SUB_TABS`): `DATE · TO BE ORDERED · iTIME
  · HARDWARE · SITE MEASURE · INVOICE · QC · O/BOOK`. DATE, TO BE ORDERED
  (a filter — `availability.blocked > 0`, not a separate table), HARDWARE,
  SITE MEASURE and O/BOOK render real data; `iTIME`, `INVOICE` and `QC`
  stay `—` placeholders pending a future invoicing/variations sub-project
  neither doc built.
- **Bulk status.** `POST /items/bulk-status` (`tracking:write`) applies one
  status + one required note to up to 500 items in a single transaction;
  missing or cross-workspace ids come back in the response instead of
  404ing the whole call. The single-item `PATCH /items/{id}/status` was
  tightened the same way — `note` is now required, not an optional
  empty-string fallback.
- **`workspace_counter` has no caller yet, deliberately.** Its own design
  doc says it's seeded here ahead of a future PO/invoice/JID-numbering
  consumer; nothing in this tree calls `next_value()` outside its own unit
  tests (`test_counter.py`). Not a gap — don't invent a caller for it.
- **RBAC — no matrix change.** New fields ride the existing
  `require_drafter()` + `tracking:write` combo in `items/routes.py`;
  `contractor_id` writes are rejected (422) if the user isn't in the
  caller's own workspace.
- **Seed.** `make seed` gives every ALF-001 item a `jid_code`/`jid_color`
  pair, marks one item `VAR`, assigns `contractor_id` on two items, sets
  `total_amount` on every item, a `site_measure_notes` on the SS-Bench
  item, and one `workspace_counter` row.
- Backend, frontend and seed all shipped; covered by
  `test_tracking_bulk_status.py` plus extensions to `test_items_routes.py`.
- **Fixed after the merge:** `ItemOut` declared the six new fields but
  `get_item_detail` never selected them, so `GET` and `PATCH /items/{id}`
  always answered `jid_code: null, var_boq: "BOQ"` (etc.) whatever the row
  held — the Tracking grid, which reads through `list_items_for_project`,
  was right all along. Pinned by
  `test_get_item_returns_tracking_2_0_fields`.

## Item & Project Detail 2.0 (migration `0036`) — shipped

> Design: `docs/archive/specs/2026-05-27-item-project-detail-2-0-design.md`;
> plan: `docs/archive/plans/2026-05-27-item-project-detail-2-0.md`. Same
> authoring-vs-merge-order caveat as Tracking 2.0 above.

- **Migration `0036`** adds `projects.closed_at`/`closed_by`;
  `project_contact` (`kind IN (office, site)`); `project_lift_access` (one
  row per project); `item_query` (Q&A per item); `item_document` (an open
  document register beyond the four named attachment slots); widens
  `item_attachment_kind_check` to add `sketchup`/`cabvision` (`cv_drawing`
  stays; the migration's comment calls it a "legacy synonym", but the code
  treats it as its own slot — see below); `project_labour_hours_view` (returns zero —
  a future labour-hours integration populates it).
- **Backend shipped:** `ProjectOut` now surfaces FileMaker-era `projects`
  columns that already existed but weren't exposed (`builder`,
  `classification`, `site_street/suburb/postcode/state`,
  `tg_project_manager`, `tg_coordinator`) plus the new `closed_at`/
  `closed_by`; `POST /projects/{id}/close-out` (admin/manager,
  `409 ALREADY_CLOSED`) — **the only way to close** (user, 2026-09-25):
  `PATCH {status: "Closed"}` is 422, so `closed_at` / `closed_by` are always
  stamped, and PATCHing `status` to `Current` / `Hold` **re-opens**, clearing
  both (the design doc's §9 rule, which the merged code had not implemented); `project_contacts/` (POST/GET/PATCH/DELETE,
  `tracking:{read,write}`); `project_lift_access/` (GET/PUT/DELETE, one row
  per project); `item_queries/` (ask on `list:read`, answer/edit-answer on
  `list:write`, second answer without `allow_overwrite` returns 409). **The
  last three routers were built in the same merge but not registered in
  `main.py`** — `apps/api/app/{item_queries,project_contacts,
  project_lift_access}/routes.py` existed with complete queries/schemas
  and zero mount, so all 11 endpoints were unreachable until a follow-up
  fix (`fix(api): mount item_queries, project_contacts,
  project_lift_access routers`). They are now live and were verified
  end-to-end against a migrated database.
- **Document Register backend** (`item_documents/`, built after the merge):
  `GET /items/{iid}/documents` (`list:read`), `POST /items/{iid}/documents`,
  `PATCH /documents/{did}` (label / sort_order; `label: null` clears it,
  `sort_order: null` is 422) and `DELETE /documents/{did}` (all
  `list:write`). Unbinding deletes the register row only — the `file_blob`
  stays, as everywhere else (no orphan GC). Audit
  `item.document.{bind,update,unbind}`. Three choices made while building,
  each where the design doc was silent or a sibling module disagreed:
  - **`list:write` alone gates writes, so editors can bind.** The design
    doc says `list:write`; `item_attachments` adds `require_drafter()` on
    top. The doc for *this* feature wins; the sibling `item_queries` (same
    doc) also uses `list:write` alone.
  - **Joinery Items only.** A related part gets 404, the same rule the
    named attachment slots follow. The design doc predates related parts.
    Widening later is additive; narrowing would orphan rows.
  - **Writes `item_edit_log` as well as `audit_log`**, per the PM Workbench
    invariant (`_document_bind` / `_document_unbind`, and
    `document.{id}.{field}` per changed field). **Fixed later:**
    `item_attachments` and `item_queries` used to write audit only; both now
    write `item_edit_log` too (`attachment.{kind}` on bind/clear;
    `_query_create` on ask, `query.{id}.answer` on answer/edit-answer),
    pinned by `test_bind_writes_item_edit_log` / `test_clear_writes_item_edit_log`
    and `test_ask_answer_edit_round_trip`'s edit-log assertion.

  A bound blob must be PDF, PNG or JPEG (415 otherwise); `POST /files`
  already only stores those three, so the check guards the register if the
  upload allowlist ever widens. Covered by `test_item_documents.py` (10
  tests).
- **Item reference fields are writable** (built after the merge):
  `PATCH /items/{id}` accepts `floor_plan`, `rls`, `joiery_details`
  (`varchar(64)` — longer is 422) and `cutlist_printed`, through the usual
  `_PATCH_FIELD_MAP` path, so they get one edit-log row per field and go
  through the Controlled Lock like every other field. `ItemOut` (the
  `GET` / `PATCH /items/{id}` payload) now returns them.
- **Attachment slots are five, purely additive** (built after the merge;
  **decided by the user**, 2026-09-25). The design doc called `cv_drawing` a
  "legacy synonym" without saying of what; the answer is that it is **not a
  synonym in the code**: `cv_drawing` ("CV Production Drawing") keeps its own
  slot and its existing rows, and `sketchup` / `cabvision` are two further,
  independent slots. `item_attachments/` now offers
  `cv_drawing · sketchup · cabvision · floor_plan · site_measure` and the
  bundle always carries all five.
  **Each slot takes one format** (user, 2026-09-25): `sketchup` a `.skp`,
  `cabvision` a `.cvj`, the other three a PDF — anything else is 415
  (`item_attachments.queries.KIND_MIME`).
  **Uploading them** (`files/validators.py`, also the user's call): the
  "signature *and* extension must agree" rule still holds. `.skp` is
  `FF FE FF 0E` (SketchUp 2021+) or the OLE compound-file signature (older
  SketchUp); `.cvj` is OLE. OLE is shared by both — and by `.doc`/`.xls`/`.msi`
  — so for OLE the extension picks between `.skp` and `.cvj` and any other
  name is refused. Stored mimes are `application/vnd.sketchup.skp` and
  `application/x-cabinet-vision-job`. **The 25 MB cap is unchanged for every
  type** — a larger SketchUp model gets 413; the user chose that over a
  per-type cap. The signatures come from published format notes, not from a
  customer file: verify against a real `.skp` / `.cvj` when one is available.
  Widening `/files` meant adding a mime check wherever a blob is bound
  without one: shop drawings (422) and the lift-access sketch (415) keep
  PDF / PNG / JPEG; samples (PNG / JPEG) and the Document Register
  (PDF / PNG / JPEG) already had their own.
  **The Combined PDF is unchanged** — still `cv_drawing`, `floor_plan`,
  `site_measure` only (also the user's call; pinned by
  `test_print_combined_ignores_sketchup_and_cabvision`). Do not "fix" this
  into a rename or an alias. The web `AttachmentsTab` still shows only the
  three Combined slots; `lib/print.ts` counts only those three so its
  "N of 3" label can't overflow when the new slots are bound via the API.
- **Frontend shipped** (plan tasks T08–T12, `docs/archive/plans/
  2026-05-27-item-project-detail-2-0.md`; each task's `→` note there records
  what was built and how it was verified):
  - `EditorTabs.tsx` now carries 8 tabs: `cutlist · hardware · board · take
    · attachments · actions · query · log`. New **Actions** tab (Set status
    — reuses the existing `StatusPopup`; Mark REQ done today; Jump to
    Orderbook) and **Query** tab (ask/answer, `list:write` — `{drafter,
    manager, admin, editor}`, one role wider than `AttachmentsTab`'s writer
    set since `item_queries` doesn't add `require_drafter()`).
  - **Cutlist Printed and the three reference fields (Floor Plan / RLS /
    Joinery Details) live in `ItemMetadataPanel`'s existing `FIELDS` array**,
    not a separate header-chip row or Refs panel — Painting Req / Solid
    Surface Req were already there with the identical pattern. A deliberate
    simplification versus the design sketch.
  - **`AttachmentsTab` widened to 5 slots** (`sketchup` / `cabvision` cards
    now render; `AttachmentSlotCard`'s file-picker `accept` is a per-kind
    map, not hardcoded `.pdf`), with a small "Combined PDF" badge on the 3
    slots Combined actually uses. `lib/attachments-types.ts` gained
    `COMBINED_PDF_KINDS` distinct from the now-5-wide `ATTACHMENT_KINDS`, so
    `print.ts`'s "N of 3" copy stays correct.
  - **New page `/projects/[id]`** — header strip (status pill, builder,
    classification, install/value, Close-out button) + 3-column layout
    (Details / Contacts / Lift & Access) + a Labour Hours card. **RBAC is
    split three ways, not one `canEdit`**: Details/close-out gate on the
    manual `manager`/`admin` check in `projects/routes.py` (not a
    `require_permission` row); Contacts/Lift-access gate on `tracking:write`
    (`{editor, drafter, manager, admin}`, one role wider). Status stays a
    **read-only pill** — no Current/Hold reopen control was added, even
    though the backend already supports it via a plain PATCH, because
    nothing in scope asked for that control on this page. `/projects` (the
    list page) gained a "Details →" link per row, and the Tracking modal
    gained "Open full project page →" in its footer.
  - `pm-types.ts` and `attachments-types.ts` had drifted from the Python
    schemas before this work started (fields the API had served since
    `0035`/`0036` were simply missing from the TS types) — resynced as a
    prerequisite.
- **Seed data shipped.** `seed/hartwood_joinery.py` sets ALF-001's `builder`
  / `classification` / site address / TG team via the real
  `patch_project()` query function (not raw SQL), and adds 4 contacts (2
  office + 2 site), lift access notes + a sketch, 2 `item_query` rows on the
  first joinery item (1 open, 1 answered), and 2 `item_document` rows —
  each through the same query functions the API uses, so seeded rows carry
  real `audit_log` / `item_edit_log` entries.
- **e2e coverage:** new `tests/e2e/item_project_detail.spec.ts` (3 tests) —
  the item editor's Query/Actions/Attachments tabs, the project page from
  both entry points, and close-out's RBAC gate. Deliberately checks that
  close-out is *invisible* to a drafter rather than actually performing a
  close-out — doing so would durably close ALF-001 for every other spec
  sharing one `make e2e` run.
- **RBAC — no matrix change**, per its design doc: `project_contact`/
  `project_lift_access` reuse `tracking:{read,write}`; `item_query` reuses
  `list:{read,write}`; close-out is admin/manager only.
- **Tests:** `test_project_enrichment.py` (enriched `ProjectOut`, close-out,
  re-open), `test_project_contacts.py`, `test_project_lift_access.py`,
  `test_item_queries.py`, `test_item_documents.py`, plus the attachment,
  upload and item-route files extended above, plus the new e2e spec.
- **Fixed later.** `PartsGrid.tsx` (Cutlist tab) left a stray whitespace text
  node as a `<tr>` child (a `<th /> {/* comment */}` pattern — the space
  before the comment was a real text child), which React logged as a
  hydration warning on every item editor load. Predated this sub-project
  entirely; fixed by dropping the space before each trailing comment.

## Document Register web UI (no migration, no API change) — shipped

> Chosen by the user ("go with the next recommendation tasks"): the gap *Lock checks on
> attachments and the document register* and *Item & Project Detail 2.0* both recorded as "the
> register has no web UI". Two things were open, so the user was asked before any code was written;
> the answers are **settled decisions**, not assumptions. Web only — `item_documents/` is unchanged.

- **Settled decisions (user).**
  1. **Placement: a "Document register" section on the item editor's Attachments tab**, below the five
     named slots — not a new tab, not the Tracking modal. `ItemDetailModal`'s "No documents attached for
     v1." placeholder is therefore **still there and still untrue**; it was not touched (not chosen).
  2. **Write controls follow the API: `list:write` — drafter, manager, admin and editor.** That is one
     role wider than the attachment slots on the same tab (drafter / manager / admin), so the tab now
     holds two writer sets (`WRITER_ROLES`, `REGISTER_WRITER_ROLES` in `AttachmentsTab.tsx`). The web
     mirrors the role set; the API decides.
- **Web.** `DocumentRegister.tsx` (`items/[id]/_components/`) + `lib/item-documents-fetch.ts` (errors carry
  `status` / `body`, as `attachments-fetch.ts` does, so `lockFromError` can word a 409). One row per
  document: label (commit-on-blur / Enter, resyncs to the server's value and **skips an unchanged blur** so a
  tab-through writes no audit row; a refused save puts the server's label back), filename · size · uploader ·
  date, **Open**, **↑ / ↓**, **Remove** (confirm). **Add document** uploads through `/files` then binds
  (PDF / PNG / JPEG picker hint; the API's 415 is the gate) and **appends** after the highest `sort_order`.
  - **Reorder renumbers the whole list.** New documents default to `sort_order = 0`, so ties are the normal
    case and swapping two values would do nothing. A move renumbers `0..n-1` and PATCHes only the rows whose
    number changed — up to N sequential PATCHes, each an `item.document.update` audit row and each checking
    the lock. Not atomic: a failure part-way leaves a partly renumbered list (the list is re-fetched, so the
    screen shows the truth).
  - **One lock notice for the tab.** `AttachmentsTab` now decides the lock reason for either writer set and
    shows a single `attachments-locked` notice, so an **editor** (register writer, not slot writer) sees the
    reason too; the slot cards and the register each get the reason only when their own writer set applies.
    Same rule as everywhere (`moduleLockReason`: Hard + Approval + Controlled), so **relabelling and
    reordering on an APPROVED item are disabled**, matching the API. Controls are disabled with the reason as
    `title`; a `409` from a stale page shows the server's reason. The reason wording still says "cutlist,
    hardware or attachments" — it does not name the register.
  - Read-only roles get the list and **Open**, no inputs, no buttons. The register lists Joinery Items only,
    like the API (a related part's editor never reaches this tab).
- **Tests.** `tests/e2e/document_register.spec.ts` (5), run against a live migrated, seeded stack and
  re-run six-plus times: a drafter adds, relabels, reorders and removes (and an unchanged blur writes
  nothing); an editor can add while the slot **Upload / Replace** buttons are absent, a viewer only reads;
  a Hard Lock disables every control for a manager with the reason; another user's Controlled Lock disables
  an editor's and shows them the notice; a stale page shows the owner's name for a refused relabel / remove /
  add and puts the label back. **All five fail without the `AttachmentsTab` wiring.** Each test leaves the
  item as seeded — including every seeded document's `sort_order`, which a reorder would otherwise leave
  renumbered. `attachments_locks.spec.ts` and `item_project_detail.spec.ts` still pass. No backend test was
  needed or added: the routes are unchanged and already covered by `test_item_documents.py` and
  `test_attachments_documents_locks.py`.
- **Found while testing — a test bug that destroyed seed data.** The first draft removed `rows.last()` right
  after an upload. The page still showed a row the spec had just deleted through the API, so the row count
  matched instantly and the click landed on a stale row — the seeded second document. The spec now reloads
  first and targets the new row by filename. Worth remembering: a count assertion is satisfied by stale rows.
- **Known flake, not the feature.** About one full-spec run in ten failed with `apiRequestContext.post: read
  ECONNRESET` on the Hard Lock test's `POST /api/items/{id}/hard-lock` through `next dev`'s proxy; the same
  call passes on retry. `attachments_locks.spec.ts` makes the same call and is exposed to it too.
- **Known gaps, recorded.**
  - ~~`ItemDetailModal` (Tracking) still shows the "No documents attached for v1." placeholder.~~ **Closed —
    see *Tracking modal shows the register and the SketchUp / CabVision slots* below.**
  - Labels only — a register document has no other metadata, and a rename cannot be undone except by typing
    the old one back.
  - A refused bind leaves an unreferenced `file_blob` (as for attachments; `POST /files` is not gated).
  - The reorder controls are per-row buttons, not drag-and-drop.
- **Out of scope (deferred):** ~~register UI outside the item editor (the Tracking modal)~~ (**built, see below**); drag-and-drop;
  bulk upload; document categories or types.

## Tracking modal shows the register and the SketchUp / CabVision slots (no migration, no API change) — shipped

> Chosen by the user ("Go with option 1", from the list of candidates after the Document Register UI).
> Two things were open, so the user was asked before any code was written; both answers are **settled
> decisions**. Web only.

- **Settled decisions (user).**
  1. **Read-only.** The modal lists the register's documents with an **Open** link each and a
     "Manage on Attachments tab →" link to `/items/{id}?tab=attachments`, where editing (and its lock and
     writer-role rules) already lives. No inputs and no buttons in the modal's register.
  2. **Fill in the SketchUp / CabVision rows too** — the user chose this over leaving them as recorded-stale.
     They had been hard-coded to a dash since `0036` made both slots real.
- **Web — `tracking/_components/ItemDetailModal.tsx` (only file changed).** `ItemFiles` fetches
  `getAttachments` and `listDocuments` (the existing helpers) when the modal's item changes. Both reads are
  `list:read`, the gate `GET /items/{id}` already needs, so no role sees a new error. **Only the newest request may
  write** (Previous / Next changes the item mid-flight). **A failed read says so** ("Couldn't load the document
  register." / "Couldn't load" in the slot row) rather than reading as "nothing attached"; an empty register says
  "No documents in the register."; a slot shows its filename and **Open**, or a dash.
- **A related part never reaches this code.** Tracking gives one no ▶ button and `GET /items/{id}` answers 404 for it
  (Q559), so the modal errors before rendering; an earlier draft had a related-part branch and it was removed as
  unreachable rather than left untested.
- **Tests.** `tests/e2e/tracking_modal_files.spec.ts` (4), run three times back to back against a live migrated,
  seeded stack: the modal lists the seeded item's documents read-only with Open links and the Manage link (and the
  old placeholder is gone); **Next shows the next item's own documents** (no stale rows from the previous item); a
  bound `.skp` shows its filename and Open link while the CabVision row stays a dash (the test unbinds it in a
  `finally`, and clears the slot first so a run killed before its cleanup cannot fail the next); a failed load
  says so and does not claim the register is empty. **All four fail against the unfixed modal.**
  `item_project_detail`, `attachments_locks`, `document_register` and `pm_workbench` still pass.
- **Found while testing.** A negative run with `--timeout 12000` timed out mid-test 3 and left a bound SketchUp slot in
  the live database: a Playwright timeout closes the request context, so the `finally` that unbinds cannot run.
  Cleaned by hand. If you run the spec with a short `--timeout`, check `item_attachment` for a stray `sketchup` row.
- **Known gaps, recorded.**
  - ~~**The modal's other disabled fields are still hard-coded dashes**: Floor Plan, RLS, Joiery Details and
    Cutlist Printed~~ **Closed — see *Tracking modal shows the reference fields and JID* below.**
  - The modal's `Actions` and `Query` tabs are still "Coming soon." stubs (both are real on the item editor).
  - The register list is not paged or scrollable beyond `max-h-48`, and shows label only (as on the editor).
- **Out of scope (deferred):** editing from the modal; ~~the four fields above~~ (**built, see below**); the two stub tabs.

## Tracking modal shows the reference fields and JID (no migration, no API change) — shipped

> Chosen by the user ("fill in the Tracking modal's placeholder fields"), the gap *Tracking modal
> shows the register and the SketchUp / CabVision slots* recorded as "not asked for". Three things were
> open, so the user was asked before any code was written; the answers are **settled decisions**.
> Web and seed only.

- **Settled decisions (user).**
  1. **Read-only.** Editing stays on the item editor's `ItemMetadataPanel`, which already owns the
     Controlled / Hard / Approval locks, field-version conflicts and revert-on-refusal. Duplicating that
     in a third place was the alternative offered and declined.
  2. **The header's JID box is included** (asked because it was *not* in what the user named): it showed
     only the word "JID" with no value although `jid_code` / `jid_color` are on `ItemOut`. It now shows the
     colour swatch and code, the same pair the Tracking grid's `JidCell` renders. Empty when the item has
     neither (`data-testid="modal-jid"`).
  3. **The `Actions` and `Query` stub tabs are left as "Coming soon."** — both are real on the item editor
     with their own lock and role rules; making them work here is a separate feature.
- **Web — `tracking/_components/ItemDetailModal.tsx` (only component changed).** Floor Plan, RLS and
  Joiery Details read `item.floor_plan` / `rls` / `joiery_details`; Cutlist Printed reads
  `item.cutlist_printed`. An empty value shows a dash, a NULL `cutlist_printed` shows a dash, `false` an
  open circle, `true` a tick. The `disabled` prop on `Field` and `CheckRow` had no other caller and was
  removed.
- **`items.cutlist_printed` defaults to TRUE** (legacy FileMaker port, `0001`), so every item reads as
  printed unless someone unticks it. A test that only looked at a ticked item would prove nothing.
- **Seed.** `seed/hartwood_joinery.py` sets `floor_plan` / `rls` / `joiery_details` and
  `cutlist_printed = FALSE` on ALF-001's **first** item only (inside the Tracking 2.0 loop's existing
  `UPDATE`, `COALESCE`d so a re-run is harmless), so the modal shows real values there, an open circle
  for Cutlist Printed, and dashes / a tick on the rest. **Direct SQL, not a PATCH**: `PATCH /items/{id}`
  claims the item's Controlled Lock, which a test could not put back.
- **Tests.** `tests/e2e/tracking_modal_files.spec.ts` (4 → 6): the modal shows the item's values (compared
  with `GET /api/items/{id}`, after asserting the seed made them non-empty so the test cannot pass on
  dashes), the JID swatch and code, an open circle for Cutlist Printed, and no inputs; **Next** shows the
  next item's own values (dashes and a tick), not the previous item's. Run three times back to back
  against a live migrated, seeded stack; **both new tests fail against the unfixed modal** (the other four
  pass there) and `item_project_detail`, `pm_workbench` and `smoke` still pass. No backend test was added:
  no API changed.
- **Found while testing.** The sandbox's Chromium (`chromium-1194`) does not match the Playwright this repo
  pins (it wants `1217`), so `playwright test` cannot launch. A throwaway config that spreads
  `playwright.config.ts` and adds `launchOptions.executablePath` pointing at `/opt/pw-browsers/chromium-1194/
  chrome-linux/chrome` runs it without touching the repo; it was deleted afterwards.
- **Known gaps, recorded.**
  - The modal's `Actions` and `Query` tabs are still stubs (above).
  - The Estimator Notes box at the bottom of the left column renders as a narrow textarea under its label
    (an existing layout quirk in `Field`'s textarea branch, not touched).
- **Out of scope (deferred):** editing from the modal; the two stub tabs.

## Duplicate a Joinery Item (Plan V1 §2, migration `0050`) — shipped

> Chosen by the user ("Start the list of questions", after I suggested it as the next task:
> ALIGNMENT's row "Item duplication with selective copy…" was `ABSENT`, the largest
> small-and-self-contained gap). Plan V1 says what *may* be copied and what must *not*, but
> not what happens to the cutlist, the status, the number or the lock, so the user was asked
> before any code was written; the answers below are **settled decisions**, not assumptions.
> No spec or plan doc; this section is its written record.

- **Settled decisions (user, 2026-10-03).**
  1. **The copy gets its own new cutlist** (named for the item, numbered from
     `joinery_number_seq`), never the source's — the Shop Floor workflow belongs to the cutlist
     (Q412), so sharing one would share its progress.
  2. **Joinery Items only.** A related part, an unknown id, another workspace's item and a
     soft-deleted item are all `404`.
  3. **Status resets to `CLEAR`.** Copying `APPROVED` would produce an Approval-Locked copy
     nobody could edit.
  4. **One copy per action.** No "make N copies".
  5. **Copied:** the item's own fields (description, qty, code, level, zone, painting /
     solid-surface requirements, notes, size, assembler / lister, item code, Group ID, floor-plan / RLS / joinery-detail references, JID code + colour, `total_amount`, VAR/BOQ, contractor,
     area / room and the legacy `stage` / `rm_no` / `rm_desc` text), **modules + parts**,
     **hardware lines**, the **five attachment slots**, the **Document Register**, and the
     **QC checklist, unticked** (labels and order kept; `is_checked`, `checked_by`,
     `checked_at` cleared). Plan V1 §2 lists the checklist as copyable and the *results* as not.
  6. **Same project only.**
  7. **Drafter, manager, admin** — `require_drafter()` plus `tracking:write`. Editor and viewer are `403`.
  8. **The source is linked by a new column**, `items.duplicated_from_item_id` (nullable self-FK,
     `ON DELETE SET NULL`, partial index): deleting the source leaves its copies intact, unlinked.
- **Not copied** (Plan V1 §2's exclusion list, kept): stage dates (`item_stages`), locks and the
  cutlist owner, `field_versions`, QC defects and rework, comments, item queries, material takes,
  orders and the edit history. The copy's own history starts with one `item_edit_log` row,
  `_duplicate` ("from #N").
- **Assumptions made while building — not user decisions.**
  - **A locked source can still be duplicated** (Hard, Approval or Controlled). Duplicating only
    *reads* the source, and every lock guards a change to that item. If a Hard Lock is meant to
    forbid copying too, that is a rule to decide, not one to assume.
  - **Attachments and register documents share the same `file_blob`** rather than copying bytes
    (blobs are content-addressed and never deleted, so sharing is safe). A relabel on the copy
    does not touch the source.
  - **`cutlist_printed` takes the column default** rather than the source's value — a copy has
    printed nothing.
  - The source's own cutlist **number and name are not reused**; the copy's cutlist is named for
    the item.
- **Backend — `apps/api/app/item_duplicates/`** (`queries.py`, `routes.py`), mounted at a top-level
  path. `POST /items/{iid}/duplicate` → `201 ItemOut`. The Item ID is allocated **inside** the
  INSERT with `nextval('joinery_number_seq')` (never `MAX+1`). Everything — the item, its children,
  the cutlist and its link, the audit and edit-log rows — happens in **one transaction**: a failure
  part-way (pinned by monkeypatching the cutlist step) leaves no half-made copy. Audit
  `item.duplicate` carries the source id and the number of modules, parts, hardware lines,
  attachments, documents and checklist items copied.
  `ItemOut` (the `GET` / `PATCH /items/{id}` payload) gained `duplicated_from_item_id` and
  `duplicated_from_item_number` (a join on the source's `num`).
- **Web.** The item editor's **Actions** tab gets a **Duplicate item** card (drafter / manager /
  admin; the web mirrors the role set, the API decides) opening `DuplicateItemDialog`: it says what
  is and is not copied, and on confirm opens the new item's editor. A copy's Actions tab shows
  **Duplicated from #N**, linking to the source.
- **Tests.** `test_item_duplicate.py` (20): the item's fields and the link back; a unique Item ID
  from the shared sequence per copy; modules, parts, hardware lines, attachments, documents and the
  unticked checklist copied; the copy's own cutlist and the source's untouched; status `CLEAR` and
  the copy editable although the source is `APPROVED`; stage dates, locks and owner not copied; QC
  defects, rework, comments and queries not copied and no `_create` edit-log row; the source
  unchanged; a locked source can be duplicated; a copy of a copy links to its immediate source;
  deleting the source leaves the copy (link cleared); audit and edit-log rows; drafter / manager /
  admin allowed, editor / viewer `403` with nothing created; related part, unknown id, deleted item
  and another workspace `404`; atomicity. `tests/e2e/item_duplicate.spec.ts` (3), run against a live
  migrated, seeded stack on a production build: a drafter duplicates `JO-K-101` (new Item ID, `CLEAR`,
  the link and its click-through, no link on the original), Cancel makes no copy, a manager sees the
  button and an editor / viewer do not. The e2e deletes its copy with `DELETE /items/{id}` (which,
  since *Item delete removes an unused cutlist*, also removes the copy's own cutlist).
- **Known gaps, recorded.**
  - **The copy set is fixed** — no per-copy choice of what to bring (ALIGNMENT counts the row
    `PARTIAL` for this reason).
  - **No bulk duplicate and no cross-project copy** (decisions 4 and 6).
  - ~~**Deleting an item does not delete its cutlist**, so duplicating and deleting leaves a one-time
    orphan cutlist row.~~ **Closed — see *Item delete removes an unused cutlist* below.**
  - **The copy's parts are not re-checked against the catalog** — a part referencing an archived
    material is copied as is.
  - **A duplicate is not searchable-linked**: Global Search indexes it like any new item and shows
    nothing about the source.
- **Out of scope (deferred):** choosing what to copy; copying across projects; making several copies
  at once; copying related parts (Plan V1 does not ask).

## Item delete removes an unused cutlist (no migration) — shipped

> **Superseded 2026-10-05 by *Item soft delete* (migration `0052`, below).** Deleting an item no longer removes
> anything, so `_drop_cutlist_if_unused`, the `cutlist.delete` audit it wrote and the `IN_USE` refusal are gone and
> `test_item_delete_cutlist.py` became `test_item_soft_delete.py`. The history below is kept as written.

> Chosen by the user ("go", after I suggested it as the next task): a gap I found while building
> *Duplicate a Joinery Item* — `DELETE /items/{id}` left the item's cutlist behind, so every
> duplicate-then-delete (and the duplicate e2e spec) left an orphan row. The rule was
> under-specified (Q440 lets an item have no cutlist but says nothing about an emptied one) and the
> obvious fix was unsafe, so the user was asked before any code was written; the answer is a
> **settled decision**: **delete the emptied cutlist only if it has no production history.**
> No migration, no spec or plan doc; this section is its written record.

- **Why "always delete" was refused.** Deleting a cutlist CASCADEs `worker_assignment` and
  `stage_completion_log` (`0030`), and the Actual Costs labour figure (§I) is priced from
  `stage_completion_log`. Removing an item would silently erase that production and cost history for
  the cutlist's work.
- **The rule (`items.queries._drop_cutlist_if_unused`, called by `delete_item`).** After the item is
  deleted, the cutlist it belonged to is deleted when **no item still references it, it has no
  `worker_assignment` row and no `stage_completion_log` row** — *any* row, so a cancelled assignment
  or an **undone** completion still counts as history and keeps the cutlist as an empty record. A
  cutlist that still holds another item is never touched; an item with no cutlist, and an unrelated
  empty cutlist, are unaffected. It is **one `DELETE … WHERE NOT EXISTS …` statement**, so the test and
  the delete cannot be split by a concurrent link. Audited as `cutlist.delete`
  (`cutlist_no`, `project_id`, `via: "item.delete"`, `item_id`), the same event the cutlist's own delete
  route writes. A refused delete (`IN_USE`, hardware allocated) returns before anything is removed.
- **Not changed.** `DELETE /cutlists/{cid}` still refuses a cutlist holding items (`HAS_ITEMS`) and is
  how an empty cutlist that *kept* its history can be removed by hand. Unlinking an item from a cutlist
  (`DELETE /cutlists/{cid}/items/{iid}`) does **not** delete the cutlist — only deleting the item does.
- **Tests.** `test_item_delete_cutlist.py` (9): the last item leaving takes an unused cutlist; the
  deletion is audited with its cause; a cutlist still holding another item is kept until its last item
  goes; a cutlist with a stage completion is kept with its history intact; an **undone** completion still
  counts; a cutlist with only a **cancelled** assignment is kept; an item with no cutlist deletes as
  before and an unrelated empty cutlist survives; a refused delete leaves the cutlist; and duplicate-then-
  delete leaves only the source's cutlist. **Four fail against the unfixed source**; the other five are
  controls (the kept-cutlist cases). 192 tests across the items, locks, attachments, cutlists, related
  parts, shop floor, actual-costs, duplication and the new file pass.
- **Known gaps, recorded.**
  - **Cutlists that kept history stay as empty records** — by design, but nothing lists or flags them, and
    removing one is manual.
  - **Existing orphan cutlists are not cleaned up** — the rule applies to deletes from now on; a cutlist
    already emptied by an earlier delete stays until someone deletes it.
  - Deleting a project or item through any path other than `DELETE /items/{id}` (e.g. a cascade) does not
    run this rule.

## Tracking layout: no sidebar, working header buttons, scrolling table (after PR #83)
Asked for by the user while reviewing a screenshot of the Tracking tab.
- **No project sidebar on `/tracking`.** `HAppChrome.SIDEBAR_ROUTES` is now `/dashboard` and `/shop-dwgs`. The header bar's project
  switcher does the same job and the items table gets the width (it now shows the DEL / INST columns without scrolling).
  `pm_workbench.spec.ts` still starts from the Dashboard sidebar.
- **Edit item / + New item were never wired.** Both buttons had no `onClick` (the New item tooltip said "needs API hookup"); it
  was not a sync problem. Now: **Edit item** opens the editor of the one ticked row (off, with a hint, for none or several);
  **+ New item** opens `NewItemDialog` (description required, code, qty), creates the item with `POST /projects/{pid}/items`
  and opens it in the editor. Cancelling creates nothing.
- **The items table scrolls both ways** inside its card (`max-h-[calc(100vh-10rem)]`, `overflow-auto`) with a sticky header.
  `.h-scrollbars` (in `globals.css`, palette tokens only) draws always-visible scrollbars: macOS and many laptops show overlay
  scrollbars only while scrolling, which made the scrollable table look cut off. Also fixed an old off-by-one: the header's top
  row spanned one cell too few, leaving the Avail. column without a header cell (invisible until the header became sticky).
- **Tests:** `tracking_layout.spec.ts` (no sidebar on Tracking but still on Dashboard; Edit item states; New item flow in a
  project of its own; table scrolls both ways and the header stays pinned). Screenshotting scrollbars in Playwright needs
  `ignoreDefaultArgs: ["--hide-scrollbars"]`, or headless Chromium hides them.

### Tracking layout, round 2 (same session; decisions by the user)
- **One row for search and filters.** `Cutlist #` and the free-text search first, then the quick-filter chips, in one card.
  The old separate search row and the "Tip: tick rows to apply a bulk status" row are gone: when rows are ticked, an
  `N selected - Apply status… - Clear selection` group appears at the right end of that row (and the bulk-result banner
  with it). `status_locks.spec.ts` still finds "Apply status…" because it ticks a row first.
- **Stats strip.** The four tiles became one slim card with the four numbers inline. "Items in job" says *joinery items,
  related parts not counted*; the footer says `Total rows: 14 (12 items + 2 related parts)` (the 12 vs 14 mismatch was
  related parts, which the tile has never counted, Q558).
- **Pinned columns.** Checkbox through Lister (17 columns, about 950px) stay in place while the stage-date columns scroll.
  `ItemsTable` measures the widths and sets `--pin-1..17`; the `.h-pinned` rules live in `globals.css`. Pinning only switches
  on when the card leaves at least 400px for the scrolling columns (`PIN_MIN_SCROLL_PX`); on a narrower window nothing is
  pinned, because pinning 953px on a 1024px window would leave the date columns unreachable. **Settled with the user**
  (options were: pin when wide enough, always pin, or pin only through Description).
- **JID on one line** (nowrap, 9px mono).
- **Page titles** match the tab name: `Tracking · JoineryFlow` etc. (`title.template` in `app/layout.tsx`, a `metadata` export in
  each tab's `page.tsx`; all of them are server components). `/login` shows plain `JoineryFlow`.

## Item soft delete + the Deleted chip (migration `0052`) — shipped

> Asked for by the user ("link `items.deleted` to get the items soft-delete"). Four decisions, all asked first and
> **settled**: soft delete everywhere; the cutlist is kept and flagged too; the Deleted chip lists deleted items with a
> Restore action; delete stays drafter/manager/admin, **restore is manager/admin only**. Later answers: delete an item
> with production history anyway; separate PR.

- **Schema.** `items.deleted` (there since `0001`, nullable, never written) becomes `NOT NULL DEFAULT false` after a
  backfill, because every reader now says `NOT i.deleted` and a NULL would hide the row. `cutlist.deleted` is new.
  No existing row changes.
- **`DELETE /items/{id}`** (`items.queries.delete_item`) flags the item, its related parts (`parent_item_id`) and its
  cutlist **once no live item is left in it** (one `UPDATE … WHERE NOT EXISTS`). Audited `item.delete` + `item_edit_log`
  `_delete`. No `IN_USE` any more: nothing is removed, so no procurement row is orphaned. Production history
  (`worker_assignment`, `stage_completion_log`), QC, orders and Actual Costs labour all stay.
- **Actual Costs (settled 2026-10-06, the user asked whether a delete should zero the labour).** It does not, and must
  not: labour is priced from the cutlist's `stage_completion_log` rows, which a delete keeps, and hours already worked are
  real cost, so the project's `labour_actual` / `total_actual` are unchanged by a delete (and by a restore). Only the
  per-item split (`labour_by_item`, Q549) follows the live items: a deleted item drops out of it and the live items on its
  cutlist absorb its share (the sum still equals the total); if none is left, the labour stays in the total with no
  per-item entry. `labour_by_item` is not shown in the web today. Tests in `test_actual_costs.py` (4).
- **`POST /items/{id}/restore`** (manager/admin, else 403): clears the flag on the item, its related parts and its
  cutlist. `404` unknown / another workspace, `409 ITEM_NOT_DELETED` for a live item. Audited `item.restore` + `_restore`.
- **A deleted item answers 404 everywhere**, like a missing one. The predicate is `row_types.not_deleted(alias)` /
  `live_joinery_items(alias)` (the old `joinery_items_only` plus the flag; modules that used the latter now use the
  former). `_item_row` hides it unless `include_deleted=True` (only `restore_item`). Shop Floor, `/cutlists`, Global Search
  (the worker drops it from the index) and notifications (a comment on a deleted item) hide it too.
  **`tests/test_items_deleted_filter.py` scans every SQL string that reads `items` / `cutlist` and fails on one with no
  deleted-row filter**; a deliberate exception goes in its `ALLOWED` with the reason (orders outlive their item, Actual
  Costs keeps spent labour, bare FROM fragments completed by their callers).
- **Tracking.** `GET /projects/{pid}/items?deleted=true` returns the deleted rows. The **Deleted** chip (`?deleted=1`) shows
  them read-only (no editor links, no status popup, no metrics strip) with a notice; manager/admin tick rows and press
  **Restore**. A **Delete** button (with a `window.confirm`) joined the selection group next to "Apply status…", because
  the web had no way to delete an item before.
- **Item codes were never unique** (`items.code` has no index), so reusing a deleted item's code needs no rule, and a
  restore cannot collide.
- **Follow-ups (settled 2026-10-07, the user chose the recommended option each time).**
  - **A Hard Lock blocks delete** (`409 HARD_LOCKED`, nothing written or audited). The Approval and Controlled Locks do not.
    Restore is never refused by a lock, since it only undoes a delete. The editor's Delete button is off while locked;
    Tracking's bulk Delete reports `N skipped (Hard Locked)`.
  - **Related parts are soft-deleted too** (`DELETE /related-parts/{id}` flags the row; the audit payload key
    `orphaned_order_ids` became `order_ids`, since an order now keeps its `item_id`). Restore goes through
    `POST /items/{id}/restore`; a part whose parent is still deleted answers `409 PARENT_DELETED`.
  - **The item editor has a Delete button** (header, drafter/manager/admin, `window.confirm`, then back to the project's Tracking).
  - **Known, accepted:** restoring a parent restores *all* its related parts, including one deleted on its own earlier
    (no per-row deleted-at to tell them apart).
- **Not changed.** Hard-deleting a *cutlist* (`DELETE /cutlists/{cid}`) is unchanged.
- **Tests.** `test_item_soft_delete.py` (21), `test_items_deleted_filter.py` (1), e2e `item_soft_delete.spec.ts` (3).

### Item editor header stays on screen (2026-10-08)
A wide Cutlist or Material Take table used to stretch `<main>` (a flex child with `min-width: auto`) and the editor's grid
(`1fr` columns) past the window, which pushed the header's Delete and close buttons, and the Hard-lock / Import from CV /
Delete module buttons, off the right edge (79px at 1500px wide, 299px at 1280px). Fixed with `min-w-0` on `<main>` in editor
mode (`HAppChrome`), `minmax(0,1fr)` columns on the editor's two grids, `min-w-0` on `PartsGrid`, and an `overflow-x-auto` box
around the Material Take table; the tables now scroll inside their own box. Verified: no sideways page scroll on any editor tab
at 1500, 1280 and 1000px. Below 1000px a small (about 35px) overflow on every tab remains from elsewhere in the chrome, which this
did not touch. e2e `item_editor_header.spec.ts` (fails without the fix: 299px at 1280).

### Parked on purpose: the disabled Orders chip on Tracking
Kept visible but disabled; **the user will build it later** (**Deleted** was built with soft delete, and **Tg Solid** went live
with migration `0053`, see `09-e3-pilot-data-import.md`: it filters on the per-item `items.tg_solid` tag).
| Chip | Why it is disabled today (the tooltip in `TrackingClient.tsx`) | What building it needs |
| --- | --- | --- |
| **Orders** | "Backend wiring pending": the list carries each row's issued order number, but the chip has no filter logic | filter to rows that have an order (`issued_order_no` / `order_no` set) once the intended meaning is confirmed |
The chip's state is already wired (`quick` filter key `orders`); only the filter logic and the removal of `disabled` are
missing. Listed in CLAUDE.md "Still open".


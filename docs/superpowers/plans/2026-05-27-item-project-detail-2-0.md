# Item & Project Detail 2.0 — Implementation Plan (#11)

> **Status: partially shipped.** Migration `0036_item_project_detail`.
> Current state lives in `## Item & Project Detail 2.0` in `CLAUDE.md` —
> read it before picking up any of T08–T15 below, it lists exactly what's
> missing (all frontend and seed). The backend (T01–T07) and its tests (T12,
> old numbering) are done. §9's re-open rule is implemented as written, and
> PATCHing a project to `Closed` is refused so close-out is the only way to
> close (user's decision, 2026-09-25).
>
> **Later change (2026-09-25):** T08–T13 below were fleshed out from stubs
> into a full task breakdown before any frontend work started. Two drifts
> surfaced while doing that, now folded into T08: `apps/web/lib/pm-types.ts`
> was never updated for #10/#11's backend changes (`ItemOut`/`ProjectOut`
> are missing fields the Python schemas have served for months), and
> `apps/web/lib/attachments-types.ts` still lists 3 attachment kinds although
> the backend has carried 5 since T07. Both are prerequisites for T09–T11,
> not scope creep — building new UI against the stale types would either not
> compile or silently drop data.
> Departures from this doc: T06 records three choices where it was silent;
> T07's attachment kinds are **five, purely additive** — `cv_drawing` is
> *not* treated as a synonym, and the Combined PDF is unchanged (user's
> decision, 2026-09-25). This doc's "PDF gate stays for named slots" is
> also superseded: `sketchup` holds a native `.skp` and `cabvision` a
> `.cvj`, which `/files` now accepts (same 25 MB cap). Design:
> `docs/superpowers/specs/2026-05-27-item-project-detail-2-0-design.md`.
>
> **Later change:** this doc's title says "#11" — free when written
> (2026-05-27), but by the time this plan merged into `main` (2026-09-24,
> commit `8ac99d5`) #11 had gone to Global Search. Go by the migration
> number or merge date, not this label.

**Spec:** `docs/superpowers/specs/2026-05-27-item-project-detail-2-0-design.md`
**Last updated:** 2026-05-27

---

## T01 — Migration 0025

**File:** `db/alembic/versions/0025_item_project_detail.py`

- `projects.closed_at`, `closed_by`.
- `project_contact`, `project_lift_access`, `item_query`, `item_document` tables.
- Expand `item_attachment_kind_check` to add `sketchup`, `cabvision` (keep `cv_drawing`).
- `project_labour_hours_view` (returns zero per project).

**Acceptance:** `make migrate` clean.

## T02 — Project schemas + queries + endpoints

**Files:** `apps/api/app/projects/{schemas,queries,routes}.py`

- `ProjectOut` adds: builder, classification, site_street/suburb/postcode/state, tg_project_manager, tg_coordinator, tg_solid, carell_pid, total_line_items, closed_at, closed_by, closed_by_name, contacts, lift_access, labour_hours.
- `PatchProjectIn` extends with the new metadata fields.
- New `POST /projects/{id}/close-out` (admin/manager). 409 if already closed.

**Acceptance:** existing project tests stay green.

## T03 — Project contacts module

**File:** `apps/api/app/project_contacts/{__init__,queries,routes,schemas}.py`

- POST/GET/PATCH/DELETE contacts.
- `tracking:write` for writes.
- Workspace isolation through project.

## T04 — Project lift access module

**File:** `apps/api/app/project_lift_access/{__init__,queries,routes,schemas}.py`

- PUT/GET/DELETE lift access.

## T05 — Item Query module

**File:** `apps/api/app/item_queries/{__init__,queries,routes,schemas}.py`

- GET list, POST ask, POST answer, PATCH edit-answer.
- 409 if already answered (on first answer).

## T06 — Item Document Register module

**File:** `apps/api/app/item_documents/{__init__,queries,routes,schemas}.py`

- GET list, POST bind, DELETE unbind, PATCH relabel/reorder.

## T07 — Attachments + item PATCH expansion

**Files:** `apps/api/app/item_attachments/routes.py`, `apps/api/app/items/{schemas,queries}.py`

- Expand attachment `KindPath` regex to add sketchup + cabvision.
- Extend `PatchItemIn` and `_PATCH_FIELD_MAP` with floor_plan, rls, joiery_details, cutlist_printed.

## T08 — Frontend/backend type sync (prerequisite, found while planning)

**Files:** `apps/web/lib/pm-types.ts`, `apps/web/lib/attachments-types.ts`, `apps/web/lib/print.ts`

`pm-types.ts` was never updated for #10/#11's backend changes. `ProjectOut`
is missing every #11 field (`builder`, `classification`, `site_street/
suburb/postcode/state`, `tg_project_manager`, `tg_coordinator`,
`carell_pid`, `closed_at`/`closed_by`/`closed_by_name`, `contacts`,
`lift_access`, `labour_hours`) and `PatchProjectIn` is missing their write
counterparts. `ItemOut` is missing the Tracking 2.0 + #11 fields that
`TrackingItemRow` already carries (`jid_code`, `jid_color`, `var_boq`,
`contractor_id`/`contractor_name`, `total_amount`, `site_measure_notes`,
`floor_plan`, `rls`, `joiery_details`, `cutlist_printed`) even though
`apps/api/app/items/schemas.py`'s Python `ItemOut` has served them since
migration `0036` — `GET /items/{id}` already returns them, the TS type just
doesn't know it. `PatchItemIn` (TS) is missing the same write fields.
Separately, `attachments-types.ts`'s `AttachmentKind` still lists only 3
kinds; the backend (`item_attachments/schemas.py`) has carried 5 since T07.

- Add the missing fields to `ProjectOut`, `PatchProjectIn`, `ItemOut`,
  `PatchItemIn` in `pm-types.ts`, copied 1:1 from the Python schemas.
  `total_amount` is a `Decimal` server-side → JSON string, matching the
  existing note on `TrackingItemRow.total_amount`.
- Add `ProjectContactOut`, `ProjectLiftAccessOut`, `ProjectLabourHoursOut`,
  `CloseOutOut` interfaces (mirrors `apps/api/app/projects/schemas.py`).
- Add `ItemQueryOut`, `CreateQueryIn`, `AnswerQueryIn` (mirrors
  `apps/api/app/item_queries/schemas.py`).
- Add `ItemDocumentOut`, `BindDocumentIn`, `PatchDocumentIn` (mirrors
  `apps/api/app/item_documents/schemas.py`).
- Widen `attachments-types.ts`: `AttachmentKind` → 5 values; `KIND_LABELS`
  gains `sketchup: "SketchUp Model"`, `cabvision: "Cabinet Vision Job"`.
  Keep `ATTACHMENT_KINDS` as the canonical all-5 order the bundle returns
  (`queries.ALL_KINDS` server-side) and add a new
  `COMBINED_PDF_KINDS: readonly AttachmentKind[] = ["cv_drawing",
  "floor_plan", "site_measure"]`. Switch `print.ts`'s
  `attachmentsCountLabel` / `combinedTooltip` to iterate `COMBINED_PDF_KINDS`
  instead of `ATTACHMENT_KINDS` — otherwise widening `ATTACHMENT_KINDS`
  silently breaks the "N of 3" Combined-PDF copy pinned by `CLAUDE.md` and
  `test_print_combined_ignores_sketchup_and_cabvision`.

**Acceptance:** web typecheck clean. No behaviour change — this only widens
types the other tasks then use.

> **→ Done (2026-09-25).** All four TS files updated as scoped; `npx tsc
> --noEmit` and `pnpm run build` both clean. One deliberate scope pull-in
> from T10: since `AttachmentsTab.tsx` already iterates `ATTACHMENT_KINDS`,
> widening that constant to 5 immediately makes it render the SketchUp/
> CabVision cards too — leaving `AttachmentSlotCard.tsx`'s file-picker
> hardcoded to `.pdf` for those two would have been a live (if minor) UX
> papercut, so its `accept` attribute was switched to a per-kind
> `KIND_ACCEPT` map in this pass as well. T10 no longer needs that step —
> only the optional "Used by Combined PDF" badge remains open there.

## T09 — Frontend: item editor — Actions tab, Query tab, reference fields

**Files:** `apps/web/app/(app)/items/[id]/_components/{EditorTabs.tsx,
ItemMetadataPanel.tsx}`; new `ActionsTab.tsx`, `QueryTab.tsx`; new
`apps/web/lib/item-queries-fetch.ts`.

RBAC (confirmed against `apps/api/app/auth/permissions.py`): asking a
question needs `list:read` (every role including `viewer`); answering needs
`list:write`, which is `{drafter, manager, admin, editor}` — **not** the
narrower `{drafter, manager, admin}` set `AttachmentsTab`/`MaterialTakeTab`
use, because those two additionally call `require_drafter()` server-side
and `item_queries` does not. Define a distinct
`CAN_ANSWER = new Set(["drafter","manager","admin","editor"])` rather than
importing the narrower set.

- `apps/web/lib/item-queries-fetch.ts` — `listQueries(itemId)`,
  `askQuery(itemId, question)`, `answerQuery(qid, answer)`,
  `editAnswer(qid, answer)`, thin `fetch("/api/...")` wrappers matching
  `attachments-fetch.ts`'s shape (throw on non-2xx, surface `detail`).
- `QueryTab.tsx` — list newest-first (question / asker / asked_at; answer /
  answerer / answered_at when present); an "Ask a question" form open to
  any reader; an inline "Answer" textarea+button per open question for
  `CAN_ANSWER` roles, and an "Edit answer" affordance on already-answered
  rows (`PATCH /queries/{qid}/answer`). Catch the 409 `ALREADY_ANSWERED`
  from a race on the POST path and point the user at Edit instead.
- `ActionsTab.tsx` — a grid of buttons:
  - **Print Combined / Cutlist / Hardware PDF** — plain links via
    `printUrl(itemId, kind)` from `lib/print.ts`, `target="_blank"`, same as
    `EditorFooter.tsx` already does; reuse that helper, don't duplicate it.
  - **Set status** — check whether the existing `StatusPopup` (Tracking
    components) is decoupled enough to reuse; if it's coupled to
    `TrackingClient`'s state, write a small standalone version here instead
    of forcing a shared import.
  - **Mark REQ done today** — `PATCH /items/{id}/lifecycle/REQ` with
    `{done_date: <today, YYYY-MM-DD>}`.
  - **Jump to Orderbook** — `ItemOut` carries no order reference today
    (only `TrackingItemRow` does), so this can only link to
    `/orderbook?project=<project_id>`, not a specific order row. Flag this
    rather than fabricating a link — the design doc didn't anticipate
    `ItemOut` lacking order fields.
  - **Cutlist Printed** toggle — the design doc sketches this as a header
    chip alongside Painting Req / Solid Surface Req. Those two **already
    exist** as checkboxes in `ItemMetadataPanel.FIELDS`
    (`ItemMetadataPanel.tsx:24-31`). Adding `cutlist_printed` there as one
    more `BoolField` entry is simpler than a new header-chip component for
    a single boolean, and keeps the three flags where a user already looks
    — a deliberate simplification versus the design sketch, called out
    rather than silently dropped.
- Refs panel (**Floor Plan / RLS / Joinery Details**, all varchar(64)) —
  same reasoning: three more `MetaField` entries in
  `ItemMetadataPanel.FIELDS` (click-to-edit-on-blur, identical to
  `level`/`description`) rather than a new panel component.
- `EditorTabs.tsx` — add `"actions"` and `"query"` to `TABS`/`TAB_LABELS`,
  render the two new components.

**Acceptance:** manual — ask a question as a viewer, answer as a drafter,
confirm the 409-then-edit path; toggle Cutlist Printed and confirm it goes
through the Controlled Lock like every other field (a non-owner's toggle
should show the same "Held for approval" message `ItemMetadataPanel`
already shows, since it reuses the same `patchField` helper).

> **→ Done (2026-09-25).** Built as scoped, with one dropped item and one
> reuse found along the way:
> - **No Print Combined/Cutlist/Hardware buttons in `ActionsTab`.**
>   `EditorFooter.tsx` already renders all three, on every tab, at all
>   times — duplicating them inside the Actions tab would just be the same
>   three links shown twice. Dropped rather than copied from the design
>   sketch.
> - **`StatusPopup`** (from `tracking/_components/`) turned out to be fully
>   decoupled from `TrackingClient`'s state (`itemId`/`onClose`/`onUpdated`
>   props, fetches its own item) — reused directly instead of writing a
>   second status-change UI.
> - Verified with `tsc --noEmit` and `next build` only (no running
>   DB/container in this environment) — the Controlled Lock / RBAC claims
>   above are verified by reading `items/routes.py` and
>   `auth/permissions.py`, not by exercising the live app. Manual
>   click-through against `make up` still belongs in T15.

## T10 — Frontend: AttachmentsTab widened to 5 slots

**Files:** `apps/web/app/(app)/items/[id]/_components/{AttachmentsTab.tsx,
AttachmentSlotCard.tsx}`

- `AttachmentsTab.tsx` — no change needed beyond T08's widened
  `ATTACHMENT_KINDS`; it already does `ATTACHMENT_KINDS.map(...)`.
- `AttachmentSlotCard.tsx` — the `<input type="file"
  accept=".pdf,application/pdf">` is hardcoded; add a
  `KIND_ACCEPT: Record<AttachmentKind, string>` map (`sketchup: ".skp"`,
  `cabvision: ".cvj"`, the other three: `".pdf,application/pdf"`) and use
  `KIND_ACCEPT[slot.kind]`. Cosmetic — the real gate is the server-side
  signature+extension check in `item_attachments/queries.py::KIND_MIME` —
  but it stops users picking the obviously-wrong file type.
- Optional: badge the 3 Combined-relevant cards ("Used by Combined PDF")
  via `COMBINED_PDF_KINDS.includes(slot.kind)`. Skip if it adds noticeable
  layout complexity for 5 cards in the existing single-column list.

**Acceptance:** `test_print_combined_ignores_sketchup_and_cabvision` and the
other pinned print tests stay green untouched (backend-only, unaffected by
this). Manual: 5 cards render; SketchUp/CabVision pickers filter to
`.skp`/`.cvj`; Combined tooltip/count still reads "N of 3".

> **→ Done (2026-09-25).** The `KIND_ACCEPT` map and the widened
> `ATTACHMENT_KINDS` iteration were already pulled into T08 (see its own
> `→ Done` note) — this pass added the one thing left: a small "Combined
> PDF" pill on the 3 relevant `AttachmentSlotCard`s, driven by
> `COMBINED_PDF_KINDS.includes(kind)` (computed once in `AttachmentsTab.tsx`
> and passed down as a prop, rather than re-deriving it inside the card).
> `tsc --noEmit` and `next build` clean; the backend print tests are
> untouched by this (frontend-only change). Manual click-through against a
> running app still belongs in T15.

## T11 — Frontend: project page `/projects/[id]`

**Files:** new `apps/web/app/(app)/projects/[id]/page.tsx`, new
`_components/{ProjectHeader,ProjectDetailsPanel,ProjectContactsPanel,
ProjectLiftAccessPanel,ProjectLabourHoursCard}.tsx`, new
`apps/web/lib/{project-contacts-fetch,project-lift-access-fetch}.ts`.

`GET /projects/{id}` already returns `contacts`, `lift_access` and
`labour_hours` embedded on `ProjectOut` (T02) — the page's initial
server-side fetch needs only the one `fetchProject(id)` call, not three.
Mutations go through the dedicated endpoints, then `router.refresh()` —
same pattern as `ItemMetadataPanel.patchField`.

RBAC is **not uniform across this page** — three different gates apply and
must not be collapsed into one `canEdit`:
- **Header/Details panel PATCH** (`builder`, `classification`, site
  address, TG team) — the route hardcodes `manager`/`admin` only
  (`apps/api/app/projects/routes.py:95`, a manual check, not the
  `tracking:write` RBAC row). Gate on `me.auth_role in ("manager","admin")`.
- **Contacts + lift access** — `tracking:write`, which per the matrix is
  `{editor, drafter, manager, admin}`. Gate on
  `can(me, "tracking", "write")` (already imported from `@/lib/session` in
  `procurement/page.tsx`).
- **Close-out** — admin/manager only (separate route check, same as
  Details).

Layout (server component `page.tsx` fetches and passes down, same shape as
`items/[id]/page.tsx`):
- **Header strip**: project_code · name · status pill · builder ·
  classification · install_start · total_value · Close-out button
  (hidden unless admin/manager; the 409 already-closed response surfaces as
  a toast, not a crash).
- **Details panel** (left): site_street/suburb/postcode/state,
  tg_project_manager, tg_coordinator, tg_solid — click-to-edit fields in
  the same style as `ItemMetadataPanel`, gated manager/admin.
- **Contacts panel** (centre): office vs. site contacts (`kind`), "Add
  contact" form, edit/delete per row — gated `tracking:write`.
- **Lift & access panel** (right): notes textarea + single sketch upload
  (`uploadFile` + `PUT /projects/{id}/lift-access`) — gated
  `tracking:write`; sketch accepts PDF/PNG/JPEG (`project_lift_access/
  routes.py` 415s otherwise).
- **Labour hours card** (footer): renders `labour_hours.{site_install,
  assembly,administration}`, all zero today — reuse the "not integrated
  yet" framing `ProjectDetailModal.tsx`'s `HoursTable` already uses for the
  TGPAY-sourced tables rather than inventing new copy.

**Acceptance:** `/projects/{id}` renders for a real ALF-001 id; close-out
works once then 409s on retry; a `viewer` sees the page with no edit
affordances; a cross-workspace id 404s.

> **→ Done (2026-09-25).** Built per the two decisions made before starting
> (asked rather than assumed, since the design doc left both open):
> - **Status stays a read-only pill** in the header — no Current/Hold
>   selector was added on this page. The backend already supports reopening
>   a closed project via a plain `PATCH {status}` (any non-"Closed" value
>   clears `closed_at`/`closed_by`), but T11's own task list never asked for
>   that control here, so it was left out rather than added silently.
> - **`/projects` (the list page) now also links to the new page** — a
>   "Details →" cell per row, alongside the existing name link to
>   `/tracking?project_id=`. Without it the page had no entry point at all
>   until T12 ships, and even then only from inside one modal.
> One correctness point worth flagging for whoever touches
> `project_lift_access` next: `PUT /projects/{id}/lift-access` is a full
> overwrite, not a partial merge (confirmed by reading
> `project_lift_access/queries.py::upsert_lift_access` — both columns are
> set from the request body every time). `ProjectLiftAccessPanel.tsx` always
> sends the current `notes` value alongside whichever field is actually
> changing; a caller that PUTs only the field it means to change will
> silently null out the other one.
> Verified with `tsc --noEmit` and `next build` only — no running
> DB/container in this environment, so the manual click-through (real
> ALF-001 id, close-out-then-409, viewer read-only, cross-workspace 404)
> still belongs in T15.

## T12 — Tracking modal → project page link

**File:** `apps/web/app/(app)/tracking/_components/ProjectDetailModal.tsx`

Add a footer link `<a href={`/projects/${project.id}`}>Open full project
page →</a>` beside the existing "Read-only view..." footer text.
`project.id` is already on `ProjectOut`.

> **→ Done (2026-09-25).** Used `next/link`'s `Link` rather than a bare
> `<a>`, matching every other in-app navigation link in this codebase
> (`/projects/page.tsx`, etc.) — client-side nav instead of a full reload.
> Also dropped "Edit project metadata from the admin tools" from the footer
> sentence, since that vague phrase now has a concrete, linked destination
> right next to it. `tsc --noEmit` and `next build` clean.

## T13 — Seed data

**File:** `seed/hartwood_joinery.py` (new block after the existing `#12
Material Take` block)

Following the file's established idempotency convention (`DELETE FROM
<table> WHERE project_id/item_id = :x` before re-inserting, since none of
these four tables has a natural `ON CONFLICT` key except lift access):

- `UPDATE projects SET builder=..., classification=..., site_street=...,
  site_suburb=..., site_postcode=..., site_state=..., tg_project_manager=...,
  tg_coordinator=... WHERE project_id = :alf` — a plain UPDATE is
  inherently idempotent, no DELETE needed.
- `project_contact`: `DELETE FROM project_contact WHERE project_id = :alf`
  then insert 2 office + 2 site contacts.
- `project_lift_access`: `ON CONFLICT (project_id) DO UPDATE` (the PK is
  one row per project, so this is natural unlike the other three) — notes
  text + a sketch bound through
  `app.files.seed_helper.put_seed_file(s, workspace_id=..., workspace_slug=
  "hartwood-joinery", app_user_id=_drafter_id, path=<one of the existing
  fixture PDFs under seed/hartwood_joinery/sample_drawings/>)`.
- `item_query`: `DELETE FROM item_query WHERE item_id = :item1` then insert
  one answered + one open question on the first ALF-001 item, via
  `app.item_queries.queries.create_query` / `.answer_query` directly (like
  the `#12` block calls `material_takes.queries` functions) so the
  audit/edit-log rows are real, not raw SQL.
- `item_document`: `DELETE FROM item_document WHERE item_id = :item1` then
  bind 2 documents via `app.item_documents.queries.bind_document`, reusing
  the fixture PDFs `put_seed_file` already loads for shop drawings /
  attachments — no new fixture files needed.

**Acceptance:** `make seed` run twice back-to-back produces identical row
counts; print a one-line summary matching the file's existing convention.

## T14 — e2e coverage (new)

**File:** new `tests/e2e/item_project_detail.spec.ts`

Every other shipped sub-project has its own Playwright spec (see the
`tests/e2e/` list in `CLAUDE.md`); this one doesn't yet. Minimal spec: log
in as drafter, open an item, use the Query tab (ask + answer), use the
Actions tab (toggle Cutlist Printed), confirm the Attachments tab renders 5
slots, visit `/projects/{id}` and confirm the header/contacts/lift-access
panels render and close-out works once. Keep it in the same
non-idempotent-suite family as the others (re-seed between runs).

## T15 — Smoke

`make up && make migrate && make seed`. Click through: item editor's 8 tabs
(cutlist/hardware/board/take/attachments/log/actions/query) all render;
`/projects/{id}` shows the 3-column layout with real seeded data; the
Tracking Project Details modal's footer link opens it.

---

## Dependencies

```
T01 ─┬─> T02 ─┬─> T03, T04
     │        ├─> T05
     │        ├─> T06
     │        └─> T07
     │
     └─> T08 (type sync) ─┬─> T09 (item editor: Actions/Query/Refs)
                           ├─> T10 (Attachments widen)
                           └─> T11 (project page) ─> T12 (tracking modal link)
     └─> T13 (seed — independent, parallel with T09–T12)

T09, T10, T11, T12, T13 ─> T14 (e2e spec) ─> T15 (smoke, last)
```

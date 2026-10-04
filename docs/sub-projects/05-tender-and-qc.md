# Tender And Qc

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## Tender Lifecycle + Financials (Plan V1 §5–§6/§16–§17, Q487–494/548–549) — shipped

> Selected by the user as the largest coherent block of decided-but-unbuilt
> Plan V1 questions after §F (Dynamic RBAC engine). Built directly against
> the confirmed decisions in `docs/plan-v1/OPEN-QUESTIONS.md` — no separate
> spec or plan doc, the same way #9a and the RBAC engine shipped. This
> section is its only written record. **Replaces**, not extends, the
> six-state workflow described in the *Estimating (sub-project #9a)* section
> above — see the superseded-callout there before reading its "Revision
> workflow" / "Convert-to-Project" bullets.

- **Migration `0038`** — widens `estimate_revision.status` from 6 values to
  the **12-stage tender lifecycle** of Plan V1 §5: 11 sequential stages
  (`OPPORTUNITY, INITIAL_REVIEW, GO_NO_GO, INFO_REQUESTED, DOCS_RECEIVED,
  ESTIMATING, SUPPLIER_PRICING, INTERNAL_REVIEW, QUOTE_PREPARED,
  MGMT_APPROVAL, SUBMITTED`) plus one terminal position resolving to
  `WON` / `LOST` / `WITHDRAWN` (Q488). Existing rows are remapped
  (Q435 data-preserving): `draft → QUOTE_PREPARED`, `sent → SUBMITTED`,
  `accepted → WON`, `rejected → LOST`, `expired → LOST` (Q548 — Plan V1's
  12 stages have no Expired terminal; mapping onto Lost keeps the reason
  distinguishable in the audit event name even though the status collapses),
  `withdrawn → WITHDRAWN`. A `draft` row lands at **QUOTE_PREPARED**, not
  stage 1 — an in-flight quote already did the opportunity/review/pricing
  work the new early stages describe, and restarting it would make it walk
  stages that, in substance, already happened.
- **`locked_at` generalises "draft".** The old partial unique index
  `uniq_estimate_draft` (`WHERE status = 'draft'`) becomes
  `uniq_estimate_unlocked` (`WHERE locked_at IS NULL`) — the same "at most
  one revision per estimate not yet sent to the client" invariant, now
  correct across all 10 pre-Submitted stages instead of naming just one of
  them. `locked_at` is set exactly once, at `MGMT_APPROVAL → SUBMITTED`, and
  never cleared. Every former `status == "draft"` gate in `queries.py`
  (line create/patch/delete, part/hardware/labour mutation, patch of the
  revision itself) is now a `locked_at IS NULL` check — `_assert_draft` was
  renamed `_assert_unlocked`. **Migration data-integrity note**: a row
  inserted directly by raw SQL with a locked status but no `locked_at` set
  would collide with the new index against a genuinely-unlocked sibling —
  the migration backfills
  `locked_at = COALESCE(locked_at, sent_at, accepted_at, rejected_at, created_at)`
  for every row in a locked status before creating the index, so this can't
  happen even against pre-existing data with hand-inserted rows.
- **`project_contract` (one row per project, immutable `original_value`) +
  `project_contract_variation`** (append-only). `current_value` is
  **computed on read** as `original_value + SUM(variation.amount_delta)`,
  never stored — the same "nowhere to drift" stance `material_summary`
  (#12) already takes (Q491).
- **`_LEGAL_TRANSITIONS`** (`apps/api/app/estimating/queries.py`) — each of
  the 10 sequential stages permits its successor or `WITHDRAWN`;
  `SUBMITTED` permits `WON` / `LOST` / `WITHDRAWN`; the three terminals
  permit nothing. `next_tender_stage()` reads the fixed
  `TENDER_STAGE_ORDER` tuple. Any illegal transition → `409
  {code:"BAD_TRANSITION", from, to}`, unchanged from #9a.
- **One generic `advance()` action covers all 10 forward steps**,
  including `MGMT_APPROVAL → SUBMITTED` — that step's lock-and-snapshot
  business logic (the labour-rate snapshot, `locked_at`, `sent_at`) lives
  in `transition_revision()`'s `target == "SUBMITTED"` branch and fires
  here too, so there is no separate `/send` entry point any more.
  `POST /revisions/{rid}/advance` replaces `/revisions/{rid}/send`
  (**404, retired** — not aliased).
- **`reject` vs `expire` still write distinct audit events** despite both
  landing on the same `LOST` status (Q548 collapses the status, not the
  audit trail) — `transition_revision()` takes an explicit `lost_kind`
  param (`"rejected"` default, `"expired"` from the `/expire` route) rather
  than inferring intent from `lost_reason`'s text.
- **`revise()` restarts a new draft at `ESTIMATING`, not `OPPORTUNITY`**
  (design decision — Plan V1 does not say where a revision restarts): the
  opportunity/review/go-no-go/info-gathering work already happened for this
  tender and doesn't need repeating just because the price is being redone.
- **Handover review screen (Q490).** `GET /revisions/{rid}/handover-preview`
  returns the lines that would become Joinery Items plus the contract value
  Convert would default to (the quote's own GST-inclusive total). The PM
  reviews before converting rather than Convert running unconditionally —
  warranted because Q489 has handover generating a project's entire Joinery
  Item list, not just the project shell.
- **Convert-to-Project, extended.** `POST /revisions/{rid}/convert` still
  requires status `WON` (`409 BAD_STATUS`), still rejects already-converted
  (`409 ALREADY_CONVERTED`, carrying the existing `project_id`) and
  archived-customer, and still re-resolves every part/hardware snapshot
  against the live catalog before writing anything (`409 CATALOG_GONE`
  listing every failure). New: an optional `include_line_ids` body field —
  omitted converts every line (old behaviour unchanged by default), an
  excluded line simply produces no Joinery Item while the rest of the quote
  is unaffected — and an optional `contract_value` override (defaults to
  the quote's own total). The `project_contract` row is created in the same
  transaction as the project, `items`, `modules`, `parts` and
  `project_hardware_catalog` rows Convert already wrote in #9a.
- **Documentation error found and corrected while building this.**
  `docs/plan-v1/OPEN-QUESTIONS.md`'s Q489 claimed "Estimate lines currently
  do **not** become items on convert" — false from the day it was written:
  `convert_to_project()` has created real Joinery Items since #9a's
  original commit (`a7b8d3d`), before Q489 was ever asked. There was no
  line-to-item mapping gap to build; what this sub-project actually added
  on top of the existing mapping is the *selective* handover (`include_line_ids`)
  Q490 asked for. Corrected in place in `OPEN-QUESTIONS.md` rather than
  silently rewritten — see the note under Q489 there.
- **Actual costs rollup (Q493/Q549), `apps/api/app/project_contracts/
  actual_costs.py`.** Pure read, nothing stored — the same "derive, don't
  capture twice" stance #9's `/optimise` already takes. Two sources:
  - **Materials** — `procurement_batches.qty_received * cost_per_unit`,
    summed per project. Project-level only (Q492 caps granularity at
    Project + Item, and there is no per-item allocation path for
    BOARD/CUSTOM/BENCHTOP batches today, the same gap #12's Material
    Summary already lives with for the same reason).
  - **Labour** — each `stage_completion_log` row's duration
    (`completed_at - worker_assignment.started_at`) priced at
    `workspace_labour_rate`. A completion belongs to a **cutlist**
    (migration `0030`), shared by every item on it, so its cost is
    **apportioned across the cutlist's items by each item's share of total
    part area** (`len_mm * wid_mm * qty`, summed per item) — falling back
    to an equal split when no item on the cutlist has any measurable part
    area yet. A completion with no `assignment_id` (nullable — pre-`0030`
    provenance rows) is excluded, not zero-costed: there is no `started_at`
    to derive a duration from.
  - `GET /projects/{pid}/actual-costs` returns `materials_actual`,
    `labour_actual`, `total_actual` and a `labour_by_item` breakdown map.
- **Backend module `apps/api/app/project_contracts/`** (`schemas.py`,
  `queries.py`, `actual_costs.py`, `routes.py`), mounted at top-level paths.
  3 endpoints, all gated `("tracking", action, project_param="pid")` — the
  **second adopter** of the Dynamic RBAC engine's project-scoped check
  (`apps/api/app/areas/routes.py` was the first, written before this
  sub-project as a demonstration only):
  - `GET /projects/{pid}/contract` — 404 if the project has none yet
    (predates Q491 or wasn't created from a converted estimate — not an
    error).
  - `POST /projects/{pid}/contract/variations` — creating the row *is* the
    decision (§6: "the PM decides whether a change becomes a Variation");
    there is no separate approval step here — whoever can write already
    decided.
  - `GET /projects/{pid}/actual-costs` — always 200 (zeros when nothing to
    roll up yet), 404 only for a foreign/missing project.
- **RBAC — no matrix change.** Contract/actual-costs routes reuse
  `tracking:{read,write}`, same as `project_contacts` / `project_lift_access`
  (Item & Project Detail 2.0) — Contract Value lives on the project page
  alongside them.
- **Web.**
  - `apps/web/lib/estimating-types.ts` — `TENDER_STAGE_ORDER`,
    `TENDER_STAGE_LABELS`, the widened 14-value `EstimateStatus` union,
    `HandoverPreview*`, `ConvertResult` (now carries `contract_value`).
  - `apps/web/lib/project-contract-types.ts` + `-fetch.ts` (new) —
    `ProjectContract`, `ContractVariation`, `ActualCosts`,
    `projectContractApi.addVariation()`.
  - `EstimateDetailClient.tsx` — the single "Send" button became
    `advance()` + a dynamic label (`nextStageLabel()` reads
    `TENDER_STAGE_LABELS[TENDER_STAGE_ORDER[i+1]]`; shows "Submit to
    client" rather than "Advance → Submitted" on the last hop, and disables
    when advancing to Submitted with zero lines). `ConvertPreviewDialog`
    now renders one checkbox per line (backed by a `Set<number>` selection
    state) sourced from the handover-preview endpoint, instead of a single
    confirm button.
  - New `ProjectFinancialsCard.tsx` on `/projects/[id]` — Contract Value
    (original + current) + an inline "+ Add variation" form, plus the
    read-only Materials / Labour / Total actual-costs strip. Renders "No
    contract on this project yet" rather than hiding itself when the
    project predates Q491.
  - `CustomerDetailClient.tsx` and `EstimatingClient.tsx`'s
    `STATUS_COLOURS` maps widened to all 14 statuses (found via `tsc
    --noEmit`, not the initial grep — `CustomerDetailClient` lives outside
    `estimating/` and was missed on the first pass).
- **Seed.** `make seed` now lands the three demo estimates on
  `QUOTE_PREPARED` / `SUBMITTED` / `WON` (was `draft` / `sent` / `accepted`)
  and adds one `project_contract` row on ALF-001 (`$185,000.00`) with one
  variation (`+$4,250.00`, "Client-requested benchtop upgrade") — through
  the same query functions the API uses, so the seeded row carries a real
  `audit_log` entry. Idempotent (`DELETE FROM project_contract WHERE
  project_id = :p` before insert).
- **Tests:** `test_estimating_lifecycle.py` (new — full 12-stage transition
  graph, including `/send`'s 404 retirement), `test_estimating_handover.py`
  (new — preview + selective convert), `test_project_contracts_routes.py`
  (new — contract CRUD + RBAC), `test_actual_costs.py` (new — labour
  apportionment, a 2:1 item-area split verified against a $200 completion
  → $133.33 / $66.67), plus `test_estimating_routes.py` /
  `test_estimating_workspace_isolation.py` / `test_home_dashboard.py`
  updated in place for the new status literals and transition actions.
  Full suite (915 passed, 10 skipped, 1 failed) run against a real migrated
  Postgres 16 instance with zero regressions outside the files above. The
  one failure, `test_search_reindex.py::test_real_reindex_swaps_and_drops_temp`,
  is a pre-existing local-environment gap unrelated to this work: unlike its
  sibling `meili`-marked tests it reads `os.environ["MEILI_URL"]` directly
  instead of skipping when unset, so it only runs (and fails) when no
  Meilisearch instance is reachable — `make test`'s docker-compose
  environment always sets `MEILI_URL`, so CI never sees this.
- **`tests/e2e/estimating.spec.ts` updated** for the new seed statuses
  (`QUOTE_PREPARED` / `SUBMITTED` / `WON` in place of
  `draft` / `sent` / `accepted`); the Convert button and quote-PDF link
  gates it exercises (`WON` / `SUBMITTED` respectively) were unchanged by
  this rewrite.
- **Out of scope (deferred):** ~~PO/supplier-order generation from a won
  quote~~ **built, see *PO Generation from a Won Quote* below**, Q472-style
  per-object rule migration into the RBAC engine for this module's
  hand-written gates (unaffected — none were added here), a rollback path
  for `_LEGAL_TRANSITIONS` (Q513 already ruled this out generally), and
  moving `Cars/OH&S`/`Scope` tab content onto the new financials card
  (blocked on Q550/Q572, unrelated customer inputs).

## QC / Rework / Packing (Plan V1 §26–§28, Q515–519) — shipped

> Selected by the user over §L (Locking/Concurrency) after §I shipped —
> chosen as the "bolt on a new subsystem" option, additive to existing
> surfaces rather than a rewrite of save semantics on the busiest ones.
> Built directly against `docs/plan-v1/OPEN-QUESTIONS.md` §M — no separate
> spec or plan doc, the same way #9a, the RBAC engine and §I shipped. This
> section is its only written record.

- **Migration `0039`** — three new tables (`qc_defect`, `qc_checklist_item`,
  `rework`), a `PACKING` row in the `stages` lookup (`sort_order 85`,
  between `MADE=80` and `DEL=90`), widened `worker_assignment` /
  `stage_completion_log` CHECKs to admit `'PACKING'`, and a backfill of
  `group_module_grant` for the new `qc` RBAC module across every existing
  workspace's 7 system groups (see *RBAC* below — this is **not** the same
  thing as adding `qc` to the static `MATRIX`, and both were required).
- **QC is a module, not a workflow stage** (Q515) — Plan V1 §22 lists QC
  among the stages, but §26 describes it as checking *the work just
  completed* at whatever stage that was, a cross-cutting activity rather
  than a milestone. `items.stage_key` / `lifecycle_stage` is untouched by
  QC; only Packing (below) is a real 11th stage.
- **`qc_defect`** — one row per finding, optionally tagged with the
  `stage_key` whose work is being checked. Two states only: `open` →
  `resolved`. Raising/editing a defect is `qc:write`; resolving it is
  `qc:approve` — a defect a Foreman raises isn't self-closed, matching the
  shop_drawings not-uploader-approves pattern. A resolved defect is
  immutable (`409` on edit or on resolving twice).
- **`qc_checklist_item`** — a per-item QC checklist line (`label`,
  `is_checked`, `checked_by`/`checked_at`, `sort_order`). Plan V1 §2 lists
  "QC checklist" among what a duplicated Joinery Item copies and "QC
  results"/"Defects" among what it must *not* copy — item duplication
  itself is not built anywhere in this tree yet, so there is nothing to
  wire that distinction into today; noted for whoever builds it.
- **`rework`** — **one entity with a `kind` CHECK** (`internal`/`full`),
  not two entity types (Q516): "they differ in when they occur and how much
  work they involve, but what must be recorded — cause, scope, cost and
  responsibility — is the same" (`plan_v1.md` line 1926-1929), and those
  four fields plus `kind` are exactly the columns. **Rework never reopens a
  completed stage** (Q517) — it is a parallel record; the original
  `stage_completion_log` rows stay intact. This also sidesteps a real
  problem the shared cutlist would otherwise create: production stages
  belong to the cutlist and are shared by every linked item, so reopening
  one for a single item would have reopened it for all of them.
  Closing rework is `qc:approve`, same shape as resolving a defect.
- **The QC-timing rule (Q518) is guidance, not enforced.** §26 describes
  what happens depending on how far the work has progressed (before
  Listing QC doesn't need to know; after Listing but before Assembly the
  Lister updates the cutlist; after Assembly it's Internal Rework; after
  Installation it's Full Rework) — none of this is checked in code. The
  `kind` a defect becomes is the QC operator's call.
- **Packing (Q519) — a real 11th lifecycle stage, with scanning.** Unlike
  QC, Packing genuinely is a stage: "the first addition to the workflow
  stage list since Q459 kept the existing ten" (`plan_v1.md` line 2130).
  It is the 6th Shop Floor stage — `SHOP_FLOOR_ORDER_DEFAULT` /
  `_PAINT_LAST` (`apps/api/app/shop_floor/lifecycle.py`) both now end in
  `PACKING` unconditionally, after `MADE`/`PAINTED` regardless of their
  relative order, since Packing always comes after all
  fabrication/finishing. Assignable, start/complete, undo — all exactly
  like `DOWN`/`CNC`/`EDGED`/`PAINTED`/`MADE`. `DEL`/`INST` remain outside
  Shop Floor (Q561, unchanged).
- **Scanning without the native app.** Q519 confirms Packing as "a tracked
  stage, with scanning," and ties that to Q532's dedicated native site
  application — which does not exist anywhere in this repo (`apps/api` +
  `apps/web` is the whole stack). Rather than wait on that separate
  project, scanning is built **in the browser**: `getUserMedia` + `jsQR`
  decode QR frames from the camera, no native app and no new backend
  service. A manual-entry fallback (type the number) covers cameraless
  browsers, denied permission, and desktop testing.
  - **`GET /items/{id}/label`** (new page, deliberately **outside** the
    `(app)` route group so it renders bare, not wrapped in TopBar/SideBar
    chrome — proxy.ts's `PUBLIC` allowlist is path-based, not
    route-group-based, so the page still redirects to `/login` without a
    session) renders a QR code (the `qrcode` npm package, client-side
    canvas) encoding the item's own `num` — the one value `joinery_number_seq`
    already guarantees unique, not a new identifier scheme. "Print Label"
    sits next to the three existing print links in `EditorFooter.tsx`.
  - **The scan target is the whole cutlist, not a single item.** Shop
    Floor's unit is the cutlist (migration `0030`); one "Mark Packing
    done" action completes it for every linked item, and there is no
    per-item completion state to scan against. Scanning **any one** item's
    label on the cutlist is enough — `StationCard.item_numbers` (new field,
    `worker_queue()`'s `array_agg` of the cutlist's item `num`s) is what the
    scanner checks the decoded value against.
  - `PackingScanner.tsx` (`shop-floor/station/[worker_id]/_components/`) —
    only wired into the kiosk's `MarkDoneDialog` when
    `card.stage_key === "PACKING"`; every other stage keeps the plain
    confirm button unchanged.
- **RBAC — new `qc` module, the 12th** (between `estimating` and
  `it_management` in `_ALL_MODULES`). Mirrors `shop_floor`'s
  drafter-is-downstream shape, not the elevated-drafter pattern most other
  modules use — QC is production-floor territory:
  - admin/manager: `{read,write,approve,comment}`
  - editor: `{read,write,comment}` — can raise a defect/checklist
    item/rework, cannot resolve or close one
  - drafter: `{read,comment}` — same shape as `shop_floor`'s drafter row
  - estimator/purchase_officer/viewer: `{read}`

  **This needed two separate changes, not one.** Adding `"qc"` to
  `_ALL_MODULES` and to the static `MATRIX` dict makes it available to
  `seed_system_groups()` for any workspace created (or re-seeded) *after*
  this migration — but every already-existing workspace's system groups
  were populated once, by `0037`'s own hardcoded backfill, and the Dynamic
  RBAC engine (§F) resolves a user with real memberships from
  `group_module_grant` alone, never falling back to `MATRIX` for them. So
  migration `0039` also inserts the 16 `(role, 'qc', action)` rows directly
  into `group_module_grant` for every workspace's existing 7 system groups
  — the same shape 0037's own backfill used, scoped to just the new
  module. Skipping this would have left `qc` invisible to every real user
  in every workspace that existed before `0039`, while still passing any
  test that creates a fresh zero-membership user (which falls back to
  `MATRIX` and would look right for the wrong reason).
- **Backend module `apps/api/app/qc/`** (`schemas.py`, `queries.py`,
  `routes.py`), mounted at top-level paths. **12 endpoints**, all
  Joinery-Items-only (`joinery_items_only()`, the `item_documents`
  precedent — a related part gets 404) and workspace-isolated through
  `items → projects.workspace_id`:
  - `GET/POST /items/{iid}/qc/defects`, `PATCH /qc/defects/{did}`,
    `POST /qc/defects/{did}/resolve`
  - `GET/POST /items/{iid}/qc/checklist`, `PATCH /qc/checklist/{cid}`,
    `DELETE /qc/checklist/{cid}`
  - `GET/POST /items/{iid}/qc/rework`, `PATCH /qc/rework/{rid}`,
    `POST /qc/rework/{rid}/close`
  - Every mutation writes `audit_log` **and** `item_edit_log` in the same
    transaction, per the PM Workbench invariant. Audit events:
    `qc.defect.{create,update,resolve}`,
    `qc.checklist.{add,check,uncheck,update,remove}`,
    `qc.rework.{create,update,close}`.
- **Web.** New **QC** tab in the item editor (`EditorTabs.tsx`, between
  Query and Log) — `QcTab.tsx` renders all three sections (Defects,
  Checklist, Rework) on one screen, matching the density of
  `AttachmentsTab`/`QueryTab` rather than three separate tabs. Shop Floor's
  office board (`ShopFloorClient.tsx`) and its types (`shop-floor-types.ts`)
  gained the 6th `PACKING` column; the kiosk (`StationClient.tsx`) gained
  the scan-gated `MarkDoneDialog` path described above.
- **Seed.** `make seed` on ALF-001's first joinery item: 1 open + 1
  resolved defect, a 3-item QC checklist (2 checked), 1 open Internal
  Rework — built through the real `app.qc.queries` functions, so seeded
  rows carry genuine `audit_log`/`item_edit_log` entries, same as #11/#12's
  seed blocks. A second item gets one `assigned` `PACKING` `worker_assignment`
  (raw SQL, matching the pre-existing #8 shop_floor seed block's own idiom)
  so the board's 6th column isn't empty out of the box. Idempotent —
  each table's target-item rows are dropped before re-inserting.
- **Tests:** `test_qc_routes.py` (new, 15 tests — defect/checklist/rework
  round-trips, `qc:write` vs `qc:approve` split via editor-cannot-resolve/
  close, resolved/closed immutability, Joinery-Items-only 404s,
  cross-workspace isolation, audit+edit-log writes), two new PACKING tests
  in `test_shop_floor_routes.py` (assignable + completes after `MADE`;
  before `MADE` is `409 STAGE_OUT_OF_ORDER`), `test_shop_floor_lifecycle.py`
  updated in place for the new 6-stage ordering (existing "last stage has
  no later stages" tests were pinned to `MADE`, now correctly `PACKING`),
  and `test_permission_groups_routes.py`'s admin-grant-count assertion
  updated `44 → 48` (12 modules × 4 actions, was 11 × 4) — the one test in
  the whole suite that hardcoded a MATRIX-derived total and needed
  updating for a module addition. Full suite (932 passed, 10 skipped, 1
  pre-existing unrelated failure — the same local-only `MEILI_URL` gap
  noted in *Tender Lifecycle + Financials* above) run against a real
  migrated Postgres 16 instance with zero regressions outside the files
  named here.
- **Out of scope (deferred):** ~~the standalone cross-project **QC
  Dashboard** Plan V1 §4.2 names~~ **built, see *QC Dashboard* below**
  (this section shipped the per-item surfaces that back it); QC checklist templates or
  per-project configuration (today's checklist is ad-hoc per item, added
  free-text, matching Simplicity First over building a template system
  nothing asked for); linking a `rework` row to the `qc_defect` that caused
  it (Plan V1 doesn't ask for the link, and rework can originate without a
  formal defect record, e.g. found on site); §L's remaining Hard/Approval
  lock types and field-level optimistic concurrency (the alternative this
  round didn't pick — **since built, see *Locking + Concurrency* below**);
  native mobile app work under Q532 (Packing's scanning need is met without
  it, per above).

## QC Dashboard (Plan V1 §4.2, Q515) — shipped

> Chosen by the user as the next sub-project after `/auth/me` ("Next task is QC
> Dashboard (§4.2). Ask me any questions"). §4.2 names a "QC Dashboard" and says
> nothing else, so the user was asked before any code was written; the answers
> below are **settled decisions**, not assumptions. No migration, no spec or plan
> doc; this section is its written record. It is the option *Deferred options*
> called C, and it closes the gap *QC / Rework / Packing* named as out of scope.

- **Settled decisions (user).**
  1. **Scope: only items whose cutlist has started but not finished.** The user's
     wording was "current cutlists have not been assigned to finished but have
     already started to make", which was ambiguous, so it was asked again and
     confirmed. A cutlist has no finished flag, so both words are **derived from
     Shop Floor** (Q412: the workflow belongs to the cutlist):
     *started* = an assignment on the cutlist with `started_at` set and not
     cancelled, **or** any `stage_completion_log` row not undone;
     *finished* = a `PACKING` completion not undone (PACKING is the last Shop
     Floor stage; DEL / INST are not assignable, Q561). A merely `assigned` task
     is **not** started; a cancelled start is not started; an undone completion
     is not a completion; an undone PACKING puts a cutlist back in scope.
     **An item with no cutlist is out of scope** (nothing to have started).
  2. **Open records only**, for both defects and rework. Resolved defects and
     closed rework are history and stay on the item's own QC tab.
  3. **Contents:** open defects by project and by stage, open rework by project
     and kind (with cost), and a drill-down list of the items carrying open
     records. Checklist completion and a per-record worklist were offered and
     **not** chosen.
  4. **`/qc` on the secondary tab strip, gated on `qc:read`.** No new permission:
     IT already controls it through the permission groups, and the tab hides
     when `qc:read` is removed (the `/auth/me` work). Q466 deliberately did not
     build tab-level scoping, so this is the same module gate every other tab has.
  5. **Read-only**, every row linking to `/items/{id}?tab=qc` where raising,
     resolving and closing already live with their own `qc:write` / `qc:approve`
     rules. Nothing on the dashboard mutates data, so it writes no audit row.
  6. **Fixed numbers, filterable by project and date range** — no configurable
     widgets, matching Q527 (fixed KPI catalogue, no formula engine).
- **Records outside the scope are counted, never dropped.** That is a choice made
  while building, not one the user asked for: with a started-but-not-finished
  scope, a defect raised on a cutlist nobody has begun would otherwise vanish
  from QC entirely. `scope.open_defects_out_of_scope` /
  `open_rework_out_of_scope` say how many were left out, and the page shows an
  amber note when either is non-zero. Related parts are neither in scope nor
  counted as outside it (they are not Joinery Items; a defect on one cannot be
  raised through the API anyway).
- **Backend — `apps/api/app/qc/dashboard.py`** (+ schemas, one route in
  `qc/routes.py`). `GET /qc/dashboard?project_id=&date_from=&date_to=`, gated
  `("qc", "read")`. One `scope` CTE feeds every number so they cannot disagree
  about which items count. `404` for a project outside the workspace, `422` when
  `date_from` is after `date_to`. The date range filters when a record was
  **raised** (`created_at`, inclusive of both ends) — for an open record that is
  the only date it has; there is no "resolved in range" because resolved records
  are not shown. Stage order comes from the `stages` lookup's `sort_order`, with
  untagged defects last. **Stage labels are lookup data and differ between
  databases** (`Marked Down` in one, `Down` in another), so tests assert
  `stage_key`, never a label.
- **Rework cost can under-count, and says so.** `rework.cost` is optional, so
  `rework_cost_total` sums only what was recorded and `rework_cost_missing`
  counts the open rework with no cost. The page shows `—` (not `$0.00`, which
  reads as a real total) when *nothing* has been priced, and "Excludes N open
  rework with no cost recorded" otherwise. Money arrives as a JSON string, as
  everywhere else.
- **Web.** `/qc` (`app/(app)/qc/page.tsx` + `QcDashboardClient.tsx`), a `QC` entry
  on the secondary strip after Cut Floor (production tabs together, Estimating and
  Customers still a pair). Filters live in state **and** the URL
  (`?project=&from=&to=`, via `history.replaceState`, the pattern the Areas &
  Rooms card uses) so a filtered view is linkable and survives a reload; only
  the newest request may write, so a slow response for an earlier filter cannot
  overwrite the one on screen. `lib/permissions.ts`'s `Module` type gained
  `"qc"` (it lagged `0039`).
- **Seed.** `make seed` adds to what §M already left on ALF-001: an open `CNC`
  defect on the third item (its cutlist has a `DOWN` completion — in scope, and a
  second stage for the chart) and an open, untagged defect on the second item
  (its cutlist is only *assigned* — out of scope, so the amber note has
  something to say). Through `app.qc.queries`, so the rows carry real audit /
  edit-log entries. Idempotent (both items' defects are dropped first). The
  dashboard then opens with 2 open defects, 1 open rework with no cost, and
  1 defect not counted.
- **RBAC — no matrix change.** `qc:read`, already granted to every role.
- **Tests.** `test_qc_dashboard.py` (15): scope at **every** boundary (started,
  completed, unpacked are in; no cutlist, not started, merely assigned,
  cancelled start, undone completion, finished are out) and an undone PACKING
  bringing a cutlist back; out-of-scope counted for both kinds of record; open
  only; by project and stage with untagged last and the oldest age; rework by
  kind with cost and unpriced count; drill-down oldest first and omitting clean
  items; the empty dashboard; related parts not counted; project filter scoping
  even the out-of-scope counts; the date range (inclusive, and applied to the
  out-of-scope counts too); the 404 / 422 edges; `qc:read` required (a group
  stripped of `qc` gets 403) and sufficient (a viewer sees it); workspace
  isolation; read-only writes no audit row. **The scope test was confirmed to
  fail against a loosened "started"** (any assignment counts: 5 items in scope
  instead of 3). `tests/e2e/qc_dashboard.spec.ts` (4) was run against a live
  migrated, seeded stack: the numbers and the amber note, a row drilling to the
  item's QC tab, filters narrowing / persisting across a reload / clearing, and a
  viewer seeing the same numbers with no buttons on the page. The spec is
  read-only, so unlike estimating / comments it is safe to re-run without
  re-seeding. `smoke.spec.ts` and `item_project_detail.spec.ts` (which touch the
  tab strip) still pass.
- **Known gaps, recorded.**
  - **Checklist completion, a per-record worklist and resolved / closed history
    are not on the dashboard** (not chosen). The drill-down goes to the item.
  - **No supplier breakdown.** Defects and rework are not linked to a supplier;
    adding that is a schema change, not a query.
  - `rework.responsibility` is free text, so there is no "by person / team"
    view either.
  - The scope is derived, so a cutlist whose stages were never assigned through
    Shop Floor (work recorded some other way) reads as *not started* and its
    defects show only in the amber count.
  - The date range uses the database session's time zone for its day
    boundaries, and "oldest" ages are computed in the browser.
  - The dashboard does not poll: the numbers refresh on a filter change or a
    reload, not on a timer (the bell and the Shop Floor board do poll).
  - **Two grants, one click.** The dashboard needs `qc:read`; the drill-down
    opens `/items/{id}`, which needs `list:read`. Every default group holds
    both, but an admin who grants one without the other gives a user a link that
    403s — the same pairing gap Comments documents for item threads. The Project
    filter's list comes from `GET /projects` (`tracking:read`), so it too comes
    back empty for a group that holds `qc:read` alone.
  - **Full rework mostly falls outside the scope.** Q518 puts Full Rework *after
    Installation*, and Installation is after PACKING — the point at which a
    cutlist leaves the dashboard's scope. So open `full` rework (and defects
    found on site) are counted only in the amber "not counted" note, and the
    Full column and cost tile are structurally sparse. This is the direct
    consequence of the user's confirmed "started but not finished" rule, not a
    bug, and the rule was **not** changed; whether post-PACKING open records
    should also be counted is the open question it leaves.
- **Out of scope (deferred):** the other §4.2 department dashboards (Estimating,
  Project Management, Procurement, Material, Production, Installation,
  Management); §4.3's management KPI dashboards; user-arranged widgets;
  export / scheduled reports (§31).

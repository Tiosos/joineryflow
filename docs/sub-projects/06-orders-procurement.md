# Orders Procurement

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## PO Generation from a Won Quote (Plan V1 §21, Q505) — shipped

> Selected by the user as the next sub-project after §L, closing the gap
> named twice as deferred — in *Estimating* and *Tender Lifecycle +
> Financials* — since Convert-to-Project shipped: Convert stops at project
> + contract creation, and every material the quote priced still had to be
> re-entered by hand into the Orderbook. Built directly against Plan V1
> §21's "Create PO" (Q505) and the existing orders/catalog schema — no
> separate spec or plan doc, the same way #9a, the RBAC engine, §I, §M and
> §L shipped. This section is its only written record.

- **Sources from the revision's own line breakdown**
  (`estimate_line_part` / `estimate_line_hardware`), not the converted
  project's items and not the Material Summary. Two reasons, both found
  during design, not assumed:
  - The converted project's `parts` table only retains a real material FK
    for **BOARD** (`board_material_id`) — CUSTOM/BENCHTOP catalog links
    survive there only as a `[material: {type}#{id}]` comment string
    (#9a's own schema constraint note). Reading the revision directly
    keeps every `material_id` real for all five order-eligible types.
  - The Material Summary (#12) was considered and rejected: **Q585**
    already confirmed "no create-order-from-line in v1" for that surface,
    deferring it to §21's full required/ordered/received/outstanding
    design. Building it there now would have contradicted a settled
    answer, not filled a gap.
- **Live catalog pricing, not the quote's frozen snapshot.** Each material
  is re-resolved against its catalog row at generation time (sku,
  description, cost, `default_supplier_id`) rather than reusing
  `cost_per_unit_snapshot` — Plan V1 §21 requires stale project-specific
  pricing to be caught before PO creation, and generation typically
  happens well after the quote was priced (Convert already requires
  `WON`, and there is no deadline after that). `_resolve_order_source()`
  (`apps/api/app/estimating/queries.py`) is a sibling of the existing
  `_resolve_part_snapshot` / `_resolve_hardware_snapshot` used when a line
  is first priced — same tables, but reading current values and the real
  `default_supplier_id` FK (migration `0029`) instead of the free-text
  `default_supplier` those two read.
- **Grouped by live default supplier, one PO per supplier.** Every
  distinct `(material_type, material_id)` referenced anywhere in the
  selected lines is **consolidated into one PO line with a summed
  quantity** — the same SKU quoted on five lines becomes one line for the
  total, not five, because a real procurement PO groups by SKU. Cut
  dimensions (`len_mm`/`wid_mm`) are deliberately dropped: they're cutting
  information for Production, not purchasing information for a PO. A
  material with no `default_supplier_id` can't become a PO line
  automatically (`purchase_orders.vendor_id` is `NOT NULL`) and is
  returned as `unassigned` instead — surfaced for the PM to order by hand
  via the existing per-item Create Order flow, never blocking the
  suppliers that DO have one. A PO's `category` is the material_type most
  represented in its lines (`"BOARD".capitalize() == "Board"`, matching
  `order_category`'s joinery keys from migration `0031` exactly — most
  suppliers specialise, so this is usually unambiguous, not an arbitrary
  pick on a tie).
- **Reuses the orders module end-to-end** (`orders.queries.create_order` /
  `add_line`) rather than inventing a parallel order entity — the same
  "`purchase_orders` + `po_line_items` ARE the order layer" stance
  Q502/Q553 already established for #10. Each generated PO carries
  `attributes: {"generated_from_revision_id": <rid>}` for traceability (no
  new column) and lands at the module's own default `status = 'Draft'` —
  Procurement reviews and edits from there like any other order.
- **Migration `0041`** — one column, `estimate_revision.orders_generated_at
  timestamptz NULL`. It guarded `generate_orders()` to run **at most once per
  revision**: the revision is already locked by the time it's WON, so its
  line breakdown is frozen and there is no legitimate reason to
  regenerate from it. Set once, never cleared — the same "quote is
  frozen" stance `locked_at` already takes. **Superseded by migration `0048`
  (see *Generate Orders: per-line selection*): the guard is now per quote *line*,
  and this column means "the most recent run".**
- **Backend** — `apps/api/app/estimating/{queries,schemas,routes}.py`
  (no new module; PO generation is estimating's own concern, keyed by
  revision like Convert and the handover preview):
  - `GET /revisions/{rid}/order-preview` — the review screen before
    generating, same shape Convert's own `handover_preview` established
    for Q490: every group + the unassigned list, computed fresh, nothing
    written.
  - `POST /revisions/{rid}/generate-orders` — `include_line_ids` (default:
    every line, same shape as `ConvertIn`). Requires the revision already
    **converted** (`409 NOT_CONVERTED` otherwise — a PO needs a real
    project to attach to) and rejects a second call
    (`409 ORDERS_ALREADY_GENERATED`) — *since `0048` only once no line is left
    to order; see *Generate Orders: per-line selection**. `409
    UNKNOWN_LINE_IDS` on a foreign line id, mirroring Convert.
  - Both gated `estimating:approve`, the same gate Convert and the
    handover preview use (admin/manager/estimator).
  - Audit: `estimate.generate_orders` on the revision, plus the orders
    module's own `order.create` / `order.line_add` per PO/line it creates
    (reused, not duplicated).
- **Fixed later, found live-testing this feature.** `convert_to_project()`
  hardcoded every `parts` row's `seq` to `1` instead of incrementing per
  part in the module — harmless while no seed or test fixture had more
  than one part on a single quote line, but `uq_parts_module_seq
  (module_id, seq)` (migration `0007`-era constraint) rejects a second
  part with the same seq, so **any WON quote line with two or more
  parts — of any material type, not just duplicates — raised a raw
  `IntegrityError`/500 instead of converting.** This had shipped
  undetected since #9a's original commit; the seed data and every
  existing test fixture happen to give each line at most one part. Found
  because verifying PO generation live needed a line quoting two
  different board materials to exercise both the "assigned" and
  "unassigned" grouping paths in one request. Fixed by enumerating
  `part_seq` per module instead of a literal `1`. Pinned by
  `test_convert_line_with_two_parts_does_not_collide_on_seq`
  (`test_estimating_routes.py`), confirmed to fail
  (`UniqueViolation` on `uq_parts_module_seq`) against the pre-fix code.
- **Web.** `EstimateDetailClient.tsx` gains a "Generate orders" button
  (visible once `converted_project_id` is set and `orders_generated_at`
  isn't) opening `OrderPreviewDialog` — styled like the existing
  `ConvertPreviewDialog`: one card per supplier group with its lines and
  live unit cost, an amber unassigned-materials card, and a confirm button
  that calls `generate-orders` with no line filter (**since *Generate Orders:
  per-line selection*, the dialog lists the quote lines and sends the ticked
  ones**). After generating, a result banner names the
  order/line counts and any unassigned materials, links to the Orderbook,
  and the button is replaced by a permanent "Orders generated {time}"
  note on reload — read from the same `orders_generated_at` the backend
  guards on, not local component state.
- **RBAC — no matrix change.** Reuses `estimating:approve`, already
  granted to admin/manager/estimator.
- **Tests:** `test_estimating_generate_orders.py` (new, 13 tests) —
  supplier grouping, quantity consolidation across lines, the unassigned
  path, both 409s (`NOT_CONVERTED`, `ORDERS_ALREADY_GENERATED`),
  `include_line_ids` filtering, `UNKNOWN_LINE_IDS`, workspace isolation,
  the `estimating:approve` RBAC gate (via a second same-workspace user —
  no role has `estimating:write` without also having `approve`, so
  testing the gate needs a lesser-privileged user looking at a quote
  someone else built), and the audit row + `orders_generated_at` write.
  Plus the `convert_to_project` regression test above. Full suite (965
  passed, 10 skipped, 1 pre-existing unrelated failure — the same
  local-only `MEILI_URL` gap noted in *Tender Lifecycle + Financials*
  above) run against a real migrated Postgres 16 instance with zero
  regressions outside the files named here.
- **Deliberately not seeded.** None of the seed's three demo estimates
  are converted — the WON one is left that way on purpose (§I's seed
  note: "ready for a human to click Convert"), and auto-converting it in
  `make seed` would silently remove the Convert button
  `tests/e2e/estimating.spec.ts` exercises against it. Verified instead
  by live-testing the full flow (create quote → WON → Convert → Generate
  orders → Orderbook) against a real browser and a real migrated
  Postgres, per this session's UI-testing requirement — the same
  live-testing pass that surfaced the `convert_to_project` seq bug above.
- **Out of scope (deferred):** ~~per-line selection in the Generate Orders
  dialog~~ (**built, see *Generate Orders: per-line selection***); §21's much larger Procurement target
  (supplier comparison, PO → Confirmation → Receipt → Inspection flow,
  procurement exceptions, supplier performance tracking, claims/credits,
  deposits/progress payments) — this ships only "Create PO" (Q505)'s real
  purchase order, not the surrounding workflow Plan V1 describes around
  it; ~~regenerating orders after a partial run~~ (**built — a later run covers
  the lines an earlier one did not, see *Generate Orders: per-line selection***);
  rolling generated-order cost back onto the item or project
  (Q543's "item cost does not roll up" stance is unaffected — orders
  carry cost, nothing aggregates it further here either).

## Orderbook — Purchase Order editing UI — shipped

> Selected as the next sub-project after PO Generation from a Won Quote —
> the gap that surfaced live-testing it: a generated PO's consolidated
> lines (summed quantities, live-catalog cost at generation time) had no
> way to be corrected before sending to a supplier, and the Orders tab
> itself was entirely read-only. Built directly against the existing
> `orders/` module and §L's field-version machinery — no separate spec or
> plan doc, the same way most sub-projects after #9a have shipped. This
> section is its only written record.

- **The order header PATCH already existed** (built for §L) — this
  sub-project closes the two gaps around it: no way to edit or remove an
  individual `po_line_items` row once added (only `POST .../lines`
  existed), and no web UI at all for either the header PATCH or the line
  endpoints.
- **`PATCH /orders/{po_id}/lines/{line_id}`** and
  **`DELETE /orders/{po_id}/lines/{line_id}`** (`apps/api/app/orders/
  {schemas,queries,routes}.py`), both gated `orderbook:write`, both
  workspace-isolated through the same `_ORDER_WORKSPACE` join every other
  route in the module uses. `patch_line()` / `remove_line()` reuse
  `_lock_order_for_update()` — the same row lock `add_line()` already took
  to serialize against `UNIQUE (po_id, line_number)` — so a concurrent
  edit and a concurrent add on the same order can't race either.
  `PatchOrderLineIn` covers `item_description` / `sku` / `quantity` /
  `unit` / `unit_price`; `line_number` and the provenance columns
  (`material_table`, `material_id` — which catalog row a generated line
  came from, if any) are not patchable. Both routes return the full
  `OrderDetailOut` (order + refreshed `lines`), matching `add_line`'s
  existing return shape.
- **No `expected_versions` on lines, deliberately.** §L's field-level
  optimistic concurrency (Q511/Q512) is scoped to exactly three named
  surfaces — items, cutlist, and the order **header** — and lines were
  never one of them; widening it to per-line versioning here would be
  scope creep the user never asked for, the same "Q510 is a ceiling, not
  an invitation to widen" reasoning this file already states for a
  different boundary. Line edits stay last-write-wins, like every
  pre-existing field on every surface §L didn't name.
- **`DELETE /orders/{po_id}/lines/{line_id}` returns `200 OrderDetailOut`,
  not the `204` its sibling `DELETE /orders/{po_id}` (whole-order
  soft-cancel) uses** — a deliberate, noted departure: the web UI needs
  the refreshed `lines` array immediately after removing one, and a line
  delete is a hard delete (no soft-cancel state to represent), unlike the
  order-level endpoint it otherwise resembles.
- **Web — `/orderbook`'s Orders tab is no longer read-only.**
  `orderbook/page.tsx` now fetches `me` (it never had before — the one
  page-level file under `(app)/` missing it) and threads it through
  `OrderbookTabs.tsx` to `OrdersClient.tsx`, which computes
  `canEdit = can(me, "orderbook", "write")`. Selecting a row now fetches
  the full `GET /orders/{po_id}` detail (with `lines` and `field_versions`)
  instead of reusing the already-fetched list row, which never carried
  either. The detail panel:
  - Editable header fields (status / priority selects; order number /
    supplier ref / notes / internal comments as blur-to-save inputs;
    required/ordered/ETA dates) follow the same `patchField` +
    `expected_versions` pattern `ItemMetadataPanel.tsx` established for
    §L — a `FIELD_CONFLICT` names the one field and its `current_value`
    rather than failing the whole save.
  - An editable lines table (inline blur-to-save per cell, a Remove button
    per row) plus an Add-line mini-form, wired to the three line
    endpoints. All editing controls are hidden — not just disabled — for
    a caller without `orderbook:write`, matching the rest of this app's
    read-only-role convention.
  - Q418's existing `?order=<po_number>` deep link is unaffected: it still
    selects and scrolls to the row; the panel that opens under it is what
    changed.
- **RBAC — no matrix change.** Reuses `orderbook:{read,write}`, already
  granted per the existing matrix (drafter has full read+write+approve+
  comment on `orderbook` since Procurement Workbench's elevated-drafter
  pattern; purchase_officer has read+write+approve; editor/viewer/
  estimator read-only).
- **`purchase_orders.total_amount` is now kept in sync with its lines.**
  The column predates `po_line_items` and was never wired to it — every PO
  `generate_orders` (§21/Q505) creates gets its lines via `add_line()` but
  `total_amount` stays at its 0.00 default forever, so the Orderbook and
  this new detail panel showed "Total: $0.00" under a stack of real-dollar
  lines. `add_line()` / `patch_line()` / `remove_line()` now all call a
  shared `_recompute_total_amount()` (`SUM(line_total)` over the PO's
  lines) after their write, and it bumps `field_versions["total_amount"]`
  too (a plain UPDATE bypassing that would let a stale header PATCH
  silently clobber the freshly-summed total with no `FIELD_CONFLICT` — see
  *Fixed later* below) — a no-op when the sum hasn't actually changed, so
  it never bumps the version for nothing. Deliberately narrow: `quantity` /
  `unit_cost` (singular fields with no coherent value across multiple
  lines) are left untouched, and a header-only order that never gets a
  line (the original per-item Create Order flow) is unaffected, since
  nothing there calls these three functions. **Known gap — CLOSED, see
  *Purchase order status guard* below**: when this shipped, neither the
  line routes nor the pre-existing header PATCH blocked editing a
  `Cancelled`/`Delivered` order — there was no order-status guard anywhere
  in this module.
- **Tests:** 16 new cases in `test_order_routes.py` — line PATCH updates
  editable fields and recomputes `line_total`, 404 for an unknown line
  (both with a real patch body and with an empty/non-patchable one — see
  *Fixed later* below) and for a line on a different order, line DELETE
  removes it and 404s the same way, both routes 403 for a `viewer`-role
  same-workspace user, a cross-workspace PATCH 404s, a parametrized case
  rejecting an explicit `null` for each of the three `NOT NULL` fields, two
  cases pinning the `total_amount` rollup (single line, and summed across
  two), one proving its version bump is real bookkeeping, one proving a
  direct header PATCH to `total_amount` is a no-op once lines exist (but
  still works on a header-only order), one proving a `FIELD_CONFLICT`'s
  `current_value` for a Decimal field stays a string, and one proving a
  stale `total_amount` version in a batch PATCH's `expected_versions`
  doesn't block an unrelated field in the same call. Full suite green
  against a real migrated Postgres 16 instance (existing 14 + new 17 in
  the module; zero regressions elsewhere).
- **Fixed later (six rounds of max-level code review, same day).**
  `patch_line()`'s empty-fields early return (a PATCH with `{}` or a
  non-patchable key like `line_number`) skipped the line-existence check
  the UPDATE's rowcount otherwise performs, so it 200'd with the order
  instead of 404ing for a line that doesn't exist on this PO — now checks
  existence explicitly before returning, pinned by
  `test_patch_line_404_for_unknown_line_with_no_patchable_fields`.
  `LineRow`'s local input state never resynced to the server's canonical
  value after a successful save (`quantity: "5"` round-trips as `"5.000"`,
  a `numeric(10,3)` column) — the next blur's dirty check
  (`quantity !== line.quantity`) kept firing an unnecessary PATCH and a
  fresh `order.line_update` audit row on every blur of that cell for the
  rest of the panel's life, even with no further edit; each of the five
  editable fields now has a `useEffect` resyncing local state to the
  matching `line.*` prop. The same missing-resync shape existed on the
  three header-field helpers (`EditableField`, `EditableDateField`,
  `BlurTextArea`) with a sharper consequence: after any *other* field's
  save refreshed `order` (and its `field_versions`), a stale local value
  left in an untouched field would be resubmitted with the now-current
  `expected_versions`, passing the conflict check and **silently
  overwriting a concurrent edit with no 409** — defeating §L/Q511-Q512's
  whole guarantee. All three now resync via `useEffect` on their value
  prop, and (a second finding on the same components) now skip the save
  entirely when the value is unchanged from props, matching `LineRow`'s
  existing dirty-check and stopping a bare tab-through from firing a
  no-op PATCH that bumps `field_versions` and hands the next real editor a
  false `FIELD_CONFLICT`. `fieldErrorMessage`'s `NOT_FOUND` branch checked
  `body.detail.code === "NOT_FOUND"`, but `patch_order_route`'s 404 is a
  plain string detail (`"order not found"`, matching every other 404 in
  this module) — the branch was unreachable dead code; it now checks
  `res.status === 404` instead. `EditableDateField` saved on every
  `onChange` rather than `onBlur` (the pattern every other editable field
  in this file, and `ItemMetadataPanel.tsx`'s own fields, follow) — a
  native `<input type="date">` fires `onChange` with `""` after each
  keystroke while typing a date directly, so the first keystroke into
  Required-by/Ordered/ETA immediately PATCHed the field to `null`, wiping
  an existing date before the user finished typing a new one; now saves on
  blur like its siblings. `PatchOrderLineIn` typed `item_description` /
  `quantity` / `unit_price` nullable (to allow *omitting* them) with
  nothing rejecting an explicit `null` for these `NOT NULL` columns, so
  `{"quantity": null}` passed validation and hit the UPDATE as a raw
  `IntegrityError`/500; a `model_validator` now rejects an explicit null
  for the three with a clean 422, pinned by the parametrized test above.
  The `total_amount` rollup above was also raised in this pass, as a
  pre-existing gap (predating this sub-project, in `add_line()`) that this
  sub-project's own new line-mutation surface made worse by giving PMs new
  ways (edit, remove) to drift the header further from the lines under it.
  A fourth pass, after the rollup landed, found two more: the rollup's own
  plain `UPDATE` bypassed `bump_field_versions()`, so a stale header PATCH
  read before a line changed the total could pass its `FIELD_CONFLICT`
  check and silently clobber the freshly-summed value — writing that fix
  exposed a **second, older, latent bug it was the first to actually
  trigger**: `patch_order_route`'s 409 handler puts `current_value`
  straight into `HTTPException`'s `detail`, which Starlette serializes
  with plain `json.dumps` (bypassing the response_model's Pydantic
  encoding) — a `Decimal` (`quantity`/`unit_cost`/`total_amount`) or a
  `date` (`required_date`/`date_ordered`/`due_date`) in that dict 500s
  instead of returning the 409. This has been reachable since §L shipped
  `patch_order`'s field-conflict path — no existing test exercised a
  conflict on any of those six fields, only string ones — and is fixed
  here, scoped to the `orders` module alone, by wrapping the detail in
  `jsonable_encoder()`; the identical shape likely exists in `items`'s and
  `cutlist`'s own conflict paths too (neither touched by this diff), left
  as a known gap rather than fixed opportunistically outside this module
  (**since fixed — see *FIELD_CONFLICT serialisation on items and cutlists***).
  Pinned by `test_recomputed_total_amount_bumps_its_field_version` (the
  version bump) and `test_field_conflict_current_value_serializes_decimal_as_string`
  (the encoder fix, added in the next pass below — this test alone would
  have failed differently, with a raw 500, before it). Separately,
  `removeLine()`'s error path showed
  "Remove failed" for a 404 on a line already removed (a double-click
  before the confirm dialog, or a second user's earlier removal) even
  though the goal — the line being gone — was already achieved; it now
  treats that 404 as success and skips the request entirely when the line
  is already absent from the last-known order.

  A fifth pass found the version-bump fix above had only patched the
  *symptom*, not the actual defect it was describing: `total_amount` was
  still directly `PATCH`-able via the header at the same time
  `_recompute_total_amount()` was writing it from the lines — two writers
  for one field, and a version bump doesn't resolve that, because the
  rollup isn't submitting an "expected prior value" to check against, it's
  deriving one; a manual header PATCH could still land after a line change
  and silently discard the freshly-summed total with no error either way.
  `patch_order()` now drops `total_amount` from a PATCH's patchable fields
  once the order has ≥1 line — the same way `_LINE_PATCHABLE` already
  drops `line_number` — so once the rollup starts writing it, it's the
  field's only writer; a header-only order (no lines, the original
  per-item Create Order flow) is unaffected and keeps direct access. Also
  from this pass: `jsonable_encoder()` (the previous pass's own fix, above)
  encodes a `Decimal` as a JSON **number**, breaking this codebase's own
  pinned convention that every money/quantity field serializes as a
  string (`orders-types.ts`'s header comment, restated in nearly every
  `-types.ts` file this session has touched) — `current_value` now goes
  through a small `_conflict_safe_value()` that stringifies
  `Decimal`/`date`/`datetime` before `jsonable_encoder` ever sees it, so
  the type stays consistent regardless of which layer serializes the
  response. And `AddLineForm.submit()`'s `setBusy(false)` sat after an
  unguarded `await onAdd(...)`, so a thrown network error or invalid-JSON
  response left "+ Add line" stuck disabled on "Adding…" for the rest of
  the panel's life; it now runs in a `finally`. Pinned by
  `test_total_amount_is_not_directly_patchable_once_lines_exist` and
  `test_field_conflict_current_value_serializes_decimal_as_string`.
  **Noted, not fixed:** `generate_orders()` (§21) calls `add_line()` once
  per consolidated material, so each now triggers its own
  `_recompute_total_amount()` — a SUM-and-conditional-UPDATE round trip per
  line instead of one after the whole batch. For the PO sizes this
  produces (materials consolidated per supplier on one quote) this is
  negligible; summing once after the loop would need a parameter threaded
  through a different module's function and isn't worth that coupling for
  a micro-optimization with no observed correctness cost.

  A sixth pass found the fifth pass's own `total_amount` fix was itself
  incomplete: dropping `total_amount` from `fields` left it in
  `payload.expected_versions` untouched, and `check_field_conflicts()`
  evaluates every key in that map regardless of whether `fields` still
  includes it — so a batch PATCH naming both `status` and `total_amount`
  together (each with its own `expected_versions`, the exact pattern this
  module's own docstring describes) would raise a spurious
  `FIELD_CONFLICT` on `total_amount` once its version had moved via the
  rollup, blocking the unrelated `status` write it was never meant to
  gate. Fixed narrowly — `total_amount` alone is dropped from
  `expected_versions` too, once lines exist — **not** by filtering to
  `fields` in general: `test_cutlist_conflict_on_unrelated_expected_version_key_does_not_500`
  (§L, cutlist) already pins the opposite behavior on purpose for every
  *other* field — a caller naming an unrelated/bogus key in
  `expected_versions` is meant to conflict, not be silently dropped — so a
  blanket filter would have broken that established, tested contract
  instead of fixing this one field's specific tension. Pinned by
  `test_stale_total_amount_expected_version_does_not_block_an_unrelated_write`.
  Separately: none of `patchField()` / `patchLine()` / `removeLine()` /
  `addLine()` in `OrdersClient.tsx` wrapped their `fetch()`/`res.json()` in
  try/catch, unlike the established pattern (`ItemMetadataPanel.tsx`'s own
  `patchField`) — a thrown network error left the calling field's onBlur
  handler mid-await with no revert and no visible error, looking saved
  while nothing had reached the server; all four now catch and report,
  matching that pattern exactly (`AddLineForm.submit()`'s `finally` from
  the fourth pass stays as defense in depth, but `addLine` itself no
  longer throws).

  A seventh pass found one more real gap and confirmed two prior notes were
  the right call to leave alone: `_recompute_total_amount()`'s `UPDATE`
  never set `updated_at`, unlike every other mutation in this module
  (`patch_order`, `cancel_order`, `sync_orders_for_item` all set
  `updated_at = now()`) — a line add/edit/remove genuinely changes the
  order, so its timestamp should move too; fixed, pinned inline in
  `test_add_line_returns_the_order_with_the_new_line`. Re-raised but
  **not fixed, on inspection**: rejecting a negative `quantity` /
  `unit_price` on the new line-PATCH endpoint — checked against every
  sibling Decimal field in this codebase (`estimate_line`'s `qty` /
  `cost_per_unit_snapshot`, this same module's own pre-existing
  `CreateOrderLineIn`) and **none** carry a `gt=0`/`ge=0` constraint
  anywhere; only percentage fields do. Adding one here alone would be a
  new, unprecedented rule for this one endpoint, not a fix to something
  this sub-project broke — left alone, consistent with the rest of the
  codebase. The order-status guard and the `EditableField`/
  `EditableDateField`/`BlurTextArea` duplication were both re-raised too;
  both already had their own notes above (*Known gap* and *Known
  duplication, not fixed*) and stood unchanged then — the guard has since
  shipped, see *Purchase order status guard*; the duplication remains.
- **Known duplication, not fixed.** `EditableField` / `EditableDateField` /
  `BlurTextArea` re-implement the same per-field PATCH +
  `expected_versions` + resync-and-dirty-check shape `ItemMetadataPanel.tsx`
  (`MetaField` / `NotesField`) and `CutlistClient.tsx` already carry as
  independent copies — a third one here. Flagged, not extracted into a
  shared hook: pulling three call sites with slightly different save
  signatures into one helper is a real refactor with its own risk, out of
  scope for a PATCH-editing UI on one more surface.
- **Out of scope (deferred):** per-line `expected_versions` (above);
  bulk line operations (multi-select delete, CSV re-import into an
  existing order); a PATCH-editing UI for anything on the Delivery Queue
  tab (`procurement_batches` — untouched, still #4's surface); reordering
  lines (`line_number` is immutable, matching `add_line`'s own
  auto-increment-only stance).

## Purchase order status guard — shipped

> Chosen by the user as "Option B" from the suggestion list that followed
> Global Search RBAC sync — **note the labels differ between lists**: this is
> Option B of *that* list, not Option B (Comments) of *Deferred options*
> below, and the user was asked which was meant before work started. Closes
> the gap the Orderbook editing section recorded as "Known gap, not fixed".
> No migration, no spec or plan doc; this section is its written record.

- **Rule.** An order whose `status` is `Cancelled` or `Delivered`
  (`orders.queries.FROZEN_STATUSES`) is read-only in the orders module:
  - **Lines** — `POST` / `PATCH` / `DELETE /orders/{po_id}/lines…` answer
    `409 {code: "ORDER_LOCKED", status}`. Enforced in the one place all three
    already pass through, `_lock_order_for_update()`, which now reads the
    status under the same `FOR UPDATE` lock — so a status change racing an
    edit cannot slip past the check. It raises `OrderLocked`; the routes turn
    that into the 409. A frozen order also answers 409 before any
    line-existence 404 (the order's state is answered first); an unknown
    *order* is still 404.
  - **Header** — `PATCH /orders/{po_id}` may change **`status` and nothing
    else**. Any other field answers `409 {code: "ORDER_LOCKED", status,
    blocked_fields: [...]}`. A mixed `{status, notes}` PATCH is **refused
    whole, not trimmed**: a 200 that silently dropped half the request would
    lie, and the caller can simply send two calls. `total_amount` on an order
    that has lines is still dropped silently first (its own rule — the
    rollup is the only writer), so a `total_amount`-only PATCH stays a no-op
    rather than a 409.
- **Settled decisions (user, asked before building; each was under-specified
  by every document):**
  1. **Which statuses freeze: Cancelled and Delivered.** Cancelled is dead;
     Delivered has been reconciled against goods received and invoices.
     `Rejected` stays editable — it can be fixed and resubmitted — as do
     `Draft` / `Pending` / `Approved` / `Hold` / `Quote` / `Next`.
  2. **`status` stays writable on a frozen order** — the deliberate,
     versioned, audited way back in. A mistaken cancel or delivery is
     reopened by PATCHing `status` (to anything, including another frozen
     status), after which the order is editable again. The alternative, a
     fully frozen order, would make that mistake fixable only in the
     database.
- **What it deliberately does not touch.**
  - **`DELETE /orders/{po_id}`** (soft-cancel) is unchanged: it still
    accepts a `Delivered` order and answers `ALREADY_CANCELLED` on a second
    call. Cancelling is a status change, which the rule permits.
  - **`sync_orders_for_item`** still rewrites CUTLIST NO. on a frozen order
    (Q430/Q431): that is the system keeping a reference true, not a person
    editing the order. Pinned by
    `test_cutlist_number_sync_still_reaches_a_frozen_order`.
  - **The legacy `/procurement/*` namespace** writes `Delivered` /
    `Cancelled` itself (`procurement/queries.py`) and carries no guard; this
    is scoped to `orders/`, the surface the Orderbook page uses.
  - **`generate_orders()`** is unaffected — it only adds lines to orders it
    has just created as `Draft`.
- **Web.** `OrdersClient.tsx` mirrors the set as `FROZEN_STATUSES`
  (**the backend is the source of truth and enforces it**; the constant only
  decides what to render). On a frozen order, for a caller who can write, the
  status select is kept and every other control — priority, the five header
  fields, notes, internal comments, and the whole lines table with Remove and
  Add-line — is rendered read-only, with a banner naming the status and how to
  reopen. A read-only role sees no banner (there is nothing for them to
  reopen). `ORDER_LOCKED` from a stale panel (the order was cancelled
  elsewhere while this one sat open) shows "Order is Cancelled — change its
  status to edit" beside the field, **refetches the order and refreshes the
  list**, so the panel lands in the frozen state instead of staying editable
  and failing again. ~~The status-set duplicated in TypeScript is a small
  drift risk~~ — **removed: `OrderOut.locked` is server-computed and the web
  reads it, see *Server-computed `locked` on orders* below.**
- **Fixed in review (same day).** `cancel_order` (`DELETE /orders/{po_id}`)
  is the *other* way into a frozen state, and it read the order with a plain
  `SELECT` and never bumped `field_versions["status"]` — so a panel that
  loaded the order before it was cancelled could PATCH `status` back with a
  still-valid `expected_versions` and silently undo the cancel, contradicting
  the "deliberate, versioned" reopen this section describes; two concurrent
  cancels could also both pass the `ALREADY_CANCELLED` check. It now takes the
  same `FOR UPDATE` lock and bumps the status version (pinned by
  `test_cancel_bumps_the_status_version_so_a_stale_reopen_is_a_conflict`).
  Separately, a lock message from a stale edit ("Order is Cancelled — change
  its status to edit") stayed in the panel's error state and reappeared under
  the same field once the order was reopened; a successful `status` change now
  clears every per-field and per-line message. `add_line` gained a docstring
  stating that it raises `OrderLocked`, since the freeze made a hidden
  precondition of it (`estimating.generate_orders` is safe only because it adds
  to orders it has just created as Draft).
- **Known gaps, found in review and deliberately not fixed.** (1) ~~`status` is
  an unvalidated string on `PatchOrderIn`~~ **Closed — see *Order field
  validation* below** (and note the `null` half was worse than described here:
  it persisted and broke every read; `priority` had the same bug, and a
  cross-workspace `vendor_id` hole turned up beside it). (2) ~~The `FROZEN_STATUSES` set exists in Python
  and TypeScript~~ (**closed — see *Server-computed `locked` on orders***), and the four handlers in
  `OrdersClient.tsx` each repeat a three-line "if locked, refetch and refresh
  the list" block; a shared helper would remove the latter but is a refactor of
  handlers this change only touched at the edges.
- **Tests:** 18 new cases in `test_order_routes.py` — all three line
  operations refused on each frozen status with nothing applied; non-status
  header fields refused with `blocked_fields`; a mixed PATCH refused whole;
  status as the way back in (and the order editable again afterwards); a
  move between frozen statuses; five non-frozen statuses stay editable; an
  unknown order is still 404 (and an unknown line on a frozen order is 409);
  the cutlist sync reaching a frozen order; a `total_amount`-only PATCH on a
  frozen order staying a no-op; cancelling a Delivered order; and the
  versioned-cancel regression above. The five refusal tests were confirmed
  to **fail against the pre-guard code**.
  Verified live in a browser against a migrated database: freeze via the
  status select, banner and editors gone, still frozen after reload, reopen,
  the stale-panel case (order cancelled out-of-band → refused, panel
  refreshed, nothing persisted), and a viewer sees no banner.
- **Out of scope (deferred):** guarding `Rejected`; ~~a server-computed
  `locked` flag~~ (**built, see below**); the same guard on the legacy `/procurement/*` routes;
  restricting who may reopen a frozen order (today anyone with
  `orderbook:write`, like every other status change) — a
  manager-only reopen would be a rule to decide, not assume.

## Order field validation (`PatchOrderIn` / `CreateOrderIn`) — shipped

> Chosen by the user as "PatchOrderIn.status validation" — the first of the two
> *Known gaps* left under *Purchase order status guard*. It grew twice while being
> built, each time because checking the neighbouring fields turned up the same
> bug or a worse one, and **each time the user was asked before it grew**: first
> `priority` and `category` (settled: "Yes: priority and category too"), then a
> cross-workspace `vendor_id` hole (settled: "Fix it in this PR"). No migration,
> no spec or plan doc; this section is its written record.

- **What was wrong, each measured before fixing.** `PatchOrderIn` took bare
  `str` / `int` for fields the database constrains, and `patch_order` sent them
  straight into the UPDATE:
  - **`status` / `priority` — an unknown value** (`"Foo"`, but also `"draft"`,
    `" Draft"`, `""`: the CHECKs are exact and case-sensitive) was a raw
    `CheckViolation` 500 (the route has no `IntegrityError` handling).
  - **`status` / `priority` — an explicit `null` poisoned the whole Orderbook.**
    This file had recorded it as "leaves an order with no status"; it was much
    worse. Both columns are nullable and NULL satisfies the CHECK, so it was
    **written**; the route calls `db.commit()` *before* FastAPI validates the
    response, so the NULL **persisted**, and then `OrderOut.status: str` /
    `priority: str` 500'd on **every read of that order — including the
    workspace-wide `GET /orders` behind the Orderbook page**. One `null` from
    anyone with `orderbook:write` took the Orderbook list down for the whole
    workspace until the row was repaired in the database. Reproduced on the
    unfixed code for both fields (`PATCH → 500`, DB value `NULL`, `GET
    /orders/{id} → 500`, `GET /orders → 500`).
  - **`category`, `vendor_id`, `description`** are `NOT NULL`, so an explicit
    `null` was a raw 500 (nothing persisted). An unknown `category` was a raw FK
    500 (the column references the `order_category` lookup).
  - **`vendor_id` — a cross-workspace hole.** `create_order` checks the vendor is
    in the caller's workspace; `patch_order` never did. `PATCH /orders/{id}` with
    **another workspace's `vendor_id` returned 200, saved it, and the response
    carried that workspace's supplier name** (verified live). An order with no
    project reaches its workspace *through its vendor* (Q554/Q555), so this could
    also have moved such an order into the other workspace. An unknown
    `vendor_id` was a 500.
- **The fix — `apps/api/app/orders/{schemas,queries,routes}.py`.**
  - **`OrderStatus` and `OrderPriority`** are `Literal`s of the values in
    `purchase_orders_status_check` / `_priority_check` (migration `0002`).
    `PatchOrderIn.status` / `.priority` use them; **`CreateOrderIn.priority`
    does too** (its unknown value was the same 500, at the INSERT).
  - **One `field_validator`** on `PatchOrderIn` refuses an explicit `null` for the
    five fields `vendor_id`, `description`, `category`, `status`, `priority`. A
    `field_validator` rather than `PatchOrderLineIn`'s `model_validator` on
    purpose: it runs only for a field the caller **supplied** (an omitted field is
    untouched) **and** the 422 names the field (`loc` ends in `status`, not just
    `body`). Explicit null is *rejected*, not read as "no change" — the choice
    `PatchOrderLineIn` already made, so it was not asked. `description` is in the
    set because it is the identical `NOT NULL` failure beside its siblings.
  - **`category` is checked against the lookup, not a `Literal`** — `order_category`
    is data IT can extend without a migration (Q557). `_category_exists()` runs in
    `patch_order` **and `create_order`**; unknown → `422 {code: "UNKNOWN_CATEGORY",
    category}`. **An archived category is still accepted**: the FK always did, this
    turns a 500 into a refusal and adds no archiving rule (pinned, and recorded as
    a gap, not endorsed).
  - **`vendor_id` is checked in `patch_order`** with the same
    `_vendor_in_workspace()` `create_order` now shares (one query, previously
    inline): unknown *or another workspace's* → `404 {code: "VENDOR_NOT_FOUND",
    vendor_id}`, the create route's own precedent and shape. Nothing is written,
    versioned or audited, and the foreign name never appears in the response.
  - **Order of checks in `patch_order`:** `NOT_FOUND` → `ORDER_LOCKED` (a frozen
    order answers its state first, whatever the values) → the two reference checks
    → `FIELD_CONFLICT` → write. A `{status: bad, notes: …}` PATCH is refused
    whole: nothing half-applied.
  - `OrderOut` is **unchanged** (`status: str`, `priority: str`): narrowing a
    *response* type would turn any legacy row holding an unexpected value into a
    500 on read, the exact failure this removes on the write side.
- **The `Literal`s are hand-kept copies of the DB CHECKs**, like `FROZEN_STATUSES`
  and the web's `STATUSES`. Unlike those they are **pinned**:
  `test_the_accepted_statuses_are_exactly_the_databases` /
  `..._priorities_...` read the CHECK from `pg_constraint` and fail if a migration
  changes one side (the first also asserts `FROZEN_STATUSES` is a subset). **A
  migration that adds a status must update `OrderStatus`, `FROZEN_STATUSES` if it
  should freeze, and `OrdersClient.tsx`'s `STATUSES`** — the first is enforced by a
  test, the web copy is not.
- **Web.** `lib/orders-types.ts`'s `PatchOrderIn`: `vendor_id`, `description`,
  `category`, `status`, `priority` lost their `| null`, so the *type* documents
  what the API refuses. It is documentation only: `patchField` in
  `OrdersClient.tsx` takes `value: unknown`, so the compiler cannot catch a null
  sent through it. No UI change: the selects can only send valid values, and any
  other failure already reads "Save failed (422)".
- **Tests** (`test_order_routes.py`, 46 new). DB-parity for status and priority;
  all nine statuses and all six priorities accepted; seven bad statuses and six
  bad priorities each a 422 that names the field and writes **nothing** (values,
  `field_versions`, `updated_at` and the `order.update` audit count unchanged);
  null `status` / `priority` a 422 that leaves the order **and `GET /orders`**
  readable (the poisoned-row regression); null for `vendor_id` / `description` /
  `category` a 422; unknown category a 422 with its code and nothing written, a
  known one accepted, an archived one still accepted; **another workspace's vendor
  refused 404 with the foreign name absent from the body and the order unchanged
  and still listed**, an unknown vendor a 404, a same-workspace vendor still fine;
  a frozen order answering `ORDER_LOCKED` before any reference check; a mixed
  `{status, notes}` PATCH refused whole; an omitted field untouched; create
  refusing an unknown priority / category cleanly and creating nothing. Run
  against the **unfixed source first (stashed): 27 of them fail**, and the 22 that
  pass there are the controls (valid values accepted, omitted fields untouched).
  Verified live over real HTTP against a migrated, seeded stack: every bad case
  above refused with nothing written and `GET /orders` still 200; valid changes
  still 200. (A first live attempt at the vendor case appeared to return 422 — that
  was malformed JSON from a shell variable capturing two lines, not the API; redone
  it showed the hole, which is why the check is worth trusting only when read
  twice.)
- **Known gaps, recorded — same shape, deliberately not fixed here.**
  - **The route commits before the response is validated.** That is *why* a
    response-model failure could poison a row, and it holds for every route in the
    app, not just this one. The five fields above can no longer trigger it here;
    closing the *class* means validating before `commit()`, a cross-cutting change.
    Other nullable columns that a response model types as non-null are worth
    auditing for the same poison. **Audited — see *Null-write audit* below**: one
    more real case (`PATCH /suppliers` `status`) and 32 raw 500s, all fixed; the
    "validate before `commit()`" half was deliberately **not** done.
  - ~~**`create_order` does not validate `project_id`**~~ **Closed — see *Small
    fixes: order `project_id` and the CV `ITEM_NOT_EMPTY` message* below.**
    (Found in review, then measured: `POST /orders` with another workspace's
    `project_id` was a raw 500, and **nothing persisted and nothing leaked** — an
    unvalidated-input 500, not an isolation break. `PatchOrderIn` does not accept
    `project_id` at all, so only create was exposed.)
  - **`PATCH` answers a bad `vendor_id` with `404`** (mirroring `create_order`'s
    `VENDOR_NOT_FOUND`, and what the user was told when asked), while the same
    handler answers an unknown `category` with `422`. A client keying on the bare
    status code cannot tell "vendor missing" from "order missing" — `OrdersClient`'s
    `fieldErrorMessage` maps every 404 to "Order not found". Harmless today because
    the UI has no vendor control, but a wart: on PATCH the path resource *does*
    exist, so `422` would be the tidier code. Left matching `create`.
  - **Reference checks re-validate an unchanged value**, so re-sending an order's
    *current* `vendor_id` / `category` is checked again. Only matters for data
    written through the old hole; the UI sends neither.
  - `CreateOrderIn.vendor_id` / `description` are required by the schema, so they
    have no null hole; `CreateOrderIn.status` does not exist (orders are created
    `Draft`).
  - The **legacy `/procurement/*`** namespace has its own order writes and was not
    touched.
  - An **archived category** can still be assigned (above).

## Small fixes: order `project_id` and the CV `ITEM_NOT_EMPTY` message (no migration) — shipped

> Chosen by the user ("go with the next recommendation tasks" — the first item of the
> recommendation, a small bug-fix change with two items). Both were **already recorded
> here as known gaps** (*Order field validation* and *Lock checks on the other module and
> part writes*) after being found and measured, and neither needed a decision: the fix in
> each case was the behaviour the surrounding code already promised. No migration, no spec
> or plan doc; this section is its written record.

- **`POST /orders` validates an explicit `project_id`.** `orders.queries._project_in_workspace`
  (the sibling of `_vendor_in_workspace`) is checked in `create_order` after the vendor and
  category checks; an unknown **or another workspace's** project answers
  `404 {code: "PROJECT_NOT_FOUND", project_id}` — the create route's own `VENDOR_NOT_FOUND` /
  `ITEM_NOT_FOUND` precedent, so a client sees one shape for "the thing you named is not
  yours". *That the code is a 404 rather than a 422 is the precedent, not a fresh decision.*
  Nothing is created, and the foreign project's name never appears in the response. Not checked,
  because already safe: an item-derived project (resolved through the item's own workspace join)
  and no project at all (Q554's project-less order, which reaches its workspace through its
  vendor). **The check order is now vendor → category → project → item.**
- **The CV wizard's `ITEM_NOT_EMPTY` message now shows.** `CvImportDialog` read
  `e.detail.code`; the body FastAPI sends is `{detail: {code}}` and `cv-fetch.ts` keeps all of it
  on `e.detail`, so the code sits at `e.detail.detail.code` (the shape `lockFromError` already
  reads). One line. It is reachable when the page went stale — someone else added modules after
  the wizard opened, since the Replace checkbox is only offered when the item already has modules.
- **Tests.** `test_order_routes.py` (+5): another workspace's project refused 404 with the foreign
  name absent, nothing created and the list still empty; an unknown project refused; this
  workspace's project still creates; no project and the item-derived project still create; an
  unknown vendor still answers first. **The two refusal tests fail against the unfixed source**
  (they surfaced the raw `IntegrityError`); the other three are controls. `cv_import.spec.ts` (+1)
  mocks the API's exact 409 body and asserts the friendly message appears and `commitCvImport: 409`
  does not — **it fails against the unfixed web code** and passes with the fix.
- **Found while verifying: `cv_import.spec.ts`'s existing test is racy in dev mode** (*hardened since — see *e2e suite repair*; the race itself was never reproduced*).
  It clicks the row's `/items/…` link the instant the row is visible; against a freshly started
  `next dev` the page is not yet hydrated, the click does nothing, and the test times out on the
  URL assertion (a diagnostic run with a 3 s pause before the click navigates fine). The new test
  reads the `href` and `goto`s it, as the lock specs do; the old one was left alone (it fails
  before reaching any code this change touches). e2e was not part of CI when this was written (it is now, advisory — see *e2e in CI*).
- **Known gaps, recorded.** `PATCH /orders/{id}` still answers a bad `vendor_id` with `404` while an
  unknown `category` is a `422` (unchanged, noted under *Order field validation*).

## Approving an order with no cost centre (legacy `/procurement/*`, no migration) — shipped, then superseded

> Chosen by the user ("go for your pick 4xx refusal"), from the two options the
> *POST-body null audit* offered: refuse with a clear 4xx, or skip the budget
> commitment. **Superseded — see *Orders with no cost centre: approve and deliver*
> below**: the `409 NO_COST_CENTRE` this section shipped (#55) was replaced by
> "approve proceeds, no commitment". Kept for what it found and why it was replaced.

- **What it did.** `POST /procurement/approvals/{workflow_id}/decide` with `approve` on an
  order whose `cost_center_id` is NULL answered `409 {code: "NO_COST_CENTRE"}` before writing
  anything (it had been a raw 500: `int(None)` after the decision was recorded). Reject was
  never affected. Tests pinned the refusal; the reject and with-cost-centre tests were controls.
- **Why it was replaced.** The refusal's message told people to "assign a cost centre", and the
  reason for picking it over skipping the commitment was that skipping would leave the budget
  understated. **Both rested on a premise that turned out false: no route can assign a cost
  centre to an existing order** — the legacy `PATCH /procurement/orders/{id}` (`POUpdate`) has no
  `cost_center_id`, and the v1 `orders/` module has none at all — and an order with no cost centre
  (nullable by design since `0031`, Q563) belongs to no cost-centre budget, so there is nothing for
  a skipped commitment to understate. The refusal made such an order impossible to approve through
  this route with no way out. Found while looking at the sibling `deliver` route; the user was
  shown the evidence and chose to revisit.
- **Found while testing — since fixed, see *Legacy order views with no cost centre* below.**
  `v_po_summary` inner-joined `cost_centers`, so a cost-centre-less order was a 404 here.

## Legacy order views with no cost centre (migration `0045`) — shipped

> Chosen by the user ("Go with The v_po_summary LEFT JOIN fix"), the gap *Approving an
> order with no cost centre* recorded as "asked for: no". Nothing in the change was
> under-specified — the join was the bug — so nothing was asked before building; one
> *sibling* bug found on the way was left for a decision (below). No spec or plan doc;
> this section is its written record.

- **What was wrong.** `0031` made `purchase_orders.cost_center_id` nullable (Q563), but
  `v_po_summary` (`0006`, redefined by `0009`) still `JOIN`ed `cost_centers`. Every read in
  `procurement/queries.py` goes through the view, so an order with no cost centre was
  invisible to the legacy namespace: `GET /procurement/orders/{id}` answered **404**, and the
  list, the filters and both approval queues (pending and history) omitted it, although the
  row existed and the order could still be approved (now with no commitment posted — see *Orders with no cost centre: approve and deliver*).
  The seed's one purchase order is such an order.
- **The fix — `0045_po_summary_left_join_cost_centre`.** `cost_centers` becomes a `LEFT JOIN`;
  `cost_center_id`, `cost_center` and `cost_center_code` read **NULL** for such an order.
  The vendor and requester joins are on NOT NULL columns and are unchanged. The migration
  is `CREATE OR REPLACE VIEW`, valid because the output columns, their order and their types
  are identical — nothing depending on the view is dropped. The downgrade restores the
  inner join (verified: upgrade → downgrade → upgrade on a migrated database; the view
  definition flips `JOIN` ↔ `LEFT JOIN`). Only `v_po_summary` changes: `v_orders_due`
  never joined `cost_centers`, and `v_budget_utilisation` reads `cost_centers` itself.
- **Workspace scoping is unchanged.** It resolves through the project-or-vendor join, not
  through the cost centre, so a wider view does not show another workspace's order (pinned).
- **Tests** (`test_procurement_routes.py`, 3 new): an order with no cost centre is a `200`
  from `GET /procurement/orders/{id}` with NULL cost-centre fields and is in the list and the
  pending-approvals queue — **fails at `0044`** (404); an order with a cost centre still names
  it; another workspace's cost-centre-less order stays a 404 and out of the list (both
  controls that pass either way). The earlier helper that read the workflow id from the table
  to dodge this 404 now goes through the same path as a real caller.
- **Found while building — since fixed, see *Orders with no cost centre: approve and deliver*
  below.** `PATCH /procurement/orders/{po_id}/deliver` had the same `int(po["cost_center_id"])`
  the approve route had (a 500 with nothing written), and more besides.
- **Known gaps, recorded.** The legacy `/procurement/*` namespace is still not used by the
  v1 surface, so nothing on the web changed.

## Orders with no cost centre: approve and deliver (legacy `/procurement/*`, no migration) — shipped

> Chosen by the user ("go to fix the second bug of the same family. ask me any question").
> Three things were open, so the user was asked before any code was written; the answers
> below are **settled decisions**, not assumptions. No migration, no spec or plan doc; this
> section is its written record. It **supersedes** the `409 NO_COST_CENTRE` on approve
> (*Approving an order with no cost centre*, #55).

- **The rule (user).** *An order with no cost centre belongs to no cost-centre budget, so it
  neither commits nor spends one.* `0031` made `purchase_orders.cost_center_id` nullable
  (Q563) and **no route can assign one afterwards** (legacy `POUpdate` and the v1 `orders/`
  module both lack the field), so "no cost centre" is a permanent property of such an order,
  not a gap to be filled:
  - **Approve** (`POST /approvals/{id}/decide`) **succeeds**, posts **no** `Commitment` row, and
    the changelog line reads "… (no cost centre — no commitment posted)". Reject is unchanged.
  - **Deliver** (`PATCH /orders/{id}/deliver`) **succeeds**, posts **no** `Expenditure` row, and
    the changelog line reads "… (no cost centre — no expenditure posted)".
  - With a cost centre both behave exactly as before.
  *Why this over a 409 (the user's call, against the recommendation this file previously
  carried):* a refusal would have made such an order impossible to approve or deliver through
  these routes with no way to make it possible, and delivery records a physical fact (the goods
  arrived) that a missing budget entry should not block.
- **`deliver` also needs Approved (user: verify, fix if real — it was).** `mark_delivered`'s
  UPDATE was guarded by `status = 'Approved'`, but the `Expenditure` insert and the "Marked
  Delivered" changelog ran regardless, so delivering a **Draft** order answered `200
  {"status": "Delivered"}`, left the order **Draft**, and posted an `Expenditure` (reproduced
  before the fix: `HTTP 200 | PO STATUS Draft | BUDGET ROWS [('Expenditure', …)]`). The same hole
  made a **second** `deliver` on a Delivered order post a **second** Expenditure. Now
  `queries.mark_delivered` returns `None` when its UPDATE matched no row and the route answers
  **`409 {code: "BAD_STATUS", message}`** with nothing written — the codes-and-409 shape the rest
  of the app uses, rather than this module's older bare-string 400s.
- **Code.** `procurement/routes.py::decide_approval` records the decision first and then posts the
  commitment only when a cost centre exists (the refusal and its early read are gone);
  `mark_delivered` (route) branches on the `None` and on the cost centre; `queries.mark_delivered`
  reads `rowcount`.
- **Tests** (`test_procurement_routes.py`): approving with no cost centre is `200`, ends
  `Approved` / `Approved` with **0** budget rows and the changelog note — *replaces* the
  refusal test; delivering an Approved order posts one `Expenditure` (control, beside its
  `Commitment`); delivering with no cost centre delivers with **0** rows and the note; delivering
  a **Draft** order is a `409 BAD_STATUS` that leaves the order row (status **and** changelog) and
  the budget untouched; delivering **twice** leaves exactly one `Expenditure`; another workspace's
  order is a 404 and stays Approved. **Four fail against the previous routes** (approve-no-cost-
  centre, deliver-no-cost-centre, deliver-Draft, deliver-twice); the rest, and the reject and
  with-cost-centre approve tests, are controls. The Draft reproduction and an approve/deliver
  probe were throwaway and are not in the repo.
- **Known gaps, recorded.**
  - **An order with no cost centre is invisible to cost-centre budget reporting by design**
    (`v_budget_utilisation` reads `cost_centers`); there is no "unallocated spend" view, and
    nothing flags that such an order has no budget line. Whether there should be one is a product
    call, not a bug.
  - **No route assigns a cost centre to an existing order** (above). Not built; it is what would
    make "attach it later, then commit" possible.
  - ~~The legacy `/procurement/*` namespace still does not use the order-status guard.~~
    **Closed — see *Legacy procurement audit* below.**

## Legacy procurement audit (`/procurement/*`, migration `0046`) — shipped

> Chosen by the user ("go for the legacy procurement audit"), the follow-up the orders-with-no-cost-centre
> work kept finding siblings for. Method: the null-write audit's — probe a scratch clone of the seeded
> database, measure before and after, and only then fix. The scope and two policies were asked before any
> code was written; the answers are **settled decisions**: fix **all four groups** below, PATCH `status`
> **"keep it, like the v1 module"**, and a delivery **posts a negative `Release`**. The probe scripts were
> throwaway and are not in the repo. The web app does not call this namespace (grep, and no e2e spec does),
> so no web change was needed.

- **Group 1 — clear defects.**
  - **PO numbers.** `generate_po_number` used `MAX(...) + 1` while the v1 `orders/` module draws from
    `po_number_seq` into the same table, so the two handed out the same number and the v1 create then failed
    on the unique index. Legacy now uses `nextval('po_number_seq')` too (Q564). `0046` advances the sequence
    past the highest `PO-YYYY-NNNN` already in use, because a database holding legacy-made numbers ahead of it
    would keep colliding (found when the first suite run hit `PO-2026-0012`). Nothing is renumbered and the
    sequence is never moved backwards.
  - **Totals.** `POST /orders` and `duplicate` never set `purchase_orders.total_amount` (the MySQL triggers
    were not ported), so every order with lines approved a **$0 Commitment**. Both now call the v1 module's
    `_recompute_total_amount`. `0046` back-fills existing orders with lines and a $0 total; a figure anyone set
    is never overwritten and `updated_at` is left alone. **Budget rows already posted at $0 are not rewritten**
    (append-only ledger).
  - **`cancel`** answered 200 "Cancelled" and logged it for any status with the order unchanged; it is now
    `409 BAD_STATUS` unless the order is Draft, Rejected or Hold.
  - **`decide`** moved the order whatever its status (approving a Cancelled or Delivered order made it Approved
    and posted a commitment); it now needs the order to be Pending (`409 BAD_STATUS`), checked **before** the
    workflow row is touched so a refusal writes nothing. The pending-approvals queue lists Pending orders only.
  - **Paging** (`limit` / `offset` / history `limit`) rejects negatives with 422 (raw 500 before).
  - **Duplicate `line_number`s** in a create body are a 422 (raw unique-violation 500 before).
  - **`duplicate`** now keeps `project_id`, `item_id`, `attributes` and each line's `attributes` /
    `material_table` / `material_id`, which it used to drop.
- **Group 2 — PATCH bypass.** `PATCH /orders/{id}` could jump Draft → Approved (no workflow, no commitment),
  → Delivered (no expenditure) or Approved → Cancelled (commitment left behind), and could overwrite the
  `changelog`. Now, the v1 *Purchase order status guard*'s rule:
  - a **Cancelled / Delivered** order is read-only except `status` (`409 ORDER_LOCKED` with `blocked_fields`;
    a mixed PATCH is refused whole);
  - on any other order `status` is **not writable** here (`409 STATUS_NOT_PATCHABLE`) — it moves through
    submit / decide / deliver / cancel, which post the budget rows;
  - `changelog` is read-only (422). A status change on a frozen order appends `(status X → Y)` to the log.
- **Group 3 — budget double count (migration `0046`).** Approve posts a `Commitment` and deliver an
  `Expenditure`, and nothing took the commitment back, so a delivered $110 order read as $220 in
  `v_budget_utilisation`. `budget_transactions` already allowed a `Release` type nobody used. **Deliver now posts
  a negative `Release`** for the outstanding commitment (`release_commitment`: the sum of the PO's Commitment
  and Release rows, posted only when positive, so a second release is impossible and a partial one is exact),
  and the view sums Commitment + Expenditure + Release. The downgrade restores the two-type view.
- **Group 4 — attachments and hardening.**
  - `uploaded_by` is validated against the caller's workspace (`422`); the listing's name join is
    workspace-scoped for older rows, so a historic foreign id no longer leaks a name.
  - Files get a unique on-disk name (`{uuid}_{name}`): two uploads called `quote.pdf` used to share a path, the
    second replacing the first's bytes and deleting one removing both. Delete keeps a file another row still
    points at (historic shared paths). *(Superseded for new uploads by migration `0047` — they no longer touch
    the local disk; see *Legacy PO attachments in the shared file store*. Rows older than it still use this.)*
  - Uploads are read in 1 MB chunks with the 25 MB `MAX_BYTE_SIZE` cap (`413`) and the file is removed if
    anything fails after it was written. `file_path` is no longer in the listing.
  - **Attachments on a Cancelled / Delivered order are read-only**, upload **and delete** (`409 ORDER_LOCKED`).
    The user named uploads; blocking delete too was a call made while building.
- **Tests** (`test_procurement_routes.py`, ~35 new; the file is 66). The new tests were run against the unfixed
  source (queries / routes / schemas stashed): **36 fail, 30 pass** (the passes are controls). An existing RTO
  filter test PATCHed `status` to stage its data; it now stages through SQL. Migration checked on a scratch
  database: upgrade → downgrade → upgrade, the back-fill, and the sequence jump (12 → 500, never backwards).
- **Known gaps, recorded.**
  - **Reopening a frozen order through `PATCH status` can bypass the workflow and the budget** — that is the
    user-chosen option: e.g. Delivered → Approved → deliver posts a second `Expenditure`, and no commitment is
    posted on reopen.
  - Workflow design left as found: any user with `orderbook:approve` can decide any workflow, the named approver
    need not hold a role that can approve, self-approval is allowed, and a Rejected order cannot be resubmitted.
  - ~~Attachments still go to `./uploads` (CWD-relative), **not** the mounted `uploads` volume, and there is no
    download route.~~ **Closed — see *Legacy PO attachments in the shared file store* below.**
  - The v1 `orders/` module can still set a Pending order's status directly, orphaning its workflow (the
    pending-queue filter hides the effect).
  - The legacy category enum has 6 of the 14 `order_category` keys.
  - Historical Commitment / Expenditure rows posted at $0 remain.

## Legacy PO attachments in the shared file store (`/procurement/*`, migration `0047`) — shipped

> Chosen by the user ("go with the next recommendation task" — the first follow-up I listed: the gap *Legacy
> procurement audit* recorded as "attachments still go to `./uploads`… and there is no download route").
> Two things were open, each asked before any code was written; the answers are **settled decisions**, not
> assumptions: **move to the shared `FileStore` / `file_blob`** (over just pointing `UPLOAD_DIR` at the volume),
> **add a download route**, **new uploads follow the app-wide allowlist**, and **old rows are left alone**
> (no backfill). No spec or plan doc; this section is its written record. The web does not call this
> namespace, so no web change was needed.

- **What was wrong.** `POST /procurement/orders/{id}/attachments` wrote to `UPLOAD_DIR` = `./uploads`, relative
  to the api process's working directory — inside the container's own layer, not the mounted `uploads` volume —
  so a rebuilt container lost every file while the rows stayed. Nothing could read a file back at all (no download
  route), and any type was accepted unchecked.
- **Migration `0047`** — one nullable column, `po_attachments.file_blob_id` → `file_blob`. No `ON DELETE`: a blob is
  never deleted anywhere in this app (no orphan GC). `file_path` stays and is nullable. **Nothing is backfilled**
  (reading the filesystem in a migration is fragile and untestable in CI; most old files are probably already gone).
- **Upload — `procurement/routes.py::upload_attachment`.** Same contract as `POST /files`, which it now shares a
  store with: 25 MB cap (`413`), empty file `400`, magic-byte sniff that must agree with the extension
  (**`415`**), sha256 dedup per workspace. So the accepted types are **PDF, PNG, JPEG, `.skp`, `.cvj`** — an `.xlsx`,
  `.docx` or `.txt` quote is now a `415` where it used to be accepted. *That is a deliberate tightening the user
  chose*; the `attachment_type` field (`File | PDF | Image`) is unchanged and unrelated to the sniff. The bytes go
  through `FileStore.put`, the `file_blob` row is written (with the same `file_blob.create` audit as `/files`), and
  the attachment row points at it with `file_path` NULL. A dedup hit reuses the existing blob and writes no
  bytes. Gated `orderbook:write` (not `shop_dwgs:write`, which `/files` needs). All earlier checks are kept and
  still run **first**: workspace, `uploaded_by` in this workspace (`422`), and the Cancelled / Delivered freeze
  (`409 ORDER_LOCKED`).
  - **Failure cleanup removes only bytes this request wrote.** A deduplicated blob belongs to other rows, so a
    failure after a dedup hit deletes nothing; a failure after a fresh `put` rolls back and deletes the file.
- **Download — `GET /procurement/orders/{po_id}/attachments/{attachment_id}/download`** (new), `orderbook:read`.
  Workspace-scoped through `po_in_workspace`; the blob join is **also** scoped to the caller's workspace
  (`file_blob_id` is a plain FK with no workspace of its own, so a row pointing across workspaces serves nothing —
  `404`). Unknown attachment, attachment on another order, and a file whose bytes are gone are all `404`. A
  frozen order's attachments can still be downloaded (reading is not editing).
  - **Blob-backed rows stream `inline`** with the stored mime and the RFC 8187 dual filename, like `GET /files/{id}`
    — safe because the type was sniffed on the way in.
  - **Legacy rows (no blob) stream from `file_path` if it still exists, always as `attachment`** with
    `X-Content-Type-Options: nosniff` and `no-store`: those files were never sniffed, so the browser must never
    render one (an uploaded `.html` would otherwise run in the app's origin). A missing file or NULL path is `404`.
- **Delete.** A blob-backed attachment deletes its **row only** — the blob is deduplicated, other rows (and other
  modules) may share it, and nothing collects orphans. A legacy row keeps its old behaviour (unlink the file unless
  another row shares the path). `queries.get_attachment` now takes `workspace_id` and returns the blob columns.
- **Removed:** the `UPLOAD_DIR` constant and its `UPLOAD_DIR` env var (nothing else read it). `FILE_STORE_ROOT`
  (`/uploads`, the mounted volume) is the only storage setting.
- **Tests** (`test_procurement_routes.py`, 66 → 83). The `upload_dir` fixture now sets `FILE_STORE_ROOT`, and test
  content is a real PDF header (`b"data"` would now be a 415). New: an upload lands in the store with a blob row and
  NULL `file_path`; identical bytes share one blob across orders; same-name uploads keep their own content; deleting
  a row keeps a blob another row uses; the four refusals (`.xlsx`, `.txt`, extension disagreeing with the bytes,
  empty) leave no row, no blob and no file; a failure after the write removes the bytes, and does **not** when the
  blob is shared; download streams the bytes with the right headers and filename; `404` across workspaces, for a
  foreign workspace's blob, for an unknown id / wrong order, for a gone legacy file, for a gone blob; `403` for a
  group with no `orderbook` grant; a legacy row downloads only as an attachment with `nosniff`; a frozen order can
  still be downloaded from. **15 fail against the unfixed source**; the 12 that pass there are controls (several
  are `404` cases that pass only because the route did not exist). Migration checked on a scratch database: upgrade
  → downgrade → upgrade.
- **Known gaps, recorded.**
  - **Old attachments are not recoverable by this change.** Rows from before `0047` still point at a container-local
    path; where the file is gone the download is a `404` and the row stays in the list.
  - The `/files` upload route is unchanged and still gated `shop_dwgs:write`; a user with `orderbook:write` and no
    `shop_dwgs` grant can attach through this route (which writes the blob itself) but cannot use `/files`.
  - Orphaned blobs from removed attachments stay (no GC), as everywhere else; the 25 MB cap is unchanged.
  - **Not verified in a browser or by e2e** — there is no web surface for this namespace.

## Server-computed `locked` on orders (no migration) — shipped

> Chosen by the user ("go with the next recommendation task") from the suggestion list after the
> `FIELD_CONFLICT` fix — the drift risk *Purchase order status guard* recorded. Nothing in it was
> under-specified, so nothing was asked. **Guarding `Rejected`, which that list paired with it, was
> deliberately dropped, not built:** the status guard's settled decision is that `Rejected` stays editable
> ("it can be fixed and resubmitted"), and reopening that would contradict the user's own answer. No
> migration, no spec or plan doc; this section is its written record.

- **What was wrong.** "Which statuses freeze an order" lived twice: `FROZEN_STATUSES` in Python, which
  enforces it (`409 ORDER_LOCKED`), and a hand-copied constant in `OrdersClient.tsx`, which decided what to
  render. A third frozen status added server-side would have been enforced but not hidden, and nothing
  pinned the two together (unlike `OrderStatus`, which a test checks against the DB CHECK).
- **The fix.** `OrderOut` gained a pydantic `computed_field` **`locked: bool`** — `status in FROZEN_STATUSES`.
  `OrderDetailOut` extends `OrderOut`, so `GET /orders`, `GET /orders/{id}` and every response that returns the
  order (the header PATCH, all three line mutations) carry it; it is computed on serialisation, so there is no
  column, no extra query and nothing to keep in sync. The web's `OrderRow.locked` is read by
  `OrderDetailPanel` in place of the old constant, which is deleted. The API still enforces the rule exactly as
  before; the flag only tells the UI what to render.
- **`FROZEN_STATUSES` moved to `orders/schemas.py`** (beside `OrderOut`), because `queries.py` already
  imports `schemas.py` and the flag needs the set — the other direction would be a circular import.
  `orders.queries` re-imports it under the same name, so `orders.queries.FROZEN_STATUSES`, the legacy
  `procurement` module's re-export of it and the existing test import are unchanged.
- **Tests** (`test_order_routes.py`, 10 new). `locked` is true for exactly `Cancelled` and `Delivered` across
  **all nine statuses**, on both the detail and the list; and it follows a reopen — on the reopening PATCH's own
  response and on a line mutation's. The expected set is written out literally in the test, not read from
  `FROZEN_STATUSES`, so the test can disagree with the code. **All 10 fail against the unfixed source**
  (`KeyError: 'locked'`). 195 pass across the order, legacy-procurement and lock test files; `tsc --noEmit` is clean.
  **Not verified in a browser or by an e2e run** — the stack was not up and no spec covers the frozen banner; the
  UI change is a one-line swap of where `frozen` comes from, with every `setOrder` call fed from an API response
  that carries the flag.
- **Known gaps, recorded.**
  - **`OrdersClient.tsx`'s `STATUSES` (the status select) is still a hand-kept copy** of the DB CHECK; only the
    frozen set was removed.
  - The four handlers in `OrdersClient.tsx` still each repeat the "if locked, refetch and refresh the list"
    block (unchanged).
  - The legacy `/procurement/*` routes do not return `locked` (the web does not call them).

## Generate Orders: per-line selection (Plan V1 §21 follow-up, migration `0048`) — shipped

> Chosen by the user ("go with 1 and 2 and 3", the second item: per-line selection in the
> Generate Orders dialog — *PO Generation from a Won Quote* recorded it as deferred). It
> collided with a rule that section states: generation ran **once per revision**, so ticking
> a subset would leave the unticked lines un-generatable for good. The user was asked before
> any code was written; the answer is a **settled decision**: **allow generating the rest
> later**, tracked per line with a migration — over keeping the once-only rule with a warning
> in the dialog, and over dropping per-line selection. No spec or plan doc; this section is its
> written record. It **supersedes** the once-per-revision rule in *PO Generation from a Won Quote*.

- **Migration `0048`** — `estimate_line.orders_generated_at timestamptz NULL`. A run sets it,
  once and never cleared, on every line it covered (the quote is frozen, so there is no
  legitimate way to order a line twice). `estimate_revision.orders_generated_at` stays but now
  means **the most recent run**; nothing reads it as a guard. **Backfill:** a revision that
  already ran gets the flag on the lines its latest `estimate.generate_orders` audit row names
  (`payload.included_line_ids`), or — with no audit row — on the lines included at Convert (what
  a run with no `include_line_ids` selects); each takes the revision's timestamp. Verified on a
  scratch database holding three revisions — a partial run named in its audit row (only the named
  line flagged), a default run with no audit row (the converted lines flagged, the excluded one not),
  and a revision that never ran (untouched) — then downgrade → upgrade again.
- **Rules** (`estimating/queries.py::_order_selection`, shared by the preview and the run so they
  cannot disagree). The lines a dialog shows: once converted, those included at Convert; before that,
  all of them (what-if). A run with no `include_line_ids` covers every shown line no earlier run
  covered; with ids, exactly those. Refusals, all `409`:
  - **`LINES_ALREADY_GENERATED`** `{line_ids}` — an id an earlier run covered (new);
  - **`ORDERS_ALREADY_GENERATED`** — no `include_line_ids` and every shown line already covered
    (the old once-per-quote answer, kept);
  - **`NO_LINES_SELECTED`** (new) — an empty `include_line_ids`. *Found while building, and measured
    against the old code:* `[]` answered `200` with zero orders, **set the once-only flag**, and the next
    real run was then refused `ORDERS_ALREADY_GENERATED` — a quote locked out with nothing ordered;
  - `UNKNOWN_LINE_IDS` unchanged. An explicit id may still name a line excluded at Convert (unchanged
    behaviour; only the default is restricted).
- **Each run makes its own POs.** A supplier used by two runs gets two draft POs, and quantities are
  consolidated per run, not across runs. ~~A line counts as covered once its run completes, including
  materials returned as `unassigned`~~ **— superseded by *Generate Orders: a line is covered only if something on it
  was ordered* below.**
- **API.** `GET /revisions/{rid}/order-preview` takes repeated `?include_line_ids=` and answers `409`
  with the same codes as the run. The response gained `lines: [{line_id, seq, description, qty, unit,
  orders_generated_at, selected}]` and its groups are computed for exactly the selection; the revision
  detail's `LineOut` gained `included_at_convert` and `orders_generated_at`. Concurrent runs naming the
  same line serialize on the revision lock (`lock_revision_for_update`), so the second sees the first's
  flag instead of making two POs.
- **Web.** `OrderPreviewDialog` lists the quote lines as checkboxes (lines an earlier run covered are
  shown "ordered {date}", disabled and unticked); ticking one **re-asks the server** for the supplier
  groups of that selection — only the newest request may write — and the confirm button sends the ticked
  ids. Nothing ticked disables it and says so. The page's "Generate orders" bar shows while any converted
  line is unordered ("N lines not yet ordered from this quote"); the "Orders generated {time}" note reads
  "last generated" while some remain. `Line` / `OrderPreview` types gained the new fields.
- **Tests.** Ten new in `test_estimating_generate_orders.py`: a partial run covers only its lines and a
  later default run takes the rest (its own PO, 3 boards, no hardware) and a third is
  `ORDERS_ALREADY_GENERATED`; a covered line is refused with nothing created and the other line still
  orderable; an empty selection is refused and leaves the quote orderable; a line whose materials were all
  unassigned still counts as covered *(since reversed — see below)*; the revision timestamp moves each run and each run is audited with its
  own `included_line_ids`; the revision detail carries the per-line flags; the preview lists the lines and
  follows the selection, marks a covered line, and refuses a covered or unknown id like the run does; and
  two real DB sessions on separate threads cannot cover the same line twice. **All ten fail against the
  unfixed estimating source** (with the migration applied); the 15 existing tests pass as controls.
  **Verified in a real browser** against a migrated, seeded stack with a throwaway spec (deleted): two
  quote lines → both ticked and 5 boards consolidated; unticking the island recomputed the groups to 2;
  unticking both disabled the button; one run → "1 line not yet ordered"; the second dialog showed the
  pantry "ordered", unticked and disabled and the island ticked at 3; the second run removed the button;
  exactly two POs existed. `estimating`, `item_project_detail`, `material_take` and `smoke` e2e still pass.
- **No permanent e2e spec when this shipped, and the reason recorded here was wrong.** It said
  `default_supplier_id` (`0029`) "no API route sets", so a spec could not build an orderable quote. A route
  did: `POST /suppliers/{id}/materials` (`suppliers/queries.py::link_material`, Q506). What was missing was any
  **web surface** for it and any **seeded link** — so in the browser every material read as unassigned.
  **Closed by *Catalog supplier link* below**, which also added the permanent spec.
- **Known gaps, recorded.**
  - No way to un-cover a line or to regenerate one (deliberate: the quote is frozen).
  - Two runs for one supplier make two POs; merging them is a manual Orderbook job.
  - ~~Covered-with-unassigned lines (above).~~ **Closed — see *Generate Orders: a line is covered only if something
    on it was ordered*.**
  - A preview or run with a stale selection (a line another tab just covered) answers `409`; the dialog
    shows "Could not refresh the preview" and the next tick retries, but a confirm with a stale selection
    is refused by the run, not pre-empted.
- **Out of scope (deferred):** §21's wider Procurement target (unchanged); per-supplier selection; undoing
  a run.

## Catalog supplier link (Plan V1 §21 follow-up, no migration) — shipped

> Chosen by the user ("Next step: let users link catalog materials to a supplier from the web UI. Ask me
> any questions"), from the gap *Generate Orders: per-line selection* surfaced: Generate Orders groups a
> won quote's materials by `default_supplier_id`, and nothing in the web could set it, so in the browser
> every material came back **unassigned**. My first scope ("web and seed only") was wrong on two counts
> found by reading the code, so four questions were asked before any code was written; the answers are
> **settled decisions**, not assumptions. No migration, no spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **The picker uses the Catalog PATCH, gated `catalog:write`** — over the existing supplier link route
     (`orderbook:write`). One gate for the whole grid and one audit trail
     (`catalog.{type}.update`). Drafter, manager, admin and editor can link; **purchase_officer cannot**
     (catalog read only) and neither can estimator or viewer. `POST /suppliers/{id}/materials` still exists,
     unchanged.
  2. **The free-text `default_supplier` is left untouched** by a pick (Q435). The two columns may disagree.
  3. **One row at a time, plus a Linked / Not linked indicator and filter.** No "match by name" helper.
  4. **`default_supplier_id` only.** `supplier_id` (the second FK on each table) is not touched — nothing
     reads it and it has no defined meaning here.
- **What the code check found.** `GET /catalog/*` never returned either supplier FK (the select list stopped
  at the free text), and the existing link route can only *set* a supplier, never clear one. So the change is
  not web-only: the read side and a clear path needed the API.
- **Backend — `apps/api/app/catalog/`.**
  - `PATCH /catalog/{slug}/{mid}` accepts **`default_supplier_id`** on all six tables
    (`queries.PATCH_ONLY`, so it is writable on PATCH and **not** on create — a `POST` that names it
    ignores it). **An explicit `null` clears the link**, unlike every other field on this route, where
    `exclude_none` drops a null; the route reads `model_fields_set` for this one field. Omitting it
    leaves the link alone.
  - **The supplier must be in the caller's workspace** (`supplier_in_workspace`): unknown, or another
    workspace's, is `422 {code: "UNKNOWN_SUPPLIER", supplier_id}` with nothing written or audited and the
    foreign name never in the response. *A 422 rather than the order routes' 404 `VENDOR_NOT_FOUND`: the
    catalog route's own validation errors are 422 and the path resource does exist.* A supplier's `status`
    is **not** checked (an inactive supplier can be linked, as the existing link route allows).
  - **Reads** (`GET /catalog/{slug}`, `GET /catalog/{slug}/{mid}`, and the PATCH / POST responses) now carry
    `default_supplier_id` and **`default_supplier_name`**. The name is a correlated sub-select scoped to the
    row's own workspace, so a stale cross-workspace id (the column is a plain FK) can never surface another
    workspace's supplier name.
  - Audit payload is the validated body, so a link carries the id and a clear carries an explicit `null`.
- **Web — Catalog grid.** A **Supplier link** column beside the (unchanged) free-text Default supplier:
  a `<select>` for writers (`isWriter`, the web mirror of `catalog:write`) listing the workspace's suppliers
  from `GET /suppliers`, and plain text (or an amber "Not linked") for readers. A header note reads "N of M
  rows have no supplier link — Generate Orders cannot order them" (not shown on the Equipment Hire tab, which
  quotes never use), and a filter (`?link=linked|unlinked`, in the URL, applied client-side) narrows the grid.
  **`GET /suppliers` needs `orderbook:read`, a different grant from the grid's `catalog:write`** — when it fails
  the picker is disabled, the page says so, and a linked row still shows its supplier (the current link is
  kept as an option even when the list did not load). Every default writer role holds both grants; an admin who
  grants one without the other creates the same pairing gap Comments and the QC dashboard document.
  Inactive suppliers are listed with "(inactive)".
- **Seed.** `make seed` creates six suppliers (Laminex Australia, Plyco, Briggs Veneers, Hettich Australia,
  Blum Australia, House of Brass — the names the catalog's free text already used) and links every board and
  hardware row whose `default_supplier` names one, by the same exact case-insensitive match `0029` used, so only
  *unlinked* rows are filled and a hand-made link survives a re-run. The block sits **after every catalog
  insert** (the legacy boards come later than the #7a ones), so **one** run links everything — verified on a fresh
  database. **BM-203 "25mm Stainless 304 Sheet" ("CDK Stone") is deliberately left unlinked** as the demo row.
- **Tests.** `test_catalog_supplier_link.py` (22): unlinked rows read null id and name; link **and clear on each of
  the six tables**; moving a link; omitting it leaves it; the free text is untouched; create cannot set it;
  unknown, other-workspace and non-integer ids refused with nothing written or audited and no foreign name;
  a stale cross-workspace id never leaks a name; another workspace's row is a 404; purchase_officer, viewer and
  estimator refused, editor allowed; link and clear audited with the id; the supplier side
  (`linked_material_count`, `/suppliers/{id}/materials`) sees a catalog link. **17 fail against the unfixed
  source** (5 are controls: 404 and role gates). `tests/e2e/catalog_supplier_link.spec.ts` (6; 7 since *Generate Orders: a line is covered only if something on it was ordered*), run twice back to
  back against a live migrated, seeded stack beside `catalog.spec.ts`: a seeded row shows its supplier, an unlinked
  one is flagged and counted; picking links it, survives a reload and clearing unlinks it (free text untouched);
  the filter narrows, lives in the URL and survives a reload; a viewer reads names with no picker; an unreadable
  supplier list disables the picker and says why; and **a board linked in the grid is ordered from that supplier by
  Generate Orders** — a quote built through the API (customer → estimate → line → part → ten advances → accept →
  convert), the dialog naming Plyco with no "No default supplier" card, one draft PO from Plyco afterwards.
  **All six fail against the unfixed web code.** Every test puts the seed back (BM-203 unlinked; the new board is
  archived); the last one leaves its quote, project and one draft PO behind, so it is re-runnable but not
  side-effect free.
- **Full suite:** 1482 passed, 10 skipped, 1 failed against a real migrated Postgres 16 (the same local-only
  `MEILI_URL` gap `test_search_reindex.py::test_real_reindex_swaps_and_drops_temp` has always had here); `tsc --noEmit`
  is clean. In the e2e run, `search.spec.ts` (two tests, no Meilisearch here) and `cutlist_related_parts.spec.ts`'s
  collapsed-by-default test (3 toggles where it expects 1, live-database state — it fails identically with this change's
  web code stashed) were red for reasons unrelated to this work.
- **Known gaps, recorded.**
  - ~~**Creating a catalog row cannot set the link** (the New dialog and bulk import), and **CV-import "Create new"
    rows start unlinked**~~ **Closed — see *Supplier link at create, bulk import and CV Create new* below.**
  - **A text edit does not move the link**, and neither the other way: changing the free-text Default supplier
    leaves `default_supplier_id` alone, so the two can name different suppliers. By decision (2).
  - ~~**The grid's own free-text clear does not work**: the Default supplier cell sends `null` for an empty value
    and the route drops nulls (`exclude_none`).~~ **Closed — see *Supplier link at create, bulk import and CV
    Create new* below** (the lead-time cell had the identical bug).
  - A supplier link says nothing about price or lead time; those still come from the catalog row.
  - ~~Linking a supplier *after* a run did not re-open the lines that were returned as unassigned.~~ **Closed
    — see *Generate Orders: a line is covered only if something on it was ordered* below** (found reviewing this
    very change: a run with nothing orderable answered 200 and locked the line out).
- **Out of scope (deferred):** linking at create or bulk import; "match by name" suggestions; a supplier page that
  lists and edits its materials (the API exists); the second FK `supplier_id`.

## Generate Orders: a line is covered only if something on it was ordered (no migration) — shipped

> Chosen by the user ("Go with option A") from the fix options I gave after reviewing the *Catalog supplier link*
> PR. The review found that the Catalog link made a latent *Generate Orders: per-line selection* assumption bite
> in practice, and the user picked the smallest fix. No migration, no spec or plan doc; this section is its record.
> It **reverses** the assumption *Generate Orders: per-line selection* recorded ("a line counts as covered once its
> run completes, including materials returned as `unassigned`").

- **What was wrong (reproduced before fixing).** A run stamped every selected line
  `estimate_line.orders_generated_at` whether or not any of its materials became a PO line. For a quote whose only
  material had no supplier, `POST /revisions/{rid}/generate-orders` answered **`200` with `orders_created: 0`** and
  stamped the line; the next run was then `409 ORDERS_ALREADY_GENERATED` — whatever the Catalog said by then. The
  Catalog Supplier link made the natural workflow ("no supplier → link it → generate again") reachable and broken.
- **The rule (`estimating/queries.py::generate_orders`).** A selected line is **covered** when at least one of its
  materials became a PO line, **or it references no catalog material at all** (`_line_material_keys` is empty — a
  labour-only line has nothing to order and must not stay pending forever). A line whose every material lacks a
  supplier is **not stamped** and comes back in the new `GenerateOrdersResultOut.uncovered_line_ids`, so it can be
  generated once a supplier is linked.
  - **`409 NOTHING_ORDERABLE`** `{unassigned_count}` when the run would create **no order at all** but has materials
    with no supplier. It writes nothing: no PO, no line stamp, no revision timestamp, no audit row. (A run over lines
    with no materials at all still answers `200` with 0 orders and covers them — nothing was left to order.)
  - The audit row's `included_line_ids` now means **the lines the run covered** (what migration `0048`'s backfill
    reads for older runs), with `uncovered_line_ids` beside it.
  - ~~**A line with some materials ordered and some not is covered**, and its unassigned remainder is reported in
    `unassigned` to order by hand.~~ **Superseded — see *Generate Orders: a line is ordered whole or held back whole*
    below** (the review found it silently lost the remainder).
- **Web (`EstimateDetailClient.tsx`).** The confirm button was already disabled when no supplier group exists; the
  dialog now says why (`data-testid="order-preview-nothing-orderable"`: link them in the Catalog, the lines stay
  orderable), the amber card reads "order these by hand, or link a supplier in the Catalog and generate again", and the
  result banner adds "N lines were left unordered because none of their materials has a supplier". The page's "N lines
  not yet ordered" counter is now accurate for such lines (it counts lines with no stamp).
- **Tests.** In `test_estimating_generate_orders.py` the test that pinned the old rule
  (`..._still_counts_as_covered`) was replaced by five: a run with nothing orderable is `409 NOTHING_ORDERABLE` and
  writes nothing (the explicit selection answers the same; the preview still offers the line); an all-unassigned line
  stays orderable and **orders in its own PO after the supplier is linked** (and a final run is
  `ORDERS_ALREADY_GENERATED`); a line with some materials ordered is covered and reports the rest; a line with no catalog
  material is covered; the audit row names covered and uncovered lines. **All five fail against the previous source**
  (three of them only on the missing `uncovered_line_ids` key — their behaviour half was already as asserted).
  `tests/e2e/catalog_supplier_link.spec.ts` gained a 7th test, run against a live migrated stack beside the other six:
  an unlinked board on a won, converted quote → the dialog says nothing can be generated and the button is disabled →
  the board is linked to Plyco in the Catalog → the same dialog now offers a Plyco order and generating it makes one draft
  PO from Plyco. (Its API half — and so the old-code failure — is pinned by the pytest above; the live server ran the new code.)
- **Known gaps, recorded.**
  - **A line left uncovered because none of its materials has a supplier keeps the page's "N lines not yet ordered"
    counter and the Generate Orders button visible** until a supplier is linked (a WON quote's lines are frozen, so
    they cannot be edited away). That is the intended signal, but there is **no way to mark such a line "ordered by
    hand" and dismiss it**.
  - **A partly ordered line loses its unassigned remainder** to the by-hand list (above) — option B (per-material state)
    is the complete fix and was not chosen.
  - **The estimator who runs Generate Orders cannot link a supplier** (`catalog:write` is drafter / manager / admin /
    editor); the dialog's message says to link in the Catalog, not who can.
- **Out of scope (deferred):** per-material coverage; ~~an "ordered by hand" dismissal~~ (**built, see *Generate Orders: mark
  a line ordered by hand***); a link-supplier shortcut inside the dialog.

## Generate Orders: a line is ordered whole or held back whole (no migration) — shipped, then superseded by *per-material coverage* below

> Chosen by the user ("Go with your recommendation of fixes to build") after the max-level review of PR #66 listed
> eight findings. This builds #1–#5, #7 and #8; **#6 (the Catalog grid's free-text clear is a no-op) was
> deliberately left alone**, and true per-material coverage ("option B", a migration) is still deferred. No
> migration, no spec or plan doc; this section is its record. It **supersedes** the "partly ordered line is
> covered" rule of *Generate Orders: a line is covered only if something on it was ordered*.

- **The rule (`estimating/queries.py::_build_order_groups`).** A line is ordered **whole or not at all.** A line
  using any material with no default supplier is **held back**: none of its materials are ordered by this run, it is
  not stamped, and it comes back in `uncovered_line_ids`. A line is **covered** when every material it references has
  a supplier — or it references none at all (labour-only). Groups are built from covered lines **only**, so a material
  shared with a held-back line is ordered for the covered lines' quantity alone; when the held line is later
  generated it orders its own share. `unassigned` is the supplier-less materials (of every selected line) that are
  holding lines back. `409 NOTHING_ORDERABLE` still answers a run that would create no order but has such materials.
  *Why not order the assigned part of a mixed line and leave the line pending:* the next run would order that part a
  second time. *Why not count it covered:* the remainder is silently lost (what the review found). Whole-or-nothing is
  the only one of the three that neither loses nor duplicates, without per-material state. **Its cost: a line whose
  board has a supplier but whose hinge has none cannot order the board until the hinge is linked** (or the line is
  left out of the selection). That departs from the "option A" the user chose last round, in the direction of the
  recommendation made after review; it is flagged here and in the PR rather than assumed.
- **Archived-but-linked materials order from their supplier (#2).** `_resolve_order_sources_batch` no longer filters
  `archived_at IS NULL`; it returns an `archived` flag instead. Before, an archived row was treated as missing, so a
  linked material fell to "unassigned" with its stale quote snapshot. An archived row with **no** supplier is still
  unassigned, now with its live SKU. The dialog tags such a line "(archived in catalog)" (`OrderPreviewLineOut.archived`).
  **Consequence for the Catalog grid (#5): archived rows are not disabled in the picker and stay in the "N rows have no
  supplier link" count**, the opposite of what the review first suggested — an archived row's link now matters for
  ordering, so disabling it would be wrong. (The grid hides archived rows unless the Archived filter is on.)
- **Preview and run share the plan.** `order_preview` and `generate_orders` both take
  `(groups, unassigned, covered_ids, held_ids)` from the one function, so they cannot disagree. The preview's source
  lines gained `held_back` (`OrderPreviewSourceLineOut`), shown as a "held back — no supplier" tag on a ticked line.
  `_line_material_keys` and `_collect_order_materials` share `_material_rows` (#8); coverage is derived in the same
  pass that builds the groups.
- **A selection with nothing to order can be confirmed (#3).** The dialog's confirm button was disabled whenever there
  were no supplier groups, so lines that reference no catalog material (labour-only) could never be marked ordered
  and kept the page's "N lines not yet ordered" counter forever. It is now enabled when there are no groups **and** no
  unassigned material, labelled "Mark ticked lines done (nothing to order)". With unassigned materials and no groups it
  stays disabled with the "nothing can be generated yet" note, as before.
- **Result banner (#4).** The old banner said the unassigned materials "need to be ordered by hand" while the same line
  stayed orderable — so ordering by hand and then generating again double-ordered. It now says the lines were **held
  back whole** and to link a supplier and generate again; nothing is "ordered by hand".
- **Shared supplier fetch (#7).** `CreateOrderDialog.tsx` used a private `Supplier` interface and its own
  `/api/suppliers` fetch; it now uses `listSupplierOptions` / `SupplierOption` from `lib/catalog-fetch` /
  `lib/catalog-types` (the Catalog grid's), so the two cannot drift.
- **Tests.** `test_estimating_generate_orders.py` (29 → 33): the "some materials ordered is covered" test was replaced
  by six — a mixed line is held back whole (preview flags it, run is `NOTHING_ORDERABLE`, nothing written); it orders once,
  with all its materials, after the link; a material shared with a held-back line is ordered for the covered line's
  quantity only (3, not 5) and the held line later orders its own 2; an archived linked material still orders and is
  flagged; an archived unlinked material is unassigned with its live SKU. **Four fail against the previous source**
  (the mixed-line, shared-material and two archived tests); the rest are controls. `catalog.spec.ts` passes against a live migrated stack running the new code. `tsc --noEmit` is clean (apart from
  generated `.next/dev` files). `catalog_supplier_link.spec.ts` gained an 8th test for the #3 confirm path (a won, converted quote whose only
  line references no catalog material: no groups, the confirm button enabled and reading "Mark ticked lines done
  (nothing to order)", confirming marks the line covered, the "Orders generated" note shows with no "last", the
  Generate orders bar is gone and no PO exists) — **it fails with the old `ready` condition** (button disabled) and
  passes with the fix; all 8 pass against a live migrated stack.
- **Known gaps, recorded.**
  - **Whole-or-nothing is coarser than the data**: no per-material state, so a line cannot be ordered "board now, hinge
    later". That is option B (a migration), still not built.
  - ~~**There is no "ordered by hand" dismissal** for a held-back line.~~ **Closed — see *Generate Orders: mark a line
    ordered by hand* below.**
  - The estimator who runs Generate Orders still cannot link a supplier (`catalog:write` excludes estimator).
  - ~~**#6 left alone:** the Catalog grid's free-text *Default supplier* cell sends `null` to clear and the route drops
    nulls, so clearing it does nothing.~~ **Closed — see *Supplier link at create, bulk import and CV Create new*.**

## Supplier link at create, bulk import and CV Create new (Plan V1 §21 follow-up, no migration) — shipped

> Chosen by the user ("do 1 now, ask me about 2", from the next-step list after PR #66): the gap *Catalog
> supplier link* recorded as "creating a catalog row cannot set the link". Two things were open, so the user
> was asked before any code was written; the answers are **settled decisions**: bulk import **matches the
> free-text `default_supplier` by name**, and CV import's Create new form **gets an optional picker**. The free-text
> clear fix (#6 of the PR #66 review) rode along because it sits in the same grid and PATCH route. No migration,
> no spec or plan doc; this section is its written record.

- **Why.** Every new catalog row — New dialog, bulk import, CV-import "Create new" — started unlinked, and since a
  quote line using any unlinked material is *held back whole* (*Generate Orders: a line is ordered whole or held
  back whole*), each new material blocked its lines until someone found it in the grid.
- **Backend (`apps/api/app/catalog/`, `app/cv/`).**
  - **`POST /catalog/{slug}`** accepts `default_supplier_id` (`_EnrichmentFields`, all six create schemas;
    `default_supplier_id` joined `ENRICHMENT_INSERT`, so `PATCH_ONLY` is gone — nothing else was PATCH-only). An unknown
    or another workspace's supplier is `422 {code: "UNKNOWN_SUPPLIER", supplier_id}` — the same body PATCH uses
    (`queries.unknown_supplier_detail`, `routes._require_supplier`) — and **nothing is created**. A row created
    without one is unlinked, as before.
  - **Bulk import links by name.** `POST /catalog/{slug}/bulk` matches each row's free-text `default_supplier` against
    this workspace's supplier names, **exact and case-insensitive** (the rule the seed and migration `0029` used,
    `queries.supplier_ids_by_name`). Exactly one match links the row; **no match, or two suppliers sharing the name
    (ambiguous), leaves it unlinked** and the row is reported. The response gained `linked: int` and
    `unlinked: [{row_index, default_supplier, reason}]`. **Only rows that named a supplier are reported** — a row naming
    none has nothing to match. A **`default_supplier_id` in a CSV row is ignored, never trusted** (the id-column option was
    declined: whoever prepares the CSV should not have to look up vendor ids). The free text is kept as typed. The import
    stays all-or-nothing: a failed import links and reports nothing. The audit row carries `linked` and `unlinked` counts.
  - **PATCH clears the free-text fields too (#6).** An explicit `null` now clears `default_supplier`,
    `default_lead_time_days` **and** `default_supplier_id` (`routes._CLEARABLE`, read from `model_fields_set`); every other
    field still drops a null, so `description: null` is still a no-op (it is `NOT NULL`). Omitting a field leaves it alone.
    The grid's lead-time cell sent `null` for an empty value and was equally dead.
  - **CV Create new.** `CvCreateNewResolution.default_supplier_id` (optional) is written by
    `insert_catalog_row_from_create_new`. **A supplier that is not this workspace's is refused `422 UNKNOWN_SUPPLIER` in the
    commit route before anything is written**, so the run stays a `preview` and the same run commits once the supplier is
    dropped (a refusal inside `commit_import` would have marked it `failed`).
- **Web.**
  - **New dialog** (`NewCatalogRowDialog`) gets a **Supplier link** select (default "Not linked"). It reuses the supplier list
    `CatalogClient` already fetches for the grid picker; if that list could not be read (`orderbook:read`) the select is disabled
    and says the row will start unlinked.
  - **Bulk import dialog** shows a result panel after a clean import (`data-testid="bulk-import-result"`): rows created, how
    many were linked, and each row that named a supplier it could not match ("Row 2 'Nobody Ltd' — no supplier has this
    name") so they can be linked in the grid. A hint above the textarea states the matching rule. An import with errors keeps
    the old alert path. `BulkImportResp` gained `linked` / `unlinked`.
  - **CV wizard** (`CvImportDialog` → `UnknownCodeRow`): an optional **Supplier link** select inside the *Create new* form.
    The supplier list is fetched once when the *resolve* phase opens and passed down; unreadable → disabled with a note, the
    import still works. `CvCreateNewResolution` gained `default_supplier_id`.
- **Tests.** `test_catalog_supplier_link.py` (22 → 38): create with a link (and on each of the five simple tables), unlinked by
  default, an unknown / foreign supplier refused with nothing created and no foreign name; bulk — a match links (case-insensitive,
  free text kept), no match is reported, a name two suppliers share is never linked, another workspace's supplier never matches, a
  `default_supplier_id` in a row is ignored, a failed import links nothing; PATCH null clears the free-text supplier and lead time,
  omitting leaves them, a null on a `NOT NULL` field is a no-op. `test_cv_routes.py` (+3): a create-new row can be linked, one without a
  supplier stays unlinked, a foreign / unknown supplier is a 422 that leaves the run a preview and the same run then commits.
  The test that pinned "creating a row cannot set the link" was replaced. **16 of the new backend cases fail against the previous
  source** (the rest are controls). `catalog_supplier_link.spec.ts` (8 → 11): the New dialog links at once; bulk import reports
  "1 linked" and lists `Row 2 … Nobody Ltd` and the rows end up linked / unlinked as reported; a CV import's Create new row is linked to
  Plyco. **All three fail against the previous web code** and pass with it; all 11 pass against a live migrated stack. Each test archives
  what it created (the CV test also deletes its `cv_material_mapping`), and the CV test shares `JO-TP01` with the other CV specs
  (tick Replace if offered, as they do). `tsc --noEmit` is clean.
- **Estimators and suppliers — built; see *Link a supplier from Generate Orders* below.**
- **Known gaps, recorded.**
  - **Bulk import matches only exact names** (any case). "Plyco Pty Ltd" against a supplier named "Plyco" is reported unlinked and
    must be linked in the grid; there is no fuzzy matching, by decision.
  - A supplier that is inactive can still be linked at create (as with PATCH).
  - The New dialog's free-text *Default supplier* and the picker are independent, so they can disagree (by the earlier decision).
  - Bulk-import result is shown only after a clean import; a failed one still uses the alert listing the error count.

## Link a supplier from Generate Orders (Plan V1 §21 follow-up, no migration) — shipped

> Chosen by the user: the "estimators and suppliers" item of the next-step list. The estimator (who runs Generate
> Orders) could not clear the "no supplier" warning because `catalog:write` excludes them, and the existing link route
> needs `orderbook:write`, which they lack too. The user was asked and chose a **shortcut in the dialog** over granting
> `catalog:write`; asked the follow-up the shortcut raised (it needed some route an estimator may call), the user chose
> **the narrower route** — a new estimating endpoint — over granting `orderbook:write`. **Settled decisions.** No
> migration, no spec or plan doc; this section is its written record.

- **`POST /revisions/{rid}/link-supplier`** (`estimating/routes.py`, `queries.link_material_supplier`), gated
  **`estimating:approve`** — the dialog's own gate (admin / manager / estimator), nothing wider. Body
  `{material_type, material_id, supplier_id}`, `204` on success. **What makes it narrow** (each pinned by a test):
  - it only touches a catalog row that **this revision's parts or hardware reference** (`404 MATERIAL_NOT_IN_REVISION`
    otherwise), so it is not a general catalog write;
  - it only links a row whose `default_supplier_id` is **NULL** — it **never re-points an existing link**
    (`409 ALREADY_LINKED`, carrying the current supplier). *That second limit is a call made while building, not one the
    user stated:* the shortcut exists to fix "no supplier", and silently re-pointing a material for the whole workspace is
    a bigger power than the user chose to give estimators. Re-pointing stays a Catalog job;
  - the supplier must be this workspace's (`422 UNKNOWN_SUPPLIER`, the same body the Catalog PATCH uses; the foreign
    name never appears); an unknown revision, or another workspace's, is `404`; a material that no longer exists is `404
    MATERIAL_NOT_FOUND`. A refusal writes nothing. The five order-eligible types only (`BOARD / CUSTOM / BENCHTOP /
    HARDWARE / APPLIANCE`; hire is never on a quote).
  - **Audit:** the catalog's own `catalog.{type}.update` event with target `catalog.{type}:{id}` and payload
    `{default_supplier_id, via: "estimate.link_supplier", revision_id}`, so the **catalog row's history shows it** and says
    why. No separate estimate event.
  - The estimator **still cannot edit the catalog**: `PATCH /catalog/...` is a 403 for them (pinned, and checked in the e2e).
- **Web (`OrderPreviewDialog`).** Each material in the amber *No default supplier* card gets a **Link supplier…** select
  (`data-testid="link-supplier-{type}-{id}"`). Picking one calls the route, then **re-asks the server for the current
  selection** (the shared `refreshFor`, which `toggle` now also uses — newest request wins), so the material leaves the
  card, its held-back lines become orderable and the confirm button enables. The supplier list is `listSupplierOptions`
  (`GET /suppliers`, `orderbook:read` — the estimator holds it); unreadable → the selects are disabled with a note. An
  `ALREADY_LINKED` / `UNKNOWN_SUPPLIER` / other failure shows a message and the preview is refreshed anyway. The card and
  "nothing can be generated yet" copy now say "link a supplier here (or in the Catalog)".
- **Tests.** `test_estimating_generate_orders.py` (33 → 44): an estimator links an unassigned material and then orders it
  (preview shows nothing unassigned, no held-back line, one order); the link is audited as `catalog.board.update` naming the
  revision; a material the revision does not use is `404` and unchanged; an existing link is never re-pointed (`409`, unchanged);
  an unknown or another workspace's supplier is `422` and writes nothing; another workspace's revision is `404`; `viewer`,
  `drafter` and `purchase_officer` are `403`; an estimator still cannot PATCH the catalog; hardware works too. The route is
  new, so all of them fail against the previous source. `catalog_supplier_link.spec.ts` (11 → 12): **as the seeded
  estimator** (`kai.ngata@hartwood.test`), against a quote and an unlinked board set up by the manager — a catalog PATCH is a
  403; the dialog says nothing can be generated; picking Plyco in the card clears that, shows a Plyco group and enables
  confirm; generating makes one draft PO from Plyco. **It fails without the dialog change** and passes with it; all 12 pass
  against a live migrated stack. `tsc --noEmit` is clean.
- **Known gaps, recorded.**
  - **No unlink and no re-point from the dialog** (above). A material with a wrong supplier is fixed in the Catalog, by someone
    with `catalog:write`.
  - A drafter cannot use it (no `estimating:approve`), but a drafter can already link in the Catalog.
  - The picker lists every supplier of the workspace, inactive ones included (as the Catalog grid's does).

## Generate Orders: mark a line ordered by hand (Plan V1 §21 follow-up, migration `0049`) — shipped

> Chosen by the user ("go with the e2e repair, then the 'ordered by hand' questions") — the gap *Generate Orders: a line is
> ordered whole or held back whole* recorded as "no way to mark such a line ordered by hand and dismiss it". It needed four
> decisions the code could not make, so the user was asked before any code was written; the answers are **settled
> decisions**, not assumptions — each the recommended option: **new columns on the line** (not a reuse of
> `orders_generated_at`), **the same gate as Generate Orders** (`estimating:approve`), **a required note**, and **an audited
> undo**. No spec or plan doc; this section is its written record.

- **Why a held-back line needed a way out.** A line holding a supplier-less material is held back whole and stays in the quote's
  "N lines not yet ordered" count — correct while it is still to be ordered, a dead end once the PM ordered it outside the system.
  The only coverage flag was `estimate_line.orders_generated_at`, and nothing could say "this one is done".
- **Migration `0049`** — `estimate_line.orders_dismissed_at`, `orders_dismissed_by` (FK `app_user`, `ON DELETE SET NULL`) and
  `orders_dismissed_reason`. **`orders_generated_at` is not reused**: it means "a run made POs for this line", and `0048`'s backfill
  and the `estimate.generate_orders` audit rows read it as exactly that. Three CHECKs make the rules the database's, not
  the application's: the time and the reason come together (`ck_estimate_line_dismissal_complete`), the reason is 1–500
  characters once trimmed, and **a line is never both covered and dismissed** (`ck_estimate_line_covered_xor_dismissed`).
  Up → down → up verified.
- **The rule.** A line is *pending* when no run covered it **and** it is not dismissed (`queries._line_pending`). Pending lines are the
  default selection; a dismissed line is **not** selected by default, and naming one by id is `409 LINES_DISMISSED {line_ids}` —
  the sibling of `LINES_ALREADY_GENERATED`, for the preview and the run alike. With nothing pending, a default run answers
  `409 ORDERS_ALREADY_GENERATED` (its meaning is now "nothing left to order", covered or dismissed). A dismissed line contributes
  nothing to the groups, so the material it alone held `unassigned` stops being reported.
- **Endpoints**, both `estimating:approve`, both lock the revision row (so they serialise with a Generate Orders run):
  - `POST /revisions/{rid}/lines/{lid}/order-dismissal` `{reason}` → `204`. Allowed for **any pending line handed over at Convert**,
    held back or not (a PM may order any line by hand). Refusals: `404 NOT_FOUND` (revision), `404 LINE_NOT_FOUND` (not on this
    revision), `409 NOT_CONVERTED`, `409 LINE_NOT_IN_HANDOVER` (excluded at Convert — no Joinery Item, never shown),
    `409 ALREADY_GENERATED`, `409 ALREADY_DISMISSED`; an empty, blank or over-500-character reason is `422`. The reason is trimmed.
  - `DELETE` the same path → `204`; the line is pending again. `409 NOT_DISMISSED` otherwise. Safe against ordering twice because
    the system never ordered the line.
  - Audit `estimate.order_dismiss` (`revision_id`, `line_id`, `reason`) and `estimate.order_undismiss` (`previous_reason`).
  - `LineOut` and the order-preview's source lines gained `orders_dismissed_at`, `orders_dismissed_reason` and
    `orders_dismissed_by_name` (a join on `app_user`, in the caller's own workspace).
- **Web (`EstimateDetailClient.tsx`).** In the Generate Orders dialog each pending line has **Ordered by hand…**, which opens a
  one-line form whose Save is disabled until the note is non-blank; a dismissed line reads "ordered by hand {date} by {name} — {reason}",
  is unticked and disabled, and has **Undo**. After either change the dialog re-reads the lines, keeps the PM's own ticks that are
  still valid (an undone line comes back ticked) and re-asks for the groups, and tells the page (`onChanged`). The page's bar counts
  pending lines only, adds "N marked ordered by hand", and **stays visible when nothing is pending but something is dismissed** —
  as "N lines marked ordered by hand." with a **Review lines** button — because otherwise the only way to undo would vanish.
- **Tests.** `test_estimating_order_dismissal.py` (21): a dismissal is recorded (trimmed, who, not a generated order) and a default
  run orders only the rest; a dismissed line cannot be picked by id (run and preview) and creates nothing; everything dismissed leaves
  nothing to generate; **a held-back line can be dismissed and stops blocking the quote**; undo makes the line orderable again; both
  verbs are audited with the reason; a missing / empty / blank / over-long reason is a 422 and writes nothing; not converted, excluded
  at Convert, unknown line, another revision's line, already covered, already dismissed and not dismissed are each refused with their
  code; viewer / drafter / purchase officer get 403 on both verbs and another workspace's revision 404; and the database itself
  refuses covered-and-dismissed and a dismissal with no / a blank / a time-less reason. **19 fail against the previous app code** (the
  2 that pass are the database CHECKs, which need only the migration). `catalog_supplier_link.spec.ts` (12 → 13): a held-back line is
  marked ordered by hand (Save disabled until a reason is typed, the line reads as ordered by hand with the reason, nothing left to
  generate), the page's bar says "1 line marked ordered by hand." with **Review lines**, and **Undo** returns it to pending and
  held back — **fails without the web change**, passes with it, run against a fresh database with the new API.
- **Known gaps, recorded.**
  - **The system cannot verify the order happened** — the note is the only record, which is why it is required. A dismissal says
    "this line is done" and nothing reconciles it with the Orderbook.
  - **A dismissal does not link to a PO.** If the order *was* entered in the Orderbook by hand, nothing ties it to the line.
  - Any `estimating:approve` user can undo anyone's dismissal (the user chose the same gate for both).
  - A dismissed line is excluded from generation for good *until* undone; there is no expiry and no list of dismissals beyond the
    dialog and the audit log.
  - Per-material coverage is still not built: a line is ordered, held back or dismissed whole.

## Generate Orders: per-material coverage (Plan V1 §21 follow-up, migration `0051`) — shipped

> Chosen by the user ("Do item 1 first and then Item 3" from the next-task list) — the "per-material order coverage" gap
> *Generate Orders: a line is ordered whole or held back whole* recorded as deferred ("option B"). It changed rules the user had
> settled earlier, so four questions were asked before any code was written; the answers are **settled decisions**, each the
> recommended option: **a new table per line + material**, **order what has a supplier and track the rest**, **"ordered by hand" per
> material with its own required note (the whole-line button stays as a shortcut)**, and **back-fill by copying the line's state to
> each of its materials**. No spec or plan doc; this section is its written record. It **supersedes** the whole-or-nothing rule.

- **Migration `0051`** — `estimate_line_material_order(line_id, material_type, material_id, orders_generated_at,
  orders_dismissed_at/by/reason)`, PK `(line_id, material_type, material_id)`, `ON DELETE CASCADE` from the line. **A row exists only
  for a material that is settled**; no row = pending. CHECKs: exactly one of ordered / dismissed, the dismissal columns travel
  together, reason 1–500 characters. Back-fill: a line already covered gets every distinct material (parts and hardware) marked
  generated with the line's timestamp; a dismissed line gets each dismissed with the line's time, user and reason. Verified on a
  database holding a covered line and a dismissed line (3 rows, right states); upgrade → downgrade → upgrade. The downgrade drops the
  table (the line columns keep the line-level state, so per-material distinctions made afterwards are lost).
- **The rule (`estimating/queries.py::_build_order_groups`).** Each *pending* material on a selected line is ordered when it has a
  default supplier and stays pending when it has none. A line that is part-ordered stays pending and is returned in
  `uncovered_line_ids`; the supplier-less pending materials come back as `unassigned`. A material is never ordered twice: what a run
  ordered is recorded (`orders_generated_at`) and skipped from then on, and quantities are summed over the *pending* (line, material)
  pairs only — a material shared by two lines orders for exactly what is still pending. `409 NOTHING_ORDERABLE` still answers a run
  that would create no order but has supplier-less materials. A line with **no** catalog material (labour only) is covered directly,
  as before.
- **Line columns are derived.** For a line that references catalog materials, `estimate_line.orders_generated_at` /
  `orders_dismissed_*` are re-derived from its material rows after every change (`_refresh_line_state`): both NULL while any material is
  pending; once none is, *generated* (latest time) if any material was ordered by a run, else *dismissed* (latest dismissal's user and
  reason). So every earlier consumer — `LINES_ALREADY_GENERATED`, `LINES_DISMISSED`, the page's "N lines not yet ordered" bar, the audit
  rows — keeps its meaning, and the table is the only thing to write.
- **Endpoints** (`estimating:approve`; both lock the revision row): `POST` / `DELETE
  /revisions/{rid}/lines/{lid}/materials/{material_type}/{material_id}/order-dismissal`. Refusals: `404 NOT_FOUND`, `404 LINE_NOT_FOUND`,
  `404 MATERIAL_NOT_ON_LINE`, `409 NOT_CONVERTED`, `409 LINE_NOT_IN_HANDOVER`, `409 ALREADY_GENERATED`, `409 ALREADY_DISMISSED`,
  `409 NOT_DISMISSED`; a bad reason or `material_type` is `422`. Audit `estimate.order_material_dismiss` / `…_undismiss`; the run's
  `estimate.generate_orders` row gained `materials_ordered` (its `included_line_ids` now means lines the run *finished*).
  The existing **line-level** verbs now act on materials: dismissing a line marks every still-pending material with the one note
  (what a run ordered is left alone); undoing it reopens only the dismissed ones, never one a run ordered.
- **API shape.** `OrderPreviewSourceLineOut.materials[]` (sku, description, qty on that line, `state`
  `pending | generated | dismissed`, who / why / when, `no_supplier`); `held_back` now means "a pending material has no supplier".
- **Web (`EstimateDetailClient.tsx`).** In the Generate Orders dialog a line with more than one material shows a per-material list
  (`order-material-state-…`: "to order", "no supplier", "ordered {date}", "ordered by hand — reason") with **Ordered by hand…** and
  **Undo** per material, reusing the one reason form; the line's own button reads **All by hand…** for such a line. The chip on a
  ticked line reads "some materials have no supplier"; the result banner says how many materials were not ordered.
- **Tests.** `test_estimating_material_coverage.py` (new, 16): one material ordered by hand while the rest orders; all dismissed
  reads as a dismissed line; undo reopens the line; the line button dismisses only what is pending and its undo never reopens a
  generated material; a generated material cannot be dismissed; double dismissal; reason bounds; unknown material / line / revision /
  type; audit rows; the run's `materials_ordered`; `estimating:approve` and workspace isolation; the DB refuses ordered-and-dismissed;
  deleting a line removes its rows. Three tests in `test_estimating_generate_orders.py` that pinned whole-or-nothing were rewritten
  (supplied material orders alone; the unsupplied one orders alone after the link without repeating the first; a shared material orders
  for each line's pending quantity). `tests/e2e/catalog_supplier_link.spec.ts` gained a 14th test, run with the other 13 against a fresh
  migrated, seeded database on a production build: a two-material line shows "no supplier" / "to order", one material is marked by hand
  (Save disabled until a reason), undone and marked again, and generating makes one Plyco PO with the line done.
- **Known gaps, recorded.**
  - **A dismissal still does not link to a PO** and nothing verifies the order happened; the note is the only record (as before).
  - **Per-material dismissal is allowed only on lines handed over at Convert** and while the revision is converted, like the line verb.
  - A material that appears in both a part row and a hardware row of one line is one material (same key) with one state.
  - Any `estimating:approve` user can undo anyone's per-material dismissal.

## PO approval — decisions and open points (October 2026)

Context: the legacy `/procurement/*` approval routes were retired (code in `legacy/procurement_v0/`). On v1 orders any holder of `orderbook:write` can set `status` to `Approved` directly, and no route checks `orderbook:approve`. Plan V1 says nothing about PO approval beyond configurable thresholds for price-source evidence.

**Step 1 — built.** The home dashboard's `pending_approvals` tile counts orders with `status = 'Pending'` (workspace-scoped) and links to `/orderbook?status=Pending`. It used to count `approval_workflows` rows, which nothing writes now, and its old link `?filter=pending_approvals` was never read by the Orderbook page. The `overdue` and `this_week` tiles still link with `?filter=…`, which the page also ignores (not changed).

**Decided by the product owner (answers to the design questions):**
- No real data in `approval_workflows`, so no data to preserve there (the legacy tables themselves stay, Q435).
- Approvers: drafter, purchase officer and manager.
- Only some orders need approval: those **above an amount**, or those the **project manager flags** as special. Everything else skips approval.
- **One approval is enough** (no chain).
- **Budget commitments must be tied to approval.**

**Open — needs an answer before step 2 (Rule Zero):**
- The threshold: how much, per workspace or global, and who can change it.
- How the PM flags an order or item as needing approval (a flag on the order, on the item, or on the line).
- Cost centres: the `cost_centers` / `budget_transactions` tables still exist and are empty; confirm whether an approved order should post a commitment against a cost centre (the old flow did), and what happens for an order with no cost centre.
- The sixth question in the owner's reply was left blank.
- Whether `admin` may approve (the stated list names three roles).


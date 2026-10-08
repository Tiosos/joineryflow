# Cutlist Search Material Take

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## Cutlist + related parts + Orderbook (sub-project #10)

> **Plan V1 #10** — selected by Q437, widened by Q542 to take the whole
> Orderbook with it. Plan + per-task verification notes:
> `docs/archive/plans/2026-09-18-cutlist-related-parts-orderbook.md`.
> Every binding rule traces to a numbered answer in
> `docs/plan-v1/OPEN-QUESTIONS.md`; Q552–Q573 were raised *while building*,
> each where a document and the code disagreed.

Seven migrations, `0026`–`0032`. The A-series (`0026`–`0029`) shipped as
schema-only ahead of any code; `0030`–`0032` were not reserved up front —
the Shop Floor re-key, the order schema and the Controlled Lock each needed one.

**No RBAC matrix change** (Q432). Still 7 roles × 11 modules. Cutlist routes
reuse `("list", action)` because Q474 settled that Cutlist *is* the `List`
tab; orders and suppliers reuse `("orderbook", action)`; areas/rooms reuse
`("tracking", action)`.

### Schema

- **`0026_area_room`** — `area` (project-scoped, Q457) + `room` **nested under
  area** (Q552). Composite FK `items (area_id, room_id) → room (area_id,
  room_id)` so an item's room can never drift out of its area. `level` and
  `zone` stay plain columns, not hierarchy levels (Q546).
- **`0027_cutlist`** — `cutlist (cutlist_id, project_id, cutlist_no UNIQUE,
  name, created_by)`, project-scoped rather than carrying `workspace_id`
  (the post-`0014` pattern `shop_drawing` / `sample` use). `items.cutlist_id`
  nullable and single-column, so an item may have none (Q440) and can never
  hold two (Q411). Introduces **`joinery_number_seq`**.
- **`0028_related_parts`** — `items.row_type` (`joinery_item` | `related_part`),
  `items.parent_item_id` self-FK, and a `related_part_type` lookup seeded with
  metal / benchtop / cushion (Q448) so IT can add a fourth without a migration.
  Nesting is **one level only** (Q449), enforced by a generated
  `parent_row_type` column feeding a composite FK — not by application code.
  CHECKs also forbid a related part holding a `cutlist_id` (Q417) and require
  a type key on exactly the related-part rows.
- **`0029_orderbook`** — revives the legacy `/procurement/*` schema as the
  order layer rather than building beside it (Q502). **There is no new `order`
  / `order_line` table and no new `supplier` table**: `purchase_orders` +
  `po_line_items` *are* the order layer (Q553) and `vendors` *is* the supplier
  entity (Q556). Adds `purchase_orders.project_id` (Q554 — workspace is
  derived by joining `projects`, not denormalised), `.item_id`, and `attributes
  jsonb` on both tables (Q503). Drops legacy `inventory` / `inventory_movements`
  / `v_inventory_status` — `board_inventory` (`0025`) wins (Q544). Adds
  `supplier_id` / `default_supplier_id` to all six catalog tables **beside**
  their free text, which Q435 requires keeping.
- **`0030_shop_floor_cutlist`** — re-keys `worker_assignment` and
  `stage_completion_log` to `(cutlist_id, stage_key)`. See the Shop Floor
  section above.
- **`0031_order_categories`** — makes the inherited office-procurement schema
  usable for joinery: `purchase_orders.cost_center_id` becomes nullable
  (Q563), the frozen `category` CHECK becomes an `order_category` lookup
  (Q557) seeded with the six legacy values plus eight joinery ones, and
  **`po_number_seq`** replaces the legacy `MAX(...) + 1` generator (Q564).
- **`0032_item_lock_request`** — the Controlled Lock. See the PM Workbench
  section above.

### Key invariants

- **One number space** (Q541). `joinery_number_seq` feeds Item IDs, cutlist
  numbers **and** related parts, so a six-digit number never means two things.
  Allocate it **inside** the INSERT; never `MAX(num) + 1` (that race is what
  B2a removed). Q540 gave every pre-existing item its own cutlist carrying its
  `num`, so historical numbers survive recognisably — which is also why
  `cutlist_no` carries **no width CHECK**.
- **`item_stages` stays per-item, as a projection** (Q439). Completing a stage
  on a cutlist fans the `done_date` out to every linked item whose own order
  contains that stage — *selectively*, not blanket (Q562), so a
  `painting_req = false` item never receives a PAINTED date from a sibling.
  Undo reverses the whole cutlist (Q446).
- **Late link leaves history blank** (Q539). An item linked to a cutlist that
  has already completed a stage gets **no** backfill; its cell stays empty and
  it catches up at the next completion. `fan_in_stage_undone` handles it for
  free — there is no row to clear.
- **A related part never carries a cutlist number** (Q417) — a DB CHECK, not a
  convention. It shares its **parent's** Group ID (Q416/Q453) and, in Tracking,
  shows its **issued order number** where a cutlist number would be.
- **An order's CUTLIST NO. is the parent's** (Q428), may be blank if the parent
  has none yet (Q429), and is filled in / rewritten automatically when the
  parent gains or changes a cutlist (Q430/Q431) — one function,
  `orders.queries.sync_orders_for_item`, called from the cutlist link/unlink
  paths. It lives in `orders/` because the orders own the column being written.
- **`row_type` filtering is centralised.** `apps/api/app/row_types.py` holds
  the single `joinery_items_only(alias)` definition. Of the 50 SQL call sites
  reading `items`, **35** carry it; the rest are item-scoped by id or
  deliberately want both kinds — B1's note in the plan classifies all 50.
  Add the helper, not a hand-written predicate. Grep finds far fewer than 35
  hits: 16 modules import it and most bind the result to a module constant
  (`_JOINERY_I = joinery_items_only("i")`) interpolated into several queries.
- **Item cost does not roll up** (Q543, deliberate). Orders carry cost;
  nothing aggregates it onto an item yet.

### Backend modules

All mounted at top-level paths from `main.py`.

- `apps/api/app/areas/` — 3 endpoints (`GET /projects/{pid}/areas`,
  `POST /projects/{pid}/areas`, `POST /areas/{aid}/rooms`), gated
  `("tracking", action)` with `require_drafter()` on the writes. Creating a
  duplicate returns 409 **carrying the existing id**, so a racing create just
  selects it.
- `apps/api/app/cutlists/` — 7 endpoints, gated `("list", action)`. Includes
  `POST /cutlists/{cid}/items` / `DELETE .../items/{iid}` for link + unlink.
  `GET /cutlists/{cid}` rolls parts and hardware up **flat across the
  cutlist's items**.
- `apps/api/app/related_parts/` — 7 endpoints. No migration of its own —
  `0028` carries every structural rule; this module turns what a CHECK cannot
  express into clean 409s instead of raw constraint violations.
- `apps/api/app/suppliers/` — 6 endpoints over `vendors`, gated
  `("orderbook", action)`, **workspace-scoped** (the four legacy
  `/procurement/vendors*` routes never were, and `0029`'s `workspace_id NOT
  NULL` had broken their POST — they are retired, Q565).
- `apps/api/app/orders/` — 9 endpoints, gated `("orderbook", action)`, at
  top-level paths and separate from the still-untouched legacy
  `/procurement/*` namespace. `POST /orders` prefills project / location /
  cutlist number from the item rather than asking for them (Q427).
  `GET /orders` is the **workspace-wide** list behind the Orderbook page and
  must stay declared *before* `/orders/{po_id}` so the literal path wins — the
  same ordering caveat `catalog/routes.py` carries. It also returns the Q554
  order that has no project at all (that one reaches its workspace through its
  vendor), which no project page can show.
- **Fixed later.** `add_line()` computed `SELECT COALESCE(MAX(line_number), 0)
  + 1` against `po_line_items` with no lock on the parent `purchase_orders`
  row, racing against `UNIQUE (po_id, line_number)` (`0002`) — and, unlike
  every other mutation in this module, the route had **no** `IntegrityError`
  handling at all, so two concurrent `POST /orders/{po_id}/lines` calls on
  the same order raised a raw 500. `_lock_order_for_update()` (same shape as
  estimating's `lock_revision_for_update()`) now locks the order row before
  the `MAX+1` read, so a concurrent `add_line()` on the same order serializes
  instead of racing. No migration. Pinned by
  `test_concurrent_add_line_serializes_instead_of_duplicating_line_number`
  (`test_orders_line_number_race.py`), confirmed to fail against the pre-fix
  code with a raw `UniqueViolation` on `po_line_items_po_id_line_number_key`.
  (A parallel-looking race was suspected in `shop_drawings.add_revision()`'s
  `rev_no` allocation, but turned out **not reachable**: every new revision
  is inserted `status='draft'`, so any two concurrent inserts on the same
  drawing always collide first on the partial unique index
  `uniq_drawing_inflight` — which the route already turns into a clean 409 —
  before the `rev_no` collision could ever surface. Verified by writing the
  same race test there and watching it hit `uniq_drawing_inflight`, not an
  unhandled 500; no code change was needed.)
- Item lock requests live in `apps/api/app/items/` — see PM Workbench above.

### Web

- **`/tracking`** — `ItemsTable` nests related parts under their parent,
  **collapsed by default** (Q420–Q422), with an **empty stage-strip area** for
  them (Q419 — scoped to the date columns only; their other columns still
  render). The leftmost column shows a cutlist number for an item and an
  issued order number for a related part (Q417), and a **seventh column-set
  `O/BOOK`** (Q570) shows Order # / Supplier / Status / ETA. **Create Order**
  opens the one generic form plus key/value `attributes` rows (Q426, Q503).
- **`/orderbook`** — two tabs since E2. **Orders** (default) reads
  `purchase_orders` and honours `?order=<po_number>` by selecting the row,
  scrolling it into view and opening its detail panel — the "locate the order"
  half of Q418. **Delivery queue** is #4's supplier-grouped procurement-batch
  queue, kept rather than replaced because Q504 leaves batches beneath orders
  as the allocation mechanism. Money and quantity arrive as **JSON strings**
  (Pydantic `Decimal`), not numbers — `lib/orders-types.ts` records that;
  typing them `number` compiles and then throws `toFixed is not a function`.
- **`/list`** — now the **Cutlist module workspace** (Q474), not a mirror of
  Tracking's item grid. `CutlistClient` lists a project's cutlists and opens
  one into Items / Parts / Hardware panes. Opens as a `target="_blank"` tab
  (Q545) and is deep-linkable (Q478).
- **Item editor** — `AreaRoomPicker` replaces the free-text Area/Room fields,
  with inline `+ New…` creation from the selector. A move is audited (Q458),
  and moving area clears a room that would be orphaned.
- **Project Details modal** — gains a `Project Stats` tab. Cars / OH&S and
  Scope are **omitted pending Q550 / Q572**, not stubbed.

### Known gaps

- **Fixed later.** The item editor's own hardware query (`hardware_lines/
  queries.py::list_catalog` + `list_source_catalog`) used to read the catalog
  `supplier` column alone, rendering "—" on every row since `0017` put the
  real value in `default_supplier`. Now `COALESCE`s both, same as the cutlist
  rollup already did (`vendor` for `custom_made`), pinned by
  `test_catalog_supplier_falls_back_to_default_supplier` and
  `test_source_catalog_supplier_falls_back_to_default_supplier`.
- Q508's Hard / Approval lock types and Q511 / Q512 have no home yet.
- **E3 is the one task of #10 left open** — migrating a copy of the customer's
  real pilot data (Q436) to confirm Q540's number preservation. It is blocked
  on data that has not been supplied, not on work.
- `apps/web/components/pm/TrackingGrid.tsx` is **dead code**: #9a replaced it
  with `ItemsTable` (`b910ab1`) and nothing renders it. Left in place per §3
  (mention unrelated dead code, do not delete it) — but do not read it as the
  Tracking grid, because it is not.

> **Fixed during E2, recorded because the shape recurs.** #9a's Tracking
> overhaul dropped the **availability chip** when `ItemsTable` replaced
> `TrackingGrid`, and with it the *only* entry point to the
> `AvailabilityDrawer` — `TrackingClient.setDrawerItemId` was left being called
> with `null` and nothing else, so a documented #4 feature was reachable only
> by hand-typing `?drawer=item-availability&itemId=N`. Nobody noticed because
> the e2e spec covering it had been failing on an unrelated login assertion
> since the same batch. **A failing or skipped spec is not coverage**; when one
> goes red for a trivial-looking reason, check what it stopped guarding.

### Seed

`make seed` gives **every** seeded Joinery Item an `area` + `room` and its own
cutlist numbered as itself — 8 areas and 13 rooms across the two demo projects
(6 and 9 of them on ALF-001). On ALF-001 it then adds cutlist **297830
"SS Bench run (shared)"** carrying two items with one `DOWN` completion fanned
out to both, plus a third item linked *afterwards* whose `DOWN` cell stays
blank (Q539); two related parts under ST-CT01, one with an issued order and one
without; supplier `Corian Stoneworks`; and one purchase order. Idempotent.

> **The recurring trap, recorded once.** Alembic backfills only touch rows that
> exist when the migration runs — and `make seed` inserts rows *afterwards*.
> This silently broke cutlists and left area/room empty. Every seed block that
> creates an item must now create its cutlist, area and room too. The
> per-item cutlist blocks also re-INSERT on every run (their idempotency guard
> is on `items`, not `cutlist`), so anything that *moves* an item between
> cutlists has to drop the vacated row unconditionally.

## Global Search (sub-project #11)

> Plan V1 §13, selected by Q520. Design: `docs/archive/specs/2026-09-24-search-design.md`;
> plan with per-task verification notes: `docs/archive/plans/2026-09-24-search.md`.
> Every rule traces to Q525 or Q574–Q580.

- **Infrastructure.** Two new compose services: `meili`
  (`getmeili/meilisearch:v1.54.0`, **no host port**, `MEILI_*` keys in `.env`)
  and `search-worker` (the api image running `python -m app.search.worker`,
  **no `--reload`** — restart it after editing `app/search/`). Meili's data
  is disposable: `make reindex` rebuilds it from Postgres.
- **Migration `0033_search_outbox` — the repo's first triggers** (Q578).
  `search_enqueue(kind, id_col)` sits on 15 tables (plus `estimate_revision`,
  which enqueues its estimate) and writes `(entity_type, entity_id)` to
  `search_outbox` in the writer's own transaction. `search_fanout()` sits on
  six parents whose values are embedded in child documents (project code,
  area / room / cutlist names, supplier and customer names) and fires only
  when one of those columns changes. **Any new write path is covered
  automatically; a new *searchable table* needs a trigger in a migration and a
  loader in `documents.py`** — `test_search_reindex.py` fails if the two
  disagree. `TRUNCATE` fires no row triggers, which is why the test suite
  truncates `search_outbox` itself (`conftest.TRUNCATE_TABLES`).
- **The outbox holds identity only.** The worker locks rows `FOR UPDATE SKIP
  LOCKED`, loads each row's *current* state, waits for Meili task success,
  then deletes exactly the ids it locked — so an outage loses nothing and a
  write mid-pass survives. A committed edit is searchable in ~3 s.
- **`app/search/`** — `index.py` (`SearchIndex` protocol, `MeiliIndex` over
  httpx, `FakeIndex` for tests; **`build_filter` is the only producer of
  filter strings** and always carries `workspace_id`), `documents.py` (the
  only module that knows the source schema; one loader per kind), `worker.py`,
  `reindex.py`, `routes.py`.
- **`GET /search?q=&types=&project_id=&include_archived=&limit=&offset=`** —
  `current_user` only; **no RBAC matrix change**. A type is visible when the
  caller's *effective* `read` grant covers its module (`routes.TYPE_MODULE`;
  the Dynamic RBAC engine since *Global Search RBAC sync* below — it was the
  static role matrix when this shipped); unreadable types are
  dropped silently, never 403'd. `503 SEARCH_UNAVAILABLE` on outage, with no
  Postgres fallback. **`GET /search/health`** is gated
  `("it_management","read")` — which the matrix gives **manager** as well as
  admin.
- **Binding search behaviour.** `codes` (item / cutlist / PO / estimate /
  SKU numbers) has **typo tolerance off**, and every query uses
  `matchingStrategy: "all"`: a number one keystroke off, or `EST-2026-0001`
  matching `EST-2026-0002` by dropping a word, would be a *different record*
  (`joinery_number_seq` is shared, Q541).
- **Coverage (Q576 + Q579):** 11 types. Area / room names are searchable
  through item documents, not as results; people are deferred; suppliers are
  indexed with **no link** (no supplier page exists). **Never indexed:**
  secrets, money columns, `vendors.bank_account` / `tax_id` /
  `payment_terms` / `rating`, customer `abn` — pinned by sentinel tests.
- **`archived` (Q580)** mirrors each record's own page: void items, and
  `archived_at` on drawings, samples, customers and catalog rows, plus rejected
  samples and rejected / expired / withdrawn estimates. Soft-deleted items are
  never indexed. Cancelled orders, inactive suppliers and closed projects stay
  visible.
- **Web.** `components/chrome/SearchBox.tsx` in `TopBar` (`/` focuses it),
  `/search?q=&type=&include_archived=` (not a tab), and a Search panel on
  `/it`. The browser still only ever talks to the Next proxy.
- **Fixed after the merge.** Four seeded catalog rows (one each in
  `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire`) had
  **`workspace_id` NULL**, making them invisible on `/catalog` as well as in
  search. `seed/hartwood_joinery.py` now sets `workspace_id` on insert and
  backfills the four rows on any database seeded before the fix.

## Material Take → Material Summary (sub-project #12)

> Plan V1 §19–§20, step 3 of `ALIGNMENT.md` §6. Design:
> `docs/archive/specs/2026-09-24-material-take-design.md`; plan with
> per-task verification notes: `docs/archive/plans/2026-09-24-material-take.md`.
> Every rule traces to Q80, Q495–Q501 or Q581–Q586.

- **Migration `0034_material_take`** — `material_take` (per Joinery Item,
  versioned; partial unique indexes allow **one draft and one approved** per
  item), `material_take_line`, `material_take_review`, `material_summary`,
  `material_summary_line`, `material_summary_source`. Not searchable (no
  `0033` triggers). Source rows **cascade**: items can be hard-deleted, and a
  lost source makes its line read stale.
- **A take is generated, then owned by a person** (Q80). `material_takes/
  generation.py` reads parts + hardware lines and never writes (Q501).
  **Boards are fractional sheets per item** — part area ÷ sheet area, rounded
  *up* to 2 dp — and the summary rounds up **once** over the project (Q586:
  per-item whole sheets overcounted, 6 against 3 on the seed's MDF). Sheet
  size: largest in-stock `board_inventory` size → largest recorded size →
  catalog size → else the line is in **m²**. Hardware sums per material.
  Edging and finishing are **manual** `OTHER` lines (Q584 — no data to
  generate from). Related parts never get a take (Q424).
- **Fixed later.** `generate()` checked for an existing draft with a plain,
  unlocked `SELECT`, then computed `SELECT COALESCE(MAX(version), 0) + 1`,
  then inserted — no lock in between. Unlike `shop_drawings` (where the
  equivalent race is masked by a constraint the route already handles), this
  module's route (`material_takes/routes.py`'s `_call`) catches only the
  app-level `NotFound`/`Conflict` exceptions, not `IntegrityError`, so two
  concurrent `POST /items/{iid}/material-take/generate` calls on an item with
  no existing draft could both pass the check and race on `uniq_take_draft` /
  `UNIQUE(item_id, version)` (`0034`) — the loser got a raw 500 instead of the
  clean `409 DRAFT_EXISTS` the pre-check is meant to give. `generate()` now
  locks the `items` row (`FOR UPDATE`) before the draft-exists check, so a
  concurrent call on the same item serializes instead of racing. No
  migration. Pinned by `test_concurrent_generate_serializes_instead_of_raw_500`
  (`test_material_take_generate_race.py`), confirmed to fail against the
  pre-fix code with a raw `UniqueViolation` on
  `material_take_item_id_version_key`.
- **Draft → approved → superseded.** Only a draft changes; an approved take is
  immutable (`409 TAKE_NOT_DRAFT`) and a change means version `n + 1`. On a
  generated line, material / unit / description are read-only and changing
  `wastage_pct` re-derives `qty`. Every mutation writes `audit_log` **and**
  `item_edit_log` in one transaction.
- **Drift, not drawings (Q583).** A take reads **outdated** when its item's
  live parts / hardware would now *generate* differently — manual lines and a
  person's adjustments never count. The reviewer records No / Partial / Full
  impact; Partial / Full opens the next version. Shop drawings are **not
  linked to items**, so there is no drawing-triggered review and no warning at
  drawing approval (Q497's advisory warning waits for that link).
- **Summary** (`material_summaries/`) — consolidates each item's *current
  approved* take, one line per material (`OTHER` by exact description), keeps
  per-item sources with their take version, lists items with no approved take.
  Computed on read, never stored: **stale** (a source item has a newer
  approved version, or a source vanished), **nest sheets** from the latest
  CutPlan (Q582 — `cut_sheet.material_sku` resolves through the catalog SKU
  **or** `cv_material_mapping`, because the seed's nest is labelled by CV code
  `18-PB`), and read-only **on order / received** from the existing
  `procurement_v1` rollup. **Confirmation is advisory** (Q499) and freezes the
  summary (`409 SUMMARY_CONFIRMED`); rebuild to revise. No ordering from a
  line yet (Q585).
- **RBAC — no matrix change.** Everything is `("list", …)`. Take edits and
  summary build / edits also need `require_drafter()` (drafter / manager /
  admin — §20's PM / Coordinator / Designer); approve and confirm need `list`
  approve; purchase officers read. Workspace-isolated through
  `items → projects.workspace_id`; another workspace gets 404.
- **Web.** Item editor **Material Take** tab (`?tab=take`, `MaterialTakeTab`);
  Procurement page **Summary** tab (`/projects/[id]/procurement?tab=summary`,
  `MaterialSummaryPanel`). Quantities are **strings** in
  `lib/material-take-types.ts` (the `orders-types.ts` lesson).
  **JSX whitespace trap, hit twice here:** text that continues onto a second
  line after a `{…}` expression or an element lost its leading space in the
  build ("4 linesmay be outdated") — build such sentences as one template
  string or add an explicit `{" "}`.
- **Seed.** On ALF-001: approved takes on every item with parts except one
  (left as a draft, so it is listed as missing), one built summary, then one
  item at v2 — so the summary opens with stale lines. Built through the same
  query functions the API uses, so audit / edit-log rows are real. Idempotent.

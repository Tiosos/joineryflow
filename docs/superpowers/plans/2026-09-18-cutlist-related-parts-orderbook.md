# Implementation Plan — Cutlist + Related Parts + Orderbook (Plan V1 #10)

> **Status: in progress.** Migrations `0026`–`0032` applied (`0030`–`0032` were
> not reserved up front — B3, B6 and B7 each needed one). **A1–A4, B1–B7, C1–C6
> and the whole D series are done**; only the E verification series is left.
> Unusually for this repo the checkboxes below *are* being kept current, and
> each finished task carries a `→` note recording what shipped and how it was
> verified — so read them, but treat `CLAUDE.md` as the statement of current
> state.

> **Later change:** seven things in the body below were superseded while
> building. The task notes record each in place; this is the list, so a reader
> does not have to mine them.
>
> 1. **Migrations `0026`–`0029` was not enough.** `0030` (Shop Floor re-key),
>    `0031` (order schema) and `0032` (Controlled Lock) were each needed once
>    the code met the schema.
> 2. **A4's task text was wrong and was corrected in place** — unusually, in
>    the body rather than here, because it described a schema that contradicted
>    the decision record. It said "add `order` + `order_line`" (there is no new
>    order table — `purchase_orders` + `po_line_items` *are* it, **Q553**) and
>    "add `workspace_id` to the 9 legacy procurement tables" (only two lack a
>    join path, **Q555**).
> 3. **B3's `(item_id, 'INST')` half of Q445 is unreachable.** Shop Floor has
>    never been able to hold DEL or INST, so there was nothing to re-key
>    (**Q561**).
> 4. **B1's "50 call sites" overcounted.** Only **35** take the `row_type`
>    filter; the other 15 are item-scoped by id or deliberately want both
>    kinds. The classification became the deliverable.
> 5. **C2 was already satisfied** by B1 and B3 before it was reached — the
>    stage strip reads `item_stages` directly and never joined to cutlist.
> 6. **Conflict 6 was not the pure rename Q455 anticipated.** `items.stage` /
>    `rm_no` / `rm_desc` are **kept and still written** beside the new FKs
>    (Q435), so **D2 does not retire the bare-"stage" terminology pin** — Q456
>    retires it only once the column is gone, and it is not.
> 7. **Scope widened before it started.** Q437 selected "cutlist + related
>    parts"; **Q542** added the whole Orderbook, which is where `0029`, `0031`,
>    `suppliers/` and `orders/` come from.

> **Decision source.** Every binding rule here traces to a numbered answer in
> `docs/plan-v1/OPEN-QUESTIONS.md` (Q432–Q573 — Q552 onward were raised while
> building, each where this plan and the code disagreed) and is mirrored in
> `docs/plan-v1/plan_v1.md` §43. Where this plan and those disagree, the
> questions are right. Where the code and Plan V1's prose disagree, see
> §7 — three departures are deliberate.

**Selected by:** Q437 (cutlist + related parts) widened by Q542 (full Orderbook).
**Gap analysis:** `docs/plan-v1/ALIGNMENT.md` §3.1, §3.2, §6.
**Migrations introduced:** `0026_area_room`, `0027_cutlist`, `0028_related_parts`,
`0029_orderbook`.
**RBAC:** no matrix change. Q432 keeps Create Order with today's `orderbook`
write holders; the `qc` module (Q515) and the permission engine (Q466) are
**later** sub-projects.

---

## 0. Why this shape

Three things that look like separate jobs share one table and one migration
window, so they ship together rather than migrating `items` three times:

- **Area/Room** (Q454/Q455) is a **rename of existing columns**, not new
  structure — `items.stage` → Area, `rm_no`+`rm_desc` → Room. 14 references
  across 7 files.
- **Related parts** (Q447) add `row_type` + a parent FK to the same table.
- **Cutlist** (Q438) repoints what `items.num` means and adds a link column.

The single largest cost is not any of those: it is that **every query reading
`items` must now filter by `row_type`** — measured at **50 SQL call sites
across 13 modules**. Task B1 exists to make that one helper rather than 50
hand-edited predicates.

## 1. Binding decisions this plan implements

| Area | Rule | Source |
| --- | --- | --- |
| Cutlist | First-class entity; one project per cutlist | Q438, Q444 |
| Cutlist number | Six digits, system-allocated, company-wide unique | Q442, Q443 |
| Number space | Item IDs and cutlist numbers share **one** sequence | Q541 |
| Migration | Each existing item gets its own cutlist carrying its `num` | Q540 |
| Stages | `item_stages` **stays per-item**, written by fan-out on completion | Q439 |
| Assignment | `(cutlist_id, stage_key)` for production; `(item_id,'INST')` install | Q445 |
| Undo | Reverses the whole cutlist atomically | Q446 |
| Late link | Item linked to a part-done cutlist leaves earlier stages **blank** | Q539 |
| Tracking | Stage strip repeats on every item row | Q441 |
| Related parts | Rows in `items`, `row_type` + self-FK parent | Q447 |
| Type list | Configurable lookup, seeded metal / benchtop / cushion | Q448 |
| Nesting | One level only | Q449 |
| Status | Related parts carry their own | Q450 |
| Reparenting | Allowed, audited, updates linked orders' cutlist ref | Q452 |
| Group ID | `items.group_id` repurposed; values migrated | Q453 |
| Area / Room | Real per-project entities; `items.stage` → `area` | Q454, Q455, Q457 |
| Level / Zone | Stay attributes, **not** hierarchy levels | Q546 |
| Orders | Commercial layer **above** batches; batches remain allocation | Q504 |
| Coverage | Orders cover **all** procurement, not just related parts | Q507 |
| Legacy | Revive and converge `/procurement/*`; **add workspace scoping** | Q502 |
| Supplier | Real entity; catalog tables repoint | Q506 |
| PO | Real entity — number, supplier, lines, status | Q505 |
| Order form | One generic form + JSONB attributes for type-specific fields | Q503 |
| Inventory | Keep `board_inventory`; **drop** legacy `inventory` tables | Q544 |
| Item cost | **Deferred** — orders carry cost, nothing rolls up yet | Q543 |
| Locking | Item soft-lock becomes a **Controlled Lock** | Q509, Q510 |

## 2. Tasks

### A. Schema (migrations `0026`–`0029`)

- [x] **A1** `0026_area_room` — **done.** `area` (project-scoped, Q457) +
      `room` **nested under area** (Q552, raised while building this); composite
      FK `items (area_id, room_id) → room` so an item's room cannot drift out of
      its area. Distinct `btrim(stage)` → `area`; `DISTINCT ON (area, rm_no)` →
      `room`. `level` + `zone` stay plain columns (Q546). `items.stage` /
      `rm_no` / `rm_desc` **kept and still populated** — dropped in a later
      migration once B/C repoint the 14 references (Q435).
      → **verified** against a real Postgres 16 with migrations `0001`–`0025`
      replayed: full chain clean on a virgin DB (60 tables); 10/10 demo items
      backfilled consistently; old columns intact; the composite FK rejects a
      cross-area room and accepts a same-area one; downgrade drops cleanly and
      leaves `items` untouched; edge cases pass (NULL stage, blank stage, no
      room, one `rm_no` with two spellings, whitespace-padded stage).
- [x] **A2** `0027_cutlist` — **done.** `cutlist` (`cutlist_no` integer UNIQUE,
      `project_id` FK per Q444, `created_by` → `app_user.id`), project-scoped
      rather than carrying `workspace_id`, matching the post-`0014` pattern
      `shop_drawing` / `sample` use. Shared `joinery_number_seq` (Q541) seeded
      above **both** existing watermarks (see B2a). `items.cutlist_id` nullable
      (Q440), single column so an item can never hold two (Q411). Data step:
      one cutlist per existing item carrying its `num` (Q540).
      **No width CHECK on `cutlist_no`** — new numbers are six digits because
      the sequence starts at ≥ 100000, but historical numbers carry across
      verbatim, since Q540 exists precisely so they survive recognisably.
      → **verified**: full chain `0001`–`0027` clean on a virgin DB (61
      tables); 16/16 items linked, every `cutlist_no` equal to its item's `num`
      and in the same project; sharing works (several items on one cutlist);
      `cutlist_id` nullable; duplicate `cutlist_no` rejected; downgrade clean
      with `items` and `items.num` intact; two full down/up round-trips
      idempotent; on an empty DB the sequence starts at a six-digit number.
- [x] **A3** `0028_related_parts` — **done.** `items.row_type`
      (`joinery_item` | `related_part`, default `joinery_item`),
      `items.parent_item_id` self-FK, `related_part_type` lookup seeded with
      metal / benchtop / cushion (Q448). Backfill `group_id = num::text` for
      Joinery Items (Q416 — see note below).
      **Five constraints, all structural:** a related part must have a parent
      and a Joinery Item must not; that parent is itself a Joinery Item
      (composite FK on `(item_id, row_type)` + a generated `parent_row_type`,
      the same technique `0026` uses for room-within-area — without it Q449's
      one-level rule is unenforced); a related part cannot hold a cutlist
      (Q417); a related part must carry a type and a Joinery Item must not;
      unknown types rejected by the lookup FK.
      **Q419 is *not* structural** — "no workflow stages for a related part"
      cannot be a CHECK, because `item_stages` is another table. It is B1's
      filter plus its test, which is why B1 is first.
      → **verified**: full chain `0001`–`0028` clean on a virgin DB (62
      tables); backfill exact on 16/16; happy path inserts; **all seven
      violation attempts rejected by the intended constraint**; parent delete
      cascades to its parts leaving no orphans; downgrade clean with `items`
      intact.

      **Two calls made rather than asked** (Rule Zero — both cheap to reverse,
      flagged rather than blocking):
      1. *Group ID is `num`, not `item_id`.* The task said "own id", which is
         ambiguous. Q416 says the internal number serves as **both** Item ID
         and Group ID, and `num` is the number users see in Tracking, so
         `group_id = num::text`.
      2. *A related part's type is required.* Nothing states whether the
         metal/benchtop/cushion kind is mandatory. A typeless related part has
         no meaning in Q420's nested display, so it is enforced. One CHECK to
         relax if that is wrong.
- [x] **A4** `0029_orderbook` — **done.** Task text **corrected 2026-09-18.** The task as first
      written said "add `order` + `order_line`" and "add `workspace_id` to the
      9 legacy procurement tables". Both contradicted the decision record; see
      **Q553** and **Q555**. What it actually does:
      1. **Reuse the legacy order tables** (Q502 = 1, Q505 = 1, Q553 = 1) —
         `purchase_orders` + `po_line_items` become the order layer. No new
         `order` / `order_line`. All 9 legacy tables are empty and unseeded,
         so reshaping costs no data.
      2. **`project_id` FK on `purchase_orders`** (Q554), nullable; workspace
         is reached through `projects.workspace_id`. `project_name` stays as
         the free-text fallback.
      3. **`workspace_id` on `vendors` and `cost_centers` only** (Q555) — the
         other tables reach workspace through `po_id` or `project_id`.
      4. **JSONB `attributes`** on `purchase_orders` and `po_line_items`
         (Q503).
      5. **`vendors` *is* the supplier entity** (Q506 + Q556) — no new
         `supplier` table. It gains the columns a joinery supplier needs, and
         the 6 catalog tables gain `supplier_id` / `default_supplier_id` FKs to
         it, **beside** the retained free text (Q435 keeps the old columns).
      6. **Port `quantity_reserved`, `reorder_point`, `reorder_quantity`** onto
         `board_inventory`; **drop** legacy `inventory` +
         `inventory_movements` (Q544) — which forces dropping
         `v_inventory_status` (migration `0006`) and not recreating it.
      Also shipped: `purchase_orders.item_id` (Q418 — Tracking shows a related
      part's order number where a cutlist number would go, so the order must
      point back at the row; a plain `items` FK, since Q507 = 2 makes orders
      cover all procurement), and `po_line_items.(material_table, material_id)`
      — the `cv_material_mapping` pair form, because the six catalog tables
      share no key and an FK is therefore impossible.

      **Left open on purpose:** the `category` CHECKs on `vendors` and
      `purchase_orders` still carry the office-procurement taxonomy
      (`IT / Office / Logistics / …`). Widening them is **Q557**, taken with
      the C-series Orderbook UI where the list is rendered — not silently here.

      **Found while building:** `CLAUDE.md` says the six catalog tables share an
      abstract interface including `supplier`. **They do not** —
      `custom_made` calls it `vendor`. Only `default_supplier` (added uniformly
      by `0017`) is genuinely common. The migration carries a per-table column
      map; `CLAUDE.md`'s claim should be corrected when C-series touches it.

      → **verified** against a real Postgres 16 with `0001`–`0028` replayed:
      full chain `0001`–`0029` clean on a virgin DB; `inventory`,
      `inventory_movements` and `v_inventory_status` gone while the other three
      legacy views survive; `cost_centers.code` now unique **per workspace**
      (same code in two workspaces accepted, twice in one rejected);
      `vendors.workspace_id` NOT NULL enforced; `attributes` rejects `[]` and
      defaults to `{}`; the material pair rejects a half-set pair and a bogus
      table name; `qty_reserved` rejects negatives **and** anything above
      `qty_on_hand`; the supplier backfill links a whitespace/case-differing
      name and **refuses to link across workspaces**; deleting a project nulls
      `purchase_orders.project_id` and keeps the order with its
      `project_name` label (Q554). Downgrade → re-upgrade produces a schema
      **byte-identical** to a fresh `0001`–`0029` across all columns,
      constraints and indexes.

### B. Backend

- [x] **B1** — **done.** `apps/api/app/row_types.py` holds the one definition
      (`joinery_items_only(alias)`); **35 of the 50 call sites** carry it. The
      count in the original task assumed all 50 take the filter. They do not —
      three kinds of site exist, and the classification is the deliverable:
      1. **Enumerations and guards → filtered** (35). Lists, counts, rollups,
         and the "does item :iid exist here?" checks that gate a child entity
         a related part cannot have.
      2. **By-id mutation helpers → deliberately unfiltered.** `_item_row` and
         the UPDATE/DELETE paths beneath it, because B4's related-part routes
         (Q450 status, Q452 reparent) reach their rows through them.
         `_item_row` now returns `row_type` so callers decide:
         `patch_lifecycle` refuses a related part (Q419 — no stages) and
         `claim_or_release_lock` refuses it (Q417 — no cutlist to lock).
      3. **The Tracking list → deliberately unfiltered** (Q558), which forced
         an ordering fix; see below.
      Two more left alone on purpose: both `INSERT INTO items` sites (0028
      gave `row_type` a DEFAULT of `joinery_item`, so they already produce
      correct rows) and estimating's `SELECT MAX(num) FROM items`, which
      **must** see every row since `num` is UNIQUE across both kinds — B2a
      replaces that allocator anyway.

      **Three questions this raised, now answered** — Q558 (Tracking list
      returns related parts **inline**, with `row_type` per row), Q559 (the
      drafter editor **404s** on one), Q560 (the availability drawer **404s**).
      Q558 forced a change the task did not anticipate: the list ordered by
      `COALESCE(num, item_id)`, but Q541's shared sequence puts a child's
      number nowhere near its parent's, so children scattered. The list now
      self-joins the parent and orders by `(parent.num, is_related_part, num)`.

      **Found while verifying:** `/public/stats` selected
      `custom_made.supplier`, a column that has never existed (the table names
      it `vendor`), so the endpoint raised `UndefinedColumn` on every call.
      Same root cause as the catalog-interface error corrected in `0029`.
      Fixed, since the query was already being edited here.

      → **verified** against a real Postgres 16 at `0029`: all 33
      predicate-bearing statements in the API tree render and parse; a seeded
      related part is excluded from the project item count, the shop-floor
      board, every patched guard, the item detail and the availability gate,
      while its parent is still found — and the **unpatched** form of the same
      guard still returns it, so the filter is what makes the difference. The
      ordering fix demonstrated on a fixture where the old `ORDER BY` put a
      second parent between the first parent and its own child.
- [x] **B2** — **done.** `apps/api/app/cutlists/` (`schemas` / `queries` /
      `routes`), mounted from `main.py`. **7 endpoints**, gated `("list",
      action)` — Q474 settled that Cutlist *is* the `List` tab, and
      `("list","read")` has gated `cutlist.pdf` since #5b, so **no RBAC matrix
      row is added** (Q432). Reads need `read`; every mutation needs `write`,
      which is drafter+.
      - `GET /projects/{pid}/cutlists` · `GET /cutlists/{cid}` (with its items)
      - `POST /projects/{pid}/cutlists` — `cutlist_no` from
        `nextval('joinery_number_seq')` **inside** the INSERT (Q442/Q443, B2a's
        rule). It is not an input on create *or* patch.
      - `PATCH /cutlists/{cid}` (rename only) · `DELETE /cutlists/{cid}`
      - `POST /cutlists/{cid}/items` · `DELETE /cutlists/{cid}/items/{iid}`

      **Four rules live in the query layer because a CHECK cannot reach another
      table**, each with its own 409 code rather than a raw constraint
      violation (which would surface as a 500):
      | Rule | Code |
      | --- | --- |
      | Q411 — one cutlist per item; the 409 **names the cutlist already held** so the UI can offer to move it | `ITEM_HAS_CUTLIST` |
      | Q444 — a cutlist belongs to one project | `WRONG_PROJECT` |
      | Q417 — a related part gets no cutlist number | `RELATED_PART` |
      | delete with items linked (the FK is ON DELETE SET NULL, so a delete would silently strip the number off every linked item — #4 refuses the same shape for a batch with allocations) | `HAS_ITEMS` |

      Re-linking an item to the cutlist it already holds is **idempotent**, not
      a 409. **Q539 is enforced by absence**: there is deliberately no
      `item_stages` backfill on link, and the query layer says so, so a later
      reader does not "fix" it. Link and unlink write `item_edit_log` as well
      as `audit_log`, per the PM Workbench convention for item-scoped
      mutations.

      → **verified** against a real Postgres 16 at `0029`: all 7 rules
      exercised on fixtures — sharing one cutlist across two items works
      (Q410), each refusal returns its own code, a cross-workspace item is
      404 not 409, and a late-linked item has **0** `item_stages` rows while
      its sibling has 2 (Q539). New `tests/test_cutlist_routes.py` (12 cases);
      **Correction:** recorded as unrunnable here; it was
      not. The suite runs in a Python 3.12 venv against a local Postgres —
      all 12 pass.
- [x] **B2a** — **done.** Both `items.num` allocators now draw from
      `joinery_number_seq`, and `num` is allocated **inside** each INSERT, so
      there is no read-then-insert window left to lose.
      - `items/queries.py`: `nextval('items_item_id_seq') + 100000` →
        `nextval('joinery_number_seq')`. The old form borrowed the PK sequence
        and burned **two** values per insert (the explicit `nextval`, plus the
        column DEFAULT for `item_id`); `item_id` and `num` are now independent.
      - `estimating/queries.py`: the `SELECT COALESCE(MAX(num), 0) + 1` is
        gone entirely — it ran **once per estimate line**, so the fix also
        removes a round-trip per line.
      - `tests/test_shop_floor_routes.py` carried the retired form in a
        fixture; repointed, so no reference to it survives.

      **A third problem this exposed, and fixed.** `make seed` inserts items
      with **fixed** numbers (`290001..`, `297830..`) so it stays idempotent —
      and it runs **after** `make migrate`. `0027` seeds the sequence from
      whatever `items` holds at migrate time, which on a fresh database is
      nothing. Measured: the sequence sat at **100001** while seeded rows
      reached **297988** — ~198k behind the data it is supposed to lead. The
      seed now ends with a monotonic `setval(GREATEST(last_value, MAX(num)))`,
      which is idempotent across re-runs.

      **Two facts worth knowing.** `joinery_number_seq` has no owning table, so
      `TRUNCATE ... RESTART IDENTITY` does **not** reset it — numbers keep
      climbing across the test suite, which is correct for a company-wide
      counter. And `purchase_orders` now appears in `TRUNCATE items CASCADE`'s
      dependent list, because `0029` gave it an `item_id` FK; harmless while
      the legacy tables are empty, but B6 should not seed POs and then let
      another test truncate `items`.

      → **verified** against a real Postgres 16 at `0029`. The bug was
      **reproduced first**: two conversions each reading `MAX(num) + 1` before
      either inserted both picked `297991`, and the second died on
      `items_num_key`. With the fix, the same interleaving allocates `297989`
      and `297990` and both commit; three genuinely overlapping transactions
      all commit with distinct numbers; `create_item` and the estimate
      converter draw from **one** counter (298025-298027 then 298028-298030,
      contiguous), which is Q541's whole point. New regression test
      `tests/test_item_number_allocation.py` (4 cases). **Correction:** this task was recorded as
      unrunnable here; it was not. `pytest` runs fine in a Python 3.12 venv
      against a local Postgres, and the suite was later run in full — these
      four pass.
- [x] **B3** — **done**, via **migration `0030_shop_floor_cutlist`** (the
      A-series reserved only `0026`–`0029`; the re-key needs schema).
      **Scope corrected — see Q561.** The task said "(item_id, 'INST') for
      install", but **Shop Floor has never been able to hold DEL or INST**:
      both tables CHECK `stage_key IN ('DOWN','CNC','EDGED','PAINTED','MADE')`
      since `0020`, neither stage appears in `app/shop_floor/`, and the board
      is five columns. The install half was unbuilt functionality, not a
      re-key. Q561 confirmed **the five production stages only**; Q413's shared
      delivery and Q415's per-item install remain unimplemented, and Q415's
      "Site Installation Manager" still has no matching auth role.

      **The two tables are treated differently, on purpose.**
      `worker_assignment` is mutable current state, so it is fully re-keyed —
      `item_id` dropped, `cutlist_id NOT NULL`. `stage_completion_log` is
      append-only history and Q435 requires data-preserving migrations, so its
      `item_id` is **kept, nullable**, as the provenance of each pre-`0030`
      completion; new rows write `cutlist_id` and leave it NULL.

      **Why the backfill cannot collide:** `0027` minted one cutlist per
      existing item (Q540), so every pre-existing item maps to a distinct
      cutlist and each unique `(item_id, stage_key)` becomes a unique
      `(cutlist_id, stage_key)`. Demonstrated on fixture data — three active
      `DOWN` assignments on three items all survived.

      **Q562 made the fan-out selective.** `painting_req` and
      `paint_after_assembly` are per item, so one cutlist can carry three
      different orders at once. `cutlist_prior_stages_done` unions each item's
      missing priors (one lagging item blocks the whole cutlist) and
      `fan_out_stage_done` writes `done_date` only to items whose **own** order
      contains the stage — a `painting_req = false` item never receives a
      PAINTED date from a painted sibling.

      **Also updated, because the contract changed:** the seed's shop-floor
      block, two existing test files (their fixtures now mint a cutlist per
      item, as `0027` does), the TypeScript types, and the **kiosk**
      (`StationClient.tsx`), which showed an item number and now shows the
      cutlist number plus its item count. The Foreman board is unchanged —
      `BoardCard` is still per item (Q441 repeats the strip on every row); only
      its `assignment` is now shared.

      → **verified** against a real Postgres 16: full `0001`–`0030` chain clean
      on a virgin DB; backfill loses **nothing** (4 assignments → 4, 1 log → 1)
      and the rebuilt partial unique index refuses a second active assignment
      on the same `(cutlist, stage)` while still allowing a cancelled row
      beside an active one; downgrade → re-upgrade is **byte-identical** across
      columns and indexes; all 18 `shop_floor` queries and all 170 test/seed
      statements parse against the re-keyed schema; the selective fan-out,
      the union gate and the cutlist-wide undo were each exercised on the
      three-item mixed-flag fixture. New `tests/test_shop_floor_cutlist.py`
      (6 cases). **Correction:** recorded as unrunnable here; it was not. Running
      the suite found **8 real failures from these changes** — see the E1 entry.
- [x] **B4** — **done.** `apps/api/app/related_parts/`, 7 endpoints. **No
      migration needed** — `0028` already carries every structural rule; this
      module adds the ones a CHECK cannot express and turns the rest into clean
      409s instead of raw constraint violations.
      - **Q423** — the Drafter or PM may create. That is exactly what the
        existing `require_drafter()` allows (`drafter`/`manager`/`admin`), so
        mutations pair it with `("tracking","write")`, the same combination
        every item mutation already uses. No matrix change.
      - **Q449** — a related part cannot be a parent. `0028`'s composite FK
        would refuse it anyway; the route answers `PARENT_IS_RELATED_PART`.
      - **Q450** — its own `status`, an ordinary editable field never copied
        from the parent.
      - **Q419** — **no `item_stages` rows, enforced by absence.** Nothing here
        writes to that table and B1 keeps related parts off every Shop Floor
        surface. The query layer says so, so a later reader does not "fix" it.
      - **Q416/Q453** — `group_id` is the **parent's** Item ID, set on create
        and moved on reparent; never an input.

      **Q452 is why this waited for B6.** Reparenting moves three things at
      once: `parent_item_id`, `group_id`, and — via B6's
      `sync_orders_for_item` — the CUTLIST NO. on every linked supplier order.
      That last part is the "Q431-style order reference updates" Q452 asks for,
      and it could not be built before orders existed. Cross-project moves are
      refused: nothing in Plan V1 contemplates one, and the order already
      carries the old project's name and location.

      Delete is a hard delete — a related part has no cutlist, no stages and no
      production history — but `0029` made `purchase_orders.item_id`
      ON DELETE SET NULL, so **an order already sent to a supplier outlives the
      row it was raised for**, and the audit payload names the orphaned ids.

      → **verified**: `tests/test_related_part_routes.py` (10 cases), run and
      passing, including the full reparent chain — the order's reference
      follows the new parent's cutlist.

      **Found while building:** I assumed `related_part_type` had an
      `archived_at` column (copying `order_category`'s shape from `0031`); it
      does not. Caught immediately by running the tests.
- [x] **B5** — **done.** `apps/api/app/suppliers/`, 6 endpoints gated
      `("orderbook", action)` like orders. **No new table** — `vendors` *is*
      the supplier entity (Q506 + Q556), and `0029` already added
      `supplier_id` / `default_supplier_id` to all six catalog tables beside
      their retained free text.

      **Two live defects found first, one of them mine.**
      1. **`0029` broke `POST /procurement/vendors`.** Q555 added
         `workspace_id NOT NULL` to `vendors`; the legacy insert
         (`procurement/queries.py:662`) never named the column, so the endpoint
         raised NotNullViolation from the moment `0029` applied. **No test
         covered it** — that namespace has 32 endpoints and the suite exercises
         almost none, which is why 592 tests stayed green through the break.
      2. **`0029` also left three `/procurement/inventory*` endpoints reading
         dropped objects.** Q544 said those endpoints "belong to the half of
         the namespace this migration retires" — but A4 never removed them, so
         they had been 500ing on `v_inventory_status` and `inventory_movements`
         ever since.

      **Q565** settles both: the four `/procurement/vendors*` endpoints are
      **retired** in favour of `/suppliers`, and the three `/inventory*` ones
      are removed as Q544 already intended. Nine dead query functions went with
      them. This is the #7a precedent — that sub-project retired `/catalogs/*`
      rather than keep two surfaces over the same tables in step. **The rest of
      the legacy namespace is untouched** (25 endpoints remain).

      What `/suppliers` does that the retired pair never did: **workspace
      isolation on every read and write** (`workspace` appeared *zero* times in
      `procurement/queries.py`), and the Q506 catalog repoint —
      `POST /suppliers/{id}/materials` points a catalog row at a supplier while
      **leaving the free-text name in place** (Q435), so an unmatched name
      stays readable. `equipment_hire` keys on `hire_id`, so the module carries
      a per-table PK map for the same reason `0029` carries a supplier-column
      one.

      → **verified**: `tests/test_supplier_routes.py` (9 cases), run and
      passing, including cross-workspace isolation, the `hire_id` path, and a
      guard that the retired endpoints stay 404.
- [x] **B6** — **done.** `apps/api/app/orders/`, 8 endpoints gated
      `("orderbook", action)` (Q432 — no matrix change), at top-level paths and
      **separate from the untouched legacy `/procurement/*` namespace**.
      Needed **migration `0031`** first: three inherited office-procurement
      requirements blocked *creating* a joinery order at all.
      - **Q563** — `cost_center_id` becomes nullable. It is budget-holder
        accounting; §16 is unscoped and Q543 deferred item cost, so forcing one
        meant inventing a placeholder on every order.
      - **Q557** — resolved here rather than in the C-series, because
        `category` is NOT NULL and so blocks creation, not just rendering. The
        frozen CHECK (`IT / Office / …`) becomes an `order_category` lookup,
        seeded with the six legacy values **plus** eight joinery ones, so §21's
        supplier comparison has something real to group on.
      - **Q564** — PO numbers keep the legacy `PO-{year}-{0000}` format but not
        its generator: `legacy/procurement_api.py:274` does `MAX(...) + 1`, the
        identical race **B2a** removed from `items.num`. A `po_number_seq`
        replaces it, seeded above anything the old format already issued.

      **The Q427→Q431 chain is the substance of this task.** Creating an order
      against a row carries PROJECT / LOCATION / CUTLIST NO. across (Q427); for
      a **related part** the cutlist number comes from its **parent** (Q428),
      since a related part never holds one (Q417); blank is legal (Q429); and
      `sync_orders_for_item` keeps every reference in step — filling blanks
      (Q430) and following a replacement (Q431). Q430 and Q431 are the *same*
      UPDATE; the only extra work Q431 needs is capturing the **previous**
      value, which `UPDATE ... RETURNING` cannot give, so the statement uses a
      `before` CTE and each changed order gets an audit row carrying it.
      The sync lives in `orders/` (it owns the column) and is called from
      `cutlists/` link **and** unlink — the reference follows the item in both
      directions rather than going stale.

      → **verified**: full `0001`–`0031` chain clean; `0031` accepts a joinery
      category and still refuses a bogus one; the allocator yields
      `PO-2026-0001` on a virgin DB and `PO-2026-0043` on one already holding
      `PO-2026-0042`; downgrade leaves columns identical to a fresh `0001`–`0030`.
      New `tests/test_order_routes.py` (10 cases) covering the whole chain —
      **run, and passing**.
- [x] **B7** Item soft-lock → Controlled Lock: a non-owner's save becomes a
      **request requiring approval** instead of succeeding with an
      `item.lock_overridden` audit row (Q509). Item and project scope only
      (Q510).

      → Migration **`0032`** adds `item_lock_request` (the `PatchItemIn` body
      held as jsonb, `pending → approved | rejected`), with
      `uniq_pending_lock_request` on `(item_id, requested_by) WHERE status =
      'pending'` so saving again **revises your own proposal** rather than
      queueing a stale one behind it.

      `PATCH /items/{id}` no longer applies a non-owner's save: it answers
      `409 {code: "LOCK_REQUEST_CREATED", request_id, owner_id, fields}`.
      `GET /items/{id}/lock-requests` lists them;
      `POST /lock-requests/{rid}/{approve,reject}` decides, restricted to the
      **lock owner or a manager/admin** — the same rule
      `claim_or_release_lock` already applies to transferring the lock.
      Approval replays the stored body through the ordinary save path, so a
      field the owner has meanwhile set to the requested value is a silent
      no-op; the edit log credits the **requester**, the audit the
      **approver**. `item.lock_overridden` is retired.

      → **Q566 raised and answered**: B7 covers Q509 and half of Q510.
      **`projects` has no lock column of any kind**, so Q510's project scope is
      read as a ceiling, not a mandate. **Q508**'s Hard and Approval locks and
      **Q511 / Q512** (optimistic concurrency, per-field versioning) have no
      task anywhere in this plan and remain unbuilt.

      → **verified**: `0032` upgrades and downgrades cleanly on the full
      `0001`–`0032` chain. `tests/test_lock_semantics.py` re-cut from 7 cases
      to 14 — the override test is now a *held-request* test — covering revise,
      approve (item changed, requester credited), reject (item untouched),
      manager-decides / bystander-403, double-decide 409, cross-workspace 404
      and the owner's own save still applying. Full suite **608 passed, 1
      skipped**.

### C. Web

- [x] **C1** `ItemsTable` — nest related parts under their parent, collapsed by
      default (Q420–Q422); **empty stage-strip area** for them (Q419); leftmost
      column shows cutlist number for an item, **issued order number** for a
      related part (Q417), linking to Orderbook (Q418).

      → **Q567 raised and answered first**: Q417's "issued" named a state that
      does not exist (`purchase_orders.status` has no `Issued`), so the test is
      **`date_ordered IS NOT NULL`**, and the most recent such order wins since
      `item_id` is not unique on `purchase_orders`. The list query gained a
      `LEFT JOIN LATERAL` serving `issued_order_no` + `issued_order_po_id`;
      **`TrackingItemRow` had no order field at all**, so C1 was not a
      web-only task.

      Web: `ItemsTable` filters and sorts **Joinery Items only** and renders
      each parent's related parts beneath it, so no sort order can separate a
      child from its parent. Disclosure control lives inside the CUTLIST cell
      (no new column, so the header/filter `colSpan` arithmetic is untouched).
      A related part gets **blank** stage cells — not em dashes, which read as
      "recorded but empty" — the type chip beside its description, and no
      editor link or ▶ detail button, because `GET /items/{id}` 404s on it
      (Q559).

      → **Three consumers corrected in the same pass**, all of them wrong the
      moment Q558 put two row kinds in one response: `TrackingMetrics` counted
      related parts in "Items in job" *and* in the installed-percentage
      denominator; `/list` counted them in its "N items" label; and
      `TrackingClient`'s quick filters judged them on stages they can never
      have, orphaning children from a parent that survived the filter.

      → **verified**: 4 new cases in `test_related_part_routes.py` (14 total,
      passing) pin the issued/not-issued boundary, the most-recent rule, that a
      Joinery Item keeps its own number, and the parent-child ordering.
      **`npx tsc --noEmit` is clean across the web app** — which also surfaced
      6 pre-existing errors in `StationClient.tsx` left by **B3**'s re-key
      (`code`, `room_no`, `room_desc` no longer exist on a cutlist-keyed
      `StationCard`); fixed here to show `item_count` instead. Driven in a real
      browser against a seeded DB: collapsed by default, expanding reveals the
      children, `PO-2026-0001` renders and links, the un-issued order's row
      stays blank, and the metric still reads 12. Full suite **612 passed, 1
      skipped**.

      → **Seed bug found and fixed** (it blocked all of this): `make seed` had
      been **broken on a fresh database since B3** — `worker_assignment.cutlist_id`
      is NOT NULL since `0030`, but the seed creates items without cutlists,
      which `0027` only minted for items that existed when it ran. Every
      seeded Joinery Item now gets its own cutlist numbered as itself (Q540),
      and the shop-floor block selects only cutlisted `joinery_item` rows, so a
      re-run cannot pick up a later-seeded item that has none. Verified across
      four consecutive runs.
- [x] **C2** Stage strip repeats on every item row (Q441) — reads `item_stages`
      directly, no join to cutlist.

      → **This task as written was already satisfied** by B1/B3:
      `list_items_for_project` fetches stages in a second query over
      `item_stages` and never joined `cutlist`, and the grid draws all ten
      cells on every row. Nothing to build.

      → **Q568 raised and answered**: the column *labelled* CUTLIST was showing
      `items.num` — the **Item ID**, not the cutlist number. Q540 gave every
      migrated item a cutlist numbered as itself, so the two matched and it
      looked right until a cutlist was genuinely shared, which is the point of
      Q438. Demonstrated on real rows: items 11 and 12 both on cutlist
      `290001`, and item 12's row read `290002`.

      `TrackingItemRow` now carries `cutlist_no` + `cutlist_id`; the CUTLIST
      column renders the shared number (blank when none, per Q440) and the
      far-right **Item ID** column takes over `items.num` (Q541/Q416) in place
      of the internal row key it was showing, keeping the editor link. Sorting
      the CUTLIST header orders by `cutlist_no`; the `Cutlist #` box matches
      either number, since Q541's one sequence means they cannot collide. The
      cutlist number is **plain text** — the workspace it should open is C3.

      → **verified**: 3 new cases in `test_cutlist_routes.py` (15 total,
      passing) pin the shared number against distinct Item IDs, the
      no-cutlist-yet blank, and that two rows on one cutlist still carry
      **different** stage strips when one joined late (Q441 + Q539 together —
      the property that only holds because Tracking reads `item_stages` per
      row). `npx tsc --noEmit` clean. Confirmed in a browser against a real
      shared cutlist: rows 1 and 2 read CUTLIST `290001` with Item IDs
      `290001` and `290002`. Full suite **615 passed, 1 skipped**.
- [x] **C3** `/list` becomes the **Cutlist module workspace** (Q474). Opens as a
      `target="_blank"` tab (Q545), deep-linkable (Q478).

      → `/list` no longer mirrors Tracking's item grid. `CutlistClient` (which
      replaces `ListClient`) lists the project's cutlists — number, name, item
      count, creator — with search, **+ New cutlist** (Q442: the number is
      allocated server-side, never supplied), and a detail panel carrying
      rename, delete, link and unlink. The link picker needs no new endpoint:
      an item holds at most one cutlist (Q411), so the candidates are the
      project's Joinery Items whose `cutlist_id` is null — the column **C2**
      added. Mutations are gated in the UI on `can(me, "list", "write")`,
      mirroring the route's own gate rather than a hardcoded role list.

      → **Q569 raised and answered, in two parts.** (a) `plan_v1.md` §1218
      wants the cutlist details to include *the parts and hardware themselves*,
      so `GET /cutlists/{cid}` now returns `parts[]` and `hardware[]` and the
      panel has three sub-panes. Both are **flat across the cutlist**, each row
      naming its item — several items share one cutlist (Q410) and the sheet is
      cut in one go. (b) C3 named only `/list`, but **Q475** named Tracking,
      Orderbook *and* Cutlist; all three now carry `target="_blank"` with a ↗
      marker, and a tab you are already on still navigates in place.

      → Tracking's cutlist number is now a link, closing what **C2** left
      plain: `plan_v1.md` §1218 says clicking it "opens a separate window
      containing the cutlist details", which Q545 makes a `target="_blank"` tab
      onto `/list?project_id=…&cutlist=…`.

      → **A trap caught by running it**: the hardware roll-up's supplier column
      read "—" on every seeded row, because `0017` put the real value in
      `default_supplier` and left the free-text `supplier` empty. Coalesced,
      with `custom_made`'s `vendor` handled as CLAUDE.md's invariant requires,
      and pinned by a test. **The item editor's own hardware query still reads
      `supplier` alone and shows the same blank** — pre-existing, untouched,
      and now recorded in Q569.

      → **verified**: 5 new cases in `test_cutlist_routes.py` (19 total,
      passing) cover the roll-up spanning two items, the empty cutlist, the
      roll-up following an unlink, and the `default_supplier` fallback.
      `npx tsc --noEmit` clean. Driven in a browser: the tab strip reports
      `target="_blank"` on exactly Tracking, List and Orderbook; clicking
      cutlist `290001` in Tracking opens a new tab at
      `/list?project_id=3&cutlist=1` whose panel is that cutlist; the panes
      read `Items (2) · Parts (6) · Hardware (4)` across both linked items,
      with suppliers resolving. Full suite **619 passed, 1 skipped**.
- [x] **C4** Tracking **O/BOOK subtab** with **Create Order** (Q425) opening the
      generic order form (Q426, Q503).

      → **Q570 raised and answered**: `O/BOOK` is a **seventh column-set** in
      the existing sub-tab strip, not a pane replacing the grid. The row keeps
      its place and its right-hand columns become **ORDER # · SUPPLIER ·
      STATUS · ETA**; the strip carries **Create Order**, shown to the Q432
      write holders via `can(me, "orderbook", "write")`. The legacy mock has
      the six existing sub-tabs and no order tab, so nothing showed the shape.

      → **Q426's screenshots were not needed.** They are not in this repo, but
      **Q503** already settles the form: one generic form with fixed fields
      plus a free `attributes` store for the type-specific ones. Project,
      location and cutlist number are **not inputs** — B6's `_prefill_from_item`
      derives all three from `item_id` (Q427/Q428), taking the cutlist number
      from the parent when the row is a related part. The dialog *shows* what
      will be carried instead of letting it be typed, and offers "No item — a
      project-level order" so Q507's item-less orders can still be raised.

      → **A second order field, deliberately.** `issued_order_no` stays
      issued-only for Q417's reference column (Q567); the O/BOOK columns take
      the latest order in **any** state, because a Draft raised moments ago is
      what the sub-tab is for. Visible in one screenshot: a related part whose
      reference cell reads "—" while its ORDER # reads `PO-2026-0002`.

      → **A C1 bug this exposed and fixed.** C1 blanked a related part's whole
      trailing column block for Q419. Q419 blanks the *workflow-stage* area;
      O/BOOK above all must render for a related part, since an order against
      one is the normal case (Q424). Now scoped to the DATE strip.

      → **verified**: 3 new cases in `test_related_part_routes.py` (17 total,
      passing) pin that a Draft shows in the O/BOOK columns while the reference
      column hides it, that the latest order wins, and the empty case.
      `npx tsc --noEmit` clean. Driven in a browser: the headers read
      `ORDER # · SUPPLIER · STATUS · ETA`, three related-part rows show
      `PO-2026-0001/2/3` with supplier and status, Create Order is present and
      its dialog lists every row plus the project-level option. Full suite
      **622 passed, 1 skipped**.
- [x] **C5** Project Details modal gains `Project Stats` + `Scope` (Q476).
      **Cars and OH&S are omitted** pending Q550.

      → **Project Stats** ships. `legacy/tracking_dashboard.html:850` turns out
      to *be* the window Q408 describes, and its meta tiles map onto real
      `projects` columns — `created_by`, `tg_solid` and `total_line_items` were
      there all along, just never carried by `ProjectOut`.

      → **Q571 raised and answered.** The tab's other two blocks — ADMIN STATS
      and PRODUCTION / INSTALL — are **hours from TGPAY**, an external payroll
      system. Nothing here records hours: no `time_record` table (#8 put one out
      of scope) and `estimate_line_labour` / `workspace_labour_rate` are
      estimating-side *rates*. Both tables render their row labels with **no
      values**, captioned "Data from TGPAY — not integrated", so the gap is
      visible in the product rather than only in a document.

      → **Q572 raised — `Scope` is NOT built, against this task's own text.**
      The task assumed Scope was specified while omitting only Cars and OH&S. It
      is not: the mock shows `SCOPE` as a **tab label with no contents**, and
      `projects` has **no scope column**. That is exactly Q550's position for
      Cars and OH&S, so Scope joins them as customer input. Guessing was
      rejected twice — a free-text column would need re-migrating if Scope is a
      structured list of works, and relabelling `classification` as "Scope"
      would invent a meaning no document gives.

      All three blocked tabs render **disabled with a tooltip naming the
      question**, rather than being hidden: the window's real shape stays
      visible.

      → **verified**: a new case in `test_projects_routes.py` (13 total,
      passing) pins the three tile columns through both `GET /projects/{pid}`
      and the list the Info button actually renders from, and that a fresh
      project leaves them null. `npx tsc --noEmit` clean. Driven in a browser:
      the strip reads `Project stats · Cars [disabled] · OH&S [disabled] ·
      Scope [disabled]`, the tiles show `CREATED BY DAVIDM · TG SOLID ✓ ·
      TOTAL LINE ITEMS 241`, and both hours tables show labels with dashes.
      Full suite **623 passed, 1 skipped**.
- [x] **C6** Area / Room selectors replace the free-text fields; item may move
      room, audited (Q458).

      → **The first code to touch `0026`'s tables.** New
      `apps/api/app/areas/` — `GET /projects/{pid}/areas` (areas with rooms
      nested per Q552, each carrying an item count), `POST
      /projects/{pid}/areas`, `POST /areas/{aid}/rooms`. Gated
      `("tracking", action)` plus `require_drafter()` on the writes, matching
      every other item-shaping mutation.

      → **Q573 raised and answered, in two parts.** (a) Scope is the **edit
      sites only**: `PatchItemIn` gains `area_id` / `room_id`, and setting
      either **also writes** `stage` / `rm_no` / `rm_desc`, so the **25 API
      references across 5 files** and 7 web files that still read them keep
      working — Q435's "kept and still populated". (b) Rows are created
      **inline from the selector**; a duplicate returns 409 **carrying the
      existing id**, so a racing create just selects it.

      → **The tables were empty and would have stayed empty.** `0026`
      backfilled from the items that existed *when it ran*; the seed inserts
      items afterwards, so a fresh database had **0 areas, 0 rooms, 0 of 20
      items with an `area_id`** — the same trap that broke `make seed` in C1.
      The seed now creates both and links every item: 8 areas, 13 rooms,
      **17 of 17** items placed, idempotent across repeated runs.

      → **Two rules the API enforces rather than the schema**, because a raw
      composite-FK violation surfaces as a 500: a room from another area is
      `409 BAD_ROOM`, a room with no area is `ROOM_WITHOUT_AREA`. And **moving
      area clears the room left behind** — it belonged to the old area, so the
      pair would be invalid — with the clear logged like any other change.

      → **Q458 needed no new mechanism**: the move writes an `item_edit_log`
      row reading `room · "K1 · Kitchen" → "B1 · Bathroom"`.

      → **verified**: new `test_area_room_routes.py` (10 cases, passing) pins
      project scoping, room nesting, the dual-write, all three refusals, the
      audited move, the area-move room clear, and that counts see Joinery Items
      only. `npx tsc --noEmit` clean. Driven in a browser: the Area selector
      lists the project's six areas plus "+ New area…", the Room selector only
      that area's rooms, the free-text Stage field is gone, a move from
      `K1 · Kitchen` to `B1 · Bathroom` persisted with `stage/rm_no/rm_desc`
      dual-written, and the move appears in the item's log. Full suite
      **633 passed, 1 skipped**.

### D. Seed + docs

- [x] **D1** Seed: areas + rooms from existing values; one shared cutlist across
      2 ALF-001 items to exercise fan-out; 1 late-linked item for Q539; 2
      related parts (one ordered, one not) for Q417/Q429; 1 supplier; 1 PO.
      → **done.** Areas + rooms already landed with C1/C6 (8 areas, 13 rooms,
      every seeded Joinery Item placed); this task added the rest as one final
      `seed/hartwood_joinery.py` block. It works on the seven `legacy_items`,
      not the five `ITEMS_PER_PROJECT` ones, because the shop-floor block (#8)
      wipes `stage_completion_log` for every cutlist the first six ALF items
      touch — a fan-out written there would not survive its own seed. It also
      runs after the `joinery_number_seq` setval, so the related parts draw
      their numbers from `nextval()` exactly as the API allocates them (Q541),
      landing at 297989/297990 instead of ~198k below the fixtures.
      Shipped: cutlist **297830 "SS Bench run (shared)"** carrying JO-SS01 +
      JO-SS02 with one `DOWN` completion fanned out to both (Q439), then
      JL-BE01a linked **after** it, whose `DOWN` cell stays blank (Q539);
      two related parts under ST-CT01 — a `benchtop` one with an issued order
      and a `metal` one with none (Q417/Q429), both carrying the parent's
      Group ID and no cutlist of their own; supplier `Corian Stoneworks`
      (Q506/Q556 — `vendors` *is* the supplier entity); and one PO whose
      `cutlist_no` is the **parent's** 297975 (Q428), `date_ordered` set so
      Tracking reads it as issued (Q567).
      → *Trap paid twice more.* The per-item cutlist blocks re-INSERT a cutlist
      numbered as the item on every run (their idempotency guard is on `items`,
      not `cutlist`), so moving an item onto the shared cutlist has to drop the
      vacated row **unconditionally**, not as a consequence of the move —
      otherwise run 2 leaves two empty cutlists in `/list`.
      → Verified: `alembic upgrade head` + seed on a virgin database, then
      five consecutive re-runs — related parts 2, vendors 1, POs 1, shared
      cutlist 3 items, empty cutlists 0, items without an area 0, every run.
      (`po_number_seq` advances one value per run; it is unowned and numbers
      are never asserted absolutely.) Driven in a browser: `/tracking` shows
      three rows on cutlist 297830 with `DOWN` 09-18 on the first two and `—`
      on the late joiner, the ordered related part showing `PO-2026-0002`
      where a cutlist number would be and the other showing `—`; the O/BOOK
      sub-tab populates Order # / Supplier / Status / ETA on that one row
      alone; `/list` lists `297830 SS Bench run (shared) · 3 items`.
- [x] **D2** Update `CLAUDE.md` — new sub-project section, migrations `0026`–
      `0029`, and **retire the bare-"stage" terminology pin** once `items.stage`
      is gone (Q456).
      → **done, except the pin — the condition did not fire.** `items.stage`,
      `rm_no` and `rm_desc` are all still present at head and still written on
      every save: `_resolve_area_room` dual-writes `area_id` + `stage` and
      `room_id` + `rm_no` + `rm_desc`, because Q435 requires the change to be
      data-preserving. Q456 retires the pin once the column is *gone*, and it
      is not, so the pin stands and now says why. A later migration drops the
      three columns; the pin retires then.
      → The section covers all **seven** migrations, not just `0026`–`0029`:
      `0030`–`0032` belong to this sub-project too. Also corrected as stale:
      the `db/` layout line claimed `0026`–`0029` were "schema only" with "no
      code reads the new tables yet"; the Plan V1 section claimed "nothing in
      it has been implemented"; conflicts 1, 2 and 6 in the conflict table
      still read "next to build"; and the plan's own reference entry said the
      B/C/D/E tasks were "not started".
      → Two **known gaps recorded rather than quietly left**: `/orderbook`
      still renders the #4 procurement-batch queue, so the
      `/orderbook?order=…` links C1 writes go nowhere and the "locate the
      order" half of Q418 is unhonoured; and the item editor's hardware query
      still reads the catalog `supplier` column alone, which `0017` left empty.
      → Numbers verified against the tree, not copied: 3/7/7/6/8 endpoints for
      `areas` / `cutlists` / `related_parts` / `suppliers` / `orders`; 8 areas
      and 13 rooms across the two demo projects (6 and 9 on ALF-001). B1's
      "35 of 50" is a count of **SQL** call sites — grep finds fewer, because
      16 modules bind the helper's result to a module constant.
- [x] **D3** Add a `> **Later change:**` note to this plan's own header if
      anything is superseded in flight (`plans/README.md` convention).
      → **done.** Seven supersessions listed in the header: the three extra
      migrations, A4's corrected task text (Q553/Q555), B3's unreachable
      `(item_id, 'INST')` (Q561), B1's 50→35 overcount, C2 arriving already
      satisfied, conflict 6 not being the pure rename Q455 anticipated, and
      Q542 widening the scope to the whole Orderbook before work started.
      A4's correction was made in the *body* rather than the header — a
      departure from `plans/README.md`, taken because the body described a
      schema that contradicted the decision record and would have misled
      anyone reading it as the design of record.

### E. Verification

- [~] **E1** — **partly done.** The suite **can** be run in this environment,
      contrary to what B2/B2a/B3 first recorded: a Python 3.12 venv
      (`pyproject.toml` requires >=3.12; the default `python3` here is 3.11)
      plus a local Postgres at `0030` runs all 572 tests in ~2 minutes.
      **Running it found 8 real failures** that the SQL-level checks could not
      see, both clusters caused by these changes:
      1. `test_items_routes.py` ×5 — `ResponseValidationError`. B1 added
         `row_type` / `parent_item_id` / `related_part_type_key` to
         `_ITEM_COLS` and to `TrackingItemRow`, but
         `list_items_for_project` assembles its result **field by field**,
         not `**row`, so the new columns never reached the response.
      2. `test_shop_floor_routes.py` ×3 — `KeyError: 'item_id'` in two audit
         payloads (`routes.py:276`, `:352`) that B3 missed when `0030`
         dropped `worker_assignment.item_id`.
      Both fixed; suite green. Still to do here: the e2e specs (E2) and the
      pilot-data migration (E3).
- [ ] ~~**E1** `make test` green~~; new tests for fan-out, undo, late-link,
      row_type isolation, order→cutlist backfill, Controlled Lock.
- [ ] **E2** `make e2e-docker` green; new spec covering nested related parts
      collapsed by default and the order-number link into Orderbook.
- [ ] **E3** Migrate a **copy of pilot data** (Q436) and confirm every item kept
      its recognisable number (Q540).

## 3. Sequencing

`A1 → A2 → A3 → A4` then **B1 before all other B tasks** — every later query
change assumes the helper exists. `B3` is the riskiest single task and should
land with its tests in the same commit. Web follows backend; seed last.

## 4. What this plan does NOT do

Deferred by explicit decision, not oversight:

- **Item-level cost roll-up** (Q543) — orders carry cost; nothing aggregates.
  Q451 describes where it will land once §16 is scoped.
- **QC module** (Q515), **permission engine** (Q466), **comments** (Q473),
  **search** (Q520, which is next), **Material Take** (Q495).
- **SharePoint** (§H) — blocked on three customer inputs (Q480, Q547, Q484).
- **Stage-list changes** (Q459) — today's 10 stand; Packing arrives with its own
  sub-project (Q519).
- **Cars / OH&S tabs** (Q550) — unspecified.

## 5. Audit events introduced

`cutlist.{create|link_item|unlink_item|renumber}`,
`related_part.{create|reparent|status_change}`,
`supplier.{create|update|archive}`,
`order.{create|issue|update|cancel}`, `po.{create|update}`,
`area.{create|update}`, `room.{create|update}`,
`item.lock_request` + `item.lock_approve` (replacing `item.lock_overridden`).

## 6. Exit criteria

- Several Joinery Items share one cutlist; completing a production stage once
  records it against the cutlist and shows on every linked item's strip.
- Installation completes per item.
- Related parts nest under their parent, carry no stages, and their order
  number links into Orderbook.
- An order exists as a commercial record above batches, with a real PO and a
  real supplier.
- Every pre-existing item kept the number its users recognise.
- `make test` and `make e2e-docker` green.

## 7. Deliberate departures from Plan V1's prose

Do not "fix" these to match the spec — the decisions supersede it:

| Decision | Departs from | Behaviour |
| --- | --- | --- |
| **Q499** | §20 — summary released only after PM confirmation | confirmation is advisory; Procurement may order early, flagged |
| **Q513** | §11 — retain 20 change states for rollback | no rollback; history is for accountability |
| **Q527** | §32 — IT defines KPI formulas | fixed KPI catalogue |

(Q499 and Q527 bear on later sub-projects; listed here so the set stays in one
place.)

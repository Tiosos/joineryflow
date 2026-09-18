# Implementation Plan — Cutlist + Related Parts + Orderbook (Plan V1 #10)

> **Status: not started.** Migrations reserved `0026`–`0029`. This is a
> **forward plan**, not a shipped-state record. Current state stays in
> `CLAUDE.md`; the checkboxes below are not a progress signal (see
> `docs/superpowers/plans/README.md`).

> **Decision source.** Every binding rule here traces to a numbered answer in
> `docs/plan-v1/OPEN-QUESTIONS.md` (Q432–Q551) and is mirrored in
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

- [ ] **B1** **Do this first.** One `visible_items()` helper (or a SQL
      fragment constant) encoding `row_type = 'joinery_item'`, and apply it to
      all **50 call sites across 13 modules** — `items` (13), `shop_floor` (8),
      `procurement_v1` (5), `parts` (5), `home` (4), `item_attachments` (3),
      `hardware_lines` (3), `estimating` (2), `cv` (2), `cut_floor` (2), and
      one each in `public`, `projects`, `printing`.
      → verify: a test asserting a seeded related part appears in **no**
      shop-floor board, cut-plan, print or estimating query.
- [ ] **B2** `apps/api/app/cutlists/` — CRUD, number allocation from the shared
      sequence, link/unlink an item, 409 on linking a second cutlist (Q411).
- [ ] **B2a** **Repoint both existing `items.num` allocators at
      `joinery_number_seq`** — this fixes a live pre-existing bug, found while
      building A2. The tree has **two** inconsistent schemes for one UNIQUE
      column:
      `items/queries.py` uses `nextval('items_item_id_seq') + 100000`, and
      `estimating/queries.py` uses `SELECT COALESCE(MAX(num), 0) + 1`. The
      second is a read-then-insert with no lock, so two concurrent estimate
      conversions pick the same number and the loser fails on `items_num_key`.
      **Reproduced directly against the real schema.** Q541's single sequence
      is the fix; `0027` already seeds it above both watermarks so nothing
      either scheme issued can collide.
      → verify: a test that two conversions in flight both succeed.
- [ ] **B3** Rework `shop_floor` — re-key `worker_assignment` and
      `stage_completion_log` to `(cutlist_id, stage_key)` for production and
      `(item_id, 'INST')` for install (Q445); rebuild the partial unique index;
      **fan out** `item_stages.done_date` to every linked item on complete
      (Q439); undo reverses the whole cutlist (Q446); a late-linked item is a
      no-op on undo (Q539).
      → verify: complete CNC on a 3-item cutlist → 3 `item_stages` rows; undo →
      0. Late-linked 4th item gains nothing on either.
- [ ] **B4** Related-part routes — create (drafter or PM, Q423), reparent with
      audit (Q452), own status (Q450). **No workflow stages** (Q419).
- [ ] **B5** `supplier` CRUD; repoint catalog reads/writes (Q506).
- [ ] **B6** Order + PO routes on the revived namespace — create from Tracking's
      O/BOOK subtab (Q425), prefill PROJECT / LOCATION / CUTLIST NO. from the
      parent (Q427, Q428), allow blank cutlist (Q429), backfill when the parent
      gains one (Q430), update all linked orders on replacement (Q431).
      Gated `("orderbook", …)` — Q432, no matrix change.
- [ ] **B7** Item soft-lock → Controlled Lock: a non-owner's save becomes a
      **request requiring approval** instead of succeeding with an
      `item.lock_overridden` audit row (Q509). Item and project scope only
      (Q510).

### C. Web

- [ ] **C1** `ItemsTable` — nest related parts under their parent, collapsed by
      default (Q420–Q422); **empty stage-strip area** for them (Q419); leftmost
      column shows cutlist number for an item, **issued order number** for a
      related part (Q417), linking to Orderbook (Q418).
- [ ] **C2** Stage strip repeats on every item row (Q441) — reads `item_stages`
      directly, no join to cutlist.
- [ ] **C3** `/list` becomes the **Cutlist module workspace** (Q474). Opens as a
      `target="_blank"` tab (Q545), deep-linkable (Q478).
- [ ] **C4** Tracking **O/BOOK subtab** with **Create Order** (Q425) opening the
      generic order form (Q426, Q503).
- [ ] **C5** Project Details modal gains `Project Stats` + `Scope` (Q476).
      **Cars and OH&S are omitted** pending Q550.
- [ ] **C6** Area / Room selectors replace the free-text fields; item may move
      room, audited (Q458).

### D. Seed + docs

- [ ] **D1** Seed: areas + rooms from existing values; one shared cutlist across
      2 ALF-001 items to exercise fan-out; 1 late-linked item for Q539; 2
      related parts (one ordered, one not) for Q417/Q429; 1 supplier; 1 PO.
- [ ] **D2** Update `CLAUDE.md` — new sub-project section, migrations `0026`–
      `0029`, and **retire the bare-"stage" terminology pin** once `items.stage`
      is gone (Q456).
- [ ] **D3** Add a `> **Later change:**` note to this plan's own header if
      anything is superseded in flight (`plans/README.md` convention).

### E. Verification

- [ ] **E1** `make test` green; new tests for fan-out, undo, late-link,
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

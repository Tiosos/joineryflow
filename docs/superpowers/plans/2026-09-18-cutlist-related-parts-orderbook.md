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

- [ ] **A1** `0026_area_room` — create `area` + `room` (project-scoped, Q457);
      add `items.area_id` / `items.room_id`; migrate distinct `items.stage`
      values → `area`, `(rm_no, rm_desc)` → `room`; keep `level` + `zone` as
      plain columns (Q546). Drop `items.stage` **last**, after A4.
- [ ] **A2** `0027_cutlist` — create `cutlist` (`cutlist_no` six-digit UNIQUE
      workspace-wide, `project_id` FK, audit columns); create the shared
      `joinery_number_seq` (Q541) starting above `MAX(items.num)`; add
      `items.cutlist_id` (nullable — Q440). **Data step:** one cutlist per
      existing item carrying its `num` (Q540).
- [ ] **A3** `0028_related_parts` — add `items.row_type`
      (`joinery_item` | `related_part`, default `joinery_item`),
      `items.parent_item_id` self-FK, `related_part_type` lookup seeded with
      metal / benchtop / cushion (Q448); CHECK that a `related_part` has a
      parent and a `joinery_item` does not (Q449); backfill
      `items.group_id` = own id for existing rows (Q453).
- [ ] **A4** `0029_orderbook` — add `workspace_id` to the 9 legacy procurement
      tables **and backfill it** (Q502 — they have none today); create
      `supplier` and repoint the 6 catalog tables' `supplier` /
      `default_supplier` free text (Q506); add `order` + `order_line` with a
      JSONB `attributes` column (Q503); port `quantity_reserved`,
      `reorder_point`, `reorder_quantity` onto `board_inventory` and **drop**
      legacy `inventory` + `inventory_movements` (Q544).
      → verify: `make migrate` clean from `0001`; re-run idempotent.

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

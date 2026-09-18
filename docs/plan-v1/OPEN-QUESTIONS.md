# Plan V1 — open questions (Q432 →)

> Continues the numbering in [`plan_v1.md`](./plan_v1.md), whose last confirmed
> decision is **Q431** and whose stated next question is **Q432**.
> Every question below is grounded in [`ALIGNMENT.md`](./ALIGNMENT.md) — where a
> question exists because Plan V1 contradicts shipped code, the conflict is
> cited. Answer in the plan's own style (*"Q4xx — Option 2"*, or a custom
> decision); answers get folded back into `plan_v1.md` and `CLAUDE.md`.

**Status (2026-09-18).** §A is settled: **Q433 = 1**, **Q435 = 2**,
**Q437 = 1**, **Q438 = 1**. Plan V1 is the roadmap for this codebase; shipped
behaviour may change but only behind data-preserving migrations; the Cutlist
becomes a first-class entity; and **Cutlist + related parts is the next
sub-project**. That promotes §B and §C from "eventually" to **design-blocking
now**. Q432, Q434 and Q436 remain open.

**§B round 2 (2026-09-18):** **Q439 = 3**, **Q440 = 1**, **Q441 = 1**,
**Q445 = 1**. Together these settle the shape: assignment and completion are
owned at **cutlist** level for production stages, `stage_completion_log`
becomes cutlist-level truth, and `item_stages` becomes a **per-item projection
of it**, fanned out on write — which is exactly what Q441's repeated stage
strip reads, with no join. Installation stays per item throughout (Q413/Q415).

**§B round 3 (2026-09-18):** **Q443 = 1**, **Q446 = 1**, **Q539 = 2**,
**Q540 = 1**. Numbers are company-wide unique; undo reverses a whole cutlist;
a late-linked item leaves earlier stages blank; and existing items each get
their own cutlist carrying their current number.

**§C round 1 (2026-09-18):** **Q442 = 1**, **Q447 = 1**, **Q448 = 2**,
**Q450 = 1**. Related parts are rows in `items` with a `row_type` discriminator
and a parent FK; the type list is a configurable lookup; each part carries its
own status; cutlist numbers are system-allocated sequentially.

**Measured blast radius of Q447 = 1.** `row_type` filtering must be added to
**50 SQL call sites across 14 files in 13 modules** — `items` (13),
`shop_floor` (8), `procurement_v1` (5), `parts` (5), `home` (4),
`item_attachments` (3), `hardware_lines` (3), `estimating` (2), `cv` (2),
`cut_floor` (2), and one each in `public`, `projects` and `printing`. Any one
of them left unfiltered silently leaks related-part rows into a surface that
should only see Joinery Items — `shop_floor` especially, since Q419 gives
related parts no workflow stages at all. This is the main implementation risk
in §C and wants a shared helper rather than 50 hand-edited predicates.

**§C round 2 (2026-09-18):** **Q449 = 1**, **Q452 = 1**, **Q453 = 1**,
**Q541 = 1**. One level of nesting; reparenting allowed with audit; `group_id`
repurposed with its values migrated; Item IDs and cutlist numbers share one
company-wide sequence.

**Q453 is cheaper than it looked — verified.** `items.group_id` is currently
**written by nothing**. The seed never sets it, no API route accepts it
(`ItemMetadataPanel.tsx:196` carries the comment *"group_id is read-only in
v1 — not exposed in PatchItemIn"*), and it is read in exactly three places:
`items/queries.py:387`, plus two display fields
(`ItemMetadataPanel.tsx:197` and `ItemDetailModal.tsx:177`). Against seeded
data the migration is a **no-op** — there are no values to migrate. Whether
real deployments hold values depends on **Q436**, which is still open; that
question is worth closing before the migration is written.

**Scope round (2026-09-18):** **Q542 = 3**, **Q432 = 1**, **Q444 = 1**,
**Q451 = 1**. The sub-project **includes the full Orderbook rework** (§K);
Create Order stays with today's `orderbook` write holders; a cutlist belongs to
exactly one project; related-part cost rolls into the parent item.

**What Q542 = 3 does to the sub-project.** It is no longer "cutlist + related
parts". It now also carries §K — an order entity, per-type order-details forms
(screenshots 07–09), PO creation and a supplier registry — on top of a row-model
reshape that already touches 50 call sites. For sizing, the two existing
procurement surfaces are: the **legacy `/procurement/*` namespace**, 9 tables
(`vendors`, `cost_centers`, `purchase_orders`, `po_line_items`,
`po_attachments`, `approval_workflows`, `inventory`, `inventory_movements`,
`budget_transactions`) and 32 endpoints, currently unused by the v1 surface;
and **`procurement_v1`**, 11 endpoints across 4 sub-routers with no order or PO
entity at all. §K (Q502–Q507) is therefore design-blocking now, and Q502
decides whether those 9 legacy tables are revived or retired.

**Raised by Q451 = 1 — pending as Q543.** Related-part cost rolls into the
parent item, but **no item-level cost field exists**; `projects.total_value` is
a single project number and §16's financial model is not scoped. Either this
sub-project introduces an item cost, or the roll-up has nowhere to land.

**§K round 1 (2026-09-18):** **Q502 = 1**, **Q504 = 2**, **Q506 = 1**,
**Q507 = 2**. These converge rather than conflict: the legacy namespace is
revived, so its `vendors` table becomes Q506's supplier entity and its
`purchase_orders` / `po_line_items` become Q504's commercial order layer, with
`procurement_batches` + `batch_allocations` kept beneath as allocation. Orders
then cover all procurement, not just related parts.

**Two verified problems with reviving the legacy namespace.**

1. **It has no workspace scoping at all.** Checked: `workspace_id` appears
   **zero times** in `0002_procurement_port.py` — none of the 9 tables have it.
   The current standard (migration `0014` and commit `cc7ea11`) is that every
   read and write scopes through `workspace_id`, with cross-workspace returning
   404. Reviving these tables therefore requires adding workspace scoping to
   each one before they can serve a multi-workspace product. This is not
   optional and is the largest hidden cost in Q502 = 1.
2. **Legacy `inventory` duplicates `board_inventory`.** The legacy table carries
   `sku` (UNIQUE), `quantity_on_hand`, `quantity_reserved`, `reorder_point`,
   `reorder_quantity`, `unit_cost` and `location`; migration `0025` added
   `board_inventory` for the same job. This is precisely the duplicate-surface
   situation #7a judged worth fixing when it retired `/catalogs`. Notably the
   legacy table has `quantity_reserved` and `reorder_point`, which
   `board_inventory` lacks and Plan V1 §18 wants — so it is a partial head
   start, not pure redundancy. Raised as **Q544**.

Legacy `cost_centers` and `budget_transactions` similarly overlap §16's
financial model, which is unscoped — they bear on **Q543**.

**§K round 2 (2026-09-18):** **Q503 = 3**, **Q505 = 1**, **Q543 = 3**,
**Q544 = 1**. A generic order form with a JSONB attributes blob; a real PO
entity; item-level cost roll-up deferred; `board_inventory` wins and the legacy
inventory tables are dropped.

**Two reconciliations this forces.**

- **Q451 is now intent, not behaviour.** Q543 = 3 defers the item cost field,
  so related-part orders carry cost and **nothing rolls up to the parent item
  in this sub-project**. Q451 describes where it will land once §16 is scoped.
- **Q503 = 3 narrows what §21 can query.** With type-specific fields in a JSONB
  blob they are neither schema-validated nor easily queryable, so supplier
  comparison (§21) cannot filter or compare on them — only on the fixed
  columns. Acceptable while the type list is still settling under Q448's
  configurable lookup; worth revisiting if comparison on, say, benchtop edging
  is later wanted.

With this round, **every question for the selected sub-project is answered**
except §A's **Q434** and **Q436**. §B (Q438–Q446), §C (Q447–Q453) and
§K (Q502–Q507) are complete, along with Q539–Q544.

**Closing round (2026-09-18):** **Q434 = 2**, **Q436 = 2**, **Q474 = custom**,
**Q475 = 2**.

**Q474 dissolves a conflict rather than resolving it.** `ALIGNMENT.md` §3.5
framed Cutlist as needing a seventh primary tab against a binding rule. It does
not: **Cutlist is the `List` tab.** The primary six stay six, the rule is
untouched, and the existing RBAC module `list` — which already gates
`cutlist.pdf` and item attachments — turns out to have been the cutlist module
from the start. Of the five conflicts in §3, this one is now closed by naming
rather than by building.

**Q475 = 2 is the one genuinely new UI cost.** Today the app is a single
Next.js shell: `(app)/layout.tsx` does a server-side `fetchMe()` and renders
one TopBar + TabStrip + SideBar around every route. Separate windows per module
means per-window auth resolution and per-window state, and the tab strip stops
being the navigation model for those three. Worth confirming the intended
behaviour before building — see **Q545**.

**Q436 = 2 sets the migration bar.** Pilot rows exist, so the Q540 cutlist mint,
the Q453 `group_id` repurpose and the Q544 inventory drop each need a correct
data step — but re-seeding is an acceptable recovery, so they do not need
rollback plans.

**Q434 = 2 sets what follows.** §7–§8 and §35–§38 (~99 decisions, the largest
single block in Plan V1) are explicitly **aspirational**, so `ALIGNMENT.md`
§6's observation that they are separable is now the agreed position.

### Q545 — What exactly does "separate window" mean? *(new — forced by Q475)*
**Option 2 confirmed (2026-09-18).** A normal browser tab opened with `target="_blank"` — a separate OS window as soon as the user drags it out, with no popup blockers, no new auth path and deep links intact.
1. **A real popup window** (`window.open` with sized chrome), as the reference
   FileMaker-era system does.
2. **A normal browser tab** opened with `target="_blank"` — separate OS window
   if the user drags it out, no popup blockers, no new auth path.
3. **Same shell, but each module is a deep-linkable route** the user may open
   in as many windows as they like — today's behaviour, formalised.

**Stage + window round (2026-09-18):** **Q459 = 3**, **Q461 = 2**,
**Q462 = 1**, **Q545 = 2**. All four are scope-reducing.

- **The stage-list conflict is deferred, not adopted.** `ALIGNMENT.md` listed
  10-vs-14 stages as one of the seven `REARCH` rows. Q459 keeps the existing
  10, so the cutlist inherits today's lifecycle **unchanged** and no stage
  migration happens in this sub-project. Q460, Q463, Q464 and Q465 go with it.
- **Q545 = 2 makes Q475 nearly free.** `target="_blank"` needs no per-window
  auth path, no popup handling and no change to the shell — each window is
  simply the app at a different route. The two-monitor use case is met.
- **Q461 + Q462 mean no lifecycle change at all**: today's paint ordering and
  the single global `stages` lookup both stand.

### Conflict scoreboard (2026-09-18)

Of the seven `REARCH` rows in `ALIGNMENT.md`:

| Conflict | State |
| --- | --- |
| §3.1 Cutlist owns the workflow | **Accepted** — being built (Q438) |
| §3.2 Related-part rows | **Accepted** — being built (Q447) |
| §3.5 Navigation / Cutlist module | **Closed** — it is the `List` tab (Q474) |
| Stage list, 10 vs 14 | **Deferred** — today's 10 stand (Q459) |
| §3.3 SharePoint project files | Open — §H unanswered |
| §3.4 RBAC as data | Open — §F unanswered; Q432 avoided touching the matrix |
| Area / Room as entities | Open — §D unanswered |

**§D round 1 (2026-09-18):** **Q454 = 1**, **Q455 = 1**, **Q457 = 1**,
**Q546 = 1**. Area and Room become real per-project entities; Area is today's
`items.stage` and Room is today's `rm_no` + `rm_desc`; `level` and `zone` stay
as attributes rather than becoming hierarchy levels.

**This is a rename plus normalisation, not new structure.** Both levels already
exist as data — the API already aliases `rm_no`/`rm_desc` to `room_no`/
`room_desc`, and CLAUDE.md already pins Stage as "site location/area". The
migration dedupes existing free-text values per project into `area` and `room`
tables and repoints `items`.

**Measured: the `items.stage` → Area rename is cheap.** Only **14 references
across 7 files** — `items/queries.py`, `items/schemas.py`, `printing/context.py`,
`TrackingFilters.tsx`, `ItemMetadataPanel.tsx`, `ItemsTable.tsx`, `pm-types.ts`.
Doing it alongside the Q447 `row_type` change means one migration on `items`
rather than two, which is why §D was worth settling now rather than later.

It also has a side effect worth taking: renaming the site-location column
frees the bare word **"stage"** to mean only the lifecycle, retiring a
terminology collision CLAUDE.md currently guards with a standing rule. That is
**Q456**.

**§D close + §J round 1 (2026-09-18):** **Q456 = 1**, **Q495 = 1**,
**Q497 = 2**, **Q499 = 2**.

**Q497 and Q499 are a consistent stance, and Q499 is a deliberate departure
from Plan V1's text.** Both choose *warn* over *block*, which matches Plan V1's
own core principle — "the system tracks, detects, alerts, records and
recommends; authorised people decide". But §20 states plainly: *"Only after PM
confirmation is the summary released to Procurement Dashboard."* That is a hard
gate as written, and Q499 = 2 knowingly softens it to a warning so lead times
can be met.

> **Recorded so it is not "fixed" later.** A future reader comparing the code to
> §20 will find them disagreeing. The code is right: Q499 supersedes §20's
> release gate. §19's ordering is likewise advisory under Q497, though §19 never
> used blocking language.

**Q456 retires a standing rule — but not yet.** The pin stays in `CLAUDE.md`
until the `items.stage` → `area` rename ships, because that file records what is
true now, not what is planned.

**§J complete (2026-09-18):** **Q496 = 3**, **Q498 = 2**, **Q500 = 2**,
**Q501 = 1**. §J (Q495–Q501) is now fully answered.

**Q496 = 3 has a sequencing tension worth designing around.** §19 puts Material
Take *before* Shop Drawing Approved, but the CutPlan nest cannot exist that
early — nesting needs parts, which arrive at Listing, well after drawing
approval. So a nest-derived take is impossible at the point §19 places it.

The resolution follows from answers already given: generate the take early from
**parts + hardware lines**, then **refine it from the nest** once one exists,
advancing the take's version (Q500) and flagging any summary line that consumed
the earlier version. This works precisely because Q497 made the take advisory
rather than a gate — an un-refined take never blocks anything.

**Q498 = 2 keeps two overlapping views.** `/procurement-queue` stays live and
the summary becomes the released artefact. The risk the option named is real:
people working from the wrong one. Worth a visible marker on the queue saying
which of its lines are covered by a confirmed summary.

**Q501 = 1 holds the line from #9.** `/optimise` stays pure. Combined with
Q544's port of `quantity_reserved` onto `board_inventory`, reservation has
somewhere to live whenever it is built, without a what-if nest ever silently
committing stock.

**§L round 1 (2026-09-18):** **Q508 = 1**, **Q509 = 1**, **Q511 = 2**,
**Q513 = 3**.

**Q513 = 3 is the second deliberate departure from Plan V1's text.** §11 states
that the system *"retains at least the last 20 change states/steps for
rollback"* and that *"rollback creates a restorative revision rather than
erasing history"*. Neither is built. The audit trail answers **who changed what
and when**; it cannot restore a prior state, and no promise of restore is made.

> **Recorded so it is not "fixed" later.** Like Q499, a future reader comparing
> code to §11 will find them disagreeing. The code is right: Q513 supersedes
> §11's rollback requirement. Q514 (scope of rollback) is moot as a result.

**Q508 = 1 and Q511 = 2 are complementary, not redundant.** The three lock
types prevent most collisions outright, so optimistic concurrency control is
only needed where a lock does *not* apply. That is why targeting three surfaces
is defensible where it would not be on its own: item editor, cutlist, orders.
Q512's field-level detection is scoped to those same three.

**Q509 = 1 tightens a real behaviour.** Today a non-owner's save **succeeds**
and merely writes `item.lock_overridden`. As a Controlled Lock that becomes a
request needing approval — a genuine behaviour change on a shipped path, and
one Q435's data-preserving-migration rule covers.

**§L close + §F round 1 (2026-09-18):** **Q510 = 2**, **Q512 = 1**,
**Q466 = 2**, **Q467 = 2**.

**Q510 = 2 and Q512 = 1 are not contradictory — they are different
mechanisms.** Q510 says there is no *field-level lock type*: nobody can
deliberately lock a field, only an item or a project. Q512 says conflict
*detection* is per-field, so when two people edit the same record the system
locks just the fields genuinely in conflict (Q366) until resolved. One is a
governance action someone takes; the other is a transient state the system
enters. Both can hold at once, and the wording matters when implementing §12.

**Q466 = 2 keeps the largest conflict bounded.** `ALIGNMENT.md` §3.4 called the
RBAC replacement the highest-blast-radius item in Plan V1. Stopping at project
scope keeps §3's real benefit — IT configuring access without a deploy — while
avoiding a permission check per row. **Item-level and tab-level scoping from §3
are not built.**

**Q467 = 2 leaves `jtbd_role` as it is.** It stays free text and display-only,
exactly as `CLAUDE.md` already records. Groups carry permission meaning, so
§4.2's department dashboards will key off group membership rather than a
department entity. Q468 (mapping the 7 roles onto ~21 departments) is
correspondingly simpler: the roles become groups.

**Consequence to design against.** Q539 = 2 means `item_stages` may legitimately
disagree with the cutlist-level completion log for a late-linked item, and
Q441's repeated strip will therefore show *different* strips for items on the
same cutlist. This is accepted, not an oversight: the completion log is the
truth, the strip is a per-item projection that may lag. Anything asking "is
this cutlist's CNC done?" must read the **log**, never an item's strip. Undo
(Q446) is a no-op on an item that never received the fanned-out date.

---

## §A — Scope and intent (answer these first)

### Q432 — Create Order authority *(Plan V1's own next question)*
**Option 1 confirmed (2026-09-18).** Today's `orderbook` write holders — admin, manager, drafter, purchase_officer. No RBAC change.
Which roles can click **Create Order** in Tracking's O/BOOK subtab and submit a
related-part order request?
Today `orderbook` write is held by `admin`, `manager`, `drafter` and
`purchase_officer`; `editor` has read+comment only.
1. Same as today's `orderbook` write holders.
2. Drafter and PM only (matching Q423's related-part creation authority).
3. Anyone who can create the related-part row, plus Procurement.
4. A new dedicated permission, assignable per project.

### Q433 — What is this repository to Plan V1?
**Option 1 confirmed (2026-09-18).** Plan V1 is the roadmap for this codebase.
1. **Plan V1 is the roadmap for this codebase** — evolve JoineryFlow into it
   incrementally, accepting the five `REARCH` rewrites.
2. **Plan V1 is a different product** — this repo continues as-is; Plan V1 is
   specified separately and may reuse parts.
3. **Plan V1 supersedes this codebase** — treat the shipped system as a
   prototype and rebuild against Plan V1.
4. **Plan V1 is a requirements archive for now** — document the gap (this
   exercise), build nothing until a sub-project is chosen.

### Q434 — Is Plan V1 committed scope, or a wish list?
**Option 2 confirmed (2026-09-18).** The joinery-workflow half is committed; the IT-governance half (§7–§8, §35–§38 — templates, validation, simulation, initiatives, escalation) is aspirational.
Plan V1 runs to Q431 across ~35 subsystems. The gap analysis
finds 50 `ABSENT` rows.
1. All of it is committed scope; the only question is ordering.
2. The joinery workflow half is committed; the IT-governance half
   (§7–§8, §35–§38 — templates, validation, simulation, initiatives,
   escalation) is aspirational.
3. Neither — Plan V1 is a superset to select from, sub-project by sub-project.

### Q435 — May shipped behaviour be broken?
**Option 2 confirmed (2026-09-18).** Changes allowed, but only behind migrations that preserve existing data.
The five `REARCH` items cannot be built without changing existing schema and
behaviour.
1. Yes — shipped code has no users yet; break freely.
2. Only behind migrations that preserve existing data.
3. No — additive only; Plan V1 features that conflict must be re-specified to
   fit the current model.

### Q436 — Is there production data or live users today?
**Option 2 confirmed (2026-09-18).** Pilot users on the demo workspace — real rows exist but nothing business-critical. Migrations must be correct; a bad one is recoverable by re-seeding.
This determines whether "migration" means data migration or just schema churn.
1. No users, no data — seed only.
2. Pilot users on the demo workspace.
3. Real production data already in the system.

### Q437 — Which single sub-project comes next?
**Option 1 confirmed (2026-09-18).** Cutlist entity + related parts (§3.1 + §3.2), built as one change.
Naming one makes everything else answerable later instead of now.
1. Cutlist entity + related parts (§3.1 + §3.2) — unblocks Q410–Q431.
2. Material Take → Material Summary → Procurement release (§19–§20) — clean
   insert, no conflicts.
3. Dynamic RBAC + departments + groups (§3.4) — unblocks every permission
   question in the document.
4. Financials: contract value, variations, close snapshots (§16–§17).
5. Something else (name it).

---

## §B — The Cutlist entity *(gap §3.1 — the largest conflict)*

Today the lifecycle lives on `item_stages (item_id, stage_key, …)`, strictly
per item, and `items.num` (UNIQUE integer) *is* the cutlist number. Q412 makes
the cutlist a separate entity owning one shared workflow.

### Q438 — Confirm the cutlist becomes a first-class entity
**Option 1 confirmed (2026-09-18).** New `cutlist` table; items link to it; the production workflow moves onto it.
1. Yes — new `cutlist` table; items link to it; the workflow moves onto it.
2. No — keep one cutlist per item (today's model); Q410–Q413's sharing was
   describing the old FileMaker system, not a requirement for the new one.
3. Yes, but sharing is rare — model it, default one-cutlist-per-item.

### Q439 — What happens to `item_stages`?
**Option 3 confirmed (2026-09-18).** `item_stages` stays per-item; completing a shared stage writes the same `done_date` to every linked item. No `cutlist_stages` table.
1. Replace with `cutlist_stages`; items read their parent cutlist's stages.
2. Keep both — cutlist stages for production, item stages for installation
   (Q413/Q415 split them anyway).
3. Keep `item_stages` and *derive* shared values by writing to every linked
   item on completion.

### Q440 — Can an item exist with no cutlist?
**Option 1 confirmed (2026-09-18).** Yes, indefinitely. The cutlist is assigned later; consistent with Q429.
Q411 sets the maximum at one and explicitly does not require one.
1. Yes, indefinitely — cutlist is assigned later in the workflow.
2. Yes, but only before the Listing stage.
3. No — every item gets a cutlist at creation.

### Q441 — Where is the shared workflow *shown* in Tracking?
**Option 1 confirmed (2026-09-18).** The stage strip repeats on every item row, as in screenshot 12. This is what makes Q439's fan-out worth having: Tracking reads `item_stages` per row with no join to the cutlist.
If five items share one cutlist and one stage strip, the current one-row-per-
item table repeats the same strip five times.
1. Repeat the strip on every item row (visually redundant, matches screenshot 12).
2. Group items under a cutlist header row that owns the strip.
3. One row per cutlist by default; expand to see its items.

### Q442 — Who allocates the six-digit cutlist number?
**Option 1 confirmed (2026-09-18).** System-allocated sequential, on creation in the Cutlist panel, from the company-wide sequence (Q443).
1. System-allocated sequential on creation in the Cutlist panel.
2. Manually entered by the Drafter.
3. System-suggested, manually overridable.

### Q443 — Are cutlist numbers unique company-wide or per project?
**Option 1 confirmed (2026-09-18).** Company-wide unique — one sequence across all projects.
Six digits across all projects implies a company-wide sequence.
1. Company-wide unique.
2. Unique per project.

### Q444 — Can a cutlist span more than one project?
**Option 1 confirmed (2026-09-18).** No — a cutlist belongs to exactly one project, enforced by FK.
1. No — a cutlist belongs to exactly one project.
2. Yes.

### Q445 — What does Shop Floor assignment key off after the change?
**Option 1 confirmed (2026-09-18).** `(cutlist_id, stage_key)` for production stages, `(item_id, 'INST')` for installation.
Migration `0020`'s `worker_assignment` and `stage_completion_log` key off
`(item_id, stage_key)`, with the partial unique index `uniq_active_assignment`.
1. `(cutlist_id, stage_key)` — one worker per stage per cutlist.
2. Keep `(item_id, stage_key)`, and completing any linked item completes them
   all.
3. `(cutlist_id, stage_key)` for production, `(item_id, 'INST')` for install.

### Q539 — An item linked to a cutlist that already has completed stages *(new — forced by Q439 + Q440)*
**Option 2 confirmed (2026-09-18).** Leave blank; the item catches up when a later stage completes.
Q440 lets an item sit with no cutlist indefinitely, and Q439 makes
`item_stages` a projection written at completion time. So an item linked to a
cutlist whose CNC and EDGED are already done has no rows for them — the
fan-out already happened, before this item existed on the cutlist.
1. **Backfill on link** — copy the cutlist's completed stages onto the item at
   link time, so its strip immediately matches its siblings. Needs an audit
   entry, since done dates appear that this item never "earned".
2. **Leave blank** — the item shows those stages incomplete and only catches up
   when a later stage completes. Honest, but the strip then contradicts the
   shared-workflow rule in Q412.
3. **Block the link** — refuse to link an item to a cutlist that has any
   completed production stage; the drafter must use a new cutlist.

### Q540 — What happens to the existing `items.num` values? *(new — forced by Q438 + Q435)*
**Option 1 confirmed (2026-09-18).** Mint one cutlist per existing item, carrying `items.num` across as its cutlist number. Verified: seeded values are already six-digit (`290001`–`290010`), so the new company-wide sequence simply starts above the highest existing value — no renumbering and no padding needed.
`items.num` is today a `UNIQUE NOT NULL integer` rendered in Tracking's CUTLIST
column. Under Q438 the cutlist number becomes a separate six-digit reference
that several items share. Q435 requires a data-preserving migration.
1. **Mint one cutlist per existing item**, carrying `items.num` across as its
   number. Every historical item keeps the number people recognise, and each
   starts on its own cutlist — sharing only begins for new work.
2. **Keep `items.num` as an internal item id** and allocate cutlist numbers
   fresh from a new sequence. Cleaner separation, but every existing item's
   visible CUTLIST number changes.
3. **Keep both visible** — `items.num` stays as the Item ID (per Q416, where
   Item ID and Group ID are the same internal number) and the cutlist number is
   a new, separate column shown alongside.

### Q446 — Does the 5-minute undo window apply per cutlist?
**Option 1 confirmed (2026-09-18).** Undo reverses the whole cutlist's completion atomically — the log entry and every fanned-out `done_date`.
An undo currently reverses one item's stage completion.
1. Undo reverses the whole cutlist's stage completion.
2. Undo is per item even where completion is shared (inconsistent — flag it).

---

## §C — Related-part rows *(gap §3.2)*

Q416–Q424 introduce metal / benchtop / cushion rows: own Item ID, parent's
Group ID, no cutlist, no stages, order number in the cutlist column. Today
`items.group_id` is an unused free-text `varchar(32)`.

### Q447 — Are related parts rows in `items`, or a new table?
**Option 1 confirmed (2026-09-18).** Rows in `items`, with a `row_type` discriminator and a self-referencing parent FK.
1. Rows in `items` with a `row_type` discriminator and a self-FK parent.
2. A new `related_part` table.
3. Reuse `modules`/`parts` (they already hang off an item) — but those are
   cutlist components, not orderable parts.

### Q448 — Is the related-part list fixed at metal / benchtop / cushion?
**Option 2 confirmed (2026-09-18).** A configurable lookup table, seeded with the three — matching how `stages` and `status_options` already work.
1. Fixed — exactly those three.
2. A configurable lookup list.
3. Free-text type.

### Q541 — Do Item IDs and cutlist numbers share one number space? *(new — forced by Q447 + Q540 + Q442)*
**Option 1 confirmed (2026-09-18).** One shared company-wide sequence, so a six-digit number never means two different things.
Q540 makes each existing item's `num` become its cutlist's number, so for every
legacy row **Item ID == cutlist number**. Going forward they diverge: Q442
allocates cutlist numbers from a company-wide sequence, and Q447 puts related
parts in `items`, so they consume Item IDs too. With two sequences, Item ID
`290042` and cutlist `290042` could be unrelated things — confusing precisely
because in legacy rows they are always the same thing.
1. **One shared sequence** — Item IDs and cutlist numbers draw from the same
   company-wide counter, so a six-digit number never means two things. Numbers
   advance faster and have gaps in each series.
2. **Two sequences, different formats** — keep them separate but make cutlist
   numbers visually distinct (a prefix, or a different digit count), so the two
   can never be mistaken for each other.
3. **Two independent sequences** — accept that the same six digits may be both
   an Item ID and an unrelated cutlist number; context disambiguates.

### Q449 — Can a related part have its own related parts?
**Option 1 confirmed (2026-09-18).** One level only — a related part cannot itself be a parent.
1. No — one level only.
2. Yes, arbitrary nesting.

### Q450 — What is a related part's status and priority?
**Option 1 confirmed (2026-09-18).** Related parts carry their own status, so a stuck supplier order can be flagged without changing the parent.
Q419 empties the workflow-stage area but says nothing about the
`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD` status.
1. Related parts carry their own status.
2. They inherit the parent's status.
3. They have no status.

### Q451 — Does a related part carry cost?
**Option 1 confirmed (2026-09-18).** Yes — the part's order cost rolls into its parent Joinery Item's cost, matching §16's Project + Item granularity.
Relevant to §16's item-level financials.
1. Yes — its order's cost rolls into the parent item's cost.
2. Yes — it is costed separately at project level.
3. No.

### Q452 — Can a related part be moved to a different parent?
**Option 1 confirmed (2026-09-18).** Yes, with audit; the move updates the part's Group ID and, per Q431's precedent, the CUTLIST NO. on any linked supplier orders.
1. Yes, with audit (and Q431-style order reference updates).
2. No — delete and recreate.

### Q453 — Existing `items.group_id` data
**Option 1 confirmed (2026-09-18).** Repurpose the column for Q416's Group ID semantics, migrating existing values.
Seeded and legacy rows carry free-text values.
1. Repurpose the column for the new Group ID semantics; migrate existing values.
2. Leave it alone; add a new column.

---

## §D — Area and Room *(gap §4, Plan V1 §2)*

Plan V1's drill-down is `Project → Area → Room → Joinery Item`. Today `items`
carries free-text `stage` (site location), `zone`, `level`, `rm_no`, `rm_desc`
and there are no Area or Room tables.

### Q454 — Do Area and Room become real entities?
**Option 1 confirmed (2026-09-18).** Yes — both, as real tables with FKs from `items`.
1. Yes — both, with their own tables and FKs from `items`.
2. Area only; Room stays free-text on the item.
3. Neither — keep today's free-text columns and treat Area/Room as labels.

### Q455 — How does this map onto the existing terminology pins?
**Option 1 confirmed (2026-09-18).** **Area = `items.stage`** (the site location CLAUDE.md already pins as "site location/area") and **Room = `rm_no` + `rm_desc`** (already aliased `room_no` / `room_desc` in `items/queries.py`). Plan V1's two levels already exist as data under other names — this is a rename plus normalisation, not an invention.
`CLAUDE.md` pins `Stage` = site location/area and `Zone` = numeric sub-division
of Stage — which reads like Plan V1's Area and Room under different names.
1. `Stage` **is** Area and `Zone` **is** Room — rename and keep the data.
2. They are different concepts; Area/Room are new alongside them.
3. Retire `stage`/`zone` entirely in favour of Area/Room.

### Q546 — What happens to `level` and `zone`? *(new — forced by Q454 + the real column set)*
**Option 1 confirmed (2026-09-18).** Both are **kept as attributes, not hierarchy
levels**. The drill-down stays `Project → Area → Room → Item` exactly as Plan V1
§2 specifies; `level` (L1/L2) and `zone` remain searchable, displayable fields.

*Why this question exists:* Plan V1's hierarchy names two location levels, but
`items` carries **four** — `level`, `stage`, `zone` and `rm_no`/`rm_desc`. The
seed populates all four (`L1` / `"Stage 1"` / `"1"` / `K1`+`Kitchen`), so a
straight two-level reading would have silently dropped two of them.

### Q456 — If renamed, what happens to the "never use bare 'stage'" pin?
**Option 1 confirmed (2026-09-18).** Rename and **retire the pin**. Once the
site-location column is `area`, "stage" can only mean the lifecycle, so the
collision the rule guards against no longer exists.

> **Not yet.** The pin stays in `CLAUDE.md` until the rename actually ships —
> that file records what is true now, and today `items.stage` still means site
> location.
Renaming site-location `stage` → `area` would free the word "stage" and remove
a long-standing source of confusion with `lifecycle_stage`.
1. Rename and retire the pin.
2. Keep the pin regardless.

### Q457 — Are Areas and Rooms project-scoped or reusable?
**Option 1 confirmed (2026-09-18).** Created per project — one job's "Stage 1" has nothing to do with another's.
1. Created per project.
2. Drawn from a workspace-level library.

### Q458 — Can an item move between Rooms?
1. Yes, with audit.
2. No.

---

## §E — The stage list *(gap §4, Plan V1 §22)*

Plan V1's 14 stages are not a relabelling of today's 10. It adds Material Take,
Shop Drawing Approved, Procurement, QC, Packing, Completed; drops REQ, SM and
DOWN; and puts Painting **after** Assembly.

### Q459 — Adopt Plan V1's 14-stage list?
**Option 3 confirmed (2026-09-18).** Keep today's 10 (`REQ · SM · LISTED · DOWN · CNC · EDGED · PAINTED · MADE · DEL · INST`). The cutlist takes over the **existing** stages unchanged; Plan V1's extras arrive with the sub-projects that need them (Material Take with §19, QC with §26). **This defers Q460, Q463, Q464 and Q465** with it.
1. Yes — replace the 10 wholesale.
2. Yes, but keep REQ / SM / DOWN as well (17 stages).
3. No — keep today's 10 and treat Plan V1's extras as sub-states.

### Q460 — Where did REQ, SM and DOWN go?
1. They are dropped — the work still happens but is not a tracked stage.
2. They are renamed (say which: SM → Site Measure is obvious; REQ and DOWN
   are not).
3. They were an oversight in Plan V1 and should stay.

### Q461 — Painting order
**Option 2 confirmed (2026-09-18).** Keep today's default — `PAINTED` before `MADE`, with `items.paint_after_assembly` as the per-item opt-in. Plan V1 §22's order becomes one project type, not the rule. No migration.
Shipped default is PAINTED **before** MADE, with `items.paint_after_assembly`
(migration `0020`) as the opt-in flag. Plan V1 §22 lists Assembly → Painting.
1. Flip the default — Painting after Assembly, keep the flag for the reverse.
2. Keep today's default; Plan V1's order is just one project type.
3. Remove the flag; the order is fixed by template (Plan V1 §7).

### Q462 — Is the stage list per project/template, or global?
**Option 1 confirmed (2026-09-18).** One global `stages` lookup; projects mark inapplicable stages N/A, which is what §22 describes. Consistent with Q434 making §7's template system aspirational.
Plan V1 §7 makes workflows template-driven; today `stages` is one global
lookup table and §22 says projects "skip stages that do not apply".
1. Global list; projects mark stages N/A (closest to today).
2. Per-template stage list.
3. Per-project, freely edited.

### Q463 — Are Material Take and Shop Drawing Approved really *stages*?
Both are approval gates rather than shop-floor work; Shop Floor's kanban would
show columns no worker can action.
1. Yes — tracked stages like any other.
2. They are gates, shown in Tracking but excluded from Shop Floor.

### Q464 — Does QC get its own stage, or one per preceding stage?
§26 says QC checks "the work just completed", implying a check after several
stages, not one QC step.
1. One QC stage, after Assembly.
2. A QC checkpoint attached to each production stage.

### Q465 — What is `stage_key` for the new stages?
Existing keys are short uppercase (`REQ`, `LISTED`, `EDGED`). Naming now avoids
a rename later.
1. Propose keys and confirm them in review.
2. You will supply them.

---

## §F — Permissions, roles and departments *(gap §3.4)*

Today: a static 7 roles × 11 modules × 4 actions `dict` in
`apps/api/app/auth/permissions.py`, one role per user, no project scoping.
Plan V1 §3: 7-level scoping, 11 actions, IT-authored groups, multi-membership,
most-permissive-wins.

### Q466 — Replace the static matrix with a DB-backed engine?
**Option 2 confirmed (2026-09-18).** Yes, but scoped down to **project** only — not item, not tab. IT can configure access without a deploy; no permission check lands on every row of every list.
1. Yes — full Plan V1 model.
2. Yes, but only down to project scope (not item, not tab).
3. No — keep the static matrix; add roles as needed.

### Q467 — Do departments become an entity?
**Option 2 confirmed (2026-09-18).** No — departments stay a descriptive label; **user groups carry all permission meaning**.
`app_user.jtbd_role` is free-text, display-only and nothing branches on it.
1. Yes — a real `department` table driving dashboards and permissions.
2. No — departments are a label; groups do the work.

### Q468 — How do today's 7 auth roles map onto Plan V1's ~21 departments?
1. The 7 roles become 7 groups; departments are added alongside as labels.
2. Roles are retired entirely in favour of groups.
3. Supply an explicit mapping table.

### Q469 — The 11 actions
Today there are 4 (`read`, `write`, `approve`, `comment`). Plan V1 lists View,
Create, Edit, Delete, Approve, Reject, Release, Lock, Unlock, Override,
Configure.
1. Adopt all 11.
2. Adopt a subset (say which).
3. Keep 4 and express the rest as per-object rules in handlers, as today.

### Q470 — Which actions are "critical" (most-permissive-wins does *not* apply)?
Plan V1 §3 reserves this but does not enumerate it.
1. Lock / Unlock / Override / Configure.
2. Only Configure.
3. IT nominates them per action at runtime.

### Q471 — Per-item permissions
Plan V1 scopes down to Joinery Item and Tab. That is a permission check on
every row of every list.
1. Yes, implement it — accept the query cost.
2. Project-level is the practical floor; item-level is over-specified.

### Q472 — What becomes of the hand-written per-object rules?
`require_drafter()`, the not-uploader approve rule, creator-or-manager, the
5-minute undo window — all currently in route handlers.
1. Move into the permission engine as rules.
2. Leave in handlers; the engine covers coarse access only.

### Q473 — Does the `comment` action get a real surface?
`comment` is granted across the matrix but **no route enforces it** — there is
no comment entity (gap §4). Plan V1 §29 wants comments on 8 object types.
1. Build §29 comms; `comment` becomes real.
2. Drop the action until §29 is built.

---

## §G — Navigation and IA *(gap §3.5)*

`CLAUDE.md` states as binding: "IA is fixed to **6 primary tabs** … the primary
six do not grow", with a secondary strip for new surfaces. Q406–Q407 want
Dashboard-as-entrance with **Orderbook / Tracking / Cutlist** module workspaces.

### Q474 — **Custom decision confirmed (2026-09-18): Cutlist *is* the `List` tab.**
The existing primary `List` tab becomes the Cutlist module workspace. No seventh primary tab, no demotion to the secondary strip, and **the binding "primary six do not grow" rule stands unchanged** — so `ALIGNMENT.md` §3.5 is resolved without amending anything.

Corroborated by the existing code: the RBAC module is already named `list`, and it **already gates the cutlist surfaces** — `GET /items/{iid}/cutlist.pdf` is gated `("list", "read")` and item-attachment writes `("list", "write")`. The module named `list` has been the cutlist module all along; this names it honestly. `/list` today is a project switcher + search + the shared `ItemsTable` (`ListClient.tsx`), which becomes the cutlist list.

### Q474 (original options, superseded)
1. Amend the binding rule — primary row becomes 7 tabs including Cutlist.
2. Cutlist joins the secondary strip.
3. Cutlist is not a top-level module; it opens from an item (today's
   `/items/[id]?tab=cutlist`).

### Q475 — Do Orderbook / Tracking / Cutlist open as separate windows?
**Option 2 confirmed (2026-09-18).** Genuinely separate browser windows, matching the reference system — so Tracking and Orderbook can sit side by side on two monitors.
The reference system opens a new window per module (Q406). The shipped web app
is a single-page shell with a tab strip.
1. Tabs in one shell (today's model) — Q407 permits a new UI.
2. Genuinely separate browser windows.

### Q476 — Project Details window
Q408 puts `Project Stats / Cars / OH&S / Scope` behind an **Info** button in
Tracking. Today `ProjectDetailModal` exists with none of those tabs, and
`/projects/[id]` is a separate page.
1. Add the four tabs to the existing `ProjectDetailModal`.
2. Build the separate window and retire `/projects/[id]`.
3. Keep both surfaces; they share one record per Q409.

### Q477 — What are Cars and OH&S?
Neither appears anywhere in this codebase or in `legacy/`.
1. Site vehicle allocation and workplace-safety records — specify them.
2. Out of scope; drop the tabs.

### Q478 — Does the Dashboard become the only entrance?
`/home` currently redirects to `/dashboard`, which is already the landing page.
1. Yes — matches today; formalise it.
2. Users should be able to deep-link into any module directly (today's
   behaviour too).

---

## §H — Project files and SharePoint *(gap §3.3)*

Sub-project #5a built `file_blob`: workspace-scoped, sha256-deduped, local disk
behind a `FileStore` Protocol. Q398–Q400 put project-level files in SharePoint,
view-only, auto-refreshing.

### Q479 — Does `file_blob` survive?
1. Yes — SharePoint is an **additional** surface for project-level files only;
   shop drawings, item attachments and sample photos stay on `file_blob`.
2. No — everything moves to SharePoint.
3. Undecided; start with option 1 and revisit.

### Q480 — What is the SharePoint tenant / site / library?
Q398 records that no site URL or document-library path has been supplied.
1. Supply them now.
2. Configurable per workspace at deploy time.

### Q481 — How does the app authenticate to Microsoft 365?
Q394 records that the permission mapping is undefined.
1. App-only (client credentials) — the app sees all project folders; in-app
   permissions are the only gate.
2. Delegated (per user) — each user sees what SharePoint lets them see.
3. Unknown; needs a spike.

### Q482 — How does the pop-up "automatically update" (Q400)?
No push channel exists today; the stack has no websockets and no client cache.
1. Poll every N seconds while the pop-up is open (say N).
2. Microsoft Graph change notifications (webhook) — needs a public callback URL.
3. Manual refresh is acceptable after all.

### Q483 — What happens when SharePoint is unreachable?
1. Show an error in the pop-up; the rest of the app is unaffected.
2. Fall back to a cached listing.

### Q484 — Are architectural drawings in the same `site related` folder?
Q402 says all architectural drawings for a project are in one common folder;
Q398 names `site related` for project-level files. It is not stated whether
these are the same folder.
1. Same folder.
2. Different folder — name it.

### Q485 — Drawing-number matching rules (Q403)
"Filename contains the drawing number" needs a rule before it can be coded.
1. Substring match, case-insensitive.
2. A filename pattern — supply it (e.g. `{number}-{rev}-{title}.pdf`).
3. Regex, IT-configurable.

### Q486 — Mixed numeric/letter revisions (Q405's open edge case)
Q405 leaves ordering undefined for mixed schemes and multi-letter revisions.
1. Letters sort after numbers.
2. Numbers after letters.
3. Never mixed within one project — reject/flag if seen.
4. Multi-letter: `AA` follows `Z` (spreadsheet-column order).

---

## §I — Tender, handover, financials

Today: `/estimating` with `draft → sent → accepted|rejected|expired|withdrawn`
and a one-shot `POST /revisions/{rid}/convert`. No contract value, no
variations, no pre-quote stages.

### Q487 — Does the Tender Dashboard replace or precede `/estimating`?
1. Tender wraps it — the existing estimate becomes one step of the 12-stage
   tender lifecycle.
2. Separate module; `/estimating` stays for non-tender quoting.
3. Tender replaces `/estimating` entirely.

### Q488 — Adopt the full 12-stage tender lifecycle?
1. Yes — all 12, extending `_LEGAL_TRANSITIONS`.
2. A subset (say which).
3. Keep today's 6 states.

### Q489 — Do Preliminary Joinery Items become real items on handover?
Estimate lines currently do **not** become items on convert.
1. Yes — handover creates items from the preliminary ones.
2. No — the PM creates items fresh.

### Q490 — Does handover get a review-and-select step (Plan V1 §6)?
Convert is currently one click.
1. Yes — a PM review screen choosing what transfers.
2. No — keep one-click.

### Q491 — Where does Contract Value live?
1. A new column on `projects`, set at handover, never overwritten.
2. A separate `project_contract` table with a full value history.

### Q492 — Financial granularity
§16 says Project + Joinery Item level, not component level.
1. Confirmed — item level, no part-level costing.
2. Cutlist level too (if §B makes cutlist the workflow owner).

### Q493 — Where do actual costs come from?
Nothing in the system currently records a cost event.
1. From procurement (received quantities × price) plus labour from Shop Floor
   completions × `workspace_labour_rate`.
2. Manual entry by Accounts.
3. An accounting integration (Xero/MYOB, §33).

### Q494 — Do variations affect an already-released Production Pack?
1. Yes — an approved variation forces a new controlled release (§24).
2. No — they are independent.

---

## §J — Material Take and Material Summary *(Plan V1 §19–§20)*

Nothing exists. Today material demand *is* `parts` + `item_hardware_lines`, and
`/procurement-queue` aggregates them live with no confirm-and-release gate.

### Q495 — Is Material Take a new entity, or a state of the existing lines?
**Option 1 confirmed (2026-09-18).** A new `material_take` entity, generated from the item's parts + hardware lines then adjusted, approved and frozen — so it can diverge from the live lines, which is what §19's post-change impact review needs to compare against.
1. New `material_take` entity, generated from parts/hardware, then adjusted.
2. A snapshot/approval flag on today's lines.

### Q496 — What generates the take?
**Option 3 confirmed (2026-09-18).** Both — parts + hardware lines give the demand, and the CutPlan nest gives real sheet counts including offcut waste.
Q80 confirms "system-generated starting point + manual control".
1. From the item's parts + hardware lines (today's data).
2. From the CutPlan optimiser's nest (which already knows sheet counts).
3. Both.

### Q497 — Does Material Take gate Shop Drawing Approved?
**Option 2 confirmed (2026-09-18).** Advisory — the approver is warned that no take exists but may proceed. #5a's `draft → pending → approved` flow is unchanged.
§19 says it occurs *before* approval.
1. Hard gate — cannot approve the drawing without an approved take.
2. Advisory only.

### Q498 — Does the Material Summary replace `/procurement-queue`?
**Option 2 confirmed (2026-09-18).** Both exist — the queue stays the live view for early visibility; the summary is the formal released artefact.
1. Yes — the queue becomes the released summary.
2. No — both exist; the queue stays the live view.

### Q499 — Does PM confirmation become a hard gate on procurement?
**Option 2 confirmed (2026-09-18).** Advisory — Procurement may order against unconfirmed lines when lead times demand it, flagged as such.
§20 says "only after PM confirmation is the summary released".
1. Yes — Procurement cannot order unconfirmed material.
2. Advisory — Procurement can order early with a warning.

### Q500 — How are stale summary lines flagged (§20)?
**Option 2 confirmed (2026-09-18).** Version the take; the summary records which version it consumed and flags when that version advances. Gives §19's impact review a concrete before/after to diff.
1. Compare against the source take's `updated_at`; flag on drift.
2. Version the take; flag when the version advances.

### Q501 — Does `/optimise` start consuming stock?
**Option 1 confirmed (2026-09-18).** Keep #9's pure-function invariant. Reservation becomes its own explicit action — Q544 is already porting `quantity_reserved` onto `board_inventory` to support it.
#9's pure-function invariant is explicit: `/optimise` reads `board_inventory`
and never reserves or decrements it. §18 wants reservations.
1. Keep the invariant — reservation is a separate, explicit action.
2. Material Take reserves stock.
3. Cut-plan completion decrements stock.

---

## §K — Orderbook and order forms *(Plan V1 §21, Q425–Q431)*

`procurement_v1` has batches + allocations but **no order entity, no PO, no
order-details form** on the v1 surface. The legacy `/procurement/*` namespace
has orders, vendors, budget and approvals but `CLAUDE.md` records it as unused
by v1.

### Q543 — Where does the parent item's cost live? *(new — forced by Q451 + Q542)*
**Option 3 confirmed (2026-09-18).** Defer until §16 is scoped. **This makes Q451 a statement of intent, not behaviour in this sub-project** — related-part orders carry cost, and nothing rolls up to the parent item yet.
Q451 rolls related-part order cost into the parent Joinery Item, but there is no
item cost column today, and §16 (financials) is not scoped.
1. **Add a derived item cost** — computed on read from linked orders, stored
   nowhere. No new truth to keep in sync; costs are always current.
2. **Add a stored item cost**, updated when a linked order changes. Cheap to
   query and report on, but a second place cost can be wrong.
3. **Defer** — related-part orders carry cost, nothing rolls up until §16 is
   scoped. Q451 then describes intent rather than this sub-project's behaviour.

### Q502 — Is the legacy `/procurement/*` namespace the basis for the order forms?
**Option 1 confirmed (2026-09-18).** Revive and converge the legacy namespace rather than building fresh.
1. Yes — revive and converge it (as #7a did for catalogs).
2. No — build fresh in `procurement_v1` and retire the legacy namespace.
3. Keep them separate.

### Q544 — Legacy `inventory` vs `board_inventory` *(new — forced by Q502 + migration 0025)*
**Option 1 confirmed (2026-09-18).** Keep `board_inventory`; drop legacy `inventory` + `inventory_movements`. Port `quantity_reserved`, `reorder_point` and `reorder_quantity` onto it, and revive only the PO/vendor half of the legacy namespace. Nothing in #9/0025's surface changes.
Reviving the legacy namespace brings `inventory` + `inventory_movements`, which
duplicate `board_inventory` (0025). Two tables for sheet stock is the situation
#7a retired for `/catalogs`.
1. **Keep `board_inventory`, drop legacy `inventory`** — port the columns worth
   having (`quantity_reserved`, `reorder_point`, `reorder_quantity`) onto it,
   and revive only the PO/vendor half of the legacy namespace.
2. **Keep legacy `inventory`, retire `board_inventory`** — it is the richer
   table, but `/optimise`, `StockPanel` and the Sheet Stock tab all read
   `board_inventory` today, so all of #9/0025's surface would be rewritten.
3. **Keep both, different jobs** — `board_inventory` for sheet stock the
   optimiser nests against, legacy `inventory` for general consumables.
   Avoids a migration but leaves two stock tables to reconcile later.

### Q503 — Are order-details forms per material type?
**Option 3 confirmed (2026-09-18).** One generic form with fixed columns for shared fields plus a JSONB attributes blob for type-specific ones.
Screenshots 07–09 show three quite different field sets.
1. One form with conditional sections per type.
2. Separate forms per type.
3. One generic form plus a free-form attributes blob.

### Q504 — How does an order relate to a procurement batch?
**Option 2 confirmed (2026-09-18).** Orders are the commercial layer; `procurement_batches` + `batch_allocations` remain beneath as the allocation mechanism, preserving #4's single-join availability query.
1. An order *is* a batch (rename and extend).
2. Orders are new; batches remain the allocation mechanism beneath them.

### Q505 — Does "Create PO" (screenshot 07) create a real PO entity?
**Option 1 confirmed (2026-09-18).** Yes — a real PO with number, supplier, lines and status, which reviving legacy `purchase_orders` + `po_line_items` supplies directly.
1. Yes — a PO entity with number, supplier, lines, status.
2. It just marks the order issued and records a number.

### Q506 — Does Supplier become an entity on the v1 surface?
**Option 1 confirmed (2026-09-18).** Yes — a supplier table, with the 6 catalog tables' free-text supplier columns repointed to it.
Supplier is free text on catalog rows today (`supplier`, `default_supplier`).
§21 wants comparison, performance and five statuses.
1. Yes — a `supplier` table, and catalog rows repoint to it.
2. Not yet — free text is fine until supplier performance is built.

### Q507 — Can non-related-part items also have orders?
**Option 2 confirmed (2026-09-18).** Orders cover **all** procurement — board, hardware and related parts alike; batches become the internal allocation detail.
Q417 attaches order numbers to related parts. Board and hardware for normal
items flow through batches instead.
1. Orders are for related parts only.
2. Orders cover all procurement; batches become an internal detail.

---

## §L — Locking, concurrency and rollback *(Plan V1 §11–§12, §39)*

Today: an advisory item soft-lock (non-owner saves are permitted and audited as
`item.lock_overridden`), **no optimistic concurrency control anywhere**, and
`item_edit_log` storing `varchar(255)` old/new values per field — enough to
display history, not to restore state.

### Q508 — Adopt the three lock types?
**Option 1 confirmed (2026-09-18).** All three — Hard, Controlled and Approval.
1. All three (Hard / Controlled / Approval).
2. Approval Lock only — auto-lock on approve is the common case.
3. Keep today's advisory lock.

### Q509 — What happens to the existing soft-lock?
**Option 1 confirmed (2026-09-18).** It becomes a **Controlled Lock** — override-with-audit becomes request-and-approve. The existing `item.lock_overridden` audit event is the evidence that people do override in practice.
1. Becomes Controlled Lock (request + approve, instead of override + audit).
2. Stays as a fourth, weakest kind.
3. Removed.

### Q510 — At what granularity does locking apply?
**Option 2 confirmed (2026-09-18).** Item and project only — no field, tab, Area, revision or department locks.
§12 lists fields, components, items, areas, projects, tabs, revisions and
departments.
1. All of them.
2. Item and project only.

### Q511 — Add optimistic concurrency control?
**Option 2 confirmed (2026-09-18).** Only where conflicts actually hurt. **Named surfaces: the item editor, the cutlist, and orders.** Everything else stays last-write-wins.
Q364–Q378's conflict resolution is unimplementable without it, and it touches
all 181 existing endpoints.
1. Yes — version column + `If-Match` on every mutating route, now.
2. Only on the surfaces where conflicts actually hurt (name them).
3. No — last-write-wins is acceptable; drop Q364–Q378.

### Q512 — Field-level conflict detection (Q366 locks only conflicting fields)
**Option 1 confirmed (2026-09-18).** True field-level, with per-field versioning, on the three Q511 surfaces.
1. True field-level — requires per-field versioning.
2. Row-level is sufficient; lock the whole record.

### Q513 — The 20-state rollback (§11)
**Option 3 confirmed (2026-09-18).** Drop rollback. `audit_log` + `item_edit_log` remain the record of who changed what; no restore capability is built.
1. Full object snapshots per change (storage cost, real rollback).
2. Keep field-level deltas and reconstruct (cheaper, fragile).
3. Drop rollback; history-for-display is enough.

### Q514 — Does rollback apply to everything, or nominated objects?
1. Every significant object.
2. Items and drawings only.

---

## §M — QC, rework, delivery, packing *(Plan V1 §26–§28)*

### Q515 — Is QC a new module?
1. Yes — a `qc` RBAC module, defect entity, checklists.
2. QC is a stage on the existing workflow with a defect list attached.

### Q516 — Internal Rework vs Full Rework (§26)
1. Two entity types.
2. One `rework` entity with a `kind` field.

### Q517 — Does rework re-open the workflow?
1. Yes — the item returns to an earlier stage.
2. No — rework is a parallel record; the original stages stay complete.

### Q518 — Does the QC-timing rule get enforced?
§26: before Listing QC need not know; after Listing but before Assembly the
Lister updates the cutlist; after Assembly it is Internal Rework.
1. Enforce automatically from the item's current stage.
2. Guidance only; QC picks.

### Q519 — Packing (§22, §27)
1. A tracked stage with scanning.
2. A stage only, no scanning yet.

---

## §N — Notifications, comms, tasks, search, reporting, KPIs

All absent. Each is a sub-project in its own right.

### Q520 — Which comes first?
Rank: Notifications (§30) · Comms (§29) · Tasks (§10) · Search (§13) ·
Reporting (§31) · KPIs (§32).

### Q521 — Notification channels for v1
1. In-app only.
2. In-app + email.
3. In-app + email + push (needs a mobile app — see §P).

### Q522 — Email transport
Nothing is configured today.
1. SMTP.
2. A provider (name it).
3. Microsoft 365 / Graph (consistent with §H).

### Q523 — Do comments support @mentions and notifications on day one?
1. Yes.
2. Comments first, mentions later.

### Q524 — Are tasks a real entity or a view over existing work?
1. A `task` table with assignment, due date, status.
2. A derived view over stages, defects and approvals.

### Q525 — Search implementation
1. Postgres full-text search (no new infrastructure).
2. A search service (Elastic/Meili) — new container.
3. Per-module filters are enough; drop global search.

### Q526 — External report sharing (§31)
Secure links with password, expiry, revoke and access tracking, for recipients
with no accounts.
1. Build it as specified.
2. PDF email attachments only for v1.

### Q527 — Are KPIs formulas-as-data (§32: "IT defines KPI formulas")?
1. Yes — a formula engine IT edits at runtime.
2. Hard-coded KPIs, management chooses which to show.

---

## §O — Templates, validation, initiatives *(Plan V1 §7–§8, §35–§38)*

~99 confirmed decisions (Q253–Q351) describing template versioning, mandatory
validation, reusable simulations, a technical-debt register, an initiative
tracker and a priority-aware escalation engine. Nothing exists, and nothing in
the daily joinery workflow depends on it.

### Q528 — Is this in scope at all?
1. Yes — it is why Plan V1 exists.
2. Later — after the joinery workflow is complete.
3. No — over-engineered for one company; drop it.

### Q529 — If in scope, what does a template actually configure?
1. Workflow stages + tasks + QC checklists + approvals + permissions
   (everything §7 lists).
2. Workflow stages only, to start.

### Q530 — Who is "IT" here?
The `admin` auth role, a real IT department, or a vendor?
1. The `admin` role.
2. A new `it_admin` role distinct from `admin`.
3. Us (the build team), not a customer role.

### Q531 — Do the Initiative and technical-debt trackers belong in this product?
They are a general-purpose issue tracker.
1. Yes — build them.
2. No — use an external tracker (Jira/Linear/GitHub) and drop Q260–Q289.

---

## §P — Platform

### Q532 — Mobile: responsive web or native app?
§14 wants offline work with sync; §30 wants push. Both are hard in a web app.
The stack is server-rendered Next.js with no client cache by design.
1. Responsive web only — drop offline and push.
2. Responsive web + PWA (offline-ish, push on Android).
3. A native app for site use.

### Q533 — How important is offline (§14)?
Offline-with-sync and conflict resolution is among the most expensive items in
the document.
1. Essential — site has no reception.
2. Nice to have.
3. Drop it.

### Q534 — QR/barcode (§15): what gets labelled?
1. Each Joinery Item.
2. Each cutlist.
3. Each part/component.
4. Each packed crate.

### Q535 — Which integration is genuinely next (§33)?
Cabinet Vision is built. §33 lists ~16 others, and §H already depends on
Microsoft 365.
1. Microsoft 365 / SharePoint (required by §H).
2. Xero or MYOB (required by §16's actual costs).
3. Excel import/export.
4. None yet.

---

## Housekeeping

### Q536 — Does `plan_v1.md` stay canonical in this repo?
It is committed at `docs/plan-v1/plan_v1.md`.
1. Yes — it is the authoritative source; update it in place as questions are
   answered.
2. It is a snapshot; the canonical copy lives elsewhere.

### Q537 — Where do answers land?
1. Back into `plan_v1.md` as new `### Q4xx` sections (its existing convention).
2. Into a separate decisions log.

### Q538 — Do the nine existing sub-project plans get re-headed?
`docs/superpowers/plans/README.md` requires a status header on every plan.
Plans that Plan V1 supersedes are currently marked simply "shipped".
1. Add a `> **Later change:** superseded by Plan V1 §x` blockquote to each
   affected plan.
2. Leave them; `ALIGNMENT.md` carries the cross-reference.

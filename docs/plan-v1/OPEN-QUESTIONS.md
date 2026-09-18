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

That combination raises two questions the original set did not contain, added
below as **Q539** (late linking) and **Q540** (migrating `items.num`).

---

## §A — Scope and intent (answer these first)

### Q432 — Create Order authority *(Plan V1's own next question)*
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
1. System-allocated sequential on creation in the Cutlist panel.
2. Manually entered by the Drafter.
3. System-suggested, manually overridable.

### Q443 — Are cutlist numbers unique company-wide or per project?
Six digits across all projects implies a company-wide sequence.
1. Company-wide unique.
2. Unique per project.

### Q444 — Can a cutlist span more than one project?
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
An undo currently reverses one item's stage completion.
1. Undo reverses the whole cutlist's stage completion.
2. Undo is per item even where completion is shared (inconsistent — flag it).

---

## §C — Related-part rows *(gap §3.2)*

Q416–Q424 introduce metal / benchtop / cushion rows: own Item ID, parent's
Group ID, no cutlist, no stages, order number in the cutlist column. Today
`items.group_id` is an unused free-text `varchar(32)`.

### Q447 — Are related parts rows in `items`, or a new table?
1. Rows in `items` with a `row_type` discriminator and a self-FK parent.
2. A new `related_part` table.
3. Reuse `modules`/`parts` (they already hang off an item) — but those are
   cutlist components, not orderable parts.

### Q448 — Is the related-part list fixed at metal / benchtop / cushion?
1. Fixed — exactly those three.
2. A configurable lookup list.
3. Free-text type.

### Q449 — Can a related part have its own related parts?
1. No — one level only.
2. Yes, arbitrary nesting.

### Q450 — What is a related part's status and priority?
Q419 empties the workflow-stage area but says nothing about the
`CLEAR / VOID / NOTE! / LIVE / APPROVED / HOLD` status.
1. Related parts carry their own status.
2. They inherit the parent's status.
3. They have no status.

### Q451 — Does a related part carry cost?
Relevant to §16's item-level financials.
1. Yes — its order's cost rolls into the parent item's cost.
2. Yes — it is costed separately at project level.
3. No.

### Q452 — Can a related part be moved to a different parent?
1. Yes, with audit (and Q431-style order reference updates).
2. No — delete and recreate.

### Q453 — Existing `items.group_id` data
Seeded and legacy rows carry free-text values.
1. Repurpose the column for the new Group ID semantics; migrate existing values.
2. Leave it alone; add a new column.

---

## §D — Area and Room *(gap §4, Plan V1 §2)*

Plan V1's drill-down is `Project → Area → Room → Joinery Item`. Today `items`
carries free-text `stage` (site location), `zone`, `level`, `rm_no`, `rm_desc`
and there are no Area or Room tables.

### Q454 — Do Area and Room become real entities?
1. Yes — both, with their own tables and FKs from `items`.
2. Area only; Room stays free-text on the item.
3. Neither — keep today's free-text columns and treat Area/Room as labels.

### Q455 — How does this map onto the existing terminology pins?
`CLAUDE.md` pins `Stage` = site location/area and `Zone` = numeric sub-division
of Stage — which reads like Plan V1's Area and Room under different names.
1. `Stage` **is** Area and `Zone` **is** Room — rename and keep the data.
2. They are different concepts; Area/Room are new alongside them.
3. Retire `stage`/`zone` entirely in favour of Area/Room.

### Q456 — If renamed, what happens to the "never use bare 'stage'" pin?
Renaming site-location `stage` → `area` would free the word "stage" and remove
a long-standing source of confusion with `lifecycle_stage`.
1. Rename and retire the pin.
2. Keep the pin regardless.

### Q457 — Are Areas and Rooms project-scoped or reusable?
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
1. Yes — replace the 10 wholesale.
2. Yes, but keep REQ / SM / DOWN as well (17 stages).
3. No — keep today's 10 and treat Plan V1's extras as sub-states.

### Q460 — Where did REQ, SM and DOWN go?
1. They are dropped — the work still happens but is not a tracked stage.
2. They are renamed (say which: SM → Site Measure is obvious; REQ and DOWN
   are not).
3. They were an oversight in Plan V1 and should stay.

### Q461 — Painting order
Shipped default is PAINTED **before** MADE, with `items.paint_after_assembly`
(migration `0020`) as the opt-in flag. Plan V1 §22 lists Assembly → Painting.
1. Flip the default — Painting after Assembly, keep the flag for the reverse.
2. Keep today's default; Plan V1's order is just one project type.
3. Remove the flag; the order is fixed by template (Plan V1 §7).

### Q462 — Is the stage list per project/template, or global?
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
1. Yes — full Plan V1 model.
2. Yes, but only down to project scope (not item, not tab).
3. No — keep the static matrix; add roles as needed.

### Q467 — Do departments become an entity?
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

### Q474 — Where does the Cutlist module go?
1. Amend the binding rule — primary row becomes 7 tabs including Cutlist.
2. Cutlist joins the secondary strip.
3. Cutlist is not a top-level module; it opens from an item (today's
   `/items/[id]?tab=cutlist`).

### Q475 — Do Orderbook / Tracking / Cutlist open as separate windows?
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
1. New `material_take` entity, generated from parts/hardware, then adjusted.
2. A snapshot/approval flag on today's lines.

### Q496 — What generates the take?
Q80 confirms "system-generated starting point + manual control".
1. From the item's parts + hardware lines (today's data).
2. From the CutPlan optimiser's nest (which already knows sheet counts).
3. Both.

### Q497 — Does Material Take gate Shop Drawing Approved?
§19 says it occurs *before* approval.
1. Hard gate — cannot approve the drawing without an approved take.
2. Advisory only.

### Q498 — Does the Material Summary replace `/procurement-queue`?
1. Yes — the queue becomes the released summary.
2. No — both exist; the queue stays the live view.

### Q499 — Does PM confirmation become a hard gate on procurement?
§20 says "only after PM confirmation is the summary released".
1. Yes — Procurement cannot order unconfirmed material.
2. Advisory — Procurement can order early with a warning.

### Q500 — How are stale summary lines flagged (§20)?
1. Compare against the source take's `updated_at`; flag on drift.
2. Version the take; flag when the version advances.

### Q501 — Does `/optimise` start consuming stock?
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

### Q502 — Is the legacy `/procurement/*` namespace the basis for the order forms?
1. Yes — revive and converge it (as #7a did for catalogs).
2. No — build fresh in `procurement_v1` and retire the legacy namespace.
3. Keep them separate.

### Q503 — Are order-details forms per material type?
Screenshots 07–09 show three quite different field sets.
1. One form with conditional sections per type.
2. Separate forms per type.
3. One generic form plus a free-form attributes blob.

### Q504 — How does an order relate to a procurement batch?
1. An order *is* a batch (rename and extend).
2. Orders are new; batches remain the allocation mechanism beneath them.

### Q505 — Does "Create PO" (screenshot 07) create a real PO entity?
1. Yes — a PO entity with number, supplier, lines, status.
2. It just marks the order issued and records a number.

### Q506 — Does Supplier become an entity on the v1 surface?
Supplier is free text on catalog rows today (`supplier`, `default_supplier`).
§21 wants comparison, performance and five statuses.
1. Yes — a `supplier` table, and catalog rows repoint to it.
2. Not yet — free text is fine until supplier performance is built.

### Q507 — Can non-related-part items also have orders?
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
1. All three (Hard / Controlled / Approval).
2. Approval Lock only — auto-lock on approve is the common case.
3. Keep today's advisory lock.

### Q509 — What happens to the existing soft-lock?
1. Becomes Controlled Lock (request + approve, instead of override + audit).
2. Stays as a fourth, weakest kind.
3. Removed.

### Q510 — At what granularity does locking apply?
§12 lists fields, components, items, areas, projects, tabs, revisions and
departments.
1. All of them.
2. Item and project only.

### Q511 — Add optimistic concurrency control?
Q364–Q378's conflict resolution is unimplementable without it, and it touches
all 181 existing endpoints.
1. Yes — version column + `If-Match` on every mutating route, now.
2. Only on the surfaces where conflicts actually hurt (name them).
3. No — last-write-wins is acceptable; drop Q364–Q378.

### Q512 — Field-level conflict detection (Q366 locks only conflicting fields)
1. True field-level — requires per-field versioning.
2. Row-level is sufficient; lock the whole record.

### Q513 — The 20-state rollback (§11)
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

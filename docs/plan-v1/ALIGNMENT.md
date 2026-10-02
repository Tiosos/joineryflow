# Plan V1 vs. shipped JoineryFlow — alignment record

> **Status: re-scored 2026-10-02 against the tree at Alembic `0047`.** This file
> began as analysis only (2026-09-18, "no code has been written against Plan V1").
> That is no longer true: Plan V1 is the roadmap for this codebase (Q433) and a
> large part of it is now built — Cutlist + related parts + Orderbook (#10), Global
> Search (#11), Material Take → Summary (#12), the Dynamic RBAC engine, the tender
> lifecycle + financials (§I), QC / Rework / Packing (§M), locking + concurrency
> (§L), PO generation, comments and the QC Dashboard. `CLAUDE.md` has a section for
> each and is the record of what is true.
>
> **What was re-scored.** In §4, the **37 rows that built work moved** carry their
> new verdict and a description of what shipped (with the migration or Q-number
> that explains it); the rest keep their 2026-09-18 wording on purpose, rather than
> being churned. **§3 and §6 are still the 2026-09-18 narrative** — the sequencing
> and the "next to build" language there is history; each carries a note saying so.
> §5's tally is recounted.
> Source of truth for the target: [`plan_v1.md`](./plan_v1.md) (canonical,
> committed verbatim as supplied 2026-09-17, questions answered through Q431).
> Source of truth for what exists today: `CLAUDE.md` at the repo root, and the
> code itself. Where this document and the code disagree, the code is right.

## 1. What this document is

Plan V1 describes a **company-wide joinery workflow and control platform**.
The repository currently holds **JoineryFlow**: the nine sub-projects it
had on 2026-09-18 (Foundation → PM Workbench → Procurement Workbench → Shop
Drawings → PDF Generation → iSample → Catalog/CV Import/Cut Floor → Shop Floor →
Estimating → CutPlan Optimiser, then at Alembic head `0025`) **plus** the Plan V1
builds listed in the banner above, at Alembic head `0047`.

The two overlap substantially but are **not** the same system, and Plan V1 is
not a superset — in five places it *contradicts* a shipped invariant rather
than extending it. This file maps every Plan V1 section onto current state and
names those contradictions, so that scoping conversations start from evidence
instead of from either document's own optimism.

**It does not authorise any of this work.** Every row marked `REARCH` or
`ABSENT` is a question, not a backlog ticket. Open questions are tracked in
[`OPEN-QUESTIONS.md`](./OPEN-QUESTIONS.md), numbered from Q432 to continue
Plan V1's own sequence.

## 2. Verdict key

| Verdict | Meaning |
| --- | --- |
| `SHIPPED` | Exists in the tree and broadly matches Plan V1's intent. |
| `PARTIAL` | Something real exists; Plan V1 asks for materially more. |
| `ABSENT` | Nothing in the tree. Additive — no shipped invariant is threatened. |
| `REARCH` | **Plan V1 contradicts a shipped invariant.** Cannot be added without changing existing schema, code or a documented rule. |

## 3. The five structural conflicts — all now decided

> **Since built (2026-10-02).** Conflicts 3.1, 3.2, 3.4 and the Area / Room row
> below were **built** (`0026`–`0030`, `0037`); 3.5 closed as decided; 3.3 stays
> bounded and blocked on customer input; the stage-list row stands with Packing as
> the first addition (`0039`). The text in this section is the 2026-09-18
> analysis and decision record — read the *outcome* in `CLAUDE.md`'s Plan V1
> table, not "built next" below.

These were the decisions that had to be made before sequencing was meaningful.
**All five are settled**, along with the two narrower ones named in §4:

| # | Conflict | State after the decisions |
| --- | --- | --- |
| 3.1 | Cutlist owns the workflow | **Accepted, scoped** — built next (Q438) |
| 3.2 | Related-part rows | **Accepted, scoped** — built next (Q447) |
| 3.3 | Project files in SharePoint | **Bounded** — additive; `file_blob` survives (Q479) |
| 3.4 | RBAC as data | **Bounded** — project scope only, not item/tab (Q466) |
| 3.5 | Navigation / Cutlist module | **Closed** — it is the `List` tab (Q474) |
| — | Area / Room as entities | **Accepted** — a rename of existing columns (Q455) |
| — | 10 vs 14 lifecycle stages | **Deferred** — today's 10 stand (Q459) |

Nothing in this section is now an open question. The per-conflict analysis
below is kept because it explains *why* each looked hard and what the decision
has to cope with.

### 3.1 The Cutlist becomes the workflow-owning entity (`REARCH` — **accepted 2026-09-18**)

> **Decided.** The cutlist becomes a first-class entity (Q438), numbers are
> system-allocated and company-wide unique (Q442/Q443), one project per cutlist
> (Q444). `item_stages` **stays per-item as a projection**, written by fan-out
> on completion (Q439) — so the rewrite is smaller than this analysis feared.
> Shop Floor re-keys to `(cutlist_id, stage_key)` for production and
> `(item_id, 'INST')` for installation (Q445); undo reverses a whole cutlist
> (Q446). A late-linked item leaves earlier stages blank (Q539). Existing
> `items.num` values each become their own cutlist's number (Q540), sharing one
> sequence with Item IDs (Q541).

Plan V1 Q410–Q413 is the largest single conflict in the document.

- **Plan V1:** a *cutlist number* is a six-digit company-internal reference,
  created in a Cutlist panel, then linked to **one or several** Joinery Items
  (Q410). One Joinery Item links to **at most one** cutlist (Q411). All items
  sharing a cutlist share **one production workflow** — each production stage
  is completed **once against the cutlist** and reflected across every linked
  item, with a shared completion date/time (Q412). Delivery is shared too;
  installation is per-item (Q413, Q415).
- **Shipped today:** the lifecycle lives on `item_stages (item_id, stage_key,
  due_date, done_date)` — strictly per-item (`db/alembic/versions/0001_tracking_port.py:268`).
  `items.num` is a `UNIQUE NOT NULL integer` that the UI renders as the
  CUTLIST number and links to `/items/[id]`. There is no cutlist entity; the
  cutlist *is* the item. Shop Floor (`worker_assignment`,
  `stage_completion_log`, migration `0020`) keys assignment and completion off
  `(item_id, stage_key)` throughout, including the partial unique index
  `uniq_active_assignment`.

**Consequence.** Adopting Q412 means a new `cutlist` entity, repointing
`item_stages` → `cutlist_stages`, and reworking the whole of Shop Floor Ops
(#8) — assignment, mark-done, the 5-min undo window, the kiosk, and the
`prior_stages_done()` ordering check — to operate on a cutlist rather than an
item. It also splits the lifecycle in two: production + delivery stages on the
cutlist, installation on the item. This is not a migration; it is a rewrite of
sub-project #8 and a reshape of #2.

### 3.2 Related-part rows are a new row class in Tracking (`REARCH` — **accepted 2026-09-18**)

> **Decided.** Rows in `items` with a `row_type` discriminator and a
> self-referencing parent FK (Q447); type list is a configurable lookup
> (Q448); one level of nesting only (Q449); own status (Q450); reparenting
> allowed with audit (Q452); `group_id` repurposed and its values migrated
> (Q453 — and it is written by nothing today, so that migration is a near
> no-op). **The measured cost is 50 SQL call sites across 13 modules**, which
> wants a shared helper rather than 50 hand-edited predicates.

- **Plan V1** Q416–Q423: each Joinery Item has a unique internal number used as
  **both** its Item ID and Group ID. Metal, benchtop and cushion **related
  parts** are separate rows with their own Item ID sharing the parent's Group
  ID; they get **no cutlist number** and **no workflow stages at all** (Q419);
  their cutlist column instead shows the **issued supplier order number**
  (Q417), which links into Orderbook (Q418); they render nested under the
  parent, collapsed by default (Q420–Q422).
- **Shipped today:** `items.group_id` is a free-text `varchar(32)` with no FK,
  no parent/child semantics and nothing reading it for hierarchy. Every row in
  `ItemsTable` is a full item with a stage strip. There is no row-type
  discriminator.

**Consequence.** Needs a row-type column plus a real self-referencing parent
link, conditional rendering of the stage strip, and a conditional meaning for
the leftmost reference column. It also interacts with 3.1: if the cutlist owns
the workflow, a related part is exactly "an item with no cutlist", which may
make the two changes cheaper together than separately.

### 3.3 Project files move to SharePoint, read-only (`REARCH` — **bounded 2026-09-18**)

> **Decided, and the blast radius is contained.** `file_blob` **survives** and
> keeps serving shop drawings, item attachments and sample photos; SharePoint
> is an **additional** surface for project-level files only (Q479). So nothing
> shipped in #5a/#5b/#5c is rewritten. Auth is app-only (Q481), the pop-up
> polls while open (Q482), an outage falls back to a stale-marked cached
> listing (Q483), drawings live in their own folder (Q484), matched by a
> filename pattern (Q485) with mixed revision schemes flagged rather than
> guessed (Q486).
>
> **Still blocked on three inputs**: the SharePoint site URL and library
> (Q480), a real drawing filename (Q547), and the drawings folder name (Q484).

- **Plan V1** Q391–Q405: project-level files live in a SharePoint folder named
  `site related` inside each project's folder (Q398). The in-app pop-up is
  **view-only** — no upload, replace, rename or delete controls (Q399);
  mutation happens in OneDrive. The pop-up auto-refreshes when the folder
  changes (Q400). Architectural drawings live in one common per-project folder;
  clicking a drawing reference number **locates** the matching file by filename
  and the user clicks it to open (Q401–Q403), resolving to the highest
  numeric / latest alphabetical revision (Q404–Q405).
- **Shipped today:** sub-project #5a built the opposite — `file_blob`,
  workspace-scoped, sha256-deduped, stored on local disk via `LocalDiskStore`
  behind a `FileStore` Protocol (`FILE_STORE_ROOT`, default `/uploads`, a named
  docker volume), with `POST /files` doing magic-byte sniffing and a 25 MB cap,
  and `GET /files/{id}` streaming workspace-isolated. Shop drawings, item
  attachments (#5b) and iSample photos (#5c) all sit on it.

**Consequence.** Q399 does not replace `file_blob` — shop drawings, item
attachments and sample photos still need it. It adds a **second, external,
read-only** document surface for project-level files with a different identity
model, different permissions (Q394 admits the Microsoft 365 permission mapping
is undefined) and a live-sync requirement. The `FileStore` Protocol is the
right seam, but Q400's push-refresh has no counterpart in the current polling-
free architecture.

### 3.4 RBAC becomes data, not code (`REARCH` — **bounded 2026-09-18**)

> **Decided, and deliberately narrower than §3.** The engine becomes DB-backed
> with groups and multi-membership but is scoped to **project level only** —
> **not item, not tab** (Q466), so no permission check lands on every row of
> every list. Departments stay labels; groups carry the meaning (Q467), and
> today's 7 roles become 7 seed groups with identical grants (Q468), making the
> migration behaviour-preserving on day one. The 4 matrix actions stay (Q469);
> Lock/Unlock/Override/Configure are critical actions resolved outside
> most-permissive-wins (Q470) — **in the rule layer, since they are not matrix
> actions at all**. The hand-written per-object rules move into that layer
> (Q472), which therefore needs a rule language.

- **Plan V1** §3: permissions resolve across
  `Company → Department → Role/User Group → Person → Project → Joinery Item →
  Tab → Action`, with eleven actions (View, Create, Edit, Delete, Approve,
  Reject, Release, Lock, Unlock, Override, Configure), IT-authored **custom
  user groups**, multi-group membership, and **most-permissive-wins** except
  for nominated critical actions.
- **Shipped today:** `apps/api/app/auth/permissions.py` is a **static
  `dict` literal** — 7 roles × 11 modules × 4 actions, one role per user
  (`app_user.auth_role`, CHECK-constrained), no project or item scoping, no
  groups. `CLAUDE.md` names that file "the source of truth". Per-object rules
  (the not-uploader approve rule, creator-or-manager, `require_drafter()`) are
  hand-written in route handlers.

**Consequence.** Plan V1 needs a DB-backed permission engine with group
resolution and object-level scoping. That is a replacement of
`permissions.py`, of `require_permission`, of the `/auth/me` permissions
payload the web tier gates navigation on, and of every hand-written per-object
rule. It is the highest-blast-radius item in the document and the one most
likely to be worth staging behind a compatibility shim.

### 3.5 The fixed 6-tab IA and the Plan V1 navigation model (~~`REARCH`~~ — **resolved 2026-09-18**)

> **Resolved by Q474: Cutlist *is* the `List` tab.** There is no seventh
> primary tab and the "primary six do not grow" rule stands unchanged. The
> RBAC module `list` already gates the cutlist surfaces
> (`GET /items/{iid}/cutlist.pdf` on `("list","read")`, item-attachment writes
> on `("list","write")`), so this names what the code already does. The
> analysis below is kept as the record of why it looked like a conflict.
>
> Q475 confirmed the module workspaces **do** open as separate windows, which
> is a real change to the single-shell model — see `OPEN-QUESTIONS.md` Q545.

- **Plan V1** Q406–Q409: Dashboard is the **main entrance**; top buttons open
  **Orderbook / Tracking / Cutlist** as dedicated module workspaces; the
  Dashboard's middle section carries tabs including a **Project** tab; an
  **Info** button inside Tracking opens a separate **Project Details** window
  with `Project Stats / Cars / OH&S / Scope` tabs, sharing one project record
  with the Dashboard Project tab (Q409). Q407 explicitly permits a new UI.
- **Shipped today:** `CLAUDE.md` states, as a **binding** design-system rule,
  "IA is fixed to **6 primary tabs** in this order: `Dashboard · Tracking ·
  List · Shop Dwgs · iSample · Orderbook` … the primary six do not grow", with
  a secondary strip for new surfaces. There is no Cutlist module, no Project
  Details window, and `SideBar.tsx` is the project list only.

**Consequence.** Plan V1 introduces **Cutlist** as a third top-level module
workspace — which the 6-tab rule forbids adding to the primary row and which
the secondary row (`Catalog · Shop Floor · Cut Floor · Estimating · Customers`)
does not obviously fit either, given Q406 puts it alongside Orderbook and
Tracking. Either the binding rule is amended or Cutlist lands on the secondary
strip against Plan V1's stated arrangement.

## 4. Section-by-section mapping

### Plan V1 §2 — Information structure

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| `Company → Project → Area → Room → Joinery Item → Activity` | `workspace → projects → area → room → items → modules → parts`. **Sub-project #10 (`0026`)** made Area and Room real project-scoped tables, Room nested under Area (Q552), with a composite FK from `items`; `items.stage` / `rm_no` / `rm_desc` are kept and still written (Q435). **"Activity" is not a hierarchy level** — lifecycle stages, QC records and comments hang off the item without one. | `PARTIAL` |
| Joinery Item is the central operational unit, not a cabinet | Matches — `items` is the unit; `modules`/`parts` sit beneath it. | `SHIPPED` |
| Item carries workflow, docs, 3D + cutlist, materials, costs, variations, revisions, tasks, comms, approvals, production, QC, delivery, install, audit, rework | Has: workflow (`item_stages`, now a projection of the cutlist's stages), docs (five `item_attachment` slots + the Document Register + shop drawings), cutlist (`modules`/`parts`), materials (hardware lines, the versioned Material Take), QC (defects, checklist, rework — `0039`), comms (comment threads, `0042`/`0043`), a Q&A log (`item_query`), audit (`audit_log` + `item_edit_log`) and the three locks. **Missing: costs at item level (Q543 — orders carry cost, nothing rolls up onto an item), revisions, tasks, approvals-as-records, delivery/install records.** Variations exist at project level only. | `PARTIAL` |
| Component-level access limited to authorised roles | `require_drafter()` gates module/part mutation to `{drafter, manager, admin}`. | `SHIPPED` |
| Item duplication with selective copy, and a hard exclusion list for execution history | Nothing. No duplicate endpoint anywhere. | `ABSENT` |

### Plan V1 §3 — Roles, departments, permissions

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Designer and Draftsperson are one role | `drafter` auth role, elevated to PM-parity on `tracking/list/shop_dwgs/isample/orderbook/catalog/cut_floor`. Closest existing analogue. | `SHIPPED` |
| ~21 departments (Sales, Site Measure, QC, Packing, Delivery, Installation, Accounts, …) | 7 auth roles. `app_user.jtbd_role` is **free-text, display-only, nothing branches on it**. No department entity. | `ABSENT` |
| 7-level permission scope, 11 actions, custom groups, most-permissive-wins | **Dynamic RBAC engine (`0037`):** DB-backed groups with most-permissive-wins; the 7 roles became 7 seed groups with identical grants, an admin panel on `/it` edits them, and `require_permission`, search and `/auth/me` all follow the groups. **Project scope only** — not item, tab or the 7 levels (Q466) — and **4 actions**, not 11 (Q469). Q470's critical actions stay outside the grants and Q472's per-object rules (`require_drafter()` etc.) are still hand-written in route handlers. | `PARTIAL` |
| Only IT edits master templates; Upper Management applies locks | No templates. **Locks now exist** (§L): a Hard Lock is set and cleared by manager / admin only, and a Controlled Lock is decided by its owner or a manager — hand-written `auth_role` checks, not RBAC actions. | `PARTIAL` |

### Plan V1 §4 — Dashboards

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Common Tracking Dashboard, consistent layout, actual completion date/time forward, planning in Details | `/tracking` — quick-filter chips, sub-tabs, search, `ItemsTable`, `ItemDetailModal`, `ProjectDetailModal`, `StatusPopup`, `TrackingMetrics`. Shows stage strip; no explicit actual-vs-scheduled split. | `PARTIAL` |
| Eight named department dashboards, IT-assigned via user groups | `/dashboard` has one `_role_view` keyed off `auth_role`; `estimator` and `editor` have their own shapes, the rest fall through to viewer. Not configurable, not group-assigned. **The QC Dashboard (§4.2, `/qc`, gated on `qc:read`) is built** — one of the eight, read-only, fixed numbers. | `PARTIAL` |
| Management company-wide dashboards, drill-down, configurable numeric KPIs | Nothing configurable. `GET /public/stats` + the dashboard's live workspace stats are the whole of it. | `ABSENT` |

### Plan V1 §5–§6 — Tender and handover

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Separate Tender Dashboard, Estimating + selected Upper Management only | Nothing. `/estimating` is the only quoting surface and every role holds `read` on the module. | `ABSENT` |
| 12-step tender lifecycle (Opportunity → … → Won/Lost/Withdrawn), Go/No-Go, feasibility/risk check | **Built (`0038`):** `estimate_revision.status` is the 12-stage lifecycle (11 sequential stages, then Won / Lost / Withdrawn) with one generic `advance()`, `locked_at` set once at `MGMT_APPROVAL → SUBMITTED`, and the old six states remapped data-preservingly. **The stages are ordering and a label** — nothing in the tree records a Go/No-Go decision or a feasibility / risk check. | `PARTIAL` |
| Preliminary Joinery Items during tender | Estimate lines (`estimate_line` + `_part`/`_hardware`/`_labour`) are the analogue but are not items **during tender**. `convert_to_project()` has created real Joinery Items since #9a (this row and Q489 used to say it did not — corrected), and since `0038` the PM chooses which lines convert. | `PARTIAL` |
| Detailed / lump-sum / hybrid estimating | Detailed only (per-line parts + hardware + labour). | `PARTIAL` |
| Handover: PM review → select information → validate → confirm | **Built (`0038`):** `GET /revisions/{rid}/handover-preview` shows the lines that would become items and the contract value; `POST /revisions/{rid}/convert` takes `include_line_ids` (Q490), re-resolves every snapshot against the live catalog (`409 CATALOG_GONE`), rejects double-convert and archived customers, and creates the project, items and contract in one transaction. Generate Orders (`0041`) then turns the won quote's materials into draft purchase orders. | `SHIPPED` |
| Contract Value baseline, selling price fixed, PM decides variation | **Built (`0038`):** `project_contract` (immutable `original_value`) plus an append-only `project_contract_variation`; `current_value` is computed on read, never stored (Q491). Creating a variation *is* the PM's decision — there is no separate approval step. | `SHIPPED` |

### Plan V1 §7–§8 — Templates, versioning, validation, simulation, initiatives

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Template hierarchy with inheritance, versions, Default marking, project pinning, Configuration Snapshot, Template Suggestions, publishing rules, retire/reactivate | Nothing. No template entity of any kind. | `ABSENT` |
| Mandatory validation, Error/Warning/Information levels, latest-result display | Nothing. | `ABSENT` |
| Reusable simulation scenarios, full test reports, IT override of failures with classification (Q253–Q259) | Nothing. | `ABSENT` |
| Template technical-debt register, custom issue workflows, dependencies, blocking/non-blocking, list + dependency map (Q260–Q265) | Nothing. | `ABSENT` |
| Initiatives: grouping, own workflow, cross-department, single owner, milestones, Major classification, overdue tracking and notification (Q266–Q289) | Nothing. | `ABSENT` |

> **Scale note.** §7, §8 and §35–§38 together (Q253–Q351, ~99 confirmed
> decisions) describe an IT governance product — templates, validation,
> simulation, an issue tracker, an initiative tracker, and a notification
> escalation engine with priority-aware rescheduling. On the evidence of the
> nine shipped sub-projects, this is comparable in size to everything built so
> far. It is also the part of Plan V1 with the least connection to the daily
> joinery workflow, and nothing in §22's item workflow depends on it.

### Plan V1 §9–§12 — Priority, tasks, change history, locking

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Priority at 6 levels, configurable names/colours/deadlines/escalation | `cut_schedule.priority` (an integer ordering within one day) is the only priority column in the schema. | `ABSENT` |
| Tasks — auto, manual, rule-driven, change-driven, request-driven | No task entity. | `ABSENT` |
| Change-impact rules, suggested actions, owner decides | Nothing. | `ABSENT` |
| Every significant object records who/what/when | `audit_log` (workspace governance, every authenticated mutation) + `item_edit_log` (per-item field history, written in the same transaction). Genuinely solid. | `SHIPPED` |
| Formal revisions coexisting with automatic history | `shop_drawing_revision`, `estimate_revision` and the versioned `material_take` — three entities, not a general mechanism. | `PARTIAL` |
| **Retain last 20 change states for rollback; rollback creates a restorative revision** | `item_edit_log` stores `old_value`/`new_value` as `varchar(255)` per field — enough to *display* history, **not** enough to reconstruct and restore an object state. No rollback anywhere. | `ABSENT` |
| Three lock types (Hard / Controlled / Approval), applicable to fields, components, items, areas, projects, tabs, revisions | **§L (2026-09-27, migration `0040`): all three ship**, at item scope only (Q510's confirmed ceiling — no field/tab/area/project/revision locks). Controlled Lock (`0032`, B7) is unchanged: a non-owner's save is held as an `item_lock_request` for the owner or a manager to decide. Hard Lock blocks `PATCH /items/{id}` for everyone, including the owner, until a manager/admin explicitly clears it. **Later rounds widened what the item's locks answer for** — still item scope, so the ceiling below stands: every module / part write, CV import, hardware lines, attachments and the Document Register answer to all three; status, bulk status and stage dates to Hard + Controlled (the Approval Lock cannot gate the write that clears it); item queries (answering) and material-take writes to Hard + Controlled, and *asking* a query to the Hard Lock only. QC records and comments are deliberately not lock-checked. Approval Lock has no column — it is `items.status == 'APPROVED'`. Also ships Q511/Q512's field-level optimistic concurrency (not itself in Plan V1's §12 text, but the mechanism the customer's interview settled on for "conflicting changes are never silently overwritten") on the three named surfaces: item editor, cutlist, orders. Still **no lock below or above item scope**: `projects` has no lock column (Q566, unchanged by this pass). | `PARTIAL` |

### Plan V1 §13–§15 — Search, mobile, QR

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Global company-wide search across ~18 object types | **Sub-project #11 (2026-09-24):** one Meilisearch index over 11 types (projects, items, related parts, cutlists, orders, suppliers, drawings, samples, customers, estimates, catalog), fed by a trigger-written outbox (`0033`), top-bar box + `/search`. Workspace-scoped and gated on module `read`; not yet project- or department-scoped (waits for §3.4 / Q466); people, tasks, documents, comms and history not covered. | `PARTIAL` |
| Desktop + tablet + mobile responsive | Desktop-only in practice. `legacy/REFINEMENT_BACKLOG.md` still carries the mobile pass as an open follow-up; #8 explicitly deferred "mobile-first responsive UI". | `ABSENT` |
| Site mobile: photos, measurements, markup, defects, scanning, signatures | Nothing. | `ABSENT` |
| **Offline work with sync, conflict detection, never silently overwritten** | Nothing. The whole stack is server-rendered with raw `fetch()` and no client cache (no TanStack Query by design). | `ABSENT` |
| QR/barcode for production, packing, installation | **Packing only (`0039`):** `/items/{id}/label` prints a QR of the item's `num`, and the Shop Floor kiosk's Packing step scans it with the browser camera (`getUserMedia` + `jsQR`, manual entry as the fallback) — no native app (Q532). Production and installation scanning are absent: `DEL` / `INST` are not Shop Floor stages (Q561). | `PARTIAL` |

### Plan V1 §16–§17 — Financials and variations

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Ten tracked financial figures (Original Estimate → Forecast Final Cost, Budget vs Actual/Forecast) at Project + Item level | `projects.total_value`, plus (`0038`) the contract's original and current value and a derived **actual cost** at Project level — materials received × cost plus labour durations × `workspace_labour_rate`, apportioned across a cutlist's items by part area (`GET /projects/{pid}/actual-costs`, Q493 / Q549). **No committed cost, forecast or margin, and no budget-vs-actual at Item level.** | `PARTIAL` |
| Real-time cost aggregation from departments | Two sources are rolled up on read and never stored: procurement receipts and Shop Floor completions (Q493). No other department records cost. | `PARTIAL` |
| Financial Close Snapshot (mandatory) + manual named snapshots + comparison + Open Financial Exceptions + post-close adjustment | Nothing. | `ABSENT` |
| Variations linked to items, full flow, Original Contract Value never overwritten | Project-level only: `project_contract_variation` is append-only and the original value is never overwritten (Q491), but **a variation is not linked to an item and has no flow** beyond the PM adding it. | `PARTIAL` |

### Plan V1 §18–§21 — Materials, Material Take, summary, procurement

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Flexible stock depth per material/project | `board_inventory` (migration `0025`) — board materials only, one row per (workspace, material, sheet size), `qty_on_hand`. No depth setting. | `PARTIAL` |
| Substitution proposed by Procurement, **approved by Designer/Draftsperson**, with impact analysis | Nothing. | `ABSENT` |
| Offcuts, reservations, partial consumption, min stock, reorder alerts, forecasting, batch/lot, expiry, FEFO, quarantine, recall | Nothing. **`/optimise` deliberately reads stock and never reserves or decrements it** — the pure-function invariant from #9. | `ABSENT` |
| Multi-location stock, transfers, stocktake, cycle counting, variance investigation | `board_inventory.location` is a free-text label on the row, not a location entity. | `ABSENT` |
| **Material Take** before Shop Drawing Approved, system-generated + manual adjust, audited, impact review on later drawing change (Q80) | **Sub-project #12 (2026-09-24):** versioned per-item take (`0034`), generated from parts + hardware (boards in fractional sheets, Q586), adjusted, approved, audited; impact review triggered by drift in the take's own inputs. **Not** triggered by drawing changes and no warning at drawing approval — drawings are not linked to items (Q583). | `PARTIAL` |
| **Project Material Summary** consolidating approved takes, PM confirms, only then released to Procurement, stale-line flagging | **Sub-project #12:** consolidates approved takes with per-item breakdown, stale lines, nest sheet counts and read-only on-order / received; PM confirmation is **advisory** (Q499, a deliberate departure). No ordering from summary lines yet (Q585). | `PARTIAL` |
| Split across suppliers/POs with required/ordered/received/outstanding | `procurement_batches` + `batch_allocations` track ordered / received and over-commit 409s, now **beneath orders** (Q504): `purchase_orders` + `po_line_items` are the PO layer (`0029`), with an Orderbook editing UI, a status guard (Cancelled / Delivered are read-only) and PO generation from a won quote. **No requisition, confirmation, receipt or inspection flow**, and no required / ordered / received / outstanding view per line. | `PARTIAL` |
| Supplier comparison, performance tracking, statuses (Approved/Conditional/Trial/Suspended/Blocked) | `vendors` is now the supplier entity (`0029`, Q556) behind a workspace-scoped `/suppliers` surface, and catalog rows link to it beside their free-text column. **No comparison, performance tracking, or Approved / Conditional / Trial / Suspended / Blocked statuses.** | `PARTIAL` |
| Price history, purchase history, quote validity with no silent fallback, evidence thresholds | Nothing. Catalog rows hold one current cost. | `ABSENT` |
| Requisitions, shared/bulk POs, cost allocation rules, claims/credits, payment terms | Nothing on the v1 surface. | `ABSENT` |

### Plan V1 §22–§27 — Item workflow, release, scheduling, QC, production

| Plan V1 stage order | Current `stages` seed | Verdict |
| --- | --- | --- |
| `Shop Drawing → Material Take → Shop Drawing Approved → Procurement → Listing → CNC → Edging → Assembly → Painting → QC → Packing → Delivery → Installation → Completed` (14) | `REQ · SM · LISTED · DOWN · CNC · EDGED · PAINTED · MADE · DEL · INST` (10) **+ `PACKING` (11), added by `0039`** (`sort_order` 85, between `MADE` and `DEL`) | ~~`REARCH`~~ **deferred (Q459)** — today's 10 stood, and **Packing has since arrived as the 11th (Q519)**; Plan V1's other extra stages arrive with the sub-projects that need them. Q461 keeps the existing paint ordering and Q462 keeps the single global lookup, so no lifecycle migration happens. |

The lists are not a relabelling of each other:

- Plan V1 **adds** Material Take, Shop Drawing Approved, Procurement, QC,
  Packing and Completed as tracked stages.
- Plan V1 **drops** `REQ` (Requested), `SM` (Site Measure) and `DOWN`
  (Marked Down) — or moves them somewhere this document does not state.
- Plan V1 puts **Painting after Assembly** by default. Shipped default is
  `PAINTED` **before** `MADE`, with `items.paint_after_assembly` (migration
  `0020`) as the opt-in reordering flag, and `painting_req = false` skipping
  `PAINTED` from the order entirely.

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Shop Drawing approval: IT defines approvers, record version/approver/timestamp/decision/comments/documents/conditions | `shop_drawing_revision` `draft → pending → approved\|rejected` with a not-uploader rule and an in-flight partial unique index. Approver set is the RBAC matrix, **not** IT-configurable per template. No conditions field. | `PARTIAL` |
| Production Release → controlled Production Pack; one current pack; older packs superseded and hidden | Nothing. `combined.pdf` renders on demand from live data — there is **no frozen, versioned pack**, so "which revision is Production building from" is currently unanswerable. | `ABSENT` |
| Production Manager owns schedule; Department Managers own actual dates; PM owns listing/start dates and may override any date | `item_stages.due_date`/`done_date` exist with no ownership model; Shop Floor writes `done_date` on complete. No scheduling roles. | `PARTIAL` |
| **Installation scheduling is coordinated outside the system (Q414)**; Site Installation Manager records actual completion per item (Q415) | `projects.installation_start` exists as a date column. No install completion capture beyond the `INST` stage. | `PARTIAL` |
| Workers explicitly Start / Complete / Block / On Hold; automatic timestamp; manager correction preserving original | Shop Floor has Start / Complete / Cancel and a 5-minute worker undo (supervisor any time). **No Block and no On Hold.** No manager correction-with-reason path. | `PARTIAL` |
| Delay engine: Overdue / At Risk / Delayed with notification, alerts, impact, escalation | Nothing. `due_date` is stored and displayed; nothing evaluates it. | `ABSENT` |
| QC stage, defects tied to the completed stage, Internal Rework (post-Assembly) and Full Rework (post-Installation) | **Built (`0039`; QC Dashboard):** `qc_defect` (optionally tagged with the stage checked; `qc:write` raises, `qc:approve` resolves), `qc_checklist_item`, and one `rework` entity with `kind` internal / full (Q516) that never reopens a completed stage (Q517). **QC is a module, not a workflow stage (Q515)**, and the timing rule that decides which kind a defect becomes is guidance, not enforced (Q518). The `/qc` dashboard covers items whose cutlist has started but not finished. | `SHIPPED` |
| Packing, delivery, installation tracking with scanning | **Packing is built:** the 11th stage, assignable on Shop Floor and completed on the kiosk by scanning a label (Q519). `DEL` / `INST` are stage keys only — Shop Floor has never been able to hold them (Q561). | `PARTIAL` |

### Plan V1 §28–§33 — Completion, comms, notifications, reporting, KPIs, integrations

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Completion → Defects → Final QC → Handover → Financial Close → Complete → Archived, with override; archived read-only with audited limited additions | `POST /projects/{id}/close-out` (admin / manager) stamps `closed_at` / `closed_by`, and PATCHing `status` back to `Current` / `Hold` re-opens. **No close checks (defects, final QC, handover, financial close), no archive semantics, no post-close rules.** | `PARTIAL` |
| Context-based comms on 8 object types, mentions, attachments, replies; general discussion areas | **Partly built (`0042`).** A `comment` thread over **6 of the 8 types** (Project, Area, Room, Joinery Item, plus a Module as Component and a shop-drawing revision as Revision since `0043` — Task and Change are not entities), one-level replies and @mentions, with a minimal in-app notification inbox. `tracking:comment` is now enforced. Area and Room threads have a home on the project page's Areas & Rooms card. **Not built:** attachments / photos, decisions, internal notes, discussion areas. Updated in place; the rest of this file is still the 2026-09-18 baseline. | `PARTIAL` |
| In-app + email + push, preferences, mandatory notifications, `Event → Recipient → Channel → Priority`, grouping, acknowledgement, escalation | A minimal **in-app inbox** (`0042`, Q521): `notification` rows for mentions and replies, a bell in the top bar that polls once a minute, `/notifications`, mark-read audited. **No email or push, no preferences, no grouping, acknowledgement or escalation, and no `Event → Recipient → Channel → Priority` rules.** | `PARTIAL` |
| External reporting: no client accounts, PM-generated secure reports, field selection, links with password/expiry/revoke/tracking, templates, snapshots, scheduling, revisions, comparison | PDF rendering exists (WeasyPrint + pypdf, five print templates, `quote.pdf`) and is a real foundation. **Everything above the renderer — sharing, scheduling, snapshots, templates, delivery — is absent.** | `PARTIAL` |
| IT-defined KPI formulas, management-selected displays, numeric-only, reporting-only | Nothing configurable. | `ABSENT` |
| AutoCAD, Revit, Cabinet Vision, CNC, Excel, Xero, MYOB, M365, Teams, Outlook, Drive, Dropbox, supplier systems, barcode, accounting/payroll, CRM | **Cabinet Vision is the one built integration** — CSV import wizard (#7b), `cv_material_mapping`, synonym resolver. Everything else absent. Note §33 wants M365 and Q398 depends on SharePoint. | `PARTIAL` |

### Plan V1 §39–§40 — Side panels, concurrency, documents

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Side panel first, full page for complex actions, fixed system rules for which is which, context preserved, auto-return, auto-refresh (Q352–Q359) | Drawers exist and are deep-linkable (`?drawer=item-availability&itemId=`, `?drawing=N&rev=M`, `?sample=N`) — the pattern is established. **No simple/complex classification, no return-and-refresh choreography.** | `PARTIAL` |
| Field-level concurrent-change conflicts: detect, lock only conflicting fields, owner-or-manager resolves, compare/merge, notify, daily reminders, escalate when blocking, set stage to Blocked, resolver picks new status (Q364–Q378) | **Detection is built (§L, `0040`):** `field_versions` on items, cutlists and orders; a PATCH may carry `expected_versions`, and a stale field answers `409 FIELD_CONFLICT` naming just that field with its `current_value` (Q511 / Q512). **Not built:** locking only the conflicting fields, owner-or-manager resolution, compare / merge (the UI says reload), notification, reminders, escalation, the Blocked stage. Omitting `expected_versions` keeps last-write-wins, as does every surface Q511 did not name. | `PARTIAL` |
| Resolved-conflict retention to archive, read-only in archive, captured access list, IT/Upper-Management edits, audit, PDF export (Q379–Q390) | Nothing (depends on the above). | `ABSENT` |
| Project files in SharePoint, view-only pop-up, auto-refresh, drawing-number matching, revision ordering (Q391–Q405) | See §3.3. | `REARCH` |

### Plan V1 §41 — Reference screenshots (Q406–Q431)

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Dashboard-as-entrance, Orderbook/Tracking/**Cutlist** module workspaces (Q406–Q407) | `/dashboard` is the landing page, `/tracking` and `/orderbook` are module workspaces, and **`/list` is the Cutlist module workspace** — Q474 settled that Cutlist *is* the `List` tab, so there is no seventh primary tab. | `SHIPPED` |
| Tracking **Info** button → Project Details window with `Project Stats / Cars / OH&S / Scope` tabs, sharing one record with the Dashboard Project tab (Q408–Q409) | `ProjectDetailModal` gained a **Project Stats** tab (#10), and `/projects/[id]` carries details, contacts, lift & access, labour hours, the contract and actual costs. **Cars and OH&S (Q550) and Scope (Q572) are still absent** — blocked on customer input, not stubbed. | `PARTIAL` |
| Item pop-up with `Details / Log / Actions / Query` tabs, creation + modification metadata, change history (screenshot 06) | `ItemDetailModal.tsx` already has exactly these four tabs. **`Actions` and `Query` are `StubPanel` placeholders** (`:119-120`); `Details` and `Log` are real. The closest thing in the tree to a reference screenshot already being implemented. | `PARTIAL` |
| JID: project-defined, **non-unique**, own convention per project (Q410) | `items.jid_code` + `jid_color` (`0035`) are free-text / hex columns shown in the Tracking grid and the item pop-up. There is **no per-project convention** (Q410 asks for one). | `PARTIAL` |
| Cutlist number: six digits, created in a Cutlist panel, shared by several items (Q410–Q413) | **Built (`0027`):** `cutlist` is an entity; `items.cutlist_id` is nullable and single-column, so an item has none or one (Q440 / Q411), and `joinery_number_seq` feeds Item IDs, cutlist numbers and related parts so a six-digit number never means two things (Q541). Every pre-existing item got its own cutlist carrying its `num` (Q540). | `SHIPPED` |
| Item ID == Group ID for a main item; related parts share the Group ID (Q416) | **Built (`0028`):** related parts are rows in `items` with a `row_type` and a one-level parent FK (Q447 / Q449), and share the parent's Group ID (Q416 / Q453). | `SHIPPED` |
| Related parts show the issued **order number** in the cutlist column and click through to Orderbook (Q417–Q418) | **Built (#10):** a related part shows its issued order number where a cutlist number would be (Q417 — a DB CHECK stops it holding a cutlist), and the Orderbook honours `?order=<po_number>` to locate it (Q418). | `SHIPPED` |
| Empty workflow-stage area for related parts (Q419) | **Built:** related parts render an empty stage-strip area (Q419) while their other columns still render. | `SHIPPED` |
| Nested, expand/collapse, collapsed by default (Q420–Q422) | **Built:** `ItemsTable` nests related parts under their parent, collapsed by default (Q420–Q422). | `SHIPPED` |
| Drafter or PM creates related-part rows (Q423) | **Built:** `apps/api/app/related_parts/` — writes sit behind `require_drafter()` (drafter / manager / admin) and `tracking:write`. | `SHIPPED` |
| Creating a related part does **not** auto-create an order (Q424) | **Holds:** nothing in `related_parts/` creates an order (Q424); Create Order is a separate, explicit action. | `SHIPPED` |
| Tracking **O/BOOK subtab** with a **Create Order** button (Q425) | **Built:** a seventh Tracking column-set, `O/BOOK` (Order # / Supplier / Status / ETA, Q570), and a Create Order action. | `SHIPPED` |
| Order-details form per screenshots 07–09 (acoustic panel / benchtop / contractor manufacturing), type-specific fields (Q426) | **Built as decided, not as drawn:** one generic Create Order form plus key/value `attributes` rows (Q426 / Q503). The screenshots' type-specific field sets (acoustic panel, benchtop, contractor manufacturing) are carried as attributes on `purchase_orders` / `po_line_items`, not as per-type forms. | `PARTIAL` |
| Prefill PROJECT, LOCATION, CUTLIST NO. from the parent (Q427–Q428); allow blank cutlist (Q429); backfill when the parent gets one (Q430); update all linked orders when replaced (Q431) | **Built:** `POST /orders` prefills project, location and cutlist number from the item (Q427); the cutlist number is the parent's (Q428), may be blank (Q429), and `orders.queries.sync_orders_for_item` fills or rewrites it on every linked order when the parent gains or changes a cutlist (Q430 / Q431). | `SHIPPED` |

## 5. Tally

> **Re-scored 2026-10-02.** The counts below are recounted mechanically from §4's
> verdict column, not carried over from the 2026-09-18 baseline.

Counting the 82 mapped rows in §4: **17 `SHIPPED`, 37 `PARTIAL`, 26 `ABSENT`**,
plus **2 rows still labelled re-architecture** — *Project files in SharePoint*
(bounded, §3.3) and the stage-list row (deferred, Q459), whose verdict cell
carries the label inline, so a mechanical count of the verdict column sees only
1 `REARCH`.

For comparison, the 2026-09-18 baseline was 4 / 21 / 50 / 7. Four in-place
updates between then and now (search, Material Take, Material Summary, comments)
had already made the mechanical count 4 / 25 / 46 / 6 before this pass. This
pass changed **26 verdicts**: **13 rows to `SHIPPED`** (12 from `ABSENT` or
`REARCH`, one from `PARTIAL` — among them the contract, handover, QC, cutlist,
related-part and module-workspace rows) and **13 to `PARTIAL`** (11 from `ABSENT`,
2 from `REARCH`), which took `REARCH` from 6 to 1. Another 11 rows kept their
verdict but have new text.

What the seven conflicts became:

| Was | Now | Decided by |
| --- | --- | --- |
| Cutlist owns the workflow | **built** (`0027`, `0030`) | Q438–Q446, Q539–Q541 |
| Related-part rows | **built** (`0028`) | Q447–Q453 |
| Project files in SharePoint | **bounded** — additive, nothing rewritten; blocked on Q480 / Q547 | Q479 |
| RBAC as data | **built** (`0037`), project scope only | Q466 |
| Navigation / Cutlist module | **closed** — it is the `List` tab | Q474 |
| Area / Room as entities | **built** (`0026`) — not a pure rename: `items.stage` / `rm_no` / `rm_desc` are kept and still written | Q552, Q435 |
| 10 vs 14 lifecycle stages | **deferred** — today's 10 stood, Packing arrived as the 11th (`0039`) | Q459, Q519 |

So of seven contradictions, **four are built**, **one closed on inspection**,
**one is bounded and waiting on customer inputs**, and **one is deferred** with
Packing as its first addition.

The shipped system remains a strong foundation for Plan V1's §2 (item-centric
data model), §11 (audit), §22 (production stages), §18–§21 (procurement
mechanics) and §31's renderer. It still has effectively nothing for the
governance half — templates, validation, initiatives, reporting, KPIs — which
**Q434 and Q528 have now placed after the joinery workflow** rather than
alongside it.

## 6. Sequencing, as decided

> **History, not a plan (2026-10-02).** Items 1–4 and 6 below have been built (#10,
> #11, #12 — in an order that differs from this list — the tender / financials
> block §I, and the §L concurrency scope); item 5 (§7–§8, §35–§38) is still
> deferred. Kept as the record of what was decided, since `CLAUDE.md` records what
> was done.

No longer a dependency sketch — this is what the answers settled.

1. **Next: Cutlist + related parts + the full Orderbook rework** (Q437, Q542).
   §3.1 and §3.2 together as predicted, plus §K, which Q542 pulled in. This is
   the largest single change in the programme: a new entity, a row-model
   reshape across **50 call sites in 13 modules**, an order/PO/supplier layer
   revived from the legacy namespace (Q502), and the Area/Room rename (Q455)
   folded in so `items` is migrated once rather than twice.
2. **Then search** (Q520) — the cheapest of the six absent subsystems and the
   only one depending on none of the others. It brings the **first new
   infrastructure since Postgres** (Q525), taking `docker-compose.yml` from
   three services to four.
3. **§19–§20 (Material Take → Summary)** remains a clean insert ahead of
   `procurement_v1`'s batches, and now has a version-tracked take (Q495, Q500)
   feeding a summary whose PM confirmation is advisory (Q499).
4. **§16–§17 (financials, variations)** still depend on a contract value that
   handover establishes (Q491), and on actual costs derived from procurement
   receipts and shop-floor completions (Q493) rather than entered.
5. **§7–§8 and §35–§38 are deferred** (Q434, Q528) — confirmed separable, to be
   revisited after the joinery workflow.
6. **§39's conflict resolution no longer needs a cross-cutting change.** Q511
   scoped optimistic concurrency to **three surfaces** — the item editor, the
   cutlist and orders — instead of all 181 endpoints, because Q508's lock types
   prevent most collisions outright. Q513 dropped rollback entirely.

### Three decisions deliberately depart from Plan V1's text

Recorded here as well as in `OPEN-QUESTIONS.md`, because a reader comparing code
to the spec will find them disagreeing and the code is right:

| Decision | Departs from | What the code does |
| --- | --- | --- |
| **Q499** | §20 — "only after PM confirmation is the summary released" | confirmation is advisory; Procurement may order early, flagged |
| **Q513** | §11 — "retains at least the last 20 change states for rollback" | no rollback; history is for accountability, not restoration |
| **Q527** | §32 — "IT defines KPI formulas" | fixed KPI catalogue; a new KPI needs a deploy |

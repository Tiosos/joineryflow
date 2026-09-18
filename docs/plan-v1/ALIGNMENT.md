# Plan V1 vs. shipped JoineryFlow — alignment record

> **Status: analysis only. No code has been written against Plan V1.**
> Source of truth for the target: [`plan_v1.md`](./plan_v1.md) (canonical,
> committed verbatim as supplied 2026-09-17, questions answered through Q431).
> Source of truth for what exists today: `CLAUDE.md` at the repo root, and the
> code itself. Where this document and the code disagree, the code is right.

## 1. What this document is

Plan V1 describes a **company-wide joinery workflow and control platform**.
The repository currently holds **JoineryFlow**, nine shipped sub-projects
(Foundation → PM Workbench → Procurement Workbench → Shop Drawings → PDF
Generation → iSample → Catalog/CV Import/Cut Floor → Shop Floor → Estimating →
CutPlan Optimiser), at Alembic head `0025`.

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

## 3. The five structural conflicts

These are the decisions that have to be made before any Plan V1 implementation
sequencing is meaningful. Everything else is additive and can be ordered freely.

### 3.1 The Cutlist becomes the workflow-owning entity (`REARCH`)

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

### 3.2 Related-part rows are a new row class in Tracking (`REARCH`)

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

### 3.3 Project files move to SharePoint, read-only (`REARCH`)

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

### 3.4 RBAC becomes data, not code (`REARCH`)

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
| `Company → Project → Area → Room → Joinery Item → Activity` | `workspace → projects → items → modules → parts`. **Area and Room are not entities** — `items` carries free-text `stage` (site location), `zone`, `level`, `rm_no`, `rm_desc`. | `REARCH` |
| Joinery Item is the central operational unit, not a cabinet | Matches — `items` is the unit; `modules`/`parts` sit beneath it. | `SHIPPED` |
| Item carries workflow, docs, 3D + cutlist, materials, costs, variations, revisions, tasks, comms, approvals, production, QC, delivery, install, audit, rework | Has: workflow (`item_stages`), docs (`item_attachment` 3 slots + shop drawings), cutlist (`modules`/`parts`), materials (`item_hardware_lines` → `project_hardware_catalog`), audit (`audit_log` + `item_edit_log`). **Missing: costs at item level, variations, revisions, tasks, comms, approvals-as-records, QC, delivery/install records, rework.** | `PARTIAL` |
| Component-level access limited to authorised roles | `require_drafter()` gates module/part mutation to `{drafter, manager, admin}`. | `SHIPPED` |
| Item duplication with selective copy, and a hard exclusion list for execution history | Nothing. No duplicate endpoint anywhere. | `ABSENT` |

### Plan V1 §3 — Roles, departments, permissions

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Designer and Draftsperson are one role | `drafter` auth role, elevated to PM-parity on `tracking/list/shop_dwgs/isample/orderbook/catalog/cut_floor`. Closest existing analogue. | `SHIPPED` |
| ~21 departments (Sales, Site Measure, QC, Packing, Delivery, Installation, Accounts, …) | 7 auth roles. `app_user.jtbd_role` is **free-text, display-only, nothing branches on it**. No department entity. | `ABSENT` |
| 7-level permission scope, 11 actions, custom groups, most-permissive-wins | Static 7×11×4 matrix, single role per user. | `REARCH` (§3.4) |
| Only IT edits master templates; Upper Management applies locks | No templates, no lock framework. | `ABSENT` |

### Plan V1 §4 — Dashboards

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Common Tracking Dashboard, consistent layout, actual completion date/time forward, planning in Details | `/tracking` — quick-filter chips, sub-tabs, search, `ItemsTable`, `ItemDetailModal`, `ProjectDetailModal`, `StatusPopup`, `TrackingMetrics`. Shows stage strip; no explicit actual-vs-scheduled split. | `PARTIAL` |
| Eight named department dashboards, IT-assigned via user groups | `/dashboard` has one `_role_view` keyed off `auth_role`; `estimator` and `editor` have their own shapes, the rest fall through to viewer. Not configurable, not group-assigned. | `PARTIAL` |
| Management company-wide dashboards, drill-down, configurable numeric KPIs | Nothing configurable. `GET /public/stats` + the dashboard's live workspace stats are the whole of it. | `ABSENT` |

### Plan V1 §5–§6 — Tender and handover

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Separate Tender Dashboard, Estimating + selected Upper Management only | Nothing. `/estimating` is the only quoting surface and every role holds `read` on the module. | `ABSENT` |
| 12-step tender lifecycle (Opportunity → … → Won/Lost/Withdrawn), Go/No-Go, feasibility/risk check | `estimate_revision` has a 6-state machine: `draft → sent → accepted\|rejected\|expired\|withdrawn`, `_LEGAL_TRANSITIONS` in `estimating/queries.py`. **No pre-quote stages at all** — no Opportunity, Initial Review, Go/No-Go, Information Requested, Documents Received, Supplier Pricing, Internal Review, Management Approval. | `PARTIAL` |
| Preliminary Joinery Items during tender | Estimate lines (`estimate_line` + `_part`/`_hardware`/`_labour`) are the analogue but are not items and do not become items on convert. | `PARTIAL` |
| Detailed / lump-sum / hybrid estimating | Detailed only (per-line parts + hardware + labour). | `PARTIAL` |
| Handover: PM review → select information → validate → confirm | `POST /revisions/{rid}/convert` requires status `accepted`, rejects double-convert and archived customers, re-resolves part snapshots, creates the project. **It is a one-shot action with no review-and-select step.** | `PARTIAL` |
| Contract Value baseline, selling price fixed, PM decides variation | `projects.estimate_revision_id` links the source. **No contract-value column, no variation concept.** | `ABSENT` |

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
| Formal revisions coexisting with automatic history | Only `shop_drawing_revision` and `estimate_revision` — two entities, not a general mechanism. | `PARTIAL` |
| **Retain last 20 change states for rollback; rollback creates a restorative revision** | `item_edit_log` stores `old_value`/`new_value` as `varchar(255)` per field — enough to *display* history, **not** enough to reconstruct and restore an object state. No rollback anywhere. | `ABSENT` |
| Three lock types (Hard / Controlled / Approval), applicable to fields, components, items, areas, projects, tabs, revisions | `items.item_locked` + `items.cutlist_owner_id` soft-lock: first save claims ownership, non-owner saves are **permitted** and write an `item.lock_overridden` audit row. That is an *advisory* lock — closest to none of the three types. | `PARTIAL` |

### Plan V1 §13–§15 — Search, mobile, QR

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Global company-wide search across ~18 object types | Per-surface `q=` filters only (tracking, list, shop-dwgs, isample, catalog, estimating, customers). No cross-object search, no search index. | `ABSENT` |
| Desktop + tablet + mobile responsive | Desktop-only in practice. `legacy/REFINEMENT_BACKLOG.md` still carries the mobile pass as an open follow-up; #8 explicitly deferred "mobile-first responsive UI". | `ABSENT` |
| Site mobile: photos, measurements, markup, defects, scanning, signatures | Nothing. | `ABSENT` |
| **Offline work with sync, conflict detection, never silently overwritten** | Nothing. The whole stack is server-rendered with raw `fetch()` and no client cache (no TanStack Query by design). | `ABSENT` |
| QR/barcode for production, packing, installation | Nothing. | `ABSENT` |

### Plan V1 §16–§17 — Financials and variations

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Ten tracked financial figures (Original Estimate → Forecast Final Cost, Budget vs Actual/Forecast) at Project + Item level | `projects.total_value` (a single numeric) and estimate-side snapshot costs. **No committed cost, no actual cost, no forecast, no margin.** The legacy `/procurement/*` namespace has `v_budget_utilisation`, but `CLAUDE.md` records it as **not used by the v1 product surface**. | `ABSENT` |
| Real-time cost aggregation from departments | Nothing to aggregate — departments do not record cost. | `ABSENT` |
| Financial Close Snapshot (mandatory) + manual named snapshots + comparison + Open Financial Exceptions + post-close adjustment | Nothing. | `ABSENT` |
| Variations linked to items, full flow, Original Contract Value never overwritten | Nothing. | `ABSENT` |

### Plan V1 §18–§21 — Materials, Material Take, summary, procurement

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Flexible stock depth per material/project | `board_inventory` (migration `0025`) — board materials only, one row per (workspace, material, sheet size), `qty_on_hand`. No depth setting. | `PARTIAL` |
| Substitution proposed by Procurement, **approved by Designer/Draftsperson**, with impact analysis | Nothing. | `ABSENT` |
| Offcuts, reservations, partial consumption, min stock, reorder alerts, forecasting, batch/lot, expiry, FEFO, quarantine, recall | Nothing. **`/optimise` deliberately reads stock and never reserves or decrements it** — the pure-function invariant from #9. | `ABSENT` |
| Multi-location stock, transfers, stocktake, cycle counting, variance investigation | `board_inventory.location` is a free-text label on the row, not a location entity. | `ABSENT` |
| **Material Take** before Shop Drawing Approved, system-generated + manual adjust, audited, impact review on later drawing change (Q80) | Nothing. Today material demand is expressed directly as `item_hardware_lines` and `parts`; there is no take-off artefact and no approval step. | `ABSENT` |
| **Project Material Summary** consolidating approved takes, PM confirms, only then released to Procurement, stale-line flagging | Nothing. `/procurement-queue` and the `/orderbook` supplier grouping are the nearest surface, but they aggregate live item lines with **no confirm-and-release gate**. | `ABSENT` |
| Split across suppliers/POs with required/ordered/received/outstanding | `procurement_batches` + `batch_allocations` track ordered/received and over-commit 409s. Genuinely close in spirit; no PO entity on the v1 surface. | `PARTIAL` |
| Supplier comparison, performance tracking, statuses (Approved/Conditional/Trial/Suspended/Blocked) | Supplier is a **free-text string** on catalog rows (`supplier`, `default_supplier`). No vendor entity on the v1 surface. The legacy `/procurement/*` namespace has vendors and POs but is unused by v1. | `ABSENT` |
| Price history, purchase history, quote validity with no silent fallback, evidence thresholds | Nothing. Catalog rows hold one current cost. | `ABSENT` |
| Requisitions, shared/bulk POs, cost allocation rules, claims/credits, payment terms | Nothing on the v1 surface. | `ABSENT` |

### Plan V1 §22–§27 — Item workflow, release, scheduling, QC, production

| Plan V1 stage order | Current `stages` seed | Verdict |
| --- | --- | --- |
| `Shop Drawing → Material Take → Shop Drawing Approved → Procurement → Listing → CNC → Edging → Assembly → Painting → QC → Packing → Delivery → Installation → Completed` (14) | `REQ · SM · LISTED · DOWN · CNC · EDGED · PAINTED · MADE · DEL · INST` (10) | `REARCH` |

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
| QC stage, defects tied to the completed stage, Internal Rework (post-Assembly) and Full Rework (post-Installation) | Nothing — no QC entity, no defect, no rework. | `ABSENT` |
| Packing, delivery, installation tracking with scanning | `DEL`/`INST` are stage keys only. No packing. | `ABSENT` |

### Plan V1 §28–§33 — Completion, comms, notifications, reporting, KPIs, integrations

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Completion → Defects → Final QC → Handover → Financial Close → Complete → Archived, with override; archived read-only with audited limited additions | `projects.status` is `Current \| Closed \| Hold`. No close checks, no archive semantics, no post-close rules. | `ABSENT` |
| Context-based comms on 8 object types, mentions, attachments, replies; general discussion areas | **No comment or thread entity exists.** The only `comment` columns in the schema are free-text fields on the legacy procurement PO tables (`0002`), which the v1 surface does not use. `comment` is one of the four RBAC actions and is granted across the matrix, but **no route enforces it** — it is currently a dead action. | `ABSENT` |
| In-app + email + push, preferences, mandatory notifications, `Event → Recipient → Channel → Priority`, grouping, acknowledgement, escalation | Nothing. No notification table, no mail transport, no push. | `ABSENT` |
| External reporting: no client accounts, PM-generated secure reports, field selection, links with password/expiry/revoke/tracking, templates, snapshots, scheduling, revisions, comparison | PDF rendering exists (WeasyPrint + pypdf, five print templates, `quote.pdf`) and is a real foundation. **Everything above the renderer — sharing, scheduling, snapshots, templates, delivery — is absent.** | `PARTIAL` |
| IT-defined KPI formulas, management-selected displays, numeric-only, reporting-only | Nothing configurable. | `ABSENT` |
| AutoCAD, Revit, Cabinet Vision, CNC, Excel, Xero, MYOB, M365, Teams, Outlook, Drive, Dropbox, supplier systems, barcode, accounting/payroll, CRM | **Cabinet Vision is the one built integration** — CSV import wizard (#7b), `cv_material_mapping`, synonym resolver. Everything else absent. Note §33 wants M365 and Q398 depends on SharePoint. | `PARTIAL` |

### Plan V1 §39–§40 — Side panels, concurrency, documents

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Side panel first, full page for complex actions, fixed system rules for which is which, context preserved, auto-return, auto-refresh (Q352–Q359) | Drawers exist and are deep-linkable (`?drawer=item-availability&itemId=`, `?drawing=N&rev=M`, `?sample=N`) — the pattern is established. **No simple/complex classification, no return-and-refresh choreography.** | `PARTIAL` |
| Field-level concurrent-change conflicts: detect, lock only conflicting fields, owner-or-manager resolves, compare/merge, notify, daily reminders, escalate when blocking, set stage to Blocked, resolver picks new status (Q364–Q378) | **Nothing. There is no optimistic concurrency control at all** — no version column, no `If-Match`, no conflict detection. Last write wins everywhere. | `ABSENT` |
| Resolved-conflict retention to archive, read-only in archive, captured access list, IT/Upper-Management edits, audit, PDF export (Q379–Q390) | Nothing (depends on the above). | `ABSENT` |
| Project files in SharePoint, view-only pop-up, auto-refresh, drawing-number matching, revision ordering (Q391–Q405) | See §3.3. | `REARCH` |

### Plan V1 §41 — Reference screenshots (Q406–Q431)

| Plan V1 | Current state | Verdict |
| --- | --- | --- |
| Dashboard-as-entrance, Orderbook/Tracking/**Cutlist** module workspaces (Q406–Q407) | 6 primary tabs + secondary strip; **no Cutlist module**. | `REARCH` (§3.5) |
| Tracking **Info** button → Project Details window with `Project Stats / Cars / OH&S / Scope` tabs, sharing one record with the Dashboard Project tab (Q408–Q409) | `ProjectDetailModal` exists in Tracking and `/projects/[id]` exists. **None of the four named tabs exist** — no Cars, no OH&S, no Scope, no labour-hours or lift/access fields. | `PARTIAL` |
| Item pop-up with `Details / Log / Actions / Query` tabs, creation + modification metadata, change history (screenshot 06) | `ItemDetailModal.tsx` already has exactly these four tabs. **`Actions` and `Query` are `StubPanel` placeholders** (`:119-120`); `Details` and `Log` are real. The closest thing in the tree to a reference screenshot already being implemented. | `PARTIAL` |
| JID: project-defined, **non-unique**, own convention per project (Q410) | `items.code` and `items.item_code` are free-text `varchar`; neither is documented as the JID and neither has a per-project convention. | `PARTIAL` |
| Cutlist number: six digits, created in a Cutlist panel, shared by several items (Q410–Q413) | `items.num` — `UNIQUE`, integer, per item, allocated by seed/insert. **Contradicts sharing.** | `REARCH` (§3.1) |
| Item ID == Group ID for a main item; related parts share the Group ID (Q416) | `items.group_id` free-text, unused for hierarchy. | `REARCH` (§3.2) |
| Related parts show the issued **order number** in the cutlist column and click through to Orderbook (Q417–Q418) | Nothing. The leftmost column is always the cutlist number and always links to `/items/[id]`. | `ABSENT` |
| Empty workflow-stage area for related parts (Q419) | Every row renders a stage strip. | `ABSENT` |
| Nested, expand/collapse, collapsed by default (Q420–Q422) | Flat table. | `ABSENT` |
| Drafter or PM creates related-part rows (Q423) | No row type to create. | `ABSENT` |
| Creating a related part does **not** auto-create an order (Q424) | N/A — nothing to not-create. | `ABSENT` |
| Tracking **O/BOOK subtab** with a **Create Order** button (Q425) | No O/BOOK subtab. `TrackingClient.tsx:116` carries a **disabled `Orders` quick-filter chip** titled *"Backend wiring pending"* — the nearest existing hook. Otherwise the only procurement affordance is the `AvailabilityDrawer` and the `/orderbook` link behind `NEXT_PUBLIC_PROCUREMENT_UI_READY`. | `ABSENT` |
| Order-details form per screenshots 07–09 (acoustic panel / benchtop / contractor manufacturing), type-specific fields (Q426) | `procurement_v1` has batches and allocations — **no order-details form, no per-type field sets, no PO creation on the v1 surface.** The legacy `/procurement/*` namespace has orders but is unused by v1. | `ABSENT` |
| Prefill PROJECT, LOCATION, CUTLIST NO. from the parent (Q427–Q428); allow blank cutlist (Q429); backfill when the parent gets one (Q430); update all linked orders when replaced (Q431) | Nothing. Also depends on both §3.1 and §3.2. | `ABSENT` |

## 5. Tally

Counting the 82 mapped rows above: **4 `SHIPPED`, 21 `PARTIAL`, 50 `ABSENT`,
7 `REARCH`.**

Seven `REARCH` rows, five named conflicts: §3 covers the cutlist (§3.1),
related parts (§3.2), project files (§3.3), RBAC (§3.4) and navigation (§3.5).
The other two are named in §4 rather than §3 because each is a single
well-understood schema decision rather than a cross-cutting rewrite — the
**Area/Room hierarchy** (Plan V1 §2: real entities vs. today's free-text
`level` / `rm_no` / `rm_desc` columns) and the **stage list** (Plan V1 §22:
14 stages vs. today's 10, with Painting moving after Assembly by default).

The shipped system is a strong foundation for Plan V1's §2 (item-centric data
model), §11 (audit), §22 (production stages), §18–§21 (procurement mechanics)
and §31's renderer. It has effectively nothing for Plan V1's governance half —
templates, validation, initiatives, notifications, reporting, KPIs — and it
**contradicts** Plan V1 on the cutlist, related parts, project files, RBAC and
navigation.

## 6. What this implies about sequencing

Not a recommendation to build, just the dependency shape:

1. **The five conflicts in §3 are gates.** Q432 onward cannot be answered
   coherently while the cutlist-vs-item question (§3.1) is open, because
   "which roles can create an order for a related part" presumes the related
   part row class (§3.2) exists.
2. **§3.1 and §3.2 are cheaper together than apart** — both reshape the
   Tracking row model and the item/workflow relationship.
3. **Everything in §16–§17 (financials, variations) depends on a contract
   value** that handover (§6) has to establish first.
4. **§19–§20 (Material Take → Summary → Procurement) is a clean insert** ahead
   of the existing `procurement_v1` batches; it does not conflict with shipped
   code, it precedes it.
5. **§7–§8 and §35–§38 (templates, validation, initiatives, escalation) are
   separable** from the whole joinery workflow and could be deferred
   indefinitely without blocking anything else in the document.
6. **§39's conflict resolution (Q364–Q378) needs optimistic concurrency
   control first** — a version column and `If-Match` on every mutating route —
   which is a cross-cutting change to all 181 existing endpoints.

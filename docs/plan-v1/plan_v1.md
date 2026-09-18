# Joinery Workflow Software — Plan V1

## 1. Vision and Objectives

This software is a company-wide joinery workflow and control platform. Its goals are:

- Nothing gets lost.
- Everyone knows what they need to do and has their own work record.
- Nobody needs to guess design details.
- Design changes are controlled and traceable.
- Production and procurement always work from the correct information.
- Management can see the complete business/project picture.
- Reduce paperwork.
- Real-time tracking of detailed workflow information.
- Reduce mistakes and track responsibility for mistakes/changes.
- Improve communication and allow staff to catch up on relevant history.
- Management controls visibility and priorities.
- Faster quoting and drafting.
- Better production planning, profitability and accountability.
- Complete project history.

Core principle:

**The system tracks, detects, alerts, records and recommends. Authorised people decide, approve, override, release and lock.**

---

## 2. Overall Information Structure

Primary drill-down:

**Company → Project → Area → Room → Joinery Item → Individual Activity/Change**

The hierarchy is mostly fixed so the common Tracking Dashboard can retain a consistent layout across projects. Some areas, fields or workflow stages may be empty or N/A depending on project type and scale.

The **Joinery Item** is the central operational unit used by all departments. Examples include Kitchen, Pantry, Laundry, Robe, Vanity, etc. It is not each individual cabinet.

Components exist below Joinery Items but component-level access is limited to authorised roles.

Each Joinery Item may contain:

- Workflow and status
- Documents and drawings
- 3D model and Cut List
- Materials and hardware
- Costs and variations
- Revisions
- Tasks
- Communications
- Approvals
- Production information
- QC information
- Delivery / installation information
- Audit / change history
- Rework history

Project Manager and Designer/Draftsperson can create, modify and duplicate Joinery Items, subject to permissions and locks.

### Joinery Item Duplication

A duplicated Joinery Item may selectively copy:

- Basic information
- 3D model
- Drawings
- Cut List
- Materials
- Hardware
- Workflow setup
- Tasks
- QC checklist
- Documents
- Photos
- Notes
- Cost structure / template configuration

It must **not** copy live execution history such as:

- Actual production records
- Completion dates
- Actual labour / actual costs
- QC results
- Defects
- Rework records
- Installation records
- Audit / change history
- Completed approvals
- Lock history

Each duplicate receives a unique ID and source-item link.

---

## 3. Roles, Departments and Permissions

Designer and Draftsperson are treated as the same role: **Designer/Draftsperson**.

Departments / functions may include:

- Sales
- Estimating / Quoting
- Project Management
- Site Measure
- Design / Drafting
- Client Approval
- Purchasing / Procurement
- Materials / Hardware
- Production
- CNC
- Edge Banding
- Assembly
- Painting / Finishing
- QC
- Packing
- Delivery
- Installation
- Rectification / Defects
- Accounts
- Management
- IT / System Administration

A user normally belongs to one department but authorised users can have multiple roles/groups.

Permission structure can operate at:

**Company → Department → Role/User Group → Person → Project → Joinery Item → Tab → Action**

Possible actions include:

- View
- Create
- Edit
- Delete
- Approve
- Reject
- Release
- Lock
- Unlock
- Override
- Configure

IT creates custom user groups. Users can belong to multiple groups.

Normally the **most permissive** assigned group wins, except for critical system/security actions that may require a specific authorised group.

Only IT/System Administrators can modify master templates.

Upper Management can apply partial or full locks.

---

## 4. Dashboard Architecture

### 4.1 Tracking Dashboard

The **Tracking Dashboard** is the common main operational dashboard used by everyone with access.

It keeps a consistent layout across projects. Unused stages or data can display empty / N/A.

The main Tracking view focuses on:

- Project / Area / Room / Joinery Item
- Current stage / status
- Actual completion date/time
- Responsible department/team
- Priority
- Alerts / exceptions

Planning information such as scheduled dates and start dates is available in the **Details** drill-down rather than cluttering the main view.

### 4.2 Department Dashboards

Department dashboards are separate and may look completely different.

Examples:

- Estimating Dashboard
- Project Management Dashboard
- Procurement Dashboard
- Material Dashboard
- Production Dashboard
- QC Dashboard
- Installation Dashboard
- Management Dashboard

IT assigns dashboard access using user groups and controls tabs, sections, widgets and related permissions.

### 4.3 Management Dashboards

Management can use company-wide dashboards with drill-down and configurable numerical KPIs.

KPIs are numeric rather than traffic-light bands.

---

## 5. Tender / Estimating Environment

Tender work exists in a separate **Tender Dashboard**, mainly accessible to Estimating and selected Upper Management. It is not yet part of the live operational system.

Tender lifecycle:

**Tender Opportunity → Initial Review → Go/No-Go → Information Requested → Tender Documents Received → Estimating → Supplier/Subcontractor Pricing → Internal Review → Quote Prepared → Management Approval → Submitted → Won / Lost / Withdrawn**

Estimating decides whether to pursue the opportunity and gathers:

- Drawings
- Specifications
- Scope
- Timeframe
- Client / builder requirements
- Other tender information

A configurable feasibility/risk check may consider:

- Capacity
- Schedule
- Materials
- Lead times
- Margin
- Missing information
- Other management-defined factors

It assists human decision-making rather than making the final decision.

Estimators may create **Preliminary Joinery Items** during tender.

Estimating supports:

- Detailed estimating
- Lump sum estimating
- Hybrid estimating

Estimators can build quotes using:

- Joinery/item templates
- Material and hardware databases
- Labour rates
- Production/CNC rates
- Installation rates
- Supplier pricing
- Overheads
- Markup / margin
- Historical projects
- Manual adjustments

---

## 6. Tender to Controlled Project Handover

A tender becomes a live controlled project only after contract signing or approved management authority.

Flow:

**Tender Won/Approved → Prepare Handover → Project Manager Review → Select Information → Validate → Confirm Handover → Controlled Live Project**

The Project Manager reviews what transfers, including:

- Client/project details
- Contract information
- Drawings
- Specifications
- Areas / Rooms
- Preliminary Joinery Items
- Estimate
- Contract value
- Assumptions
- Exclusions
- Programme
- Supplier information
- Notes
- Documents

No manual re-entry is required where information already exists.

Original tender history remains intact.

After handover:

- Tender Estimate remains historical.
- Contract Value becomes the commercial baseline.
- Selling price is fixed.
- Design changes do not automatically change selling price.
- The Project Manager decides whether a change becomes a Variation.

---

## 7. Project Templates and Configuration

When a project becomes live, the system determines initial departments, workflows and permissions using project type / scale / template configuration, subject to authorised override.

Template hierarchy supports inheritance:

**Company Master → Project Type → Department → Joinery Item → Workflow/Task/QC/Approval/etc.**

Only IT can edit master templates.

Project Managers may:

- Load approved project templates/patterns
- Add/remove/modify Areas
- Apply permitted project-specific configuration

Master template changes do not silently overwrite existing projects.

### Template Versions

- Multiple published versions may coexist.
- IT marks one published version as **Default**.
- New work normally uses the current Default.
- Existing projects stay pinned to the version they were created with.
- Authorised project creators may select another published version.
- Selecting a non-default version requires no reason, but the system shows a warning and difference summary.
- Before project creation, users may selectively merge chosen settings from the current Default into a non-default version.
- The result becomes a **Project Configuration Snapshot** containing base template version, imported settings/source lineage, project-specific changes, and author/time.

Project Managers may submit project-specific configuration to IT as a **Template Suggestion**.

IT can approve, reject, request changes, convert an approved suggestion into a draft master template, manually rebuild it, compare it against the current default, and selectively accept/reject changes.

### Template Publishing

IT defines what counts as a material change per template type.

Approval requirements can differ by change type. Once required approvals are complete, the template can automatically publish without a separate Pending Publication stage.

Old versions may be retired and later reactivated. Reactivated versions become selectable again but are not automatically made Default.

Existing scheduled reports/template instances remain pinned to old versions until manual upgrade.

Manual upgrades provide old-vs-new comparison, selective acceptance, remembered accepted/rejected decisions, and rules for when a future change is materially different enough to resurface.

---

## 8. Template Validation and Simulation

Template validation is mandatory before publication and can also be run manually by IT at any time.

Validation uses common base rules plus template-specific rules.

Validation levels:

- Error
- Warning
- Information

Errors block normal validation completion. Warning acknowledgement authority is configurable by warning type.

The user-facing template page shows the **latest validation result** rather than a long list of validation runs.

Validation checks both template structure and sample project simulation.

### Q253 — Reusable Simulation Scenarios

**Option 1 confirmed.** IT can create and save multiple reusable simulation scenarios.

Examples include small residential kitchen, luxury full-house joinery, multi-unit apartment, commercial fitout, material shortage, design change after Listing, Internal Rework, Full Rework, procurement delay, supplier substitution, permission conflict, and archive/post-close adjustment.

Each scenario may preserve sample structure, test data, expected workflow behaviour and validation criteria.

### Q254 — Simulation Review

**Option 3 confirmed.** Use both automated checks and manual IT review.

### Q255 — Simulation Test Report

**Option 1 confirmed.** Every simulation run produces a full report containing scenario, template version, sample data, automated pass/fail checks, manual review notes, Errors/Warnings/Information, final result, tested by, and date/time.

### Q256 — Failed Simulation Override

**Option 2 confirmed.** IT may override a failed simulation and continue toward publishing. The failed result, failed checks, user, timestamp, reason/notes, version and audit history are preserved.

### Q257 — Additional Approval for Override

**Option 2 confirmed.** IT override alone is sufficient; no automatic extra Department Manager/Senior Management approval is required.

### Q258 — Failure Classification

**Option 6 confirmed.** Support all classifications:

- Accepted Risk
- False Positive
- Deferred Fix
- Not Applicable
- Custom Reason

### Q259 — Deferred Fix Follow-up Task

**Option 3 confirmed.** Ask IT each time whether to create a follow-up task.

### Q260 — Template Technical Debt / Outstanding Issues

**Option 1 confirmed.** Provide a central list across templates.

Possible fields include title, template/type/version, source simulation, failed check, classification, priority, owner/team, due date, status, notes, linked task, dates and audit history.

### Q261 — Technical Debt Workflow

**Option 3 confirmed.** IT can customise status workflows.

### Q262 — Different Workflows by Type/Category

**Option 1 confirmed.** Different issue workflows can exist for different template types or issue categories.

### Q263 — Issue Dependencies

**Option 1 confirmed.** Issues can depend on other issues.

### Q264 — Blocking vs Non-blocking

**Option 1 confirmed.** Support both blocking and non-blocking dependencies.

### Q265 — Issue Views

**Option 3 confirmed.** Support both list view and visual dependency map.

### Q266 — Initiatives / Improvement Projects

**Option 1 confirmed.** Multiple issues may be grouped into a larger Initiative / Improvement Project.

### Q267 — Initiative Status and Progress

**Option 3 confirmed.** Each Initiative has its own workflow/status plus calculated issue progress.

### Q268 — Cross-template / Cross-department Initiatives

**Option 1 confirmed.** Allowed.

### Q269 — Initiative Ownership

**Option 2 confirmed.** One overall Initiative owner only. Individual issues may still have their own owners.

### Q270 — Initiative Milestones

**Option 3 confirmed.** Milestones are intended for Major Initiatives.

### Q271 — Major Classification

**Option 1 confirmed.** IT manually decides whether an Initiative is Major.

### Q272 — Change Major/Normal Later

**Option 1 confirmed.** IT may change the classification at any time with full audit history.

### Q273 — Major to Normal with Existing Milestones

**Option 3 confirmed.** Existing milestones remain active.

### Q274 — New Milestones After Returning to Normal

**Option 1 confirmed.** New milestones remain allowed.

### Q275 — Milestone Dependencies

**Option 3 confirmed.** Use simple sequential ordering only, with no separate dependency engine.

### Q276 — Milestone Dates

**Option 1 confirmed.** Each milestone has planned date and actual completion date.

### Q277 — Milestone Overdue Tracking

**Option 3 confirmed.** Automatic by default, but IT can disable overdue tracking for selected milestones.

### Q278 — Overdue Milestone Notification

**Option 1 confirmed.** If overdue tracking is enabled and a milestone passes its planned date without completion, automatically mark it Overdue and notify/alert the Initiative owner.

---

## 9. Priority System

Priority can exist at multiple levels:

**Company → Project → Area → Joinery Item → Task → Individual Change**

Management can configure priority names, colours, deadlines, escalation rules and notification behaviour.

---

## 10. Tasks and Change Triggers

Tasks can be created automatically by workflow, manually, by configured rules/conditions, from changes, from another person/team request, or from other system events.

When a change occurs, configured task/change-impact rules may be suggested. The change owner decides whether to apply them. If not used, the system presents affected options/actions for confirmation.

Change visibility is hybrid: departments see relevant changes by default; authorised users/management/item owner can access full history.

---

## 11. Change History, Revisions and Rollback

Every significant object records who changed what and when. Formal revisions coexist with automatic change history.

The system retains at least the last **20 change states/steps** for rollback.

Rollback creates a restorative revision rather than erasing history.

Change engine principle:

**Change → Impact Detection → Proposed Change → Human Review → Accept / Reject / Modify / Send for Approval → Controlled Update → Audit Record**

Dependent recalculation must not silently overwrite controlled information.

---

## 12. Locking

Three lock types:

1. **Hard Lock** — cannot change until authorised management unlocks.
2. **Controlled Lock** — change can be requested but requires approval.
3. **Approval Lock** — information automatically locks when approved.

Locks can apply to fields, components, Joinery Items, Areas, Projects, tabs, revisions, department information or entire projects.

Every lock/unlock/request/approval/override is audited.

---

## 13. Search

Support global company-wide search for authorised users and department-specific search.

Search may cover projects, clients/builders/sites, Joinery Items, Areas/Rooms, components, drawings, revisions, materials, hardware, suppliers, POs, tasks, people, status, priority, dates, history, documents, notes and communications.

---

## 14. Multi-Device and Mobile

The software works on desktop, tablet and mobile with responsive/adaptive interfaces.

Site/installation mobile capabilities include photos, measurements, drawing markup, defects, QR/barcode scanning, task/status updates, notes, installation progress, signatures/approvals and offline work with later sync.

Offline sync is automatic with conflict detection and authorised conflict resolution. Conflicting changes are never silently overwritten.

---

## 15. QR / Barcode

QR/barcodes are mainly used for Production, Packing, Installation and physical products/components.

---

## 16. Financial Model

Financial tracking is at Project + Joinery Item level, not full component profitability level.

Track separately:

- Original Estimate
- Fixed Contract Value
- Approved Variations
- Current Contract Value
- Committed Cost
- Actual Cost
- Forecast Final Cost
- Profitability / Margin
- Budget vs Actual
- Budget vs Forecast

Project Managers can see real-time costs aggregated from departments.

Selling price is fixed after handover. PM decides whether a change creates a variation or is absorbed by the company.

A formal Financial Close Snapshot is created for every Project. Additional snapshots are manual by PM and can be custom named/noted.

Financial snapshot comparison supports side-by-side, variance analysis, cross-project comparison and filtering/grouping.

Financial close may proceed with open claims/credits/disputed invoices only when authorised PM or Accounts accepts them as Open Financial Exceptions with a reason.

Post-close financial adjustments are allowed with full audit while the original Financial Close Snapshot is preserved.

---

## 17. Variations

Variations are linked to Joinery Items and may include variation number, reason, requester/date, cost/selling-price impact, time impact, design/procurement/production/installation impact, drawings/revisions, approval status/history, related tasks and audit history.

Flow:

**Potential Change → PM Decision → Variation Prepared → Cost Calculated → Client/Builder Approval where required → Approved/Rejected → Current Contract Value Updated → Related Work Updated**

Original Contract Value is never overwritten.

---

## 18. Materials and Stock

Stock-control depth is flexible by material/project: full stock, purchase-only, supplier-direct, project-specific or no stock tracking.

Material substitution can be proposed by Procurement/Material Team, but Designer/Draftsperson must approve design-related substitutions. Impact can include cost, design, drawings, hardware, Production, CNC, QC, Installation and client approval.

Selected materials may support usage/waste tracking, offcut inventory, automatic matching, reservations, partial consumption, minimum stock, reorder alerts, usage-based forecasting, batch/lot tracking, expiry/shelf-life, FEFO, quarantine and recall traceability.

Stock may be reserved to Project/Joinery Item. Authorised managers may override reservations with reason; if this creates shortage/risk, affected work is flagged At Risk.

Support multi-location stock including warehouse, Production, offcut rack, site, external storage and supplier-held stock.

Stock transfers are direct for authorised users and fully audited.

Support physical stocktake, cycle counting, reconciliation and threshold-based variance approval. Major variance creates a Stock Variance Investigation and surfaces recent related stock activity.

---

## 19. Material Take

Material Take occurs before Shop Drawing Approved.

**Q80 confirmed: Option 1 — system-generated starting point + authorised manual control.**

The system can generate board/material, edging, hardware, accessories, finishing materials and other requirements.

Authorised users can confirm/adjust quantities, add/remove materials, choose supplier/material codes, add wastage and notes. Every manual adjustment is audited.

If Shop Drawing changes after Material Take, the system detects possible impact and requires human review: No Impact / Partial Impact / Full Impact. Original history remains preserved.

---

## 20. Project Material Summary → Procurement

Approved Material Take remains saved with each Joinery Item.

Project Manager / Project Coordinator / Designer-Draftsperson then creates a project-level **Material Summary Spreadsheet**.

The system automatically consolidates approved Material Takes as a starting draft, grouping identical materials while retaining source Joinery Item breakdown.

The Project Manager checks and confirms final quantity.

Only after PM confirmation is the summary released to Procurement Dashboard.

Procurement may then compare prices or directly order.

If an underlying Material Take changes after the summary is prepared, affected summary lines are flagged as potentially outdated.

---

## 21. Procurement, Suppliers and Purchase Orders

Procurement may split requirements across multiple suppliers/POs while showing required, ordered, received and outstanding quantities.

Supplier Comparison may include supplier, product code, unit/total price, stock, lead time, delivery, payment, MOQ, substitutions, notes and supplier performance.

Receiving flow:

**PO → Supplier Confirmation → Expected Delivery → Partial/Full Receipt → Inspection → Storage/Allocation**

Damaged/short/incorrect deliveries create Procurement Exceptions. If Production may be affected, affected Joinery Items are flagged At Risk; PM/Production Manager decides the response.

Supplier performance tracks delivery, lead time, wrong/damaged/short goods, exceptions, quote response, price competitiveness, credits/refunds, spend and project history.

Supplier statuses: Approved / Conditional / Trial / Suspended / Blocked. Blocked prevents normal ordering unless authorised override with audit.

Shared Supplier/Product Catalogue is used by Estimating, Material Take, Procurement, comparison and Production planning. Editors include Procurement, Material Team, Estimating and Designer/Draftsperson. Products are usable immediately once created; no separate approval gate.

Maintain full price history and full purchase history by product.

Track supplier quote validity. Expired project-specific pricing must be explicitly replaced/confirmed before PO creation; no silent fallback.

Price-source evidence is mandatory only above configurable thresholds. Multiple supplier quotes are not mandatory.

Purchase Requisition is optional, requires no approval, belongs to one Project, can include multiple Joinery Items and can create multiple POs.

Shared/bulk POs may be used for selected materials across projects/items/general stock. Allocations may be changed after order with full audit.

Cost allocation is manually controlled by Procurement or PM using manual amount, quantity, percentage, item value, even split or custom rule. Only PM can create reusable allocation templates/rules. PM or Accounts can confirm final allocation before financial close.

Supplier claims/credits/replacements use:

**Raised → Sent → Awaiting → Approved/Rejected → Credit/Replacement Pending → Received → Closed**

Credit notes link to the original PO and update net procurement/project cost without erasing original records.

POs support deposits, progress payments, final payment, credits and outstanding balance. Accounts controls payment approval/status. Payment-before-release creates warning/schedule risk rather than a universal hard block.

---

## 22. Standard Joinery Item Workflow

**Shop Drawing → Material Take → Shop Drawing Approved → Procurement → Listing → CNC → Edging → Assembly → Painting → QC → Packing → Delivery → Installation → Completed**

Different projects may skip stages that do not apply while retaining the same Tracking Dashboard structure.

---

## 23. Shop Drawing Approval

Approval depends on project/template. IT defines who may approve. Each approval records version, approver, timestamp, decision, comments, documents and conditions.

---

## 24. Production Release and Production Pack

Designer/Draftsperson releases official production information.

**3D Model + Cut List → Production Release → Controlled Production Pack**

Production uses one current approved Production Pack. Older packs remain historical, clearly superseded/obsolete and normally hidden from Production.

Changes after release require a new controlled revision/release rather than silent update.

---

## 25. Scheduling and Date Ownership

- Production Manager creates the production schedule.
- Department Managers manage actual operational dates.
- Project Manager controls project-level listing/start dates. Q414 supersedes earlier references to recording installation schedules: the Project Manager and Site Installation Manager coordinate installation scheduling outside this system.
- Installation is individual to each Joinery Item under Q413, but installation schedules are not recorded in the system under Q414. Actual installation progress/completion remains distinct from scheduling.
- Project Manager may override any scheduled or actual date.

Track scheduled and actual date/time for each Joinery Item.

Main Tracking view primarily shows actual completion date/time; scheduled/start information is in Details.

Workers explicitly Start / Complete / Block or place On Hold. Completion timestamp is automatic; authorised managers can correct it while preserving the original and reason.

Delay engine can detect Overdue / At Risk / Delayed and trigger configurable notifications, dashboard alerts, impact indications and escalation.

Joinery Item sequencing is primarily human-controlled through PM/Production Manager scheduled dates rather than a complex automatic dependency graph.

---

## 26. QC and Rework

QC checks the work just completed against the applicable controlled Cut List / 3D model / current work information.

- Before Listing: QC does not need to know.
- After Listing but before Assembly: Lister/Designer-Draftsperson updates Cut List/3D model.
- After Assembly: create **Internal Rework** linked to the Joinery Item.
- After Installation: create **Full Rework** linked to the Joinery Item.

QC defects relate to work completed at that stage.

---

## 27. Production, Packing and Installation Tracking

Production/Packing/Installation use physical product/component scanning and mobile features. Production Manager controls production stages; PM may control permitted parts and coordinate scheduling.

---

## 28. Project Completion and Archive

**Installation Complete → Defects/Rectification → Final QC → Client/Builder Handover → Financial Close → Project Complete → Archived**

Normal completion requires configured checks. Authorised management may override with recorded reason.

Archived projects are generally read-only, but authorised users may make limited post-completion additions/corrections such as late documents, invoices/costs, photos, defects, warranty, rework or administrative corrections. All are auditable.

---

## 29. Communications

Context-based communication attaches to Project, Area, Room, Joinery Item, Component, Task, Change or Revision and supports comments, replies, mentions, attachments, photos, drawing/task references, approval discussions, decisions and internal notes.

General company/team/department discussion areas may also exist.

Important technical decisions should remain linked to the relevant work object.

---

## 30. Notifications

Support in-app, email and mobile push, with extensibility for Teams/other integrations.

Users may configure preferences where allowed. IT/management can define mandatory notifications.

Rules may use:

**Event → Recipient → Channel → Priority**

with immediate alerts, summaries, grouping, acknowledgement and escalation.

---

## 31. Reporting and External Sharing

External clients/builders do not receive accounts or portal access.

PM can generate secure external/daily reports and choose which fields to share. Internal costs/comments/staff information can remain hidden.

IT can create external report master templates; PM selects/customises content.

Secure sharing may include unique link, password, expiry, revoke, access tracking/view history, and snapshot or live mode.

Management scheduled reports may combine dashboards. Department scheduled reports remain department-focused.

Management can configure layout, filters, grouping, dates, projects, departments, outputs and recipients.

Report templates can be saved, duplicated, edited and retired/soft deleted. Only IT restores old versions by creating a new active version based on the old.

Every generated report is stored as a historical snapshot with template/version, filters, period, recipients, generated-by/time and delivery status.

Recipient tracking for management reports uses sent/delivered/failed where possible, not open/view tracking.

Delivery channels may include email attachment, secure link, in-app, Teams and future integrations.

Scheduled reports may skip full output when there is no relevant data and instead send a custom No Activity notice. Minimum-data rules can use nested AND/OR logic.

Management can test rules against current/historical data, preview the full report, send a clearly labelled TEST REPORT — NOT LIVE, run the first live report immediately, pause/resume schedules, and manually backfill missed periods.

Historical reporting snapshots are preserved at scheduled cutoffs where possible. Authorised management may correct them with original/corrected audit preserved. Existing generated reports do not change when underlying snapshots are corrected.

Revised Historical Reports are manually created and manually sent. Revisions use sequential numbering by default plus generated timestamp, optional custom label, and authorised number override.

Report comparison supports side-by-side and difference-only views, source user/date visibility, and direct drill-through to source data. If source data changes, the comparison can refresh or create a new report revision.

Revision-specific settings can remain one-off or update the reusable template; updating may change current version or create a new version.

Scheduled reports stay pinned to old template versions until manually upgraded.

---

## 32. KPIs

IT defines KPI formulas. Management selects displays and may set project-specific targets. KPIs can combine system-wide data and use simple or weighted formulas.

KPI display uses numbers only. KPIs are reporting-only and do not themselves trigger operational alerts.

---

## 33. Integrations

The integration layer should be modular/API-friendly and may include AutoCAD, Revit, Cabinet Vision, CNC/manufacturing software, Excel, Xero, MYOB, Microsoft 365, Teams, Outlook/email, Google Drive, Dropbox, PDF, supplier systems/catalogues, barcode/QR, accounting/payroll, CRM and future integrations.

---

## 34. Core Design Principles

### Human-Controlled Automation
**System tracks, detects, alerts, records and recommends. Authorised people decide, approve, override, release and lock.**

### Controlled Change
**Change → Impact Detection → Human Review → Decision → Controlled Update → Audit Record**

### Single Source of Truth
Production, Procurement and other departments can always identify the current controlled information without guessing which revision is correct.

### Simple Main View, Deep Drill-Down
Tracking Dashboard stays simple; detailed information appears through Details and department-specific dashboards.

### Complete Accountability
Important records preserve who, what, when, previous/new values, reasons, approvals, releases, locks and overrides.

---

## 35. Initiative Milestone Notifications and Escalation — Q279–Q289

### Q279 — Overdue milestone reminders
**Option 4:** Send the first overdue notification automatically, then use IT-defined reminder/escalation rules. Rules may control reminder frequency, escalation timing/recipients, priority/severity, channels and stop conditions. Completion stops future overdue reminders. All actions are auditable.

### Q280 — Rule variation
**Option 3:** Different overdue escalation rules are defined by **priority level only**, not Initiative type.

### Q281 — Initiative priority assignment
**Option 3:** The system suggests a priority using factors such as issue severity, number of affected templates/departments, business/operational/security impact, blockers, urgency and overdue items, but IT makes the final decision.

### Q282 — Reason when changing suggested priority
**Option 2:** IT may change the suggested priority without giving a reason.

### Q283 — Priority history
**Option 1:** Keep the full Initiative priority-change history, including previous/new priority, changed by, date/time, and the system-suggested priority at the time.

### Q284 — Priority increase/decrease effect
**Option 1:** A priority change immediately applies the new priority's reminder/escalation rules.

### Q285 — Lowered priority and already-scheduled escalation
**Option 2:** Already-scheduled escalation still occurs after Initiative priority is lowered; only future scheduling uses the new lower-priority rules.

### Q286 — Escalation created under old priority
**Option 1:** Clearly show when an upcoming escalation was created under an older priority and identify the original priority/rule source and schedule time.

### Q287 — Raised priority and future escalation schedule
**Option 2:** When priority is increased, replace all future escalation schedules with the new higher-priority schedule; preserve the old schedule in audit history.

### Q288 — Owner notification after recalculation
**Option 3:** Notify the Initiative owner about the changed escalation schedule only when the new priority is High or Critical.

### Q289 — Management priority view
**Option 4:** IT decides which priority levels appear in a dedicated management Initiative view.

---

## 36. Management Initiative Views — Q290–Q320

### Q290 — Available/displayed columns
**Option 4:** IT defines which fields/columns are available; management chooses which permitted fields to display.

### Q291 — Saved custom views
**Option 4:** IT creates permanent shared views; management can also create personal views.

### Q292 — Sharing personal views
**Option 4:** Management may temporarily share a personal view with authorised management users; IT controls permanent shared views.

### Q293 — Temporary share expiry
**Option 2:** Temporary sharing remains active until the owner removes it; no automatic expiry is required.

### Q294 — Recipient ability to copy
**Option 2:** Recipients can view the shared personal view and copy it into their own personal views.

### Q295 — Copied-view source reference
**Revised answer — Option 3:** Copied views become functionally independent and do not show the original source/owner in the normal UI, but the source reference is retained in audit history.

### Q296 — Editing copied views
**Option 1:** Copied personal views are fully editable immediately, including filters, columns, sorting, grouping and layout.

### Q297 — Copied-view naming
**Option 3:** Copied personal views can be renamed, but the system automatically includes a copied-view identifier such as “Copy” or the user’s name in the naming format.

### Q298 — Deleting personal views
**Option 3:** Management may delete their own personal Initiative views using soft-delete/retire so they remain restorable and auditable.

### Q299 — Restoring retired personal views
**Option 3:** The original owner or IT may restore a retired personal Initiative view.

### Q300 — Sharing settings on restore
**Option 3:** During restoration, ask whether to restore the previous temporary sharing settings or restore the view privately.

### Q301 — Permission re-check on restore
**Option 1:** Re-check each previous recipient’s current permissions and restore only recipients who remain valid.

### Q302 — Some previous recipients invalid
**Option 3:** Ask the restoring user whether to proceed with only the valid recipients.

### Q303 — User declines partial restore of sharing
**Option 3:** Restore the view but keep all sharing disabled until reviewed later.

### Q304 — Previous recipients shown during later review
**Option 1:** Show the previous recipient list with current validity status.

### Q305 — Bulk reselect valid recipients
**Option 4:** Provide “Select All Valid Previous Recipients,” but require confirmation before applying the selection.

### Q306 — Summary before bulk confirmation
**Option 2:** Do not add an extra summary screen; use a confirmation prompt only.

### Q307 — Activation after bulk selection
**Option 3:** Ask whether to activate sharing immediately or save the recipient list as a draft.

### Q308 — Sharing Draft visibility
**Option 1:** Clearly show a **Sharing Draft** status on the personal Initiative view when a draft recipient list exists but access is not active.

### Q309 — Sharing Draft filtering
**Option 3:** Show Sharing Draft as a badge/status indicator, but not as a dedicated filter option.

### Q310 — Badge after sharing activation
**Option 1:** Remove the Sharing Draft badge immediately once sharing becomes active.

### Q311 — Active sharing indicator
**Option 1:** Show an **Active Sharing** badge while the personal Initiative view is currently shared.

### Q312 — Recipient count
**Option 3:** Show the recipient count only when the owner hovers over or taps the Active Sharing badge.

### Q313 — Active Sharing quick view
**Option 3:** The quick view shows recipient names plus each recipient’s current permission/access status.

### Q314 — Remove recipient from quick view
**Option 2:** The quick view is visibility-only; recipient removal requires the full Sharing settings panel.

### Q315 — Confirmation on removal
**Option 3:** Confirmation is required only when the recipient currently has active access.

### Q316 — Impact text in confirmation
**Option 3:** Show the effect of removal in the confirmation only if the recipient has recently accessed the view.

### Q317 — Definition of recently accessed
**Option 3:** “Recently accessed” means within the last **30 days**.

### Q318 — Last accessed date/time visibility
**Option 3:** Record the recipient’s most recent access date/time in audit history only, not as a normal UI field.

### Q319 — Access history depth
**Option 2:** Keep only the most recent access record, not a full event-by-event access history.

### Q320 — Retention while sharing remains
**Option 1:** Keep the most recent access timestamp indefinitely while the sharing relationship exists.

---

## 37. Shared-View Access Retention and Migration — Q321–Q339

### Q321 — Retention after sharing removal
**Option 3:** Keep the recipient’s most recent access timestamp for 12 months after sharing is removed.

### Q322 — Configurable post-removal retention
**Option 1:** IT can change the post-removal retention period; changes are auditable.

### Q323 — Effect of new retention rule on historical records
**Option 4:** Existing records retain their original retention rule unless manually migrated; new records use the new rule.

### Q324 — Bulk migration
**Option 4:** IT can bulk-migrate historical records to a new retention rule, but a preview is required before applying.

### Q325 — Final confirmation
**Option 1:** Require an explicit final confirmation after the preview before applying the bulk migration.

### Q326 — Scheduling bulk migration
**Option 1:** IT can schedule a bulk retention-rule migration for a later date/time.

### Q327 — Execution at scheduled time
**Option 2:** Scheduled migrations do not execute automatically; IT must confirm again at execution time.

### Q328 — Fresh execution-time impact check
**Option 1:** Always run a fresh impact check before execution-time confirmation.

### Q329 — Material differences
**Option 3:** Block execution for review only when the affected record count changes significantly.

### Q330 — Significant-count threshold
**Option 2:** Use a fixed system threshold.

### Q331 — Threshold override
**Option 1:** IT may override the threshold block and continue, but a reason is required.

### Q332 — Threshold Override flag
**Option 1:** Clearly flag the migration as **Threshold Override** in execution history.

### Q333 — Dedicated override review list
**Option 3:** Threshold Override migrations enter a dedicated follow-up review only if the migration later produces errors.

### Q334 — Error follow-up
**Option 1:** If a Threshold Override migration later produces errors, automatically create a linked IT follow-up issue/task.

### Q335 — Follow-up priority
**Option 1:** Assign the follow-up issue/task priority automatically from migration error severity.

### Q336 — Manual priority change
**Option 1:** IT may manually change the automatically assigned priority at any time; retain priority history.

### Q337 — Reason when lowering priority
**Option 2:** IT may lower the priority without giving a reason.

### Q338 — Raising follow-up priority
**Option 1:** Raising the priority immediately applies the new priority’s escalation/reminder rules.

### Q339 — Lowering follow-up priority
**Option 2:** Lowering the priority cancels future higher-priority escalations and recalculates them using the new lower-priority rules; preserve the old schedule in audit history.

---

## 38. Critical Notification Delivery Rules — Q340–Q351

### Q340 — Notify owner after lowered-priority schedule change
**Option 4:** IT defines by priority level whether the issue/task owner is notified after a priority reduction changes the escalation schedule.

### Q341 — Delivery channels for schedule-change notice
**Option 3:** Use the issue/task owner’s personal notification preferences.

### Q342 — Critical override of personal preferences
**Option 1:** Critical escalation-schedule-change notices may override the owner’s personal notification preferences and use mandatory delivery channels.

### Q343 — Mandatory Critical channels
**Option 4:** Critical notices use fixed system-defined mandatory channels.

### Q344 — Extra channels
**Option 2:** Fixed mandatory minimum channels cannot be removed; IT may add extra channels on top.

### Q345 — Department overrides
**Option 3:** Use a company-wide default for IT-added extra channels, with department-specific overrides.

### Q346 — Role-specific overrides
**Option 1:** Department-specific Critical-notice channel overrides may differ by role.

### Q347 — Multiple applicable roles
**Option 1:** Use the most comprehensive combined set of channels from all applicable roles.

### Q348 — Deduplication
**Option 1:** Deduplicate overlapping configurations into one message per delivery channel.

### Q349 — Consolidating simultaneous Critical notices
**Option 3:** Consolidate Critical notices only when they relate to the same Initiative / issue / task.

### Q350 — Consolidated notice format
**Option 1:** Show a concise summary plus expandable detail for each underlying trigger.

### Q351 — Links from consolidated notice
**Option 3:** Include both a link to the parent Initiative/issue/task and a direct link to the exact trigger/action record.

---

## 39. Side Panel / Full-Page Interaction — Q352–Q390

### Q352 — Trigger/action link behaviour
**Option 3:** Open the exact trigger/action in a side panel/detail drawer first, with an option to open the full page.

### Q353 — Actions from side panel
**Option 3:** Allow simple permitted actions directly in the side panel; complex actions require the full page.

### Q354 — Simple vs complex action definition
**Option 2:** Use fixed system rules to determine which actions are simple enough for the side panel and which require the full page.

### Q355 — Full-page requirement indicator
**Option 4:** Show both a clear message such as “Open full page to complete this action” and a visible full-page icon/button.

### Q356 — Preserve context when opening full page
**Option 3:** Open the same record and preserve the active tab/section where possible.

### Q357 — Return after completing complex action
**Option 1:** Automatically return the user to the previous side panel and context after the full-page action is completed.

### Q358 — Refresh on return
**Option 1:** Automatically refresh the side panel to show the latest data.

### Q359 — Concurrent change detected after refresh
**Option 1:** Show the latest data and a clear **“Record changed by another user”** notice if another user changed the same record while the current user was working on the full page.

### Q364 — Resolving concurrent changes
**Option 2 confirmed.** When a concurrent change affects the same data the returning user just edited, require comparison and resolution. Show both versions and allow an authorised user to choose one version or merge the changes. Do not resolve the conflict automatically by silently overwriting either version.

### Q365 — Authority to resolve concurrent changes
**Option 2 confirmed.** Only the record owner or responsible manager may choose between or merge conflicting versions. Other users involved in the conflict may review the conflict information but cannot make the final resolution unless they are also the record owner or responsible manager.

### Q366 — Editing while conflict awaits resolution
**Option 1 confirmed.** While a concurrent-change conflict awaits resolution, lock only the fields involved in the conflict. Other non-conflicting fields in the same record remain editable, subject to normal permissions and any other applicable locks.

### Q367 — Conflict notification recipients
**Option 3 confirmed.** When a field conflict is created, notify both the record owner and the responsible manager. These notifications identify the affected record and fields and provide access to the conflict comparison and resolution process, subject to permissions.

### Q368 — Conflict notification delivery
**Option 3 confirmed.** Deliver conflict notifications according to each recipient's personal notification preferences.

### Q369 — Unresolved conflict reminders
**Option 2 confirmed.** If a field conflict remains unresolved, send a daily reminder to both the record owner and the responsible manager until the conflict is resolved.

### Q370 — Escalating unresolved conflicts
**Option 3 confirmed.** Escalate an unresolved field conflict when it blocks a workflow stage or deadline.

### Q371 — Conflict escalation recipients
**Option 3 confirmed.** When an unresolved field conflict blocks a workflow stage or deadline, escalate it to both the Project Manager and the relevant Department Manager.

### Q372 — Workflow status during a blocking conflict
**Option 1 confirmed.** When a field conflict blocks progress, automatically change the affected workflow stage status to **Blocked**.

### Q373 — Status after conflict resolution
**Option 3 confirmed.** After a blocking conflict is resolved, require the conflict resolver to select the affected workflow stage's new status.

### Q374 — Available status choices
**Option 3 confirmed.** After resolving the conflict, the resolver may select any status normally available for the affected workflow stage.

### Q375 — Reason for the selected status
**Option 2 confirmed.** When selecting the workflow stage's new status after conflict resolution, the resolver may add an optional comment explaining the choice.

### Q376 — Conflict-resolution notifications
**Option 2 confirmed.** After a conflict is resolved and the workflow stage receives its new status, notify the record owner and responsible manager only.

### Q377 — Resolution notification details
**Option 3 confirmed.** The conflict-resolution notification includes the resolver, resolution time, selected values, new workflow-stage status, and any comment provided.

### Q378 — Link in the resolution notification
**Option 2 confirmed.** The resolution notification links directly to the resolved conflict's comparison and audit-history view.

### Q379 — Resolved-conflict history retention
**Option 2 confirmed.** Keep resolved conflict records available until the project is archived.

### Q380 — Conflict history after project archiving
**Option 2 confirmed.** When the project is archived, retain resolved conflict records as read-only records within the archived project.

### Q381 — Access to archived conflict records
**Option 1 confirmed.** Users who had access to the conflict records when the project was archived may continue to view those read-only records in the archived project.

### Q382 — Later permission changes
**Option 1 confirmed.** Preserve the archived conflict-record access list captured when the project was archived; later permission changes do not automatically alter that archived access list.

### Q383 — Changing the archived access list
**Option 4 confirmed.** IT or Upper Management may modify the captured access list after project archiving, and every change must be recorded in the audit history.

### Q384 — Reason for archived-access changes
**Option 2 confirmed.** When IT or Upper Management changes the archived access list, they may add an optional comment explaining the change.

### Q385 — Notifications for archived-access changes
**Option 4 confirmed.** Do not send notifications when the archived access list changes; record the change in the audit history only.

### Q386 — Archived-access audit details
**Option 2 confirmed.** Each archived-access change record includes the person who made the change, the timestamp, and the users added or removed.

### Q387 — Viewing the archived-access audit log
**Option 1 confirmed.** Everyone who can view the archived project may also view its archived-access audit history.

### Q388 — Exporting the archived-access audit log
**Option 3 confirmed.** Only IT and Upper Management may export the archived-access audit history.

### Q389 — Archived audit export format
**Option 1 confirmed.** Export the archived-access audit history in PDF format only.

### Q390 — PDF audit-export content
**Option 3 confirmed.** The exported PDF includes full audit entries together with project details, the export time, and the exporter's identity.

---

## 40. Document, Drawing and Revision Management — Q391–Q405

### Q391 — Document storage structure
**Custom combination of Options 1 and 3 confirmed.** Drawings, specifications, approvals, photos, and other project files may be stored only at the **Project** level or within a **Joinery Item**. Files are not stored directly at Area or Room level.

### Q392 — Project-level file coverage
**Option 4 confirmed.** Keep Project-level files separate from Joinery Item files; do not link Project-level files to individual Joinery Items.

### Q393 — Project-level file visibility
**Option 1 confirmed.** Everyone with access to the project may view its Project-level files.

### Q394 — Managing Project-level files
**Option 3 confirmed.** Only users who have file-management permission for the project may upload, replace, rename, or remove Project-level files.

**Clarified by Q399:** This permission does not provide file-mutation controls in the Project-file pop-up. The pop-up is view-only; file changes are performed through OneDrive in the linked folder. How these permissions map to Microsoft 365 permissions remains undefined.

### Q395 — Granting file-management permission
**Option 4 confirmed.** The Project Manager or IT may grant or remove Project-level file-management permission, and every permission change must be recorded.

### Q396 — Scope of file-management permission
**Option 1 confirmed.** Assign Project-level file-management permission separately for each project.

### Q397 — File organisation and separate drawing/cutlist views
**Custom decision confirmed.**

- **Project-level files:** Provide an individual pop-up window in which the folder location linked to Project-level file storage can be assigned. Q398 identifies this as the SharePoint `site related` folder within each project's folder; the storage/linking mechanism remains to be clarified. Project-level files remain separate from Joinery Item files under Q392.
- **Joinery Item architectural reference:** Clicking a Joinery Item opens its pop-up window. Include a tab showing all design details and the architectural drawing reference number.
- **Joinery Item cutlist entry:** Show the assigned cutlist number at the front of each Joinery Item's information row. Clicking that number opens a separate window containing the cutlist details, including individual parts and components, design instructions, and hardware.
- **Deferred design:** The user will define the detailed cutlist contents and design later. Do not infer those specifications from this navigation decision.

### Q398 — Project-file folder location
**Custom decision confirmed.** Each project's linked Project-level file folder is named `site related` and is located inside that project's folder in SharePoint. Logical location: SharePoint / [project folder] / site related. No specific SharePoint site URL or document-library path has yet been supplied.

### Q399 — Project-file pop-up actions
**Custom decision confirmed.** Users may only view files in the Project-file pop-up. To change, edit, or delete files, they must use OneDrive to access the project's linked SharePoint `site related` folder and perform those actions there. Do not provide upload, replace, rename, edit, or delete controls inside the view-only pop-up. This rule concerns Project-level files; detailed Joinery Item and cutlist design remains deferred as previously requested.

### Q400 — Refreshing the file view
**Custom decision confirmed.** When files in the linked SharePoint `site related` folder change through OneDrive, automatically update the open Project-file pop-up to display the latest file version, without requiring a manual refresh. The pop-up remains view-only under Q399. Refresh timing and technical mechanism are not yet specified.

### Q401 — Architectural drawing reference navigation
**Custom decision confirmed; corrected by Q402.** Clicking the architectural drawing reference number in a Joinery Item's design tab opens the project's common architectural-drawings folder and locates the file matching that drawing number. The user then clicks the located file to open the drawing. The reference click itself does not automatically open the drawing file. Which application displays the folder remains to be defined.

### Q402 — Common architectural-drawings folder and file location
**Custom clarification confirmed.** All architectural drawings for a project are in the same folder. Do not assign a separate drawing-folder location to each Joinery Item or architectural drawing reference. Use the common folder and the clicked drawing number to locate the related file so the user can directly click it to open the drawing. This replaces the separate-folder premise of the original Q402 question. Q403 defines filename-based matching.

### Q403 — Matching drawing numbers to files
**Yes confirmed.** Each architectural drawing's filename contains its architectural drawing number. The system uses that number to automatically locate the matching file in the project's common architectural-drawings folder. The user clicks the located file to open it, as confirmed in Q401–Q402. Q404 defines which file to locate when multiple revisions match.

### Q404 — Multiple matching drawing revisions
**Custom decision confirmed.** When multiple files contain the same architectural drawing number, locate only the latest revision in the common drawing folder. The user then clicks that file to open the drawing. Q405 defines revision ordering.

### Q405 — Latest revision ordering
**Custom decision confirmed.** Determine the latest drawing revision by the highest revision number for numeric revisions, or the latest letter in alphabetical order for letter revisions (for example, 10 follows 9; C follows B). This comparison concerns the revision identifier, not the drawing number or file modification date. Ordering mixed numeric/letter schemes and multi-letter revisions remains undefined.

---

## 41. Reference Screenshot Review — Pending Design Confirmation

The user supplied 18 screenshots of a similar system and requested a complete review followed by related design questions, including clarification of the overall structure and links between screens where uncertain. All 18 were visually reviewed. The observations below are reference evidence, not automatically adopted requirements. Continue asking one question at a time and record confirmed answers in the relevant structured sections. Detailed cutlist design remains deferred until the user supplies it.

| Screenshot | Observed content and follow-up topics |
| --- | --- |
| 01 Dashboard | Project search/default/favourites/recent lists; personal tabs; employee absence/availability table; top-level module navigation. Clarify dashboard scope and relevant personal features. |
| 02 Dashboard contact | Contact directory with search, extension filters, export/print and new-entry controls. Clarify directory scope and management. |
| 03 Dashboard my order | Personal order list across projects, with supplier, product and ordered/due/arrived dates. Clarify how personal orders relate to Orderbook. |
| 04 Dashboard project detail | Project roles, status, classification, dates, contacts, notes, labour hours and access/lift details. Appears to be a close-up of 05. |
| 05 Dashboard project | Project tab containing the information shown in 04. Clarify its relationship to standalone Project Details in 11. |
| 06 JID | Item Details pop-up with Log selected; creation/modification metadata and change history; Details/Log/Actions/Query tabs. Clarify JID meaning and item/group/cutlist relationships. |
| 07 Orderbook Details 1 | Acoustic-panel order form with dimensions, material attributes, quantity, cost, tax, stock flag, attachments, internal and PO comments, and Create PO action. |
| 08 Orderbook Details 2 | Benchtop order form with underside, edging, laminate, joins and dimensions; shared order fields. |
| 09 Orderbook Details 3 | Contractor-manufacturing order form with description, cutlist and supplier references; shared order fields. Clarify type-specific forms, procurement lifecycle, PO grouping, stock and delivery links across 07–09. |
| 10 Orderbook 2.0 | Orders grouped by type, with priority, requester, project, supplier, product, costs and dates; due/overdue/arrived and personal filters. Clarify list-to-detail navigation and procurement dashboard relationship. |
| 11 Project Details | Separate project window with address, office/site contacts, labour statistics, lift details, project status, totals and close-out control; Project Stats/Cars/OH&S/Scope tabs. Clarify overlap with 04–05 and which tabs are needed. |
| 12 Tracking 2.0 | Joinery rows with cutlist, location, JID, description, status, size, quantity, assigned staff and workflow dates; multiple department tabs and filters. Repeated JIDs/cutlist numbers need relationship clarification. |
| 13 Tracking invoice | Same row structure with invoice-request information, selection, PDF and not-invoiced controls. Clarify invoicing linkage and permissions. |
| 14 Tracking item detail new | Close-up of item Details tab: level/room, Floor Plan/RLS/Joinery Details references, model files, document register, flags, Group ID/Item ID and estimator notes. Appears to show the same content as 15. |
| 15 Tracking item detail | Item Details pop-up in the Tracking context; previous/next navigation. Clarify required fields, reference types and file links. |
| 16 Tracking site measure | Tracking rows with required/measurement dates, snapshots and site-measure instructions. Clarify requests, completion evidence and mobile capture. |
| 17 Tracking status new | Close-up of status control: CLEAR/VOID/NOTE!/LIVE/APPROVED/HOLD, required notes, current-item/all update actions and status log. Appears to show the same control as 18. |
| 18 Tracking status | Status pop-up within Tracking. Clarify status meaning versus workflow stages and the scope of Update All. |

### Q406 — Reference-system entrance and module navigation
**Custom explanation confirmed for the reference system.** Dashboard is the main entrance to the software. Buttons at the top labelled Orderbook, Tracking and Cutlist each open another window dedicated to the selected module. The middle of Dashboard contains tabs; its Project tab displays the project details. Q407 confirms the navigation direction for the new software; Q408 identifies the entry point to the separate Project Details window shown in screenshot 11.

### Q407 — Navigation direction and UI flexibility
**Custom decision confirmed.** Use a navigation arrangement similar to the reference system described in Q406: Dashboard as the main entrance, access to Orderbook/Tracking/Cutlist module workspaces, and project details accessible from the Dashboard's Project tab. The design may extend the functionality and introduce a new UI; it does not need to reproduce the reference screens exactly. Specific additional features and navigation changes remain design proposals until confirmed through the ongoing interview. Existing confirmed workflow and permission rules continue to apply.

### Q408 — Tracking access to Project Details
**Custom explanation confirmed for the reference system.** Clicking the Info button in the Tracking window opens the separate Project Details window shown in screenshot 11, containing the Project Stats, Cars, OH&S and Scope tabs. Q409 confirms that it shares underlying project information with the Dashboard Project tab.

### Q409 — Shared project information across views
**Yes confirmed.** The Dashboard's Project tab and the Project Details window opened through Tracking's Info button share the same underlying project information. Changes made in one view appear in the other for the same project. These are two views of the same project record, not independently maintained copies.

### Q410 — Joinery IDs and internal cutlist numbers
**Custom decision confirmed.**

- **JID (Joinery ID):** A project-defined reference associated with each Joinery Item. Each project has its own naming convention. Multiple Joinery Items may share the same JID, so JID alone does not uniquely identify an individual item record.
- **Cutlist number:** The company's internal workflow-tracking reference, always exactly six digits. It is created in the Cutlist panel and then linked to one or several Joinery Items. Multiple Joinery Items may therefore share one cutlist number.
- **Distinct purposes:** Keep the project-defined JID separate from the company cutlist number. Sharing either reference does not by itself merge the individual Joinery Item records.
- **Relationship detail:** Q411 confirms that a Joinery Item may link to only one cutlist number. Number allocation rules and detailed cutlist contents are not established by this decision.

### Q411 — Cutlist links per Joinery Item
**No confirmed.** A single Joinery Item cannot link to more than one cutlist number. One cutlist number may be shared by several Joinery Items under Q410. This sets the maximum to one cutlist link per item; it does not require a cutlist link before an item can be created.

### Q412 — Shared cutlist production workflow
**No independent production completion times confirmed.** Each cutlist has one workflow. All Joinery Items linked to that cutlist share its production-stage progress and the same completion date/time for each production stage. Record each production-stage completion once against the cutlist and reflect it across all linked Joinery Items. Each stage has its own completion time; that time is shared by the linked items. This refines earlier item-level workflow descriptions: individual Joinery Items remain separate records, but do not maintain independent production workflows when they share a cutlist. Whether this shared timing also applies to delivery and installation remains to be clarified.

### Q413 — Shared delivery and individual installation
**Custom decision confirmed; scheduling clarified by Q414.** Shared cutlist timing applies to delivery: all Joinery Items linked to one cutlist share its delivery completion date/time. It does not apply to installation, which is individual to each Joinery Item. Q414 confirms that installation scheduling is coordinated outside the system, rather than recorded as item-level or project-level installation schedules here. This resolves the delivery/installation scope left open in Q412.

### Q414 — Installation scheduling outside the system
**Custom decision confirmed.** The Project Manager and Site Installation Manager communicate and coordinate the installation schedule outside this system. Do not record that installation schedule in the software. This supersedes earlier assumptions about recording installation schedules or enforcing item schedules against project-level installation dates. Existing actual installation progress/completion tracking is separate from this scheduling exclusion; the role responsible for recording item completion is the next clarification.

### Q415 — Recording actual installation completion
**Custom decision confirmed.** The Site Installation Manager records actual installation completion for each Joinery Item in the system. Completion is recorded individually for each item, not shared across the cutlist. Installation schedules remain outside the system under Q414.

### Q416 — Item ID, Group ID and related part rows
**Custom decision confirmed.** Each main Joinery Item has its own unique internal number, used as both its Item ID and its Group ID. Tracking also displays related part rows when required, including metal parts, benchtops and cushions. Each related part has its own distinct Item ID and shares the main Joinery Item's Group ID. The shared Group ID identifies the specific Joinery Item to which that part belongs; the part is linked to that Joinery Item only. These internal identifiers are distinct from the project-defined JID and the company cutlist number described in Q410. The cutlist links and workflow behaviour of related part rows remain to be clarified; sharing a Group ID alone does not establish those rules.

### Q417 — Cutlist and supplier-order references in Tracking
**Custom decision confirmed.** Cutlist numbers are assigned only to Joinery Items. Related metal, benchtop and cushion rows do not receive cutlist numbers. Once an order for a related part has been issued to its supplier, display the order number on that part's Tracking row in the same position used for a Joinery Item's cutlist number. The displayed reference therefore depends on the row type: cutlist number for a Joinery Item, issued supplier-order number for a related part. The six-digit cutlist format does not establish the format of order numbers. This resolves the cutlist-link question left open in Q416; related-part workflow details remain to be clarified.

### Q418 — Tracking order-number navigation
**Custom decision confirmed.** Clicking the issued order number on a related-part row in Tracking navigates to Orderbook and locates the matching order number there. This provides the link from the metal, benchtop or cushion Tracking row to its order record. This decision does not specify automatically opening the order-detail pop-up.

### Q419 — Empty workflow-stage area for related parts
**Custom decision confirmed.** For related metal, benchtop and cushion rows in Tracking, show no workflow stages; leave the entire workflow-stage area empty. Do not populate it with the parent Joinery Item's cutlist stages or supplier-order stages. The related-part row and its issued order-number link remain as confirmed in Q416–Q418. This is a Tracking display rule and does not define the underlying supplier-order lifecycle.

### Q420 — Related-part row placement
**Yes confirmed.** In Tracking, display related metal, benchtop and cushion rows directly beneath their parent Joinery Item, using the Group ID relationship confirmed in Q416. Their workflow-stage area remains empty under Q419. Q421 confirms expand/collapse controls.

### Q421 — Expand and collapse related-part rows
**Yes confirmed.** Users can expand or collapse each Joinery Item's related-part rows in Tracking. Expanding displays its related parts directly beneath the parent item; collapsing hides those related-part rows while leaving the parent Joinery Item visible. The initial expanded/collapsed state remains to be defined.

### Q422 — Default related-part visibility
**Yes confirmed.** Related-part rows are collapsed by default when Tracking first opens. Users can expand each Joinery Item to see its related metal, benchtop and cushion rows under Q421. This resolves the initial-state question left open in Q421.

### Q423 — Creating related-part rows
**Custom decision confirmed.** The Drafter (Designer/Draftsperson role) or Project Manager can create related metal, benchtop and cushion rows beneath a Joinery Item. Each created part has its own Item ID and shares its parent Joinery Item's Group ID under Q416. Existing change-recording rules apply.

### Q424 — Related-part creation and order requests
**No confirmed.** Creating a related metal, benchtop or cushion row in Tracking does not automatically create a linked order request in Orderbook. The action used to create and link the order request remains to be defined. Issued order numbers are displayed and navigated as confirmed in Q417–Q418.

### Q425 — Create Order entry point in Tracking
**Custom decision confirmed.** Tracking has an O/BOOK subtab. Users switch to that subtab and click its Create Order button to initiate an order request for a related part. This is an explicit user action, consistent with Q424. The subsequent form, prefilled information and exact linking interaction remain to be clarified.

### Q426 — Create Order details form
**Custom decision confirmed.** Clicking Create Order in Tracking's O/BOOK subtab opens the order-details form shown in the supplied Orderbook Details screenshots (07–09). Those screenshots provide examples for acoustic panels, benchtops and contractor manufacturing. The reference establishes the form opened by this action; exact field requirements, type-specific variations, automatic prefilling and linking behaviour remain to be confirmed.

### Q427 — Prefilled order-details fields
**Custom decision confirmed.** When creating an order through Tracking's O/BOOK subtab, automatically carry over PROJECT, LOCATION and CUTLIST NO. into the Orderbook Details form. Q417 establishes that related-part rows do not themselves receive cutlist numbers, so the source of the CUTLIST NO. value for these orders must be clarified. Do not infer a cutlist assignment to the related part from this form field.

### Q428 — Parent cutlist reference on related-part orders
**Yes confirmed.** The CUTLIST NO. prefilled in an order for a related metal, benchtop or cushion part comes from that part's parent Joinery Item. Use the parent relationship established by Group ID in Q416. This is an order reference to the parent's cutlist; the related-part row does not receive its own cutlist number under Q417. This resolves the source question in Q427. Behaviour when the parent has no cutlist number yet remains to be defined.

### Q429 — Orders before cutlist assignment
**Yes confirmed.** A related-part order can be created before its parent Joinery Item has a cutlist number. A parent cutlist number is therefore not required to create the order; CUTLIST NO. remains unfilled when no parent cutlist number is available. The order remains associated with its related part and parent Joinery Item. Q430 confirms later automatic population.

### Q430 — Automatic cutlist update on an existing order
**Yes confirmed.** When a related-part order has a blank CUTLIST NO. and its parent Joinery Item later receives a cutlist number, automatically populate the order's CUTLIST NO. with the parent's number. The existing order-to-part and Group ID relationships provide the link. Q431 confirms automatic updates after later replacement.

### Q431 — Updating orders after cutlist replacement
**Yes confirmed.** If the parent Joinery Item's cutlist number is replaced, automatically update the CUTLIST NO. on all linked related-part orders to the new number. Record the change under the existing audit-history rules so the previous reference remains traceable.

### Interview continuation topics
Start with screen/module relationships and what the user wants to carry into the new system. Then clarify project-view overlap, identifiers and repeated rows, drawing-reference fields, tracking tabs and site measurements, status actions, procurement forms and links, invoicing, and personal/dashboard features. Compare each topic with existing confirmed requirements before asking; do not reopen settled archive questions. Screenshot labels alone do not establish data relationships or permissions. Mixed revision conventions from Q405 remain an open edge case.

---

## 42. Current Question Status

Questions have progressed through **Q540**. Q432–Q540 were added on
2026-09-17 by the alignment pass against the existing JoineryFlow codebase and
are recorded in `docs/plan-v1/OPEN-QUESTIONS.md`; §43 below carries the ones
confirmed so far.

**Confirmed on 2026-09-18:** Q433 = Option 1, Q435 = Option 2, Q437 = Option 1,
Q438 = Option 1, Q439 = Option 3, Q440 = Option 1, Q441 = Option 1,
Q443 = Option 1, Q445 = Option 1, Q446 = Option 1, Q539 = Option 2,
Q540 = Option 1, Q442 = Option 1, Q447 = Option 1, Q448 = Option 2,
Q450 = Option 1, Q449 = Option 1, Q452 = Option 1, Q453 = Option 1,
Q541 = Option 1, Q432 = Option 1, Q444 = Option 1, Q451 = Option 1,
Q542 = Option 3, Q502 = Option 1, Q504 = Option 2, Q506 = Option 1,
Q507 = Option 2, Q503 = Option 3, Q505 = Option 1, Q543 = Option 3,
Q544 = Option 1, Q434 = Option 2, Q436 = Option 2, Q475 = Option 2,
Q474 = custom decision, Q459 = Option 3, Q461 = Option 2, Q462 = Option 1,
Q545 = Option 2, Q454 = Option 1, Q455 = Option 1, Q457 = Option 1,
Q546 = Option 1, Q456 = Option 1, Q495 = Option 1, Q497 = Option 2,
Q499 = Option 2, Q496 = Option 3, Q498 = Option 2, Q500 = Option 2,
Q501 = Option 1, Q508 = Option 1, Q509 = Option 1, Q511 = Option 2,
Q513 = Option 3, Q510 = Option 2, Q512 = Option 1, Q466 = Option 2,
Q467 = Option 2, Q469 = Option 3, Q470 = Option 1, Q472 = Option 1,
Q473 = Option 1, Q479 = Option 1, Q481 = Option 1, Q482 = Option 1,
Q485 = Option 2, Q515 = Option 1, Q516 = Option 2, Q517 = Option 2,
Q518 = Option 2, Q521 = Option 1, Q522 = Option 1, Q524 = Option 1,
Q520 = Search first, Q525 = Option 2, Q526 = Option 1, Q527 = Option 2,
Q468 = Option 1, Q487 = Option 1, Q488 = Option 1, Q489 = Option 1,
Q491 = Option 2, Q548 = Option 2, Q490 = Option 1, Q493 = Option 1,
Q494 = Option 2.

**Next unanswered questions: Q432** (which roles may click Create Order),
**Q434** (committed scope vs. wish list), **Q436** (production data today), and
all of §B–§P in `OPEN-QUESTIONS.md`. §B and §C are now design-blocking, since
Q437 selected Cutlist + related parts as the next sub-project.

This file is the canonical **Plan V1** project source for the Joinery Workflow Software and should be used as the authoritative basis for future questions and design work in this project.

---

## 43. Codebase Alignment Decisions — Q432 onward

These questions arose from mapping Plan V1 onto the existing JoineryFlow
codebase (nine shipped sub-projects, Alembic head `0025`). The full gap
analysis is `docs/plan-v1/ALIGNMENT.md`; the full question set is
`docs/plan-v1/OPEN-QUESTIONS.md`.

### Q433 — Relationship between Plan V1 and the existing codebase
**Option 1 confirmed.** Plan V1 is the **roadmap for this codebase**.
JoineryFlow evolves into it incrementally, accepting the re-architecture work
this implies rather than rebuilding from scratch or specifying a separate
product. Plan V1 therefore governs future design work in this repository, and
`CLAUDE.md` remains the statement of what is currently true.

### Q435 — Whether shipped behaviour may be broken
**Option 2 confirmed.** Shipped schema and behaviour **may change, but only
behind migrations that preserve existing data**. Breaking changes are not
forbidden; unmigrated ones are. Every reshape ships as a real Alembic
migration with a data step, not a drop-and-recreate.

### Q437 — Next sub-project
**Option 1 confirmed.** **Cutlist entity + related-part rows**, built as a
single change. They are cheaper together than apart because both reshape the
Tracking row model and the item/workflow relationship, and together they
unblock Q410–Q431 — the entire reference-screenshot section.

### Q438 — Cutlist as a first-class entity
**Option 1 confirmed.** A new `cutlist` entity is created. Joinery Items link
to it, and the production workflow moves onto it, implementing Q410–Q413:
several Joinery Items share one cutlist and one set of production-stage
completions, with delivery shared and installation individual per item.

Consequences to design against (from `ALIGNMENT.md` §3.1):

- `item_stages (item_id, stage_key, due_date, done_date)` is today strictly
  per-item and must move to the cutlist.
- Shop Floor Ops (migration `0020`) keys `worker_assignment` and
  `stage_completion_log` off `(item_id, stage_key)`, including the partial
  unique index `uniq_active_assignment`. That module is reworked, not extended.
- `items.num` is today a `UNIQUE NOT NULL integer` rendered as the CUTLIST
  number in Tracking. Under Q410 the cutlist number is a separate six-digit
  company reference that several items share, so the two must be separated.
- Q413/Q415 split the lifecycle: production and delivery stages belong to the
  cutlist, installation completion stays on the individual item.

### Q439 — Where the workflow stages are stored
**Option 3 confirmed.** `item_stages` remains **per item**. Completing a shared
production stage writes the same completion date/time to **every** Joinery Item
linked to that cutlist. No separate `cutlist_stages` table is created.

The stored per-item rows are therefore a **projection** of cutlist-level truth,
not an independent record. The authoritative record of who completed what and
when is the cutlist-level completion log (Q445); `item_stages` is the
read-optimised copy that Tracking renders.

### Q440 — Joinery Items without a cutlist
**Option 1 confirmed.** A Joinery Item may exist with **no cutlist number
indefinitely**. The cutlist is assigned later in the workflow. This is
consistent with Q429, which already allows a related-part order to be created
before the parent Joinery Item has a cutlist number.

### Q441 — Displaying a shared cutlist in Tracking
**Option 1 confirmed.** Each Joinery Item keeps its own Tracking row and the
shared workflow-stage strip is drawn on **every** such row, as in reference
screenshot 12. Items are not collapsed under a cutlist header row.

This is what makes Q439's fan-out worth having: Tracking reads the per-item
stage rows directly, with no join to the cutlist.

### Q445 — Ownership of production assignment and completion
**Option 1 confirmed.** Worker assignment and stage completion are keyed at
**cutlist level for production stages** and at **item level for installation**.
One worker owns a given production stage for the whole cutlist; installation is
assigned and completed per Joinery Item, per Q413 and Q415.

### Q443 — Scope of cutlist number uniqueness
**Option 1 confirmed.** Cutlist numbers are **unique company-wide** — one
sequence across all projects, not a per-project sequence. A cutlist number is
therefore unambiguous in search, on a printed sheet and on a shop-floor scan.

### Q446 — Scope of the completion undo
**Option 1 confirmed.** Undo reverses the **whole cutlist's** completion
atomically: the cutlist-level completion log entry and the fanned-out
completion date on every linked Joinery Item. If completion is a single
cutlist-level act under Q445, so is undoing it.

### Q539 — Linking an item to a cutlist with completed stages
**Option 2 confirmed.** The newly linked Joinery Item's earlier stages are
**left blank**. It catches up when a later stage completes and fans out.

This means a Joinery Item's stage strip may legitimately differ from its
siblings on the same cutlist, and from the cutlist's own completion record.
That is accepted. The cutlist-level completion log remains the authoritative
answer to "has this stage been done"; the per-item strip is a projection that
may lag for a late-linked item. Undo under Q446 is simply a no-op on an item
that never received the fanned-out date.

### Q540 — Migration of existing internal item numbers
**Option 1 confirmed.** Each existing Joinery Item receives **its own cutlist**,
carrying its current internal number across as that cutlist's number. Nobody
loses the number they recognise, and cutlist **sharing begins only with new
work**. The company-wide sequence (Q443) starts above the highest existing
number.


### Q442 — Cutlist number allocation
**Option 1 confirmed.** Cutlist numbers are **system-allocated sequentially**
on creation in the Cutlist panel, from the company-wide sequence of Q443.

### Q447 — Storage of related-part rows
**Option 1 confirmed.** Related metal, benchtop and cushion rows are stored as
rows in the existing Joinery Item table, distinguished by a **row-type**
discriminator and linked to their parent by a self-referencing parent
reference. They therefore receive their own Item ID naturally, as Q416
requires, and share the parent's Group ID.

Every query that reads Joinery Items must filter on the row type. In the
current codebase that is **50 SQL call sites across 13 modules**; the highest
risk is Production/Shop Floor, since Q419 gives related parts no workflow
stages at all.

### Q448 — The related-part type list
**Option 2 confirmed.** The list is a **configurable lookup table**, seeded with
metal, benchtop and cushion. New types can be added without a schema change,
consistent with how workflow stages and statuses are already configured.

### Q450 — Status of a related part
**Option 1 confirmed.** A related part carries **its own status**, independent
of its parent Joinery Item, so a single stuck supplier order can be flagged
without changing the parent's status.

### Q449 — Nesting of related parts
**Option 1 confirmed.** **One level only.** A related part cannot itself have
related parts; its parent must be a Joinery Item.

### Q452 — Moving a related part to another Joinery Item
**Option 1 confirmed.** A related part **may be reassigned** to a different
parent Joinery Item. The move updates its Group ID and, following the
precedent set by Q431, the parent cutlist reference on any supplier order
already linked to that part. Every such move is recorded in the change history.

### Q453 — Existing Group ID values
**Option 1 confirmed.** The existing Group ID field is **repurposed** for the
semantics of Q416, with existing values migrated. For a main Joinery Item the
Group ID is its own Item ID; related parts carry their parent's.

### Q541 — Relationship between Item IDs and cutlist numbers
**Option 1 confirmed.** Item IDs and cutlist numbers draw from **one shared
company-wide sequence**, so the same six-digit number is never both an Item ID
and an unrelated cutlist number. Each series will contain gaps, which is
acceptable. This preserves the property Q540 creates for every migrated record,
where a Joinery Item's Item ID and its cutlist number are the same number.


### Q432 — Authority to create a related-part order
**Option 1 confirmed.** The roles that may click **Create Order** and submit a
related-part order request are the existing Orderbook write holders:
Management, Project Management, Designer/Draftsperson and Purchasing. No new
permission is introduced for this action.

### Q444 — Project scope of a cutlist
**Option 1 confirmed.** A cutlist belongs to **exactly one project**. Cutlists
do not span projects.

### Q451 — Cost of a related part
**Option 1 confirmed.** A related part's order cost **rolls into its parent
Joinery Item's cost**, consistent with §16's stated granularity of Project and
Joinery Item level rather than component level.

### Q542 — Scope of the Cutlist sub-project
**Option 3 confirmed.** The sub-project selected in Q437 also carries the
**full Orderbook rework** — the order entity, the order-details forms of
Q426, purchase-order creation and the supplier registry of §21 — rather than
deferring them or shipping a minimal order record.

This makes the sub-project substantially larger than "Cutlist + related parts":
it now spans the cutlist entity, the Tracking row model, and procurement.

### Q543 — Location of the parent item's cost
*Raised by the combination of Q451 and Q542; pending.*


### Q502 — Basis for the order and purchase-order work
**Option 1 confirmed.** The existing legacy procurement namespace is
**revived and converged** into the live product surface, rather than being
replaced by a newly built one. Its vendor, purchase-order, line-item,
attachment and approval tables become the basis of the order work.

Two conditions follow from the current codebase and are binding on that
revival: the legacy tables carry **no workspace scoping whatsoever**, which
must be added to meet the isolation standard every other surface now holds;
and the legacy inventory tables **duplicate** the sheet-stock table added
later, which Q544 resolves.

### Q504 — Orders and procurement batches
**Option 2 confirmed.** The order is the **commercial record** — supplier,
purchase-order number, cost. Procurement batches and their allocations
**remain beneath it** as the allocation mechanism that answers "is this
Joinery Item blocked on a material". Two layers, each with one job.

### Q506 — Supplier as an entity
**Option 1 confirmed.** Supplier becomes a **real entity**. The free-text
supplier fields on the six Material Catalogue tables are repointed to it. This
is the prerequisite for §21's supplier comparison, supplier performance
tracking and the five supplier statuses.

### Q507 — Coverage of orders
**Option 2 confirmed.** Orders cover **all procurement** — board, hardware and
related parts alike — not only related parts. Batches become an internal
allocation detail beneath the order layer.

### Q503 — Structure of the order-details form
**Option 3 confirmed.** One **generic order form**: fixed fields for everything
shared across order types (project, location, cutlist number, quantity, cost,
supplier, comments), plus a flexible attributes store for the type-specific
fields seen in the reference forms — benchtop underside, edging, laminate and
joins; acoustic-panel dimensions; contractor-manufacturing references.

Consequence: type-specific fields are not individually validated or readily
searchable, so §21's supplier comparison can compare on the shared fields only.

### Q505 — Purchase orders
**Option 1 confirmed.** **Create PO** creates a **real purchase order** with its
own number, supplier, line items and status — not merely a note that an order
was issued. This is what §21's receiving flow, deposits, progress payments and
credits attach to. Reviving the legacy purchase-order tables under Q502
supplies this directly.

### Q543 — Location of the parent item's cost
**Option 3 confirmed.** **Deferred** until the financial model of §16 is
scoped. Related-part orders carry their own cost; no roll-up to the parent
Joinery Item is built in this sub-project. Q451 therefore records where that
cost will land, not what this sub-project does.

### Q544 — Duplicate inventory tables
**Option 1 confirmed.** The **sheet-stock table stays**; the legacy inventory
and inventory-movement tables are **dropped** rather than revived. The columns
worth keeping — reserved quantity, reorder point and reorder quantity — are
ported onto the sheet-stock table, which §18's reservation and reorder-alert
requirements will need anyway. Only the purchase-order and vendor half of the
legacy namespace is revived.


### Q434 — Extent of committed scope
**Option 2 confirmed.** The **joinery-workflow half of Plan V1 is committed
scope**. The IT-governance half — template versioning, validation, simulation,
the technical-debt register, Initiatives and the escalation engine (§7–§8 and
§35–§38) — is **aspirational**, to be revisited rather than scheduled.

### Q436 — Live data today
**Option 2 confirmed.** There are **pilot users on the demonstration
workspace**. Real records exist but nothing business-critical, so every
migration needs a correct data step while re-seeding remains an acceptable
recovery.

### Q474 — Where the Cutlist module lives
**Custom decision confirmed. The Cutlist module *is* the existing `List`
tab.** It is not a seventh primary tab and not a secondary-strip entry. The
fixed six-tab information architecture is unchanged.

This matches how the system is already built: the permission module governing
that tab is already the one guarding the cutlist print and item-attachment
routes. The tab is being named for what it has always contained.

### Q475 — Module workspaces as separate windows
**Option 2 confirmed.** Orderbook, Tracking and Cutlist open as **genuinely
separate windows**, as in the reference system, so that two of them can be kept
open side by side on separate monitors.

This is a real departure from the current single-shell application, which
resolves the signed-in user once and draws one set of navigation chrome around
every screen. Q545 settles precisely what "separate window" means before it is
built.

### Q545 — Definition of a separate window
**Option 2 confirmed.** A **normal new browser tab**, which the user can drag
out into its own window whenever they want two modules side by side. Not a
fixed popup window. Deep links keep working and no separate sign-in path is
needed.

### Q459 — The workflow stage list
**Option 3 confirmed.** The **existing ten production stages are kept** for
now. The cutlist takes over the current lifecycle unchanged. The additional
stages named in §22 — Material Take, Shop Drawing Approved, Procurement, QC,
Packing and Completed — arrive with the sub-projects that introduce that work,
rather than being added in advance as empty columns.

### Q461 — Order of Painting and Assembly
**Option 2 confirmed.** The **current default order is kept**, with the
existing per-item flag continuing to reverse it where a job paints after
assembly. §22's ordering is treated as one project pattern rather than the
company-wide rule.

### Q462 — Scope of the stage list
**Option 1 confirmed.** **One company-wide stage list**, with individual
projects marking stages not applicable — which is what §22 already describes,
and which keeps the Tracking Dashboard's consistent layout under §4.1. A
per-template stage list is not built, consistent with Q434 treating the
template system as aspirational.


### Q454 — Area and Room as entities
**Option 1 confirmed.** **Both Area and Room become real entities**, with
Joinery Items referring to them, rather than remaining free text.

### Q455 — Mapping onto existing information
**Option 1 confirmed.** **Area is the existing site location** (the field
holding values such as "Stage 1" and "Stage 2") and **Room is the existing room
number together with its description** (for example `K1` / Kitchen). Plan V1's
Area and Room already exist in the system under other names, so this is a
rename and normalisation rather than a new structure.

### Q457 — Scope of Areas and Rooms
**Option 1 confirmed.** Areas and Rooms are **created per project**. They are
not drawn from a shared company-wide library: one project's "Stage 1" bears no
relation to another's.

### Q546 — Level and Zone
**Option 1 confirmed.** The system also records a building **level** and a
numeric **zone**, which Plan V1's hierarchy does not name. Both are **kept as
attributes** of the record rather than becoming levels of the drill-down. The
hierarchy remains Project → Area → Room → Joinery Item exactly as §2 states,
and the Tracking Dashboard's consistent layout is unaffected.


### Q456 — The "stage" terminology rule
**Option 1 confirmed.** Once the site-location field is renamed to Area, the
word **stage** can only mean a workflow stage, and the standing rule warning
against the bare word is **retired**. The rule stays in force until the rename
has actually been made.

### Q495 — Material Take as a record
**Option 1 confirmed.** Material Take is its **own record**, generated from the
Joinery Item's parts and hardware, then adjusted, approved and frozen. It is
not merely a flag on the live lines. Keeping it separate is what allows §19's
later impact review — comparing an approved take against a changed Shop
Drawing — to have something to compare against, and what preserves the original
history §19 requires.

### Q497 — Material Take and Shop Drawing Approval
**Option 2 confirmed.** Material Take is **advisory**, not a hard gate. An
approver is warned when no approved take exists but may still approve the Shop
Drawing. The existing drawing approval workflow is unchanged.

### Q499 — Releasing the Material Summary to Procurement
**Option 2 confirmed.** Project Manager confirmation is **advisory**.
Procurement may order against unconfirmed summary lines where lead times
require it, with the unconfirmed state clearly flagged.

**This knowingly departs from §20**, which states that the summary is released
to Procurement only after Project Manager confirmation. The decision here
supersedes that sentence: the confirmation is a strong recommendation, not a
block, so that long-lead material is never held up by an unconfirmed summary.


### Q496 — Source of the generated Material Take
**Option 3 confirmed.** The take is generated from **both** the Joinery Item's
parts and hardware — which express the demand — **and** the cutting nest, which
knows the real sheet counts including offcut waste.

Because a nest only exists once parts have been listed, which is later than the
point §19 places Material Take, the take is first generated from parts and
hardware and later **refined from the nest**, advancing its version (Q500). No
work is blocked meanwhile, since Q497 makes the take advisory.

### Q498 — The Material Summary and the existing procurement queue
**Option 2 confirmed.** **Both exist.** The live procurement queue continues to
show current demand for early visibility, and the Material Summary is the
formal artefact the Project Manager confirms and releases.

### Q500 — Flagging outdated summary lines
**Option 2 confirmed.** Each approved take carries a **version**. The Material
Summary records which version each line consumed, and any line whose take has
since advanced is flagged as potentially outdated, as §20 requires.

### Q501 — Stock reservation
**Option 1 confirmed.** The optimiser continues to **read stock without
reserving or consuming it**. Reservation is a separate, explicit action, so
exploring a nest never commits material. §18's reservation features are built
on that separate action when they arrive.


### Q508 — The lock types
**Option 1 confirmed.** All three lock types in §12 are adopted: **Hard Lock**
(only authorised management can unlock), **Controlled Lock** (a change may be
requested but requires approval) and **Approval Lock** (information locks
automatically once approved).

### Q509 — The existing ownership lock
**Option 1 confirmed.** The current advisory ownership lock becomes a
**Controlled Lock**. Today a second person's save succeeds and merely records
that the lock was overridden; under a Controlled Lock that becomes a request
requiring approval. This is a real change to existing behaviour, made under the
migration rule confirmed in Q435.

### Q511 — Detecting simultaneous edits
**Option 2 confirmed.** Simultaneous-edit detection is added **only where
conflicts actually occur** — the Joinery Item editor, the cutlist, and orders.
Elsewhere the last save wins, as today.

The three lock types make this sufficient: locks prevent most collisions
outright, so detection is only needed where no lock applies. The conflict
comparison and resolution flow of Q364–Q378 therefore operates on those three
surfaces.

### Q513 — Rollback
**Option 3 confirmed.** **Rollback is not built.** The change history remains a
complete record of who changed what, when, and from what value to what value,
but it cannot restore a previous state.

**This knowingly departs from §11**, which requires at least the last twenty
change states to be retained for rollback and describes rollback as creating a
restorative revision. That requirement is superseded: history is for
accountability and review, not restoration. Q514, which asked what rollback
applies to, no longer arises.


### Q510 — What can be locked
**Option 2 confirmed.** Locks apply at **Joinery Item and Project level only**.
The wider list in §12 — fields, components, Areas, tabs, revisions and
department information — is not implemented.

### Q512 — Granularity of simultaneous-edit detection
**Option 1 confirmed.** Detection is **per field**. When two people edit the
same record, only the fields genuinely in conflict are held for resolution, and
the rest of the record stays editable, as Q366 requires.

This does not contradict Q510. A **lock** is a governance action a person
takes, and those exist only at Item and Project level. A **conflict hold** is a
transient state the system enters on its own, and that is per field.

### Q466 — The permission engine
**Option 2 confirmed.** The permission model becomes **configurable data rather
than code**, with departments, IT-authored user groups and multiple group
membership — but scoped **down to Project level only**. Per-Joinery-Item and
per-tab permissions described in §3 are **not** built: they would place a
permission check on every row of every list for very little practical gain.

### Q467 — Departments
**Option 2 confirmed.** Departments remain a **descriptive label**. All
permission meaning is carried by **user groups**, which can already express any
department's access. The department dashboards of §4.2 key off group
membership.


### Q469 — The action list
**Option 3 confirmed.** The **four existing actions are kept** — view, edit,
approve and comment. The remaining actions named in §3 are expressed as rules
about particular records rather than as separate grantable permissions.

### Q470 — Critical actions
**Option 1 confirmed.** **Lock, Unlock, Override and Configure** are critical:
the normal "most permissive group wins" resolution does **not** apply to them.
Belonging to two groups must never quietly confer the authority to override a
Hard Lock.

Because Q469 keeps these out of the grant list, this rule is enforced in the
rule layer described under Q472 — not by the grant resolution, which has
nothing to resolve for them.

### Q472 — The existing record-specific rules
**Option 1 confirmed.** Rules that today live in individual request handlers —
that only a Designer/Draftsperson may change item content, that a reviewer may
not approve their own upload, that only a creator or manager may edit a record,
that a worker may undo a completion within five minutes — **move into the
permission engine**, so that any access question has a single place to be
answered.

This requires the engine to express conditions about the record and the time,
not merely who holds which grant.

### Q473 — Comments
**Option 1 confirmed.** The **comment capability becomes real**: §29's
context-based comments are built, and the long-standing comment permission
stops describing something the system cannot do.


### Q479 — The existing document store
**Option 1 confirmed.** The system's own document store **remains**, serving
shop drawings, Joinery Item attachments and sample photographs. SharePoint is an
**additional** surface, used for Project-level files only. This matches Q392,
which already keeps Project-level files separate from Joinery Item files.

### Q481 — Connecting to Microsoft 365
**Option 1 confirmed.** The system connects with **its own single application
identity**, not as each signed-in person.

A consequence to be aware of: Microsoft no longer decides who may see which
project's files. The system's own project permissions become the only control,
so a mistakenly granted project access exposes that project's SharePoint files
as well.

### Q482 — Keeping the file view current
**Option 1 confirmed.** The open Project-file view **checks for changes on a
timer** while it is open, rather than receiving a push from Microsoft. The
interval is not yet fixed; fifteen seconds is proposed, matching the refresh
cadence already used on the Shop Floor board.

### Q485 — Finding a drawing by its number
**Option 2 confirmed.** Files are matched by a **defined filename convention**
rather than a loose text search, so that a drawing number never matches a
longer number that merely starts with it, and the revision can be read
reliably.

**The convention itself has not yet been supplied**, so this cannot be built
yet. Q547 records what is needed.

### Q547 — The drawing filename convention
*Raised by Q485; pending — a real example filename is required.*


### Q515 — Quality Control as a module
**Option 1 confirmed.** QC becomes **its own module**, with defects and
checklists and its own permissions, rather than a checkbox hanging off the
production workflow. This is what backs the QC Dashboard named in §4.2.

Note that QC is therefore **not added as a workflow stage**. §22 lists QC among
the stages, but §26 describes QC as checking *the work just completed* at
whatever stage that was — which is a cross-cutting activity, not a milestone of
its own. The workflow stage list is unchanged (Q459).

### Q516 — Recording rework
**Option 2 confirmed.** Internal Rework and Full Rework are **one kind of
record with a type**, not two separate things. They differ in when they occur
and in how much work they involve, but what must be recorded — cause, scope,
cost and responsibility — is the same.

### Q517 — Rework and the workflow
**Option 2 confirmed.** Rework **does not re-open completed stages**. It is
recorded alongside them, with its own progress.

This also avoids a problem the shared cutlist would otherwise create: since
production stages belong to the cutlist and are shared by every Joinery Item
linked to it, re-opening a stage for one item would have re-opened it for all of
them. It keeps the completion history truthful — the item really was assembled
on that date, and the rework records what happened after.

### Q518 — The QC timing rule
**Option 2 confirmed.** §26's rule about what happens depending on how far the
work has progressed is shown as **guidance**; the QC operator chooses. The
operator may know something the recorded stage does not.


### Q520 — Order of the remaining subsystems
**Search first, confirmed.** Of the six subsystems still to build — search,
comments, notifications, tasks, reporting and KPIs — **search is built first**.
It depends on none of the others and works against information the system
already holds.

### Q521 — Notification channels
**Option 1 confirmed.** Notifications are **in-app only** to begin with. Email
and mobile push follow later.

A consequence worth carrying forward: an in-app notice reaches someone only when
they next sign in. Several parts of this plan assume more than that — daily
reminders about unresolved conflicts, overdue-milestone escalation, and the
"mandatory channels" of the critical-notification rules, which with a single
channel have nothing to escalate to. Until email is added, nothing genuinely
time-critical should depend on a notification alone.

### Q522 — How email will be sent
**Option 1 confirmed.** When email is added, it is sent by **standard mail
relay (SMTP)** rather than through a third-party sending service or the
Microsoft 365 mail API. Under Q521 no email is sent in the first release, so
this settles the mechanism ahead of the need.

### Q524 — Tasks
**Option 1 confirmed.** Tasks are a **real record** with an assignee, a due
date and a status — not a view assembled from existing work. §10 requires tasks
that are created manually, by configured rules, from changes and at another
person's request, and none of those can be derived from work already tracked.


### Q525 — How search is built
**Option 2 confirmed.** Search is built on a **dedicated search service**
rather than on the database's own text search, for better relevance, tolerance
of misspelling, and filtering across the many kinds of record §13 lists.

This is the first additional piece of infrastructure the system has needed. It
brings an index that must be kept in step with the database, and a new
component to run and monitor.

### Q526 — Sharing reports outside the company
**Option 1 confirmed.** Secure external links are built as §31 describes —
unique link, password, expiry, revocation, a record of who viewed and when, and
a choice of a fixed snapshot or live information.

This is the first place the system shows a particular project's information to
someone without an account, so the link itself carries the whole of the
protection and warrants its own security review.

### Q527 — How KPIs are defined
**Option 2 confirmed.** KPIs are a **fixed catalogue of measures** built into
the system, from which management chooses what to display. There is no formula
editor.

**This departs from §32**, which says IT defines KPI formulas. Adding a new KPI
requires a change to the system rather than configuration. The trade is
predictability: no formula can be written that is invalid, unsafe or ruinously
slow.

### Q468 — Today's roles and the new groups
**Option 1 confirmed.** The seven existing roles become the **seven starting
groups**, carrying exactly the access they grant today. Nobody's access changes
when the new permission model arrives, and IT then creates
department-shaped groups as they are needed.


### Q487 — The Tender Dashboard and the existing quoting module
**Option 1 confirmed.** The Tender Dashboard **wraps** the existing quoting
module rather than replacing it. The quote that the system already produces
becomes one step of the tender lifecycle, and nothing already built is
discarded.

### Q488 — The tender lifecycle
**Option 1 confirmed.** The **full twelve-stage lifecycle of §5 is adopted**,
replacing the six states the quoting module uses today. The module, its data
and its quotes survive under Q487; it is the set of states that changes, and
existing quotes are migrated onto the new stages.

One existing state has no equivalent in §5: a quote that **lapsed** because its
validity window passed. §5 ends at Won, Lost and Withdrawn. Q548 settles where
lapsed quotes belong.

### Q489 — Preliminary Joinery Items at handover
**Option 1 confirmed.** Preliminary Joinery Items created during tender
**become real Joinery Items** when the project is handed over, delivering §6's
requirement that nothing already captured is re-entered by hand.

This requires a defined correspondence between a priced quote line and a
buildable Joinery Item, which the system does not have today.

### Q491 — Contract Value
**Option 2 confirmed.** Contract value is held as a **record with history** —
the original value agreed at handover, every approved variation, and the
resulting current value — rather than as a pair of fields. §17 requires that
the original is never overwritten, and §16 reports Original and Current
separately, which a history supports and two columns do not.

### Q548 — Lapsed quotes in the new lifecycle
**Option 2 confirmed.** A quote that **lapses is recorded as Lost**. No separate
Expired outcome is added; commercially, a quote that expired unanswered did not
win.

Two things follow. Existing lapsed quotes become indistinguishable from those
the client rejected, so the reason is not recoverable after the change. And the
validity window itself is retained — §21 depends on knowing whether supplier
pricing is still valid — so reaching the end of that window now marks the quote
Lost.

### Q490 — Reviewing the handover
**Option 1 confirmed.** Handover includes a **Project Manager review** of what
transfers, as §6 describes, rather than happening in a single action.

This matters more under Q489: handover now creates not just the project but its
whole list of Joinery Items, drawn from the quote. That is too much structure to
generate without a look first.

### Q493 — Where actual costs come from
**Option 1 confirmed.** Actual costs are **derived from work the system already
records** — materials from quantities received against their price, and labour
from completed production stages priced at the stored labour rates. Neither
Accounts nor anyone else re-enters figures, and no accounting integration is
required for §16's cost tracking.

### Q494 — Variations and Production Release
**Option 2 confirmed.** An approved variation does **not** by itself force a new
Production Release. A variation is a commercial record; many change only price
or timing.

This does not weaken §24. That section requires changes made after release to go
through a new controlled release rather than a silent update — the trigger is
the **design change**, not the variation. A variation that alters what gets
built still forces a new release by way of the change it causes.

# JoineryFlow — Software Function Specification

> Companion to `button-reference.html` and `STAFF-GUIDE.md`. Every control id here (e.g. `TRAC-07`) is the same id shown on the matching card in the HTML. Both files are generated from one data file, so they cannot disagree.

> Generated from the code on **2026-10-19** (Alembic head `0077_appliance_fields`, main at `26527b8`). Where this document and CLAUDE.md or Plan V1 disagree, **ask** — see the Questions at the end (CLAUDE.md Rule Zero).

## Contents

- 1. Product overview
- 2. Architecture and conventions
- 3. Roles, modules and permissions
- 4. Core data concepts and invariants
- 5. Locks
- 6. Production lifecycle
- 7. Orders and procurement rules
- 8. Estimating (tender) rules
- 9. Files, search and notifications
- 10. Screen-by-screen function reference (every button)
- 11. REST API catalogue
- 12. Not built / open items
- 13. Questions for you
- 14. Suggestions
- Appendix A. Source index of every button
- Appendix B. Role × control matrix

## 1. Product overview

**JoineryFlow** is a web replacement for a FileMaker-based joinery production system. It is three apps on one database:

| App | Users | Purpose |
| --- | --- | --- |
| Project Information Management | Drafter / PM / CEO | Project → Item → Module → Part + HardwareLine + lifecycle. The drafter is the authoritative data-entry point. |
| Shop Floor Ops | Shop workers, supervisors | Kanban and kiosk keyed on cutlist and production stage; cut planning; QC; packing. |
| Cabinet Vision integration layer | Drafter | Paste/upload CV output, resolve unknown material codes, create modules and parts. |

Plus the commercial side: **Orderbook / Procurement** (orders, PO documents, suppliers, cost centres) and **Estimating** (customers, revisioned quotes, tender lifecycle, convert to project, generate orders).

Information architecture is fixed: **6 primary tabs** — Dashboard · Tracking · List · Shop Dwgs · iSample · Orderbook — plus admin-only `/it`; new top-level surfaces go on the **secondary strip** — Catalog · Shop Floor · Cut Floor · QC · Estimating · Customers.

## 2. Architecture and conventions

- **Browser → Next.js Route Handler (`app/api/[...proxy]/route.ts`) → FastAPI.** The browser never calls FastAPI directly. `proxy.ts` redirects unauthenticated users to `/login`.
- **API:** FastAPI + SQLAlchemy Core (`text()` queries, no ORM) + Pydantic v2. **Web:** Next.js 16 App Router, Tailwind v4, TypeScript. State is raw `fetch()` + URL search params + controlled inputs (no TanStack Query / React Hook Form / Zustand).
- **Auth:** Argon2id passwords, opaque 32-byte tokens (sha256 stored), httpOnly `jf_session` cookie, sliding 14 days with a 30-day hard cap.
- **Audit:** every authenticated mutation writes `audit_log`; item-scoped mutations also write `item_edit_log` in the same transaction.
- **Refusals are `409 {detail:{code,…}}`** with a stable `code` (e.g. `HARD_LOCKED`, `SUPPLIER_MISMATCH`, `REJECTION_NOTE_REQUIRED`). Optimistic concurrency is field-level: PATCH may carry `expected_versions`; a stale field answers `409 FIELD_CONFLICT`.
- **Money and quantities backed by Pydantic `Decimal` arrive as JSON strings** (typed `string` on the web).
- **Workspace isolation everywhere:** every route scopes through `projects.workspace_id` (or the entity’s own `workspace_id`); another workspace’s id answers **404**, identical to a nonexistent id.
- **Tokens/design:** colours only from `globals.css` / `lib/tokens.ts`; Inter for UI, JetBrains Mono for part #, PO #, ETAs, money.

## 3. Roles, modules and permissions

**7 roles:** `admin, manager, editor, drafter, estimator, purchase_officer, viewer`.
**12 modules:** `dashboard, tracking, list, shop_dwgs, isample, orderbook` (the six tabs) + `catalog, cut_floor, shop_floor, estimating, qc` + admin-only `it_management`.
**4 actions:** `read, write, approve, comment`.

- The **live source of truth is the DB engine** (groups + memberships, migration `0037`); the static `MATRIX` is only the fallback for a user with zero memberships. A user with ≥1 membership is fully DB-governed.
- Tabs are hidden when `read` is denied, but the API’s 403 is the real control.
- Per-object rules (drafter-only item writes, uploader ≠ approver, creator-or-manager, 5-minute undo) live in route handlers.
- Drafter is PM-parity on `orderbook` (except `approve`), `shop_dwgs`, `isample`, `catalog`, `cut_floor`.
- `jtbd_role` is display-only; nothing branches on it.
- `/auth/me`, Global Search and comment routes use workspace-wide grants only.


### 3.1 Default module permissions per role

From `apps/api/app/auth/permissions.py` (`MATRIX`), which is also what `seed_system_groups` writes for a new workspace; migrations 0037/0039/0054 mirror it. **An admin can edit the groups on /it, so a live workspace may differ.** R = read, W = write, A = approve, C = comment.

| Module | admin | manager | editor | drafter | estimator | purchase_officer | viewer |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `dashboard` | RWAC | RWAC | RWC | R | R | R | R |
| `tracking` | RWAC | RWAC | RWC | RWAC | RC | RC | R |
| `list` | RWAC | RWAC | RWC | RWAC | RC | R | R |
| `shop_dwgs` | RWAC | RWAC | RWC | RWAC | RC | R | R |
| `isample` | RWAC | RWAC | RWC | RWAC | RC | R | R |
| `orderbook` | RWAC | RWAC | RC | RWC | R | RWAC | R |
| `catalog` | RWAC | RWAC | RWC | RWAC | RC | RC | R |
| `cut_floor` | RWAC | RWAC | RWC | RWAC | R | R | R |
| `shop_floor` | RWAC | RWAC | RWC | RC | R | R | R |
| `estimating` | RWAC | RWAC | R | RC | RWAC | R | R |
| `qc` | RWAC | RWAC | RWC | RC | R | R | R |
| `it_management` | RWAC | R | — | — | — | — | — |

Notes: `viewer` is read-only everywhere except `it_management`; `manager` has only read on `it_management`; `drafter` has no `orderbook:approve` (deciding orders is purchase_officer, manager, admin). Item writes additionally need drafter/manager/admin (`require_drafter`).

## 4. Core data concepts and invariants

| Concept | Rule |
| --- | --- |
| Catalog tables | Nine physical tables: `board_materials`, `hardware_materials`, `custom_made`, `benchtop_materials`, `appliances`, `equipment_hire` (the original six) plus `edging_materials` (`0069`), `glass_materials` (`0070`), `timber_materials` (`0074`). Catalog tabs are product types; Delivery, Supplies, Paint, TG Solid, Laminate and Contractor Manufacturing stay tabs over an existing table. Soft-archive only; hard delete only for `cv_material_mapping`. See Question Q-11: CLAUDE.md still carries a “six tables — never unify” invariant. |
| Number sequences | `joinery_number_seq` (Item IDs, cutlist numbers, related parts) and `po_number_seq` (`PO-{year}-{0000}`); never `MAX+1`; drawing numbers from `workspace_counter`; PO documents from `po_document_no_seq` (next PO is 193971). |
| Stage vs lifecycle | **Stage** = site location (`items.stage`); **Zone** = sub-division of Stage; `lifecycle_stage` / `stage_key` = production milestones `REQ SM LISTED DOWN CNC EDGED PAINTED MADE DEL INST` (+ `PACKING` on Shop Floor). Never use bare “stage” for the milestones. |
| Status | Record state: `CLEAR VOID NOTE! LIVE APPROVED HOLD`. *Status Symbol* is a drafter-only UI flag. |
| Cutlist | Owns the production workflow. Shop Floor keys on `(cutlist_id, stage_key)`; `item_stages` is a per-item projection fanned out on completion; undo reverses the whole cutlist; late-linked items get no backfill; DEL/INST are not Shop Floor stages. |
| Soft delete | `items.deleted`, `cutlist.deleted`. Delete flags item + related parts + (when empty) cutlist; restore is manager/admin; a Hard Lock refuses delete (`409 HARD_LOCKED`); a deleted item answers 404 everywhere except Tracking’s Deleted list. |
| Related parts | `items` rows with `row_type='related_part'` and a parent FK (one level). No cutlist number, thread, take, QC or attachments. |
| Area / Room | Project-scoped tables, Room nested under Area; composite FK `items (area_id, room_id)`. |
| CutPlan ≠ CutSchedule | Two entities. `/optimise` is a pure function (no writes); sheet stock is read, never consumed. |
| Factories | Per-workspace lookup of where work is made (`TG`, `SI`…), `items.factory_id`; `items.tg_solid` is a per-item tag. |
| Material Take | Generated, then person-owned; approved takes are immutable (new version = n+1); boards are fractional sheets per item, rounded up once over the project (Q586). Confirmation of the Material Summary is advisory (Q499). |
| ProjectHardwareCatalog | Project-scoped link layer; item hardware lines reference materials through it (log-only governance, audited). |

## 5. Locks

Three lock types on an item, all checked through `assert_item_content_unlocked` **before** anything is written:

- **Hard** (`hard_locked_at`): manager/admin set it; blocks everyone including the owner.
- **Approval:** derived from `status = 'APPROVED'` (no column).
- **Controlled** (`item_locked` + `cutlist_owner_id`): owner and manager/admin pass; others’ `PATCH /items/{id}` is held as a lock request (`LOCK_REQUEST_CREATED`).

| Write | Hard | Approval | Controlled |
| --- | :-: | :-: | :-: |
| `PATCH /items/{id}` | ✔ | ✔ | request held |
| Modules, parts, CV import commit, module delete | ✔ | ✔ | ✔ refused |
| Hardware lines, attachment slots, Document Register | ✔ | ✔ | ✔ refused |
| `/status`, `/bulk-status` (skips + lists locked), `/lifecycle/{stage}` | ✔ | — | ✔ |
| Answer / edit-answer a query; every material-take write | ✔ | — | ✔ |
| Ask a query | ✔ | — | — |
| `DELETE /items/{id}` | ✔ | — | — |

Deliberately not locked: QC records, comments, Material Summary, project hardware catalog, `POST /files`, Shop Floor fan-out, reads and print routes. On the web, a lock disables the control and shows its reason; a 409 fallback reverts the edit.

## 6. Production lifecycle

1. **Tracking** item created in a project (with cutlist, area, room) → Status `CLEAR`.
2. Drafter builds the **Cutlist tab** (modules/parts, optional CV import) and **Hardware tab**; attachments and the Document Register are filled.
3. **Material Take** generated → approved; project **Material Summary** computed.
4. **Cut Floor** optimises and schedules cutting (planned → running → done).
5. **Shop Floor** assigns workers to the cutlist’s next stage; workers Start / Mark done; stage order enforced; Packing via QR scan.
6. **QC** records defects, checklist and rework alongside.
7. Delivery and installation (DEL / INST) are dates tracked in Tracking; an installed item also gets REQ done.
8. **Close-out** on the project page is the only way to close a project.

## 7. Orders and procurement rules

- `purchase_orders` + `po_line_items` are the order layer (one row per ordered item); `vendors` is the supplier entity. Item cost does not roll up.
- **Order decision:** the software runs no approval process. An order added in the Orderbook starts **Pending** (from a won quote it starts **Draft**). A purchase officer, manager or admin (`orderbook:approve`) sets **Approved** or **Rejected** by hand; **Rejected requires a note** (`REJECTION_NOTE_REQUIRED`). Cancelling (`DELETE /orders/{id}`) needs the same grant (`DECISION_FORBIDDEN`).
- **Priority** has three levels (High / Medium / Low); Next, Hold, Quote are statuses only.
- **Budget follows the order:** an order commits its total against its cost centre while Approved; later changes post the difference (negative *Release*); cancel releases; delivering posts an *Expenditure* and releases. A cost centre is optional; ledger figures are visible to managers/admins only; the budget informs and never blocks.
- **Frozen orders:** `Cancelled` and `Delivered` are read-only except `status`.
- **Orders waiting for a decision** are shown only to `purchase_officer` (bell badge “need attention”); derived from `status='Pending'`, no table.
- **PO documents:** groups open orders of one supplier; marks them ordered; delivery charge is a real ‘Delivery Fee’ order; Invoice Details (GST 10% auto), Authorisation Form (deposit % or amount, not both), Payment Method list.
- **Order pop-up tabs:** HOME, Delivery, Glass C, Timber, Stock, Tracking, Supplier, TGSolid, Cutlists, ADMIN.
- **Delivery queue** shows what is due; the Overdue / This Week dashboard tiles open it with `?eta=`.

## 8. Estimating (tender) rules

- Customers → Estimates → **Revisions** (v1, v2…) → Lines (+ parts, hardware, labour). Costs are snapshotted.
- **12-stage lifecycle**; `advance()` is the only forward action; `locked_at` (set at MGMT_APPROVAL → SUBMITTED) is the frozen gate. Terminal outcomes: Accept, Reject (reason), Withdraw, Expire (optional reason).
- **Convert to project** takes selected lines and creates a `project_contract`; variations are append-only; `current_value` is computed on read.
- **Generate orders from a won quote:** coverage is per (quote line, material) in `estimate_line_material_order`; materials with a live default supplier order now (one draft PO per supplier per run), others stay pending; each may be marked “ordered by hand” with a required note.
- Quote PDF is cached by the hash of the rendered HTML (`quote_pdf_cache`).

## 9. Files, search and notifications

- **Files:** `file_blob` is workspace-scoped, sha256-deduped, never deleted. Allowed: PDF / PNG / JPEG plus `.skp` / `.cvj` (signature and extension must agree); 25 MB cap. A blob has no name of its own.
- **Search:** Meilisearch fed by a trigger-written outbox and a worker. `GET /search` is available to any signed-in user and drops unreadable types silently; 503 on outage. Never index secrets, money, bank/tax fields.
- **Comments / notifications:** threads on project, area, room, item, module and shop-drawing revision; one-level replies; @mentions by id; in-app bell only.

## 10. Screen-by-screen function reference (every button)

Each row: **id · control · kind · what it does · API · who can use it · notes**. “Who” names the permission the route enforces (`module:action`); the DB groups decide who holds it.

### Global chrome (every signed-in page)

*Route:* `(app)/layout.tsx`  
*Purpose:* The shell around every signed-in page: top bar, 6 primary tabs, secondary strip, global search, notification bell, sign-out. Editor mode (/items/[id]) hides the TabStrip and SideBar. The browser never calls FastAPI directly: every request goes through the Next.js proxy (app/api/[...proxy]).

**Top bar**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `CHRO-01` | **JoineryFlow logo / name** | link | Link to /dashboard. | — | — | — |
| `CHRO-02` | **Search box (type-ahead)** | input | Debounced global search across projects, items, orders, suppliers, drawings, samples, customers, estimates. ArrowUp/Down moves the highlight, Enter opens the highlighted hit, Escape closes. A `/` shortcut focuses it when you are not typing in a field. | GET /search | any signed-in user (workspace-wide grants only; unreadable types are dropped silently) | 503 when Meilisearch is down. |
| `CHRO-03` | **Search hit row** | link | Opens the hit (item editor, project, order, drawing…). Shows first code, title, subtitle. | — | — | — |
| `CHRO-04` | **All results for “q” →** | link | Opens /search?q=… with type chips and paging. | — | — | — |
| `CHRO-05` | **🔔 Notification bell** | button | Toggles the dropdown and refreshes it. Badge shows unread count (99+ cap). For the purchase_officer role the badge also counts orders waiting for a decision (labelled “need attention”, not “unread”) and lists them above comment notifications. | GET /notifications?limit=… | any signed-in user; ‘orders waiting’ only for purchase_officer with orderbook read | Polls on a timer; a failed poll keeps the last known state. |
| `CHRO-06` | **Mark all read (bell)** | button | Marks every comment notification read and clears the badge. | POST /notifications/read-all | — | — |
| `CHRO-07` | **Notification row** | button | Marks that notification read, then navigates to the object it points to (comment thread, order…). | POST /notifications/{id}/read | — | — |
| `CHRO-08` | **Sign out** | button | Ends the session (server deletes the session row), then replaces the route with /login?reason=signed_out. | POST /auth/logout | — | — |

**Primary tab strip**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `CHRO-09` | **Dashboard** | tab | Go to /dashboard. | — | module dashboard:read (tab hidden otherwise) | — |
| `CHRO-10` | **Tracking ↗** | tab | Opens /tracking in a NEW browser tab (so two modules can sit on two monitors, Q475/Q545). If you are already on it, navigates in place. | — | tracking:read | — |
| `CHRO-11` | **List ↗** | tab | Opens the Cutlist module (/list) in a new tab. The ‘List’ tab IS the Cutlist module (Q474). | — | list:read | — |
| `CHRO-12` | **Shop Dwgs** | tab | Go to /shop-dwgs. | — | shop_dwgs:read | — |
| `CHRO-13` | **iSample** | tab | Go to /isample. | — | isample:read | — |
| `CHRO-14` | **Orderbook ↗** | tab | Opens /orderbook in a new tab. | — | orderbook:read | — |

**Secondary strip**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `CHRO-15` | **Catalog / Shop Floor / Cut Floor / QC / Estimating / Customers** | tab | Navigation links to /catalog, /shop-floor, /cut-floor, /qc, /estimating, /customers. Customers uses the estimating module’s gate. A tab is hidden when read is denied; the API’s 403 is the real control. If the permissions map is entirely absent the strip fails OPEN (shows tabs) rather than blanking the nav. | — | any signed-in user (a tab shows only when its module’s read is granted) | — |
| `CHRO-16` | **/it (admin only)** | tab | Admin surface link: permission groups, labour rates, staff photos, search health, shop-worker roster. | — | it_management:read (admin only) | — |

**Project sidebar (Dashboard only)**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `CHRO-17` | **FAV / ALL toggle** | tab | Switches the sidebar list between favourite projects and all projects. | — | — | Only shown on Dashboard (HAppChrome.SIDEBAR_ROUTES). |
| `CHRO-18` | **☆ / ★ favourite star** | button | Adds/removes the project from the user’s favourites. | POST\|DELETE /projects/{id}/favourites | any signed-in user | — |

### Login

*Route:* `/login  (public)`  
*Purpose:* Sign-in page with brand panel (live workspace counts from /public/stats).

**Sign-in form**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `LOGI-01` | **Sign in** | button | Submits workspace slug + email + password. On success sets the httpOnly jf_session cookie (sliding 14 days, hard cap 30) and redirects to the requested page or dashboard. Shows ‘Signing in…’ while busy. | POST /auth/login | public | Argon2id password check; wrong credentials give a generic failure. |
| `LOGI-02` | **× (dismiss notice)** | button | Closes the banner shown after ‘signed out’ or ‘session expired’ redirects. | — | — | — |
| `LOGI-03` | **Continue with SSO** | button | Placeholder: the click handler only calls preventDefault. No SSO is wired. | — | — | Kept deliberately: SSO is planned (your decision, 2026-10-19). Remains a no-op until built. |

### Dashboard

*Route:* `/dashboard`  
*Purpose:* Role-personalised landing page: metric tiles, My Day, today’s deliveries, team status card, team activity feed.

**Metric tiles**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `DASH-01` | **Metric tile (each)** | link | A whole-tile link. Tiles differ by role. Examples: Overdue Items, In Optimisation, Awaiting Install, Value in Progress (production); Drafts Open, Awaiting Response, Accepted · Unconverted, Expiring ≤7d (estimating); Overdue Deliveries, This Week, Open POs, Pending approvals (procurement). Overdue/This-Week open the Delivery queue with ?eta=; Open POs opens Orders with ?status=open; Pending approvals opens /orderbook?status=Pending. | GET /home/dashboard | any signed-in user | — |

**My Day / Deliveries / Activity**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `DASH-02` | **My Day row, Delivery row, Activity row** | link | Each row is a link to the underlying item, order or project. | GET /home/dashboard | — | — |

**Team card**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `DASH-03` | **✎ Update status** | button | Opens the work-status editor for the signed-in user. | — | any signed-in user | — |
| `DASH-04` | **Status choices (In / On site / Shop / WFH / Off)** | toggle | Picks one status; the picked one highlights. | — | — | — |
| `DASH-05` | **Clear** | button | Un-picks the status so ‘No status set’ will be saved. | — | — | — |
| `DASH-06` | **Save** | button | Saves your own work_status + free-text location label. Shown to every teammate on the card. | PATCH /users/status | any signed-in user (own row only) | — |
| `DASH-07` | **Cancel** | button | Closes the editor without saving. | — | — | — |

### Projects list

*Route:* `/projects`  
*Purpose:* All projects in the workspace.

**List page**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `PROJ-01` | **+ New project** | button | Opens the right-hand Create Project drawer. | — | tracking:write | — |
| `PROJ-02` | **✕ (drawer)** | button | Closes the drawer and clears the form. | — | — | — |
| `PROJ-03` | **Create** | button | Creates a project from project code, name and optional install start. Shows ‘Creating…’ while pending; errors inline. | POST /projects | signed-in; creation allowed per project routes | — |
| `PROJ-04` | **Cancel (drawer)** | button | Closes the drawer, clears the form and errors. | — | — | — |

### Tracking (item grid)

*Route:* `/tracking?project_id=…`  
*Purpose:* The main production grid for one project: one row per joinery item, with sub-tabs of columns, quick filters, bulk actions and pop-ups. Related parts nest under their parent. Soft-deleted items appear only under the Deleted chip.

**Project info bar**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-01` | **Project name ▾** | button | Opens the project switcher menu. | — | tracking:read | — |
| `TRAC-02` | **★ FAV / ALL (menu)** | tab | Filters the switcher list to favourites or all projects. | — | — | — |
| `TRAC-03` | **Project row (menu)** | link | Switches the grid to that project (router.push /tracking?project_id=…). | — | — | — |
| `TRAC-04` | **★ (favourite)** | button | Toggles this project as favourite; optimistic UI, reverts on failure. | POST\|DELETE /projects/{id}/favourites | — | — |
| `TRAC-05` | **Info** | button | Opens the Project Information pop-up (Project stats / Budget; Cars, OH&S, Scope are disabled placeholders — Q550, Q572). | — | tracking:read | — |
| `TRAC-06` | **🛒 Open Procurement** | button | Opens /projects/{id}/procurement (materials, batches, allocations, material summary). | — | orderbook:read | — |
| `TRAC-07` | **Edit item** | button | Opens the ticked item in the item editor (/items/{id}). Works only with exactly one row ticked; otherwise disabled with the tooltip ‘Tick exactly one row to edit it’. | — | list:read | Hidden/disabled in the Deleted view. |
| `TRAC-08` | **+ New item** | button | Opens the New Item dialog. | — | tracking:write | — |

**Quick-filter chips**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-09` | **My Entries** | chip | Shows only rows created by you. | — | — | Disabled until the user is loaded. |
| `TRAC-10` | **Deleted** | chip | Switches to the soft-deleted list (?deleted=1), read-only with Restore. | GET /projects/{pid}/items?deleted=true | — | — |
| `TRAC-11` | **Void** | chip | Shows items whose Status is VOID. | — | — | — |
| `TRAC-12` | **Tg Solid** | chip | Shows items tagged Tg Solid (items.tg_solid, separate from solid_surface_req). | — | — | — |
| `TRAC-13` | **Orders** | chip | Shows items with an order, or whose related parts have one. | — | — | — |
| `TRAC-14` | **Overdue** | chip | Shows items with a lifecycle due date passed and not done (red tone). | — | — | — |
| `TRAC-15` | **Installed** | chip | Shows items whose INST stage is done (green tone). | — | — | — |

**Grid toolbar and selection bar**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-16` | **↻ (refresh)** | button | router.refresh(): re-reads the grid from the server. | GET /projects/{pid}/items | — | — |
| `TRAC-17` | **Show / Hide (row count)** | toggle | Toggles the row-count readout. | — | — | — |
| `TRAC-18` | **Apply status…** | button | Opens the Bulk Status dialog for the ticked rows (up to 500). | — | tracking:write | Appears only with a selection. |
| `TRAC-19` | **Delete (selection)** | button | Confirms, then soft-deletes every ticked item plus related parts and (when empty) cutlist. A Hard Lock refuses (HARD_LOCKED) and is reported. | DELETE /items/{id} (per item) | tracking:write | — |
| `TRAC-20` | **Restore (selection)** | button | In the Deleted view: restores ticked items with their related parts and cutlist. | POST /items/{id}/restore | manager / admin only | — |
| `TRAC-21` | **Clear selection** | button | Un-ticks all rows. | — | — | — |

**Sub-tabs of the grid**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-22` | **DATE · TO BE ORDERED · iTIME · HARDWARE · SITE MEASURE · INVOICE · QC · O/BOOK** | tab | Eight sub-tabs. DATE shows the ten lifecycle stages (REQ SM LISTED DOWN CNC EDGED PAINTED MADE DEL INST) with due/done dates; each other tab swaps in its own column set. TO BE ORDERED and O/BOOK show order data for the row. | — | — | — |
| `TRAC-23` | **+ Create Order** | button | Opens the Create Order dialog for the selected row (prefills project / location / cutlist no. from the item). | — | orderbook:write | Shown on order-related sub-tabs. |
| `TRAC-24` | **Clear (filters)** | button | Resets column filters and sort (back to ‘num’ ascending). | — | — | — |
| `TRAC-25` | **Column headers (Th)** | link | Click to sort; filter dropdowns under headers narrow the rows. | — | — | — |

**Row controls**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-26` | **▶ (open)** | button | Opens the Item Detail modal for the row (read-mostly summary; editing stays in the item editor). | — | tracking:read | — |
| `TRAC-27` | **▶ / ▼ (related parts)** | button | Expands / collapses the related-part rows under a parent. | — | — | — |
| `TRAC-28` | **Status pill** | button | Opens the Status pop-up for that row. | — | tracking:write | — |
| `TRAC-29` | **Open item availability** | button | Opens the Availability drawer: per-item ‘is this blocked on a material?’ (procurement batch → allocation → hardware line). | GET /items/{id}/availability | list:read | — |

**Status pop-up**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-30` | **Status choices** | toggle | Select the new Status (CLEAR VOID NOTE! LIVE APPROVED HOLD). A note is required. | — | — | A Hard or Controlled lock disables this and shows the reason; APPROVED does not block status changes. |
| `TRAC-31` | **⚠ Update Status To All** | button | Disabled placeholder (tooltip: ‘Bulk update not yet wired’). Use ‘Apply status…’ on the grid instead. | — | — | Kept deliberately as a planned control (decision 2026-10-19). Disabled with the tooltip ‘Bulk update not yet wired’. When built it applies to every item in the project, shows ‘This will change N items’, requires the note, and skips and lists locked items like bulk status. |
| `TRAC-32` | **↻ Update Current Item** | button | Saves the status + note on this one item and writes audit_log + item_edit_log. | PATCH /items/{id}/status | tracking:write | — |
| `TRAC-33` | **Close** | button | Closes the pop-up. | — | — | — |

**Bulk Status dialog**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-34` | **Apply <STATUS>** | button | Applies one status with a required shared note to all ticked items in one transaction. Reply lists updated / not found / skipped-because-locked; the grid shows a banner. | POST /items/bulk-status | tracking:write | Max 500 items; locked items are skipped and listed. |
| `TRAC-35` | **Cancel** | button | Closes without changes. | — | — | — |

**New Item dialog**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-36` | **Create and open** | button | Creates an item (and its cutlist, area, room per the seed rules) in the project, then opens the item editor. | POST /projects/{pid}/items | tracking:write (drafter-gated in the editor) | — |
| `TRAC-37` | **Cancel** | button | Closes. | — | — | — |

**Item Detail modal**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-38` | **✕ / CLOSE** | button | Closes the modal. | — | — | — |
| `TRAC-39` | **Modal tabs (register / slots / reference fields)** | tab | Read-only views of Document Register, five attachment slots and reference fields. Editing is done in the item editor. | — | — | — |
| `TRAC-40` | **‹ Previous / Next ›** | button | Moves to the previous/next row of the grid without closing the modal. | — | — | Disabled at the ends. |

**Create Order dialog (Tracking)**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-41` | **+ Add field** | button | Adds a key/value row for the order’s free-form attributes (Acoustic, Benchtop use attributes). | — | — | — |
| `TRAC-42` | **Create order** | button | Creates an order for supplier, description, category, qty… linked to the item/project. | POST /orders | orderbook:write | — |
| `TRAC-43` | **Close / Cancel** | button | Closes the dialog. | — | — | — |

**Project Information pop-up**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `TRAC-44` | **Project stats / Budget tabs** | tab | Stats shows counts; Budget shows material cost by order type with labour-hours tables blank (Q571). | GET /projects/{id}/budget | Budget: manager and admin only (403 BUDGET_FORBIDDEN) | — |
| `TRAC-45` | **Cars / OH&S / Scope tabs** | tab | Disabled placeholders (blocked on Q550 / Q572). | — | — | — |
| `TRAC-46` | **Close** | button | Closes the pop-up. | — | — | — |

### Item editor

*Route:* `/items/[id]?tab=…`  
*Purpose:* Full editor for one item. Opens in its own window; hides the TabStrip and SideBar. Every write passes the lock checks (Hard, Approval, Controlled) before anything is written.

**Header and locks**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-01` | **Delete** | button | Confirms, then soft-deletes the item (related parts and empty cutlist go with it) and returns to Tracking. 409 HARD_LOCKED is shown as a message. | DELETE /items/{id} | tracking:write | Manager/admin can restore from Tracking’s Deleted chip. |
| `ITEM-02` | **✕ (close editor)** | button | window.close(); if the browser blocks that, falls back to /dashboard. | — | — | — |
| `ITEM-03` | **Hard-lock / Unlock (banner)** | button | Hard Lock blocks every edit for everyone including the owner. Shown only to those who can manage it, or whenever locked. | POST\|DELETE /items/{id}/hard-lock | manager / admin | — |
| `ITEM-04` | **Lock / Unlock (footer)** | button | Takes or releases the Controlled Lock (owner + manager/admin may pass; others’ edits become held lock requests). cutlist_owner_id is sticky. | POST\|DELETE /items/{id}/lock | tracking:write | — |
| `ITEM-05` | **(no button) Lock requests** | link | The API can hold an edit made under someone else’s Controlled Lock as a lock request and has approve/reject routes, but NO web button calls them today. | GET /items/{id}/lock-requests · POST /lock-requests/{id}/approve\|reject | owner / manager / admin | DECIDED: build a banner with Approve/Reject on the item editor plus a bell notification (not built yet). |

**Editor tabs**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-06` | **Cutlist · Hardware · Board · Material Take · Attachments · Actions · Query · Comments · QC · Log** | tab | Ten tabs; selection is kept in ?tab=. | — | — | — |

**Cutlist tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-07` | **Import from CV** | button | Opens the Cabinet Vision import wizard (?import=cv). | — | cut_floor:write + not locked | — |
| `ITEM-08` | **+ Add module** | button | Creates ‘New module’ numbered by position and selects it. | POST /items/{id}/modules | drafter / manager / admin | — |
| `ITEM-09` | **Module (tree item)** | link | Selects a module and loads its parts grid. | — | — | — |
| `ITEM-10` | **Delete module** | button | Opens the delete dialog (shows impact: parts and comments deleted). | GET /modules/{id}/delete-impact | — | — |
| `ITEM-11` | **Delete module (confirm)** | button | Deletes the module and its parts. | DELETE /modules/{id} | drafter+ | Refused under Hard/Approval/Controlled lock. |
| `ITEM-12` | **+ Add row** | button | Adds an empty part (qty 1) to the module; rows edit in place. | POST /modules/{id}/parts | — | — |
| `ITEM-13` | **– (delete part)** | button | Removes the part; optimistic, reverts on failure. | DELETE /parts/{id} | — | — |

**CV import wizard**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-14` | **Preview** | button | Uploads a file or pasted CSV text and parses it; produces unknown-code list. | POST /items/{id}/cv-imports/preview | cut_floor:write | — |
| `ITEM-15` | **Use existing / Create new / Skip (per unknown code)** | toggle | Resolution for each CV code the resolver can’t find (order: mapping → synonyms → SKU → unknown). | — | — | — |
| `ITEM-16` | **Continue / Back** | button | Moves between Upload → Resolve → Confirm phases. | — | — | — |
| `ITEM-17` | **Import** | button | Commits the run. If the item already has an import this 409s unless ‘replace’ is ticked, which first warns how many modules/comments will be deleted. | POST /items/{id}/cv-imports/{run}/commit | cut_floor:write | — |
| `ITEM-18` | **Cancel / Close** | button | Closes the wizard. | — | — | — |

**Hardware tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-19` | **+ (Pantry row)** | button | Adds the project-catalog item to this item’s hardware lines at qty 1. | POST /items/{id}/hardware_lines | drafter+ | — |
| `ITEM-20` | **+ Add from global** | button | Opens the global-source modal (six catalog tables) to put a material into the PROJECT hardware catalog. | GET /source_catalog/{table} | — | — |
| `ITEM-21` | **Table tabs (modal)** | tab | Switches between the catalog tables. | — | — | — |
| `ITEM-22` | **Add (modal row)** | button | Adds the row to the project hardware catalog (log-only governance; audited). | POST /projects/{pid}/hardware_catalog | — | — |
| `ITEM-23` | **− / + (cart qty)** | button | Changes qty by 1 (min 1); debounced save 300 ms, reverts on error. | PATCH /hardware_lines/{id} | — | — |
| `ITEM-24` | **– (cart delete)** | button | Removes the hardware line. | DELETE /hardware_lines/{id} | — | — |
| `ITEM-25` | **✕ (modal)** | button | Closes the modal. | — | — | — |

**Material Take tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-26` | **Generate material take / Start v(n+1)** | button | Generates a take from parts + hardware (draft). If an approved one exists starts the next version. | POST /items/{id}/material-take/generate | drafter+ | — |
| `ITEM-27` | **Regenerate** | button | Re-runs generation over the draft. | POST /material-takes/{id}/regenerate | — | — |
| `ITEM-28` | **Add line / Remove** | button | Hand-edits take lines (generated first, then person-owned). | POST /material-takes/{id}/lines · DELETE …/lines/{lid} | — | — |
| `ITEM-29` | **Approve** | button | Approves the draft; approved takes are immutable. | POST /material-takes/{id}/approve | list approve-capable roles | — |
| `ITEM-30` | **No impact / Partial impact / Full impact** | button | Records the review outcome of an approved take after a design change. Partial and Full are disabled while a draft exists. | POST /material-takes/{id}/reviews | — | — |

**Attachments tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-31` | **Upload / Replace (slot card)** | button | Uploads a file and binds it to one of five slots (cv_drawing, sketchup, cabvision, floor_plan, site_measure). One format per slot; 25 MB cap; signature AND extension must agree. | POST /files then POST /items/{id}/attachments/{kind} | list:write | — |
| `ITEM-32` | **Delete (slot card)** | button | Confirms and clears the slot (logged). | DELETE /items/{id}/attachments/{kind} | — | — |
| `ITEM-33` | **Add document (Register)** | button | Adds a document to the Document Register. | POST /items/{id}/documents | — | — |
| `ITEM-34` | **↑ / ↓ (register)** | button | Reorders by renumbering sort_order 0..n-1. | PATCH /documents/{id} | — | — |
| `ITEM-35` | **Remove (register)** | button | Confirms; unbinds the document (logged). | DELETE /documents/{id} | — | — |

**Actions tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-36` | **Set status** | button | Opens the Status dialog for this item. | PATCH /items/{id}/status | — | — |
| `ITEM-37` | **Mark REQ done today** | button | Sets the REQ lifecycle stage’s done_date to today. Disabled when already done. | PATCH /items/{id}/lifecycle/{stage_key} | — | — |
| `ITEM-38` | **Duplicate item** | button | Opens the Duplicate dialog. | — | tracking:write | — |
| `ITEM-39` | **Duplicate (confirm)** | button | Same-project copy with its own new cutlist, status reset to CLEAR, QC checklist unticked; links to source via duplicated_from_item_id. | POST /items/{id}/duplicate | tracking:write | — |
| `ITEM-40` | **Duplicated from #n** | link | Link to the source item. | — | — | — |
| `ITEM-41` | **Jump to Orderbook** | link | Opens /orderbook?project=… for this item’s project. | — | — | — |

**Query tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-42` | **Ask** | button | Raises a question on the item (only needs list:read). Refused under a Hard Lock. | POST /items/{id}/queries | list:read | — |
| `ITEM-43` | **Answer / Save / Edit answer** | button | Answers or edits the answer. Refused under Hard or Controlled lock. | POST\|PATCH /queries/{id}/answer | list:write (drafter+) | — |

**QC tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-44` | **Raise (defect)** | button | Raises a defect on the item. | POST /items/{id}/qc/defects | qc:write | — |
| `ITEM-45` | **Mark resolved** | button | Resolves a defect. | POST /qc/defects/{id}/resolve | qc:approve | — |
| `ITEM-46` | **Add / × (checklist)** | button | Adds or removes a checklist line. | POST /items/{id}/qc/checklist · DELETE /qc/checklist/{id} | qc:write | — |
| `ITEM-47` | **+ Log rework / Log / Cancel** | button | Logs a rework (internal or full; never reopens a stage). | POST /items/{id}/qc/rework | qc:write | — |
| `ITEM-48` | **Close (rework)** | button | Closes a rework. | POST /qc/rework/{id}/close | qc:approve | — |

**Comments tab**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-49` | **Comment** | button | Posts a comment with @mentions (by id). | POST /comments | any signed-in user with the module grant | — |
| `ITEM-50` | **Reply / Edit / Delete / Save / Cancel** | button | One-level replies; author edits; creator-or-manager deletes (5-min undo rule lives in handlers). | POST\|PATCH\|DELETE /comments | — | — |

**Label page**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ITEM-51` | **Print label** | button | window.print() for the item QR label (/items/[id]/label). | — | — | — |

### Project page and Procurement workbench

*Route:* `/projects/[id] · /projects/[id]/procurement`  
*Purpose:* Project detail 2.0 (contacts, lift access, contract/variations, areas & rooms with comment counts) and the Procurement workbench (materials, batches, allocations, Material Summary).

**Project header and cards**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `PROJ-01` | **Close out** | button | Confirms, then closes the project (the only way to close; PATCH to Current/Hold reopens). | POST /projects/{id}/close-out | admin / manager | 409 → ‘Already closed’. |
| `PROJ-02` | **+ Add contact / Add / Cancel / Remove** | button | Manage project contacts. | POST\|DELETE /projects/{pid}/contacts · /contacts/{id} | tracking:write | — |
| `PROJ-03` | **Upload sketch / Replace / Remove** | button | Lift & Access sketch file (PNG/JPEG/PDF) and notes. | PUT\|DELETE /projects/{pid}/lift-access | tracking:write | — |
| `PROJ-04` | **+ Add variation / Add / Cancel** | button | Appends a contract variation (append-only; current value is computed on read). | POST /projects/{pid}/contract/variations | tracking:write | — |
| `PROJ-05` | **Area row / Room row** | link | Selects the area/room and shows its comment thread; deep-linkable (?area= / ?room=). | GET /projects/{pid}/areas · comment-counts | — | — |

**Procurement workbench**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `PROJ-06` | **Material-type headers (n item(s) ▾)** | toggle | Collapses/expands each of six material groups. | — | — | — |
| `PROJ-07` | **+ New batch / Save / Cancel batch** | button | Creates or edits a procurement batch (drawer). Cancel batch is refused while allocations exist. | POST /batches · PATCH\|DELETE /batches/{id} | orderbook:write | — |
| `PROJ-08` | **+ Allocate / remove** | button | Allocates qty from a batch to an item hardware line; over-commit is 409; removes an allocation. | POST /batches/{id}/allocations · DELETE /allocations/{id} | orderbook:write | — |
| `PROJ-09` | **Catalog tabs / + Add** | button | Quick-add a catalog row of the chosen type. | POST /catalog/{slug} | catalog:write | — |
| `PROJ-10` | **Build summary / Rebuild from approved takes** | button | Computes the project Material Summary (boards: fractional sheets per item, rounded up once, Q586). | POST /projects/{pid}/material-summary | list:write | — |
| `PROJ-11` | **Confirm (summary)** | button | Records PM confirmation — advisory only (Q499), blocks nothing. | POST /material-summaries/{id}/confirm | list:approve | — |
| `PROJ-12` | **▸ / ▾ line** | toggle | Expands a summary line’s breakdown. | — | — | — |
| `PROJ-13` | **✕ (batch drawer)** | button | Closes the drawer. | — | — | — |

### List (Cutlist module)

*Route:* `/list`  
*Purpose:* First-class Cutlist entity. The cutlist owns the production workflow (Shop Floor keys on (cutlist_id, stage_key)). Three panes: Items · Parts · Hardware.

**Cutlist list and detail**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `LIST-01` | **+ New cutlist** | button | Prompts for an optional name, then creates a cutlist; the number is allocated by the server from joinery_number_seq (never typed). | POST /projects/{pid}/cutlists | list:write | — |
| `LIST-02` | **Rename** | button | Prompt; sends expected_versions so a race is a named FIELD_CONFLICT, not an overwrite. | PATCH /cutlists/{id} | list:write | — |
| `LIST-03` | **Delete** | button | Confirms; refused while items are linked (HAS_ITEMS). | DELETE /cutlists/{id} | list:write | — |
| `LIST-04` | **Close** | button | Closes the detail panel. | — | — | — |
| `LIST-05` | **Items / Parts / Hardware** | tab | Switches the pane. | — | — | — |
| `LIST-06` | **Link** | button | Links an item to the cutlist (picker). | POST /cutlists/{id}/items | list:write | — |
| `LIST-07` | **Unlink** | button | Removes the item from the cutlist. | DELETE /cutlists/{id}/items/{iid} | list:write | — |

### Shop Dwgs

*Route:* `/shop-dwgs`  
*Purpose:* Shop drawing register, details panel and full-screen viewer. Revision flow draft → pending → approved|rejected; approver ≠ uploader; queues are derived from the latest revision.

**Register**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `SHOP-01` | **Upload drawing** | button | Opens the upload dialog. | — | shop_dwgs:write | — |
| `SHOP-02` | **Create drawing (dialog)** | button | Uploads the file, then creates the drawing (title, room, type, level, optional submit-immediately). drawing_no from workspace_counter. | POST /files · POST /projects/{pid}/shop-drawings | shop_dwgs:write | — |
| `SHOP-03` | **Queue buttons (Being drawn, Internal review… with counts)** | chip | Filter the register by derived queue; counts shown. | — | — | — |
| `SHOP-04` | **My drawings on/off** | toggle | Limits to drawings you uploaded. | — | — | — |
| `SHOP-05` | **All (n)** | chip | Clears the queue filter. | — | — | — |
| `SHOP-06` | **Column headers** | link | Sort asc/desc with ↑ ↓ indicator. | — | — | — |
| `SHOP-07` | **‹ ›** | button | Previous / next page. | — | — | — |
| `SHOP-08` | **View (row)** | button | Opens the full-screen viewer without selecting the row. | GET /files/{id} | shop_dwgs:read | — |

**Details panel**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `SHOP-09` | **✕** | button | Closes the panel. | — | — | — |
| `SHOP-10` | **Revisions / Notes / Attachments / Status History / Audit Log** | tab | Panel sub-tabs. | — | — | — |
| `SHOP-11` | **Comments on v# ▾** | toggle | Collapses the revision’s comment thread. | — | — | — |
| `SHOP-12` | **Revision row / View** | link | Selects a revision / opens it in the viewer. | — | — | — |
| `SHOP-13` | **Submit for review** | button | draft → pending. | POST /shop-drawings/{id}/revisions/{rid}/submit | shop_dwgs:write | — |
| `SHOP-14` | **Withdraw** | button | pending → draft. | POST …/withdraw | shop_dwgs:write | — |
| `SHOP-15` | **Approve** | button | pending → approved. Refused for the uploader. | POST …/approve | shop_dwgs:approve | — |
| `SHOP-16` | **Reject / Confirm reject / Cancel** | button | Reject needs a note. | POST …/reject | shop_dwgs:approve | — |
| `SHOP-17` | **Upload new revision / Add revision** | button | Uploads a PDF/image and adds the next revision. | POST /shop-drawings/{id}/revisions | shop_dwgs:write | — |
| `SHOP-18` | **Archive drawing** | button | Confirms and moves it to the Archive. | POST /shop-drawings/{id}/archive | shop_dwgs:approve | — |

**Viewer**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `SHOP-19` | **← Back** | button | Closes the viewer. | — | — | — |
| `SHOP-20` | **− / + / Fit** | button | Zoom out/in through preset steps; Fit resets to fit-to-width. | — | — | — |
| `SHOP-21` | **Revision rows** | link | Switches the displayed revision (Latest / Viewing chips). | — | — | — |
| `SHOP-22` | **Thumbnail** | link | Jumps to that PDF page. | — | — | — |

### iSample

*Route:* `/isample`  
*Purpose:* Sample wall: pending → approved|rejected; reject needs a note; reviewer ≠ creator; approval ledger = filtered audit_log.

**Board, Ledger, Archive**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ISAM-01` | **Board / Approval ledger / Archive** | tab | Sub-tabs (with count badges). | — | — | — |
| `ISAM-02` | **+ New sample / Create sample / Cancel** | button | Creates a sample (project, title, room, hex swatch, supplier, optional photo). | POST /projects/{pid}/samples | isample:write | — |
| `ISAM-03` | **Status filter chips** | chip | Pending / Approved / Rejected with counts. | — | — | — |
| `ISAM-04` | **Sample card** | link | Opens the drawer for that sample. | — | — | — |
| `ISAM-05` | **✕ (drawer)** | button | Closes the drawer. | — | — | — |
| `ISAM-06` | **Approve** | button | Approves a pending sample (reviewer ≠ creator). | POST /samples/{id}/approve | isample:approve | — |
| `ISAM-07` | **Reject / Confirm reject / Cancel** | button | Rejects with required note. | POST /samples/{id}/reject | isample:approve | — |
| `ISAM-08` | **Edit / Save / Cancel** | button | Edits title, room, hex swatch, supplier. | PATCH /samples/{id} | isample:write | — |
| `ISAM-09` | **Upload photo / Replace photo / Upload** | button | Adds PNG/JPEG photo. | POST /samples/{id}/photo | isample:write | — |
| `ISAM-10` | **Clear photo** | button | Removes the photo. | DELETE /samples/{id}/photo | isample:write | — |
| `ISAM-11` | **Archive** | button | Confirms; archives the sample. | POST /samples/{id}/archive | isample:write | — |
| `ISAM-12` | **Ledger entry / Previous / Next** | link | Opens the sample from a ledger row; pages the ledger. | GET /projects/{pid}/samples/ledger | isample:read | — |

### Orderbook

*Route:* `/orderbook`  
*Purpose:* Orders list grouped by order type, Delivery queue, Cost-centre breakdown, Supplier list, PO documents. The software runs NO approval process: a purchase officer, manager or admin sets Approved/Rejected by hand.

**Tabs and toolbar**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ORDE-01` | **Orders / Delivery queue** | tab | Switches the two Orderbook tabs. | — | orderbook:read | — |
| `ORDE-02` | **Cost centre** | button | Opens the cost-by-material-type breakdown pop-up (every order but Cancelled/Rejected). | GET /orders/cost-breakdown | orderbook:read | — |
| `ORDE-03` | **Edit / Done (cost centres)** | button | Toggles the cost-centre manager. | GET\|POST\|PATCH /cost-centers | purchase_officer / admin | — |
| `ORDE-04` | **Add / Save / Cancel (cost centre)** | button | Creates a cost centre (code + name). | POST /cost-centers | purchase_officer / admin | No delete; an inactive one stays on orders that have it. |
| `ORDE-05` | **Save / Deactivate / Reactivate (row)** | button | Renames or switches a cost centre off/on. | PATCH /cost-centers/{id} | purchase_officer / admin | — |
| `ORDE-06` | **RTO** | chip | Client-side filter: Approved and not yet ordered. | — | — | — |
| `ORDE-07` | **TBO** | chip | Filter: open and not yet ordered. | — | — | — |
| `ORDE-08` | **Due / Over Due / Arrived / My Orders** | chip | Filters: due within 7 days; past due; arrived; requested by you. | — | — | — |
| `ORDE-09` | **Clear** | button | Clears the view filter and the selected order. | — | — | — |
| `ORDE-10` | **New** | button | Opens New Order as a form. | — | orderbook:write | — |
| `ORDE-11` | **Create order** | button | Saves a Pending order (project optional). | POST /orders | orderbook:write | Needs a supplier and a description. |
| `ORDE-12` | **Supplier** | button | Opens the supplier list (edit and add). | GET /suppliers | orderbook:read | — |
| `ORDE-13` | **Po (n)** | button | Puts the ticked orders on one PO document. Same supplier only (SUPPLIER_MISMATCH), open orders only (ORDER_NOT_OPEN), not already on a PO (ORDER_ALREADY_ON_PO). | POST /purchase-orders | orderbook:write | — |
| `ORDE-14` | **Clear selection (n)** | button | Un-ticks rows / closes the pop-up. | — | — | — |
| `ORDE-15` | **PO link in a row** | link | Opens the PO document the order is on. | — | — | — |

**Order pop-up (ten tabs)**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ORDE-16` | **Close** | button | Closes the pop-up. | — | — | — |
| `ORDE-17` | **Reject order / Cancel** | button | Rejected needs a rejection_note. | PATCH /orders/{id} | orderbook:approve (purchase_officer / manager / admin) | 409 REJECTION_NOTE_REQUIRED. |
| `ORDE-18` | **Cancel order / Keep order** | button | Cancels (asks a reason; stamps cancelled_at/by, releases commitments). Keep order aborts. | DELETE /orders/{id}?reason= | orderbook:approve | 403 DECISION_FORBIDDEN otherwise; second cancel is 409. |
| `ORDE-19` | **Open PO n / Create PO!** | button | Opens the PO for this order, or creates one. | POST /purchase-orders | orderbook:write | — |
| `ORDE-20` | **HOME · Delivery · Glass C · Timber · Stock · Tracking · Supplier · TGSolid · Cutlists · ADMIN** | tab | Pop-up tabs. | — | — | — |
| `ORDE-21` | **+ Add line / × (line)** | button | Adds or removes an order line. | POST /orders/{id}/lines · DELETE …/lines/{lid} | orderbook:write | Cancelled/Delivered orders are read-only except status. |
| `ORDE-22` | **− (attachment) / FILE / PDF upload** | button | Add or remove files; PDF box accepts PDF only. | POST\|DELETE /orders/{id}/attachments | orderbook:write | — |
| `ORDE-23` | **remove (product image)** | button | Removes the single PNG/JPEG product image. | DELETE /orders/{id}/image | orderbook:write | — |
| `ORDE-24` | **Catalog item block (HOME, read-only)** | link | Shows the catalog row(s) whose SKU equals the order’s product code, across all nine catalog tables: type, UM, website (http/https only), the type’s own fields, and the picture. Nothing is stored on the order; it re-reads when the product code is edited. Equipment Hire matches only the order’s own project. | GET /orders/{id}/catalog-item · GET …/catalog-item/image?n= | orderbook:read | No money, notes or supplier columns are shown. |

**Order-pop-up tabs**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ORDE-25` | **+ Add / − / × (Delivery)** | button | Adds a delivery received (qty, date, signed by, notes, docket) or removes it/the docket. The log never changes the order status. | POST\|DELETE /orders/{id}/deliveries | orderbook:write | — |
| `ORDE-26` | **Clear All / ▸ Copy Size (Glass C)** | button | Clears the calculator; Copy Size reads ‘1471 x 1000 x 6’ from the start of the description. | PUT /orders/{id}/glass-calc | orderbook:write | — |
| `ORDE-27` | **Edit price list / Done / Switch on\|off / Add (Glass C)** | button | Maintains the per-workspace glass rate list. | POST\|PATCH /glass-rates | purchase_officer / admin | — |
| `ORDE-28` | **CLEAR / CREATE (Timber)** | button | CLEAR saves empty fields; CREATE saves then renders and keeps the Timberwood Panels pressing-form PDF. | PUT /orders/{id}/timber · POST …/timber/form | orderbook:write | — |
| `ORDE-29` | **+ Add / − (TGSolid)** | button | Adds/removes production rows (a record only). | POST\|DELETE /orders/{id}/tg-runs | orderbook:write | — |

**Supplier list**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ORDE-30` | **Add supplier / Edit / Save / Cancel / Close** | button | Supplier company cards. | POST\|PATCH /suppliers | orderbook:write | — |
| `ORDE-31` | **Remove (logo)** | button | Removes the logo. | DELETE /suppliers/{id}/logo | orderbook:write | — |
| `ORDE-32` | **+ Contact / Edit / − / Save contact / Cancel** | button | Manage supplier contacts. | POST\|PATCH\|DELETE /suppliers/{id}/contacts | orderbook:write | — |

**PO document window**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ORDE-33` | **Close / Done** | button | Closes the PO window (saves pending edits first). | — | — | — |
| `ORDE-34` | **Add Delivery / Update Delivery / Remove** | button | The delivery charge is a real ‘Delivery Fee’ order on the PO. | PUT\|DELETE /purchase-orders/{id}/delivery | orderbook:write | — |
| `ORDE-35` | **○ / ✓ (Invoiced)** | toggle | Opens the Invoice Details window for that line. | — | — | — |
| `ORDE-36` | **− (line)** | button | Takes an order off the PO (restores date only if the PO set it). | DELETE /purchase-orders/{id}/orders/{oid} | orderbook:write | — |
| `ORDE-37` | **Add from TBO** | button | Lists the supplier’s open orders to add. | GET /orders?supplier=…&status=open | — | — |
| `ORDE-38` | **Add (TBO row)** | button | Adds that order to the PO. | POST /purchase-orders/{id}/orders | orderbook:write | — |
| `ORDE-39` | **+ Contact / Add contact / Cancel** | button | Adds a supplier contact from the PO. | POST /suppliers/{vid}/contacts | — | — |
| `ORDE-40` | **Print** | button | PDF / Excel export. | GET /purchase-orders/{id}/pdf\|excel | orderbook:read | — |
| `ORDE-41` | **Authorisation Form** | button | Opens the Authorisation window. | — | orderbook:write | — |
| `ORDE-42` | **Cancel PO** | button | Frees the orders and cancels the Delivery Fee order. Refused while invoices exist (PO_HAS_INVOICES). | POST /purchase-orders/{id}/cancel | orderbook:write | — |
| `ORDE-43` | **Email Details** | link | A mailto: link; the PDF must be attached by the user. Ticked staff become cc. | GET /purchase-orders/staff | orderbook:read | — |

**Invoice window and Authorisation window**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ORDE-44` | **‹ / ›** | button | Previous/next invoice on the line (commits first). | — | — | — |
| `ORDE-45` | **+ Add (invoice)** | button | Starts a new invoice on the line. | POST /purchase-orders/{id}/invoices | orderbook:write | — |
| `ORDE-46` | **↻ (Total Ex)** | button | Total Ex = qty × the line’s unit cost. | — | — | — |
| `ORDE-47` | **✓ / ○ (GST auto)** | toggle | While on, GST is 10% of Ex (server-computed). Off = typed figure. Inc = Ex + GST. | — | — | — |
| `ORDE-48` | **remove (file) / Delete / Close** | button | Remove Delivery/Invoice/Non-Delivery file, delete the invoice, or close. | DELETE …/invoices/{id}(/files/{slot}) | orderbook:write | — |
| `ORDE-49` | **Create Form (Authorisation)** | button | Renders and keeps the authorisation PDF from the saved details. Deposit % or amount, not both (DEPOSIT_BOTH). | POST …/authorisation/form | orderbook:write | — |
| `ORDE-50` | **remove (Signed Form) / Close** | button | Removes the hand-signed scan / closes. | DELETE /purchase-orders/{id}/authorisation/signed | orderbook:write | — |
| `ORDE-51` | **Edit list / Switch on\|off / Add (payment method)** | button | Maintains the per-workspace Payment Method list. | POST\|PATCH /payment-methods | purchase_officer / admin | — |
| `ORDE-52` | **Open (Invoice Details table)** | link | Opens the invoice in the window. | — | — | — |

### Catalog

*Route:* `/catalog`  
*Purpose:* Catalog tabs are product types (Edging, Glass, Solid Timber, Hardware, Board, Laminate, Paint, TG Solid, Supplies, Delivery, Contractor Manufacturing…). Rows live in nine physical tables: board_materials, hardware_materials, custom_made, benchtop_materials, appliances, equipment_hire, edging_materials, glass_materials, timber_materials. Types without their own fields (Delivery, Supplies, Paint, TG Solid, Laminate, Contractor Manufacturing) stay tabs over an existing table. Plus CV mappings and board stock.

**Catalog page**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `CATA-01` | **Product-type tabs (name (count))** | tab | One tab per product type in use, with its row count; picks which rows the grid shows (type tabs come from product_type). | GET /catalog/product-types · GET /catalog/by-type | catalog:read | — |
| `CATA-02` | **No type (n)** | tab | Shows rows with no product type; only present when there are some. | GET /catalog/by-type | catalog:read | — |
| `CATA-03` | **Sheet Stock / CV Mappings** | tab | Switch to the board stock panel or the CV code mappings. | — | catalog:read | — |
| `CATA-04` | **+ New / Create / Cancel** | button | Creates a catalog row of the active type (hire needs a project; each type has its own fields). | POST /catalog/{slug} | catalog:write | — |
| `CATA-05` | **Bulk import / Import n rows / Done** | button | All-or-nothing: every row validated first; supplier matched by exact name. | POST /catalog/{slug}/bulk | catalog:write | — |
| `CATA-06` | **Archive (row)** | button | Soft-archives the row (no hard delete). | POST /catalog/{slug}/{mid}/archive | catalog:write | — |
| `CATA-07` | **Cells (inline edit)** | input | Click-to-edit description, sku, supplier, lead time, unit cost and the type’s own fields (board sizes, UM, website…). | PATCH /catalog/{slug}/{mid} | catalog:write | — |
| `CATA-08` | **Product image: upload / remove** | button | One PNG/JPEG picture per row on types that have one (Board, Edging, Glass, Timber, Hardware, Custom, Benchtop, Hire, Appliance). ‘remove’ deletes it. | PUT\|DELETE /catalog/{slug}/{mid}/image · GET …/image | catalog:write | — |
| `CATA-09` | **+ New mapping / Create / Cancel** | button | Maps a CV code to a catalog row. | POST /catalog/cv-mappings | catalog:write | — |
| `CATA-10` | **Delete (mapping)** | button | The only hard delete in the catalog. | DELETE /catalog/cv-mappings/{id} | catalog:write | — |
| `CATA-11` | **Set stock / Remove (Stock)** | button | Upserts sheet stock for (material, size); removes a stock row. | POST\|DELETE /board-inventory | cut_floor:write | — |

### Cut Floor

*Route:* `/cut-floor`  
*Purpose:* CutPlan (what to cut) vs CutSchedule (when). Status planned → running → done; cancel from planned/running.

**Schedule board**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `CUTF-01` | **← / →** | button | Moves the schedule date by a day. | — | — | — |
| `CUTF-02` | **Optimise…** | button | Opens the optimiser (MaxRects nesting). Pure function: reads sheet stock but never writes or consumes it. | POST /projects/{pid}/optimise | cut_floor:write | — |
| `CUTF-03` | **Select all / Clear all** | button | Includes/excludes items in the optimisation. | — | — | — |
| `CUTF-04` | **Optimise (run)** | button | Runs with kerf, strategy, sheet size (or sizes from stock). | POST /projects/{pid}/optimise | — | — |
| `CUTF-05` | **← Back / Discard** | button | Back to settings / close without saving. | — | — | — |
| `CUTF-06` | **Save as plan** | button | Saves the proposal as a CutPlan. | POST /projects/{pid}/cut-plans | cut_floor:write | — |
| `CUTF-07` | **+ Add to <date> / Add / Cancel** | button | Schedules a plan for the date. | POST /cut-schedules | cut_floor:write | — |
| `CUTF-08` | **Start** | button | planned → running. | PATCH /cut-schedules/{id} | cut_floor:write | — |
| `CUTF-09` | **Mark done** | button | running → done. | PATCH /cut-schedules/{id} | cut_floor:write | — |
| `CUTF-10` | **Cancel (row)** | button | Confirms, then cancels the schedule. | DELETE /cut-schedules/{id} | cut_floor:write | — |
| `CUTF-11` | **Drag handle (not a button)** | link | Drag rows to reorder the day. | POST /cut-schedules/reorder | cut_floor:write | — |

### Shop Floor and station kiosk

*Route:* `/shop-floor · /shop-floor/station/[worker_id]`  
*Purpose:* Kanban keyed on (cutlist_id, stage_key) plus a worker kiosk. Mark-done enforces stage order; undo within 5 minutes for workers; Packing is the 6th stage with in-browser QR scanning.

**Kanban**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `SHOP-01` | **+ Assign worker** | button | Opens the assign dialog for the card’s next stage. | — | shop_floor:write | — |
| `SHOP-02` | **Assign / Cancel (dialog)** | button | Assigns a worker to (item, next stage) with a note. | POST /projects/{pid}/items/{iid}/assignments | — | — |
| `SHOP-03` | **× (assignment)** | button | Confirms, then cancels the assignment. | DELETE /assignments/{id} | — | — |

**Station kiosk**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `SHOP-04` | **Start <STAGE>** | button | Starts the worker’s assignment. | POST /assignments/{id}/start | shop_floor:write | — |
| `SHOP-05` | **Mark <STAGE> done / Confirm done / Cancel** | button | Completes with optional note; out-of-order → STAGE_OUT_OF_ORDER listing what to finish first. Fans out to item_stages. | POST /assignments/{id}/complete | — | — |
| `SHOP-06` | **Undo (recent completion)** | button | Reverses the whole cutlist’s completion; workers within 5 minutes. | POST /completions/{log_id}/undo | — | — |
| `SHOP-07` | **Confirm (Packing scanner)** | button | Submit button of the manual-entry form under the camera: validates the typed item number as if it had been scanned. The camera decodes QR codes continuously. | — | shop_floor:write | — |

### QC dashboard

*Route:* `/qc`  
*Purpose:* Read-only open defects and rework for cutlists that have started but not been packed.

**Filters**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `QC-01` | **Clear** | button | Resets project and date filters (URL stays linkable). | GET /qc/dashboard | qc:read | — |

### Estimating and Customers

*Route:* `/estimating · /estimating/[eid] · /customers · /customers/[cid]`  
*Purpose:* Revisioned quotes with snapshotted costs, 12-stage tender lifecycle, order preview/generation and Convert-to-Project. `advance()` is the only forward action; locked_at is the frozen gate.

**Estimate list**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ESTI-01` | **+ New estimate / + Create your first quote / Create / Cancel** | button | Creates an estimate for a customer. | POST /estimates | estimating:write | — |
| `ESTI-02` | **Active / Archive** | tab | Switches the sub-tab (URL ?subtab=). | — | — | — |

**Estimate detail**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ESTI-03` | **Revision rail (v1, v2…)** | link | Selects a revision (view-only for non-current). | — | — | — |
| `ESTI-04` | **Back to current** | button | Leaves the old revision. | — | — | — |
| `ESTI-05` | **Advance (label changes: Lock & send at Submitted)** | button | Moves one stage along the 12-stage lifecycle. MGMT_APPROVAL → SUBMITTED sets locked_at. | POST /revisions/{rid}/advance | estimating:approve | — |
| `ESTI-06` | **Accept / Reject / Withdraw / Expire** | button | Terminal outcomes (Reject and Expire ask for a reason). | POST /revisions/{rid}/accept\|reject\|withdraw\|expire | estimating:approve | — |
| `ESTI-07` | **Revise (new draft)** | button | Creates the next revision. | POST /estimates/{eid}/revise | estimating:write | — |
| `ESTI-08` | **Convert to project / Convert** | button | Pick lines, creates project + project_contract. | POST /revisions/{rid}/convert | estimating:approve | — |
| `ESTI-09` | **Generate orders / Review lines** | button | Opens the order preview, then generates draft POs grouped by live default supplier (one per supplier per run). | GET …/order-preview · POST …/generate-orders | estimating:approve | — |
| `ESTI-10` | **Ordered by hand… / Mark ordered by hand / Undo** | button | Per line or per material, with a required note. | POST\|DELETE …/order-dismissal | estimating:approve | — |

**Line editing**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ESTI-11` | **+ Add line** | button | Adds a quote line. | POST /revisions/{rid}/lines | estimating:write | — |
| `ESTI-12` | **✎ Edit / Save / Cancel** | button | Edits description, qty, unit, sell override. | PATCH /lines/{lid} | — | — |
| `ESTI-13` | **⎘ Clone** | button | Duplicates the line. | — | — | — |
| `ESTI-14` | **Delete line** | button | Confirms and deletes. | DELETE /lines/{lid} | — | — |
| `ESTI-15` | **+ Material (catalog picker) / kind tabs / pick row** | button | Adds a catalog material part to the line. | POST /lines/{lid}/parts | — | — |
| `ESTI-16` | **+ Labour / ×** | button | Sets labour hours per stage / zeroes it. | POST /lines/{lid}/labour | — | — |
| `ESTI-17` | **× (part) / × (hardware)** | button | Removes a part or hardware row. | DELETE /estimate-parts/{pid} · /hardware/{hid} | — | — |

**Customers**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `ESTI-18` | **+ New customer / Create / Cancel** | button | Creates a customer. | POST /customers | estimating:write | — |
| `ESTI-19` | **✎ Edit / Save / Cancel** | button | Edits customer details. | PATCH /customers/{cid} | — | — |
| `ESTI-20` | **Archive** | button | Confirms; archives. | POST /customers/{cid}/archive | — | — |

### IT management (admin only)

*Route:* `/it`  
*Purpose:* RBAC groups, labour rates, search health, staff photos, shop-worker roster.

**Panels**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `IT-01` | **Group row** | link | Selects a permission group (warns about unsaved changes). | — | — | — |
| `IT-02` | **Create (group)** | button | Creates a custom group. | POST /permission-groups | it_management:write | — |
| `IT-03` | **Save grants** | button | Writes the module × action grid (7 roles, 12 modules, 4 actions read/write/approve/comment). | PUT /permission-groups/{gid}/grants | — | — |
| `IT-04` | **Delete group** | button | Confirms and deletes (system groups cannot be). | DELETE /permission-groups/{gid} | — | — |
| `IT-05` | **Add / Remove (member)** | button | Adds a member (optionally project-scoped) or removes one. | POST /permission-groups/{gid}/memberships · DELETE /permission-groups/memberships/{mid} | — | — |
| `IT-06` | **Save (labour rates)** | button | Saves hourly rate per lifecycle stage. | PATCH /it/labour-rates | — | — |
| `IT-07` | **Refresh (search health)** | button | Reloads Meilisearch health/outbox. | GET /search/health | — | — |
| `IT-08` | **Remove (staff photo)** | button | Removes a staff photo (PNG/JPEG shown in the PO staff list). | DELETE /users/{id}/photo | — | — |

### Search results and Notifications pages

*Route:* `/search · /notifications`  
*Purpose:* Full pages behind the top-bar search and the bell.

**Pages**

| Id | Control | Kind | What it does | API | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `SEAR-01` | **Type chips (with counts)** | chip | Filter results by entity type; resets paging. | — | — | — |
| `SEAR-02` | **← Previous / Next →** | button | Pages results. | GET /search | — | — |
| `SEAR-03` | **Mark all read (page)** | button | Marks every notification read. | POST /notifications/read-all | — | — |
| `SEAR-04` | **Notification row** | button | Marks read and opens the object. | POST /notifications/{id}/read | — | — |

## 11. REST API catalogue

348 routes extracted from `apps/api/app`. The permission shown is the `require_permission(module, action)` guard; `current_user` means any signed-in user; `require_drafter` means drafter/manager/admin.

### `areas`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/areas` | tracking:read | The project's areas with their rooms nested (Q552). |
| POST | `/projects/{pid}/areas` | tracking:write |  |
| POST | `/areas/{aid}/rooms` | tracking:write |  |

### `auth`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| POST | `/auth/login` | — |  |
| POST | `/auth/logout` | current_user |  |
| GET | `/auth/me` | current_user |  |

### `catalog`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/catalog/cv-mappings` | catalog:read |  |
| POST | `/catalog/cv-mappings` | catalog:write |  |
| PATCH | `/catalog/cv-mappings/{mid}` | catalog:write |  |
| DELETE | `/catalog/cv-mappings/{mid}` | catalog:write |  |
| PUT | `/catalog/{slug}/{mid}/image` | catalog:write |  |
| GET | `/catalog/{slug}/{mid}/image` | catalog:read |  |
| DELETE | `/catalog/{slug}/{mid}/image` | catalog:write |  |
| GET | `/catalog/product-types` | catalog:read | The tabs of the Catalog screen: every product type in use, with its item count. |
| GET | `/catalog/by-type` | catalog:read | The items of one product type (or of none: `untyped=true`) across the six tables, grouped by table. |
| GET | `/catalog/{slug}` | catalog:read |  |
| POST | `/catalog/{slug}/bulk` | catalog:write | All-or-nothing: validate every row first; insert only if all clean. |
| GET | `/catalog/{slug}/{mid}` | catalog:read |  |
| POST | `/catalog/{slug}` | catalog:write |  |
| PATCH | `/catalog/{slug}/{mid}` | catalog:write |  |
| POST | `/catalog/{slug}/{mid}/archive` | catalog:write |  |

### `comments`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/comments` | current_user |  |
| GET | `/projects/{pid}/comment-counts` | — | Backs the project page's Areas & Rooms card: how many live comments each     area and room has. Read-only; sam |
| POST | `/comments` | current_user |  |
| PATCH | `/comments/{cid}` | current_user |  |
| DELETE | `/comments/{cid}` | current_user |  |

### `cut_floor`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| POST | `/projects/{pid}/cut-plans` | cut_floor:write |  |
| GET | `/projects/{pid}/cut-plans` | cut_floor:read |  |
| GET | `/cut-plans/{plan_id}` | cut_floor:read |  |
| GET | `/items/{iid}/cut-plan` | cut_floor:read |  |
| DELETE | `/cut-plans/{plan_id}` | cut_floor:write |  |
| POST | `/projects/{pid}/optimise` | cut_floor:write | Pure-function nest proposal — **no DB writes, no audit**. Packs parts     across one or more sheets and return |
| GET | `/board-inventory` | cut_floor:read |  |
| POST | `/board-inventory` | cut_floor:write | Record stock for a (material, sheet size). Upserts: posting the same     size again sets the quantity rather t |
| PATCH | `/board-inventory/{inventory_id}` | cut_floor:write |  |
| DELETE | `/board-inventory/{inventory_id}` | cut_floor:write |  |
| GET | `/cut-schedules` | cut_floor:read |  |
| GET | `/cut-schedules/{sid}` | cut_floor:read |  |
| POST | `/cut-schedules` | cut_floor:write |  |
| PATCH | `/cut-schedules/{sid}` | cut_floor:write |  |
| POST | `/cut-schedules/reorder` | cut_floor:write |  |
| DELETE | `/cut-schedules/{sid}` | cut_floor:write |  |

### `cutlists`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/cutlists` | list:read |  |
| GET | `/cutlists/{cid}` | list:read |  |
| POST | `/projects/{pid}/cutlists` | list:write |  |
| PATCH | `/cutlists/{cid}` | list:write |  |
| DELETE | `/cutlists/{cid}` | list:write |  |
| POST | `/cutlists/{cid}/items` | list:write |  |
| DELETE | `/cutlists/{cid}/items/{iid}` | list:write |  |

### `cv`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| POST | `/items/{iid}/cv-imports/preview` | cut_floor:write |  |
| POST | `/items/{iid}/cv-imports/{run_id}/commit` | cut_floor:write |  |
| GET | `/items/{iid}/cv-imports/replace-impact` | cut_floor:write | Read-only: how many modules and live module comments a `replace` commit     would delete. Same gate as the com |
| GET | `/items/{iid}/cv-imports` | cut_floor:read |  |
| GET | `/cv-imports/{run_id}` | cut_floor:read |  |

### `estimating`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/customers` | estimating:read |  |
| GET | `/customers/{cid}` | estimating:read |  |
| POST | `/customers` | estimating:write |  |
| PATCH | `/customers/{cid}` | estimating:write |  |
| POST | `/customers/{cid}/archive` | estimating:write |  |
| GET | `/estimates` | estimating:read |  |
| GET | `/estimates/{eid}` | estimating:read |  |
| POST | `/estimates` | estimating:write |  |
| PATCH | `/estimates/{eid}` | estimating:write |  |
| POST | `/estimates/{eid}/revise` | estimating:write |  |
| GET | `/estimates/{eid}/revisions/{rid}` | estimating:read |  |
| PATCH | `/revisions/{rid}` | estimating:write |  |
| POST | `/revisions/{rid}/advance` | estimating:approve | Move to the next stage in the 12-stage tender lifecycle (Q487/488) —     one generic action for all 10 forward |
| POST | `/revisions/{rid}/accept` | estimating:approve |  |
| POST | `/revisions/{rid}/reject` | estimating:approve |  |
| POST | `/revisions/{rid}/expire` | estimating:approve |  |
| POST | `/revisions/{rid}/withdraw` | estimating:approve |  |
| GET | `/revisions/{rid}/handover-preview` | estimating:approve |  |
| POST | `/revisions/{rid}/convert` | estimating:approve |  |
| GET | `/revisions/{rid}/order-preview` | estimating:approve |  |
| POST | `/revisions/{rid}/link-supplier` | estimating:approve | Narrow shortcut for the Generate Orders dialog: link a supplier to a material on     this revision that has no |
| POST | `/revisions/{rid}/lines/{lid}/order-dismissal` | estimating:approve | Mark a quote line "ordered by hand" (reason required) so it leaves the quote's     "not yet ordered" count. Ga |
| DELETE | `/revisions/{rid}/lines/{lid}/order-dismissal` | estimating:approve | Undo "ordered by hand": the line is orderable again (the old reason stays in the audit row). |
| POST | `/revisions/{rid}/lines/{lid}/materials/{material_type}/{material_id}/order-dismissal` | estimating:approve | Mark one material on a quote line "ordered by hand" (reason required). |
| DELETE | `/revisions/{rid}/lines/{lid}/materials/{material_type}/{material_id}/order-dismissal` | estimating:approve | Undo "ordered by hand" for one material: it is orderable again. |
| POST | `/revisions/{rid}/generate-orders` | estimating:approve |  |
| POST | `/revisions/{rid}/lines` | estimating:write |  |
| PATCH | `/lines/{lid}` | estimating:write |  |
| DELETE | `/lines/{lid}` | estimating:write |  |
| POST | `/revisions/{rid}/lines/reorder` | estimating:write |  |
| POST | `/lines/{lid}/parts` | estimating:write |  |
| DELETE | `/estimate-parts/{pid}` | estimating:write |  |
| PATCH | `/estimate-parts/{pid}` | estimating:write |  |
| POST | `/lines/{lid}/hardware` | estimating:write |  |
| DELETE | `/hardware/{hid}` | estimating:write |  |
| PATCH | `/hardware/{hid}` | estimating:write |  |
| POST | `/lines/{lid}/labour` | estimating:write |  |
| GET | `/it/labour-rates` | it_management:read |  |
| PATCH | `/it/labour-rates` | it_management:write |  |
| GET | `/revisions/{rid}/quote.pdf` | estimating:read |  |

### `files`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| POST | `/files` | shop_dwgs:write |  |
| GET | `/files/{file_blob_id}` | shop_dwgs:read |  |

### `hardware_lines`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/hardware_catalog` | list:read |  |
| POST | `/projects/{pid}/hardware_catalog` | require_drafter, current_user |  |
| DELETE | `/projects/{pid}/hardware_catalog/{cid}` | require_drafter, current_user |  |
| POST | `/items/{id}/hardware_lines` | require_drafter, current_user |  |
| PATCH | `/hardware_lines/{lid}` | require_drafter, current_user |  |
| DELETE | `/hardware_lines/{lid}` | require_drafter, current_user |  |
| GET | `/source_catalog/{table}` | list:read |  |

### `home`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/home/dashboard` | current_user | Composite landing payload personalised by role. |

### `item_attachments`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/items/{iid}/attachments` | list:read |  |
| POST | `/items/{iid}/attachments/{kind}` | list:write |  |
| DELETE | `/items/{iid}/attachments/{kind}` | list:write |  |

### `item_documents`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/items/{iid}/documents` | list:read |  |
| POST | `/items/{iid}/documents` | list:write |  |
| PATCH | `/documents/{did}` | list:write |  |
| DELETE | `/documents/{did}` | list:write |  |

### `item_duplicates`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| POST | `/items/{iid}/duplicate` | tracking:write |  |

### `item_queries`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/items/{iid}/queries` | list:read |  |
| POST | `/items/{iid}/queries` | list:read | Asking a question only needs read on `list`.  Drafter+ answers. |
| POST | `/queries/{qid}/answer` | list:write |  |
| PATCH | `/queries/{qid}/answer` | list:write |  |

### `items`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/items` | tracking:read | List items for a project. |
| GET | `/items/{id}/availability` | list:read |  |
| GET | `/items/{id}` | list:read |  |
| POST | `/projects/{pid}/items` | tracking:write | Create a new item inside a project.  Drafter-only gate. |
| PATCH | `/items/{id}` | tracking:write | Partially update an item.  Drafter-only gate.  Controlled Lock applies. |
| DELETE | `/items/{id}` | tracking:write | Soft-delete an item, its related parts and (when empty) its cutlist. |
| POST | `/items/{id}/restore` | tracking:write | Manager/admin only. Brings back a soft-deleted item with its related parts and cutlist. |
| POST | `/items/{id}/lock` | tracking:write | Claim lock (no body) or transfer lock to another user (body with owner_id). |
| PATCH | `/items/{id}/status` | tracking:write | Update items.status.  Allowed for any role with tracking:write     (admin, manager, editor, drafter — NOT purc |
| POST | `/items/bulk-status` | tracking:write | Apply a status + shared note to many items in one transaction. |
| PATCH | `/items/{id}/lifecycle/{stage_key}` | tracking:write | UPSERT due_date / done_date for a lifecycle stage on an item.     Allowed for any role with tracking:write.    |
| DELETE | `/items/{id}/lock` | tracking:write | Release a lock on an item.  cutlist_owner_id is NOT cleared (sticky). |
| POST | `/items/{id}/hard-lock` | tracking:write | Manager/admin only. Blocks PATCH /items/{id} for everyone, including     the current owner, until cleared with |
| DELETE | `/items/{id}/hard-lock` | tracking:write |  |
| GET | `/items/{id}/lock-requests` | tracking:read | Saves held against this item's lock, newest first.  `?status=pending` filters. |
| POST | `/lock-requests/{rid}/approve` | tracking:write | Apply the held save.  The edit log credits the requester, the audit the approver. |
| POST | `/lock-requests/{rid}/reject` | tracking:write | Discard the held save; the item is untouched. |

### `main.py`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/health` | — |  |

### `material_summaries`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/material-summary` | list:read |  |
| GET | `/projects/{pid}/material-summaries` | list:read |  |
| POST | `/projects/{pid}/material-summary` | list:write |  |
| PATCH | `/material-summaries/{sid}/lines/{lid}` | list:write |  |
| POST | `/material-summaries/{sid}/confirm` | list:approve |  |

### `material_takes`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/items/{iid}/material-take` | — |  |
| GET | `/items/{iid}/material-takes` | — |  |
| POST | `/items/{iid}/material-take/generate` | require_drafter |  |
| POST | `/material-takes/{tid}/regenerate` | require_drafter |  |
| POST | `/material-takes/{tid}/lines` | require_drafter |  |
| PATCH | `/material-takes/{tid}/lines/{lid}` | require_drafter |  |
| DELETE | `/material-takes/{tid}/lines/{lid}` | require_drafter |  |
| POST | `/material-takes/{tid}/approve` | — |  |
| POST | `/material-takes/{tid}/reviews` | — |  |

### `notifications`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/notifications` | current_user |  |
| POST | `/notifications/read-all` | current_user |  |
| POST | `/notifications/{nid}/read` | current_user |  |

### `order_tabs`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/glass-rates` | orderbook:read |  |
| POST | `/glass-rates` | orderbook:write |  |
| PATCH | `/glass-rates/{rate_id}` | orderbook:write |  |
| GET | `/orders/{po_id}/glass-calc` | orderbook:read |  |
| PUT | `/orders/{po_id}/glass-calc` | orderbook:write |  |
| GET | `/orders/{po_id}/deliveries` | orderbook:read |  |
| POST | `/orders/{po_id}/deliveries` | orderbook:write |  |
| PATCH | `/orders/{po_id}/deliveries/{delivery_id}` | orderbook:write |  |
| DELETE | `/orders/{po_id}/deliveries/{delivery_id}` | orderbook:write |  |
| POST | `/orders/{po_id}/deliveries/{delivery_id}/docket` | orderbook:write |  |
| GET | `/orders/{po_id}/deliveries/{delivery_id}/docket` | orderbook:read |  |
| DELETE | `/orders/{po_id}/deliveries/{delivery_id}/docket` | orderbook:write |  |
| GET | `/orders/{po_id}/stock` | orderbook:read |  |
| GET | `/orders/{po_id}/tracking` | orderbook:read |  |
| GET | `/orders/{po_id}/cutlists` | orderbook:read |  |
| GET | `/orders/{po_id}/catalog-item` | orderbook:read |  |
| GET | `/orders/{po_id}/catalog-item/image` | orderbook:read | The picture of the order's n-th catalog match (as listed by `/catalog-item`), gated by `orderbook`, not `catal |
| PUT | `/orders/{po_id}/image` | orderbook:write |  |
| GET | `/orders/{po_id}/image` | orderbook:read |  |
| DELETE | `/orders/{po_id}/image` | orderbook:write |  |
| GET | `/orders/{po_id}/tg-runs` | orderbook:read |  |
| POST | `/orders/{po_id}/tg-runs` | orderbook:write |  |
| PATCH | `/orders/{po_id}/tg-runs/{run_id}` | orderbook:write |  |
| DELETE | `/orders/{po_id}/tg-runs/{run_id}` | orderbook:write |  |
| GET | `/orders/{po_id}/timber` | orderbook:read |  |
| PUT | `/orders/{po_id}/timber` | orderbook:write |  |
| POST | `/orders/{po_id}/timber/form` | orderbook:write | Create: render the sheet from the saved fields and keep that PDF on the order. |
| GET | `/orders/{po_id}/timber/form` | orderbook:read |  |

### `orders`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/orders/{po_id}/attachments` | orderbook:read |  |
| POST | `/orders/{po_id}/attachments` | orderbook:write |  |
| GET | `/orders/{po_id}/attachments/{attachment_id}/download` | orderbook:read |  |
| DELETE | `/orders/{po_id}/attachments/{attachment_id}` | orderbook:write |  |
| GET | `/order-categories` | orderbook:read | The category lookup `0031` introduced in place of the frozen CHECK. |
| GET | `/orders` | orderbook:read | Backs the Orderbook page's Orders tab — every order in the workspace. |
| GET | `/orders/cost-breakdown` | orderbook:read | The Orderbook's Cost centre pop-up: cost by order type over every order.     Declared before `/orders/{po_id}` |
| GET | `/projects/{pid}/budget` | tracking:read | Tracking > Info > Budget: one project's material cost by order type. Managers and admins     only (the budget  |
| GET | `/projects/{pid}/orders` | orderbook:read |  |
| GET | `/items/{iid}/orders` | orderbook:read | Backs Tracking's O/BOOK subtab for one row (Q425). |
| GET | `/orders/{po_id}` | orderbook:read |  |
| POST | `/orders` | orderbook:write | Create Order (Q425). Passing `item_id` prefills PROJECT / LOCATION /     CUTLIST NO. from that row — for a rel |
| PATCH | `/orders/{po_id}` | orderbook:write |  |
| DELETE | `/orders/{po_id}` | orderbook:write | Soft-cancel, matching #4's batch semantics — a second cancel is a 409. Cancelling an Approved     or Rejected  |
| POST | `/orders/{po_id}/lines` | orderbook:write |  |
| PATCH | `/orders/{po_id}/lines/{line_id}` | orderbook:write |  |
| DELETE | `/orders/{po_id}/lines/{line_id}` | orderbook:write |  |
| GET | `/cost-centers` | orderbook:read |  |
| POST | `/cost-centers` | orderbook:write | A purchase officer's (or an admin's) to add, like the approval limit. |
| PATCH | `/cost-centers/{cost_center_id}` | orderbook:write | Rename or (de)activate: the same people who add one. Orders that already use it are left as     they are; an i |

### `parts`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| POST | `/items/{id}/modules` | require_drafter, current_user |  |
| PATCH | `/modules/{mid}` | require_drafter, current_user |  |
| GET | `/modules/{mid}/delete-impact` | require_drafter, current_user | Read-only preview for the delete confirmation. Same gate as the delete it     warns about; another workspace's |
| DELETE | `/modules/{mid}` | require_drafter, current_user |  |
| POST | `/modules/{mid}/parts` | require_drafter, current_user |  |
| PATCH | `/parts/{pid}` | require_drafter, current_user |  |
| DELETE | `/parts/{pid}` | require_drafter, current_user |  |

### `payment_methods`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/payment-methods` | orderbook:read |  |
| POST | `/payment-methods` | orderbook:write |  |
| PATCH | `/payment-methods/{payment_method_id}` | orderbook:write |  |

### `permission_groups`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/permission-groups` | it_management:read |  |
| POST | `/permission-groups` | it_management:write |  |
| PUT | `/permission-groups/{gid}/grants` | it_management:write |  |
| DELETE | `/permission-groups/{gid}` | it_management:write |  |
| GET | `/permission-groups/{gid}/memberships` | it_management:read |  |
| POST | `/permission-groups/{gid}/memberships` | it_management:write |  |
| DELETE | `/permission-groups/memberships/{mid}` | it_management:write |  |
| GET | `/permission-groups/users/{uid}/memberships` | it_management:read |  |

### `printing`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/items/{iid}/cutlist.pdf` | list:read |  |
| GET | `/items/{iid}/hardware.pdf` | list:read |  |
| GET | `/items/{iid}/combined.pdf` | list:read |  |

### `procurement_v1`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/batches/{bid}/allocations` | orderbook:read |  |
| POST | `/batches/{bid}/allocations` | orderbook:write |  |
| PATCH | `/allocations/{aid}` | orderbook:write |  |
| DELETE | `/allocations/{aid}` | orderbook:write |  |
| GET | `/batches` | orderbook:read |  |
| POST | `/batches` | orderbook:write |  |
| GET | `/batches/{bid}` | orderbook:read |  |
| PATCH | `/batches/{bid}` | orderbook:write |  |
| DELETE | `/batches/{bid}` | orderbook:write |  |
| GET | `/projects/{pid}/materials` | orderbook:read |  |
| GET | `/procurement-queue` | orderbook:read |  |

### `project_contacts`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/contacts` | tracking:read |  |
| POST | `/projects/{pid}/contacts` | tracking:write |  |
| PATCH | `/contacts/{cid}` | tracking:write |  |
| DELETE | `/contacts/{cid}` | tracking:write |  |

### `project_contracts`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/contract` | tracking:read |  |
| POST | `/projects/{pid}/contract/variations` | tracking:write |  |
| GET | `/projects/{pid}/actual-costs` | tracking:read |  |

### `project_lift_access`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/lift-access` | tracking:read |  |
| PUT | `/projects/{pid}/lift-access` | tracking:write |  |
| DELETE | `/projects/{pid}/lift-access` | tracking:write |  |

### `projects`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects` | tracking:read |  |
| GET | `/projects/{pid}` | tracking:read |  |
| POST | `/projects` | current_user |  |
| PATCH | `/projects/{pid}` | current_user |  |
| POST | `/projects/{pid}/close-out` | current_user | Close out a project.  Admin/manager only.  409 if already closed. |
| POST | `/projects/{pid}/favourites` | current_user |  |
| DELETE | `/projects/{pid}/favourites` | current_user |  |

### `public`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/public/stats` | — | Aggregate counts for a workspace — used on the login page brand panel.     No authentication required; returns |

### `purchase_orders`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/purchase-orders/staff` | orderbook:read |  |
| GET | `/purchase-orders/staff/{user_id}/photo` | orderbook:read |  |
| GET | `/purchase-orders` | orderbook:read |  |
| POST | `/purchase-orders` | orderbook:write |  |
| GET | `/purchase-orders/{doc_id}` | orderbook:read |  |
| PATCH | `/purchase-orders/{doc_id}` | orderbook:write |  |
| POST | `/purchase-orders/{doc_id}/orders` | orderbook:write |  |
| DELETE | `/purchase-orders/{doc_id}/orders/{order_id}` | orderbook:write |  |
| POST | `/purchase-orders/{doc_id}/cancel` | orderbook:write |  |
| PUT | `/purchase-orders/{doc_id}/delivery` | orderbook:write |  |
| DELETE | `/purchase-orders/{doc_id}/delivery` | orderbook:write |  |
| POST | `/purchase-orders/{doc_id}/invoices` | orderbook:write |  |
| PATCH | `/purchase-orders/{doc_id}/invoices/{invoice_id}` | orderbook:write |  |
| DELETE | `/purchase-orders/{doc_id}/invoices/{invoice_id}` | orderbook:write |  |
| GET | `/purchase-orders/{doc_id}/pdf` | orderbook:read |  |
| GET | `/purchase-orders/{doc_id}/excel` | orderbook:read |  |
| POST | `/purchase-orders/{doc_id}/invoices/{invoice_id}/files/{slot}` | orderbook:write |  |
| GET | `/purchase-orders/{doc_id}/invoices/{invoice_id}/files/{slot}` | orderbook:read |  |
| DELETE | `/purchase-orders/{doc_id}/invoices/{invoice_id}/files/{slot}` | orderbook:write |  |
| GET | `/purchase-orders/{doc_id}/authorisation` | orderbook:read |  |
| PUT | `/purchase-orders/{doc_id}/authorisation` | orderbook:write |  |
| POST | `/purchase-orders/{doc_id}/authorisation/form` | orderbook:write | Create Form: render the sheet from the saved details and keep that PDF (the one that is printed,     signed by |
| POST | `/purchase-orders/{doc_id}/authorisation/signed` | orderbook:write |  |
| GET | `/purchase-orders/{doc_id}/authorisation/{which}` | orderbook:read |  |
| DELETE | `/purchase-orders/{doc_id}/authorisation/signed` | orderbook:write |  |

### `qc`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/qc/dashboard` | qc:read |  |
| GET | `/items/{iid}/qc/defects` | qc:read |  |
| POST | `/items/{iid}/qc/defects` | qc:write |  |
| PATCH | `/qc/defects/{did}` | qc:write |  |
| POST | `/qc/defects/{did}/resolve` | qc:approve |  |
| GET | `/items/{iid}/qc/checklist` | qc:read |  |
| POST | `/items/{iid}/qc/checklist` | qc:write |  |
| PATCH | `/qc/checklist/{cid}` | qc:write |  |
| DELETE | `/qc/checklist/{cid}` | qc:write |  |
| GET | `/items/{iid}/qc/rework` | qc:read |  |
| POST | `/items/{iid}/qc/rework` | qc:write |  |
| PATCH | `/qc/rework/{rid}` | qc:write |  |
| POST | `/qc/rework/{rid}/close` | qc:approve |  |

### `related_parts`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/related-part-types` | tracking:read | Q448 — configurable, seeded with metal / benchtop / cushion. |
| GET | `/items/{parent_id}/related-parts` | tracking:read |  |
| GET | `/related-parts/{rid}` | tracking:read |  |
| POST | `/items/{parent_id}/related-parts` | tracking:write |  |
| PATCH | `/related-parts/{rid}` | tracking:write |  |
| POST | `/related-parts/{rid}/reparent` | tracking:write | Q452 — moves the part, its Group ID, and its orders' CUTLIST NO. |
| DELETE | `/related-parts/{rid}` | tracking:write |  |

### `samples`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/samples` | isample:read |  |
| GET | `/projects/{pid}/samples/ledger` | isample:read |  |
| GET | `/samples/{sid}` | isample:read |  |
| POST | `/projects/{pid}/samples` | isample:write |  |
| PATCH | `/samples/{sid}` | isample:write |  |
| POST | `/samples/{sid}/approve` | isample:approve |  |
| POST | `/samples/{sid}/reject` | isample:approve |  |
| POST | `/samples/{sid}/archive` | isample:write |  |
| POST | `/samples/{sid}/photo` | isample:write |  |
| DELETE | `/samples/{sid}/photo` | isample:write |  |

### `search`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/search` | current_user |  |
| GET | `/search/health` | it_management:read |  |

### `shop_drawings`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/shop-drawings` | shop_dwgs:read |  |
| GET | `/shop-drawings/{did}` | shop_dwgs:read |  |
| GET | `/shop-drawings/{did}/history` | shop_dwgs:read |  |
| POST | `/projects/{pid}/shop-drawings` | shop_dwgs:write |  |
| PATCH | `/shop-drawings/{did}` | shop_dwgs:write |  |
| POST | `/shop-drawings/{did}/archive` | shop_dwgs:approve |  |
| POST | `/shop-drawings/{did}/revisions` | shop_dwgs:write |  |
| POST | `/shop-drawings/{did}/revisions/{rid}/submit` | shop_dwgs:write |  |
| POST | `/shop-drawings/{did}/revisions/{rid}/withdraw` | shop_dwgs:write |  |
| POST | `/shop-drawings/{did}/revisions/{rid}/approve` | shop_dwgs:approve |  |
| POST | `/shop-drawings/{did}/revisions/{rid}/reject` | shop_dwgs:approve |  |

### `shop_floor`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/shop-floor/board` | shop_floor:read |  |
| GET | `/projects/{pid}/shop-floor/workers` | shop_floor:read |  |
| GET | `/workers/{wid}/queue` | shop_floor:read |  |
| GET | `/workers/{wid}/recent-completions` | shop_floor:read |  |
| POST | `/projects/{pid}/items/{iid}/assignments` | shop_floor:write |  |
| PATCH | `/assignments/{aid}` | shop_floor:write |  |
| DELETE | `/assignments/{aid}` | shop_floor:write |  |
| POST | `/assignments/{aid}/start` | shop_floor:write |  |
| POST | `/assignments/{aid}/complete` | shop_floor:write |  |
| POST | `/completions/{log_id}/undo` | shop_floor:write |  |

### `suppliers`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/suppliers` | orderbook:read |  |
| GET | `/suppliers/{vendor_id}` | orderbook:read |  |
| GET | `/suppliers/{vendor_id}/materials` | orderbook:read | Every catalog row pointing here, across all six tables. |
| POST | `/suppliers` | orderbook:write |  |
| PATCH | `/suppliers/{vendor_id}` | orderbook:write |  |
| POST | `/suppliers/{vendor_id}/materials` | orderbook:write | Q506 — repoint a catalog row's supplier at this vendor. |
| GET | `/suppliers/{vendor_id}/contacts` | orderbook:read |  |
| POST | `/suppliers/{vendor_id}/contacts` | orderbook:write |  |
| PATCH | `/suppliers/{vendor_id}/contacts/{contact_id}` | orderbook:write |  |
| DELETE | `/suppliers/{vendor_id}/contacts/{contact_id}` | orderbook:write |  |
| PUT | `/suppliers/{vendor_id}/logo` | orderbook:write |  |
| GET | `/suppliers/{vendor_id}/logo` | orderbook:read |  |
| DELETE | `/suppliers/{vendor_id}/logo` | orderbook:write |  |

### `users`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/users` | it_management:read |  |
| PATCH | `/users/{uid}` | it_management:write |  |
| PUT | `/users/{uid}/photo` | it_management:write | The small photo shown in front of a name in the PO staff list (an admin sets it). |
| DELETE | `/users/{uid}/photo` | it_management:write |  |
| GET | `/users/team` | current_user | List all workspace members with their current work_status + location.     Any authenticated user can read. is_ |
| PATCH | `/users/status` | current_user | Update caller's own work_status + location_label. Authenticated-only     (no module gate — every user can publ |
| PATCH | `/users/{uid}/shop-worker` | it_management:write | Admin-only toggle of `is_shop_worker`. Powers the /it     WorkerRosterPanel. |

### `workspaces`

| Method | Path | Guard | Note |
| --- | --- | --- | --- |
| GET | `/workspace` | current_user |  |

## 12. Not built / open items

- Cars and OH&S tabs (Q550) and Scope tab (Q572) on Project Information (shown disabled).
- Q480 SharePoint URL; Q547 drawing filename; Task and Change comment threads (no entities); Q472 rule engine (per-object rules stay in handlers); §21’s wider Procurement flow.
- PO approval reporting: cost centres have no delete, no cross-centre report and no hard budget limit.
- E3 data import: only the item grid and the orders grid are imported; modules, parts, hardware, drawings and QC still need their own exports.
- Planned, kept on purpose (decision 2026-10-19): login ‘Continue with SSO’ and status pop-up ‘Update Status To All’ do nothing yet.
- Lock-request routes have no web UI yet; decision 2026-10-19: add an item-editor banner with Approve/Reject plus a bell notification.
- Legacy `/procurement/*` retired October 2026 (code in `legacy/procurement_v0/`, unmounted).

Three decisions deliberately depart from Plan V1’s prose and must not be “fixed”: **Q499** (PM confirmation of the Material Summary is advisory), **Q513** (no rollback of change states), **Q527** (fixed KPI catalogue).

## 13. Questions for you

| Id | Topic | Question | My recommendation |
| --- | --- | --- | --- |
| Q-01 | Audience | Who reads these two files — developers, the joinery staff/customer, or both? It decides the language (technical vs. plain), whether API routes stay in the spec, and whether I add a short ‘day in the life’ walkthrough per role. | Both: keep the spec technical, add a plain-language ‘What this does for me’ line per screen. |
| Q-02 | Source of truth | CLAUDE.md says per-sub-project history lives in docs/sub-projects/ and Plan V1 is the roadmap. Should this spec replace, sit beside, or link into those files? Two documents describing the same behaviour will drift. | Keep it as docs/software-spec/ and make the sub-project files link to it; regenerate the button tables from code (see S-01). |
| Q-03 | Login · Continue with SSO | The button only calls preventDefault — it does nothing. Remove it, hide it, or is SSO (which provider?) planned? | DECIDED 2026-10-19: keep it (SSO is planned). Provider still to be named. |
| Q-04 | Status pop-up · ‘Update Status To All’ | Permanently disabled with the tooltip ‘Bulk update not yet wired’, yet ‘Apply status…’ on the grid already does bulk updates (up to 500). Is the pop-up button meant to be removed, or to apply to a different set (e.g. all rows of this cutlist)? | DECIDED 2026-10-19: keep it as a planned control. Its intended scope (this item vs. a whole cutlist) is still open. |
| Q-05 | Controlled Lock requests | The API holds an edit made under someone else’s Controlled Lock as a lock request (and has approve/reject/list routes), but no web button calls them. Where should the owner approve/reject — item editor banner, a Notifications entry, or both? | DECIDED 2026-10-19: banner on the item editor for the lock owner plus a bell notification. Not built; needs its own PR (see Q-12). |
| Q-06 | Disabled tabs: Cars, OH&S, Scope | Project Information shows three permanently disabled tabs (blocked on Q550 / Q572). Keep showing them, or hide until specified? | Hide; list them under ‘Not built’ in the spec. |
| Q-07 | Per-role button matrix | Roles are DB-governed (groups + memberships), not fixed. The spec records the permission each route needs, not what each of the 13 seeded users sees. Do you want a role × button matrix, and for which workspace/DB (the dev seed, or your real groups)? | Generate it from the seeded groups; I can add it as a table. |
| Q-08 | Screenshots | The HTML is text-only. Want a Playwright screenshot of each screen/pop-up embedded next to its buttons? It needs a running stack (make up/migrate/seed) and makes the file much larger. | Yes, as separate PNGs linked from the HTML (keeps the file small). |
| Q-09 | What counts as a ‘button’ | I included every <button> (409 in 129 files), plus tabs, chips, toggles and the nav links that behave like buttons. I left out plain table links, text inputs, selects and drag-and-drop except where they replace a button. Is that the right line? | Keep, but add a short ‘non-button controls’ list per screen (filters, selects). |
| Q-11 | CLAUDE.md: six tables or nine? | CLAUDE.md §7 still lists a binding invariant ‘Six separate catalog tables … never unify’, while the entries directly above it say the Catalog now has nine tables (Edging, Glass, Solid Timber added; 14 product types) and that this ‘will end the rule below’. Which statement is current? | Treat nine as current and edit the invariant to say so; this spec already does. |
| Q-12 | Order of the remaining work | You asked for: the lock-request banner + bell (a code feature), a role × button matrix, screenshots, and a plain-language staff guide. The matrix and guide need no running app; the screenshots need the stack up; the lock-request UI touches locks (CLAUDE.md §9) and should have its own tests. Which first? | Matrix, then staff guide (docs only), then lock-request UI as its own PR with tests, then screenshots. |
| Q-10 | Scope: web only, or API-only functions too? | The spec describes everything the UI exposes. Some API routes have no UI (e.g. lock-request routes, related-parts reparent, legacy /procurement). Should the spec document those as ‘API-only’? | Yes — a short API-only appendix (generated from the routes table below). |

## 14. Suggestions

| Id | Suggestion | Why | Priority |
| --- | --- | --- | --- |
| S-01 | **Generate the button table from code in CI** | The extractor I used (a ~40-line script) finds every <button>, its label, handler, data-testid and line. Run in CI it would fail the build when a button is added/removed without the spec being regenerated, so the spec can never drift. | High |
| S-02 | **Label planned controls as planned** | You chose to keep ‘Continue with SSO’ and ‘Update Status To All’. A visible ‘Coming soon’ tooltip on the SSO button (the status one already has one) keeps users from reporting them as bugs. | Low |
| S-03 | **Build the lock-request UI (decided)** | Banner with Approve/Reject on the item editor plus a bell notification, as you chose. Needs tests under CLAUDE.md §9 and a workspace-isolation check; do it as its own PR. | High |
| S-04 | **Replace window.confirm / prompt / alert** | About 40 native dialogs are used (delete, archive, rename, cancel, expiry reason…). They cannot be styled, translated or tested reliably and block the thread. A single shared ConfirmDialog (with required-reason and typed-confirm variants) would also fix inconsistent wording. | Medium |
| S-05 | **Only 114 of 409 buttons have a data-testid** | Most e2e flake shapes in CLAUDE.md §3 (‘locator matches a different element with the same role’) come from this. Add stable test ids to destructive and state-changing buttons first. | Medium |
| S-06 | **Standardise the dialog pattern** | Cancel / primary-submit with a ‘…ing…’ busy label is hand-copied in ~60 places (fixed inset-0 overlays; only 19 have role=dialog and 8 aria-modal). One Dialog primitive gives focus trap, Esc-to-close and consistent busy/disabled behaviour for free. | Medium |
| S-07 | **44 buttons have no type attribute** | Inside a <form> a button without type="button" submits the form. Audit those, or add an ESLint rule (react/button-has-type). | Medium |
| S-08 | **Show why a button is disabled** | 160 buttons use disabled=…, but only some give a reason (e.g. ‘Tick exactly one row to edit it’, lock reasons). Make a tooltip/inline reason the rule for every disabled button. | Medium |
| S-09 | **Document keyboard shortcuts** | Only ‘/’ (focus search) and arrow/enter/esc in the search box exist. Candidates: n = new item on Tracking, j/k to move rows, ? for a shortcut cheat-sheet. | Low |
| S-10 | **Per-role ‘what I can click’ view** | Because RBAC is data-driven, nobody can answer ‘what does a drafter see?’ without logging in as one. A generated role × module × action matrix on /it would answer it and double as a review aid. | Medium |
| S-11 | **Undo for destructive grid actions** | Bulk Delete and Archive actions confirm with a native dialog but have no in-app undo (apart from manager/admin Restore). A 10-second ‘Undo’ toast (like Shop Floor’s 5-minute undo) fits the existing pattern. | Low |
| S-12 | **Print/PDF actions deserve one pattern** | PO PDF/Excel, cutlist/hardware/combined PDFs, quote PDF, item label and the Timber/Authorisation forms each have their own button style and loading behaviour. A shared ‘Download / Print’ menu would reduce the count of one-off buttons. | Low |

## Appendix B. Role × control matrix

✔ = the role holds the grant the control needs, — = it does not, **?** = the requirement is a per-object or free-text rule I could not reduce to a grant (read the Who column in section 10). Computed from the default `MATRIX`; per-object rules (uploader ≠ approver, creator-or-manager, locks, 5-minute undo) are not reflected.

| Id | Control | admin | manager | editor | drafter | estimator | purchase_officer | viewer |
| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `CHRO-01` | JoineryFlow logo / name | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-02` | Search box (type-ahead) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-03` | Search hit row | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-04` | All results for “q” → | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-05` | 🔔 Notification bell | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-06` | Mark all read (bell) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-07` | Notification row | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-08` | Sign out | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-09` | Dashboard | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-10` | Tracking ↗ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-11` | List ↗ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-12` | Shop Dwgs | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-13` | iSample | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-14` | Orderbook ↗ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-15` | Catalog / Shop Floor / Cut Floor / QC / Estimating / Customers | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-16` | /it (admin only) | ✔ | ✔ | — | — | — | — | — |
| `CHRO-17` | FAV / ALL toggle | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CHRO-18` | ☆ / ★ favourite star | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `LOGI-01` | Sign in | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `LOGI-02` | × (dismiss notice) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `LOGI-03` | Continue with SSO | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `DASH-01` | Metric tile (each) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `DASH-02` | My Day row, Delivery row, Activity row | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `DASH-03` | ✎ Update status | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `DASH-04` | Status choices (In / On site / Shop / WFH / Off) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `DASH-05` | Clear | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `DASH-06` | Save | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `DASH-07` | Cancel | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `PROJ-01` | + New project | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `PROJ-02` | ✕ (drawer) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `PROJ-03` | Create | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `PROJ-04` | Cancel (drawer) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-01` | Project name ▾ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-02` | ★ FAV / ALL (menu) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-03` | Project row (menu) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-04` | ★ (favourite) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-05` | Info | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-06` | 🛒 Open Procurement | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-07` | Edit item | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-08` | + New item | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `TRAC-09` | My Entries | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-10` | Deleted | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-11` | Void | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-12` | Tg Solid | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-13` | Orders | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-14` | Overdue | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-15` | Installed | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-16` | ↻ (refresh) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-17` | Show / Hide (row count) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-18` | Apply status… | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `TRAC-19` | Delete (selection) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `TRAC-20` | Restore (selection) | ✔ | ✔ | — | — | — | — | — |
| `TRAC-21` | Clear selection | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-22` | DATE · TO BE ORDERED · iTIME · HARDWARE · SITE MEASURE · INVOICE · QC  | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-23` | + Create Order | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `TRAC-24` | Clear (filters) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-25` | Column headers (Th) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-26` | ▶ (open) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-27` | ▶ / ▼ (related parts) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-28` | Status pill | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `TRAC-29` | Open item availability | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-30` | Status choices | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-31` | ⚠ Update Status To All | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-32` | ↻ Update Current Item | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `TRAC-33` | Close | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-34` | Apply <STATUS> | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `TRAC-35` | Cancel | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-36` | Create and open | ✔ | ✔ | — | ✔ | — | — | — |
| `TRAC-37` | Cancel | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-38` | ✕ / CLOSE | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-39` | Modal tabs (register / slots / reference fields) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-40` | ‹ Previous / Next › | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-41` | + Add field | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-42` | Create order | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `TRAC-43` | Close / Cancel | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-44` | Project stats / Budget tabs | ✔ | ✔ | — | — | — | — | — |
| `TRAC-45` | Cars / OH&S / Scope tabs | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `TRAC-46` | Close | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-01` | Delete | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-02` | ✕ (close editor) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-03` | Hard-lock / Unlock (banner) | ✔ | ✔ | — | — | — | — | — |
| `ITEM-04` | Lock / Unlock (footer) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-05` | (no button) Lock requests | ✔ | ✔ | — | — | — | — | — |
| `ITEM-06` | Cutlist · Hardware · Board · Material Take · Attachments · Actions · Q | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-07` | Import from CV | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-08` | + Add module | ✔ | ✔ | — | — | — | — | — |
| `ITEM-09` | Module (tree item) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-10` | Delete module | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-11` | Delete module (confirm) | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-12` | + Add row | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-13` | – (delete part) | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-14` | Preview | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-15` | Use existing / Create new / Skip (per unknown code) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-16` | Continue / Back | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-17` | Import | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-18` | Cancel / Close | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-19` | + (Pantry row) | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-20` | + Add from global | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-21` | Table tabs (modal) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-22` | Add (modal row) | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-23` | − / + (cart qty) | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-24` | – (cart delete) | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-25` | ✕ (modal) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-26` | Generate material take / Start v(n+1) | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-27` | Regenerate | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-28` | Add line / Remove | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-29` | Approve | ? | ? | ? | ? | ? | ? | ? |
| `ITEM-30` | No impact / Partial impact / Full impact | ? | ? | ? | ? | ? | ? | ? |
| `ITEM-31` | Upload / Replace (slot card) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-32` | Delete (slot card) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-33` | Add document (Register) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-34` | ↑ / ↓ (register) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-35` | Remove (register) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-36` | Set status | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-37` | Mark REQ done today | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-38` | Duplicate item | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-39` | Duplicate (confirm) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ITEM-40` | Duplicated from #n | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-41` | Jump to Orderbook | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-42` | Ask | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-43` | Answer / Save / Edit answer | ✔ | ✔ | — | ✔ | — | — | — |
| `ITEM-44` | Raise (defect) | ✔ | ✔ | ✔ | — | — | — | — |
| `ITEM-45` | Mark resolved | ✔ | ✔ | — | — | — | — | — |
| `ITEM-46` | Add / × (checklist) | ✔ | ✔ | ✔ | — | — | — | — |
| `ITEM-47` | + Log rework / Log / Cancel | ✔ | ✔ | ✔ | — | — | — | — |
| `ITEM-48` | Close (rework) | ✔ | ✔ | — | — | — | — | — |
| `ITEM-49` | Comment | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-50` | Reply / Edit / Delete / Save / Cancel | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ITEM-51` | Print label | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `PROJ-01` | Close out | ✔ | ✔ | — | — | — | — | — |
| `PROJ-02` | + Add contact / Add / Cancel / Remove | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `PROJ-03` | Upload sketch / Replace / Remove | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `PROJ-04` | + Add variation / Add / Cancel | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `PROJ-05` | Area row / Room row | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `PROJ-06` | Material-type headers (n item(s) ▾) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `PROJ-07` | + New batch / Save / Cancel batch | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `PROJ-08` | + Allocate / remove | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `PROJ-09` | Catalog tabs / + Add | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `PROJ-10` | Build summary / Rebuild from approved takes | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `PROJ-11` | Confirm (summary) | ✔ | ✔ | — | ✔ | — | — | — |
| `PROJ-12` | ▸ / ▾ line | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `PROJ-13` | ✕ (batch drawer) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `LIST-01` | + New cutlist | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `LIST-02` | Rename | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `LIST-03` | Delete | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `LIST-04` | Close | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `LIST-05` | Items / Parts / Hardware | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `LIST-06` | Link | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `LIST-07` | Unlink | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `SHOP-01` | Upload drawing | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `SHOP-02` | Create drawing (dialog) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `SHOP-03` | Queue buttons (Being drawn, Internal review… with counts) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-04` | My drawings on/off | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-05` | All (n) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-06` | Column headers | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-07` | ‹ › | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-08` | View (row) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-09` | ✕ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-10` | Revisions / Notes / Attachments / Status History / Audit Log | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-11` | Comments on v# ▾ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-12` | Revision row / View | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-13` | Submit for review | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `SHOP-14` | Withdraw | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `SHOP-15` | Approve | ✔ | ✔ | — | ✔ | — | — | — |
| `SHOP-16` | Reject / Confirm reject / Cancel | ✔ | ✔ | — | ✔ | — | — | — |
| `SHOP-17` | Upload new revision / Add revision | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `SHOP-18` | Archive drawing | ✔ | ✔ | — | ✔ | — | — | — |
| `SHOP-19` | ← Back | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-20` | − / + / Fit | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-21` | Revision rows | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SHOP-22` | Thumbnail | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ISAM-01` | Board / Approval ledger / Archive | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ISAM-02` | + New sample / Create sample / Cancel | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ISAM-03` | Status filter chips | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ISAM-04` | Sample card | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ISAM-05` | ✕ (drawer) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ISAM-06` | Approve | ✔ | ✔ | — | ✔ | — | — | — |
| `ISAM-07` | Reject / Confirm reject / Cancel | ✔ | ✔ | — | ✔ | — | — | — |
| `ISAM-08` | Edit / Save / Cancel | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ISAM-09` | Upload photo / Replace photo / Upload | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ISAM-10` | Clear photo | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ISAM-11` | Archive | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `ISAM-12` | Ledger entry / Previous / Next | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-01` | Orders / Delivery queue | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-02` | Cost centre | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-03` | Edit / Done (cost centres) | ✔ | — | — | — | — | ✔ | — |
| `ORDE-04` | Add / Save / Cancel (cost centre) | ✔ | — | — | — | — | ✔ | — |
| `ORDE-05` | Save / Deactivate / Reactivate (row) | ✔ | — | — | — | — | ✔ | — |
| `ORDE-06` | RTO | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-07` | TBO | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-08` | Due / Over Due / Arrived / My Orders | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-09` | Clear | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-10` | New | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-11` | Create order | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-12` | Supplier | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-13` | Po (n) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-14` | Clear selection (n) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-15` | PO link in a row | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-16` | Close | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-17` | Reject order / Cancel | ✔ | ✔ | — | — | — | ✔ | — |
| `ORDE-18` | Cancel order / Keep order | ✔ | ✔ | — | — | — | ✔ | — |
| `ORDE-19` | Open PO n / Create PO! | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-20` | HOME · Delivery · Glass C · Timber · Stock · Tracking · Supplier · TGS | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-21` | + Add line / × (line) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-22` | − (attachment) / FILE / PDF upload | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-23` | remove (product image) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-24` | Catalog item block (HOME, read-only) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-25` | + Add / − / × (Delivery) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-26` | Clear All / ▸ Copy Size (Glass C) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-27` | Edit price list / Done / Switch on/off / Add (Glass C) | ✔ | — | — | — | — | ✔ | — |
| `ORDE-28` | CLEAR / CREATE (Timber) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-29` | + Add / − (TGSolid) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-30` | Add supplier / Edit / Save / Cancel / Close | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-31` | Remove (logo) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-32` | + Contact / Edit / − / Save contact / Cancel | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-33` | Close / Done | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-34` | Add Delivery / Update Delivery / Remove | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-35` | ○ / ✓ (Invoiced) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-36` | − (line) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-37` | Add from TBO | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-38` | Add (TBO row) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-39` | + Contact / Add contact / Cancel | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-40` | Print | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-41` | Authorisation Form | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-42` | Cancel PO | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-43` | Email Details | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-44` | ‹ / › | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-45` | + Add (invoice) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-46` | ↻ (Total Ex) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-47` | ✓ / ○ (GST auto) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ORDE-48` | remove (file) / Delete / Close | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-49` | Create Form (Authorisation) | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-50` | remove (Signed Form) / Close | ✔ | ✔ | — | ✔ | — | ✔ | — |
| `ORDE-51` | Edit list / Switch on/off / Add (payment method) | ✔ | — | — | — | — | ✔ | — |
| `ORDE-52` | Open (Invoice Details table) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CATA-01` | Product-type tabs (name (count)) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CATA-02` | No type (n) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CATA-03` | Sheet Stock / CV Mappings | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CATA-04` | + New / Create / Cancel | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CATA-05` | Bulk import / Import n rows / Done | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CATA-06` | Archive (row) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CATA-07` | Cells (inline edit) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CATA-08` | Product image: upload / remove | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CATA-09` | + New mapping / Create / Cancel | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CATA-10` | Delete (mapping) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CATA-11` | Set stock / Remove (Stock) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-01` | ← / → | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CUTF-02` | Optimise… | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-03` | Select all / Clear all | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CUTF-04` | Optimise (run) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-05` | ← Back / Discard | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `CUTF-06` | Save as plan | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-07` | + Add to <date> / Add / Cancel | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-08` | Start | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-09` | Mark done | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-10` | Cancel (row) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `CUTF-11` | Drag handle (not a button) | ✔ | ✔ | ✔ | ✔ | — | — | — |
| `SHOP-01` | + Assign worker | ✔ | ✔ | ✔ | — | — | — | — |
| `SHOP-02` | Assign / Cancel (dialog) | ✔ | ✔ | ✔ | — | — | — | — |
| `SHOP-03` | × (assignment) | ✔ | ✔ | ✔ | — | — | — | — |
| `SHOP-04` | Start <STAGE> | ✔ | ✔ | ✔ | — | — | — | — |
| `SHOP-05` | Mark <STAGE> done / Confirm done / Cancel | ✔ | ✔ | ✔ | — | — | — | — |
| `SHOP-06` | Undo (recent completion) | ✔ | ✔ | ✔ | — | — | — | — |
| `SHOP-07` | Confirm (Packing scanner) | ✔ | ✔ | ✔ | — | — | — | — |
| `QC-01` | Clear | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ESTI-01` | + New estimate / + Create your first quote / Create / Cancel | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-02` | Active / Archive | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ESTI-03` | Revision rail (v1, v2…) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ESTI-04` | Back to current | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ESTI-05` | Advance (label changes: Lock & send at Submitted) | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-06` | Accept / Reject / Withdraw / Expire | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-07` | Revise (new draft) | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-08` | Convert to project / Convert | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-09` | Generate orders / Review lines | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-10` | Ordered by hand… / Mark ordered by hand / Undo | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-11` | + Add line | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-12` | ✎ Edit / Save / Cancel | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-13` | ⎘ Clone | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ESTI-14` | Delete line | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-15` | + Material (catalog picker) / kind tabs / pick row | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-16` | + Labour / × | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-17` | × (part) / × (hardware) | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-18` | + New customer / Create / Cancel | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-19` | ✎ Edit / Save / Cancel | ✔ | ✔ | — | — | ✔ | — | — |
| `ESTI-20` | Archive | ✔ | ✔ | — | — | ✔ | — | — |
| `IT-01` | Group row | ✔ | ✔ | — | — | — | — | — |
| `IT-02` | Create (group) | ✔ | — | — | — | — | — | — |
| `IT-03` | Save grants | ✔ | — | — | — | — | — | — |
| `IT-04` | Delete group | ✔ | — | — | — | — | — | — |
| `IT-05` | Add / Remove (member) | ✔ | — | — | — | — | — | — |
| `IT-06` | Save (labour rates) | ✔ | — | — | — | — | — | — |
| `IT-07` | Refresh (search health) | ✔ | ✔ | — | — | — | — | — |
| `IT-08` | Remove (staff photo) | ✔ | — | — | — | — | — | — |
| `SEAR-01` | Type chips (with counts) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SEAR-02` | ← Previous / Next → | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SEAR-03` | Mark all read (page) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `SEAR-04` | Notification row | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |

Controls each role can use (of 295 with a computable rule; 2 are `?`): admin 295, manager 284, editor 208, drafter 245, estimator 157, purchase_officer 176, viewer 141.


## Appendix A. Source index of every `<button>` in the web app

410 `<button>` elements in 130 files (`apps/web`). Labels are as written in the source (expressions shown verbatim). The searchable version is in the HTML.

**`app/(app)/catalog/_components/BoardImageCell.tsx`**

- L39 — remove

**`app/(app)/catalog/_components/CatalogBulkImportDialog.tsx`**

- L98 — Done
- L133 — Cancel
- L136 — {busy ? "Importing…" : `Import ${parsed.rows.length} rows`}

**`app/(app)/catalog/_components/CatalogClient.tsx`**

- L180 — Bulk import
- L184 — + New

**`app/(app)/catalog/_components/CatalogRow.tsx`**

- L322 — Archive

**`app/(app)/catalog/_components/CatalogTabs.tsx`**

- L21 — {label} {active && }

**`app/(app)/catalog/_components/MappingPanel.tsx`**

- L37 — + New mapping
- L68 — Delete

**`app/(app)/catalog/_components/NewCatalogRowDialog.tsx`**

- L306 — Cancel
- L307 — {busy ? "Saving…" : "Create"}

**`app/(app)/catalog/_components/NewMappingDialog.tsx`**

- L108 — {r.description}{" "} {r.sku}
- L129 — Cancel
- L130 — {busy ? "Saving…" : "Create"}

**`app/(app)/catalog/_components/StockPanel.tsx`**

- L223 — Remove
- L336 — {busy ? "Saving…" : "Set stock"}

**`app/(app)/customers/[cid]/_components/CustomerDetailClient.tsx`**

- L98 — {editing ? "Cancel" : "✎ Edit"} · `edit-customer-btn`
- L108 — Archive · `archive-customer-btn`
- L239 — Cancel
- L246 — {submitting ? "Saving…" : "Save"} · `save-customer-btn`

**`app/(app)/customers/_components/CustomersClient.tsx`**

- L70 — + New customer · `new-customer-btn`
- L107 — + Create your first customer
- L226 — Cancel
- L233 — {submitting ? "Creating…" : "Create"}

**`app/(app)/cut-floor/_components/CutFloorClient.tsx`**

- L181 — ←
- L195 — →
- L221 — Optimise…
- L230 — + Add to {date === initialDate ? "today" : date}
- L290 — Start
- L299 — Mark done
- L309 — Cancel
- L473 — Cancel
- L480 — {submitting ? "Adding…" : "Add"}

**`app/(app)/cut-floor/_components/OptimiseDialog.tsx`**

- L383 — {allIncluded ? "Clear all" : "Select all"}
- L441 — Cancel
- L448 — {busy ? "Optimising…" : "Optimise"}
- L552 — ← Back
- L559 — Discard
- L566 — {busy ? "Saving…" : "Save as plan"}

**`app/(app)/estimating/_components/EstimateDetailClient.tsx`**

- L317 — Back to current · `back-to-current`
- L361 — Withdraw · `withdraw-btn`
- L370 — {nextStageLabel(currentRev?.status) === "Submitted" ? "Lock & send" : `Advance → · `advance-btn`
- L386 — Accept · `accept-btn`
- L395 — Reject
- L403 — Withdraw
- L411 — Expire · `expire-btn`
- L420 — Revise (new draft)
- L434 — Convert to project · `convert-btn`
- L483 — {pendingOrderLines > 0 ? "Generate orders" : "Review lines"} · `generate-orders-btn`

**`app/(app)/estimating/_components/EstimatingClient.tsx`**

- L91 — + New estimate · `new-estimate-btn`
- L103 — Active
- L114 — Archive
- L140 — + Create your first quote
- L324 — Cancel
- L331 — {submitting ? "Creating…" : "Create"}

**`app/(app)/estimating/_components/estimate-detail/CatalogPicker.tsx`**

- L49 — {KIND_LABEL[k]} · ``picker-kind-${k}``
- L64 — ×
- L153 — {row.sku} — {row.description} · ``picker-pick-${row.material_id}``

**`app/(app)/estimating/_components/estimate-detail/ConvertPreviewDialog.tsx`**

- L80 — Cancel
- L87 — {busy ? "Converting…" : "Convert"} · `convert-confirm-btn`

**`app/(app)/estimating/_components/estimate-detail/HardwareRow.tsx`**

- L38 — × · ``remove-hw-${hardware.hw_id}``

**`app/(app)/estimating/_components/estimate-detail/LabourEditor.tsx`**

- L19 — ×

**`app/(app)/estimating/_components/estimate-detail/LineCard.tsx`**

- L158 — ×
- L175 — + Material · ``add-material-${line.line_id}``
- L183 — + Labour · ``add-labour-${line.line_id}``
- L191 — ✎ Edit · ``edit-line-${line.line_id}``
- L199 — ⎘ Clone · ``clone-line-${line.line_id}``
- L207 — Delete line

**`app/(app)/estimating/_components/estimate-detail/LineEditRow.tsx`**

- L87 — Cancel
- L94 — Save · ``line-edit-save-${line.line_id}``

**`app/(app)/estimating/_components/estimate-detail/NewLineForm.tsx`**

- L74 — + Add line · `new-line-submit`

**`app/(app)/estimating/_components/estimate-detail/OrderPreviewDialog.tsx`**

- L290 — Undo · ``undo-dismiss-${l.line_id}``
- L300 — {l.materials && l.materials.length > 1 ? "All by hand…" : "Ordered by hand…"} · ``dismiss-line-${l.line_id}``
- L339 — Undo · ``undo-dismiss-material-${l.line_id}-${mKey}``
- L349 — Ordered by hand… · ``dismiss-material-${l.line_id}-${mKey}``
- L404 — {lineBusy ? "Saving…" : "Mark ordered by hand"} · `dismiss-save`
- L412 — Cancel
- L522 — Cancel
- L529 — {busy ? "Generating…" : preview.groups.length === 0 ? "Mark ticked lines done (n · `generate-orders-confirm-btn`

**`app/(app)/estimating/_components/estimate-detail/PartRow.tsx`**

- L43 — × · ``remove-part-${part.part_id}``

**`app/(app)/estimating/_components/estimate-detail/RevisionRail.tsx`**

- L25 — v{r.rev_no}{" "} {r.status} {isCurrent ? ( current ) : null} {fmtMoney(r.total_i · ``revision-rail-${r.rev_no}``

**`app/(app)/isample/_components/ApprovalLedger.tsx`**

- L74 — {humanize(e)}
- L86 — Previous
- L90 — Next

**`app/(app)/isample/_components/EditSampleForm.tsx`**

- L76 — {busy ? "Saving…" : "Save"}
- L80 — Cancel

**`app/(app)/isample/_components/ISampleClient.tsx`**

- L88 — + New sample

**`app/(app)/isample/_components/NewSampleDialog.tsx`**

- L105 — Cancel
- L106 — {busy ? "Creating…" : "Create sample"}

**`app/(app)/isample/_components/PhotoUploadDialog.tsx`**

- L44 — Cancel
- L45 — {busy ? "Uploading…" : "Upload"}

**`app/(app)/isample/_components/ReviewActions.tsx`**

- L54 — Approve
- L60 — Reject
- L72 — Confirm reject
- L82 — Cancel
- L93 — Edit
- L99 — {p.sample.photo_file_blob_id ? "Replace photo" : "Upload photo"}
- L105 — Clear photo
- L111 — Archive

**`app/(app)/isample/_components/SampleCard.tsx`**

- L31 — {sample.title} {sample.project_code}{sample.room ? ` · ${sample.room}` : ""} {de

**`app/(app)/isample/_components/SampleDrawer.tsx`**

- L67 — ✕

**`app/(app)/isample/_components/SampleFilters.tsx`**

- L33 — {label} {count}

**`app/(app)/isample/_components/SubtabStrip.tsx`**

- L26 — {t.label}{badge} {active && }

**`app/(app)/it/_components/LabourRatesPanel.tsx`**

- L111 — {saving ? "Saving…" : "Save"} · `save-rates-btn`

**`app/(app)/it/_components/PermissionGroupsPanel.tsx`**

- L146 — {g.name} {g.is_system && ( system )} {g.grants.length}
- L179 — {creating ? "…" : "Create"}
- L298 — {deleting ? "…" : "Delete group"}
- L312 — {savingGrants ? "Saving…" : "Save grants"}
- L465 — Remove
- L512 — {adding ? "…" : "Add"}

**`app/(app)/it/_components/SearchHealthPanel.tsx`**

- L32 — Refresh

**`app/(app)/it/_components/StaffPhotosPanel.tsx`**

- L56 — Remove

**`app/(app)/items/[id]/_components/ActionsTab.tsx`**

- L162 — {label} {description} · `testId`

**`app/(app)/items/[id]/_components/AttachmentSlotCard.tsx`**

- L141 — {populated ? (busy ? "Replacing…" : "Replace") : (busy ? "Uploading…" : "Upload"
- L151 — Delete

**`app/(app)/items/[id]/_components/DocumentRegister.tsx`**

- L123 — {busy ? "Working…" : "Add document"}
- L182 — ↑
- L192 — ↓
- L202 — Remove

**`app/(app)/items/[id]/_components/DuplicateItemDialog.tsx`**

- L83 — Cancel
- L91 — {busy ? "Duplicating…" : "Duplicate"} · `duplicate-confirm`

**`app/(app)/items/[id]/_components/EditorFooter.tsx`**

- L101 — {item.item_locked ? "Unlock" : "Lock"}

**`app/(app)/items/[id]/_components/EditorTabs.tsx`**

- L75 — {TAB_LABELS[tab]}

**`app/(app)/items/[id]/_components/HardLockBanner.tsx`**

- L67 — {busy ? "…" : locked ? "Unlock" : "Hard-lock"}

**`app/(app)/items/[id]/_components/ItemHeader.tsx`**

- L70 — {deleting ? "Deleting…" : "Delete"} · `delete-item`
- L81 — ✕ · `close-editor`

**`app/(app)/items/[id]/_components/MaterialTakeTab.tsx`**

- L103 — {o === "no_impact" ? "No impact" : o === "partial" ? "Partial impact" : "Full im
- L118 — {cur.approved ? `Start v${cur.approved.version + 1}` : "Generate material take"}
- L165 — Regenerate
- L170 — Approve
- L224 — Add line
- L284 — Remove

**`app/(app)/items/[id]/_components/QcTab.tsx`**

- L113 — Raise
- L156 — Mark resolved
- L244 — Add
- L282 — ×
- L344 — + Log rework
- L408 — Close
- L502 — Log
- L509 — Cancel

**`app/(app)/items/[id]/_components/QueryTab.tsx`**

- L105 — Ask
- L196 — {answered ? "Save" : "Answer"}
- L206 — Cancel
- L221 — Edit answer

**`app/(app)/items/[id]/_components/cutlist/CutlistTab.tsx`**

- L111 — Import from CV
- L151 — Delete module · `delete-module`

**`app/(app)/items/[id]/_components/cutlist/CvImportDialog.tsx`**

- L161 — Close
- L211 — Cancel
- L218 — {busy ? "Parsing…" : "Preview"}
- L248 — Back
- L255 — Continue
- L315 — Back
- L326 — {busy ? "Importing…" : "Import"}

**`app/(app)/items/[id]/_components/cutlist/DeleteModuleDialog.tsx`**

- L123 — Cancel
- L131 — {busy ? "Deleting…" : "Delete module"}

**`app/(app)/items/[id]/_components/cutlist/ModuleTree.tsx`**

- L37 — {m.name ?? "Untitled module"}
- L53 — + Add module

**`app/(app)/items/[id]/_components/cutlist/PartsGrid.tsx`**

- L103 — + Add row
- L239 — –

**`app/(app)/items/[id]/_components/cutlist/UnknownCodeRow.tsx`**

- L92 — Use existing
- L101 — Create new
- L108 — Skip

**`app/(app)/items/[id]/_components/hardware/AddFromGlobalModal.tsx`**

- L99 — ✕
- L112 — {t.replace(/_/g, " ")}
- L165 — Add

**`app/(app)/items/[id]/_components/hardware/Cart.tsx`**

- L177 — −
- L189 — +
- L217 — –

**`app/(app)/items/[id]/_components/hardware/Pantry.tsx`**

- L92 — +
- L111 — + Add from global

**`app/(app)/list/_components/CutlistClient.tsx`**

- L129 — + New cutlist
- L263 — Rename
- L271 — Delete
- L281 — Close
- L305 — Link
- L331 — {label}
- L386 — Unlink

**`app/(app)/notifications/_components/NotificationsList.tsx`**

- L61 — Mark all read
- L116 — {notificationText(n)} {n.object_label && · {n.object_label}} {formatLocalTs(n.cr

**`app/(app)/orderbook/_components/CostBreakdownModal.tsx`**

- L37 — Close

**`app/(app)/orderbook/_components/NewOrderDialog.tsx`**

- L130 — Cancel
- L132 — Create order · `new-order-create`

**`app/(app)/orderbook/_components/OrderbookTabs.tsx`**

- L46 — {t === "orders" ? "Orders" : "Delivery queue"}

**`app/(app)/orderbook/_components/OrdersClient.tsx`**

- L236 — Cost centre · `cost-centre-breakdown-open`
- L243 — {ccManage ? "Done" : "Edit"} · `cost-centre-manage`
- L248 — Add · `cost-centre-add`
- L259 — Save · `cost-centre-save`
- L261 — Cancel
- L269 — Clear selection ({selected})
- L283 — {v.label} · ``orders-view-${k}``
- L292 — New · `orders-new`
- L295 — Clear · `orders-view-clear`
- L300 — Supplier · `orders-suppliers`
- L302 — Po{tickedRows.length > 0 ? ` (${tickedRows.length})` : ""} · `orders-po`
- L311 — {v.label} · ``orders-view-${v.key}``

**`app/(app)/orderbook/_components/SupplierContacts.tsx`**

- L71 — {open === "new" ? "Add contact" : "Save contact"} · `supplier-contact-save`
- L75 — Cancel
- L85 — + Contact · `supplier-contact-add`
- L100 — Edit · `supplier-contact-edit`
- L102 — − · `supplier-contact-delete`

**`app/(app)/orderbook/_components/SupplierListModal.tsx`**

- L159 — Remove
- L165 — {open === "new" ? "Add supplier" : "Save"} · `supplier-save`
- L169 — Cancel
- L188 — Add supplier · `supplier-add`
- L191 — Close
- L218 — Edit · `supplier-edit`

**`app/(app)/orderbook/_components/orders/AddLineForm.tsx`**

- L71 — {busy ? "Adding…" : "+ Add line"}

**`app/(app)/orderbook/_components/orders/CostCentreManager.tsx`**

- L54 — Save · `cost-centre-edit-save`
- L59 — {c.is_active ? "Deactivate" : "Reactivate"} · `cost-centre-toggle`

**`app/(app)/orderbook/_components/orders/LineRow.tsx`**

- L111 — ×

**`app/(app)/orderbook/_components/orders/OrderAttachments.tsx`**

- L79 — − · `order-attachment-remove`

**`app/(app)/orderbook/_components/orders/OrderDetailPanel.tsx`**

- L309 — Close · `order-detail-close`
- L335 — Reject order · `order-reject-confirm`
- L349 — Cancel
- L367 — Cancel order · `order-cancel-confirm`
- L372 — Keep order
- L459 — {t} · ``order-tab-${t}``
- L475 — Open PO {order.po_no} · `order-create-po`
- L480 — Create PO! · `order-create-po`

**`app/(app)/orderbook/_components/orders/OrderRowView.tsx`**

- L55 — {row.po_no} · `order-po-link`

**`app/(app)/orderbook/_components/orders/ProductImage.tsx`**

- L37 — remove · `order-image-remove`

**`app/(app)/orderbook/_components/orders/tabs/DeliveryTab.tsx`**

- L68 — ×
- L77 — − · `delivery-remove`
- L91 — + Add · `delivery-add`

**`app/(app)/orderbook/_components/orders/tabs/GlassTab.tsx`**

- L57 — Clear All · `glass-clear`
- L82 — ▸ Copy Size · `glass-copy-size`
- L95 — {listOpen ? "Done" : "Edit price list"} · `glass-edit-list`
- L128 — {r.is_active ? "Switch off" : "Switch on"}
- L138 — Add · `glass-new-add`

**`app/(app)/orderbook/_components/orders/tabs/TgSolidTab.tsx`**

- L48 — − · `tg-remove`
- L59 — + Add · `tg-add`

**`app/(app)/orderbook/_components/orders/tabs/TimberTab.tsx`**

- L69 — CLEAR · `timber-clear`
- L74 — CREATE · `timber-create`

**`app/(app)/orderbook/_components/po/AuthorisationWindow.tsx`**

- L122 — Close
- L182 — remove
- L186 — Close · `auth-close`
- L187 — Create Form · `auth-create`

**`app/(app)/orderbook/_components/po/InvoiceWindow.tsx`**

- L195 — ‹
- L198 — ›
- L202 — + Add · `inv-add`
- L224 — ↻ · `inv-refresh`
- L234 — {d.gst_auto ? "✓" : "○"} · `inv-gst-auto`
- L278 — remove
- L285 — Close · `inv-close`
- L287 — Delete · `inv-delete`

**`app/(app)/orderbook/_components/po/PaymentMethodSelect.tsx`**

- L37 — {editing ? "Done" : "Edit list"} · ``${testId}-edit``
- L53 — {m.is_active ? "Switch off" : "Switch on"}
- L61 — Add · ``${testId}-add``

**`app/(app)/orderbook/_components/po/PoInvoices.tsx`**

- L35 — Open · `po-invoice-open`

**`app/(app)/orderbook/_components/po/PurchaseOrderModal.tsx`**

- L175 — Close · `po-done`
- L212 — Done · `po-done`
- L244 — {doc.delivery_order_id ? "Update Delivery" : "Add Delivery"} · `po-add-delivery`
- L246 — Remove
- L272 — {l.invoiced ? "✓" : "○"} · `po-line-invoiced`
- L281 — − · `po-line-remove`
- L299 — Add · `po-tbo-add`
- L321 — −
- L332 — Add contact · `po-contact-save`
- L333 — Cancel
- L336 — + Contact · `po-contact-add`
- L375 — Add from TBO · `po-add-tbo`
- L377 — Print · `po-print`
- L380 — Authorisation Form · `po-auth`
- L382 — Cancel PO · `po-cancel`

**`app/(app)/projects/[id]/_components/ProjectAreasCommentsCard.tsx`**

- L182 — {a.name}{" "} · {a.item_count} item{a.item_count === 1 ? "" : "s"} · ``area-row-${a.area_id}``
- L206 — {r.rm_no} {r.rm_desc && {r.rm_desc}} · ``room-row-${r.room_id}``

**`app/(app)/projects/[id]/_components/ProjectContactsPanel.tsx`**

- L28 — + Add contact
- L128 — Remove
- L227 — Add
- L234 — Cancel

**`app/(app)/projects/[id]/_components/ProjectFinancialsCard.tsx`**

- L33 — + Add variation
- L170 — Add
- L177 — Cancel

**`app/(app)/projects/[id]/_components/ProjectHeader.tsx`**

- L69 — {closed ? "Closed" : busy ? "Closing…" : "Close out"}

**`app/(app)/projects/[id]/_components/ProjectLiftAccessPanel.tsx`**

- L89 — Replace
- L97 — Remove
- L110 — {busy ? "Uploading…" : "Upload sketch"}

**`app/(app)/projects/[id]/procurement/_components/AllocationEditor.tsx`**

- L59 — remove
- L86 — + Allocate · `alloc-add`

**`app/(app)/projects/[id]/procurement/_components/BatchDrawer.tsx`**

- L57 — ✕
- L144 — Save · `save-batch`
- L148 — Cancel batch

**`app/(app)/projects/[id]/procurement/_components/BatchesTable.tsx`**

- L40 — + New batch · `new-batch`

**`app/(app)/projects/[id]/procurement/_components/CatalogTabs.tsx`**

- L84 — {t.replace("_"," ")}
- L132 — + Add

**`app/(app)/projects/[id]/procurement/_components/MaterialSummaryPanel.tsx`**

- L64 — {s ? "Rebuild from approved takes" : "Build summary"}
- L70 — Confirm
- L166 — {expanded ? "▾" : "▸"} {line.description}

**`app/(app)/projects/[id]/procurement/_components/ProjectMaterialsTable.tsx`**

- L52 — {rows.length} item(s) {isOpen ? "▾" : "▸"}

**`app/(app)/projects/_components/CreateProjectDrawer.tsx`**

- L53 — + New project
- L71 — ✕
- L124 — Cancel
- L131 — {isPending ? "Creating…" : "Create"}

**`app/(app)/qc/_components/QcDashboardClient.tsx`**

- L171 — Clear

**`app/(app)/search/_components/SearchResults.tsx`**

- L82 — {label} {n}
- L172 — ← Previous
- L183 — Next →

**`app/(app)/shop-dwgs/_components/DetailsPanel.tsx`**

- L149 — ✕
- L225 — {t.label}
- L248 — Comments on v{selectedRev.rev_no} {commentsOpen ? "▾" : "▸"}
- L341 — v{r.rev_no} {i === 0 && Latest} {r.uploaded_by_name ?? "—"} {fmtTs(r.uploaded_at
- L349 — View

**`app/(app)/shop-dwgs/_components/DrawingViewer.tsx`**

- L91 — ← Back
- L100 — −
- L102 — +
- L103 — Fit
- L151 — v{r.rev_no} {i === 0 && Latest} {active && Viewing}

**`app/(app)/shop-dwgs/_components/NewRevisionDialog.tsx`**

- L41 — Cancel
- L42 — {busy ? "Uploading…" : "Add revision"}

**`app/(app)/shop-dwgs/_components/QueueRail.tsx`**

- L33 — {QUEUE_LABELS[q]} {counts[q] ?? 0} · ``queue-${q}``
- L55 — My drawings {mine ? "on" : "off"} · `queue-mine`
- L72 — {QUEUE_LABELS.all} {total} · `queue-all`

**`app/(app)/shop-dwgs/_components/RegisterTable.tsx`**

- L122 — View · `view-drawing`
- L176 — ‹
- L179 — ›
- L199 — {col.label} {active ? (sort.dir === 1 ? "↑" : "↓") : "↕"}

**`app/(app)/shop-dwgs/_components/ReviewActions.tsx`**

- L50 — Submit for review
- L56 — Withdraw
- L63 — Approve
- L68 — Reject
- L80 — Confirm reject
- L90 — Cancel
- L107 — Upload new revision
- L113 — Archive drawing

**`app/(app)/shop-dwgs/_components/ShopDwgsClient.tsx`**

- L126 — Upload drawing

**`app/(app)/shop-dwgs/_components/ThumbnailStrip.tsx`**

- L109 — { canvases.current[n - 1] = el; }} /> · `thumbnail`

**`app/(app)/shop-dwgs/_components/UploadDialog.tsx`**

- L103 — Cancel
- L104 — {busy ? "Uploading…" : "Create drawing"}

**`app/(app)/shop-floor/_components/ShopFloorClient.tsx`**

- L225 — ×
- L238 — + Assign worker
- L373 — Cancel
- L380 — {submitting ? "Assigning…" : "Assign"}

**`app/(app)/shop-floor/station/[worker_id]/_components/PackingScanner.tsx`**

- L123 — Confirm

**`app/(app)/shop-floor/station/[worker_id]/_components/StationClient.tsx`**

- L157 — Start {active.stage_key}
- L166 — Mark {active.stage_key} done
- L244 — Undo
- L352 — Cancel
- L359 — {submitting ? "Marking…" : "Confirm done"}
- L373 — Cancel

**`app/(app)/tracking/_components/BulkStatusDialog.tsx`**

- L114 — Cancel
- L122 — {submitting ? "Applying…" : `Apply ${status}`}

**`app/(app)/tracking/_components/CreateOrderDialog.tsx`**

- L122 — Close
- L288 — + Add field
- L299 — Cancel
- L306 — {busy ? "Creating…" : "Create order"}

**`app/(app)/tracking/_components/ItemDetailModal.tsx`**

- L62 — ✕
- L118 — {t}
- L143 — ‹ Previous
- L151 — CLOSE
- L158 — Next ›

**`app/(app)/tracking/_components/ItemsTable.tsx`**

- L217 — {st}
- L231 — + Create Order
- L281 — Clear

**`app/(app)/tracking/_components/NewItemDialog.tsx`**

- L122 — Cancel
- L130 — {submitting ? "Creating…" : "Create and open"} · `new-item-create`

**`app/(app)/tracking/_components/ProjectDetailModal.tsx`**

- L82 — Close
- L93 — {t.label} · ``project-tab-${t.key}``

**`app/(app)/tracking/_components/ProjectInfoBar.tsx`**

- L72 — {project.name} ▾
- L86 — ★ FAV
- L97 — ALL
- L117 — ★ {p.name} {p.project_code}
- L142 — ★
- L156 — Info
- L172 — 🛒 Open Procurement
- L181 — Edit item · `edit-item`
- L192 — + New item · `new-item`

**`app/(app)/tracking/_components/StatusPopup.tsx`**

- L155 — ⚠ Update StatusTo All
- L164 — ↻ UpdateCurrent Item
- L209 — Close

**`app/(app)/tracking/_components/TrackingClient.tsx`**

- L255 — ↻
- L270 — Restore
- L279 — Apply status…
- L286 — Delete
- L295 — Clear selection
- L330 — Show
- L337 — Hide
- L442 — {label}

**`app/(app)/tracking/_components/items-table/Row.tsx`**

- L78 — ▶
- L94 — {relatedOpen ? "▼" : "▶"}
- L140 — {row.status ?? "—"}
- L200 — Open item availability · `open-availability`

**`app/(public)/login/page.tsx`**

- L163 — ×
- L251 — {busy ? "Signing in…" : "Sign in"}
- L265 — Continue with SSO

**`app/items/[id]/label/_components/ItemLabelClient.tsx`**

- L47 — Print label

**`components/chrome/LogoutButton.tsx`**

- L12 — Sign out

**`components/chrome/NotificationBell.tsx`**

- L79 — 🔔 {badge > 0 && ( {badge > 99 ? "99+" : badge} )} · `notification-bell`
- L109 — Mark all read
- L153 — {notificationText(n)} {n.object_label && ( · {n.object_label} )} {n.excerpt}

**`components/chrome/ProjectSidebar.tsx`**

- L44 — {t}
- L86 — {p.is_favourite ? "★" : "☆"}

**`components/chrome/SearchBox.tsx`**

- L144 — {hit.codes[0] && ( {hit.codes[0]} )} {hit.title} {hit.subtitle && ( {hit.subtitl
- L170 — All results for “{q.trim()}” →

**`components/comments/CommentThread.tsx`**

- L127 — Comment · `comment-submit`
- L246 — Save
- L259 — Cancel
- L292 — Reply
- L305 — Cancel
- L319 — Reply
- L324 — Edit
- L336 — Delete

**`components/comments/MentionTextarea.tsx`**

- L102 — {m.full_name} {m.auth_role}

**`components/pm/TeamCard.tsx`**

- L90 — ✎ Update status
- L235 — {STATUS_LABEL[o]}
- L249 — Clear
- L272 — Cancel
- L279 — {submitting ? "Saving…" : "Save"}

**`components/procurement/AvailabilityDrawer.tsx`**

- L85 — ✕

**`components/procurement/CostBreakdownTable.tsx`**

- L37 — {open ? "▾" : "▸"} {g.label}

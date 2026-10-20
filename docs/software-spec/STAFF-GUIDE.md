# JoineryFlow — Staff Guide

A plain-language guide to what each role can do in JoineryFlow. For every button and screen in detail, see `button-reference.html`; for the technical rules, see `SOFTWARE-SPEC.md`.

> **Written from the code on 2026-10-20, not from watching people use the software.** The permissions below are the *default* ones. An admin can change them on the IT page (`/it`), so what you can click at your workplace may differ. If a button you expect is missing or greyed out, hover over it: many say why.

## The basics (everyone)

- **Sign in** at the login page with your email and password. You stay signed in for up to 14 days of use (30 days at most).
- **Six main tabs** run along the top: **Dashboard, Tracking, List, Shop Dwgs, iSample, Orderbook**. Below them is a second row: **Catalog, Shop Floor, Cut Floor, QC, Estimating, Customers**. You only see the tabs your role may read. Tracking, List and Orderbook open in a **new browser tab** (the small ↗), so you can keep two side by side.
- **Search** box (top): type to find projects, items, orders, suppliers, drawings, samples, customers or quotes. Press `/` to jump into it, arrow keys to choose, Enter to open.
- **Bell** (top): comment notifications and @mentions. *Mark all read* clears it. Purchase officers also see orders waiting for a decision here.
- **Comments**: most records have a comment thread. You can reply, edit your own comment and @mention a colleague.
- **Asking and confirming**: risky actions (delete, archive, cancel, reject, close out) ask first in a dialog; names (a new cutlist, a rename, a new area or room) are typed in a dialog too. **Enter** confirms; **Esc**, **Cancel** or a click outside do nothing.
- **Undo**: after you confirm a bulk delete in Tracking, or an archive of a catalog row, customer, shop drawing or sample, a box at the bottom left says what you did and offers **Undo** for 10 seconds. Nothing has really happened until the 10 seconds end, so Undo simply cancels it. If you close the tab or leave the app inside the 10 seconds the action is carried out straight away; if the whole browser or computer is switched off in that time it is lost. Deleting a single item from the item editor is immediate (no Undo).
- **Locks**: an item can be locked so nobody breaks work in progress. A locked control is greyed out and says why. See "Locks in plain words" at the end.
- **Dashboard**: tiles for your role, "My Day", today's deliveries, your team's status and recent activity. Click a tile to jump to the list behind it. Use **✎ Update status** on the team card to tell everyone whether you are In, On site, Shop, WFH or Off.

## Admin

**You can:** everything below, plus the **IT page**: create permission groups and choose what each can read, write, approve and comment on; add or remove members; set labour rates per production stage; check the search engine's health; upload staff photos.

**Day to day:**
- Add a new person to the right group (IT page → group → *Add*). A member can be limited to one project.
- Change a group's grants and press **Save grants**. The page asks "Discard unsaved grant changes?" if you switch groups with unsaved changes.
- **View as role** (below the groups): pick a role to see, read only, what its group allows right now (every module and read/write/approve/comment) and which tabs that role sees. It does not log you in as that role, and it shows grants only, not rules such as "you cannot approve your own upload".
- Everything a manager can do (below).

## Manager

**You can:** nearly everything, except edit permission groups (you can only view the IT page).

**Things only you and admins do:**
- **Hard-lock** an item (stops all edits for everyone, including the person who owns it) and unlock it.
- **Restore** deleted items from Tracking's **Deleted** chip.
- **Close out** a project (project page → *Close out*).
- See a project's **Budget** tab on Tracking → Info, and the cost-centre money figures.
- Decide orders (*Approved* / *Rejected* / cancel), as purchase officers do.
- Approve shop drawings and samples; accept, reject, withdraw or expire a quote.

## Drafter

You are the main data-entry person: the item editor is yours.

**Daily tasks:**
1. **Tracking** → pick a project → **+ New item**, or tick one row and press **Edit item**.
2. In the item editor, choose the **Area** and **Room** (the last option of each list adds a new one in a small dialog), then work through the tabs: **Cutlist** (add modules and parts, or **Import from CV** to paste or upload Cabinet Vision output and resolve unknown codes), **Hardware** (add from the project's catalog, or **+ Add from global**), **Attachments** (five fixed slots and the Document Register), **Query** (ask or answer questions), **Material Take** (generate, edit, approve).
3. **Set status** with a note, or **Mark REQ done today**, from the **Actions** tab or by clicking the status pill on Tracking.
4. **Shop Dwgs**: upload a drawing, submit it for review, upload new revisions. **iSample**: create and edit samples.
5. **Cut Floor**: optimise parts onto sheets, save a plan and schedule it.
6. **Orderbook**: add orders (they start as *Pending*).

**You cannot:** decide an order (Approved / Rejected / cancel) — that is the purchase officer, manager or admin; change anything on Shop Floor (you can read it and comment); or approve your own uploads (you can approve other people's shop drawings and samples).

## Editor

Like a drafter for Tracking, List, Shop Dwgs, iSample, Cut Floor, Shop Floor and QC, and you can edit the Catalog. You can read the Orderbook but not change it, and you can only read Estimating. Item-editing tools that require a drafter (modules, parts, hardware lines, attachments, queries) are for drafters, managers and admins, so some editor controls may be read-only.

## Estimator

You own **Estimating** and **Customers**.

**Daily tasks:**
1. **+ New estimate** for a customer; add quote lines (**+ Add line**) with materials, hardware and labour.
2. Move a quote forward with the main button (**Advance**). At the step that sends it, the button says **Lock & send** and the quote is frozen. **Revise (new draft)** makes the next version.
3. When won: **Accept**, then **Convert to project** (choose which lines) and **Generate orders** to create draft purchase orders grouped by supplier. If a line was bought by hand, mark it **Ordered by hand** with a note.
4. If it is lost: **Reject** (reason), **Withdraw** or **Expire**.

You can read the other tabs and comment, but not change them.

## Purchase officer

You own the **Orderbook**.

**Daily tasks:**
1. The **bell** lists orders waiting for a decision; click one to open it.
2. Open an order → set **Approved**, or **Reject order** (a note is required), or **Cancel order** (give a reason).
3. Tick several open orders from the *same supplier* → **Po** to put them on one purchase order. Then use the PO window: **Add Delivery** (delivery fee), tick **Invoiced** to enter invoices, **Authorisation Form** → **Create Form**, **Print**, **Email Details** (attach the PDF yourself).
4. Use the filters **RTO** (approved, not ordered yet), **TBO** (still to be ordered), **Due**, **Over Due**, **Arrived** and **My Orders**.
5. Keep the lists: **Supplier** (companies, contacts, logos), **Cost centre** (**Edit**), the **Glass C** price list and the **payment methods**.

**You cannot:** edit items, drawings or cutting plans; you can read most other tabs and comment on Tracking.

## Viewer

Read-only everywhere (except the IT page, which you cannot open). You can look at every tab, search, and use the bell. You cannot create, change, approve or comment.

## Shop floor workers

Workers (staff an admin has marked as shop workers) use the **Shop Floor station** page, one per worker.

1. Your **active card** shows the stage you are on (for example Down, CNC, Edged, Painted, Made, Packing).
2. Press **Start <stage>** to begin and **Mark <stage> done** when finished; add a note if needed. You cannot skip an earlier stage; the screen tells you what to finish first.
3. Made a mistake? **Undo** appears for a few minutes after a completion.
4. **Packing** can use the camera to scan an item's QR label, or you can type the item number and press **Confirm**.

A supervisor assigns work on the **Shop Floor** board (**+ Assign worker** on a card).

## Locks in plain words

- **Hard lock**: a manager or admin froze the item. Nobody can edit it until it is unlocked.
- **Approved**: once an item's status is APPROVED, its design content (modules, parts, hardware, attachments) is frozen. You can still change status and add comments.
- **Controlled lock** (the **Lock** button at the bottom of the item): the person who locked it, and managers and admins, can still edit. Others' edits to the item header are held as a request. The owner, managers and admins are told in two places: a banner at the top of the item (with **Approve** and **Reject** and an optional note) and the bell ("Held saves waiting for your decision"). Approving applies the change and credits the person who proposed it; rejecting leaves the item as it was.

## Things that look like they should work but do not (yet)

- **Continue with SSO** on the login page does nothing yet.
- **Update Status To All** in a row's status pop-up is disabled. Use **Apply status…** on the grid after ticking the rows you want (up to 500).
- Project Information tabs **Cars**, **OH&S** and **Scope** are greyed out; they are not built.

## Who to ask

If a screen does not show what this guide says, check your role with an admin first (the IT page shows your group), then check whether the item is locked or the order is already Cancelled or Delivered (those are read-only except for their status).

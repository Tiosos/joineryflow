# Comments

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## Comments, mentions and notifications (Plan V1 §29, Q473 / Q521 / Q523) — shipped

> Chosen by the user as the next sub-project after the Purchase order status
> guard ("Go with Comments (§29)"). §29 was under-specified in three ways, so
> the user was asked before any code was written — the three answers below are
> **settled decisions**, not assumptions. No spec or plan doc; this section is
> its written record. Q473 (build §29, so `comment` stops being a dead grant),
> Q521 (notifications: in-app only) and Q523 (mentions ship with comments)
> were already confirmed.

- **Settled scope (user).**
  1. **Four object types, not eight** (*since six — Module and shop-drawing
     revision were added by `0043`, see the section below; Task and Change are
     still not built*). §29 names Project, Area, Room, Joinery
     Item, Component, Task, Change and Revision. **Task and Change are not
     entities in this tree** (Q524 decided a `task` table, nobody built it;
     §11's change engine is unbuilt), and **Component / Revision are
     ambiguous** (module or part? shop-drawing or estimate revision?). v1
     covers **Project, Area, Room and Joinery Item** — the four that exist.
     The other four get a thread when their entity does; adding one is a new
     nullable FK column + an `object_type` branch, not a redesign.
  2. **Comments, one-level replies and @mentions.** Attachments / photos,
     decision marking, "internal notes" and company / team / department
     discussion areas are **not built** (§29 lists them; a channel entity +
     membership is a materially bigger build).
  3. **A minimal in-app inbox** behind the mentions — not §30's
     Event → Recipient → Channel rules engine: no preferences, grouping,
     acknowledgement, escalation, email or push.
- **Migration `0042`.**
  - `comment` — the object is **four nullable real FKs** (`project_id`,
    `area_id`, `room_id`, `item_id`) with `CHECK num_nonnulls(...) = 1`, not a
    polymorphic `(object_type, object_id)` pair: deleting an item / area /
    room / project takes its thread with it (`ON DELETE CASCADE`) instead of
    leaving dangling comments, and `object_type` is a **generated column**, so
    there is no second source of truth. `workspace_id` is a direct column
    (the Q555 pattern — a comment spans four parents with no single join
    path), set from the resolved object.
  - **Replies are one level deep, enforced by the database**, the way `0028`
    enforces Q449: `parent_is_reply` is always false when a parent is set, so
    the composite FK `(parent_comment_id, parent_is_reply) → comment
    (comment_id, is_reply)` can only be satisfied by a top-level comment.
    Which object a reply belongs to is **inherited from its parent by the
    application** — a reply request names only `parent_id`, never an object,
    so the two cannot disagree (the DB cannot express that check across four
    nullable columns; `MATCH SIMPLE` skips a FK with any NULL column).
  - `comment_mention (comment_id, user_id)` and `notification` (recipient,
    actor, `kind IN ('mention','reply')`, `read_at`) with
    `UNIQUE (recipient_id, comment_id, kind)` — re-mentioning someone on edit
    cannot ping them twice. **Not searchable** (no `0033` trigger).
- **Backend — `apps/api/app/comments/` and `apps/api/app/notifications/`**,
  mounted at top-level paths.
  - `GET /comments?object_type=&object_id=` (`tracking:read`),
    `POST /comments` (`tracking:comment`), `PATCH /comments/{cid}`,
    `DELETE /comments/{cid}`, and `GET /projects/{pid}/comment-counts`
    (`tracking:read`; live comments per area and per room of one project —
    deleted ones are not counted, an area or room with none is simply absent). **This is the first place the `comment` action
    is enforced** — the four original object types are governed by the
    `tracking` module (areas / rooms already gate on it); a Module and a
    revision are governed by `list` and `shop_dwgs` instead (*see below*). A viewer (read only) can read
    a thread and cannot post; editor, drafter, purchase officer, estimator,
    manager and admin can.
  - **Edit is author-only — even a manager cannot edit someone else's words**
    (`403 NOT_AUTHOR`). **Delete is the author, or a manager / admin**
    (`403 FORBIDDEN`), and is a **soft delete** (`409 ALREADY_DELETED` on a
    second). A deleted comment survives only as a blanked placeholder while a
    surviving reply hangs off it; a deleted reply, or a deleted top-level
    with no replies, disappears from the API. Replying to a deleted comment
    is `409 PARENT_DELETED`; a reply to a reply is `409 REPLY_TO_REPLY`.
    These per-object rules live in the query layer, not the matrix (Q472 is
    still not built).
  - **Joinery Items only** — a related part has no thread (404), the
    `item_documents` / `qc` precedent and §29's own wording.
  - **Mentions are ids, not parsed text.** The client sends
    `mentioned_user_ids`; the body's `@Name` is presentation. Each id must be
    an **active user of this workspace who can read what the thread links
    to** (checked against the Dynamic RBAC engine, workspace-wide) or the whole
    request is refused `422 BAD_MENTION` listing the ids and **nothing is
    written** — a notification linking someone to a record they cannot open is
    worse than refusing. "Can read" is `tracking:read` for a Project / Area /
    Room thread and **`tracking:read` + `list:read` for an Item thread**,
    because the notification opens the item editor and `GET /items/{id}` is
    gated on `list` (the engine lets an admin grant one without the other; every
    default role holds both). The same pair gates *reading and posting* to an
    item thread (`403` without `list:read`). At most **20** mentions per
    comment. Only *newly added* mentions are validated on an edit: one already
    on the comment must not block an unrelated typo fix because its owner has
    since lost access. A mention notifies the mentioned user (never yourself); a reply
    notifies the parent's author, **unless they were also mentioned** (the
    mention wins, one row) **and only if that author can still read the thread**
    — a reply is never refused over its recipient, it is just not sent to
    someone who could no longer open it. Editing replaces the mention set: a *newly added*
    mention is notified, a *removed* one keeps the notice already sent (they
    were told), and an unchanged edit is a no-op (no `edited_at`, no audit).
  - Notifications (`current_user` only, no RBAC row — like `/search`, it shows
    a person only what is addressed to them): `GET /notifications?unread_only=
    &limit=&offset=` (newest first, with `unread_count`),
    `POST /notifications/{nid}/read` (404 if it is not yours),
    `POST /notifications/read-all`. **Notifications whose comment was
    deleted are hidden and not counted** — a badge pointing at nothing would
    be a lie. **So are notifications the recipient can no longer read**: an
    excerpt is comment text, so without `tracking:read` the inbox is empty and
    without `list:read` item threads are left out (hidden, not deleted — they
    return if access is restored). Marking read is audited
    (`notification.read`, `notification.read_all`), **once per real change** —
    re-marking a read notification, or a read-all that marks none, writes
    nothing — so "every authenticated mutation is audited" holds without
    bending it. (A first draft skipped this on the project-favourites
    precedent; the review pointed at the stated rule.)
  - Creating a comment takes `FOR KEY SHARE` on its object's row, so a hard
    delete racing the INSERT waits instead of surfacing as a raw FK 500.
  - Every comment mutation writes `audit_log` (`comment.{create,edit,delete}`)
    and — on an item — `item_edit_log` in the same transaction, per the PM
    Workbench invariant (`_comment_create`, `comment.{id}`, `_comment_delete`).
    Bodies are stripped before the length check (1–5000): a whitespace-only
    body is a clean `422`, not a raw `ck_comment_body_len` violation (found by
    the test suite — the first pass validated length before stripping).
- **Web.**
  - `components/comments/CommentThread.tsx` (+ `MentionTextarea`,
    `mentions.ts`) — one component for any object type: post, one-level
    reply, edit own, delete (own, or manager / admin), with an `@` picker fed
    from `/workspace/team` (arrow keys / Enter / Escape; a full name with a
    space can be typed). Which members get notified is derived from the
    **final text** (`mentionedIds`, longest name first with each match
    consumed, so `@Ann Lee` does not also mention `Ann`), so deleting an
    inserted `@Name` un-mentions it; only names the API confirmed are
    highlighted in a stored body. Two members with the very same full name
    cannot be told apart by text — only the first is mentioned. Timestamps
    render in the viewer's own zone (`formatLocalTs`), not as sliced server
    time. `canComment` mirrors `tracking:comment`;
    the API enforces it regardless.
  - **Surfaces: the item editor's Comments tab
    (`/items/[id]?tab=comments`), a Comments card and an **Areas & Rooms card**
    on `/projects/[id]`.** Area and Room have no page of their own, so their
    threads live on the Areas & Rooms card
    (`ProjectAreasCommentsCard.tsx`, placed there by the user): the project's
    areas with their nested rooms, each with a comment-count badge, and the
    selected one's `CommentThread` beside the list. The selection lives in the
    URL (`?area=<id>` / `?room=<id>`) so it can be linked to, and that is
    exactly what a notification for an Area or Room comment deep-links to
    (`/projects/{pid}?area=…`). **A click sets local state and the URL
    together, synchronously** (`history.replaceState`, which Next 16 integrates
    with `useSearchParams` — per the bundled docs), and a URL change that did
    not come from a click — a notification followed *while already on this
    page*, or back/forward — is synced back into state. **A deep link scrolls the card
    into view** (it is the last card on the page, 1447px down against a 720px
    viewport); a click on a row does not. A link to an area or room that has
    since been deleted says so instead of showing nothing. Posting, replying,
    editing or deleting refreshes the badges (`CommentThread`'s `onMutated`;
    only the newest refresh may write, so two quick posts cannot leave a stale
    count). A project with no areas says areas are created from an item's Area
    picker. A room's notification label names its area (`R01 Kitchen (Level 1)`),
    because "R01" alone is ambiguous across areas.
  - **Found in review, worth remembering: a selection with a live input beside
    it must change synchronously.** Two earlier cuts were wrong in opposite
    ways. Deriving the selection purely from `useSearchParams()` with
    `router.replace` meant the URL — and so the thread — changed only after a
    server round trip; until then the *previous* thread's input was still on
    screen, a test typed into it, and the text was thrown away when the thread
    remounted (Playwright: "element was detached from the DOM"), and two quick
    clicks raced their landings. Holding the selection in state alone left a
    same-page notification link unable to switch the thread. It is now local
    state **plus** a synchronous `replaceState`, with a URL→state sync for
    changes that are not ours. The area/room roster is fetched once by the card
    and passed to each thread (`roster` prop) rather than once per remount, and
    is deliberately **not** cached in a module: that would outlive a logout and
    show the previous user's team to the next one. A link naming an area or room
    created since the page loaded triggers one refetch of the list before the
    card calls it deleted.
  - `NotificationBell` in the `TopBar` (unread badge, six most recent,
    mark-all-read; **polls once a minute and on window focus — there is no
    push channel, by Q521**) and a `/notifications` page (not a tab).
- **Seed.** `make seed` on ALF-001: three comments on the first joinery item
  (a drafter mentions the foreman, the foreman replies, a manager comments)
  and one project comment mentioning the drafter — through the same query
  functions the API uses — so Juno Okafor's bell starts at 1 and Noa
  Lindqvist's at 2. It also leaves one comment on that item's own area and one
  on its room (**no mentions**, so those bell counts are unchanged) so the
  Areas & Rooms card opens with badges. Idempotent (the demo item's, project's,
  areas' and rooms' threads are dropped first; notifications cascade).
- **RBAC — no matrix change.** `tracking:{read,comment}`, already granted.
- **Tests.** `test_comments.py` (46 cases): each object type round-trips;
  the `comment` action is enforced; body trim / bounds; related part 404;
  workspace isolation on every verb; replies inherit the object, refuse
  reply-to-reply, and the DB itself rejects reply-to-reply, two objects and
  none; deleting the object takes its thread; mention / reply notification
  rules (self-silent, mention beats reply, unique on edit, only new mentions
  notified); bad mentions (foreign, inactive, unknown, and a user whose only
  group grants nothing on `tracking`) refused whole with nothing written;
  author-only edit, author-or-manager delete, deleted-thread shapes, hidden
  notifications; inbox read-state and ownership; audit + `item_edit_log`;
  and seven regression tests for the review fixes above (item threads need
  `list:read`, an unchanged mention never blocks an edit, no reply to a parent
  author who lost access, the inbox hides what is no longer readable, mark-read
  audited once, the FOR KEY SHARE lock, the 20-mention cap) — six were
  confirmed to **fail against the pre-fix code**; the cap test was tightened
  after it turned out to pass there for the wrong reason. Four more cover the
  Areas & Rooms work: counts are per area and per room (replies count; item
  and project threads do not), deleted comments are not counted, counts are
  scoped to one project, and the endpoint needs `tracking:read` and a project
  in this workspace; and the notification-link test now pins
  `/projects/{pid}?area=…` / `?room=…` (it used to assert an area had *no*
  link).
  `tests/e2e/comments.spec.ts` (6 tests) was run against a live migrated,
  seeded stack: a mention reaches the bell and opens the item's Comments tab
  with the mention highlighted and the reply nested; the `@` picker, edit,
  and a manager's delete; a viewer sees the thread with no form; the Areas &
  Rooms card (badges, an area's and a room's thread, the room's badge
  following a post); a mention on an area's thread deep-linking the
  notification to that thread; the project page's thread. The migration
  downgrades and re-upgrades cleanly.
- **Known gaps, recorded rather than silently left.**
  - Task and Change have no thread at all (above); Component and Revision got
    one in `0043` (as a Module and a shop-drawing revision — an estimate
    revision still has none).
    (Area / Room had no UI when Comments first shipped; the Areas & Rooms card
    closed that.)
  - The Areas & Rooms card lives only on `/projects/[id]`: an item's editor
    does not link to its own area's or room's thread. It is one click away, not
    inline.
  - `GET /projects/{pid}/comment-counts` and every `/comments` route check
    **workspace-wide** `tracking` grants, while `GET /projects/{pid}/areas`
    honours a project-scoped membership (`project_param`). A user whose only
    `tracking:read` is project-scoped therefore sees the area list but gets 403
    for counts and threads (the badges silently vanish; the thread shows the
    error). The same ceiling mentions and Global Search already document;
    passing `project_param` on the comment routes needs the object's project
    resolved before the permission check, so it is a design change, not a
    one-liner.
  - A mention of a user who is later deactivated is left in the stored body;
    editing the comment drops that mention (the roster no longer lists them).
  - `_readers` asks the RBAC engine once per mentioned user (one or two
    queries each), which is why mentions are capped at 20; resolving a whole
    id set in one query would mean re-implementing the engine's
    membership-fallback rule beside it (the same call Global Search made).
  - The bell's poll is a plain interval: a comment made in another window
    shows up within a minute, not instantly.
  - Who may be mentioned is decided from workspace-wide grants only — a user
    whose only `tracking` access is a project-scoped membership cannot be
    mentioned, the same ceiling Global Search documents.
- **Out of scope (deferred):** Task and Change threads (Component and Revision
  were built by `0043`); attachments /
  photos, decisions, internal notes and discussion areas; §30's rules engine,
  preferences, email / push, grouping and escalation; search over comments;
  a comment count on the Tracking grid.

## Deferred options (recorded, not built)

Three alternatives were proposed alongside Purchase Order editing (above)
when this session was asked to suggest the next sub-project; the user chose
PO editing and asked that the other three be recorded rather than dropped
silently. **B (Comments), C (QC Dashboard) and D (Search RBAC sync) have all
since been built.**

- ~~**Option B — Comments (Plan V1 §29, Q473).**~~ **Built — see *Comments,
  mentions and notifications* above.** Kept for history: a generic comment/mention
  system over 8 object types, the feature that would finally give the
  `comment` RBAC action (present on every module in the matrix since
  Foundation) something real to gate — today it is a dead grant everywhere
  except `isample`/`shop_drawings`-style review notes, which are bespoke
  fields, not this. Sized larger than PO editing: a new entity, @mentions,
  and a decision on which 8 object types get a comment thread first.
  Already named once as deferred, in *Dynamic RBAC engine* above (Q473).
- ~~**Option C — QC Dashboard (Plan V1 §4.2).**~~ **Built — see *QC
  Dashboard* below.** Kept for history: the standalone cross-project
  dashboard the *QC / Rework / Packing* section above explicitly named as
  out of scope when that sub-project shipped the per-item QC surfaces
  (defects/checklist/rework tabs, PACKING stage) that would back it. This
  ships only the aggregation view on top of data that already exists —
  lower schema risk than B, but needs a design decision on what it
  aggregates across (open defects by project? by supplier? by stage?)
  that Plan V1 doesn't spell out.
- ~~**Option D — Sync Global Search's RBAC check to the Dynamic RBAC
  engine.**~~ **Built — see *Global Search RBAC sync* below.** B and C
  remain unstarted.

## Comment threads on Modules and shop-drawing revisions (Plan V1 §29, migration `0043`) — shipped

> Chosen by the user ("Next task is comment threads for Task, Change, Component
> and Revision"). Two of the four had no entity and two were ambiguous, so the
> user was asked before any code was written; the four answers below are
> **settled decisions**, not assumptions. No spec or plan doc; this section is
> its written record. It extends *Comments, mentions and notifications* above,
> which records why v1 stopped at four object types.

- **Settled scope (user).**
  1. **Task and Change: skipped.** Neither is a table (grep of migrations
     `0001`–`0042` finds none; Q524 decided a `task` table nobody built, §11's
     change engine is unbuilt). Building either would mean inventing the entity,
     and Change has no defined shape outside that unbuilt engine. They get a
     thread when their entity exists — a nullable FK column + one `object_type`
     branch, as before.
  2. **Component = a Module** (`modules`, one level below a Joinery Item), not a
     Part. Parts number in the hundreds per item after a CV import and are rarely
     discussed one by one.
  3. **Revision = a shop-drawing revision** (`shop_drawing_revision`), not an
     estimate revision — §29's "approval discussions" and drawing references, and
     the approve / reject flow already exists to hang discussion on. An estimate
     revision has no thread.
  4. **Each type's own module governs its thread**, instead of `tracking` for
     all: a Module by `list`, a revision by `shop_dwgs`. See below — this is the
     one change that reaches back into the four original types' code.
- **Migration `0043`** — `comment.module_id` and `comment.revision_id`, both real
  FKs with `ON DELETE CASCADE`; `ck_comment_one_object` widened to exactly one of
  **six**; `object_type` regenerated (Postgres cannot alter a generation
  expression, so it is dropped and re-added — nothing depends on it, and
  `varchar(8)` still fits: `revision` is exactly 8). Downgrade deletes module /
  revision threads (they have no home in the `0042` shape) and restores it; the
  upgrade / downgrade / upgrade cycle was run on a database holding real rows.
  Not searchable (no `0033` trigger).
- **Per-type permissions** (`comments/queries.py`: `COMMENT_MODULE`,
  `READ_MODULES`). `comment` on the object's own module posts, edits and
  deletes; `read` on every module the thread links into reads it:

  | Type | `comment` | `read` |
  | --- | --- | --- |
  | project / area / room | `tracking` | `tracking` |
  | item | `tracking` | `tracking` + `list` |
  | **module** | **`list`** | **`list`** |
  | **revision** | **`shop_dwgs`** | **`shop_dwgs`** |

  The default roles differ from `tracking` in exactly the way that shows the gate
  works: `purchase_officer` holds `tracking:comment` but only `read` on `list` and
  `shop_dwgs`, so it can comment on an item and can read but not write a module
  or revision thread. Without this a user who cannot open a drawing could read
  the discussion about it — the leak class the item thread's `list:read` rule
  already exists to avoid. Mentions (`_readers`) and the inbox follow the same
  table, so a mention needs `read` on the object's own modules.
- **The routes no longer carry a fixed `require_permission("tracking", …)`.**
  Which module gates a comment depends on what it is a comment *on*, so the
  routes use `current_user` and check per type: `GET` and top-level `POST`
  know the type from the request; **`PATCH`, `DELETE` and a reply look the
  comment's type up first** (`queries.object_type_of`, workspace-scoped) and
  then check. Consequence: `PATCH`/`DELETE` on an unknown comment is now `404`
  for everyone, where a caller without `tracking:comment` used to get `403`
  first. The project comment-counts route is unchanged (`tracking:read`).
- **A reply now needs the read modules too — a tightening of existing
  behaviour, found while doing this.** A reply names no object, so the old route
  had no type to check and skipped the read check for it: a user holding
  `tracking:comment` but not `list:read` could reply to an item thread, although
  *Comments* above says the pair gates "reading and posting". The type now comes
  from the parent, so a reply to an item thread without `list:read` is `403`
  (pinned by `test_a_reply_on_an_item_thread_now_needs_list_read_too`). No
  default role is affected — every one holds both.
- **Joinery Items only, again.** A module of a related part has no thread (404):
  the thread's link opens the item editor. A revision has no such rule (a
  drawing belongs to a project, not an item).
- **Edit log.** A module comment writes `item_edit_log` against **the module's
  item** (`_comment_create`, `comment.{id}`, `_comment_delete`), per the PM
  Workbench invariant; a revision belongs to no item and writes `audit_log`
  only (`comment.*`, target `module:{id}` / `revision:{id}`).
- **Notifications.** `notifications/routes.py` now decides visibility **per
  object type** from `READ_MODULES` instead of "empty without `tracking:read`,
  item threads need `list:read`": a notification is shown while the recipient can
  read every module its thread links into. So a user holding `list:read` but no
  `tracking` at all now sees module notifications (before, the whole inbox was
  empty for them). `list_notifications` / `unread_count` take a `types` list in
  place of `include_items`. Links and labels:
  - module → `/items/{item_id}?tab=cutlist&module={module_id}`,
    label `M01 Base (#297871)`;
  - revision → `/shop-dwgs?project={pid}&drawing={did}&rev={rid}&comments=1`,
    label `Vanity plan · v1`.
- **Web.**
  - **Module** — the item editor's Cutlist tab shows the active module's thread
    under its parts (`data-testid="module-comments"`). The selection is now
    `?module=<id>` — a click sets state and the URL together, synchronously
    (`history.replaceState`), and a URL change that is not from a click (a
    notification followed while already on the page) is synced back into state,
    the same reasoning the Areas & Rooms card documents. **Fixed later: `+ Add
    module` was broken by this.** `ModuleTree` adds a module, calls
    `router.refresh()` and selects it in the same tick; `selectModule`'s
    `history.replaceState` then raced that refresh and the refreshed module list
    never arrived — the tab kept saying "Add a module to start the cutlist" (the
    API had returned 201; a manual reload showed the module). It shipped in the
    module-threads change unnoticed because nothing exercised adding a module.
    `selectModule` now leaves the URL alone for an id not yet in the item's list.
    Pinned by `cv_replace_comments.spec.ts`'s "adding a module shows it, selected,
    with its comment thread" — **confirmed to fail without the guard** (1 module
    where 2 are expected) and to pass with it.
    `EditorTabs` gained a `canCommentOnModule` prop (`list:comment`) beside
    `canComment` (`tracking:comment`, the item thread's).
  - **Revision** — `DrawingDrawer` gets a **collapsible** "Comments on vN" panel
    for the selected revision (`data-testid="revision-comments"`), collapsed by
    default so it never squeezes the PDF viewer; `?comments=1` (what the
    notification link carries) opens it on arrival. The drawer used to read
    `?rev=` only as its *initial* state, so a notification for another revision
    followed while the drawer was already open was ignored; it now follows the
    URL. `canComment` is `can(me, "shop_dwgs", "comment")`.
  - `CommentObjectType` / `NotificationOut.object_type` widened in
    `lib/comments-types.ts`. `NotificationBell` and `/notifications` needed no
    change: they render `url` and `object_label`.
- **Seed.** ALF-001's first item's first module gets a foreman comment, and the
  project's first non-archived shop-drawing revision (pending preferred) a
  manager comment — **no mentions**, so the seeded bell counts (Juno 1, Noa 2) are
  unchanged. Both are looked up rather than assumed, and dropped first so a
  re-run does not stack them (verified: two runs, one comment each).
- **RBAC — no matrix change.** `list:comment` and `shop_dwgs:comment` were
  already granted.
- **Tests.** `test_comments_module_revision.py` (29): both new types round-trip
  with replies; threads stay per-object across all six; the DB holds exactly one
  object and regenerates `object_type`; a related part's module has no thread;
  workspace isolation on every verb; cascade on module / revision delete; the
  `FOR KEY SHARE` lock for both; the default roles (purchase_officer, viewer,
  editor); a group with **only** `list` (or only `shop_dwgs`) can read and post,
  while **`tracking` alone cannot reach the thread**; `comment` without `read` is
  refused; edit and delete follow the comment's own module; replies gated on the
  parent's module (and the item-reply tightening); mentions need read on the
  object's modules; both notification links and labels; the inbox following each
  type's modules including "no `tracking` at all"; audit + edit log. **Eight of
  them were confirmed to fail** with `comments/routes.py` reverted to the fixed
  `tracking` gate (the other 21 pass there — the schema, queries and
  notifications are unchanged in that run — so they are controls, not gate
  tests). The 46 existing `test_comments.py` cases pass **unchanged** on the
  refactored routes. `tests/e2e/comments_module_revision.spec.ts` (4) was run
  against a live migrated, seeded stack: a drafter's module comment mentioning a
  manager and the manager's bell opening that module; a viewer reading but not
  posting to a module thread; a manager's revision comment mentioning a drafter
  and the drafter's bell opening the drawer with the panel expanded; a viewer
  reading but not posting to a revision thread. A same-page follow (notification
  for the item's *second* module while its first was selected) was checked
  separately and works with no reload; it is not a permanent spec because it
  needs an item with two modules, which only the seed's "SS Bench" has.
- **Known gaps, recorded.**
  - **Deleting a module deletes its thread — and a CV re-import with
    `?mode=replace` deletes the threads on every module of the item.** Both
    remove modules by `DELETE` (`parts/queries.py`, `cv/queries.py`; see the CV
    Import section), and a comment cascades with the module it is on. That follows from
    the user's choice of Module as Component with the cascade the migration
    documents — SET NULL would violate the exactly-one CHECK — but nothing warns
    about it: `cv.import.replace_wipe`'s audit payload lists the deleted module
    ids and not how many comments went with them. **CV re-import is now covered — see
    *Replace warns about the comments it deletes* in the CV Import section**: the
    wizard warns, and the count is on the commit response and both audit rows.
    **Deleting a single module is now covered too — see *Delete module asks
    first* below** (it also gained the UI control it never had).
  - ~~**No comment counts for modules or revisions.** The Areas & Rooms card has
    badges (`GET /projects/{pid}/comment-counts`); the module list and the
    revision history strip do not, so a thread is found by opening it (or by a
    mention). One count endpoint per parent would close it.~~ **Closed — see
    *Comment counts on modules and revisions* below** (by embedding the counts in
    payloads the screens already fetch, not by adding count endpoints).
  - **A module's thread is not shown on the Hardware or other item tabs**, only
    on Cutlist, and a revision's only in the drawer.
  - The same workspace-wide-grants ceiling as the other comment routes: a
    project-scoped `list` / `shop_dwgs` membership is not consulted.
  - An **estimate** revision still has no thread, and Component means Module, not
    Part — both are the user's settled scope, not oversights.
- **Out of scope (deferred):** Task and Change threads; Part and estimate-revision
  threads; ~~counts / badges on the module list and revision strip~~ (**built, see *Comment counts on modules and revisions***); everything the
  *Comments* section already defers (attachments, decisions, internal notes,
  discussion areas, §30's rules engine).

## Delete module asks first (Plan V1 §29 follow-up, no migration) — shipped

> Chosen by the user ("Next task is a warning before deleting a single module").
> It closed the last gap *Replace warns about the comments it deletes* left open,
> but the request assumed something that was not true: **there was no way to
> delete a module from the UI.** `DELETE /modules/{mid}` existed, `PM.deleteModule`
> was defined in `pm-fetch.ts`, and nothing called it (`ModuleTree` has no delete
> control). A warning needs something to warn before, so the user was asked before
> any code was written; the three answers below are **settled decisions**, not
> assumptions. No migration, no spec or plan doc; this section is its record.

- **Settled decisions (user).**
  1. **Scope: add a Delete module control and a confirm dialog** — the first way
     to delete a module from the UI, so this is a new capability, not only a
     warning.
  2. **Advisory only, not enforced by the API** — the same call as the CV
     re-import warning. `DELETE /modules/{mid}` keeps deleting exactly as before;
     the dialog is the safeguard.
  3. **The dialog names parts and comments**, not comments alone.
- **Backend — `apps/api/app/parts/`.**
  - `GET /modules/{mid}/delete-impact` → `{parts, live_comments}`. Read-only, gated
    `require_drafter()` — **the delete's own gate** (drafter / manager / admin) —
    and workspace-scoped through `_item_id_for_module` (Joinery Items only; another
    workspace's module and an unknown id are both 404). Declared beside the other
    `/modules/{mid}` routes; no path collides (`PATCH /modules/{mid}` and
    `POST /modules/{mid}/parts` differ by method / suffix).
  - **What is counted.** `parts` = part **rows** (the number a person sees in the
    grid), not the sum of their `qty`. `live_comments` = comments on the module
    with `deleted_at IS NULL`, **replies included** — the same rule as the CV
    replace warning. The cascade also removes soft-deleted rows, so the true row
    count can be higher.
  - **The count is recorded, not returned.** `delete_module` counts *before* the
    DELETE and writes `deleted_parts` and `deleted_comment_count` into the
    `module.delete` audit payload. The route still answers **`204` with no
    body**: changing it to `200` would change what existing API callers see, and
    the user chose "advisory, existing callers keep working". (The option offered
    to the user said the count would also be "returned"; that half was
    deliberately **not** done, for the reason above.)
- **Web — `cutlist/DeleteModuleDialog.tsx` + `CutlistTab.tsx`.** A **Delete
  module** button in a header row above the active module's parts grid
  (`data-testid="delete-module"`), shown to drafter / manager / admin only — the
  web mirrors `require_drafter`, the API decides. It opens a confirm dialog that
  reads `delete-impact` **fresh when it opens**: "This permanently deletes the
  module and its **3 parts** and **3 comments**. It can't be undone.", or "This
  module is empty." when both are 0. If the lookup fails it says "Couldn't check
  what this module contains…" instead of implying the module is empty. The
  Delete button stays disabled until the numbers (or the failure) are on screen,
  so the person always sees them first; Cancel and Escape close it. A `404` on
  delete (already gone elsewhere) counts as success.
  - **After a delete the tab refreshes and selects a neighbour in state — and
    deliberately leaves the URL alone.** `router.refresh()` followed by
    `history.replaceState` is the race that broke `+ Add module` (see *Comment
    threads on Modules…*); a stale `?module=<deleted id>` is harmless because
    `moduleFrom` only accepts ids still in the item. Deleting the last module
    returns to the empty state.
- **Tests.** Four new in `test_parts_routes.py`: the impact counts the module's
  parts and live comments only (replies counted, a soft-deleted comment and a
  sibling module's comment not); an empty module reads 0/0; the gate (editor and
  viewer 403, another workspace and an unknown id 404); and the delete writes the
  counts to the audit row, still answers 204 and cascades — **all four fail
  against the unfixed source** (the six existing parts tests pass as controls).
  `tests/e2e/module_delete.spec.ts` (4; 7 since the lock checks), run twice back to back against a live
  migrated, seeded stack: the full add → comment → warning → Cancel → Delete cycle
  on `JO-TP01` on a module the spec creates (so nothing seeded is deleted); the
  parts count on a seeded module (Cancel only); the lookup-failed message via a
  route intercept; and editor / viewer are not offered the button.
- **Known gaps, recorded.**
  - ~~A module can still be deleted on an item that is Hard-Locked,
    Approval-Locked or Controlled-Locked.~~ **Closed — see *Lock checks on module
    delete* below.**
  - The count is live comments only (above); an API caller who skips the
    lookup gets no warning at all — by the user's choice.
  - No undo: deletion is permanent, as it always was.
- **Out of scope (deferred):** enforcing an acknowledgement in the API; returning
  the counts in the DELETE response; a warning before deleting a **part** (a
  single row, nothing cascades from it).

## Comment counts on modules and revisions (Plan V1 §29 follow-up, no migration) — shipped

> Chosen by the user ("go with the next recommendation task" — the first gap *Comment threads on
> Modules and shop-drawing revisions* recorded: "no comment counts for modules or revisions"). Two
> things were open, each asked before any code was written; the answers are **settled decisions**,
> not assumptions: **embed `comment_count` in payloads the screens already fetch** (over new
> count endpoints like `GET /projects/{pid}/comment-counts`), and **badges on the module list and on
> both revision lists** (the details panel's Revisions tab and the viewer's versions list).

- **What a count is.** The thread's **live** comments — `deleted_at IS NULL`, **replies included** —
  the rule the Areas & Rooms badges and the register's per-drawing count already follow. So a deleted
  parent that survives only as a blanked placeholder (because a live reply hangs off it) is **not**
  counted, and a top-level comment deleted with no replies simply drops out.
- **Backend (no new route, no migration).**
  - `ModuleOut.comment_count` (`items/schemas.py`, default 0) is filled by `GET /items/{id}`'s module
    query (a correlated `count(*)` on `comment.module_id`) **and** by `parts.queries.get_module`, the
    helper behind `POST /items/{id}/modules` and `PATCH /modules/{mid}` — so a patched module's
    response carries its true count, not a default zero. A new module reads 0.
  - `RevisionOut.comment_count` (`shop_drawings/schemas.py`, default 0) is filled by the one query
    that builds a drawing's revision list, which every route returning a `DrawingDetailOut` shares
    (`GET`, the `PATCH`, the create and the add-revision routes), so none can answer a stale zero.
  - **Gating needed no change:** each count rides a route whose read rule already equals its thread's —
    `list:read` for `GET /items/{id}` (a module thread needs `list:read`) and `shop_dwgs:read` for
    `GET /shop-drawings/{id}` (a revision thread needs `shop_dwgs:read`) — so a count is never served
    to someone who could not open the thread. Counts are workspace-scoped through the same item /
    drawing lookups, and a related part's modules never reach this code (404, as before).
- **Web.** `components/comments/CommentBadge.tsx` — the "💬 N" chip (nothing at 0, `data-testid=
  "comment-badge"`), the same look as the Areas & Rooms card's own `CountBadge`, which was **left as it
  was** rather than migrated (it is a private copy in `ProjectAreasCommentsCard.tsx`; a later cleanup
  can point it at the shared one). Used by `ModuleTree` (each module row), `DetailsPanel`'s
  `RevisionList` and `DrawingViewer`'s Versions list. `ModuleOut` / `Revision` in
  `lib/pm-types.ts` / `lib/shop-drawings-types.ts` gained `comment_count: number`.
  **The badges follow a post, reply, edit or delete with no reload**, because each thread now tells its
  parent: the Cutlist tab's module thread calls `router.refresh()`; the details panel and the viewer
  call their own `refresh()` (each holds its own copy of the drawing detail) as well as
  `props.onChanged` (the register list). **Both hookups are load-bearing** — with either removed the
  badge stayed one behind (6 vs 7, 9 vs 10) and the e2e failed. `router.refresh()` here is safe against
  the `+ Add module` race recorded under *Comment threads on Modules…* because the module thread never
  touches the URL.
- **Seed.** Nothing new: the seed already leaves one comment on the first item's first module and one
  on an in-review revision, so a fresh `make seed` opens with a 💬 1 on each.
- **Tests.** `test_comment_counts_module_revision.py` (15): a module / revision with no comments reads 0;
  the count is its live thread with replies included; per module and per revision, not per item or per
  drawing; the item, project and the *other* kind of thread do not count; a deleted comment is not
  counted, and a deleted parent with a live reply counts only the reply; the module create / patch and
  the drawing PATCH responses carry the true count; a read-only role sees the same numbers; another
  workspace's comments never count. **All 15 fail against the unfixed source** (`comment_count` is
  absent from the payloads). `tests/e2e/comment_counts.spec.ts` (2), run against a live migrated, seeded
  stack and **re-run back to back**: the first module's badge shows the seed's 💬 1 and becomes baseline
  + 1 after a post from the screen; the latest revision's badge in the details panel, then in the
  viewer's Versions list, each following a post made there. Both fail without the web changes (no badge)
  and, separately, with the `onMutated` hookups removed (stale badge). The neighbouring
  `comments_module_revision`, `cv_replace_comments` and `shop_drawings` specs still pass (12). Like the
  other comment specs these add comments and leave the rows behind.
- **Known gaps, recorded.**
  - **The counts are loaded with the page, not pushed**: a comment another person makes shows up on the
    next page load or after you post, reply, edit or delete on that thread yourself — there is no poll
    (the bell polls; these badges do not).
  - **Only the module and revision lists carry a badge.** A module's thread is still shown only on the
    Cutlist tab, a revision's only in the details panel and viewer, and the Hardware / other item tabs and
    the register table's per-drawing count (all revisions summed, unchanged) are as they were.
  - The module count query runs once per module row of the item detail (a correlated subquery); an item
    has a handful of modules, so this is negligible, but a bulk "counts for N items" surface would want a
    grouped query instead.
- **Out of scope (deferred):** counts on the Tracking grid or the Cutlist module summary elsewhere; an
  unread / "new since you looked" marker; polling the counts; migrating the Areas & Rooms card onto
  `CommentBadge`.

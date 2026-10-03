# Rbac And Locks

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## Dynamic RBAC engine (Plan V1 §3.4, Q466–473) — shipped

> Built directly against the confirmed decisions in `docs/plan-v1/OPEN-QUESTIONS.md`
> §F, the same way #9a shipped without a spec or plan — there is no
> `docs/superpowers/{specs,plans}/` doc for this one; this section is its only
> written record.

Replaces the static `apps/api/app/auth/permissions.py` matrix as the *live*
source of truth for `require_permission`, with the DB-backed, project-scoped
engine Q466 confirmed — while keeping day one bit-for-bit
behaviour-preserving (Q468, Q435) and touching none of the ~181 existing
`require_permission(module, action)` call sites.

- **Migration `0037`** adds three tables: `permission_group` (workspace_id,
  name, is_system — direct `workspace_id` column, Q555's pattern, since a
  group has no other join path), `group_module_grant` (group_id, module,
  action), `user_group_membership` (user_id, group_id, `project_id` nullable
  — NULL means workspace-wide). A unique index on
  `(user_id, group_id, COALESCE(project_id, 0))` prevents duplicate
  workspace-wide memberships, since plain UNIQUE treats NULLs as distinct.
  **Backfill, in the same migration:** every workspace that already existed
  gets 7 system groups named after the 7 auth roles, with grants copied
  **verbatim from `MATRIX`** (188 rows, machine-generated from the live dict
  when the migration was authored, not hand-transcribed); every existing
  `app_user` gets a workspace-wide membership in the group matching their
  `auth_role`. Verified on a real Postgres 16 instance: grant counts per role
  (44/41/27/33/18/15/10 = 188) and one membership per seeded user, exactly
  matching `MATRIX`.
- **`apps/api/app/auth/rbac_engine.py`** — `effective_actions(db, user,
  module, project_id=None)` is the resolver: union of `group_module_grant`
  rows across every membership where `project_id IS NULL OR project_id =
  :pid`, most-permissive-wins across a user's groups (Q469). **`MATRIX` is
  the fallback**, not dead code — a user with **zero** memberships (any test
  file's raw-SQL `INSERT INTO app_user`, or a workspace created after `0037`
  ran — there is no "create workspace" route in v1) is governed by it
  exactly as before; a user with at least one membership is fully
  DB-governed, and an empty result for them is a real "no", never a
  fallback trigger. `seed_system_groups(db, workspace_id)` is the live,
  idempotent equivalent of the migration's one-time backfill — for a
  workspace created later, or for tests — not wired to any trigger,
  deliberately (see *Known gaps* below). `swap_default_group_membership(...)`
  moves a user's workspace-wide membership when their `auth_role` changes.
- **`require_permission(module, action, project_param=None)`**
  (`apps/api/app/auth/rbac.py`) is unchanged in effect for every existing
  call site: omitting `project_param` (all ~181 of them) checks
  workspace-wide grants only, which is exactly what the `0037` backfill gives
  every pre-existing user — verified by running the **full existing test
  suite (881 passed, 10 meili-skipped) with zero regressions**. Passing
  `project_param="pid"` (the path-parameter name holding a project id) makes
  the check *also* honour memberships scoped to that one project — a real
  behaviour difference, safe to add anywhere a project id is directly in the
  path, since no membership is project-scoped until an admin deliberately
  creates one. Wired onto `apps/api/app/areas/routes.py`'s two
  `/projects/{pid}/...` routes as a working demonstration (not a general
  rewire — see *Known gaps*). `apps/api/app/project_contracts/routes.py`
  (added by §I, migration `0038`) is the second adopter — its three
  `/projects/{pid}/contract...` / `/projects/{pid}/actual-costs` routes pass
  `project_param="pid"` from the day they were written, not retrofitted.
- **`PATCH /users/{uid}`** (`apps/api/app/users/routes.py`) now calls
  `swap_default_group_membership` when `auth_role` is in the patch, so a
  role change doesn't leave the old role's DB grants in effect under the new
  engine.
- **Admin CRUD API** — `apps/api/app/permission_groups/` (schemas / queries
  / routes), mounted at `/permission-groups`, gated `it_management` (read:
  admin+manager per the existing matrix row; write: admin only — the "IT
  configures access without a deploy" surface Q466 asked for):
  - `GET /permission-groups` — every group + its grants.
  - `POST /permission-groups` — create a group; 409 on a duplicate name,
    carrying the existing `group_id` (the areas/rooms 409-with-id pattern).
  - `PUT /permission-groups/{gid}/grants` — replace-all; 422 on an unknown
    module/action.
  - `DELETE /permission-groups/{gid}` — 409 `SYSTEM_GROUP` on one of the 7
    seeded groups, 409 `GROUP_HAS_MEMBERS` while it still has memberships.
  - `GET/POST /permission-groups/{gid}/memberships`,
    `DELETE /permission-groups/memberships/{mid}` — 422 `UNKNOWN_USER` /
    `UNKNOWN_PROJECT` for a foreign id, 409 `MEMBERSHIP_EXISTS` (carrying the
    existing `membership_id`) on a duplicate.
  - `GET /permission-groups/users/{uid}/memberships` — one user's
    memberships across all groups.
  - Every mutation writes `audit_log` (`permission_group.{create,
    set_grants,delete}`, `permission_group.membership.{create,delete}`).
- **Web — Groups panel on `/it` (shipped later, follow-up pass).**
  `PermissionGroupsPanel.tsx` (`apps/web/app/(app)/it/_components/`), a new
  `libs/permission-groups-{types,fetch}.ts` pair, and one new line in
  `it/page.tsx`. Sidebar list of all groups (name, `system` badge, grant
  count) + a detail pane: a 12-module × 4-action grants grid with dirty-state
  tracking (Save button only enables when changed, and switching groups or
  creating a new one while dirty prompts a discard confirm — the same
  `window.confirm` shape `removeGroup` already used), and a Members table
  (add/remove, workspace-wide vs. project-scoped). System groups hide the
  Delete button; deleting a group that still has members surfaces the
  backend's `409 GROUP_HAS_MEMBERS` inline. Verified end-to-end in a real
  browser against a live migrated stack (group create/select/delete,
  grants save, membership add, the two 409 paths) — this is the first
  sub-project in this file verified that way rather than by `tsc`/`next
  build`/pytest alone, per this session's UI-testing requirement.
  **Fixed along the way — `GET /users` / `PATCH /users/{uid}` 500'd for
  every real seeded user.** `UserOut.email` (`apps/api/app/users/schemas.py`)
  was `EmailStr`, a *response*-validation type, and `email-validator>=2.2`
  rejects `.test` as an RFC 2606 reserved TLD — so both routes broke against
  any `*.hartwood.test` address the moment a real browser (not the test
  suite's `@example.com` fixtures) exercised them. This was silently
  breaking the already-shipped `WorkerRosterPanel` (#8) too, not just the
  new membership picker here. Fixed to plain `str`, matching
  `auth/schemas.py`'s existing stance that email format is enforced upstream
  and an output field just echoes what's stored. Pinned by
  `test_admin_lists_users_with_reserved_tld_email`.
- **What Q466–473 answered but this build deliberately does not do:**
  - **Q472** (move hand-written per-object rules — `require_drafter()`, the
    not-uploader approve rule, creator-or-manager, the 5-minute undo window
    — into the engine as rules) is **not built**. They stay exactly where
    they are, in route handlers. A generic rule language is real design work
    Q472's own text flags as a cost, not a schema addition.
  - **Q470**'s critical actions (Lock, Unlock, Override, Configure) stay
    deliberately **outside** `group_module_grant` — they are not matrix
    actions, so most-permissive-wins never applies to them, and nothing here
    tries to express them as grants.
  - **Q473** (build §29 comments so the `comment` action stops being a dead
    grant) was **not built here — since built, see *Comments, mentions and
    notifications***. Originally: **not built** — a new entity, 8 object types and @mentions is
    a separate feature, not part of the permission engine itself.
  - **CLOSED — see *Global Search RBAC sync* below.** (Originally: `apps/api/app/search/routes.py`'s
    type-visibility check — the function is `readable_types`, not the
    `visible_types()` this bullet first named — filtered on
    `has_permission(auth_role, ...)`, the static matrix, not this engine.
    Kept for history.) A user whose grants an admin customised
    via the new engine (e.g. revoked `list:read` from their group, or gave
    them a project-scoped-only grant) will not see that reflected in which
    search result *types* are visible to them. Search's own workspace/project
    filtering on the results themselves is unaffected.
  - The **181 existing endpoints were not rewired** to pass `project_param`.
    They are unaffected (workspace-wide checks, unchanged), but a project id
    already in most of their paths is not yet exploited — that is additive
    work for whichever surface needs it next, not a gap in the engine.
- **Tests:** `test_rbac_engine.py` (resolver: fallback, DB-override,
  `seed_system_groups` parity with `MATRIX`, project scoping,
  most-permissive-wins, the `patch_user` auth_role-change swap end-to-end,
  and the `project_param` HTTP-level proof) and
  `test_permission_groups_routes.py` (admin CRUD, access control, delete
  guards, membership validation) — 26 tests, all passing against a real
  migrated Postgres 16 instance; the pre-existing `test_rbac.py` /
  `test_rbac_drafter.py` / `test_permissions.py` / `test_shop_drawings_rbac.py`
  / `test_users_routes.py` / `test_area_room_routes.py` pass unchanged.
- **Known gaps, recorded rather than silently left:**
  - No automatic group provisioning for a workspace created through the API —
    there is no "create workspace" route in v1 today. **`make seed` is a
    real instance of this**, though: it creates the `hartwood-joinery`
    workspace *after* `0037`'s one-time backfill already ran, so without a
    fix the seeded workspace would ship with zero `permission_group`/
    `group_module_grant`/`user_group_membership` rows and `GET
    /permission-groups` would show nothing on a fresh `make up && make
    migrate && make seed`. Fixed: `seed/hartwood_joinery.py` now calls
    `seed_system_groups()` right after creating the workspace and gives
    every seeded user a workspace-wide membership matching their
    `auth_role`, mirroring `0037`'s backfill exactly. `seed_system_groups()`
    is still ready to be called from a future "create workspace" route when
    one exists — this fix doesn't add one.
  - No web UI for the admin API — **closed, see above.**
  - Q472, Q470's rule layer, Q473's comments, and the broader project-scoped
    rewire of existing endpoints are open follow-ups, not oversights.

## Locking + Concurrency (Plan V1 §11–§12, Q508/Q511/Q512) — shipped

> Selected as the next sub-project after §M — it is the option §M's own
> "out of scope" note named as "the alternative this round didn't pick".
> Built directly against `docs/plan-v1/OPEN-QUESTIONS.md` §L's five
> confirmed answers, the same way #9a, the RBAC engine, §I and §M shipped:
> no separate spec or plan doc. This section is its only written record.

Closes out **Q566**'s list of what B7 (the Controlled Lock, migration
`0032`) left unbuilt: Q508's Hard and Approval lock types, and Q511/Q512's
field-level optimistic concurrency. Q509 (soft-lock → Controlled Lock) and
Q510 (item + project granularity, read as a ceiling) were already done —
see *PM Workbench* above.

- **Migration `0040`** — `items.hard_locked_at` / `hard_locked_by` (Hard
  Lock, Q508) and a `field_versions jsonb` column on each of `items`,
  `cutlist` and `purchase_orders` (Q511/Q512's three named surfaces).
  Approval Lock (also Q508) gets **no column**: "information automatically
  locks when approved" binds directly to the existing Status taxonomy's
  `APPROVED` value on `items.status` — there is nothing to store that isn't
  already there. **Q510 remains a ceiling, not a mandate**: no project-level
  lock column is added, for the same reason `0032`'s docstring already gave
  for the Controlled Lock — `projects` has no lock column of any kind, so a
  project lock would be new functionality with no owner or UI, not a
  conversion of something that exists.
- **Hard Lock (Q508 type 1) — item-scoped, `PATCH /items/{id}` only.**
  Unlike the Controlled Lock, there is no request-and-approve path around
  it: `POST /items/{id}/hard-lock` (manager/admin only, a manual
  `auth_role` check matching `claim_or_release_lock`'s transfer-permission
  pattern, not a new RBAC action) blocks the item for **everyone, including
  the current owner**, until the same authority clears it with `DELETE` on
  the same path. Scope matches the Controlled Lock's own documented
  boundary: `/status` and `/lifecycle/{stage_key}` did not consult either
  lock when this shipped (**the Hard Lock now stops them too — see *Lock checks on
  status and lifecycle***). Audited as `item.hard_lock` / `item.hard_unlock`.
- **Approval Lock (Q508 type 3) — derived, not stored.** Setting
  `items.status` to `APPROVED` (via `PATCH /items/{id}/status` or
  `POST /items/bulk-status`) locks `PATCH /items/{id}` with
  `409 APPROVAL_LOCKED`; moving status away from `APPROVED` unlocks it.
  Both directions are audited (`item.approval_lock` / `item.approval_unlock`)
  from inside `patch_item_status()`/`bulk_patch_item_status()`, even though
  there is no lock column for the event to name — Q516 requires every
  lock/unlock to be audited regardless of mechanism.
- **Field-level optimistic concurrency (Q511/Q512).** `apps/api/app/
  concurrency.py` holds the one shared implementation —
  `check_field_conflicts()` / `bump_field_versions()` — used identically by
  `items/queries.py::patch_item()`, `cutlists/queries.py::patch_cutlist()`
  and `orders/queries.py::patch_order()`. A PATCH may carry
  `expected_versions: {field: version}`, read from a prior GET's own
  `field_versions`; a named field whose stored version has moved on is a
  **409 FIELD_CONFLICT** naming just that field (with its `current_value`),
  not the whole record — Q366's "lock only the fields genuinely in
  conflict," now actually buildable. **Omitting `expected_versions` (every
  pre-existing caller, and any field not being changed) keeps
  last-write-wins for that field** — this is additive, verified by running
  every existing test in `test_lock_semantics.py`, `test_order_routes.py`
  and the cutlist suite unchanged and green.
  - **Checked only on the direct-apply path for items.** When the item is
    Controlled-Locked by someone else, nothing is written by that PATCH — it
    becomes a pending request instead (see *PM Workbench* above) — so there
    is no concurrent-write race for versioning to catch; the Controlled Lock
    already serialises that case through its own approve/reject flow. A
    version bump also happens when a held request is later approved, so a
    GET taken after approval reflects the field's new version correctly —
    and that approval path re-checks Hard Lock / Approval Lock too (see
    *Fixed later* below), since the requester's proposal predates either.
  - **`cutlist` has one patchable field** (`name`), so its conflict surface
    is trivial by construction — Q442 already made `cutlist_no` and
    `created_by` immutable.
  - **`purchase_orders`** reuses the module's existing `_PATCHABLE` set;
    every field in it is versioned, not a hand-picked subset.
- **Fixed later (max-level code review, same day).** The first pass's
  read-then-write field-version check had no row lock on any of the three
  surfaces: `patch_item`/`patch_cutlist`/`patch_order` all read the current
  row with a plain `SELECT`, so two concurrent PATCHes on the same field
  could both pass `check_field_conflicts()` against the same stale read and
  the second's write would silently clobber the first's — exactly the
  "nothing is silently overwritten" guarantee this feature exists to
  provide, undone by its own race. `_item_row` / `_cutlist_row` / `get_order`
  now take `for_update: bool = False`; the three `patch_*` functions pass
  `for_update=True` for their initial read (every other, read-only caller is
  unaffected), the same `SELECT ... FOR UPDATE` shape `_lock_order_for_update`
  / `lock_revision_for_update` already use elsewhere in this codebase.
  Pinned by `test_concurrent_patch_serializes_field_version_check_instead_of_lost_update`
  (two real DB sessions on separate threads), confirmed to fail against the
  pre-fix code. Three smaller findings from the same review: `decide_lock_request`'s
  approval path called `_apply_item_changes()` without ever checking Hard
  Lock or Approval Lock, so a request approved after either was set would
  slip through — both are now checked there too (`test_approving_a_lock_request_is_blocked_by_hard_lock`
  / `..._by_approval_lock`); `patch_cutlist`'s conflict branch hardcoded
  `conflicts["name"]`, raising an unhandled `KeyError`/500 if
  `expected_versions` ever named a different key — now generic like the
  items/orders versions (`test_cutlist_conflict_on_unrelated_expected_version_key_does_not_500`);
  and `ItemMetadataPanel.tsx`'s Area/Room save sent `expected_versions` for
  **both** `area_id` and `room_id` even though `AreaRoomPicker.onChange`
  only ever changes one of them, so a concurrent edit to the *other* field
  could wrongly reject an unrelated save — it now versions only the key
  actually present in the payload.
- **Web.** `ItemMetadataPanel.tsx`'s existing per-field PATCH calls now send
  `expected_versions` for the field being saved (and, for the Area/Room
  picker, for whichever of `area_id`/`room_id` that specific change actually
  touches — never both) and surface
  `FIELD_CONFLICT`/`HARD_LOCKED`/`APPROVAL_LOCKED` inline next to the field,
  alongside the existing `LOCK_REQUEST_CREATED` message — this is the same
  per-field error-banner mechanism, not a new one. `CutlistClient.tsx`'s
  rename prompt does the same for `name`. New `HardLockBanner.tsx`
  (manager/admin see a toggle; everyone else sees the banner while locked)
  and `ApprovalLockBanner.tsx` (informational only — unlocking is a status
  change on the Actions tab, not a button) sit above the metadata panel on
  `/items/[id]`. **`purchase_orders` has no PATCH-editing UI at all yet** —
  `orders-types.ts` carries `PatchOrderIn`/`field_versions` for whenever
  that surface is built, but nothing in this pass invents one.
- **Deliberately not seeded.** Every other sub-project's seed block leaves a
  demo row behind, but Hard Lock and Approval Lock each block **every**
  PATCH on the item they sit on — Hard Lock unconditionally, Approval Lock
  until status moves off `APPROVED` — and this repo's fixed e2e suite
  (`tests/e2e/`) PATCHes seeded ALF-001 items across several specs. Locking
  one of them in `make seed` risks breaking a spec this pass has no way to
  run and verify (Playwright needs a live browser + full stack). The
  feature is fully covered by `test_lock_types_concurrency.py` instead;
  don't add a seeded Hard/Approval lock without first confirming no e2e
  spec touches that item.
- **RBAC — no matrix change.** Hard Lock's manager/admin check is a manual
  `auth_role` check in `items/queries.py`, the same shape
  `claim_or_release_lock`'s transfer permission and `decide_lock_request`'s
  decider permission already use — not a new RBAC action, matching Q508's
  own silence on what should gate it.
- **Tests:** `test_lock_types_concurrency.py` (17 tests) — Hard Lock
  set/clear/block-everyone-including-owner/manager-only, Approval Lock
  auto-lock/unlock on status change, field-conflict 409s on all three
  surfaces with `current_value` in the response, correct-version saves
  succeeding and bumping again, a same-record-different-field save proving
  Q366's per-field (not per-record) conflict scope, plus the four review-fix
  regressions named above. Full suite (950 passed, 10 skipped, 1
  pre-existing unrelated failure — the same local-only `MEILI_URL` gap noted
  in *Tender Lifecycle + Financials* above) run against a real migrated
  Postgres 16 instance with zero regressions outside
  `test_lock_types_concurrency.py` itself.
- **Out of scope (deferred):** Q472's rule-engine migration of hand-written
  per-object rules (`require_drafter()`, the not-uploader approve rule,
  creator-or-manager, the 5-minute undo window) into the Dynamic RBAC
  engine — unaffected by this pass, still open from *Dynamic RBAC engine*
  above; extending Hard/Approval Lock or field-level concurrency to any
  surface beyond the three Q508/Q511 named (Q510 is a ceiling, not an
  invitation to widen); a PATCH-editing UI for orders (above); resolving a
  `FIELD_CONFLICT` by merging the two versions client-side (today's UI just
  tells the user to reload — a merge view is real design work Q366 doesn't
  ask for either).

## Global Search RBAC sync — shipped

> Chosen by the user from the four options proposed after the Orderbook
> editing UI (the recommended one: smallest, clearest "done"). Closes the
> gap *Dynamic RBAC engine* recorded as "flagged, not silently resolved".
> No migration, no spec or plan doc; this section is its written record.

- **What changed.** `apps/api/app/search/routes.py::readable_types(db, user)`
  (was `readable_types(auth_role)`) now asks the Dynamic RBAC engine
  (`rbac_engine.has_permission_db`) instead of the static `MATRIX`, so a
  group's grants — customised through the Permission Groups admin UI —
  decide which result **types** a member sees, in both directions: a
  revoked `orderbook:read` hides order/supplier results, and a custom group
  granting only `orderbook:read` hides item results even though the role's
  `MATRIX` row would show them. `GET /search` gained a `db` dependency to
  supply the session. Nothing else moved; the Meilisearch filter still
  always carries `workspace_id`, and unreadable types are still dropped
  silently, never 403'd.
- **Settled decision — workspace-wide grants only (`project_id=None`).**
  The option's own note flagged this as needing to be stated, not assumed.
  Search has no single project in scope (the `project_id` query param
  narrows *results*, it is not a permission scope), so a project-scoped
  membership is deliberately not consulted. **Consequence, recorded
  rather than hidden:** a user whose *only* memberships are project-scoped
  gets no result types at all — the engine treats "has any membership"
  as fully DB-governed and never falls back to `MATRIX`, and a
  project-scoped grant is invisible at workspace scope. Pinned by
  `test_project_scoped_only_membership_sees_no_types`. In practice this
  needs an admin to deliberately strip a user's workspace-wide group;
  Q466's model is project memberships *added to* a role group. If that
  becomes a real need, passing the request's `project_id` into the check
  when supplied is safe (the index filter already restricts to that
  project) — but an unfiltered search would still show nothing, so it is
  a design question, not a one-line fix.
- **Cost.** `readable_types` resolves each *distinct module* once (11 types
  map onto 7 modules) rather than once per type — it runs on every
  keystroke of the TopBar box, and each engine call is a query (two when
  the grant set is empty). A single all-grants query would be cheaper
  still; not done, since it would re-implement the engine's
  membership-fallback rule beside the engine.
- **Test infrastructure trap, recorded because it recurs.**
  `rbac_engine.py` does `from .permissions import MATRIX`, binding its own
  name. A test that swaps the fallback matrix must patch
  **`rbac_engine.MATRIX`**, not `permissions.MATRIX` — patching the latter
  replaces an attribute the engine never reads, and the test passes or
  fails for the wrong reason. `test_unreadable_type_is_dropped_silently`
  was patched this way; `_login()`'s raw-SQL users hold zero memberships,
  so they still exercise the fallback.
- **Tests:** three new in `test_search_routes.py` — revoking a system
  group's grant hides the type, a custom group governs in both directions
  (and `types=` cannot reach past it), and the project-scoped-only ceiling.
  Full suite green (985 passed, 10 skipped, the same pre-existing local
  `MEILI_URL` failure) before the last two tests were added; the search
  route module alone re-run green after (21 passed).
- **Was a known gap here: `/auth/me` served the static matrix.** **Closed — see
  *`/auth/me` follows the permission groups* below.**

## `/auth/me` follows the permission groups — shipped

> Chosen by the user ("Go with /auth/me permissions") from the gaps left open
> after the Areas & Rooms card — the one *Global Search RBAC sync* recorded as
> "its own decision". No migration, no spec or plan doc; this section is its
> written record.

- **What changed.** `GET /auth/me` served `permissions_for(user.auth_role)` —
  the static `MATRIX` row — while every `require_permission` check and (since
  the Search sync) Global Search already asked the Dynamic RBAC engine. So a
  user whose grants an admin customised through the Permission Groups panel saw
  the tab strip and every `can(me, …)` write affordance follow the *role*, not
  the *groups*: a revoked `orderbook:read` dropped the Orderbook results from
  search and still showed the Orderbook tab. `/auth/me` now serves
  `rbac_engine.effective_permissions(db, user)`, so the web tier follows the
  same grants the API enforces, in both directions.
- **`effective_permissions` is one grants query, not twelve.** `/auth/me` runs on
  every page load; calling `effective_actions` per module would cost 12–24
  queries. It reads the user's workspace-wide grants once and applies the
  engine's own fallback rule: a module with grants uses them; otherwise a user
  holding **any** membership gets `[]` (a real "no"), and a user holding **none**
  gets the `MATRIX` row (`permissions_for`). It deliberately re-states that
  rule beside the engine's rather than sharing it, so
  `test_effective_permissions_agrees_with_effective_actions` pins the two
  together across every branch — do not loosen it. Same response shape as
  before: every module present, actions sorted, `[]` meaning no access.
- **Settled decision — workspace-wide grants only.** The map carries no
  project, so a project-scoped membership is not represented in it (the same
  ceiling Global Search and the comment routes document, and what the ~181
  call sites without a `project_param` check anyway). Consequence: a user whose
  *only* memberships are project-scoped gets an all-empty map, and the tab
  strip hides everything for them, even though a route that passes
  `project_param` would let them in on that project. Pinned by
  `test_effective_permissions_project_scoped_only_membership_is_empty`. Serving
  per-project grants would mean a second payload keyed by project, which is a
  design change, not part of this.
- **`MATRIX` is still the fallback and `permissions_for` still exists** — the
  route no longer calls it directly, `effective_permissions` does, for a user
  with zero memberships (every test file's raw-SQL user). Nothing else changed:
  `require_permission`, the 181 call sites and the web `can()` are untouched.
- **Web.** No behavioural change to `TabStrip` / `can()`; only the comments in
  `lib/permissions.ts` that said "for this user's role". The tab-strip gate is
  now live in the sense the *Web shell* section anticipated: removing a module's
  `read` grant from a group hides that tab for its members.
- **Tests.** In `test_rbac_engine.py`: parity with `effective_actions` across
  zero memberships, a narrow group, a project-scoped membership, and
  most-permissive-wins; the project-scoped-only ceiling; parity with the seeded
  system group for every role in `MATRIX`; and an HTTP test that a grant
  revoked from a group disappears from `/auth/me` (confirmed to **fail against
  the old route**: `['read'] == []`). The existing
  `test_me_includes_permissions_matching_the_matrix` still passes unchanged —
  a zero-membership user falls back to the matrix, which is the point of the
  fallback. Verified live in a browser against a migrated, seeded stack: a
  seeded viewer's Orderbook tab and `me.orderbook` (`["read"]`) both went away
  after the grant was deleted from the viewer group, on reload.
- **Known gaps, recorded.**
  - ~~The web `Module` type in `lib/permissions.ts` lacked `"qc"`.~~ **Closed by
    the QC Dashboard**, whose tab is the first thing to call `can(me, "qc", …)`.
  - A permissions change takes effect on the user's **next page load** — there
    is no push channel, and `(app)/layout.tsx` fetches `me` per navigation.
  - Q472's per-object rules (`require_drafter()` etc.) are still hand-written
    in route handlers, so a group grant cannot express them and `can(me, …)`
    is a coarse gate for those surfaces, as it already was.

## Lock checks on module delete (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on module delete"). It closes the
> gap *Delete module asks first* recorded, and it is the **first place §L's locks
> reach beyond `PATCH /items/{id}`**. The request left three things open, so the
> user was asked before any code was written; the three answers below are
> **settled decisions**, not assumptions. No migration, no spec or plan doc; this
> section is its written record.

- **Settled decisions (user).**
  1. **Scope: module delete only.** `POST /items/{id}/modules`, `PATCH /modules/{mid}`,
     every part write, hardware lines and CV import (including its `replace` mode,
     which deletes every module of the item) **still never consult a lock** — the
     recommended option, kept narrow on purpose. See *Known gaps*.
  2. **Hard + Approval + Controlled.** A delete cannot be held as a Controlled-Lock
     request (`item_lock_request` stores a `PatchItemIn` body, which can only carry
     field edits), so it is **refused** instead. Otherwise a lock could be bypassed
     by deleting where it forbids editing.
  3. **UI: disable with the reason, plus a 409 fallback.**
- **The rule — `items.queries.assert_item_content_unlocked`.** Called by
  `parts.queries.delete_module` right after the workspace lookup and *before*
  anything is counted, audited or deleted; raises `ItemContentLocked`, which
  `delete_module_route` turns into `409 {detail: {code, …}}`:
  - **`HARD_LOCKED`** (`locked_by`) — everyone, including the owner and admins.
  - **`APPROVAL_LOCKED`** — `items.status = 'APPROVED'`.
  - **`ITEM_LOCKED`** (`owner_id`, `owner_name`) — `item_locked` with someone else
    as `cutlist_owner_id`. **The owner and managers/admins pass**, matching who can
    decide a lock request. `cutlist_owner_id` is *sticky* (survives Unlock), so it
    is `item_locked` that matters: an owner with no active lock never blocks.
  - `HARD_LOCKED` / `APPROVAL_LOCKED` use the same codes and bodies as
    `PATCH /items/{id}`; `ITEM_LOCKED` is new (the PATCH path answers a Controlled
    Lock with `LOCK_REQUEST_CREATED` instead). The lookup takes the item row
    `FOR UPDATE`, so a lock set concurrently is seen or waits for the delete's
    transaction. A refused delete writes **nothing**: no audit row, no edit log.
  - `delete_module` now takes the acting `AuthUser` (`actor=`) instead of
    `actor_id=`, because the Controlled-Lock exemption needs the role. Its only
    caller is the route.
  - `GET /modules/{mid}/delete-impact` is **not** gated by any lock (read-only; the
    dialog can still be opened by someone who will then be refused).
- **Web — `cutlist/moduleLock.ts`.** `moduleLockReason(item, userId, role)` mirrors
  the rule from data the page already holds (`hard_locked_at`, `status`,
  `item_locked`, `cutlist_owner_id`); when it returns a reason, the **Delete
  module** button is `disabled` with the reason as its `title` **and** as a line
  in a notice at the top of the tab (`data-testid="cutlist-locked"` since the
  follow-up below moved it there from under the header row — a tooltip alone is
  invisible on a disabled button). `lockMessage(code, detail)` holds the wording
  for a code, shared with the dialog: a `409` on the delete (a stale page that
  still offered the button) shows that message in the dialog and leaves it open,
  nothing deleted. The client check only decides what to show — the API refuses
  regardless. **The client message for `ITEM_LOCKED` cannot name the owner**
  (`ItemOut` carries `cutlist_owner_id` but no name); the server's 409 does.
- **Tests.** Four new in `test_parts_routes.py`: a Hard Lock refuses everyone (an
  admin included), leaves module / parts / comments untouched and writes no audit
  row, then passes once cleared; an Approval Lock likewise until status moves off
  `APPROVED`; a Controlled Lock refuses a non-owner (naming the owner), leaves the
  impact lookup open, and lets a manager and the owner through; a sticky owner
  with no active lock does not block. **The first three fail against the unfixed
  source** (the sticky-owner one passes there — it is the control). Three new in
  `tests/e2e/module_delete.spec.ts`, each restoring the item exactly as seeded:
  a Hard Lock disables the button for a manager, with the reason, and unlocking
  re-enables it; seeded `JO-K-103` (Controlled-Locked, drafter-owned) is open to a
  manager, and after ownership is transferred to the manager the drafter is
  disabled — then transferred back and enabled again; and a mocked `409
  ITEM_LOCKED` shows the owner's name in the dialog. **All three fail against the
  unfixed web code.** Also checked over real HTTP through the proxy: a Hard-Locked
  item's delete answers `409 HARD_LOCKED` and the module is still there.
- **Known gaps, recorded.**
  - ~~Every other write under a locked item is still open.~~ **Closed for module
    and part writes and CV import — see *Lock checks on the other module and part
    writes* below; hardware lines — see *Lock checks on hardware lines*.**
  - ~~`PATCH /items/{id}/status` and `/lifecycle/{stage_key}` still never consult the
    lock.~~ **Closed for the Hard and Controlled locks — see *Lock checks on status
    and lifecycle* below.**
  - A Controlled Lock is not held as a request for a delete: the person is told to
    ask the owner or a manager. There is no "request a delete" flow.
  - The role check for the Controlled-Lock exemption is a hand-written
    `auth_role in (manager, admin)`, like `decide_lock_request`'s — Q472 is still
    not built.
- **Out of scope (deferred):** a lock-request flow for a delete; naming the lock
  owner in the disabled-button text.

## Lock checks on the other module and part writes (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on the other module and part
> writes"). It extends *Lock checks on module delete* above. The request left the
> reach open, so the user was asked before any code was written; the two answers
> below are **settled decisions**, not assumptions. The rule itself is the one the
> delete already settled (Hard + Approval + Controlled, refused because none of these
> can be held as a `PatchItemIn` request) and was carried over, not re-asked. No
> migration, no spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **Reach: the five module / part routes, plus CV import commit.** The routes
     are `POST /items/{id}/modules`, `PATCH /modules/{mid}`, `POST /modules/{mid}/parts`,
     `PATCH /parts/{pid}` and `DELETE /parts/{pid}` (with `DELETE /modules/{mid}`
     already covered). CV import was added because it writes modules and parts and
     its `replace` mode **deletes modules — which sidestepped the delete lock**.
     **Hardware lines were offered and not chosen**, so they still never consult a
     lock.
  2. **UI: one notice + controls disabled**, not per-control tooltips or 409
     messages alone.
- **Backend.** `parts.queries.{create_module, patch_module, create_part, patch_part,
  delete_part}` now take the acting `AuthUser` (`actor=`, was `actor_id=`) and call
  `items.queries.assert_item_content_unlocked` right after resolving the item — before
  anything is written, audited or logged; each route turns `ItemContentLocked` into
  the same `409 {detail: {code, …}}` the delete uses. An unknown id is still 404 (the
  lookup runs first). **A refused write changes and logs nothing** (pinned by
  comparing module / part rows, `item_edit_log` and `audit_log` counts before and
  after). **CV commit** checks in the route after the run is validated
  (404 / `RUN_NOT_PENDING` first) and before anything else, so a refused commit
  **leaves the run `preview`** and the same run commits once the lock is gone.
  Preview, `replace-impact` and the delete-impact lookup are read-only or write only
  the run row and are not gated. One consequence worth knowing: **part edits on an
  APPROVED item are refused** until its status moves off Approved (the Approval Lock
  read as Q508 says — "information locks when approved").
- **Web.** `moduleLockReason` now decides for the whole Cutlist tab, and
  `lockFromError(e)` reads a `409` lock refusal from either error shape in use
  (`ApiError.body` in pm-fetch, the CV helper's `detail`). `CutlistTab` shows one
  notice at the top (`data-testid="cutlist-locked"`, drafter / manager / admin only —
  the roles that can write) and disables **+ Add module**, **+ Add row**, every part
  cell (including the Paint select), **part delete**, **Import from CV** and
  **Delete module**. A `409` from a stale page shows the server's reason and **reverts**
  the edit: a refused cell edit restores its value, a refused add adds no row, a
  refused delete brings the row back. `PaintSelect` gained a `key` on its value so
  the rollback actually resets it (it kept its local state before). The wizard shows
  the reason when its commit is refused.
- **Tests.** `test_parts_routes.py` (+22): all five routes × Hard and Approval Lock
  (refused for the owner and an admin alike, nothing changed or logged, then the
  same request succeeds once cleared); all five × Controlled Lock (a non-owner
  refused naming the owner; the owner and a manager pass); a sticky owner with no
  active lock and an unlocked item do not block; unknown ids stay 404.
  `test_cv_routes.py` (+8): first import and `replace` × all three locks — 409, no
  module or part written, run still `preview`, then the same run commits once
  unlocked — plus the owner and a manager passing a Controlled Lock. **21 of the new
  cases fail against the unfixed source** (the rest are the controls: owner / manager
  passes, unlocked, sticky owner, 404s). `tests/e2e/cutlist_locks.spec.ts` (4): a Hard
  Lock disables every control for a manager, with the reason, and unlocking restores
  them; seeded `JO-K-103` (Controlled-Locked, drafter-owned) is open to a manager,
  and after ownership moves to the manager the drafter is disabled, then restored;
  a stale page reverts a refused edit / add / delete with the owner named; the CV
  wizard shows a refused commit's reason. **All four fail against the unfixed web
  code.** Each e2e test puts the item back exactly as seeded.
- **Known gaps, recorded.**
  - ~~Hardware lines still ignore every lock.~~ **Closed — see *Lock checks on
    hardware lines* below.**
  - ~~`PATCH /items/{id}/status` and `/lifecycle/{stage_key}` still never consult the
    lock.~~ **Closed for the Hard and Controlled locks — see *Lock checks on status
    and lifecycle* below.**
  - ~~**`CvImportDialog`'s `ITEM_NOT_EMPTY` branch looks dead**~~ **Closed — see
    *Small fixes: order `project_id` and the CV `ITEM_NOT_EMPTY` message* below.**
    (It read `e.detail.code`, but `cv-fetch.ts` keeps the whole parsed body
    `{detail: {code}}` in `e.detail`, so the friendly message never showed and the
    person saw `commitCvImport: 409`.)
  - **The notice is hidden from read-only roles**, while their controls are disabled
    too — a viewer on a locked item sees disabled controls and the lock banner above
    the page, not the cutlist notice.
  - The same hand-written `auth_role in (manager, admin)` Controlled-Lock exemption,
    and no "request a change" flow for a refused write — Q472 is still not built.
- **Out of scope (deferred):** a request flow for a refused module / part write; guarding the CV `preview` (it writes only a run row).

## Lock checks on hardware lines (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on hardware lines") — the gap
> *Lock checks on the other module and part writes* left as "offered and not chosen".
> Both questions it would have raised were already settled by the two rounds before
> it, so **nothing was re-asked**: the rule is the same `assert_item_content_unlocked`
> (Hard + Approval + Controlled, refused because none can be held as a `PatchItemIn`
> request) and the UI is the same "one notice + controls disabled". No migration, no
> spec or plan doc; this section is its written record.

- **Backend.** `hardware_lines.queries.{create_hardware_line, patch_hardware_line,
  delete_hardware_line}` take the acting `AuthUser` (`actor=`, was `actor_id=`) and check
  the lock right after resolving the item, before anything is written, audited or
  logged; the three routes (`POST /items/{id}/hardware_lines`, `PATCH` and `DELETE
  /hardware_lines/{lid}`) turn `ItemContentLocked` into the same `409 {detail: {code,
  …}}` the module / part routes use. Unknown ids stay 404. **A refused write changes
  and logs nothing.** Deleting a line also **cascades its procurement allocations**
  (`batch_allocations`, `ON DELETE CASCADE`), which is one more reason the delete is
  refused rather than allowed. The Approval Lock consequence is the same as for parts:
  hardware edits on an APPROVED item are refused until its status moves off Approved.
- **Deliberately not locked: the project catalog.** `POST` / `DELETE
  /projects/{pid}/hardware_catalog` (and the Pantry's **+ Add from global**) belong to
  the **project**, not to an item, so no item's lock can govern them; a catalog row
  is shared by every item of the project. Pinned by
  `test_project_catalog_writes_are_not_governed_by_an_items_lock` (a Hard-Locked item
  does not stop a catalog add, and `DELETE` of a row still 409s only because a line
  references it). *This is an assumption made while building, not a user decision* —
  the alternative (locking a project's catalog while any of its items is locked) has
  no owner to name and would be new functionality.
- **Estimate Convert is unaffected.** `estimating.convert_to_project` inserts hardware
  lines for **brand-new** items it has just created, so there is no lock to consult.
- **Web.** `HardwareTab` now takes `currentUserId` / `currentUserRole` (threaded from
  `EditorTabs`) and reuses `moduleLockReason` / `lockFromError` from
  `cutlist/moduleLock.ts` — the file is named for modules but now serves the whole item
  editor, and its wording changed to "cutlist or hardware"; it was **not renamed**, to
  keep the diff to what the task needs. One notice at the top (`data-testid=
  "hardware-locked"`, drafter / manager / admin only, the roles that can write) and the
  Pantry's **+**, the Cart's quantity steppers, note field and **Remove** are disabled.
  A `409` from a stale page shows the server's reason and **reverts** the edit (the note
  and quantity roll back, a refused add adds no line, a refused remove brings the line
  back). **+ Add from global** stays enabled (project catalog, above).
- **Tests.** `test_hardware_lines_routes.py` (+15): all three routes × Hard and Approval
  Lock (refused for the owner and an admin alike, nothing changed or logged, then the same
  request succeeds once cleared); all three × Controlled Lock (a non-owner refused naming
  the owner; the owner and a manager pass); an unlocked item and a sticky owner do not
  block; unknown ids stay 404; the project catalog is not governed by an item's lock.
  **9 of the new cases fail against the unfixed source** (the rest are controls).
  `tests/e2e/hardware_locks.spec.ts` (3): a Hard Lock disables every hardware control for
  a manager, with the reason (and leaves **+ Add from global** on), unlocking restores
  them; seeded `JO-K-103` (Controlled-Locked, drafter-owned) is open to a manager, and
  after ownership moves to the manager the drafter is disabled, then restored; a stale
  page reverts a refused note / add / remove with the owner named. **All three fail
  against the unfixed web code.** Each puts the item back exactly as seeded.
- **Known gaps, recorded.**
  - **Locks now cover the whole item editor's writes to an item's cutlist and hardware,
    but not everything on an item**: `PATCH /items/{id}/status` and `/lifecycle/
    {stage_key}` **now consult it too (Hard and Controlled — see *Lock checks on status
    and lifecycle* below)**, and **attachments and the document register now do too
    (see *Lock checks on attachments and the document register* below)**, but the
    other item-scoped writes — QC records and comments — do not (**item queries and
    material takes now do — see *Lock checks on item queries and material takes***).
    None was asked for; whether either should follow is a product question
    (a comment on an approved item, for instance, is probably meant to stay possible).
  - No "request a change" flow for a refused write, and the same hand-written
    `auth_role in (manager, admin)` Controlled-Lock exemption — Q472 is still not built.
  - `moduleLock.ts` is named for modules but serves hardware too (above).
- **Out of scope (deferred):** locks on the other item-scoped writes named above; a
  request flow for a refused write; locking the project catalog.

## Lock checks on status and lifecycle (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on status and lifecycle"). It closes
> the gap every earlier lock round recorded as "unchanged §L scope". The request
> collided with a rule already in this file, so the user was asked before any code was
> written; the four answers below are **settled decisions**, not assumptions. No
> migration, no spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **The Approval Lock applies to neither route.** It is derived from
     `status = 'APPROVED'`, and changing status is the documented way to clear it
     (*Locking + Concurrency*; `ApprovalLockBanner`), so gating `/status` on it would make
     an approved item impossible to unlock. Lifecycle was decided the same way, because
     approval (drawings signed off) is exactly when production dates start being recorded.
     Hard and Controlled gate both routes.
  2. **Bulk status skips locked items and lists them**, rather than refusing the whole
     batch — the pattern `not_found` / `cross_workspace` already set.
  3. **Shop Floor's fan-out is not gated.** Completing a stage writes `item_stages.done_date`
     onto every linked item (Q439); that is the system projecting a cutlist-level fact, like
     `sync_orders_for_item` rewriting CUTLIST NO., not a person editing the item.
  4. **Same Controlled-Lock rule as the other writes** — the owner and managers/admins
     pass; anyone else, foremen (`editor`) included, is refused.
- **Backend.** `items.queries.assert_item_content_unlocked` gained
  `include_approval: bool = True`; status and lifecycle pass `False`, so the check is the
  Hard Lock and someone else's Controlled Lock only (codes `HARD_LOCKED`, `ITEM_LOCKED`,
  same bodies as the other routes). `patch_item_status`, `bulk_patch_item_status` and
  `patch_lifecycle` take the acting `AuthUser` (`actor=`, was `actor_id=`) and check right
  after resolving the item, **before anything is written, audited or logged**; the two
  single-item routes turn `ItemContentLocked` into `409 {detail: {code, …}}`. Unknown ids
  stay 404, and an invalid `stage_key` is still `400` (validated before any lock).
  `POST /items/bulk-status` answers `200` with a new **additive** field
  `locked: [{item_id, code, owner_name}]`; skipped items get no status-log, audit or edit-log
  row, and everything else in the batch is applied.
- **A Hard Lock beats the Approval state**: a hard-locked APPROVED item answers
  `HARD_LOCKED` on these routes, not a pass.
- **Web.** `cutlist/moduleLock.ts` gained a `LockScope` (`"content"` | `"status"`) on
  `moduleLockReason` / `lockMessage` / `lockFromError`; `"status"` leaves the Approval Lock
  out and words the Hard Lock as "before its status or stage dates can be changed". The
  Actions tab shows one notice (`data-testid="actions-locked"`, drafter / editor / manager /
  admin only — the roles that can act) and disables **Set status** and **Mark REQ done**.
  `StatusPopup` takes optional `currentUserId` / `currentUserRole` (passed by both callers):
  with them it shows the reason up front (`data-testid="status-locked"`) and disables
  **Update Current Item**; a `409` from a stale page shows the server's reason and keeps the
  dialog open. `BulkStatusDialog`'s response type gained `locked`, and Tracking's banner reads
  "N updated · M skipped (locked: #12, #14)".
- **Tests.** `test_status_lifecycle_locks.py` (13): Hard Lock refuses everyone (an admin
  included) on both routes, nothing changed or logged, then the same request succeeds once
  cleared; Controlled Lock refuses a non-owner and a foreman, naming the owner, while the
  owner and a manager pass; unlocked and sticky-owner items don't block; **the Approval Lock
  does not stop a status change (and audits `item.approval_unlock`) or a lifecycle date**; a
  Hard Lock wins over an approved item; unknown ids 404 and a bad stage key 400; bulk skips
  Hard / Controlled items and lists them while updating the rest (including an APPROVED item),
  a manager and the owner pass, and an unlocked batch reports `locked: []`. **Eight fail against
  the unfixed source**; the other five are controls. `tests/e2e/status_locks.spec.ts` (5) ran
  against a live migrated, seeded stack: a Hard Lock disables both Actions for a manager and
  unlocking restores them; seeded Controlled-Locked `JO-K-103` is open to a manager and, once
  ownership moves to the manager, disabled for the drafter — then restored; **an APPROVED item
  keeps both Actions and the status dialog usable and can be moved off Approved**; a stale page
  shows the owner's name for a refused status and a refused date; a mocked bulk response with a
  skipped item reads in the banner. **Four fail against the unfixed web code** (the Approval Lock
  one is the control). Each test puts the item back exactly as seeded.
- **Known gaps, recorded.**
  - **A Hard Lock can still receive a date from Shop Floor** — completing a stage on the item's
    cutlist writes `item_stages.done_date` regardless (decision 3). Only the manual lifecycle route
    is refused, so Tracking and the item's own lock can disagree until it is unlocked.
  - **A foreman is refused on a drafter's Controlled Lock** (decision 4). Marking a stage date
    for an item a drafter has claimed needs the drafter or a manager — the same friction the
    module / part / hardware writes already have, now reaching the two things foremen actually do.
  - No "request a change" flow for a refused status or date; the Controlled-Lock exemption is
    still a hand-written `auth_role in (manager, admin)` check (Q472 not built).
  - Still not lock-checked: QC records and comments (none asked for; a comment on an
    approved item should probably stay possible). Attachments and the document register
    **are now — see *Lock checks on attachments and the document register* below** — and
    so are item queries and material takes (*Lock checks on item queries and material
    takes*).
  - `moduleLock.ts` is named for modules but now serves hardware, status and stage dates.
- **Out of scope (deferred):** gating Shop Floor's fan-out; the Approval Lock on either route;
  a request flow for a refused write; the other item-scoped writes named above.

## Lock checks on attachments and the document register (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("Next task is lock checks on attachments and the document
> register") — the gap *Lock checks on hardware lines* and *Lock checks on status and
> lifecycle* both recorded as "not asked for". The one open decision — whether the
> Approval Lock applies — was asked before any code was written, and is a **settled
> decision**, not an assumption. Everything else was settled by the earlier lock rounds
> and carried over. No migration, no spec or plan doc; this section is its written record.

- **Settled decision (user).** **Hard + Approval + Controlled, for both.** Unlike status and
  lifecycle (where status *is* the unlock lever), attachments and the register are plain
  information, so the same rule as the cutlist and hardware writes applies: an approved item's
  whole information set locks together (Q508 — "information locks when approved"). To replace a
  floor plan or add a register document on an approved item, move its status off Approved first.
  The alternatives offered — attachments only, or neither — were declined.
- **What is gated.** All five writes, each refused with `409 {detail: {code, …}}` (`HARD_LOCKED`,
  `APPROVAL_LOCKED`, `ITEM_LOCKED` — the same codes and bodies as the other routes):
  `POST` / `DELETE /items/{iid}/attachments/{kind}` and `POST /items/{iid}/documents`,
  `PATCH` / `DELETE /documents/{did}`. **Relabelling and reordering a register document is a change
  too** and is refused like the rest (an assumption made while building — the register has no web UI
  to show the question, and a Hard Lock means "cannot change"). Reads (`GET` bundle, `GET` register,
  the print routes) are never gated.
- **Backend.** `item_attachments.queries.{bind_attachment, clear_attachment}` and
  `item_documents.queries.{bind_document, patch_document, unbind_document}` take the acting
  `AuthUser` (`actor=`, was `actor_id=`) and call `items.queries.assert_item_content_unlocked` right
  after resolving the item — **before** the blob is validated, and before anything is written,
  audited or logged; the routes turn `ItemContentLocked` into the 409. Unknown ids stay 404: the
  lookup runs first, and `clear_attachment` on an unknown item finds nothing to lock and falls
  through to its 404. So a locked item with a bad mime answers `409`, not `415`. **A refused write
  changes and logs nothing** (pinned by comparing slot rows, register rows, `item_edit_log` and
  `audit_log` counts before and after). `patch_document` / `unbind_document` resolve the document's
  item from the document, so a lock on *that* item governs it.
- **Not gated, deliberately: `POST /files`.** Uploading a blob belongs to the workspace, not to an
  item, so no item's lock can govern it (the same reason the project hardware catalog stayed open). A
  refused bind therefore leaves an unreferenced `file_blob` behind — exactly like every other
  abandoned upload, and there is still no orphan GC. *An assumption made while building.*
- **The register had no web UI when this shipped** (its rule was covered by pytest alone) — **it has one
  now, see *Document Register web UI* below.**
- **Web.** `AttachmentsTab` takes `item` and `currentUserId` (threaded from `EditorTabs`) and shows one
  notice (`data-testid="attachments-locked"`, drafter / manager / admin only — the roles the tab already
  lets write); `AttachmentSlotCard` disables **Upload / Replace** and **Delete** with the reason as
  `title`, and a refusal from a stale page shows the server's reason. `lib/attachments-fetch.ts`
  errors now carry `status` and `body` (they used to throw a bare message, so a 409 read
  "[object Object]" or "clear failed: 409" and `lockFromError` had nothing to read). `moduleLock.ts`'s
  `"content"` wording now says "cutlist, hardware or attachments".
- **Seed.** `seed/hartwood_joinery.py` builds an `AuthUser` for the drafter to call `bind_document`
  (it now needs an actor); verified by running the whole seed against a fresh migrated database — the
  "2 item documents" line still prints. Nothing new is seeded: as with the other locks, a seeded lock
  would risk the fixed e2e suite.
- **Tests.** `test_attachments_documents_locks.py` (30): all five writes × Hard and Approval Lock
  (refused for a drafter and an admin alike, nothing changed or logged, then the same request succeeds
  once cleared); all five × Controlled Lock (a non-owner refused naming the owner; the owner passes; a
  manager passes); an editor refused on the three register writes (`list:write` alone gates them, so
  editors may write it); an unlocked item and a sticky owner do not block; reads are never gated;
  unknown ids stay 404 under a Hard Lock. **18 fail against the unfixed source**; the other 12 are
  controls. `test_item_attachments_crud.py` was updated in place for `actor=`.
  `tests/e2e/attachments_locks.spec.ts` (4) ran against a live migrated, seeded stack: a Hard Lock
  disables every slot control for a manager, with the reason, and unlocking restores them; seeded
  Controlled-Locked `JO-K-103` is open to a manager and, once ownership moves to the manager, disabled
  for the drafter — then restored; an approved item disables them until status moves off Approved; a
  stale page shows the owner's name for a refused delete and a refused upload. **All four fail against
  the unfixed web code.** Each puts the item back exactly as seeded. (The stale-page test uploads a
  small PDF through the real `/files` before the mocked bind is refused, leaving one deduplicated blob.)
- **Known gaps, recorded.**
  - Still not lock-checked: QC records and comments (none asked for). Item queries and material
    takes **now are — see *Lock checks on item queries and material takes* below.**
  - No "request a change" flow for a refused write; the Controlled-Lock exemption is still a
    hand-written `auth_role in (manager, admin)` check (Q472 not built).
  - A refused bind leaves an unreferenced blob (above); the Combined PDF and print routes read
    whatever the slots hold and never consult a lock.
  - `moduleLock.ts` is named for modules but now serves hardware, status, stage dates and attachments.
- **Out of scope (deferred):** ~~a web UI for the Document Register~~ (**built, see below**); gating `POST /files`; a request flow
  for a refused write; the other item-scoped writes named above.

## FIELD_CONFLICT serialisation on items and cutlists (no migration) — shipped

> Chosen by the user ("go with 1") from the suggestion list after the legacy procurement audit; it is
> the gap *Orderbook — Purchase Order editing UI* recorded as "the identical shape likely exists in
> `items`'s and `cutlist`'s own conflict paths". Nothing in it was under-specified, so nothing was
> asked. No migration, no spec or plan doc; this section is its written record.

- **What was wrong (reproduced before fixing).** A `FIELD_CONFLICT`'s `current_value` rides in
  `HTTPException(detail=...)`, which bypasses the response_model's encoding and goes through
  Starlette's plain `json.dumps`. `patch_order` had been fixed for this; `patch_item` and
  `patch_cutlist` still put the raw column value in, so a conflict on a non-string value was a raw
  `TypeError` 500 instead of the 409:
  - **Items:** `total_amount` is a versioned, patchable `Decimal`. A stale-version PATCH on it
    500'd. This is the one *reachable by a normal client*.
  - **Cutlists:** `expected_versions` may name any key and `current_value` is read from the row for
    whatever key it names, so naming a datetime column (`created_at`) 500'd. Contrived, but the same
    code path. (`name`, the only patchable field, is a string.)
  - Items cannot hit the datetime case: the items row carries no datetime column a caller can reach
    (`hard_locked_at` is only set under a Hard Lock, which refuses the PATCH before the conflict check).
- **The fix.** The orders module's private `_conflict_safe_value` moved to
  `app/concurrency.py::conflict_safe_value` and all three modules call it where they fill
  `current_value`. Decimal and date / datetime become **strings** (not `jsonable_encoder`'s float, which
  would break this API's money-is-a-string invariant). Items and cutlist routes are unchanged; orders keeps
  its `jsonable_encoder` wrapper.
- **Tests** (`test_lock_types_concurrency.py`, 2 new): an item `total_amount` conflict answers 409 with
  `current_value == "1234.50"` (a string) and the stale write does not land; a cutlist conflict naming
  `created_at` answers 409. **Both fail against the unfixed source** (`TypeError: Object of type Decimal /
  datetime is not JSON serializable`). The existing orders conflict test still passes through the shared
  helper. 173 pass across the lock, order, cutlist and item route files.
- **Known gaps, recorded.** `expected_versions` is not validated against the real field names, so a
  caller can still name any key (cutlist reads it from the row; items falls back to the key itself). That
  is the behaviour `test_cutlist_conflict_on_unrelated_expected_version_key_does_not_500` pins on purpose.
  The three modules each still call `check_field_conflicts` and fill `current_value` themselves.

## Lock checks on item queries and material takes (Plan V1 §12 follow-up, no migration) — shipped

> Chosen by the user ("go with 1 and 2 and 3", the third item of a list I proposed:
> "lock checks on the remaining item writes: queries, QC records and material takes").
> Reach and rule were open, so the user was asked before any code was written; the two
> answers below are **settled decisions**, not assumptions. The UI half — one notice,
> controls disabled, a 409 fallback — was **carried over from the earlier lock rounds,
> not re-asked**. No migration, no spec or plan doc; this section is its written record.

- **Settled decisions (user).**
  1. **Reach: item queries and material takes. QC records stay unlocked** (comments too,
     as before). QC is production-floor work done by `editor` users (foremen) on items
     that by then are approved or claimed by a drafter, so a lock check would refuse the
     people doing it on exactly those items.
  2. **Hard Lock + someone else's Controlled Lock, not the Approval Lock** — the status /
     lifecycle rule. Takes are approved and queries answered on approved items, so gating
     them on `APPROVED` would stop the workflow they belong to. **Asking** a query answers
     to the Hard Lock only: anyone with `list:read` may ask, and a Controlled Lock must not
     stop a person putting a question to its owner.
- **What is gated** — all refused with `409 {detail: {code, …}}` (`HARD_LOCKED`, `ITEM_LOCKED`,
  the same codes and bodies as the other routes), before anything is written, audited or
  logged, so a refused write changes and logs nothing:
  - `POST /queries/{qid}/answer`, `PATCH /queries/{qid}/answer` — Hard + Controlled.
  - `POST /items/{iid}/queries` (asking) — **Hard only**.
  - All seven take writes: generate, regenerate, add / edit / remove a line, approve, and
    record an impact review (`/reviews`, which can open the next version) — Hard + Controlled.
  - Reads are never gated; unknown ids stay 404 (the lookup runs first).
  - **Choices made while building, not user decisions:** the Hard Lock *does* refuse asking
    (the answer only exempted the Controlled Lock); approving a take and recording a review
    count as writes; the **Material Summary** (build, confirm, line edits) is not gated — it is
    project-level, not item-scoped, like the project hardware catalog.
- **Backend.** `items.queries.assert_item_content_unlocked` gained `include_controlled`
  (`False` for asking). `item_queries.queries.{create_query, answer_query}` and every
  `material_takes.queries` write take the acting `AuthUser` (`actor=`, was `actor_id=`), as in
  the earlier rounds. A take write resolves the item first and **locks the item row before the
  take row** (`_unlocked_take`), the order `generate` takes them in, and checks the lock
  *before* `TAKE_NOT_DRAFT` / `TAKE_NOT_APPROVED`, so a locked item answers `409` whatever the
  take's state. `review` → `generate` re-checks, harmlessly. The seed builds an `AuthUser` for the
  take and query blocks; `test_material_take_generate_race.py` passes one.
- **Web.** `cutlist/moduleLock.ts` gained the scope `"records"` (Hard + Controlled, wording
  "queries or material take"). `QueryTab` and `MaterialTakeTab` now take `item` and
  `currentUserId` (threaded from `EditorTabs`) and show one notice
  (`data-testid="queries-locked"` / `"take-locked"`, to the roles that can write — and to
  anyone on the Query tab under a Hard Lock, since asking is refused too) while disabling the
  answer box, Answer / Edit answer, Ask (Hard Lock only), and on a take Generate / Start vN,
  Regenerate, Approve, the impact buttons, every line input, Add line and Remove, each with the
  reason as `title`. **409 fallback:** `lib/item-queries-fetch.ts` errors now carry `status` and
  `body` (they used to put FastAPI's `detail` *object* into `Error`'s message, so a refusal read
  "[object Object]"); the take tab words a 409 from its own `ApiError.detail` and **reloads the
  take on any failed write**, so a refused cell edit snaps back to what the server holds. A
  refused *answer* keeps the typed text (nothing was saved; losing it would be worse).
- **Tests.** `test_queries_takes_locks.py` (39): all seven take writes × Hard Lock (refused for
  a drafter and an admin alike, nothing changed or logged, then the same request succeeds once
  cleared) and × a non-owner under a Controlled Lock (naming the owner; the owner passes; a manager
  passes); the Approval Lock does **not** stop any of the seven; answer and edit-answer × Hard and
  Controlled (a foreman, a non-owner, is refused); asking refused by a Hard Lock and **not** by a
  Controlled or Approval Lock; an unlocked item and a sticky owner (`cutlist_owner_id` survives
  Unlock) do not block; reads are never gated; unknown ids stay 404 under a Hard Lock; a refused
  review opens no next version; QC defects are deliberately not lock-checked. **20 fail against the
  unfixed source**; the other 19 are controls (the Approval-Lock-does-not-block cases, owner / manager
  passes, reads, 404s). `tests/e2e/queries_takes_locks.spec.ts` (4), run twice back to back against a
  live migrated, seeded stack: a Hard Lock stops answering and asking on K-101 and says why; a Hard
  Lock disables every take control on K-102 (the seeded draft); seeded Controlled-Locked K-103 is open to
  a manager and, once ownership moves to the manager, the drafter's take controls are disabled while
  asking stays open; a stale page shows the owner's name for a refused take edit (the cell snaps back)
  and a refused answer. **All four fail against the unfixed web code.** Each puts the items back as
  seeded. `item_project_detail`, `material_take`, `estimating` and `smoke` still pass.
- **Known gaps, recorded.**
  - **QC records and comments are not lock-checked, by decision** — a foreman raising a defect on an
    approved or claimed item is the normal case.
  - No "request a change" flow for a refused write; the Controlled-Lock exemption is still a
    hand-written `auth_role in (manager, admin)` check (Q472 not built).
  - Under a Controlled Lock the Query tab's notice speaks of changes and does not say that asking is
    still open; the Ask form simply stays enabled.
  - `moduleLock.ts` is named for modules but now serves hardware, status, attachments, queries and takes.
  - The Tracking modal's `Query` tab is still a "Coming soon." stub (unchanged).
  Full suite: **1460 passed, 10 skipped, 1 failed** against a real migrated Postgres 16 (the failure is the
  same local-only `MEILI_URL` gap `test_search_reindex.py::test_real_reindex_swaps_and_drops_temp` has always
  had here), with this and *Generate Orders: per-line selection* both in. `tsc --noEmit` is clean.
- **Out of scope (deferred):** a request flow for a refused write; locking QC records or comments; the
  Material Summary.

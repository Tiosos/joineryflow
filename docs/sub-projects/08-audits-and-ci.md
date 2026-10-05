# Audits And Ci

> Archived verbatim from the old CLAUDE.md (2026-10-03 reorganisation). History and per-sub-project detail; `CLAUDE.md` holds the current rules.

## Null-write audit (`schema_guards.no_null`, no migration) — shipped

> Chosen by the user ("go with the audit", after "Suggest the next task and give me
> reasons"). It is the audit *Order field validation* recorded as a known gap: the orders bug
> (an explicit `null` written into a nullable column that the response model types non-null,
> poisoning every later read) could exist anywhere. The scope was asked before any code was
> written; the answer is a **settled decision**: **fix the poison and all the raw-500 fields**.
> The third option offered — also reject *unknown values* for constrained string fields — was
> **not chosen**, and moving validation ahead of `commit()` app-wide was **never in scope**.
> No migration, no spec or plan doc; this section is its written record.

- **Method (measured, not guessed).** A static scan listed every write schema field that accepts
  an explicit `null` (**359 fields on 81 routes**; a name-matching heuristic against the database
  was too noisy to trust). Then every PATCH / PUT field was **probed empirically**: on a scratch copy
  of the seeded database, send `{field: null}` to the route for a real row and record what
  happens — refused 4xx, accepted, a **raw 500 with nothing written**, or a **poison** (500 *and*
  the column is now NULL, i.e. the write landed before the response failed validation).
  221 (route, field) pairs across 34 routes (two routes, `/me/status` and the lifecycle date
  route, had no row to probe). Then a **read-side crawl**: every GET route whose path ids could be resolved
  (**96**) before and after all the accepted nulls were left in place, diffing status codes, because a
  null a PATCH accepts can still break a *different* read model.
- **Found, before the fix.** **One poison:** `PATCH /suppliers/{vendor_id}` `status`. `vendors.status`
  is nullable and `SupplierOut.status` is `str`, so the null persisted and `GET /suppliers` and
  `GET /suppliers/{id}` answered 500 for the whole workspace — the orders bug again, in the
  module next door. **32 raw 500s:** an explicit null for a field whose column is `NOT NULL`
  (nothing persisted, but a 500 instead of a 422). The crawl confirmed nothing else breaks a read:
  after all 91 accepted-null probes (before the fix) the only routes that changed were `/suppliers` and
  `/suppliers/1` (200 → 500) — the known poison, which doubled as the crawl's control.
- **The fix — `apps/api/app/schema_guards.py`.** `no_null(*fields)` is a `field_validator`
  factory: an explicit null is a **422 that names the field** (`loc` ends in the field), and, being a
  `field_validator`, it runs **only for a field the caller supplied**, so omitting a field is untouched
  (the reason the field is typed `X | None = None`). It is attached as `reject_null = no_null(...)` to
  **18 schemas / 33 fields**: `PatchSupplierIn` (`name`, `category`, `status`), `PatchSampleIn`
  (`title`, `hex_swatch`), `UserPatch` (`full_name`, `is_active`), `PatchBatchIn` (`qty_ordered`,
  `qty_received`), `PatchProjectIn` (`name`), `PatchContactIn` (`kind`, `name`, `sort_order`),
  `BoardInventoryPatchIn` (`qty_on_hand`), `CutSchedulePatchIn` (`priority`), `PatchRelatedPartIn`
  (`related_part_type_key`), material-take `PatchLineIn` (`qty`, `wastage_pct`), and in estimating
  `PatchEstimateIn` (`title`), `PatchRevisionIn` (`markup_pct`, `gst_pct`), `PatchLineIn`
  (`description`, `qty`, `unit`), `PatchPartIn` (`qty`, `paint_instruction`), `PatchHardwareIn`
  (`qty`), and QC's `PatchDefectIn` (`description`), `PatchChecklistItemIn` (`label`, `is_checked`,
  `sort_order`), `PatchReworkIn` (`cause`, `scope`). **`PatchOrderIn` / `PatchOrderLineIn` keep their
  own earlier validators** (untouched). Fields whose column legitimately clears (notes, dates, a contact
  name) are deliberately **not** guarded: clearing them is the point.
  **Re-probed after the fix:** 0 poison, 0 raw 500 (was 1 and 32); the same 33 fields now answer 422.
- **Tests.** `test_null_write_guards.py` — every (schema, field) refuses an explicit null naming the
  field, and every schema still accepts an empty body (33 + 18 cases) — and three new in
  `test_supplier_routes.py`: null `status` is a 422, **writes nothing, and `GET /suppliers` and
  `GET /suppliers/{id}` stay 200** (the poison regression); null `name` / `category` a clean 422; and
  a control that `contact_name` still clears to null. **36 of them fail against the unfixed source**
  (33 schema cases + the 3 supplier HTTP tests); the rest are controls. The two probe / crawl scripts
  were throwaway and are **not in the repo**.
- **Known gaps, recorded.**
  - **The guard is opt-in.** A *new* PATCH schema must call `no_null` for its NOT NULL fields; nothing
    fails if it forgets, because a generic test would have to know each field's column and nullability.
    The next audit is the same two steps above.
  - **POST bodies: audited afterwards, found clean — see *POST-body null audit* below.**
  - **Not audited:** `PATCH /me/status` and
    `PATCH /items/{id}/lifecycle/{stage_key}` (no resolvable row in the probe); **unknown values** for
    constrained strings (`status`, `kind`, `paint_instruction`, ...) beyond what each schema already
    validates — the option the user did not choose.
  - **The audit saw only routes with a resolvable row and the first row of each resource**, and a
    read that no crawled GET exercises could still be broken by a null. 96 GET routes were crawled, not all.
  - **Accepted nulls that are legal but odd:** `PATCH /projects` accepts `status: null` (the column is
    nullable and every crawled read tolerated it), as do related parts' `status` / `description`. They
    are not poison, so they were left; a NULL project status is unlikely to be intended.
  - **Commit-before-validate is unchanged** (user's decision): a *new* nullable-column-versus-non-null-
    response mismatch introduced later can poison a row again, because every route still commits
    before FastAPI validates the response.
  - The 422 body is FastAPI's default (`detail: [{loc, msg}]`), so the web shows its generic
    "Save failed (422)" — no web change was needed or made.
- **Out of scope (deferred):** ~~POST bodies~~ (**audited, see below**); unknown-value validation for
  constrained strings; validating before `commit()`; a generic guard that infers NOT NULL from the schema.

## POST-body null audit (no code change, no migration) — measured, found clean

> Chosen by the user ("Go for POST-body null audit"), the follow-up the section above
> recorded as "not audited". **The result is that there is nothing to fix**, so no scope
> question was asked and no schema, test or migration changed; this section is the record
> so the audit is not repeated. The probe scripts were throwaway and are **not in the repo**.

- **Method — the PATCH audit's, adapted to creates.** The static scan lists every POST body
  field that accepts an explicit `null`: **45 routes / 138 fields**. Each create route got a
  hand-built **valid base body** (a control that must answer 2xx) and then the base with one
  field set to `null`, on a scratch clone of the seeded database, with per-table row counts
  taken around every call: *nothing gained* = refused or raw 500, *rows gained* = persisted
  (and, if the answer was a 500, **poison**). 32 create routes were probed in one process. The
  13 state-changing action routes (`approve`, `reject`, `complete`, `resolve`, `close`,
  `expire`, `withdraw`, `convert`, `generate-orders`, `assign`, `reviews`, `decide`) can only
  succeed once per database, so each ran in its **own fresh clone**, once with the field
  omitted and once with `null`.
- **Result: 0 poison, 0 raw 500.** Of the 138 (route, field) pairs: **121 accepted** (a nullable
  column, or a value the query layer defaults — `estimate_no` becomes `EST-2026-…`, `type`
  becomes `IFA`, `paint_instruction` becomes `NONE`), **2 refused 422** (`POST /comments`
  `object_type` / `object_id`: the schema already requires both together) and **1 `409
  MEMBERSHIP_EXISTS`** (`project_id: null` *means* workspace-wide, and that membership existed —
  the control, not a defect). The 14 action pairs were all 200 with `null`, identical to the
  omitted control. **Nothing answered 500.** Reason it differs from PATCH: a POST names the
  columns it writes and the create schemas type the NOT NULL ones as required or give them a
  non-null default, so a `null` is refused by pydantic or replaced before the INSERT.
- **Read side, crawled.** 96 GET routes were crawled after all probes, three ways — the first
  row of each resource, the *newest* row of each (the probe-created ones), and a targeted pass
  pinned to ALF-001 with both the first item and the most null-heavy created item (null
  description / qty / code / stage; parts with no name or length; modules with no name).
  **No 5xx anywhere.** A first pass only read the oldest rows and so could not have seen a
  probe row; the newest-row and pinned passes exist because of that.
- **Found while probing, not caused by a null — since fixed, see *Approving an order with no
  cost centre* below.** `POST /procurement/approvals/{workflow_id}/decide` answered **500 for an
  approval on a purchase order with no cost centre**, with the field omitted too. `0031` made
  `purchase_orders.cost_center_id` nullable (Q563) but the legacy handler still ran
  `int(po["cost_center_id"])` after `decide` → `commit_budget`, so it raised `TypeError`.
  Nothing was written, and the seed's one PO has no cost centre, so it was reachable on the
  demo data.
- **Legal-but-odd, left:** a create can now leave real NULLs in nullable columns that some
  screens may render as blank — `items.description` / `qty` / `code`, `parts.part_name` /
  `len_mm`, `modules.name` — because the columns and the read models allow it. Every crawled
  read tolerated them; whether a create *should* require a description is a product call.
- **Known gaps, recorded.** The probe used one hand-built body per route, so a route whose
  behaviour depends on *other* body fields (a different `material_type`, a related-part `status`)
  was tested down one path only; `POST /catalog/{slug}/bulk`, the CV-import commit and the
  file / photo bind routes take non-null-typed bodies and were not probed; a crawl that
  reads 96 GET routes is not every read; and — as before — every route still commits before
  FastAPI validates the response.

## e2e suite repair (no migration, no app code) — shipped

> Chosen by the user ("go with the e2e repair, then the 'ordered by hand' questions"), the first item of
> the next-step list after PR #67. Every earlier section of this file recorded the same sentence — *e2e is
> not part of CI, and these specs were red for reasons unrelated to the change* — so the suite was last run
> **whole** long before this. Nothing here needed a decision, so nothing was asked. Test files only: no
> application code, schema or seed changed. Method: reproduce each failure on a **fresh** database, find the
> cause, fix it, and prove the fix by repeating the test (`--repeat-each`) or re-running the sequence it
> fails in.

- **How to run the whole suite (the baseline that matters).** The seed skips items that already exist, so a
  database that earlier runs have touched is *not* the seeded state, and half of what looked like regressions
  on a first whole-suite run (a Controlled Lock gone from `JO-K-103`, a take already approved) were that. Use a
  database nobody has run anything against: create it, `alembic upgrade head`, `python -m seed.hartwood_joinery`,
  start the API on it, then `playwright test` with `workers: 1` (the config). **Verified: 118 passed, 2 skipped
  (the two `search` tests, no Meilisearch here), 0 failed in 7.2 min** on a fresh database with every fix below in
  — the first whole run of this session was 107 passed / 9 failed.
- **Red specs, and what each was.**
  - **`cutlist_related_parts` (collapsed by default)** — counted every `button[aria-expanded]` on the page, and
    the notification bell (added with Comments) and Next's dev-overlay button carry it too (3 where it expects 1).
    Now scoped to `[data-testid="tracking-row"] button[aria-expanded]`. *Not* live-database state, as an earlier
    note here guessed: it failed on a freshly reseeded database.
  - **`search` (2 tests)** — there is no Postgres fallback, so with no Meilisearch `GET /search` is
    `503 SEARCH_UNAVAILABLE`. Both now **skip on exactly that response**; a reachable but empty or broken index
    still fails. **Their bodies are unchanged and were not run past the skip here** — no Meilisearch in the
    sandbox — so the passing path is unverified in this environment.
  - **`drafter_editor`** — toggles the lock of the drafter's first My Day item once and leaves it flipped. That
    item is `K-103`, which the seed leaves Controlled-Locked, so every lock spec after it (hardware, status,
    module-delete, takes) started with no lock: **five tests failed in a whole run and passed alone**. It now
    toggles it back. The audit log named the culprit (`item.unlock`, the drafter, at the moment the spec ran).
  - **`queries_takes_locks` (2 tests)** — need K-102's *draft* take; `material_take.spec.ts`, which runs just
    before, approves that one draft for good. A spec that only passes when another has not run is a trap, so
    `ensureDraftTake` starts the next version through the API when no draft exists (what "Start vN" does).
  - **`comments` (mention picker)** — deterministic on a fresh database. The tab is driven by the URL, so on a
    cold dev build the click takes a moment, and until it lands the Cutlist tab's *module* thread is on screen
    with the same `comment-input` test id; the spec typed `@Rin` into that one and the text vanished when the tab
    swapped. `openCommentsTab` waits for `tab=comments` **and** for `module-comments` to be gone. (Found by
    logging navigations and requests during the test.)
  - **`module_delete` (add / comment / delete)** — passed 3 of 8 repeated runs. Once the module has a comment its
    row's accessible name is **"New module 💬 1"** (the comment-count badge), so `{name: "New module", exact: true}`
    stopped matching the very module the test had just commented on. It matches the name with or without the badge
    now: **8 of 8**. `cv_replace_comments.spec.ts` has the same exact-name locator but never comments on that
    module, so it was left alone.
  - **`procurement`** — clicks the availability chip as soon as a row is visible; before the page hydrates the
    click does nothing. Reproduced at **6 of 12**; the click now retries until `drawer=item-availability`
    appears (`toPass`), which is safe because opening the drawer twice is harmless: **12 of 12**.
  - **`cv_import` (first test)** — hardened with the `href` + `goto` the sibling test and the lock specs use.
    **Not reproduced** in this session (it passed warm and on a cold dev server), so this is hardening, not a
    confirmed fix.
- **The recurring shape, recorded once.** Four of the eight were *one spec leaving shared state changed* (a
  lock, a take) and a later spec assuming the seeded state. Specs run alphabetically in one worker, so the
  failing spec is rarely the guilty one — the audit log (`item.unlock`, `material_take.approve`, …) says who
  touched what and when. Two were a locator that matched a *different* element with the same role or test id
  (the bell, a module thread, a badge in a name). Two were a click before hydration.
- **Known gaps, recorded.**
  - ~~**e2e is still not run in CI** (CI is pytest + `tsc`), so nothing stops the next red spec.~~ **Closed — see
    *e2e in CI* below** (advisory, not a required check).
  - ~~`estimating`, `procurement` and `comments` are still not re-runnable on one database~~ **Closed — see *e2e re-runnable* below.**
  - `search.spec.ts` is unexercised wherever Meilisearch is absent; `cv_import` hardening is unconfirmed.
  - `drafter_editor` still leaves a part ("Test part") and a hardware line on that item on every run; only the
    lock is restored.

## e2e in CI (`.github/workflows/ci.yml`, no migration, no app code) — shipped

> Chosen by the user ("agree, go on asking the two questions", after I suggested it as the next task because
> *e2e suite repair* had just found the suite 9 specs red with nothing to notice). Two things were open, so the user was
> asked before any code was written; the answers are **settled decisions**: the job is **advisory** (not a required
> check, "advisory first") and runs on **every PR and every push to `main`** (the same triggers and docs-only
> `paths-ignore` as the other two jobs). Nothing else in the app changed.

- **The job — `E2E (Playwright)`, third job in `ci.yml`.** On a fresh runner it does what *e2e suite repair* documents as
  the only valid baseline: `docker compose up db meili api`, `alembic upgrade head`, `python -m seed.hartwood_joinery`, then
  `docker compose up search-worker` **after** the seed (the seed's writes sit in `search_outbox` and the worker drains them,
  which is what lets the two search specs find their records — so unlike the pytest job, which must *not* start the worker,
  this one must). The web app runs **on the runner, not in compose**: `.env` is exported, `API_URL=http://localhost:8000`
  (the compose name `api` does not resolve there), `pnpm build`, `next start -p 3000`. Then
  `playwright install --with-deps chromium` and `pnpm exec playwright test` with `PW_BASE_URL=http://localhost:3000`.
  A fresh database per run is also what makes the non-idempotent specs (`estimating`, `procurement`, `comments`) a non-issue.
  `timeout-minutes: 40`. On failure it uploads `apps/web/test-results` (traces) and dumps the compose and web logs.
- **Production build, not `next dev` — a deliberate difference from the dev loop.** Several repaired failures were
  click-before-hydration races caused by on-demand compilation. `next start` has none. **Measured locally before pushing:
  the whole suite against a production build on a fresh database is `119 passed, 2 skipped, 0 failed in 4.0 min`** (the two
  skips are the search specs, no Meilisearch in the sandbox) against ~7 min under `next dev`. `NEXT_PUBLIC_*` values are
  inlined at build time, which is why `.env` is exported *before* `pnpm build`.
- **`retries: process.env.CI ? 1 : 0`** in `apps/web/playwright.config.ts`. One retry, CI only: the one known flake is a
  dev-proxy `ECONNRESET`, and a real failure fails twice. This is a retry, not a skip — **never skip, disable or quarantine
  a spec to get green.** A retried spec that *passes* is reported by Playwright as "flaky": read those lines, they are the
  early warning. Caveat: a spec that changes state and then fails (estimating converts once) can fail again on the retry for
  a different reason; read the first failure.
- **Advisory means the check can be red and merge anyway.** It is **not** `continue-on-error` (that would show green when
  the suite is red and hide the signal). It is simply not added to branch protection. **Promote it to required only after a
  couple of weeks of green runs**; if branch protection ever requires it, note `ci.yml`'s own comment about docs-only PRs
  leaving required checks pending.
- **Wait for the index.** A step logs in through the web proxy and polls `GET /api/search?q=297830` until it returns a hit,
  and is **not fatal** if it never does: the search specs skip on 503, so a slow first index must not fail the job — but it
  would turn two real tests into skips, so look for "search index not ready" in the log.
- **Known gaps, recorded.**
  - **The job's own CI run is the first time the compose path runs end to end**: what was verified locally is the same
    suite against a production build on a fresh database (no Docker daemon in the sandbox), not the workflow itself.
  - ~~The search specs have **never** run past their skip until this job runs them.~~ **They did, on the job's first run
    (PR #69): both passed** — 120 passed, 1 failed, 0 skipped. That run is also the first time the workflow itself ran
    end to end, and every step worked.
  - **The first run's one failure was a real race in a spec, not the job**: `comments.spec.ts` "a mention on an area's or
    room's thread deep-links…" typed the note straight after clicking a mention in the picker. `MentionTextarea.choose()`
    re-places the caret in a `requestAnimationFrame`, so on the slower runner the note's characters landed out of order
    and the comment (a 201 in the API log) did not read as the note. It failed on both attempts at different steps (area,
    then room), which is how it was told apart from a one-off. The spec now waits for the picker to close — it closes only
    after that frame has run — before typing. **Not reproduced locally** (it passed on every local run, before and after),
    so the fix is reasoned from the code and the API log, not demonstrated by a red-then-green run.
  - **Reading a failed CI run from here:** the job log is one long line per request; the Playwright summary (`N failed`,
    the `Locator:` / `Error:` lines) sits above the compose-log dump. `get_job_logs` with a large `tail_lines` saves to a
    file that can be searched; the signed log URL and `gh api …/logs` are both blocked by the sandbox proxy.
  - ~10 minutes of Actions time per push on top of the other two jobs; the `concurrency` group cancels a superseded run.
  - Failures show as a red `E2E (Playwright)` row, not a blocked merge. Someone has to look.

## Test consolidation and cross-workspace isolation probes (PR #76, no migration) — shipped

> Chosen by the user: "check all the test files, review at max level, simplify or combine", then, over several
> rounds of "suggest what we can still fix", the isolation probes and the fixes they forced. Decisions that were
> **asked, not assumed** (Rule Zero): report **plus** implementation; merge depth = shared helpers and
> parametrisation, **not** merging files or renaming tests (so `docs/sub-projects/` test-name citations stay valid);
> e2e got a shared login only; `_login` copies that return different shapes were **left** (user: "leave them");
> a foreign or missing catalog material answers **404 `MATERIAL_NOT_FOUND`**; bulk-status folds foreign ids into
> `not_found`; the seed gets rows so the probes have something to find.

- **Consolidation, measured.** 106 pytest files / 1597 tests / 31 e2e specs. One `tests/helpers.py` (`login`,
  `login_same_workspace`, `create_project`, `set_item`), `helpers_<family>.py` for per-feature builders, and **no test
  file imports another `test_*.py`**. `truncate_after` / `truncate_fixture(*extra)` replaced ~35 cleanup copies; `meili`
  tests skip centrally; `_seed_refs` copies went because `conftest` already re-asserts `status_options`/`stages`. Test
  ids are identical before and after except one deliberate replacement (a permanently skipped autoescape test became a
  real one). **Cheap argon2 in tests** cut the full run from ~18 to ~11 minutes (every login hashed and verified at
  ~175 ms). e2e: `tests/e2e/helpers.ts` `login()`; the two `search` specs now **fail** instead of skip when `CI` is set.
- **The probes (the real find).** Three tests, one oracle: *another workspace's id must be answered exactly like a
  nonexistent one* (status and body, ids masked). `test_workspace_isolation_probe.py` walks every OpenAPI operation with a
  path id (235); `_body_probe` varies each foreign-key field of a JSON body (60 pairs); `_query_probe` does id-like query
  parameters. Each pair also gets a **control** (the caller's own row must be told apart from a ghost), otherwise the
  probe proved nothing: an operation without signal must be listed in `NOT_PROBED` with a reason, and the list is an
  **exact ratchet** (a new unprobable route fails; a probable one must come off). Every probe also **fails on any 5xx**.
- **Lessons that cost time (so the next probe avoids them).**
  - A probe is only worth keeping if it can fail: a deliberately broken `GET /batches?project_id=` (workspace filter
    dropped) did **not** fail the first query probe, because the caller was A's admin passing *B's* id and B owns no
    batches. The direction that leaks data is **B's admin passing A's id** (A has the data). The query probe now
    calls that way for lists with no path id, and the break is caught.
  - A control that mutates its own permissions blinds everything after it: `PUT /permission-groups/{gid}/grants` on the
    admin's own group made every later write a 403 (an empty DB result is a real "no", §5). Those operations run last.
  - Ordering matters for deletes (parts → modules → items) and a control must pick a row the listed rows actually carry
    (the seeded order's vendor, not the first vendor).
- **Defects found and fixed (each with a test that fails on the old code).**
  1. `POST /shop-drawings/{did}/revisions/{rid}/submit|withdraw`: 403 "only the uploader…" for another workspace's
     revision (the pre-check was not workspace-scoped). An existence leak, no data reachable.
  2. Seven routes took another workspace's catalog material from the body (parts create/patch, batches, order lines,
     material take lines, CV mappings create/patch): accepted it, echoed its name, or **500**'d on a nonexistent id.
     Now `catalog.queries.assert_material_in_workspace`, after the lock check and before any write.
  3. `POST /items/bulk-status` returned `cross_workspace: [id]`, telling the caller an id exists elsewhere. Folded into
     `not_found`; the field is gone from API, web and tests.
  4. `POST /projects/{pid}/hardware_catalog` for a material already in the catalog: a raw 500 (`uq_proj_mat`). Now
     `ON CONFLICT DO NOTHING` and `409 ALREADY_IN_CATALOG`. Found by the **5xx check**, not by an isolation rule.
  5. `POST /procurement/approvals/{workflow_id}/decide` accepted another workspace's user as `approver_id` and wrote
     them into the order's changelog (later joined to a name). Now `422 approver not found in this workspace`, the
     same answer `submit` gives. Found only once the **seed gained an approval workflow** (the probe had no signal before).
  6. Not a defect but a behaviour fix: an oversized *pasted* CV CSV answered Starlette's plain 400 (the structured
     `415 FILE_TOO_LARGE` guard was unreachable for pasted text). The preview route now reads its form itself.
- **Conventions settled here.** A catalog row in a body: **404 `{code: MATERIAL_NOT_FOUND}`** (as orders do with
  `VENDOR_NOT_FOUND`). A user reference on the legacy `/procurement/*` module: **422 "… not found in this workspace"**
  (that module's own convention). A refusable mutation: 409 with a stable code. Recorded in `CLAUDE.md` §7.
- **Seed additions** (built with the API's own query functions, idempotent over repeated runs, no e2e count moved): a
  cost centre with one Commitment and a PDF attached to the seeded order; a second, item-less order submitted for
  approval by the seeded admin; a mention notification for that admin (an extra mention on the existing project
  comment, so no comment or bell count changes); one comment by the admin on TRT-014. `make seed` also finds its sample
  files relative to itself now (it hard-coded `/code/...`).
- **Known gaps, recorded.**
  - `NOT_PROBED` today: path probe 2 (`POST /catalog/{slug}` and `/bulk` take a catalog type, not a row id); body probe 3
    (a manual take line, sheet stock for `/optimise`, an unlinked material used by a quote); query probe none. Lock-request
    approve/reject and `approvals/history` came off the list once the seed gained a pending Controlled-Lock request
    (TRT-014 K-103, requested by mina; no e2e spec uses TRT-014's lock flows, nothing on the item changes) and a
    rejected order (see "Follow-up" below). Sheet stock and a manual take line stay unseeded.
  - `GET /search` is excluded from the query probe (503 without Meilisearch); `test_search_routes` covers it on a fake index.
  - **CI had never run any of this** until PR #76 (a branch push does not trigger it; only `main` and PRs do), and the
    `concurrency` group cancels a superseded run, so a flurry of small pushes means no run ever finishes.

### Follow-up (after PR #76)
- **Seed:** a second item-less order is now *rejected* by the seeded admin (a row in `/procurement/approvals/history`), and
  TRT-014's seeded-locked K-103 holds one pending lock request from mina (`patch_item` with a changed description; saving
  again revises the same request, so a re-run is a no-op). The two lock-request routes and `approvals/history ?approver_id`
  are probed now; `NOT_PROBED` shrank accordingly.
- **`log_in(..., client=)`:** logs an existing client in again as another user (cookies cleared). The remaining raw
  `/auth/login` copies (`_login_user`, `_login_b` x3, related parts, samples, shop drawings, users, auth, files upload,
  estimating order helper) now go through it or `login()`. What remains per file are one-line `login(role, prefix=...)`
  wrappers, and setups that build more than a login (`test_actual_costs`, `test_cut_floor_routes`, `test_cv_routes`,
  `test_procurement_routes`).
- **Dead code:** `TrackingGrid.tsx` and `StatusChip.tsx` (used only by it) were deleted. Older plan docs still mention them.

### e2e re-runnable on one database (after PR #77)
- **Measured, not guessed:** the whole suite was run twice on one database without re-seeding. Run 1 passed (bar the two
  `search` specs, which need Meilisearch); run 2 failed **six** more, for six different reasons:
  - `procurement`: two "Test Supplier" rows from the first run broke a strict locator -> a supplier name unique per run.
  - `item_project_detail`: it answered the seeded open question, so the second run found it already answered -> it asks
    and answers a question of its own (unique text).
  - `comments` (Areas & Rooms card): "the first row with a badge" was no longer the seeded area, because other specs and
    earlier runs comment on others -> the rows are found by the seeded comment's text.
  - `comments` (bell): reads Juno's seeded notification, which the first run marks read -> Noa mentions Juno through the
    API first, and the test asserts "one fewer unread" instead of a fixed count.
  - `estimating`: converts the seeded WON estimate, after which there is nothing to convert -> it takes its own estimate
    to WON through the API and converts that (the seeded one stays untouched).
  - `material_take`: approved the seeded draft take and rebuilt the summary, which is the state the second run needs
    to find stale -> it builds a project of its own (a stale summary line and a draft take) through the API.
- **A trap found on the way:** a first version of `material_take` added its items to ALF-001. They became "the first
  item" and "the first tracking row" that `comments`, `comment_counts`, `comments_module_revision`,
  `item_project_detail` and `procurement` open, and have none of the seeded comments, questions or hardware, so seven
  specs failed. Fixtures belong in a project of their own (projects list in id order, so ALF-001 stays first).
- **Result:** two consecutive runs on one database give the same result (only the `search` specs differ, without
  Meilisearch). The seed and the app are unchanged. `drafter_editor` still leaves a part and a hardware line per run.


# E2E speed-up tracker

Why: the Playwright suite (66 specs, `workers: 1`, run twice in CI) takes long. This file records every
suggestion made (2026-10-21), what was done, and what is still open, so later work can pick up from here.
Coverage must not drop: each item says what it keeps. Timings below are estimates until measured (item 8).

| # | Suggestion | Status | Coverage kept / risk |
| --- | --- | --- | --- |
| 1 | **Sign in through the API, not the form.** `tests/e2e/helpers.ts::login` posts to `/api/auth/login` (what the form calls), then opens `/dashboard`. Saves a page load and hydration on each of ~232 logins (est. 4-8 min). | **Done** | The login form is still driven by `smoke.spec.ts` (login to tabs to logout). Not done: a `storageState` setup project (would save the API call too, but a session revoked by one spec would break the rest). |
| 2b | **Limit the second pass to the changed specs on a spec-only PR** (user decision 2026-10-22). Most PRs add an e2e spec, so they all paid for a second whole-suite pass (about 5 min). The `Decide whether the second pass runs` step in `ci.yml` now sets `mode`: `full` on a push to `main` and on a PR that touches `seed/`, `db/`, `apps/web/playwright.config.ts`, `ci.yml` or any e2e file that is not a whole `tests/e2e/*.spec.ts` (helpers, fixtures); `changed` when the PR only adds / edits / renames spec files, which are then the only files the second pass runs (`playwright test <files>`); `none` otherwise. A deleted spec is never passed to Playwright. | **Done** (decision logic tested locally against 14 simulated PR file lists under `bash -eo pipefail`; the `changed` branch itself cannot run on the PR that adds it, since that PR touches `ci.yml` and takes `full`) | Keeps the guard for the spec that changed. Not caught on a PR: an unchanged spec that a new spec breaks on a second run (the whole-suite pass on `main` still catches it, after merge). |
| 2c | **Per-test timing read (2026-10-22), then two setup trims.** The pass-2 log of run 39758741860 (218 tests, 5.6 min) has no slow spec: slowest 6.4 s, median about 1.3 s, and the only fixed waits are two `waitForTimeout(500)` in `undo_toast.spec.ts`. The cost is the per-test fixed overhead (new context, page loads), so there is no cheap spec to fix. Setup trims in `ci.yml`: the api image is built with `docker/bake-action` and the GitHub Actions layer cache (tags `joineryflow-api` / `joineryflow-search-worker` = compose's own names, so `compose up` no longer passes `--build`), and `playwright install-deps` on a cache hit runs beside `pnpm build` instead of after it. | **Open until measured on a run** (`bake` needs the `joineryflow-*` names to match compose's; if not, compose builds as before, no worse than today) | Expected 20 to 40 s per job, not minutes. Sharding the suite is the only large saving left. |
| 2d | **Two shards** (user decision 2026-10-22). The E2E job is a matrix of 2 runners (`--shard=N/2`), each with its own stack and database, so specs cannot collide on shared rows (the failure of the earlier 3-workers-on-one-database attempt). GitHub appends the matrix value to a matrix job's name (`E2E shard (1)`), so a separate `e2e-result` job named `E2E (Playwright)` needs both shards and keeps the required check unchanged (found on the PR's first run, where the shards showed as `E2E (Playwright) (1)` / `(2)`). Playwright cuts the alphabetical file list in two (111 + 107 tests); a changed-specs second pass uses `--pass-with-no-tests` because a shard may get none of them. Timing and trace artifacts carry a `-shard-N` suffix. | **Measured on PR #155's run: shard 1 5m43s, shard 2 6m43s, both passes (was 13m38s in one job).** Checked locally first: each half passes alone on a freshly migrated, seeded database (shard 2 in 3.3 min, shard 1 in 3.3 min; shard 2's only failures were the 4 search specs, which need Meilisearch and fail under `CI=true` by design) | Expected E2E job about 7 min for a whole-suite two-pass run (was 12.5), about 4.5 min for one pass. Costs about 1.5 min more runner time per shard. A new spec that relies on an earlier-sorted spec's data now fails in its own shard: build the data in the spec, as §3 already says. |
| 2e | **Install Playwright system packages only when dpkg says one is missing** (2026-10-22). On PR #155's run shard 2's `Build & start web` took 110 s against shard 1's 24 s: `pnpm build` ended after 21 s, then 89 s passed before `web ready`, and the only slow candidate is the background `playwright install-deps` (its `apt-get update`). The step now reads the package list from `playwright install-deps --dry-run chromium`, checks each with `dpkg -s`, and runs `install-deps` only for a missing one (an unreadable list counts as missing); it also prints timestamps (build start / done, install-deps done, web ready) so the next slow run shows which part it was. | **Open until measured on a run** | Saves up to about 90 s on a slow runner and about 20 s on a normal one. Not checked: font packages are in the list, so a missing font still triggers the install. |
| 2 | **Run the second CI pass (the re-runnability guard) less often.** User decision 2026-10-21: it runs on every push to `main`, and on a PR only when the PR touches `tests/e2e/`, `seed/`, `db/`, `apps/web/playwright.config.ts` or `ci.yml`; other PRs run one pass. It stays a conditional step of the required `E2E (Playwright)` job (no name change). | **Done** (unverified until CI runs) | Departs from the old `CLAUDE.md` §3 wording (always twice); §3 updated. Risk: an API change that makes a spec non-re-runnable is only caught after merge, on `main`. The PR file list comes from `gh api .../pulls/N/files`. |
| 3 | Set up data through the API instead of the UI (projects, items, orders) in the heaviest files: `catalog_supplier_link` (636 lines, 14 tests), `orderbook_layout`, `tracking_layout`. | **Closed: not pursued** (user, 2026-10-21) | Review spec by spec; the UI must stay for what the test checks. |
| 4 | Share one page per file for read-only specs (serial `describe` + `beforeAll` page), e.g. `qc_dashboard`. | **Closed: not pursued** (user, 2026-10-21) | Trades isolation for a small gain; only after 1 and only where tests share a start state. Keep tests separate for failure granularity. |
| 5 | Parallelism: put read-only / self-contained specs in a separate Playwright project with `workers > 1`; keep stateful ones serial. Or shard CI across jobs. | **Closed after an experiment: not adopted** (user, 2026-10-21). See below | Needs an audit of each spec's shared state (specs share data today, `CLAUDE.md` §3); a shard also needs its own database. |
| 6 | CI around the tests. | **Part done** | Done: Playwright browser cached (`actions/cache`, keyed on `apps/web/pnpm-lock.yaml`; a hit still runs `install-deps`). Open: Docker layer cache (buildx + GitHub Actions cache) for `docker compose up --build`; starting the browser install in parallel with the web build. Job names unchanged (they are required checks). |
| 7 | Small clean-ups. | **Part done** | Done: `tracking_layout` pinned-column test polls instead of `waitForTimeout(200)`; `search.spec` retries the `/` shortcut instead of `networkidle`. Kept on purpose: the two `waitForTimeout(500)` in `undo_toast.spec.ts`, which guard that *nothing* is sent after Undo (a negative check needs a wait). Open: lower the many `timeout: 30_000` ceilings (only helps failing runs); check whether `legacy-screenshots` / `screenshot-login` belong in the default CI run. |
| 8 | **Measure first.** CI now writes a JSON report per pass (`PW_JSON_REPORT`, `apps/web/playwright.config.ts`) and `scripts/playwright_slowest.py` puts the 15 slowest tests and spec files of each pass in the job summary; the reports are uploaded as the `playwright-timing` artifact. | **Done** (read the first CI run) | Next: use those numbers to choose between items 3, 4 and 5. Locally: `PW_JSON_REPORT=r.json make e2e`, then `python3 scripts/playwright_slowest.py apps/web/r.json`. |
| 9 | **Fast-forward the Undo window** with Playwright's fake clock (`page.clock.install()` before the page loads, `endUndoWindow(page)` in `helpers.ts` once the toast is up) in the four tests that waited it out. | **Done** (unverified until CI runs) | The tests still prove the request is sent only when the window ends (they check "not sent yet" first). Risk: the fake clock also moves the page's `Date`. Tests that press Undo or leave the page still use real time. |

## First measurement (PR #144, 2026-10-21)

E2E job 16 min 35 s (main, run #143) to 11 min 22 s. Pass 1: 6 min 59 s to 4 min 47 s; pass 2: 7 min 15 s to
4 min 55 s (about 31% from the API login alone). Pass 1 has 212 tests and 279 s of test time against a 287 s step, so
almost all the time is the tests. The tail is flat (average 1.3 s a test; the 15th slowest is 2 s), which is why
reworking single heavy specs (items 3, 4) would pay little. What stood out:

| Finding | Seconds per pass | Action |
| --- | --- | --- |
| Four tests wait the real 10 s Undo window (`undo_toast` x2, `item_soft_delete` x2) | about 46 | **Done** (table row 9) |
| `legacy-screenshots.spec.ts` (static `legacy/*.html` mocks, not the app) | 13.6 | **Decided: leave as is** (user, 2026-10-21) |
| Everything else | flat tail | Only parallelism (item 5) moves it |


## Audit for item 5 (parallel project), first pass

Method: grep of all 66 specs for writes, seeded-row references and global aggregates, then a read of the risky ones.
**This is a static reading, not proof**: shared state also hides in lists, counts and bells that grep cannot see.

What can be shared between specs on one database:
1. **Seeded rows that some spec changes** (ALF-001, TRT-014): specs that read them break if a mutator runs at the same time.
2. **Workspace-wide aggregates**: the purchase officer's bell and badge (every Pending order), tasks in the bell, dashboard tiles, QC tiles, cost-centre totals, search, catalog lists.
3. **User and role state** (permission groups, view-as-role).

| Group | Specs | Why |
| --- | --- | --- |
| **A. Probably safe in parallel** (own project or unique names, no shared aggregate) | `undo_toast`, `item_soft_delete`, `item_duplicate`, `module_delete`, `status_locks`, `status_update_all`, `cutlist_locks`, `hardware_locks`, `attachments_locks`, `document_register`, `pdf_generation`, `prompt_dialogs`, `confirm_dialog` (bell use to check), `tracking_orders_chip`, `catalog_*` single-test files (new rows by unique SKU; `catalog_board_fields`, `catalog_error_toast`, `catalog_type` assert counts: check) | Create their own project / rows, assert by name |
| **B. Read seeded rows, need no concurrent mutator** | `qc_dashboard` (exact counts on ALF-001 / TRT-014; no other spec writes QC records), `comment_counts`, `cv_import`, `shop_drawings`, `isample`, `item_project_detail`, `material_take`, `search`, `tracking_factory_tg_solid`, `catalog` | Safe among themselves; unsafe next to group C mutators of the same rows |
| **C. Mutate seeded rows or shared aggregates: keep serial** | `comments`, `comments_module_revision`, `queries_takes_locks`, `tracking_modal_files`, `cv_replace_comments`, `cutlist_related_parts`, `tracking_layout`, `tasks` (ALF-001, bell, tiles); `lock_requests` (TRT-014, bell); `orders_waiting`, `order_decision`, `budget_report`, `po`, `po_invoice_authorisation`, `order_*`, `orderbook_layout` (Pending orders feed the purchase officer's bell and the cost-centre totals); `estimating` (declares `mode: "serial"`); `view_as_role`; `smoke`, `drafter_editor`, `pm_workbench` (dashboard tiles) | Shared by design |

Unverified guesses to settle before moving anything: whether the orders specs' bell and badge assertions depend on the
count of all Pending orders; which group-A specs read a dashboard or bell count.

**Experiment result and decision (2026-10-21).** The experiment ran the whole suite twice with 3 workers on one database:
2 min 36 s and 2 min 51 s against about 5.5 min serial (roughly 2x), and 66 of 68 files passed both runs. The two failures were
real races on shared seeded items, not random flakes: `cv_replace_comments` (JO-TP01, which `cv_import` also imports onto; 5 files use it)
and `document_register` (JO-K-101, which 7 other lock/attachment specs use). A file that passed once is weak evidence, because
files that share an item only collide when they happen to run at the same moment. By a static count, 30 of the 68 files
reference a seeded row (ALF-001 in 18, JO-K-101 in 8, JO-TP01 in 5, TRT-014 in 3) and would stay serial; 38 do not (the 12 single-test
`catalog_*` files, `undo_toast`, `item_soft_delete`, `pdf_generation`, `prompt_dialogs`, the order/PO files, which share bell and cost-centre
totals). A parallel group of those 38 would save roughly a quarter to a third of a pass, at the cost of an explicit file list to
maintain (with a check that fails on an unclassified new spec) and race risk.

**Decision: stop here.** The suite is about 31% faster and the rest is not worth the upkeep. The experiment workflow
(`e2e-parallel-experiment.yml`), its report script and the `PW_WORKERS` / `PW_RETRIES` config hooks were removed. To revisit: run the suite with
`--workers=3` on a fresh database, treat any file that touches a shared seeded item as serial, and repeat the run several times before trusting it.

**Second measurement (PR #144, after the Undo fake clock).** The four 10 s Undo tests left the top 15 (slowest test now 6.6 s), so the fake
clock works. Total test time still rose, 279 s to 323 s, but tests this change did not touch got 40-50% slower too (`pdf_generation` 4.4 to
6.6 s), which points to a slower runner, not a regression.

## Verification state of the done items

The changes were made without a running stack, so they have **not** been run here: confirm with `make e2e` (or
`make e2e-docker`) and by the CI run twice on one database. If a spec fails after item 1, suspect one that relied on
the login form's side effects (it landed on the form's `next` target, `/dashboard`, and the helper does too).

# E2E speed-up tracker

Why: the Playwright suite (66 specs, `workers: 1`, run twice in CI) takes long. This file records every
suggestion made (2026-10-21), what was done, and what is still open, so later work can pick up from here.
Coverage must not drop: each item says what it keeps. Timings below are estimates until measured (item 8).

| # | Suggestion | Status | Coverage kept / risk |
| --- | --- | --- | --- |
| 1 | **Sign in through the API, not the form.** `tests/e2e/helpers.ts::login` posts to `/api/auth/login` (what the form calls), then opens `/dashboard`. Saves a page load and hydration on each of ~232 logins (est. 4-8 min). | **Done** | The login form is still driven by `smoke.spec.ts` (login to tabs to logout). Not done: a `storageState` setup project (would save the API call too, but a session revoked by one spec would break the rest). |
| 2 | Run the second CI pass (the re-runnability guard) less often: only on `main` / nightly, or on PRs that touch `tests/e2e/**`. Would halve CI e2e time. | **Open, needs a decision** | `CLAUDE.md` §3 says CI runs the suite twice, so this departs from a rule. Do not change without the user's say-so and a note in §3. |
| 3 | Set up data through the API instead of the UI (projects, items, orders) in the heaviest files: `catalog_supplier_link` (636 lines, 14 tests), `orderbook_layout`, `tracking_layout`. | Open | Review spec by spec; the UI must stay for what the test checks. |
| 4 | Share one page per file for read-only specs (serial `describe` + `beforeAll` page), e.g. `qc_dashboard`. | Open | Trades isolation for a small gain; only after 1 and only where tests share a start state. Keep tests separate for failure granularity. |
| 5 | Parallelism: put read-only / self-contained specs in a separate Playwright project with `workers > 1`; keep stateful ones serial. Or shard CI across jobs. | Open, largest remaining win | Needs an audit of each spec's shared state (specs share data today, `CLAUDE.md` §3); a shard also needs its own database. |
| 6 | CI around the tests. | **Part done** | Done: Playwright browser cached (`actions/cache`, keyed on `apps/web/pnpm-lock.yaml`; a hit still runs `install-deps`). Open: Docker layer cache (buildx + GitHub Actions cache) for `docker compose up --build`; starting the browser install in parallel with the web build. Job names unchanged (they are required checks). |
| 7 | Small clean-ups. | **Part done** | Done: `tracking_layout` pinned-column test polls instead of `waitForTimeout(200)`; `search.spec` retries the `/` shortcut instead of `networkidle`. Kept on purpose: the two `waitForTimeout(500)` in `undo_toast.spec.ts`, which guard that *nothing* is sent after Undo (a negative check needs a wait). Open: lower the many `timeout: 30_000` ceilings (only helps failing runs); check whether `legacy-screenshots` / `screenshot-login` belong in the default CI run. |
| 8 | **Measure first.** `pnpm exec playwright test --reporter=json > report.json`, sort by duration; the slowest 10-15 tests probably dominate. | Open | None of the numbers above has been measured. |

## Verification state of the done items

The changes were made without a running stack, so they have **not** been run here: confirm with `make e2e` (or
`make e2e-docker`) and by the CI run twice on one database. If a spec fails after item 1, suspect one that relied on
the login form's side effects (it landed on the form's `next` target, `/dashboard`, and the helper does too).

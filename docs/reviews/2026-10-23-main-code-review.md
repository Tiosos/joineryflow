# JoineryFlow consolidated code review

**Reviewed revision:** `987318e54bea57b5c9d508dd4cbbd486d4badf08` on `main` (PR #162: Tracking across projects).

**Consolidated:** 23 October 2026.

**Status:** R02/R03 merged in PR #163. The eight remaining findings are implemented and tested; individual changes and final validation are tracked in the [change record](2026-10-23-review-fix-record.md). Original review evidence is retained below.

This document combines `code-review.md`, `additional-code-review.md`, and
`imports-production-review.md` into one review with ten distinct findings:
**six P1 findings and four P2 findings**. Each retains its code location,
reproduction evidence, and recommended correction. Historical labour repricing
appears once, as a confirmed defect following the product owner's decision.

## Scope and confirmed requirements

The review covered the complete 13-file delta from `d555c7b` to the reviewed
revision, including dashboard predicates, role scope, workspace isolation, API
serialization, and navigation. Subsequent passes examined selected authentication,
material-ordering, task, estimating, import, Shop Floor, and costing functions.
This was not an exhaustive audit of every module. The initial pass found no
confirmed regression in the latest dashboard/Tracking change; its findings were
existing defects present on the reviewed revision.

The product owner confirmed:

- JoineryFlow is for **one company's internal use**.
- **Imports and production workflows** are the priority for deeper review.
- **Completed labour must retain its historical rate** when current rates change.
- **Items requiring different painting orders must use separate cutlists**.
  Shared progression through incompatible painting/assembly orders is not the
  intended solution. The detailed handling of existing incompatible cutlists and
  historical-cost backfills is described under R04 and R06. Existing labour
  records with unknown historical rates must remain unresolved and be flagged;
  do not substitute today's rates. No automatic migration or data rewrite has
  been performed.

## Findings index

| ID | Priority | Finding |
| --- | --- | --- |
| [R01](#r01) | P1 | Outstanding-quantity check is not atomic with order creation |
| [R02](#r02) | P1 | Simultaneous edits persist a quote total that differs from its lines |
| [R03](#r03) | P1 | A submitted, locked quote can still be changed by an in-flight edit |
| [R04](#r04) | P1 | Shared cutlists can deadlock painting and assembly |
| [R05](#r05) | P1 | Undo and successor completion are not serialized |
| [R06](#r06) | P1 | Completed labour is repriced using today's rate |
| [R07](#r07) | P2 | Read-only activity does not extend sessions |
| [R08](#r08) | P2 | Task validation uses a snapshot from before acquiring the lock |
| [R09](#r09) | P2 | Estimate-number allocation races and fails after the four-digit boundary |
| [R10](#r10) | P2 | The same CV preview can commit twice in replacement mode |

## Fixes included in this PR

This first implementation addresses **R02 and R03** only. Quote line, part,
hardware, labour, reorder, markup, and terms mutations now acquire the revision
lock before changing data. Child mutations reread their current state after any
lock wait. This serializes edits with total rollups and submission, preserving
consistent totals and refusing edits once submission has locked the revision.

Regression coverage is in
[`test_estimating_revision_races.py`](../../apps/api/tests/test_estimating_revision_races.py).
The other eight findings remain outstanding, including all production/import,
session, task, ordering, estimate-number, and historical-cost changes. Existing
records and historical costs are not rewritten by this PR.

Implementation validation: **2,018 API tests passed** (18 dependency deprecation
warnings, 153.38 seconds), including **13 new regression cases**. All 13 cases
were also run against the original application source and failed there, then
passed with the fix. CI's selected Ruff rules and whitespace checks passed.

<a id="r01"></a>

## R01 — [P1] Outstanding-quantity check is not atomic with order creation

Location: [apps/api/app/material_summaries/queries.py:292](../../apps/api/app/material_summaries/queries.py#L292) (`order_line`).

The summary is read without its supported row lock, `_detail()` computes `qty_to_order` using committed orders, then a new purchase order is inserted. Two transactions can both read the same outstanding quantity and both commit. The existing test checks a second request only after the first commits, so it misses simultaneous buyers.

Reproduced against PostgreSQL in a disposable database: a line requiring one sheet produced two purchase orders totalling two sheets. The probe synchronizes two independent transactions immediately after their real `_detail()` reads; it does not replace the calculation or insertion.

Serialize the calculation and insertion before reading quantities. At least lock the current summary for simultaneous clicks on it. A project/material lock shared by relevant ordering and summary-building paths provides broader protection across different summary versions. Recompute after obtaining the lock, commit the order in that transaction, and add a two-session regression test requiring one success and one NOTHING_TO_ORDER conflict for the same line.

<a id="r02"></a>

## R02 — [P1] Simultaneous edits persist a quote total that differs from its lines

Location: [apps/api/app/estimating/_q_core.py:844](../../apps/api/app/estimating/_q_core.py#L844), called by [apps/api/app/estimating/_q_lines.py:143](../../apps/api/app/estimating/_q_lines.py#L143).

Line-edit functions update their individual lines before acquiring a common revision lock. `_recompute_revision_totals()` aggregates line values in an UPDATE statement that may wait on another editor's revision-row lock. Under PostgreSQL READ COMMITTED the aggregate can still use the statement snapshot from before that other editor committed.

Reproduction uses two database sessions: start with two lines priced at 100 each; transaction A changes its line to 200 and holds its revision update uncommitted; B changes the other line to 200 and waits on the revision update; commit A, then B. The final stored subtotal_sell is **300.00** while the committed lines sum to **400.0000**. Waiting was verified using pg_blocking_pids(), without replacing the financial calculation. The detail loader serves those stored totals, and Convert uses the stored GST-inclusive total as its default contract value.

Acquire the same revision lock before changing any lines/components or computing totals, and hold it through commit. Apply a consistent parent-first lock order across line, part, hardware, labour, markup and submission paths. Test parallel edits of different lines and compare persisted cost, selling and GST totals with a fresh aggregation of the committed lines.

<a id="r03"></a>

## R03 — [P1] A submitted, locked quote can still be changed by an in-flight edit

Location: [apps/api/app/estimating/_q_lines.py:111](../../apps/api/app/estimating/_q_lines.py#L111) (`patch_line`). Related unlocked checks exist in several component mutation helpers and in `patch_revision()`.

The function reads locked_at without locking the revision. Submission correctly locks that revision, but the line edit can read its previously committed unlocked state, change the line, and block only when it reaches the later revision-total UPDATE. After submission commits, the edit completes without repeating the locked check.

Reproduced with the actual transition_revision(target='SUBMITTED') and patch_line() functions: the final revision was SUBMITTED and its line description had been changed to 'Changed after submission'. Numeric line fields use the same path. This permits submitted PDFs and handover data to change without a new revision.

Lock the revision first, then validate locked_at and perform the mutation in that transaction. Add a two-session submission-vs-edit regression expecting REVISION_LOCKED for an edit when submission wins.

<a id="r04"></a>

## R04 — [P1] Shared cutlists can deadlock painting and assembly

Location: [apps/api/app/shop_floor/queries.py:227](../../apps/api/app/shop_floor/queries.py#L227) (`cutlist_prior_stages_done`).

The lifecycle supports painting before assembly and painting after assembly per item, while completing a cutlist stage requires all linked items' prerequisites. A cutlist containing one painted item of each order therefore has a dependency cycle: PAINTED needs MADE for one item, while MADE needs PAINTED for the other.

Reproduced through HTTP assignment/start/complete endpoints: both items had DOWN, CNC and EDGED done; PAINTED completion returned 409 STAGE_OUT_OF_ORDER with missing=[MADE], and MADE completion returned the same error with missing=[PAINTED]. Neither next stage can progress normally.

Existing shared-cutlist tests include different painting orders but exercise individual helpers, not the complete progression through both finish stages.

Resolution confirmed by the user: items requiring different painting orders must use separate cutlists. Validate compatibility when linking or moving an item to a cutlist and when changing its painting settings. Apply the same rule to imports and other paths that create or alter those relationships. Painting-order compatibility concerns items requiring painting; do not unnecessarily separate items that do not require painting. Identify existing incompatible cutlists for an explicit split; do not silently move items or rewrite production history. No implementation has been made during this review.

<a id="r05"></a>

## R05 — [P1] Undo and successor completion are not serialized

Locations: [apps/api/app/shop_floor/routes.py:534](../../apps/api/app/shop_floor/routes.py#L534) (undo guard) and the prior-stage check in `complete_assignment_route`.

Completion locks its own assignment, but undo and completion do not take a common cutlist lock. Each can validate against the state before the other transaction commits.

Reproduced: start CNC completion after DOWN was complete, pause immediately after the real prior-stage query returned no missing stages, then undo DOWN through HTTP, then allow CNC completion to proceed. Both operations succeeded. The final item_stages rows had DOWN.done_date=NULL and CNC.done_date set. The probe changes scheduling only, not query results.

Acquire a common cutlist lock before validating prerequisites/successors and changing completion projections, using the same lock order in completion, undo and other relevant stage-mutating paths. Add a concurrent completion-vs-undo test requiring a valid ordered final state.

<a id="r06"></a>

## R06 — [P1] Completed labour is repriced using today's rate

Location: [apps/api/app/project_contracts/actual_costs.py:65](../../apps/api/app/project_contracts/actual_costs.py#L65) (`_labour_completions`).

The cost query joins stage_completion_log to the current workspace_labour_rate. It does not use a rate effective at the completion or a stored historical rate. This violates the user's explicitly confirmed requirement.

Reproduced through the actual-costs API: the same two completed hours cost 200.00 at a 100/hour rate; after changing only the current rate to 250/hour, the API reported 500.00 for the already-completed work.

Persist the applicable rate or cost on completion, or maintain an effective-dated rate history and select the historical rate. Rate changes must affect subsequent work without rewriting completed costs. Existing completions need an explicit backfill policy: the current schema alone cannot establish their original rates accurately.

<a id="r07"></a>

## R07 — [P2] Read-only activity does not extend sessions

Location: [apps/api/app/auth/sessions.py:72](../../apps/api/app/auth/sessions.py#L72) (`lookup_session`), together with [apps/api/app/db.py:8](../../apps/api/app/db.py#L8) (`get_db`).

`lookup_session` updates `last_seen_at` and flushes but does not commit. Read-only routes such as `/auth/me` also do not commit; closing their database session rolls the timestamp update back. A user who remains active through reads can therefore expire 14 days after their last committed mutation/login.

Reproduced: set an otherwise-valid session's last_seen_at to 13 days ago, request `/auth/me` successfully, and read the timestamp through a separate connection. It is unchanged.

There is also a browser-side limit: the cookie receives a 14-day Max-Age at login (`auth/routes.py:43`), and authenticated reads do not renew it. Persist session activity independently of business-transaction rollback and refresh the cookie through a response path visible to the browser, bounded by hard_expires_at. Do not fix this by committing arbitrary partially executed application mutations inside authentication.

<a id="r08"></a>

## R08 — [P2] Task validation uses a snapshot from before acquiring the lock

Location: [apps/api/app/tasks/queries.py:253](../../apps/api/app/tasks/queries.py#L253) (`patch_task`), particularly its version-only lock at line 294.

The function reads the task and checks status, ownership and assignment before obtaining FOR UPDATE. After waiting, it refreshes only field_versions; all business decisions still use the old task. A concurrently completed task can be edited despite the normal TASK_CLOSED guard. Expected versions for the edited title do not prevent this because closing changes the status version, not the title version.

Reproduced: transaction A locks and completes a task; transaction B reads its previously committed open state and blocks on the lock; A commits; B succeeds and changes the title of the completed task. The same stale snapshot pattern affects authorization after reassignment and the current_value returned in conflicts.

Lock and read the current task before validating its mutable status/ownership/target, or fully refresh and repeat validation after acquiring the lock. Add a deterministic two-session test expecting TASK_CLOSED when completion wins the race.

<a id="r09"></a>

## R09 — [P2] Estimate-number allocation races and fails after the four-digit boundary

Location: [apps/api/app/estimating/_q_core.py:153](../../apps/api/app/estimating/_q_core.py#L153) (`_next_estimate_no`).

The next number is derived from the lexicographically greatest existing estimate_no, without coordinating creators. Two simultaneous creates both allocate the same number. One raises IntegrityError; the HTTP handler translates this to 409 DUPLICATE_ESTIMATE_NO, so a valid create fails because of an identifier the server assigned. The probe reproduced one success and one IntegrityError.

There is also a deterministic boundary error: with EST-2026-9999 and EST-2026-10000 already present, the function returns EST-2026-10000 again because '9999' sorts after '10000'. Normal creation then repeatedly conflicts instead of advancing to 10001.

Use an atomic numeric counter keyed by workspace/year, or another transaction-safe allocator. Preserve existing identifiers. Test parallel creation and the 9999/10000/10001 boundary.

<a id="r10"></a>

## R10 — [P2] The same CV preview can commit twice in replacement mode

Location: [apps/api/app/cv/routes.py:285](../../apps/api/app/cv/routes.py#L285) (`commit_cv_import_route`).

The route loads the import run and checks status=preview before obtaining the item lock. Two requests can both pass that check. The second waits for the item lock, then proceeds using its stale run without repeating the status check. In replace mode it deletes the modules just imported by the first request and imports again.

Reproduced with the real route handler in two independent database sessions and a barrier after the real get_run() reads: both calls succeeded and each created one part; the same run had two cv.import.commit audit events and one cv.import.replace_wipe event. A committed run should have been rejected with RUN_NOT_PENDING on the second call.

After obtaining the item lock, reload and validate the run, or atomically claim a pending run under a consistent locking order before destructive replacement. Test concurrent commits of the same run with replace=true.

## Validation and evidence

These are the results recorded during the review passes. The focused suites
are subsets of the repository tests and **must not be added to the full-suite
count**.

| Check | Result |
| --- | --- |
| Full API suite on the reviewed revision | **2,005 passed**, 18 deprecation warnings, 166.52 seconds; no failures or skips reported |
| Focused dashboard/Tracking/session tests | **20 passed** |
| Estimating suites | **179 passed**, 2 dependency deprecation warnings, 49.44 seconds |
| CV, Shop Floor, tracking/order/catalog importers, and actual-cost suites | **188 passed**, 4 dependency deprecation warnings, 15.24 seconds |
| TypeScript checking | Passed |
| CI's selected Ruff rules (`F401`, `F841`, `F811`) | Passed |
| Additional PostgreSQL probes | Reproduced the failures described in R01–R10, including the estimate-number boundary |

The probes created, migrated, and seeded uniquely named disposable PostgreSQL
databases and dropped them afterward. Concurrency probes controlled scheduling
without replacing the relevant query results or financial calculations. Passing
existing suites do not cover the failing scenarios documented above.

Production builds and browser tests were not rerun during these review passes.
Earlier environment onboarding encountered network restrictions for Google Fonts
and Playwright downloads. UI and production-build validation therefore remain
outside the evidence supporting this review.

### Local evidence artifacts

The following artifacts are retained in the review workspace under
`/workspace/.joineryflow/`. They are local evidence, **not files included in this
documentation PR**. The finding descriptions above are self-contained; PR readers
do not need these local files to understand the reproductions.

| Review pass | Reproducer | Results and test logs |
| --- | --- | --- |
| Initial review (R01, R07, R08) | `review_checks.py` | `review-findings.log`, `fresh-main-tests.log`, `fresh-main-tsc.log` |
| Estimating (R02, R03, R09) | `additional_review_checks.py` | `additional-review-findings.log`, `additional-review-tests.log` |
| Imports and production (R04, R05, R06, R10) | `production_review_checks.py` | `production-review-findings.log`, `production-review-tests.log` |

## Change status

R02 and R03 have a focused implementation and regression tests in this PR.
No dependency changes, schema migrations, or existing-data rewrites are included.
The remaining eight findings and their regression coverage are still outstanding.
Original review validation above describes the pre-fix revision; the PR description
records validation of this implementation. Source line references describe the
reviewed revision and may move in subsequent commits.

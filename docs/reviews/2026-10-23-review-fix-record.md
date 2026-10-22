# Review fix change record

Review: [consolidated findings](2026-10-23-main-code-review.md).

PR [#163](https://github.com/Tiosos/joineryflow/pull/163) merged R02/R03 into
`main` at `41990eac7396443e5378c8d94280f57a749d1072`. Its CI passed 2,018 API
tests, 221 browser tests, lint and typechecking. The follow-up fixes below are
implemented sequentially, with a separate commit and validation record per finding.

Confirmed requirements: one company internally; incompatible painting orders
require separate cutlists; future labour completions retain their applicable
rate; existing completions without a historical rate remain unresolved and are
flagged rather than assigned today's rate.

| Finding | Status |
| --- | --- |
| R01 — summary ordering | Implemented and tested |
| R04 — incompatible painting orders | Implemented and tested |
| R05 — completion versus undo | Implemented and tested |
| R06 — historical labour costs | Implemented and tested |
| R07 — sliding sessions | Implemented and tested |
| R08 — task mutation validation | Pending |
| R09 — estimate numbering | Pending |
| R10 — CV import replay | Pending |

## R01 — Serialize automatic summary orders and summary replacement

The project row is locked before building a replacement summary or calculating
an order from a summary line. Ordering then locks and reloads the summary before
checking that it is current and recomputing quantities. Two concurrent automatic
orders cannot both purchase the same outstanding quantity, and a new summary
cannot bypass the check by using a different summary-row lock.

Validation: both new PostgreSQL concurrency regressions failed before the fix.
After the fix, material-summary and material-take suites passed **55 tests**;
selected Ruff rules and whitespace checks passed. No schema or existing-data
changes. Ordinary manually entered orders keep their existing behaviour.

## R04 — Require compatible painting orders within a cutlist

Links, direct painting edits, approved Controlled-Lock requests and restores
reject `PAINT_ORDER_CONFLICT` when painted items would require opposite orders.
A project-scoped transaction advisory lock is acquired before item locks, so
concurrent changes to different items cannot jointly introduce a cycle.
Unpainted items can still share a cutlist. Existing incompatible cutlists are
preserved and flagged by `paint_order_conflict` on list/detail responses; unlink
and separate-cutlist linking remain available for an explicit split.

The tracking importer does not import painting flags (new items default to no
painting), quote conversion creates separate cutlists, and duplication creates
a new cutlist. None can introduce opposite painting orders through its current
inputs. No production history is rewritten and no migration is required.

Validation: six new regressions failed against the original source, then all
**84 tests** across cutlists, shared production, soft deletion and item locks
passed. Ruff and whitespace checks passed.

## R05 — Serialize completion and undo across a cutlist

Completion and undo acquire the same workspace-scoped cutlist row lock before
assignment/item mutations and lifecycle validation. Assignment and completion
log state are refreshed after waiting. An undo cannot clear an earlier stage
while a concurrent successor completes; the operation waiting second sees the
new progress and receives the existing appropriate 409. Double undo sees
`ALREADY_UNDONE` rather than reapplying a stale log.

Validation: all three concurrency regressions failed before the fix. The
shop-floor routes, shared-cutlist and lifecycle suites passed **52 tests**
afterwards; Ruff and whitespace checks passed. No schema/data migration.

## R06 — Capture completion rates; flag unresolved historical costs

Migration `0083` adds nullable `hourly_rate_snapshot` with no default or backfill.
New completion inserts capture the workspace/stage rate atomically in the same
SQL statement; a missing rate remains null, while an explicit zero is valid.
Actual costs use only recorded rates. Unresolved rates or start times make
labour/total actuals and affected item amounts null, with a completion count;
the Financials card explains the unavailable amounts. Materials remain visible.
Existing test fixtures with known costs now supply their known snapshot explicitly.

Validation: four new regressions failed with the schema present but unfixed
application code. **49 API tests** across actual costs, contracts and production
passed after the fix. Migration applied successfully; web typecheck and production
build passed, along with Ruff and whitespace checks. Existing completions remain
unresolved by design; this release does not guess rates or offer a backfill UI.

## R07 — Persist read activity and renew browser sessions safely

Authentication uses its own short database transaction, locking and validating
the session before committing its activity timestamp. Business writes keep their
own transaction and can roll back independently. Successful authenticated API
responses renew the HttpOnly/SameSite cookie to the earlier of the sliding
window and hard expiry. The existing Next API proxy forwards these Set-Cookie
headers to the browser; server-component fetches alone cannot update browser
cookies. Login applies the same configured lifetime bound. Invalid sessions
are refused without renewal; logout still clears the cookie.

Validation: three new regressions failed before the fix, covering read activity,
cookie renewal capped at two hours and rollback isolation. All **16 authentication
and session tests** passed, including revoked, inactive, sliding-expired and
hard-expired cases; Ruff and whitespace checks passed. No schema migration.

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
| R05 — completion versus undo | Pending |
| R06 — historical labour costs | Pending |
| R07 — sliding sessions | Pending |
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

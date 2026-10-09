# Archive

Design specs and implementation plans written before each sub-project was built, **one file per feature** (spec first, then its plan; Cabinet Vision holds three plans). They are a record of intent at one moment, **not** a description of the current code. Originally `docs/superpowers/specs/` and `plans/`; merged here in October 2026.

- What is true now: `CLAUDE.md` and `docs/sub-projects/`.
- The roadmap: `docs/plan-v1/`.

## Files

- `2026-04-22-foundation.md` — Foundation
- `2026-04-25-pm-workbench.md` — PM Workbench
- `2026-04-28-procurement-workbench.md` — Procurement Workbench
- `2026-05-01-shop-drawings.md` — Shop Drawings
- `2026-05-02-isample.md` — iSample
- `2026-05-02-pdf-generation.md` — PDF generation
- `2026-05-05-cabinet-vision.md` — Cabinet Vision (7a catalog, 7b CV import, 7c cut floor)
- `2026-05-05-shop-floor.md` — Shop Floor
- `2026-05-09-cutplan-optimiser.md` — CutPlan optimiser
- `2026-05-26-estimating.md` — Estimating
- `2026-05-27-item-project-detail-2-0.md` — Item & Project Detail 2.0
- `2026-05-27-tracking-2-0.md` — Tracking 2.0
- `2026-09-18-cutlist-related-parts-orderbook.md` — Cutlist, related parts, Orderbook
- `2026-09-24-material-take.md` — Material Take
- `2026-09-24-search.md` — Global Search

## How to read a plan
### Every plan carries a status header

The first thing under the H1 is a blockquote saying whether the plan has
shipped, which migration(s) it introduced, and where current state is
recorded:

```markdown
# <Plan title>

> **Status: shipped.** Migration `00NN`. Current state lives in
> `## <section>` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/archive/README.md`).
```

Use `**Status: in progress.**` or `**Status: not started.**` while a plan is
live, and update it at merge. A plan without a status header is a bug — a
reader has no way to tell a design from a description of shipped code, and
[that has already caused real trouble][1].

When something later contradicts the plan, add a `> **Later change:** …`
blockquote under the status header rather than editing the body. The body is
the design record of a moment; the header is what is true now.

[1]: `2026-05-09-cutplan-optimiser.md`, which claimed for three months that
     sub-project #9 was unbuilt after it had shipped and been superseded.

### Checkboxes are not the progress signal

The long-form plans use `- [ ]` step syntax, and across the eight of them
**866 boxes are unticked, including for work that shipped months ago.** Nobody
ticks them at merge, so an unticked box means nothing. Ticking them all
retroactively would be busywork with no reader benefit, so the convention is
the status header instead: one line to maintain, at the top, where it is seen.

If you do work a plan task-by-task, ticking as you go is welcome — just don't
treat the absence of ticks in an old plan as evidence of anything.

### Two formats, both fine

- **Long-form** (#1–#7b, 1.2k–4.7k lines): full code for each task, verify
  steps, checkboxes. Written to be executed by an agent task-by-task.
- **Summary** (#7c, #8, #9, #9a, ~140 lines): task list, binding decisions,
  status machines, out-of-scope. Written for a reader who will make their own
  implementation choices.

Pick per sub-project. The summary form has held up better as a *reference*
after the fact — the long-form plans embed code that drifts from the tree the
moment anyone edits it.

### Shipped-state records

Two plans (`2026-05-09-cutplan-optimiser.md`, `2026-05-26-estimating.md`) were
written *after* the code, to backfill a design record for work that shipped
without one. They are labelled as such in their headers. They explain **why**
the code reads as it does; `CLAUDE.md` remains the statement of **what** is
currently true. When the two disagree, the code is right and both docs are
wrong.

### What is not covered here

Migration `0010` (item_edit_log reshape) has no plan or spec. `CLAUDE.md` is
its only written reference.

> **Merged files.** Each feature file keeps its spec and plan(s) as parts. The status header a plan carries sits under that part's own heading (`### …`), not under the file's H1.

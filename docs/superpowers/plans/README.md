# Implementation plans — how to read and write them

## Every plan carries a status header

The first thing under the H1 is a blockquote saying whether the plan has
shipped, which migration(s) it introduced, and where current state is
recorded:

```markdown
# <Plan title>

> **Status: shipped.** Migration `00NN`. Current state lives in
> `## <section>` in `CLAUDE.md`;
> the task checkboxes below were never ticked and are not a progress signal
> (see `docs/superpowers/plans/README.md`).
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

## Checkboxes are not the progress signal

The long-form plans use `- [ ]` step syntax, and across the eight of them
**866 boxes are unticked, including for work that shipped months ago.** Nobody
ticks them at merge, so an unticked box means nothing. Ticking them all
retroactively would be busywork with no reader benefit, so the convention is
the status header instead: one line to maintain, at the top, where it is seen.

If you do work a plan task-by-task, ticking as you go is welcome — just don't
treat the absence of ticks in an old plan as evidence of anything.

## Two formats, both fine

- **Long-form** (#1–#7b, 1.2k–4.7k lines): full code for each task, verify
  steps, checkboxes. Written to be executed by an agent task-by-task.
- **Summary** (#7c, #8, #9, #9a, ~140 lines): task list, binding decisions,
  status machines, out-of-scope. Written for a reader who will make their own
  implementation choices.

Pick per sub-project. The summary form has held up better as a *reference*
after the fact — the long-form plans embed code that drifts from the tree the
moment anyone edits it.

## Shipped-state records

Two plans (`2026-05-09-cutplan-optimiser.md`, `2026-05-26-estimating.md`) were
written *after* the code, to backfill a design record for work that shipped
without one. They are labelled as such in their headers. They explain **why**
the code reads as it does; `CLAUDE.md` remains the statement of **what** is
currently true. When the two disagree, the code is right and both docs are
wrong.

## What is not covered here

Migration `0010` (item_edit_log reshape) has no plan or spec. `CLAUDE.md` is
its only written reference.

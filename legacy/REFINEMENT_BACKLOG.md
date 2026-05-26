# Legacy Refinement Backlog

Items deferred from the 2026-05-10 alignment pass. Listed by leverage (highest first).
Items 1–3 (`make legacy-screenshots`, drift-check script, `_chrome.js` extraction) shipped in the same pass.

---

## 4. Fix `make migrate` recipe robustly

**Problem.** `db/alembic.ini` lives at `/db` inside the api container, but the canonical place is repo-root or `apps/api/`. Current Makefile recipe was patched to `docker compose exec -w /db api alembic upgrade head` — the `-w /db` workaround papers over a structural issue.

**Proposal.** Move `db/alembic.ini` → `apps/api/alembic.ini` (or repo-root `alembic.ini`) and update `script_location` to point at `db/versions/`. Then the recipe becomes plain `docker compose exec api alembic upgrade head`.

**Why it matters.** First-time setup is the fragile path. Eliminating the `-w` flag means a fresh clone runs `make up && make migrate && make seed` clean.

**Effort.** ~30 min. One file move + 1 line edit in `alembic.ini` + 1 line edit in Makefile.

---

## 5. Promote rich palette tokens into `apps/web/app/globals.css`

**Problem.** The legacy hi-fi tokens include richer slots that the live app strips down:

| Legacy token | In live `globals.css`? |
|---|---|
| `--h-good-soft`, `--h-warn-soft`, `--h-bad-soft`, `--h-info-soft` | NO |
| `--h-line2`, `--h-surface-deep` | NO |
| `--h-accent-deep` | NO |
| `--h-ink4` | yes (just barely) |

The 4 refined HTML mockups quietly assume the richer tokens. When a future live page wants the same status-pill softening, it has to hand-code `rgba()` values instead of using the canonical token.

**Proposal.** Add the 7 missing tokens to `apps/web/app/globals.css` `:root` and the `@theme inline` block, then mirror them into `apps/web/lib/tokens.ts`.

**Why it matters.** Single source of truth for colour. Stops the legacy mocks and the live app from drifting tokens.

**Effort.** ~20 min. Strictly additive; no risk of breaking existing styles.

---

## 6. `/dev/legacy` route inside `apps/web` (Storybook-lite)

**Proposal.** A dev-only Next.js route at `/dev/legacy` (gated by `NODE_ENV !== 'production'` or a `NEXT_PUBLIC_DEV_TOOLS` flag) that iframes each legacy mock side-by-side with its live counterpart. Designers can A/B-compare visual fidelity without browser-tabbing.

**Layout sketch.**

```
+----------------------------------+----------------------------------+
| <iframe src="/legacy/tracking_…">| <iframe src="/tracking?project…">|
| Legacy mock                      | Live screen                      |
+----------------------------------+----------------------------------+
```

Plus a header bar with mock-picker dropdown and viewport buttons (375 / 768 / 1440).

**Why it matters.** Closes the loop between mock and shipped UI. Shifts visual review from "open both files manually" to a single URL.

**Effort.** ~2–3 hours. New route segment, iframe wrapper component, viewport state.

---

## 7. Print stylesheet for the 4 mockups

**Proposal.** Add `@media print { ... }` blocks to `home.html`, `tracking_dashboard.html`, `drafter_item_editor.html`, `procurement_orderbook_dashboard.html` that:
- Hide the topbar + secondary nav (`.h-topbar { display: none; }`).
- Force light backgrounds (`background: white !important;`).
- Avoid page-break inside `.card` / `.metric` / `tr`.
- Set page size to A4 landscape for tables, A4 portrait for the dashboards.

**Why it matters.** PDF export becomes a "Print → Save as PDF" away. Useful for client / stakeholder handoffs.

**Effort.** ~1 hour. Mostly CSS.

---

## 8. Mobile-responsive pass on tracking + procurement

**Problem.** Both files assume a ≥1100 px viewport. The live `apps/web` has at least one breakpoint (`@media(max-width:1100px)` for the home dashboard 2-column → 1-column collapse).

**Proposal.** Add 1–2 breakpoints (768 px, 480 px) to:
- `tracking_dashboard.html`: collapse the 4-column metric grid → 2-column → 1-column; horizontally scroll the items table; hide low-priority columns at 480 px.
- `procurement_orderbook_dashboard.html`: same metric grid collapse; stack the 6 legacy tabs vertically below 768 px.

**Why it matters.** Field staff (Foreman, Machine team) increasingly use phones / tablets. Without breakpoints, the mocks don't read on those devices.

**Effort.** ~2 hours per file.

---

## 9. Dark-mode pass

**Problem.** All 4 mocks are light-only. The live `apps/web` is also light-only currently.

**Proposal.** Defer until the live app introduces a dark mode. When that lands:
- Add `@media (prefers-color-scheme: dark)` blocks to each mock.
- Or migrate to `[data-theme="dark"]` selectors if the live app uses an explicit theme toggle.

**Why it matters.** Future-proofing only — not user-facing today.

**Effort.** ~1 hour per file once the canonical dark palette exists in `globals.css`.

---

## 10. Migrate `procurement_orderbook_dashboard.html` → `procurement_orderbook_v1.html`

**Problem.** The current `procurement_orderbook_dashboard.html` is a pre-Procurement-Workbench-v1 prototype (no `cancelled_at`, no allocations, no over-commit, no SQL-derived status pill). The "Legacy" amber banner + cross-link comment make it honest, but it's misleading as a "current procurement reference".

**Proposal.** Create a fresh `legacy/procurement_orderbook_v1.html` mocking the live model:
- Cross-project queue grouped by supplier (mirrors `apps/web/app/(app)/orderbook/_components/QueueClient.tsx`).
- Project-scoped tabs `materials | batches | catalog` (mirrors `apps/web/app/(app)/projects/[id]/procurement/page.tsx`).
- Soft-cancelled batches show with strikethrough.
- Allocation over-commit pill (409 surface).

Keep the existing legacy file as a historical reference.

**Why it matters.** Gives PMs / drafters a reference doc that matches what they actually click in production.

**Effort.** ~2 hours.

---

## Tracking

When you pick one up, move it into `docs/superpowers/plans/` as a proper implementation plan and link the resulting commit / PR back here.

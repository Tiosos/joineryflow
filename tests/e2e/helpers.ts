import { expect, type Page } from "@playwright/test";

/** Every seeded user shares this dev password (see `make seed`). */
export const PASSWORD = "hartwood-dev";

/** Manager on ALF-001; the default user for specs that do not care who they are. */
export const MANAGER = "rin.park@hartwood.test";

/** Workspace every spec signs in to (the login page hard-codes the same slug). */
const WORKSPACE_SLUG = "hartwood-joinery";

/**
 * Sign in and land on the dashboard. The session comes from `POST /api/auth/login`
 * (the call the login form makes), not from filling the form: it skips a page
 * load and hydration per test, which across the suite is minutes. The form
 * itself is still covered by `smoke.spec.ts`.
 */
export async function login(page: Page, email: string = MANAGER) {
  const resp = await page.request.post("/api/auth/login", {
    data: { workspace_slug: WORKSPACE_SLUG, email, password: PASSWORD },
  });
  expect(resp.ok(), `login as ${email}: ${resp.status()}`).toBeTruthy();
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

/** The Undo window of `components/undo/UndoProvider` (`UNDO_MS`); keep the two in step. */
const UNDO_MS = 10_000;

/**
 * Delete and archive wait out a 10-second Undo window before the request is sent. Call
 * `page.clock.install()` before the page that starts the action loads, then this once the
 * toast is up: it jumps the page's timers instead of waiting the window out in real time.
 */
export async function endUndoWindow(page: Page) {
  await page.clock.fastForward(UNDO_MS);
}

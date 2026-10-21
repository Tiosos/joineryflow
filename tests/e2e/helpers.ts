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

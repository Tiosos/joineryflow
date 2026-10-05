import { expect, type Page } from "@playwright/test";

/** Every seeded user shares this dev password (see `make seed`). */
export const PASSWORD = "hartwood-dev";

/** Manager on ALF-001; the default user for specs that do not care who they are. */
export const MANAGER = "rin.park@hartwood.test";

/** Sign in through the login form and wait for the post-login landing page. */
export async function login(page: Page, email: string = MANAGER) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

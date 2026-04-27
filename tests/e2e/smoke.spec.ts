// preamble:
// callers: discovered by Playwright via apps/web/playwright.config.ts
//   (testDir ../../tests/e2e). Invoked by Makefile targets `e2e` and `e2e-docker`.
// glob: tests/e2e/*.spec.ts.
// data-shape: posts login form { email: string, password: string }; asserts URLs
//   /dashboard and /login plus six tab link labels. No data files.
// user instruction: "You are implementing Task 29 of the JoineryFlow Foundation
//   plan: a Playwright smoke test that exercises the full login → tabs → logout flow."
// /resume-session

import { test, expect } from "@playwright/test";

test("login → six tabs → logout", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');

  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });

  for (const label of [
    "Dashboard",
    "Tracking",
    "List",
    "Shop Dwgs",
    "iSample",
    "Orderbook",
  ]) {
    await expect(page.getByRole("link", { name: label, exact: true })).toBeVisible();
  }

  await page.click('button:has-text("Sign out")');
  await expect(page).toHaveURL(/\/login$/, { timeout: 30_000 });
});

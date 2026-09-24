import { test, expect } from "@playwright/test";

/**
 * Sub-project #11 (E4) — Global Search, end to end against `make seed` with
 * the search-worker running (compose starts it).
 *
 *  - A seeded cutlist number typed in the top bar opens the Cutlist module on
 *    that cutlist: 297830 "SS Bench run (shared)" on ALF-001.
 *  - A misspelt word still finds its record (typo tolerance on titles), and
 *    the results page groups hits into type chips.
 */
async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

test("a cutlist number in the top bar opens that cutlist", async ({ page }) => {
  await login(page);
  // The "/" shortcut is attached on hydration; pressing earlier is a no-op.
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("/");
  const box = page.getByRole("searchbox", { name: "Search", exact: true });
  await expect(box).toBeFocused();
  await box.fill("297830");

  const hit = page.getByRole("option").filter({ hasText: "SS Bench run (shared)" });
  await expect(hit).toBeVisible({ timeout: 15_000 });
  await hit.click();

  await expect(page).toHaveURL(/\/list\?project_id=\d+&cutlist=\d+/);
  await expect(page.getByText("SS Bench run (shared)").first()).toBeVisible();
  await expect(page.locator("span.font-mono", { hasText: "297830" }).first()).toBeVisible();
});

test("a misspelt word still finds its record on the results page", async ({ page }) => {
  await login(page);
  const box = page.getByRole("searchbox", { name: "Search", exact: true });
  await box.fill("stonewroks"); // Corian Stoneworks
  await box.press("Enter");

  await expect(page).toHaveURL(/\/search\?q=stonewroks/);
  await expect(page.getByText("Corian Stoneworks").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: /^Suppliers \d+$/ })).toBeVisible();
});

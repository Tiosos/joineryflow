import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Sub-project #11 (E4) — Global Search, end to end against `make seed` with
 * the search-worker running (compose starts it).
 *
 *  - A seeded cutlist number typed in the top bar opens the Cutlist module on
 *    that cutlist: 297830 "SS Bench run (shared)" on ALF-001.
 *  - A misspelt word still finds its record (typo tolerance on titles), and
 *    the results page groups hits into type chips.
 */
/**
 * Search has no Postgres fallback: with Meilisearch down `GET /search` answers
 * `503 SEARCH_UNAVAILABLE`. Locally that is an environment without the `meili` /
 * `search-worker` services (a bare dev stack, the sandbox), so skip. In CI the
 * stack always has them, so a 503 fails. A reachable but empty or broken index
 * fails everywhere.
 */
async function skipWithoutSearch(page: import("@playwright/test").Page) {
  const res = await page.request.get("/api/search?q=297830");
  if (res.status() !== 503) return;
  // The CI e2e job starts Meilisearch and the search-worker, so a 503 there is a
  // broken stack, not a missing optional service: fail instead of skipping.
  expect(process.env.CI, "Meilisearch is not reachable (503 SEARCH_UNAVAILABLE) in CI").toBeFalsy();
  test.skip(true, "Meilisearch is not reachable (503 SEARCH_UNAVAILABLE)");
}

test("a cutlist number in the top bar opens that cutlist", async ({ page }) => {
  await login(page);
  await skipWithoutSearch(page);
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
  await skipWithoutSearch(page);
  const box = page.getByRole("searchbox", { name: "Search", exact: true });
  await box.fill("stonewroks"); // Corian Stoneworks
  await box.press("Enter");

  await expect(page).toHaveURL(/\/search\?q=stonewroks/);
  await expect(page.getByText("Corian Stoneworks").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: /^Suppliers \d+$/ })).toBeVisible();
});

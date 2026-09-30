import { test, expect, type Page } from "@playwright/test";

/**
 * Deleting a module asks first (Plan V1 §29 module threads, migration 0043): a
 * module's parts and any comments on it go with it, so the confirm dialog says how
 * many — read fresh when it opens. Advisory only: the API does not refuse.
 *
 * The delete itself runs on JO-TP01 (seeded with no modules; cv_import.spec.ts and
 * cv_replace_comments.spec.ts also use it) on a module this spec adds, so nothing
 * seeded elsewhere is touched; the other tests only open the dialog and cancel.
 */
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

/** Go to an item's Cutlist tab by its tracking-row code, by href rather than a
 *  click (a row-link click intermittently did not navigate). */
async function openCutlist(page: Page, code: string) {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  await page.goto(href!);
  await expect(page).toHaveURL(/\/items\/\d+/);
  await page.getByRole("tab", { name: /cutlist/i }).click();
}

test("Delete module names its parts and comments, Cancel keeps it, Delete removes it", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openCutlist(page, "JO-TP01");

  // A module of our own, with one comment on it.
  const added = page.getByRole("button", { name: "New module", exact: true });
  await expect(page.getByRole("button", { name: /\+ Add module/ })).toBeVisible({ timeout: 30_000 });
  const before = await added.count();
  await page.getByRole("button", { name: /\+ Add module/ }).click();
  await expect(added).toHaveCount(before + 1, { timeout: 15_000 });
  const thread = page.getByTestId("module-comments");
  const stamp = Date.now();
  await thread.getByTestId("comment-input").fill(`Delete me ${stamp}`);
  await thread.getByTestId("comment-submit").click();
  await expect(thread.getByText(`Delete me ${stamp}`)).toBeVisible();

  // The warning names what will go — before anything is deleted.
  await page.getByTestId("delete-module").click();
  const dialog = page.getByTestId("delete-module-dialog");
  const impact = dialog.getByTestId("delete-module-impact");
  await expect(impact).toBeVisible({ timeout: 15_000 });
  await expect(impact).toContainText("permanently deletes");
  await expect(impact).toContainText("0 parts");
  await expect(impact).toContainText(/1 comment(?!s)/);

  // Cancel: nothing happens.
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(added).toHaveCount(before + 1);

  // Delete: the module (and its thread) are gone.
  await page.getByTestId("delete-module").click();
  await expect(dialog.getByTestId("delete-module-impact")).toContainText(/1 comment(?!s)/, { timeout: 15_000 });
  await dialog.getByRole("button", { name: "Delete module" }).click();
  await expect(dialog).toHaveCount(0, { timeout: 15_000 });
  await expect(added).toHaveCount(before, { timeout: 15_000 });
  await expect(page.getByText(`Delete me ${stamp}`)).toHaveCount(0);
});

test("the dialog names the parts of a module that has them (Cancel only)", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  await openCutlist(page, "JO-K-101");
  await page.getByTestId("delete-module").click();
  const impact = page.getByTestId("delete-module-impact");
  await expect(impact).toBeVisible({ timeout: 15_000 });
  const parts = Number(((await impact.locator("strong").first().textContent()) ?? "").replace(/\D/g, ""));
  expect(parts).toBeGreaterThanOrEqual(1); // the seeded module has parts
  await page.getByTestId("delete-module-dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("delete-module-dialog")).toHaveCount(0);
  await expect(page.getByTestId("module-comments")).toBeVisible(); // still there
});

test("Delete module says so when it cannot check what the module holds", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test");
  await openCutlist(page, "JO-K-101");
  await page.route("**/api/modules/*/delete-impact", (route) =>
    route.fulfill({ status: 500, body: "boom" }),
  );
  await page.getByTestId("delete-module").click();
  await expect(page.getByTestId("delete-module-check-failed")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("delete-module-impact")).toHaveCount(0);
  await page.getByTestId("delete-module-dialog").getByRole("button", { name: "Cancel" }).click();
});

test("only drafter, manager and admin are offered Delete module", async ({ page }) => {
  for (const email of ["juno.okafor@hartwood.test", "sam.ito@hartwood.test"]) { // editor, viewer
    await page.context().clearCookies();
    await login(page, email);
    await openCutlist(page, "JO-K-101");
    await expect(page.getByTestId("module-comments")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("delete-module")).toHaveCount(0);
  }
});

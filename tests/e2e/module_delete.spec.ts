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

// ── Lock checks (a lock on the item refuses the delete) ────────────────────────
// Each test puts the item back exactly as seeded before it ends (workers: 1, so
// nothing else runs meanwhile).

const itemIdFromUrl = (page: Page) => Number(new URL(page.url()).pathname.split("/")[2]);

test("a Hard Lock disables Delete module for everyone, with the reason; unlocking restores it", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openCutlist(page, "JO-K-101");
  const id = itemIdFromUrl(page);
  const del = page.getByTestId("delete-module");
  await expect(del).toBeEnabled({ timeout: 30_000 });
  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await page.reload();
    await expect(del).toBeDisabled({ timeout: 30_000 }); // even a manager: Hard Lock has no way round
    await expect(page.getByTestId("delete-module-locked")).toContainText("hard-locked");
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await page.reload();
  await expect(del).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByTestId("delete-module-locked")).toHaveCount(0);
});

test("another user's Controlled Lock disables Delete module, except for the owner and managers", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openCutlist(page, "JO-K-103"); // seeded Controlled-Locked, owned by the drafter
  const id = itemIdFromUrl(page);
  const me = await (await page.request.get("/api/auth/me")).json();
  const item = await (await page.request.get(`/api/items/${id}`)).json();
  const seededOwner: number = item.cutlist_owner_id;
  expect(item.item_locked).toBe(true);
  expect(seededOwner).not.toBe(me.id);
  const del = page.getByTestId("delete-module");
  const locked = page.getByTestId("delete-module-locked");

  try {
    // A manager passes another user's Controlled Lock…
    await expect(del).toBeEnabled({ timeout: 30_000 });
    // …and once the manager owns it, the seeded drafter is the one refused.
    const t = await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: me.id } });
    expect(t.ok()).toBe(true);
    await page.context().clearCookies();
    await login(page, "noa.lindqvist@hartwood.test"); // drafter, no longer the owner
    await page.goto(`/items/${id}?tab=cutlist`);
    await expect(del).toBeDisabled({ timeout: 30_000 });
    await expect(locked).toContainText("locked this item");
  } finally {
    await page.context().clearCookies();
    await login(page, "rin.park@hartwood.test");
    await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: seededOwner } });
  }
  // Back with its owner, the drafter can delete again.
  await page.context().clearCookies();
  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto(`/items/${id}?tab=cutlist`);
  await expect(del).toBeEnabled({ timeout: 30_000 });
  await expect(locked).toHaveCount(0);
});

test("a stale page that offered Delete module shows the lock's reason when the server refuses", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  await openCutlist(page, "JO-K-101");
  await page.route("**/api/modules/*", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({ detail: { code: "ITEM_LOCKED", owner_id: 9, owner_name: "Olive Owner" } }),
        })
      : route.continue(),
  );
  await page.getByTestId("delete-module").click();
  const dialog = page.getByTestId("delete-module-dialog");
  await expect(dialog.getByTestId("delete-module-impact")).toBeVisible({ timeout: 15_000 });
  await dialog.getByRole("button", { name: "Delete module" }).click();
  await expect(dialog).toContainText("Olive Owner has locked this item");
  await expect(dialog.getByRole("button", { name: "Delete module" })).toBeEnabled(); // still open, nothing deleted
  await dialog.getByRole("button", { name: "Cancel" }).click();
});

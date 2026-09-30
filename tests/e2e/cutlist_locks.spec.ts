import { test, expect, type Page } from "@playwright/test";

/**
 * Locks on the item refuse every module and part write (`assert_item_content_unlocked`,
 * Plan V1 §12): the Cutlist tab shows why and disables + Add module, + Add row, the
 * part cells, part delete, Import from CV and Delete module. A stale page that still
 * offered a control shows the server's refusal instead.
 *
 * Each test puts the item back exactly as seeded (workers: 1, so nothing else runs
 * meanwhile). Nothing here writes a module or part: refusals are the point.
 */
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

async function openCutlist(page: Page, code: string) {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  await page.goto(href!);
  await expect(page).toHaveURL(/\/items\/\d+/);
  await page.getByRole("tab", { name: /cutlist/i }).click();
}

const itemIdFromUrl = (page: Page) => Number(new URL(page.url()).pathname.split("/")[2]);

/** Every control the lock disables, in one place. */
async function expectWritesDisabled(page: Page, disabled: boolean) {
  const check = disabled ? "toBeDisabled" : "toBeEnabled";
  await expect(page.getByRole("button", { name: /\+ Add module/ }))[check]();
  await expect(page.getByRole("button", { name: /\+ Add row/ }))[check]();
  await expect(page.getByRole("button", { name: /Import from CV/ }))[check]();
  await expect(page.getByTestId("delete-module"))[check]();
  const row = page.locator('[data-testid="part-row"]').first();
  await expect(row.locator('[data-field="part_name"]'))[check]();
  await expect(row.locator('[data-field="qty"]'))[check]();
  await expect(row.getByRole("button", { name: "Delete part" }))[check]();
}

test("a Hard Lock disables every module and part write, with the reason", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openCutlist(page, "JO-K-101");
  const id = itemIdFromUrl(page);
  await expect(page.locator('[data-testid="part-row"]').first()).toBeVisible({ timeout: 30_000 });
  await expectWritesDisabled(page, false);
  await expect(page.getByTestId("cutlist-locked")).toHaveCount(0);
  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await page.reload();
    await expect(page.getByTestId("cutlist-locked")).toContainText("hard-locked", { timeout: 30_000 });
    await expectWritesDisabled(page, true); // even a manager: a Hard Lock has no way round
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await page.reload();
  await expect(page.getByTestId("cutlist-locked")).toHaveCount(0);
  await expectWritesDisabled(page, false);
});

test("another user's Controlled Lock disables the writes, except for the owner and managers", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openCutlist(page, "JO-K-103"); // seeded Controlled-Locked, owned by the drafter
  const id = itemIdFromUrl(page);
  const me = await (await page.request.get("/api/auth/me")).json();
  const item = await (await page.request.get(`/api/items/${id}`)).json();
  const seededOwner: number = item.cutlist_owner_id;
  expect(item.item_locked).toBe(true);
  expect(seededOwner).not.toBe(me.id);
  await expect(page.locator('[data-testid="part-row"]').first()).toBeVisible({ timeout: 30_000 });

  try {
    await expectWritesDisabled(page, false); // a manager passes another user's Controlled Lock
    expect((await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: me.id } })).ok()).toBe(true);
    await page.context().clearCookies();
    await login(page, "noa.lindqvist@hartwood.test"); // drafter, no longer the owner
    await page.goto(`/items/${id}?tab=cutlist`);
    await expect(page.getByTestId("cutlist-locked")).toContainText("locked this item", { timeout: 30_000 });
    await expectWritesDisabled(page, true);
  } finally {
    await page.context().clearCookies();
    await login(page, "rin.park@hartwood.test");
    await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: seededOwner } });
  }
  await page.context().clearCookies();
  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto(`/items/${id}?tab=cutlist`);
  await expect(page.locator('[data-testid="part-row"]').first()).toBeVisible({ timeout: 30_000 });
  await expectWritesDisabled(page, false);
  await expect(page.getByTestId("cutlist-locked")).toHaveCount(0);
});

const refusal = (code: string) => ({
  status: 409,
  contentType: "application/json",
  body: JSON.stringify({ detail: { code, owner_id: 9, owner_name: "Olive Owner" } }),
});

test("a stale page shows the lock's reason and reverts a refused part edit, add and delete", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  await openCutlist(page, "JO-K-101");
  const row = page.locator('[data-testid="part-row"]').first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  const rows = await page.locator('[data-testid="part-row"]').count();
  await page.route("**/api/parts/*", (route) =>
    ["PATCH", "DELETE"].includes(route.request().method())
      ? route.fulfill(refusal("ITEM_LOCKED"))
      : route.continue(),
  );
  await page.route("**/api/modules/*/parts", (route) =>
    route.request().method() === "POST" ? route.fulfill(refusal("ITEM_LOCKED")) : route.continue(),
  );

  // edit: refused, message shown, the cell reverts to what it held
  const cell = row.locator('[data-field="part_name"]');
  const before = await cell.inputValue();
  await cell.fill("changed on a stale page");
  await cell.blur();
  await expect(page.getByText("Olive Owner has locked this item")).toBeVisible({ timeout: 15_000 });
  await expect(row.locator('[data-field="part_name"]')).toHaveValue(before);

  // add: refused, no row appears
  await page.getByRole("button", { name: /\+ Add row/ }).click();
  await expect(page.getByText("Olive Owner has locked this item")).toBeVisible();
  await expect(page.locator('[data-testid="part-row"]')).toHaveCount(rows);

  // delete: refused, the row comes back
  await row.getByRole("button", { name: "Delete part" }).click();
  await expect(page.getByText("Olive Owner has locked this item")).toBeVisible();
  await expect(page.locator('[data-testid="part-row"]')).toHaveCount(rows);
});

test("the CV wizard shows the lock's reason when the server refuses the commit", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openCutlist(page, "JO-TP01");
  await page.route("**/api/items/*/cv-imports/*/commit*", (route) => route.fulfill(refusal("HARD_LOCKED")));
  await page.getByRole("button", { name: /Import from CV/i }).click();
  await page.getByPlaceholder(/Module,Part Name/).fill(
    "Module,Part Name,Qty,Length,Width,Material\n1,Side L,1,720,580,18-PB\n",
  );
  await page.getByRole("button", { name: /^Preview$/ }).click();
  await expect(page.getByText(/Import 1 parts/i)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /^Import$/ }).click();
  await expect(page.getByText(/This item is hard-locked/)).toBeVisible({ timeout: 15_000 });
});

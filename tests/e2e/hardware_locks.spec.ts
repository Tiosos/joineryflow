import { test, expect, type Page } from "@playwright/test";

/**
 * Locks on the item refuse every hardware line write (`assert_item_content_unlocked`,
 * Plan V1 §12): the Hardware tab shows why and disables the pantry's "+", the cart's
 * quantity steppers, note and remove. A stale page that still offered a control shows
 * the server's refusal and reverts the edit. The project catalog ("+ Add from global")
 * belongs to the project, not the item, so it stays available.
 *
 * Each test puts the item back exactly as seeded (workers: 1, so nothing else runs
 * meanwhile). Nothing here writes a hardware line: refusals are the point.
 */
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

async function openHardware(page: Page, code: string) {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  await page.goto(href!);
  await expect(page).toHaveURL(/\/items\/\d+/);
  await page.getByRole("tab", { name: /hardware/i }).click();
  await expect(page.locator('[data-testid="cart-line"]').first()).toBeVisible({ timeout: 30_000 });
}

const itemIdFromUrl = (page: Page) => Number(new URL(page.url()).pathname.split("/")[2]);

/** Every control the lock disables, in one place. */
async function expectWritesDisabled(page: Page, disabled: boolean) {
  const check = disabled ? "toBeDisabled" : "toBeEnabled";
  await expect(page.getByRole("button", { name: "Add", exact: true }).first())[check]();
  const line = page.locator('[data-testid="cart-line"]').first();
  await expect(line.getByRole("button", { name: "+", exact: true }))[check]();
  await expect(line.getByRole("button", { name: "−", exact: true }))[check]();
  await expect(line.getByPlaceholder("Note…"))[check]();
  await expect(line.getByRole("button", { name: "Remove hardware line" }))[check]();
}

test("a Hard Lock disables every hardware control, with the reason", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openHardware(page, "JO-K-101");
  const id = itemIdFromUrl(page);
  await expectWritesDisabled(page, false);
  await expect(page.getByTestId("hardware-locked")).toHaveCount(0);
  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await page.goto(`/items/${id}?tab=hardware`);
    await expect(page.getByTestId("hardware-locked")).toContainText("hard-locked", { timeout: 30_000 });
    await expect(page.locator('[data-testid="cart-line"]').first()).toBeVisible({ timeout: 30_000 });
    await expectWritesDisabled(page, true); // even a manager: a Hard Lock has no way round
    // The project catalog is not the item's to lock.
    await expect(page.getByRole("button", { name: /\+ Add from global/ })).toBeEnabled();
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await page.goto(`/items/${id}?tab=hardware`);
  await expect(page.locator('[data-testid="cart-line"]').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("hardware-locked")).toHaveCount(0);
  await expectWritesDisabled(page, false);
});

test("another user's Controlled Lock disables the hardware controls, except for the owner and managers", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openHardware(page, "JO-K-103"); // seeded Controlled-Locked, owned by the drafter
  const id = itemIdFromUrl(page);
  const me = await (await page.request.get("/api/auth/me")).json();
  const item = await (await page.request.get(`/api/items/${id}`)).json();
  const seededOwner: number = item.cutlist_owner_id;
  expect(item.item_locked).toBe(true);
  expect(seededOwner).not.toBe(me.id);

  try {
    await expectWritesDisabled(page, false); // a manager passes another user's Controlled Lock
    expect((await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: me.id } })).ok()).toBe(true);
    await page.context().clearCookies();
    await login(page, "noa.lindqvist@hartwood.test"); // drafter, no longer the owner
    await page.goto(`/items/${id}?tab=hardware`);
    await expect(page.getByTestId("hardware-locked")).toContainText("locked this item", { timeout: 30_000 });
    await expect(page.locator('[data-testid="cart-line"]').first()).toBeVisible({ timeout: 30_000 });
    await expectWritesDisabled(page, true);
  } finally {
    await page.context().clearCookies();
    await login(page, "rin.park@hartwood.test");
    await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: seededOwner } });
  }
  await page.context().clearCookies();
  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto(`/items/${id}?tab=hardware`);
  await expect(page.locator('[data-testid="cart-line"]').first()).toBeVisible({ timeout: 30_000 });
  await expectWritesDisabled(page, false);
  await expect(page.getByTestId("hardware-locked")).toHaveCount(0);
});

const refusal = {
  status: 409,
  contentType: "application/json",
  body: JSON.stringify({ detail: { code: "ITEM_LOCKED", owner_id: 9, owner_name: "Olive Owner" } }),
};

test("a stale page shows the lock's reason and reverts a refused hardware edit, add and remove", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  await openHardware(page, "JO-K-101");
  const lines = page.locator('[data-testid="cart-line"]');
  const count = await lines.count();
  const line = lines.first();
  await page.route("**/api/hardware_lines/*", (route) =>
    ["PATCH", "DELETE"].includes(route.request().method()) ? route.fulfill(refusal) : route.continue(),
  );
  await page.route("**/api/items/*/hardware_lines", (route) =>
    route.request().method() === "POST" ? route.fulfill(refusal) : route.continue(),
  );

  // note: refused, message shown, the field reverts
  const note = line.getByPlaceholder("Note…");
  const before = await note.inputValue();
  await note.fill("changed on a stale page");
  await note.blur();
  await expect(page.getByText("Olive Owner has locked this item").first()).toBeVisible({ timeout: 15_000 });
  await expect(note).toHaveValue(before);

  // add from the pantry: refused, no line appears
  await page.getByRole("button", { name: "Add", exact: true }).first().click();
  await expect(page.getByText("Olive Owner has locked this item").first()).toBeVisible();
  await expect(lines).toHaveCount(count);

  // remove: refused, the line comes back
  await line.getByRole("button", { name: "Remove hardware line" }).click();
  await expect(page.getByText("Olive Owner has locked this item").first()).toBeVisible();
  await expect(lines).toHaveCount(count);
});

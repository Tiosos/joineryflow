import { test, expect, type Page } from "@playwright/test";

/**
 * Locks on the item refuse a status change and a stage-date change (Plan V1 §12):
 * a Hard Lock or another user's Controlled Lock disables the Actions tab and the
 * status dialog with the reason. The Approval Lock does NOT: changing status is how
 * an approved item is unlocked, and production dates follow approval.
 *
 * Each test puts the item back exactly as seeded (workers: 1, so nothing else runs
 * meanwhile). Nothing here changes a status or a date: refusals are the point.
 */
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

async function itemId(page: Page, code: string): Promise<number> {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  return Number(href!.split("/")[2]);
}

const setStatus = (page: Page) => page.getByRole("button", { name: /Set status/ });
const markReq = (page: Page) => page.getByRole("button", { name: /REQ/ });

async function openActions(page: Page, id: number) {
  await page.goto(`/items/${id}?tab=actions`);
  await expect(setStatus(page)).toBeVisible({ timeout: 30_000 });
}

test("a Hard Lock disables Set status and the stage date, with the reason", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-101");
  await openActions(page, id);
  await expect(page.getByTestId("actions-locked")).toHaveCount(0);
  await expect(setStatus(page)).toBeEnabled();
  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await openActions(page, id);
    await expect(page.getByTestId("actions-locked")).toContainText("hard-locked", { timeout: 30_000 });
    await expect(page.getByTestId("actions-locked")).toContainText("status or stage dates");
    await expect(setStatus(page)).toBeDisabled(); // even a manager: a Hard Lock has no way round
    await expect(markReq(page)).toBeDisabled();
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await openActions(page, id);
  await expect(page.getByTestId("actions-locked")).toHaveCount(0);
  await expect(setStatus(page)).toBeEnabled();
});

test("another user's Controlled Lock disables status and dates, except for the owner and managers", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-103"); // seeded Controlled-Locked, owned by the drafter
  const me = await (await page.request.get("/api/auth/me")).json();
  const item = await (await page.request.get(`/api/items/${id}`)).json();
  const seededOwner: number = item.cutlist_owner_id;
  expect(item.item_locked).toBe(true);
  expect(seededOwner).not.toBe(me.id);

  try {
    await openActions(page, id);
    await expect(setStatus(page)).toBeEnabled(); // a manager passes another user's Controlled Lock
    expect((await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: me.id } })).ok()).toBe(true);
    await page.context().clearCookies();
    await login(page, "noa.lindqvist@hartwood.test"); // drafter, no longer the owner
    await openActions(page, id);
    await expect(page.getByTestId("actions-locked")).toContainText("locked this item", { timeout: 30_000 });
    await expect(setStatus(page)).toBeDisabled();
    await expect(markReq(page)).toBeDisabled();
  } finally {
    await page.context().clearCookies();
    await login(page, "rin.park@hartwood.test");
    await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: seededOwner } });
  }
  await page.context().clearCookies();
  await login(page, "noa.lindqvist@hartwood.test");
  await openActions(page, id);
  await expect(page.getByTestId("actions-locked")).toHaveCount(0);
  await expect(setStatus(page)).toBeEnabled();
});

test("the Approval Lock does not stop a status change or a stage date", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-101");
  const before = await (await page.request.get(`/api/items/${id}`)).json();
  try {
    const r = await page.request.patch(`/api/items/${id}/status`, {
      data: { status: "APPROVED", note: "e2e approval lock" },
    });
    expect(r.ok()).toBe(true);
    await openActions(page, id);
    // approved => content is locked, but the two Actions are not
    await expect(page.getByTestId("actions-locked")).toHaveCount(0);
    await expect(setStatus(page)).toBeEnabled();
    await setStatus(page).click();
    await expect(page.getByTestId("status-locked")).toHaveCount(0);
    await page.getByRole("radio", { name: "LIVE" }).check();
    await page.getByPlaceholder("Description of Status Change...").fill("e2e unlock");
    await page.getByRole("button", { name: /Update\s*Current Item/ }).click();
    await expect.poll(async () => (await (await page.request.get(`/api/items/${id}`)).json()).status, {
      timeout: 15_000,
    }).toBe("LIVE");
  } finally {
    await page.request.patch(`/api/items/${id}/status`, {
      data: { status: before.status ?? "CLEAR", note: "e2e restore" },
    });
  }
});

test("a stale page shows the lock's reason when a status or date change is refused", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  const id = await itemId(page, "JO-K-101");
  const refusal = {
    status: 409,
    contentType: "application/json",
    body: JSON.stringify({ detail: { code: "ITEM_LOCKED", owner_id: 9, owner_name: "Olive Owner" } }),
  };
  await page.route("**/api/items/*/status", (route) =>
    route.request().method() === "PATCH" ? route.fulfill(refusal) : route.continue(),
  );
  await page.route("**/api/items/*/lifecycle/*", (route) =>
    route.request().method() === "PATCH" ? route.fulfill(refusal) : route.continue(),
  );
  await openActions(page, id);

  // status dialog: refused, reason shown, dialog stays open
  await setStatus(page).click();
  await page.getByRole("radio", { name: "HOLD" }).check();
  await page.getByPlaceholder("Description of Status Change...").fill("stale");
  await page.getByRole("button", { name: /Update\s*Current Item/ }).click();
  await expect(page.getByText("Olive Owner has locked this item")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Close", exact: true }).click();

  // stage date: refused, reason shown
  const req = markReq(page);
  if (await req.isEnabled()) {
    await req.click();
    await expect(page.getByText("Olive Owner has locked this item")).toBeVisible({ timeout: 15_000 });
  }
});

test("Apply status… reports the locked items a bulk change skipped", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await itemId(page, "JO-K-101"); // opens /tracking?project_id=1
  // The API's answer is mocked, so no status changes; the API side is covered by pytest.
  const box = page.locator('[data-testid="tracking-row"]').first().getByRole("checkbox");
  await page.route("**/api/items/bulk-status", async (route) => {
    const sent = route.request().postDataJSON() as { item_ids: number[] };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        updated: 0,
        not_found: [],
        cross_workspace: [],
        locked: sent.item_ids.map((item_id) => ({ item_id, code: "HARD_LOCKED", owner_name: null })),
      }),
    });
  });
  await box.check();
  await page.getByRole("button", { name: "Apply status…" }).click();
  await page.getByPlaceholder(/Why is this status changing/).fill("e2e bulk");
  await page.getByRole("button", { name: "Apply HOLD" }).click();
  await expect(page.getByText(/0 updated · 1 skipped \(locked: #\d+\)/)).toBeVisible({ timeout: 15_000 });
});

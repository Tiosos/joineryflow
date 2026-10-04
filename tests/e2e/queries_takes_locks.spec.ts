import { test, expect, type Page } from "@playwright/test";

/**
 * Locks on the item refuse item-query answers and every material-take write
 * (`assert_item_content_unlocked`, Plan V1 §12): Hard Lock + someone else's Controlled
 * Lock, not the Approval Lock. *Asking* a query answers to the Hard Lock only. The
 * Query and Material Take tabs show why and disable their controls; a stale page that
 * still offered one shows the server's refusal.
 *
 * Seed facts relied on (ALF-001): K-101 has one open and one answered query and an
 * approved take; K-102 has a draft take (re-created by `ensureDraftTake` if another spec
 * approved it); K-103 is Controlled-Locked by the drafter and
 * has an approved take and no queries. Each test puts the item back exactly as seeded
 * (workers: 1). Nothing here writes a query or a take: refusals are the point, and
 * asking is only checked for being *enabled* (clicking it would add a row).
 */
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

/** The item's id, found through the Tracking row for its code (as the other lock specs do). */
async function itemId(page: Page, code: string): Promise<number> {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  return Number(href!.split("/")[2]);
}

async function openQueries(page: Page, id: number) {
  await page.goto(`/items/${id}?tab=query`);
  await expect(page.locator("#new-query-question")).toBeVisible({ timeout: 30_000 });
}

async function openTake(page: Page, id: number) {
  await page.goto(`/items/${id}?tab=take`);
  // a take heading, or the button that starts one — an item may show both
  await expect(
    page.getByRole("heading", { name: /^Take v/ })
      .or(page.getByRole("button", { name: /Generate material take|Start v\d+/ }))
      .first(),
  ).toBeVisible({ timeout: 30_000 });
}

/**
 * Make sure the item has a *draft* take to look at. The seed leaves K-102 with one,
 * but `material_take.spec.ts` (which runs just before this file) approves it for good,
 * and a spec that depends on another having not yet run is a trap. Starting the next
 * version through the API is what the "Start vN" button does, and the controls these
 * tests check only exist on a draft. A no-op when a draft is already there.
 */
async function ensureDraftTake(page: Page, id: number) {
  const current = await (await page.request.get(`/api/items/${id}/material-take`)).json();
  if (current.draft) return;
  const res = await page.request.post(`/api/items/${id}/material-take/generate`);
  expect(res.ok(), `starting a draft take: ${res.status()}`).toBe(true);
}

const ask = (page: Page) => page.getByRole("button", { name: "Ask", exact: true });
const answerBoxes = (page: Page) => page.getByPlaceholder("Write an answer…");

test("a Hard Lock stops answering and asking, and says why", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "K-101");
  await openQueries(page, id);
  await expect(page.getByTestId("queries-locked")).toHaveCount(0);
  await expect(page.locator("#new-query-question")).toBeEnabled();
  await expect(answerBoxes(page).first()).toBeEnabled();

  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await openQueries(page, id);
    await expect(page.getByTestId("queries-locked")).toContainText("hard-locked");
    // asking answers to the Hard Lock too — even a manager has no way round it
    await expect(page.locator("#new-query-question")).toBeDisabled();
    // the button is also disabled while the box is empty, so the lock shows as its reason
    await expect(ask(page)).toBeDisabled();
    await expect(ask(page)).toHaveAttribute("title", /hard-locked/);
    await expect(answerBoxes(page).first()).toBeDisabled();
    await expect(page.getByRole("button", { name: "Answer", exact: true }).first()).toBeDisabled();
    await expect(page.getByRole("button", { name: "Edit answer" }).first()).toBeDisabled();
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await openQueries(page, id);
  await expect(page.getByTestId("queries-locked")).toHaveCount(0);
  await expect(page.locator("#new-query-question")).toBeEnabled();
  await expect(page.getByRole("button", { name: "Edit answer" }).first()).toBeEnabled();
});

test("a Hard Lock disables every material-take control, with the reason", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "K-102"); // seeded draft take
  await ensureDraftTake(page, id);
  await openTake(page, id);
  await expect(page.getByTestId("take-locked")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Regenerate" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Approve" })).toBeEnabled();

  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await openTake(page, id);
    await expect(page.getByTestId("take-locked")).toContainText("hard-locked");
    await expect(page.getByRole("button", { name: "Regenerate" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Approve" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Add line" })).toBeDisabled();
    await expect(page.getByLabel("New line description")).toBeDisabled();
    await expect(page.getByLabel(/^Qty for /).first()).toBeDisabled();
    await expect(page.getByLabel(/^Wastage for /).first()).toBeDisabled();
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await openTake(page, id);
  await expect(page.getByTestId("take-locked")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Regenerate" })).toBeEnabled();
  await expect(page.getByLabel(/^Qty for /).first()).toBeEnabled();
});

test("another user's Controlled Lock stops take writes and answers but not asking; the owner and managers pass", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "K-103"); // seeded Controlled-Locked, owned by the drafter
  const me = await (await page.request.get("/api/auth/me")).json();
  const item = await (await page.request.get(`/api/items/${id}`)).json();
  const seededOwner: number = item.cutlist_owner_id;
  expect(item.item_locked).toBe(true);
  expect(seededOwner).not.toBe(me.id);

  try {
    // a manager passes another user's Controlled Lock
    await openTake(page, id);
    await expect(page.getByTestId("take-locked")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Start v\d+/ })).toBeEnabled();

    // hand the lock to the manager: the drafter is now "someone else"
    expect((await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: me.id } })).ok()).toBe(true);
    await page.context().clearCookies();
    await login(page, "noa.lindqvist@hartwood.test"); // drafter, no longer the owner

    await openTake(page, id);
    await expect(page.getByTestId("take-locked")).toContainText("locked this item");
    await expect(page.getByRole("button", { name: /Start v\d+/ })).toBeDisabled();

    // Asking answers to the Hard Lock only, so the form stays open under a Controlled Lock
    await openQueries(page, id);
    await expect(page.getByTestId("queries-locked")).toContainText("locked this item");
    await expect(page.locator("#new-query-question")).toBeEnabled();
    await page.locator("#new-query-question").fill("Is this still wanted?");
    await expect(ask(page)).toBeEnabled();
    await page.locator("#new-query-question").fill(""); // not sent: it would add a row
  } finally {
    await page.context().clearCookies();
    await login(page, "rin.park@hartwood.test");
    await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: seededOwner } });
  }
  await page.context().clearCookies();
  await login(page, "noa.lindqvist@hartwood.test");
  await openTake(page, id);
  await expect(page.getByTestId("take-locked")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Start v\d+/ })).toBeEnabled();
});

const refusal = {
  status: 409,
  contentType: "application/json",
  body: JSON.stringify({ detail: { code: "ITEM_LOCKED", owner_id: 9, owner_name: "Olive Owner" } }),
};

test("a stale page shows the lock's reason and reverts a refused take edit, and keeps a refused answer", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  const takeItem = await itemId(page, "K-102");
  await ensureDraftTake(page, takeItem);
  await openTake(page, takeItem);
  await page.route("**/api/material-takes/*/lines/*", (route) =>
    route.request().method() === "PATCH" ? route.fulfill(refusal) : route.continue(),
  );
  const qty = page.getByLabel(/^Qty for /).first();
  const before = await qty.inputValue();
  await qty.fill("999");
  await qty.blur();
  await expect(page.getByText("Olive Owner has locked this item").first()).toBeVisible({ timeout: 15_000 });
  await expect(qty).toHaveValue(before); // the refused edit snaps back to what the server holds

  const queryItem = await itemId(page, "K-101");
  await page.route("**/api/queries/*/answer", (route) =>
    route.request().method() === "POST" ? route.fulfill(refusal) : route.continue(),
  );
  await openQueries(page, queryItem);
  const box = answerBoxes(page).first();
  await box.fill("answered on a stale page");
  await page.getByRole("button", { name: "Answer", exact: true }).first().click();
  await expect(page.getByText("Olive Owner has locked this item").first()).toBeVisible({ timeout: 15_000 });
  await expect(box).toHaveValue("answered on a stale page"); // nothing was saved; the text is still there
});

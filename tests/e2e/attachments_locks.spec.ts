import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * Locks on the item refuse every attachment-slot write (`assert_item_content_unlocked`,
 * Plan V1 §12), and the Document Register's (which has no web UI yet — covered by
 * pytest): the Attachments tab shows why and disables Upload / Replace / Delete. A stale
 * page that still offered a control shows the server's refusal.
 *
 * Each test puts the item back exactly as seeded (workers: 1, so nothing else runs
 * meanwhile). Nothing here binds or clears a slot: refusals are the point.
 */
async function itemId(page: Page, code: string): Promise<number> {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  return Number(href!.split("/")[2]);
}

// Not the editor header's own Delete-item button (data-testid="delete-item"), which is on every tab.
const tabButtons = (page: Page) => page.locator('button:not([data-testid="delete-item"])');

const writeButtons = (page: Page) =>
  tabButtons(page).filter({ hasText: /^(Upload|Replace|Uploading…|Replacing…|Delete)$/ });

async function openAttachments(page: Page, id: number) {
  await page.goto(`/items/${id}?tab=attachments`);
  await expect(page.getByRole("heading", { name: "Attachments" })).toBeVisible({ timeout: 30_000 });
  await expect(writeButtons(page).first()).toBeVisible({ timeout: 30_000 });
}

/** Every write control the lock disables, in one place. */
async function expectWritesDisabled(page: Page, disabled: boolean) {
  const buttons = writeButtons(page);
  const n = await buttons.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    if (disabled) await expect(buttons.nth(i)).toBeDisabled();
    else await expect(buttons.nth(i)).toBeEnabled();
  }
}

test("a Hard Lock disables every attachment control, with the reason", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-101");
  await openAttachments(page, id);
  await expect(page.getByTestId("attachments-locked")).toHaveCount(0);
  await expectWritesDisabled(page, false);
  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await openAttachments(page, id);
    await expect(page.getByTestId("attachments-locked")).toContainText("hard-locked", { timeout: 30_000 });
    await expect(page.getByTestId("attachments-locked")).toContainText("attachments");
    await expectWritesDisabled(page, true); // even a manager: a Hard Lock has no way round
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await openAttachments(page, id);
  await expect(page.getByTestId("attachments-locked")).toHaveCount(0);
  await expectWritesDisabled(page, false);
});

test("another user's Controlled Lock disables the attachment controls, except for the owner and managers", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-103"); // seeded Controlled-Locked, owned by the drafter
  const me = await (await page.request.get("/api/auth/me")).json();
  const item = await (await page.request.get(`/api/items/${id}`)).json();
  const seededOwner: number = item.cutlist_owner_id;
  expect(item.item_locked).toBe(true);
  expect(seededOwner).not.toBe(me.id);

  try {
    await openAttachments(page, id);
    await expectWritesDisabled(page, false); // a manager passes another user's Controlled Lock
    expect((await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: me.id } })).ok()).toBe(true);
    await page.context().clearCookies();
    await login(page, "noa.lindqvist@hartwood.test"); // drafter, no longer the owner
    await openAttachments(page, id);
    await expect(page.getByTestId("attachments-locked")).toContainText("locked this item", { timeout: 30_000 });
    await expectWritesDisabled(page, true);
  } finally {
    await page.context().clearCookies();
    await login(page, "rin.park@hartwood.test");
    await page.request.post(`/api/items/${id}/lock`, { data: { owner_id: seededOwner } });
  }
  await page.context().clearCookies();
  await login(page, "noa.lindqvist@hartwood.test");
  await openAttachments(page, id);
  await expect(page.getByTestId("attachments-locked")).toHaveCount(0);
  await expectWritesDisabled(page, false);
});

test("an approved item disables the attachment controls until its status moves off Approved", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-101");
  const before = await (await page.request.get(`/api/items/${id}`)).json();
  try {
    expect((await page.request.patch(`/api/items/${id}/status`, {
      data: { status: "APPROVED", note: "e2e approval lock" },
    })).ok()).toBe(true);
    await openAttachments(page, id);
    await expect(page.getByTestId("attachments-locked")).toContainText("approved", { timeout: 30_000 });
    await expectWritesDisabled(page, true);
  } finally {
    await page.request.patch(`/api/items/${id}/status`, {
      data: { status: before.status ?? "CLEAR", note: "e2e restore" },
    });
  }
  await openAttachments(page, id);
  await expect(page.getByTestId("attachments-locked")).toHaveCount(0);
  await expectWritesDisabled(page, false);
});

const refusal = {
  status: 409,
  contentType: "application/json",
  body: JSON.stringify({ detail: { code: "ITEM_LOCKED", owner_id: 9, owner_name: "Olive Owner" } }),
};

test("a stale page shows the lock's reason when a slot write is refused", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  const id = await itemId(page, "JO-K-101");
  await page.route("**/api/items/*/attachments/*", (route) =>
    ["POST", "DELETE"].includes(route.request().method()) ? route.fulfill(refusal) : route.continue(),
  );
  await openAttachments(page, id);
  const message = page.getByText("Olive Owner has locked this item");

  // delete: refused, message shown, nothing removed
  page.once("dialog", (d) => d.accept());
  await tabButtons(page).filter({ hasText: "Delete" }).first().click();
  await expect(message.first()).toBeVisible({ timeout: 15_000 });

  // upload / replace: the file is stored, the bind is refused
  const pdf = Buffer.from("%PDF-1.4\n%e2e lock refusal\n" + "x".repeat(100) + "\n%%EOF\n");
  await page.locator('input[type="file"]').first().setInputFiles({
    name: "e2e-lock.pdf", mimeType: "application/pdf", buffer: pdf,
  });
  await expect(message.first()).toBeVisible({ timeout: 15_000 });
});

import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * The Document Register section of the item editor's Attachments tab: list, add,
 * relabel, reorder and remove, gated on `list:write` (editors included — unlike the
 * attachment slots) and on the item's locks (Hard, Approval, Controlled).
 *
 * Each test puts the item back exactly as seeded (workers: 1, so nothing else runs
 * meanwhile): documents a test adds are removed again, and locks are restored.
 */
async function itemId(page: Page, code: string): Promise<number> {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  return Number(href!.split("/")[2]);
}

const register = (page: Page) => page.getByTestId("document-register");
const rows = (page: Page) => register(page).getByTestId("register-row");
const addButton = (page: Page) => register(page).getByRole("button", { name: /^(Add document|Working…)$/ });

async function openAttachments(page: Page, id: number) {
  await page.goto(`/items/${id}?tab=attachments`);
  await expect(register(page)).toBeVisible({ timeout: 30_000 });
  await expect(register(page).getByText("Loading…")).toHaveCount(0, { timeout: 30_000 });
}

async function docs(page: Page, id: number): Promise<{ document_id: number; label: string | null; sort_order: number }[]> {
  return (await page.request.get(`/api/items/${id}/documents`)).json();
}

const pdf = (tag: string) => ({
  name: `e2e-${tag}.pdf`,
  mimeType: "application/pdf",
  buffer: Buffer.from(`%PDF-1.4\n%e2e register ${tag} ${Date.now()}\n` + "x".repeat(100) + "\n%%EOF\n"),
});

test("a drafter adds, relabels, reorders and removes a document", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  const id = await itemId(page, "JO-K-101");
  await openAttachments(page, id);
  const before = await docs(page, id);
  await expect(rows(page)).toHaveCount(before.length);

  let added: number | null = null;
  try {
    // add: appended after the last existing document
    await register(page).locator('input[type="file"]').setInputFiles(pdf("add"));
    await expect(rows(page)).toHaveCount(before.length + 1, { timeout: 15_000 });
    const afterAdd = await docs(page, id);
    added = afterAdd.find((d) => !before.some((b) => b.document_id === d.document_id))!.document_id;
    expect(afterAdd[afterAdd.length - 1].document_id).toBe(added);

    // relabel: commit on Enter, persisted
    const last = rows(page).last();
    await last.getByLabel("Document label").fill("E2E label");
    await last.getByLabel("Document label").press("Enter");
    await expect.poll(async () => (await docs(page, id)).find((d) => d.document_id === added)?.label, {
      timeout: 15_000,
    }).toBe("E2E label");

    // an unchanged blur writes nothing (no audit row for a bare tab-through)
    const editsBefore = await (await page.request.get(`/api/items/${id}/documents`)).json();
    await rows(page).last().getByLabel("Document label").focus();
    await rows(page).last().getByLabel("Document label").blur();
    expect(await docs(page, id)).toEqual(editsBefore);

    // reorder: move the new row up one place
    if (before.length > 0) {
      await rows(page).last().getByRole("button", { name: "Move up" }).click();
      await expect.poll(async () => (await docs(page, id)).map((d) => d.document_id), {
        timeout: 15_000,
      }).toEqual([
        ...before.slice(0, -1).map((d) => d.document_id),
        added,
        before[before.length - 1].document_id,
      ]);
      await expect(rows(page).nth(before.length - 1).getByLabel("Document label")).toHaveValue("E2E label");
    }
  } finally {
    if (added != null) await page.request.delete(`/api/documents/${added}`);
    // a reorder renumbers the whole list: put every seeded document's sort_order back
    for (const d of before) {
      await page.request.patch(`/api/documents/${d.document_id}`, { data: { sort_order: d.sort_order } });
    }
  }

  // remove through the UI on a fresh add, confirm dialog accepted. Reload first: the list on
  // screen still holds the row the cleanup above deleted through the API, and acting on a
  // stale row would remove a seeded document instead.
  await openAttachments(page, id);
  await register(page).locator('input[type="file"]').setInputFiles(pdf("remove"));
  const target = rows(page).filter({ hasText: "e2e-remove.pdf" });
  await expect(target).toHaveCount(1, { timeout: 15_000 });
  page.once("dialog", (d) => d.accept());
  await target.getByRole("button", { name: "Remove" }).click();
  await expect(target).toHaveCount(0, { timeout: 15_000 });
  expect((await docs(page, id)).map((d) => d.document_id)).toEqual(before.map((d) => d.document_id));
});

test("an editor can write the register though not the attachment slots; a viewer only reads", async ({ page }) => {
  await login(page, "juno.okafor@hartwood.test"); // editor
  const id = await itemId(page, "JO-K-101");
  await openAttachments(page, id);
  await expect(addButton(page)).toBeEnabled();
  await expect(page.getByRole("button", { name: /^(Upload|Replace)$/ })).toHaveCount(0); // slots: drafter+

  await page.context().clearCookies();
  await login(page, "sam.ito@hartwood.test"); // viewer
  await openAttachments(page, id);
  await expect(rows(page).first()).toBeVisible();
  await expect(register(page).getByRole("link", { name: "Open" }).first()).toBeVisible();
  await expect(addButton(page)).toHaveCount(0);
  await expect(register(page).getByRole("button", { name: /Remove|Move/ })).toHaveCount(0);
  await expect(register(page).getByLabel("Document label")).toHaveCount(0);
});

test("a Hard Lock disables every register control, with the reason", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-101");
  await openAttachments(page, id);
  await expect(addButton(page)).toBeEnabled();
  try {
    expect((await page.request.post(`/api/items/${id}/hard-lock`)).ok()).toBe(true);
    await openAttachments(page, id);
    await expect(page.getByTestId("attachments-locked")).toContainText("hard-locked", { timeout: 30_000 });
    await expect(addButton(page)).toBeDisabled(); // even a manager: a Hard Lock has no way round
    const n = await rows(page).count();
    expect(n).toBeGreaterThan(0);
    for (let i = 0; i < n; i++) {
      const row = rows(page).nth(i);
      await expect(row.getByLabel("Document label")).toBeDisabled();
      await expect(row.getByRole("button", { name: "Remove" })).toBeDisabled();
      await expect(row.getByRole("button", { name: "Move up" })).toBeDisabled();
      await expect(row.getByRole("button", { name: "Move down" })).toBeDisabled();
    }
  } finally {
    await page.request.delete(`/api/items/${id}/hard-lock`);
  }
  await openAttachments(page, id);
  await expect(page.getByTestId("attachments-locked")).toHaveCount(0);
  await expect(addButton(page)).toBeEnabled();
});

test("another user's Controlled Lock disables the register for an editor, who gets the notice too", async ({ page }) => {
  await login(page, "juno.okafor@hartwood.test"); // editor, not the owner
  const id = await itemId(page, "JO-K-103"); // seeded Controlled-Locked, owned by the drafter
  await openAttachments(page, id);
  await expect(page.getByTestId("attachments-locked")).toContainText("locked this item", { timeout: 30_000 });
  await expect(addButton(page)).toBeDisabled();
});

const refusal = {
  status: 409,
  contentType: "application/json",
  body: JSON.stringify({ detail: { code: "ITEM_LOCKED", owner_id: 9, owner_name: "Olive Owner" } }),
};

test("a stale page shows the lock's reason when a register write is refused", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  const id = await itemId(page, "JO-K-101");
  await page.route("**/api/items/*/documents", (route) =>
    route.request().method() === "POST" ? route.fulfill(refusal) : route.continue(),
  );
  await page.route("**/api/documents/*", (route) =>
    ["PATCH", "DELETE"].includes(route.request().method()) ? route.fulfill(refusal) : route.continue(),
  );
  await openAttachments(page, id);
  const before = await docs(page, id);
  const message = page.getByText("Olive Owner has locked this item");

  // relabel: refused, message shown, the input shows the server's label again
  const first = rows(page).first().getByLabel("Document label");
  const original = await first.inputValue();
  await first.fill("should not stick");
  await first.press("Enter");
  await expect(message.first()).toBeVisible({ timeout: 15_000 });
  await expect(first).toHaveValue(original);

  // remove: refused, row still there
  page.once("dialog", (d) => d.accept());
  await rows(page).first().getByRole("button", { name: "Remove" }).click();
  await expect(message.first()).toBeVisible({ timeout: 15_000 });
  await expect(rows(page)).toHaveCount(before.length);

  // add: the file is stored, the bind is refused
  await register(page).locator('input[type="file"]').setInputFiles(pdf("refused"));
  await expect(message.first()).toBeVisible({ timeout: 15_000 });
  expect(await docs(page, id)).toEqual(before);
});

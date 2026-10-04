import { test, expect, type Page } from "@playwright/test";

/**
 * Duplicate a Joinery Item (Plan V1 §2): a drafter / manager / admin copies an item from
 * its Actions tab into the same project, with its own Item ID, status CLEAR and a link
 * back to the source. The spec deletes every copy it makes (DELETE /items/{id}) in a
 * `finally`; deleting the copy also removes its own, never-used cutlist, so the seeded
 * project is left as it was.
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

const duplicateButton = (page: Page) => page.getByTestId("duplicate-item");

test("a drafter duplicates an item: new Item ID, status CLEAR, link back to the source", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter
  const id = await itemId(page, "JO-K-101");
  const source = await (await page.request.get(`/api/items/${id}`)).json();
  let copyId: number | null = null;
  try {
    await page.goto(`/items/${id}?tab=actions`);
    await duplicateButton(page).click();
    await expect(page.getByTestId("duplicate-dialog")).toContainText(`#${source.item_number}`);
    await page.getByTestId("duplicate-confirm").click();

    await expect(page).toHaveURL(/\/items\/\d+$/, { timeout: 30_000 });
    copyId = Number(new URL(page.url()).pathname.split("/")[2]);
    expect(copyId).not.toBe(id);

    const copy = await (await page.request.get(`/api/items/${copyId}`)).json();
    expect(copy.item_number).not.toBe(source.item_number);
    expect(copy.status).toBe("CLEAR");
    expect(copy.project_id).toBe(source.project_id);
    expect(copy.duplicated_from_item_id).toBe(id);
    expect(copy.duplicated_from_item_number).toBe(source.item_number);
    expect(copy.description).toBe(source.description);
    expect(copy.modules.length).toBe(source.modules.length);

    await page.goto(`/items/${copyId}?tab=actions`);
    await expect(page.getByTestId("duplicated-from")).toContainText(`#${source.item_number}`, { timeout: 30_000 });
    await page.getByTestId("duplicated-from").click();
    await expect(page).toHaveURL(new RegExp(`/items/${id}$`));
    // the original carries no such link
    await page.goto(`/items/${id}?tab=actions`);
    await expect(duplicateButton(page)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("duplicated-from")).toHaveCount(0);
  } finally {
    if (copyId) await page.request.delete(`/api/items/${copyId}`);
  }
});

test("Cancel closes the dialog and stays on the source item", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test");
  const id = await itemId(page, "JO-K-101");
  await page.goto(`/items/${id}?tab=actions`);
  await duplicateButton(page).click();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("duplicate-dialog")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`/items/${id}\\?tab=actions$`));
});

test("a manager may duplicate; an editor and a viewer are not offered the button", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  const id = await itemId(page, "JO-K-101");
  await page.goto(`/items/${id}?tab=actions`);
  await expect(duplicateButton(page)).toBeVisible({ timeout: 30_000 });

  for (const email of ["juno.okafor@hartwood.test", "sam.ito@hartwood.test"]) {
    await page.context().clearCookies();
    await login(page, email); // editor, viewer
    await page.goto(`/items/${id}?tab=actions`);
    await expect(page.getByRole("button", { name: /Set status/ })).toBeVisible({ timeout: 30_000 });
    await expect(duplicateButton(page)).toHaveCount(0);
  }
});

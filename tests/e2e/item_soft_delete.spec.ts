import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Soft delete from Tracking: Delete flags the ticked rows, the Deleted chip lists them, and
 * Restore (manager/admin) brings them back. Runs in a project of its own, so no seeded row
 * changes (CLAUDE.md §3).
 */

test("Delete hides an item; the Deleted chip lists it; Restore brings it back", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `SD-${stamp}`, name: `Soft delete ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const mk = async (description: string) => {
    const r = await page.request.post(`/api/projects/${pid}/items`, {
      data: { description, code: null, qty: 1 },
    });
    expect(r.status()).toBe(201);
    return (await r.json()).id as number;
  };
  const keepDesc = `Keep ${stamp}`, goneDesc = `Gone ${stamp}`;
  await mk(keepDesc);
  const goneId = await mk(goneDesc);

  page.on("dialog", (d) => d.accept());
  const rows = page.locator('[data-testid="tracking-row"]');
  const row = (text: string) => rows.filter({ hasText: text });

  await page.goto(`/tracking?project_id=${pid}`);
  await expect(row(goneDesc)).toHaveCount(1);
  await row(goneDesc).locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(row(goneDesc)).toHaveCount(0);                       // gone from the live list
  await expect(row(keepDesc)).toHaveCount(1);                       // the other one is untouched

  // A deleted item answers 404 like a missing one.
  expect((await page.request.get(`/api/items/${goneId}`)).status()).toBe(404);

  await page.getByRole("button", { name: "Deleted", exact: true }).click();
  await expect(page).toHaveURL(/deleted=1/);
  await expect(page.getByTestId("deleted-view-notice")).toBeVisible();
  await expect(row(goneDesc)).toHaveCount(1);
  await expect(row(keepDesc)).toHaveCount(0);
  await expect(row(goneDesc).locator('a[href^="/items/"]')).toHaveCount(0);   // read-only: no editor link

  await row(goneDesc).locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(row(goneDesc)).toHaveCount(0);

  await page.getByRole("button", { name: "Deleted", exact: true }).click();   // back to the live list
  await expect(page).not.toHaveURL(/deleted=1/);
  await expect(row(goneDesc)).toHaveCount(1);
  expect((await page.request.get(`/api/items/${goneId}`)).status()).toBe(200);
});

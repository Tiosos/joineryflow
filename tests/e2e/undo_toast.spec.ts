import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Delete and archive wait out a 10-second Undo window before the request is sent. Runs in
 * a project of its own (CLAUDE.md §3): nothing seeded changes.
 */

async function projectWithItems(page: import("@playwright/test").Page, label: string) {
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `UT-${stamp}`, name: `Undo ${label} ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const description = `${label} ${stamp}`;
  const r = await page.request.post(`/api/projects/${pid}/items`, {
    data: { description, code: null, qty: 1 },
  });
  expect(r.status()).toBe(201);
  return { pid, description, id: (await r.json()).id as number };
}

test("Undo after a bulk delete puts the row back and sends nothing", async ({ page }) => {
  await login(page);
  const { pid, description, id } = await projectWithItems(page, "Undo delete");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: description });

  await page.goto(`/tracking?project_id=${pid}`);
  await row.locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(row).toHaveCount(0);
  await expect(page.getByTestId("undo-toast")).toContainText("Deleted 1 item");

  await page.getByTestId("undo-toast-undo").click();
  await expect(page.getByTestId("undo-toast")).toHaveCount(0);
  await expect(row).toHaveCount(1);
  await page.waitForTimeout(500);
  expect((await page.request.get(`/api/items/${id}`)).status()).toBe(200);
});

test("without Undo the delete is sent when the window ends", async ({ page }) => {
  await login(page);
  const { pid, description, id } = await projectWithItems(page, "No undo");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: description });

  await page.goto(`/tracking?project_id=${pid}`);
  await row.locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  // Still there while the toast is up: nothing has been sent yet.
  expect((await page.request.get(`/api/items/${id}`)).status()).toBe(200);
  await expect(async () => {
    expect((await page.request.get(`/api/items/${id}`)).status()).toBe(404);
  }).toPass({ timeout: 20_000 });
  await expect(page.getByTestId("undo-toast")).toHaveCount(0);
});

test("leaving the page sends a pending delete at once", async ({ page }) => {
  await login(page);
  const { pid, description, id } = await projectWithItems(page, "Leave page");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: description });

  await page.goto(`/tracking?project_id=${pid}`);
  await row.locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByTestId("undo-toast")).toBeVisible();
  await page.goto("/login");               // a full navigation: pagehide flushes the action
  await expect(async () => {
    expect((await page.request.get(`/api/items/${id}`)).status()).toBe(404);
  }).toPass({ timeout: 10_000 });
});

test("leaving the page sends every pending delete of a bulk selection, not just the first", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `UM-${stamp}`, name: `Undo many ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const ids: number[] = [];
  for (let i = 0; i < 4; i++) {
    const r = await page.request.post(`/api/projects/${pid}/items`, {
      data: { description: `Many ${i} ${stamp}`, code: null, qty: 1 },
    });
    expect(r.status()).toBe(201);
    ids.push((await r.json()).id as number);
  }

  await page.goto(`/tracking?project_id=${pid}`);
  const rows = page.locator('[data-testid="tracking-row"]').filter({ hasText: `${stamp}` });
  await expect(rows).toHaveCount(4);
  for (let i = 0; i < 4; i++) await rows.nth(i).locator('input[type="checkbox"]').check();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(page.getByTestId("undo-toast")).toContainText("Deleted 4 items");
  await page.goto("/login");               // a full navigation: pagehide flushes the action
  await expect(async () => {
    for (const id of ids) expect((await page.request.get(`/api/items/${id}`)).status()).toBe(404);
  }).toPass({ timeout: 10_000 });
});

test("archiving a customer waits for the window; Undo keeps it", async ({ page }) => {
  await login(page, "kai.ngata@hartwood.test");               // estimator
  const made = await page.request.post("/api/customers", { data: { name: `Undo customer ${Date.now()}` } });
  expect(made.status()).toBeLessThan(300);
  const cid = (await made.json()).customer_id as number;

  await page.goto(`/customers/${cid}`);
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await page.getByTestId("undo-toast-undo").click();
  await page.waitForTimeout(500);
  const c = await (await page.request.get(`/api/customers/${cid}`)).json();
  expect(c.archived_at).toBeFalsy();

  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await page.getByTestId("confirm-dialog-confirm").click();
  await expect(async () => {
    const after = await (await page.request.get(`/api/customers/${cid}`)).json();
    expect(after.archived_at).toBeTruthy();
  }).toPass({ timeout: 20_000 });
});

import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * Names and small forms ask through the shared dialog (askText / askFields), not window.prompt.
 * Runs in a project of its own (CLAUDE.md §3): nothing seeded changes.
 */

const dialog = (page: Page) => page.getByTestId("confirm-dialog");
const confirmBtn = (page: Page) => page.getByTestId("confirm-dialog-confirm");

async function project(page: Page, label: string) {
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `PD-${stamp}`, name: `${label} ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const r = await page.request.post(`/api/projects/${pid}/items`, {
    data: { description: `${label} item ${stamp}`, code: null, qty: 1 },
  });
  expect(r.status()).toBe(201);
  return { pid, stamp, itemId: (await r.json()).id as number };
}

test("a new cutlist and a rename ask in a dialog; Cancel and Esc change nothing", async ({ page }) => {
  await login(page);
  const { pid, stamp } = await project(page, "Cutlist names");
  await page.goto(`/list?project_id=${pid}`);
  const before = await page.getByText(/\d+ cutlists?/).first().innerText();

  // Esc: nothing is created.
  await page.getByRole("button", { name: "+ New cutlist" }).click();
  await expect(page.getByRole("alertdialog", { name: "New cutlist" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog(page)).toHaveCount(0);
  await expect(page.getByText(before).first()).toBeVisible();

  // Enter in the box confirms.
  const name = `Named ${stamp}`;
  await page.getByRole("button", { name: "+ New cutlist" }).click();
  await page.getByTestId("confirm-dialog-field-text").fill(name);
  await page.getByTestId("confirm-dialog-field-text").press("Enter");
  await expect(page.getByText(name).first()).toBeVisible({ timeout: 15_000 });

  // Rename: the box starts with the current name.
  await page.getByText(name).first().click();
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await expect(page.getByTestId("confirm-dialog-field-text")).toHaveValue(name);
  const renamed = `Renamed ${stamp}`;
  await page.getByTestId("confirm-dialog-field-text").fill(renamed);
  await confirmBtn(page).click();
  await expect(page.getByText(renamed).first()).toBeVisible({ timeout: 15_000 });
});

test("a new area and room ask in a dialog (the room in one form)", async ({ page }) => {
  await login(page);
  const { itemId, stamp } = await project(page, "Area room");
  await page.goto(`/items/${itemId}`);
  const areaSelect = page.locator("select").filter({ has: page.locator('option[value="__new__"]') }).first();
  await expect(areaSelect).toBeVisible({ timeout: 30_000 });

  await areaSelect.selectOption("__new__");
  await expect(confirmBtn(page)).toBeDisabled();                    // the name is required
  await page.getByTestId("confirm-dialog-field-text").fill(`Block ${stamp}`);
  await confirmBtn(page).click();
  await expect(areaSelect.locator("option", { hasText: `Block ${stamp}` })).toHaveCount(1, { timeout: 15_000 });

  const roomSelect = page.locator("select").filter({ has: page.locator('option[value="__new__"]') }).nth(1);
  await roomSelect.selectOption("__new__");
  await expect(page.getByRole("alertdialog", { name: "New room" })).toBeVisible();
  await page.getByTestId("confirm-dialog-field-rm_no").fill("057");
  await page.getByTestId("confirm-dialog-field-rm_desc").fill("Lab");
  await confirmBtn(page).click();
  await expect(roomSelect.locator("option", { hasText: "057 · Lab" })).toHaveCount(1, { timeout: 15_000 });
});

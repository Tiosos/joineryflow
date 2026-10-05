import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Tracking tab layout: no project sidebar (the header's project switcher does that job, and the
 * table gets the width), a working Edit item / + New item pair, and an items table that scrolls
 * both ways with its header kept in view.
 *
 * Creates a project of its own for the New item flow: an item added to ALF-001 would become the
 * "first item" other specs open (CLAUDE.md §3).
 */

test("Tracking has no project sidebar; Dashboard still does", async ({ page }) => {
  await login(page);
  await expect(page.locator('[data-testid="project-sidebar"]')).toBeVisible();   // lands on Dashboard

  await page.goto("/tracking?project_id=1");
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();
  await expect(page.locator('[data-testid="project-sidebar"]')).toHaveCount(0);
});

test("Edit item opens the one ticked row; it is off for none or several", async ({ page }) => {
  await login(page);
  await page.goto("/tracking?project_id=1");
  const rows = page.locator('[data-testid="tracking-row"]');
  await expect(rows.first()).toBeVisible();
  const edit = page.getByTestId("edit-item");

  await expect(edit).toBeDisabled();                                   // nothing ticked
  await rows.nth(0).locator('input[type="checkbox"]').check();
  await expect(edit).toBeEnabled();
  await rows.nth(1).locator('input[type="checkbox"]').check();
  await expect(edit).toBeDisabled();                                   // two ticked
  await rows.nth(1).locator('input[type="checkbox"]').uncheck();
  await expect(edit).toBeEnabled();

  const href = await rows.nth(0).locator('a[href^="/items/"]').first().getAttribute("href");
  await edit.click();
  await expect(page).toHaveURL(new RegExp(`${href}$`), { timeout: 30_000 });
});

test("+ New item creates the item in the project and opens the editor", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `TL-${stamp}`, name: `Tracking layout ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;

  await page.goto(`/tracking?project_id=${pid}`);
  await page.getByTestId("new-item").click();
  const dialog = page.getByTestId("new-item-dialog");
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId("new-item-create")).toBeDisabled();    // description is required

  // Cancel creates nothing.
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);

  await page.getByTestId("new-item").click();
  const description = `New item ${stamp}`;
  await page.getByTestId("new-item-description").fill(description);
  await page.getByTestId("new-item-code").fill(`NI-${stamp % 100000}`);
  await page.getByTestId("new-item-create").click();
  await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 30_000 });

  // The item is in the project's tracking list.
  await page.goto(`/tracking?project_id=${pid}`);
  await expect(page.locator('[data-testid="tracking-row"]').filter({ hasText: description })).toHaveCount(1);
});

test("the items table scrolls both ways and keeps its header in view", async ({ page }) => {
  await login(page);
  await page.goto("/tracking?project_id=1");
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();

  const box = page.locator("table").first().locator("xpath=..");        // the scroll container
  const metrics = await box.evaluate((el) => {
    const cs = getComputedStyle(el);
    return {
      overflowX: cs.overflowX, overflowY: cs.overflowY,
      wide: el.scrollWidth > el.clientWidth, tall: el.scrollHeight > el.clientHeight,
    };
  });
  expect(metrics.overflowX).toBe("auto");
  expect(metrics.overflowY).toBe("auto");
  expect(metrics.wide).toBe(true);                                     // more columns than fit
  expect(metrics.tall).toBe(true);                                     // more rows than the capped height

  await box.evaluate((el) => { el.scrollTop = 200; el.scrollLeft = 150; });
  const { headTop, boxTop, left, top } = await box.evaluate((el) => ({
    headTop: el.querySelector("thead")!.getBoundingClientRect().top,
    boxTop: el.getBoundingClientRect().top,
    left: el.scrollLeft, top: el.scrollTop,
  }));
  expect(left).toBeGreaterThan(0);
  expect(top).toBeGreaterThan(0);
  expect(Math.abs(headTop - boxTop)).toBeLessThan(3);                  // header stuck to the top edge
});

import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test("Procurement resolution flow", async ({ page }) => {
  await login(page);

  await page.goto("/tracking?project_id=1");
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();

  // Click availability chip on first row → drawer opens
  // Retry the click until the drawer opens: a click before the page hydrates does
  // nothing (the chip is rendered by the server first), and opening it twice is harmless.
  await expect(async () => {
    await page.locator('[data-testid="open-availability"]').first().click();
    await expect(page).toHaveURL(/drawer=item-availability/, { timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
  await expect(page.locator('[data-testid="availability-drawer"]')).toBeVisible();
  await expect(page.locator('[data-testid="availability-line"]').first()).toBeVisible();

  // "Order more" → routes to project procurement page with create-batch drawer auto-open
  await page.locator('[data-testid="order-more"]').first().click();
  await expect(page).toHaveURL(/\/projects\/1\/procurement\?.*action=order/, { timeout: 30_000 });
  await expect(page.locator('[data-testid="batch-drawer"]')).toBeVisible();

  // Fill the batch form and save (a supplier name unique to this run, so a re-run finds only its own row)
  const supplier = `Test Supplier ${Date.now()}`;
  await page.locator('[data-testid="batch-supplier"]').fill(supplier);
  await page.locator('[data-testid="batch-qty_ordered"]').fill("10");
  await page.locator('[data-testid="batch-eta_date"]').fill("2026-06-01");
  await page.locator('[data-testid="save-batch"]').click();

  await expect(page.locator('[data-testid="batch-drawer"]')).not.toBeVisible({ timeout: 10_000 });

  // Confirm the new row exists
  await page.goto("/projects/1/procurement?tab=batches");
  await expect(page.getByText(supplier)).toBeVisible({ timeout: 10_000 });
});

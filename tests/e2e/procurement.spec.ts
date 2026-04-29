import { test, expect } from "@playwright/test";

test("Procurement resolution flow", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]',    "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });

  await page.goto("/tracking?project_id=1");
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();

  // Click availability chip on first row → drawer opens
  await page.locator('[data-testid="open-availability"]').first().click();
  await expect(page).toHaveURL(/drawer=item-availability/, { timeout: 10_000 });
  await expect(page.locator('[data-testid="availability-drawer"]')).toBeVisible();
  await expect(page.locator('[data-testid="availability-line"]').first()).toBeVisible();

  // "Order more" → routes to project procurement page with create-batch drawer auto-open
  await page.locator('[data-testid="order-more"]').first().click();
  await expect(page).toHaveURL(/\/projects\/1\/procurement\?.*action=order/, { timeout: 30_000 });
  await expect(page.locator('[data-testid="batch-drawer"]')).toBeVisible();

  // Fill the batch form and save
  await page.locator('[data-testid="batch-supplier"]').fill("Test Supplier");
  await page.locator('[data-testid="batch-qty_ordered"]').fill("10");
  await page.locator('[data-testid="batch-eta_date"]').fill("2026-06-01");
  await page.locator('[data-testid="save-batch"]').click();

  await expect(page.locator('[data-testid="batch-drawer"]')).not.toBeVisible({ timeout: 10_000 });

  // Confirm the new row exists
  await page.goto("/projects/1/procurement?tab=batches");
  await expect(page.getByText("Test Supplier")).toBeVisible({ timeout: 10_000 });
});

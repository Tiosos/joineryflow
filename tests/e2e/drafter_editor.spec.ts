import { test, expect } from "@playwright/test";

test("Drafter editor happy path", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "noa.lindqvist@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });

  // My Day shows >=1 item
  await expect(page.locator('[data-testid="myday-row"]').first()).toBeVisible();

  // Click an item -> editor
  await page.locator('[data-testid="myday-row"] a').first().click();
  await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 30_000 });

  // Cutlist tab: add row
  await page.getByRole("button", { name: /add row/i }).click();
  const lastRow = page.locator('[data-testid="part-row"]').last();
  await lastRow.locator('[data-field="qty"]').fill("2");
  await lastRow.locator('[data-field="part_name"]').fill("Test part");
  await lastRow.locator('[data-field="part_name"]').blur();
  // Wait for PATCH success indicator
  await expect(lastRow).toHaveAttribute("data-saved", "true", { timeout: 10_000 });

  // Hardware tab
  await page.getByRole("tab", { name: /hardware/i }).click();
  // Wait for pantry panel to be fully rendered
  await expect(page.locator('[data-testid="pantry-row"]').first()).toBeVisible();
  const cartCountBefore = await page.locator('[data-testid="cart-line"]').count();
  await page.locator('[data-testid="pantry-row"] [aria-label="Add"]').first().click();
  await expect(page.locator('[data-testid="cart-line"]')).toHaveCount(cartCountBefore + 1);

  // Lock toggle
  const lockBtn = page.getByRole("button", { name: /lock|unlock/i });
  const isLocked = (await lockBtn.textContent())?.toLowerCase().includes("unlock");
  await lockBtn.click();
  await expect(lockBtn).toHaveText(isLocked ? /^Lock$/i : /^Unlock$/i, { timeout: 10_000 });

  // Close window button
  // window.close() may be blocked by browser; allow either-or.
  await page.locator('[data-testid="close-editor"]').click();
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });
});

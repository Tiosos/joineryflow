import { test, expect } from "@playwright/test";

test("PM workbench happy path", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');

  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
  // 4 metric cards
  await expect(page.locator('[data-testid="metric-card"]')).toHaveCount(4);
  // Sidebar shows >=1 project
  const sidebar = page.locator('[data-testid="project-sidebar"] li');
  await expect(sidebar.first()).toBeVisible();

  // Click first sidebar project
  await sidebar.first().click();
  await expect(page).toHaveURL(/\/tracking\?project_id=/, { timeout: 30_000 });

  // Tracking grid shows >=1 item row; CODE column visible
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /code/i })).toBeVisible();

  // Open the editor from the first row. #9a re-pointed ▶ at the in-page
  // ItemDetailModal, so the route into the editor is now the Item ID link.
  const firstRow = page.locator('[data-testid="tracking-row"]').first();
  await firstRow.locator('a[href^="/items/"]').first().click();
  await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 30_000 });
  await expect(page.getByRole("link", { name: /return to (home|dashboard)/i })).toBeVisible();

  // Return to home
  await page.getByRole("link", { name: /return to (home|dashboard)/i }).click();
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
});

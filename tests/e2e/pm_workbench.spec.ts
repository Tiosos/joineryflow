import { test, expect } from "@playwright/test";

test("PM workbench happy path", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');

  await expect(page).toHaveURL(/\/home$/);
  // 4 metric cards
  await expect(page.locator('[data-testid="metric-card"]')).toHaveCount(4);
  // Sidebar shows >=1 project
  const sidebar = page.locator('[data-testid="project-sidebar"] li');
  await expect(sidebar.first()).toBeVisible();

  // Click first sidebar project
  await sidebar.first().click();
  await expect(page).toHaveURL(/\/tracking\?project_id=/);

  // Tracking grid shows >=1 item row; CODE column visible
  await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /code/i })).toBeVisible();

  // Click ▶ on first row
  await page.locator('[data-testid="tracking-row"] [data-testid="open-item"]').first().click();
  await expect(page).toHaveURL(/\/items\/\d+\?tab=cutlist/);
  await expect(page.getByRole("link", { name: /return to home/i })).toBeVisible();

  // Return to home
  await page.getByRole("link", { name: /return to home/i }).click();
  await expect(page).toHaveURL(/\/home$/);
});

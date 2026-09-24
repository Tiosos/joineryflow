// preamble:
// callers: discovered by Playwright via apps/web/playwright.config.ts (testDir ../../tests/e2e).
// glob: tests/e2e/*.spec.ts.
// data-shape: relies on seed.hartwood_joinery (workspace=hartwood-joinery,
//   estimator=kai.ngata@hartwood.test, password=hartwood-dev,
//   EST-2026-0001 draft / EST-2026-0002 sent / EST-2026-0003 accepted).
// user instruction: "add an estimating system into the current project, fully integrate with joinery items."

import { test, expect } from "@playwright/test";

test.describe.configure({ mode: "serial" });

test("estimator can view + convert seeded estimate to project", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "kai.ngata@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });

  await page.getByRole("link", { name: "Estimating", exact: true }).click();
  await expect(page).toHaveURL(/\/estimating/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Estimating" })).toBeVisible();

  await expect(page.getByText("EST-2026-0001")).toBeVisible();
  await expect(page.getByText("EST-2026-0002")).toBeVisible();
  await expect(page.getByText("EST-2026-0003")).toBeVisible();

  await page.getByText("EST-2026-0003").click();
  await expect(page.locator('[data-testid="status-pill"]')).toHaveText(/accepted/i);
  await expect(page.locator('[data-testid="convert-btn"]')).toBeVisible();

  await page.locator('[data-testid="convert-btn"]').click();
  await expect(page.locator('[data-testid="convert-preview-dialog"]')).toBeVisible();
  await page.locator('[data-testid="convert-confirm-btn"]').click();
  await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 30_000 });
});

test("quote PDF renders for the sent demo estimate", async ({ page, context }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "kai.ngata@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/);

  await page.goto("/estimating");
  await page.getByText("EST-2026-0002").click();
  await expect(page.locator('[data-testid="status-pill"]')).toHaveText(/sent/i);

  const pdfLink = page.locator('[data-testid="quote-pdf-link"]');
  await expect(pdfLink).toBeVisible();
  const href = await pdfLink.getAttribute("href");
  expect(href).toMatch(/quote\.pdf$/);
  const origin = new URL(page.url()).origin;
  const resp = await context.request.get(`${origin}${href}`);
  expect(resp.status()).toBe(200);
  expect(resp.headers()["content-type"]).toContain("application/pdf");
});

test("PM (manager) sees the New estimate button", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="email"]', "rin.park@hartwood.test");
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/);

  await page.goto("/estimating");
  await expect(page.locator('[data-testid="new-estimate-btn"]')).toBeVisible();
});

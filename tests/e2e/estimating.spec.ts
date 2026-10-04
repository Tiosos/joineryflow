// preamble:
// callers: discovered by Playwright via apps/web/playwright.config.ts (testDir ../../tests/e2e).
// glob: tests/e2e/*.spec.ts.
// data-shape: relies on seed.hartwood_joinery (workspace=hartwood-joinery,
//   estimator=kai.ngata@hartwood.test, password=hartwood-dev,
//   EST-2026-0001 QUOTE_PREPARED / EST-2026-0002 SUBMITTED / EST-2026-0003 WON).
// user instruction: "add an estimating system into the current project, fully integrate with joinery items."

import { test, expect } from "@playwright/test";
import { login } from "./helpers";

test.describe.configure({ mode: "serial" });

test("estimator can view + convert seeded estimate to project", async ({ page }) => {
  await login(page, "kai.ngata@hartwood.test");

  await page.getByRole("link", { name: "Estimating", exact: true }).click();
  await expect(page).toHaveURL(/\/estimating/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Estimating" })).toBeVisible();

  await expect(page.getByText("EST-2026-0001")).toBeVisible();
  await expect(page.getByText("EST-2026-0002")).toBeVisible();
  await expect(page.getByText("EST-2026-0003")).toBeVisible();

  await page.getByText("EST-2026-0003").click();
  await expect(page.locator('[data-testid="status-pill"]')).toHaveText(/won/i);
  await expect(page.locator('[data-testid="convert-btn"]')).toBeVisible();

  await page.locator('[data-testid="convert-btn"]').click();
  await expect(page.locator('[data-testid="convert-preview-dialog"]')).toBeVisible();
  await page.locator('[data-testid="convert-confirm-btn"]').click();
  await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 30_000 });
});

test("quote PDF renders for the submitted demo estimate", async ({ page, context }) => {
  await login(page, "kai.ngata@hartwood.test");

  await page.goto("/estimating");
  await page.getByText("EST-2026-0002").click();
  await expect(page.locator('[data-testid="status-pill"]')).toHaveText(/submitted/i);

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
  await login(page);

  await page.goto("/estimating");
  await expect(page.locator('[data-testid="new-estimate-btn"]')).toBeVisible();
});

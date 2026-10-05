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

test("estimator can view the seeded estimates and convert a won one to a project", async ({ page }) => {
  await login(page, "kai.ngata@hartwood.test");

  // The seeded WON estimate is left unconverted, so a re-run on the same database still
  // finds what it needs: the test takes its own estimate to WON through the API and converts that.
  const api = async (method: "post", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.json();
  };
  const customer = await api("post", "/customers", { name: `E2E customer ${Date.now()}` });
  const estimate = await api("post", "/estimates", {
    customer_id: customer.customer_id,
    title: `E2E convert ${Date.now()}`,
  });
  const rid = estimate.current_revision_id as number;
  await api("post", `/revisions/${rid}/lines`, { description: "E2E line", qty: 1 });
  for (let i = 0; i < 10; i++) await api("post", `/revisions/${rid}/advance`);
  await api("post", `/revisions/${rid}/accept`);

  await page.getByRole("link", { name: "Estimating", exact: true }).click();
  await expect(page).toHaveURL(/\/estimating/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Estimating" })).toBeVisible();

  await expect(page.getByText("EST-2026-0001")).toBeVisible();
  await expect(page.getByText("EST-2026-0002")).toBeVisible();
  await expect(page.getByText("EST-2026-0003")).toBeVisible();

  await page.getByText(estimate.estimate_no, { exact: true }).click();
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

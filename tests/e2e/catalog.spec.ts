import { test, expect, type Page } from "@playwright/test";

// Seeded users (see seed/hartwood_joinery.py):
//   rin.park@hartwood.test       — manager (PM, owner of ALF-001)
//   noa.lindqvist@hartwood.test  — drafter
// Catalog write actions are gated on `("catalog","write")` which both
// manager and drafter have. We use rin.park for parity with isample.spec.ts.
const EMAIL = "rin.park@hartwood.test";
const PASSWORD = "hartwood-dev";

async function login(page: Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });
}

test.describe("catalog (#7a)", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("/catalog renders the 7-tab strip + board grid", async ({ page }) => {
    await page.goto("/catalog");
    await expect(page.getByRole("heading", { name: "Catalog", level: 1 })).toBeVisible({
      timeout: 15_000,
    });
    for (const label of ["Board", "Hardware", "Custom", "Benchtop", "Appliances", "Equipment Hire", "CV Mappings"]) {
      await expect(page.getByRole("button", { name: label })).toBeVisible();
    }
    // Seeded board rows render in inline-edit <input value="..."> cells, so
    // assert via getByDisplayValue rather than text content.
    await expect(page.getByDisplayValue("18mm White MDF").first()).toBeVisible({ timeout: 10_000 });
  });

  test("creates a new board material and sees it in the grid", async ({ page }) => {
    const ts = Date.now();
    const code = `E2E-${ts}`;
    const sku = `e2e-${ts}`;
    const desc = `E2E test board ${ts}`;
    await page.goto("/catalog?tab=board");
    await page.getByRole("button", { name: "+ New" }).click();
    await expect(page.getByRole("heading", { name: /\+ New board/ })).toBeVisible();

    await page.getByLabel("Description").fill(desc);
    await page.getByLabel("SKU").fill(sku);
    await page.getByLabel("Code").fill(code);
    await page.getByRole("button", { name: "Create" }).click();

    // Newly-created row appears as an input value in the grid (inline-edit).
    await expect(page.getByDisplayValue(desc).first()).toBeVisible({ timeout: 15_000 });
  });

  test("CV Mappings tab renders the seeded mappings", async ({ page }) => {
    await page.goto("/catalog?tab=cv-mappings");
    await expect(page.getByRole("columnheader", { name: "CV code" })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("18-PB").first()).toBeVisible({ timeout: 10_000 });
  });
});

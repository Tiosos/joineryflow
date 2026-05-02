import { test, expect, type Page } from "@playwright/test";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });
}

test("shop drawings: drafter uploads + manager approves", async ({ page }) => {
  // Drafter uploads + submits.
  await login(page, "noa.lindqvist@hartwood.test");

  await page.goto("/shop-dwgs");
  await expect(page.getByRole("heading", { name: "Shop Drawings" })).toBeVisible();
  await expect(page.getByText(/across \d+ rooms/)).toBeVisible();

  await page.getByRole("button", { name: "Upload drawing" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "e2e-test.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%abc\n" + "x".repeat(200) + "\n%%EOF\n"),
  });
  await page.locator('input[placeholder^="Title"]').fill("E2E test drawing");
  await page.locator('input[placeholder^="Room"]').fill("Kitchen");
  await page.getByLabel("Submit for review immediately").check();
  await page.getByRole("button", { name: "Create drawing" }).click();

  // Drawer auto-opens with the new drawing in the In review subtab.
  await expect(page).toHaveURL(/drawing=\d+/, { timeout: 30_000 });
  await expect(page.getByText("E2E test drawing").first()).toBeVisible();

  // Switch to manager.
  await page.context().clearCookies();
  await login(page, "rin.park@hartwood.test");

  await page.goto("/shop-dwgs?subtab=in_review");
  await page.getByText("E2E test drawing").first().click();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/Approved/i).first()).toBeVisible({ timeout: 10_000 });

  // Now visible in Current.
  await page.goto("/shop-dwgs?subtab=current");
  await expect(page.getByText("E2E test drawing").first()).toBeVisible({ timeout: 10_000 });
});

test("shop drawings: reject requires note and leaves drawing without current revision", async ({ page }) => {
  // Drafter uploads + submits.
  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto("/shop-dwgs");
  await page.getByRole("button", { name: "Upload drawing" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "reject-test.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%xyz\n" + "y".repeat(150) + "\n%%EOF\n"),
  });
  await page.locator('input[placeholder^="Title"]').fill("Reject me");
  await page.locator('input[placeholder^="Room"]').fill("Bathroom");
  await page.getByLabel("Submit for review immediately").check();
  await page.getByRole("button", { name: "Create drawing" }).click();
  await expect(page).toHaveURL(/drawing=\d+/, { timeout: 30_000 });

  // Manager rejects with required note.
  await page.context().clearCookies();
  await login(page, "rin.park@hartwood.test");
  await page.goto("/shop-dwgs?subtab=in_review");
  await page.getByText("Reject me").first().click();
  // Wait for the drawer's action bar (Approve button means rev is pending + we can review).
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await page.locator('input[placeholder^="Reason"]').fill("Missing edge profile");
  await page.getByRole("button", { name: "Confirm reject" }).click();

  await expect(page.getByText(/Rejected/i).first()).toBeVisible({ timeout: 10_000 });

  // No current revision -> drawing absent from Current subtab.
  await page.goto("/shop-dwgs?subtab=current");
  await expect(page.getByText("Reject me")).toHaveCount(0);
});

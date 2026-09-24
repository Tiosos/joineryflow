import { test, expect, type Page } from "@playwright/test";

// Seeded users (see seed/hartwood_joinery.py):
//   rin.park@hartwood.test   — manager (PM, owner of ALF-001)
//   theo.blake@hartwood.test — manager (PM)
// The reject/approve flow requires "reviewer != creator" (enforced server-side
// by sample.queries.py), so we create as `rin.park` and review as `theo.blake`.
// Both are `manager` (auth_role.manager grants the `approve` action on the
// `isample` module per RBAC matrix).
const CREATOR_EMAIL = "rin.park@hartwood.test";
const REVIEWER_EMAIL = "theo.blake@hartwood.test";
const PASSWORD = "hartwood-dev";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

async function gotoIsample(page: Page) {
  await page.goto("/isample");
  await expect(page.getByRole("heading", { name: "iSample", level: 1 })).toBeVisible({
    timeout: 15_000,
  });
}

async function openNewSampleDialog(page: Page) {
  await page.getByRole("button", { name: "+ New sample" }).click();
  // Dialog title appears.
  await expect(page.getByRole("heading", { name: "New sample" })).toBeVisible({
    timeout: 10_000,
  });
}

test("iSample: drafter creates sample, manager approves", async ({ page }) => {
  // Use a unique title per run so re-runs don't collide on the seed leftovers.
  const title = `E2E swatch ${Date.now()}`;

  await login(page, CREATOR_EMAIL);
  await gotoIsample(page);
  await openNewSampleDialog(page);

  await page.locator('input[placeholder^="Title"]').fill(title);
  await page.locator('input[placeholder^="Room"]').fill("Lab");
  // hex defaults to #cccccc; supplier optional; skip both.
  await page.getByRole("button", { name: "Create sample" }).click();

  // Drawer opens on the new sample (URL gains ?sample=<id>) and shows the title.
  await expect(page).toHaveURL(/[?&]sample=\d+/, { timeout: 15_000 });
  await expect(
    page.getByRole("heading", { level: 2, name: title }),
  ).toBeVisible({ timeout: 15_000 });

  // The creator cannot approve their own sample — drawer shows the inline note.
  await expect(
    page.getByText("You created this sample; another reviewer must approve."),
  ).toBeVisible();

  // Switch to a different manager to approve.
  await page.context().clearCookies();
  await login(page, REVIEWER_EMAIL);
  await gotoIsample(page);

  // Open the new sample by clicking its card on the Board subtab.
  await page.getByRole("button", { name: `Open sample ${title}` }).click();
  await expect(page).toHaveURL(/[?&]sample=\d+/, { timeout: 15_000 });

  // Approve. The drawer status pill flips to "Approved".
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(
    page.locator("aside").getByText("Approved", { exact: true }),
  ).toBeVisible({ timeout: 15_000 });
});

test("iSample: reject path requires note and moves to Archive", async ({ page }) => {
  const title = `Reject me ${Date.now()}`;

  await login(page, CREATOR_EMAIL);
  await gotoIsample(page);
  await openNewSampleDialog(page);
  await page.locator('input[placeholder^="Title"]').fill(title);
  await page.getByRole("button", { name: "Create sample" }).click();
  await expect(page).toHaveURL(/[?&]sample=\d+/, { timeout: 15_000 });

  await page.context().clearCookies();
  await login(page, REVIEWER_EMAIL);
  await gotoIsample(page);
  await page.getByRole("button", { name: `Open sample ${title}` }).click();
  await expect(page).toHaveURL(/[?&]sample=\d+/, { timeout: 15_000 });

  // First click reveals the inline reason input.
  await page.getByRole("button", { name: "Reject", exact: true }).click();

  // Confirm reject is initially disabled (no note typed).
  const confirmBtn = page.getByRole("button", { name: "Confirm reject" });
  await expect(confirmBtn).toBeDisabled();

  await page.locator('input[placeholder^="Reason for rejection"]').fill("Wrong tone");
  await expect(confirmBtn).toBeEnabled();
  await confirmBtn.click();

  // Drawer pill flips to "Rejected".
  await expect(
    page.locator("aside").getByText("Rejected", { exact: true }),
  ).toBeVisible({ timeout: 15_000 });

  // Rejected samples auto-show in Archive subtab. Navigate there and verify the card.
  await page.goto("/isample?subtab=archive");
  await expect(
    page.getByRole("button", { name: `Open sample ${title}` }),
  ).toBeVisible({ timeout: 15_000 });
});

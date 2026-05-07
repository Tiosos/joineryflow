import { test, expect, type Page } from "@playwright/test";

// rin.park is a manager on ALF-001; manager has cut_floor read+write+approve+comment.
const EMAIL = "rin.park@hartwood.test";
const PASSWORD = "hartwood-dev";

async function login(page: Page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/home$/, { timeout: 30_000 });
}

test.describe("CV Import wizard (#7b)", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("manager imports a CSV with 1 unknown code, skips it, commits", async ({ page }) => {
    // Pick the second ALF-001 item to keep this test independent of the
    // populated first item.
    await page.goto("/projects");
    await page.getByText(/ALF-001/i).first().click();
    const itemLinks = page.locator('a[href^="/items/"]');
    const count = await itemLinks.count();
    test.skip(count < 2, "ALF-001 has fewer than 2 items in the seed");
    await itemLinks.nth(1).click();
    await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 15_000 });
    // Switch to the cutlist tab.
    await page.getByRole("tab", { name: /cutlist/i }).click();

    // Open the CV import wizard.
    await page.getByRole("button", { name: /Import from CV/i }).click();
    await expect(page.getByRole("heading", { name: /Import from Cabinet Vision/i })).toBeVisible();

    // Phase A — paste a CSV with 1 mapped + 1 unknown row.
    await page.locator("textarea").fill(
      "Module,Part Name,Qty,Length,Width,Material\n" +
      "1,Side L,1,720,580,18-PB\n" +
      "1,Side R,1,720,580,99-MYSTERY\n",
    );
    await page.getByRole("button", { name: /^Preview$/ }).click();

    // Phase B — resolve the unknown code by skipping.
    await expect(page.getByText("99-MYSTERY")).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: /^Skip$/ }).first().click();
    await page.getByRole("button", { name: /^Continue$/ }).click();

    // Phase C — confirm.
    await expect(page.getByText(/Import 1 parts/i)).toBeVisible();
    await page.getByRole("button", { name: /^Import$/ }).click();

    // Done — wizard closes after a short delay; success message visible.
    await expect(page.getByText(/imported/i)).toBeVisible({ timeout: 10_000 });
  });
});

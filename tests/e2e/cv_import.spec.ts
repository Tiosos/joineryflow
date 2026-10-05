import { test, expect } from "@playwright/test";
import { login } from "./helpers";

// rin.park is a manager on ALF-001; manager has cut_floor read+write+approve+comment.

test.describe("CV Import wizard (#7b)", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("manager imports a CSV with 1 unknown code, skips it, commits", async ({ page }) => {
    // Reach the item through Tracking, not /projects: on that page the code
    // sits in a plain <td> and only the NAME cell is a link, so clicking
    // "ALF-001" navigated nowhere and the old `count < 2` guard skipped this
    // whole test silently.
    //
    // JO-TP01 is chosen deliberately, not by position. The wizard 409s
    // ITEM_NOT_EMPTY on an item that already has modules, and every
    // ITEMS_PER_PROJECT item is seeded with one — `nth(1)` would have landed
    // on K-102 and failed at Import. JO-TP01 is seeded with none, and is clear
    // of the #10 fixtures (the shared cutlist and the related parts).
    await page.goto("/tracking?project_id=1");
    await expect(page.locator('[data-testid="tracking-row"]').first()).toBeVisible();
    const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: "JO-TP01" });
    await expect(row).toHaveCount(1);
    // goto the link's href rather than click it: a click before the dev build hydrates
    // does nothing (the test below and the lock specs do the same).
    const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
    await page.goto(href!);
    await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 15_000 });
    // Switch to the cutlist tab.
    await page.getByRole("tab", { name: /cutlist/i }).click();

    // Open the CV import wizard.
    await page.getByRole("button", { name: /Import from CV/i }).click();
    await expect(page.getByRole("heading", { name: /Import from Cabinet Vision/i })).toBeVisible();

    // Phase A — paste a CSV with 1 mapped + 1 unknown row. Scope by placeholder:
    // the wizard renders inline in the Cutlist tab rather than in a dialog, so
    // a bare `textarea` also matches the Metadata comment field behind it.
    await page.getByPlaceholder(/Module,Part Name/).fill(
      "Module,Part Name,Qty,Length,Width,Material\n" +
      "1,Side L,1,720,580,18-PB\n" +
      "1,Side R,1,720,580,99-MYSTERY\n",
    );
    await page.getByRole("button", { name: /^Preview$/ }).click();

    // Phase B — resolve the unknown code by skipping.
    await expect(page.getByText("99-MYSTERY")).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: /^Skip$/ }).first().click();
    await page.getByRole("button", { name: /^Continue$/ }).click();

    // Phase C — confirm. A previous run leaves a module on this item, and the
    // wizard then offers "Replace existing modules"; ticking it keeps the spec
    // re-runnable instead of 409ing ITEM_NOT_EMPTY on the second pass.
    await expect(page.getByText(/Import 1 parts/i)).toBeVisible();
    const replace = page.getByRole("checkbox", { name: /Replace existing modules/i });
    if (await replace.count()) await replace.check();
    await page.getByRole("button", { name: /^Import$/ }).click();

    // Done — wizard closes after a short delay; success message visible.
    await expect(page.getByText(/imported/i)).toBeVisible({ timeout: 10_000 });
  });
  test("an ITEM_NOT_EMPTY refusal tells the person to tick Replace, not 'commitCvImport: 409'", async ({ page }) => {
    // The API's answer is mocked (the body is exactly what routes.py raises), so
    // nothing is written; a stale page — modules added by someone else after the
    // wizard opened — is the real-world way to reach it, because the Replace
    // checkbox is only offered when the item already has modules.
    await page.route("**/api/items/*/cv-imports/*/commit*", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: { code: "ITEM_NOT_EMPTY" } }),
      }),
    );
    await page.goto("/tracking?project_id=1");
    const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: "JO-TP01" });
    await expect(row).toHaveCount(1, { timeout: 30_000 });
    // goto the link's href rather than click it: a click before the dev build hydrates
    // does nothing (the other lock specs do the same).
    const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
    await page.goto(href!);
    await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 15_000 });
    await page.getByRole("tab", { name: /cutlist/i }).click();
    await page.getByRole("button", { name: /Import from CV/i }).click();
    await page.getByPlaceholder(/Module,Part Name/).fill(
      "Module,Part Name,Qty,Length,Width,Material\n1,Side L,1,720,580,18-PB\n",
    );
    await page.getByRole("button", { name: /^Preview$/ }).click();
    await expect(page.getByText(/Import 1 parts/i)).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /^Import$/ }).click();
    await expect(
      page.getByText('Item already has modules. Tick "Replace existing modules" and try again.'),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/commitCvImport: 409/)).toHaveCount(0);
  });
});

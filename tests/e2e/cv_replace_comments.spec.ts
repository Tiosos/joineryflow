import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * The CV wizard's "Replace existing modules" step warns about the comments it
 * would delete (Plan V1 §29 module threads, migration 0043): a comment cascades
 * with the module it is on, so replacing an item's modules takes their threads
 * with them.
 *
 * Uses JO-TP01 — seeded with no modules and the one item cv_import.spec.ts also
 * imports onto — so it does not touch the seeded module comment on ALF-001's
 * first item that comments_module_revision.spec.ts reads. Re-runnable: it adds a
 * module only when the item has none, and ends with the item's comments deleted
 * by the replace it performs.
 */
async function openTeaPointCutlist(page: Page) {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: "JO-TP01" });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  // Go to the item by its href rather than clicking the link: the click
  // intermittently did not navigate (the row re-renders as the grid loads).
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  await page.goto(href!);
  await expect(page).toHaveURL(/\/items\/\d+/);
  await page.getByRole("tab", { name: /cutlist/i }).click();
}

/** Open the wizard, paste a one-row CSV and reach the confirm step. */
async function openWizardAtConfirm(page: Page) {
  await page.getByRole("button", { name: /Import from CV/i }).click();
  await page.getByPlaceholder(/Module,Part Name/).fill(
    "Module,Part Name,Qty,Length,Width,Material\n1,Side L,1,720,580,18-PB\n",
  );
  await page.getByRole("button", { name: /^Preview$/ }).click();
  await expect(page.getByText(/Import 1 parts/i)).toBeVisible({ timeout: 15_000 });
}

test("Replace warns how many module comments it will delete, then reports them", async ({ page }) => {
  await login(page);
  await openTeaPointCutlist(page);

  // The item may or may not already have a module (cv_import.spec.ts leaves one).
  const thread = page.getByTestId("module-comments");
  if ((await thread.count()) === 0) {
    await page.getByRole("button", { name: /\+ Add module/ }).click();
  }
  await expect(thread).toBeVisible({ timeout: 30_000 });

  // Two comments on the module: a top-level one and a reply.
  const stamp = Date.now();
  await thread.getByTestId("comment-input").fill(`Scribe note ${stamp}`);
  await thread.getByTestId("comment-submit").click();
  const first = thread.getByTestId("comment-item").filter({ hasText: `Scribe note ${stamp}` });
  await expect(first).toBeVisible();
  await first.getByRole("button", { name: "Reply", exact: true }).click();
  await first.getByTestId("comment-reply-input").fill(`Reply ${stamp}`);
  await first.getByRole("button", { name: "Reply", exact: true }).click(); // now the submit
  await expect(thread.getByText(`Reply ${stamp}`)).toBeVisible();

  // Confirm step: the warning names the comments before anything is deleted.
  await openWizardAtConfirm(page);
  const warning = page.getByTestId("cv-replace-comment-warning");
  await expect(warning).toBeVisible({ timeout: 15_000 });
  const before = Number(((await warning.locator("strong").textContent()) ?? "").replace(/\D/g, ""));
  expect(before).toBeGreaterThanOrEqual(2); // ours; earlier failed runs may have left more
  await expect(warning).toContainText("permanently deleted");

  // Replace, and the outcome reports the same number.
  await page.getByRole("checkbox", { name: /Replace existing modules/i }).check();
  await page.getByRole("button", { name: /^Import$/ }).click();
  await expect(
    page.getByText(new RegExp(`${before} comments? on the replaced modules (was|were) deleted`)),
  ).toBeVisible({ timeout: 15_000 });

  // The comments really went with the module: the fresh module's thread is empty,
  // and re-opening the wizard shows no comment warning.
  await expect(page.getByRole("button", { name: /Import from CV/i })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(`Scribe note ${stamp}`)).toHaveCount(0);
  await openWizardAtConfirm(page);
  await expect(page.getByRole("checkbox", { name: /Replace existing modules/i })).toBeVisible();
  await expect(page.getByTestId("cv-replace-comment-warning")).toHaveCount(0);
});

// Regression: CutlistTab's `selectModule` used to call `history.replaceState`
// for a module that was only just created, racing the `router.refresh()` that
// ModuleTree fires first — the refreshed module list never arrived and the tab
// kept saying "Add a module to start the cutlist" (or never showed the new
// module). Works on any item, with or without modules, so it is re-runnable.
test("adding a module shows it, selected, with its comment thread", async ({ page }) => {
  await login(page);
  await openTeaPointCutlist(page);
  const added = page.getByRole("button", { name: "New module", exact: true });
  await expect(page.getByRole("button", { name: /\+ Add module/ })).toBeVisible({ timeout: 15_000 });
  const before = await added.count();
  await page.getByRole("button", { name: /\+ Add module/ }).click();
  await expect(added).toHaveCount(before + 1, { timeout: 15_000 });
  await expect(page.getByTestId("module-comments")).toContainText("Comments on New module");
});

// If the impact lookup itself fails, the wizard must say so — silence would read
// as "no comments", which is exactly the wrong thing to imply before a delete.
test("Replace says so when it cannot check for comments", async ({ page }) => {
  await login(page);
  await openTeaPointCutlist(page);
  if ((await page.getByTestId("module-comments").count()) === 0) {
    await page.getByRole("button", { name: /\+ Add module/ }).click();
    await expect(page.getByTestId("module-comments")).toBeVisible({ timeout: 15_000 });
  }
  await page.route("**/api/items/*/cv-imports/replace-impact", (route) =>
    route.fulfill({ status: 500, body: "boom" }),
  );
  await openWizardAtConfirm(page);
  await expect(page.getByTestId("cv-replace-comment-check-failed")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("cv-replace-comment-warning")).toHaveCount(0);
});

import { test, expect, type Locator, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * Comment counts on a Module and on a shop-drawing revision (Plan V1 §29), against
 * `make seed`'s fixtures: one comment on the first ALF-001 item's first module and
 * one on an in-review shop-drawing revision.
 *
 * Each test reads the badge it is about to change and asserts baseline + 1 after
 * posting from the screen, with no reload, so the specs are re-runnable without
 * re-seeding (like the other comment specs they leave the extra rows behind).
 */
/** "💬 3" -> 3; no badge -> 0. */
async function countOf(scope: Locator): Promise<number> {
  const badge = scope.getByTestId("comment-badge");
  if ((await badge.count()) === 0) return 0;
  const m = /(\d+)/.exec((await badge.first().textContent()) ?? "");
  return m ? Number(m[1]) : 0;
}

async function openFirstAlfredItem(page: Page) {
  await page.goto("/projects");
  await page.getByRole("link", { name: "Alfred Street Renovation", exact: true }).click();
  await expect(page).toHaveURL(/\/tracking\?project_id=\d+/, { timeout: 30_000 });
  const firstItem = page.locator('a[href^="/items/"]').first();
  await firstItem.waitFor({ timeout: 30_000 });
  await firstItem.click();
  await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 30_000 });
}

async function post(thread: Locator, text: string) {
  await thread.getByTestId("comment-input").fill(text);
  await thread.getByTestId("comment-submit").click();
  await expect(thread.getByTestId("comment-item").filter({ hasText: text })).toBeVisible({ timeout: 30_000 });
}

test("a module's badge shows its thread's count and follows a new comment without a reload", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await openFirstAlfredItem(page);

  const section = page.getByTestId("module-comments");
  await expect(section).toBeVisible({ timeout: 30_000 });
  const firstModule = page.locator("aside").locator("button").first();
  const before = await countOf(firstModule);
  expect(before).toBeGreaterThanOrEqual(1); // the seed's foreman comment

  await post(section.getByTestId("comment-thread"), `Count check ${Date.now()}`);

  await expect(firstModule.getByTestId("comment-badge")).toHaveText(`💬 ${before + 1}`, { timeout: 30_000 });
  await expect(page.getByText("💬 0")).toHaveCount(0); // a thread with no comments shows no chip at all
});

test("a revision's badge shows in the details panel and the viewer, and follows a new comment", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/shop-dwgs?subtab=in_review");
  await page.getByTestId("register-row").first().click(); // any in-review drawing

  // Revisions are listed newest first, so the first "vN" row is the latest.
  const latest = page.getByRole("button", { name: /^v\d+/ }).first();
  await expect(latest).toBeVisible({ timeout: 30_000 });
  const before = await countOf(latest);
  expect(before).toBeGreaterThanOrEqual(1); // the seed's manager comment

  // Panel: expand the revision's thread and post.
  await page.getByRole("button", { name: /^Comments on v\d+/ }).click();
  await post(page.getByTestId("revision-comments"), `Panel count ${Date.now()}`);
  await expect(latest.getByTestId("comment-badge")).toHaveText(`💬 ${before + 1}`, { timeout: 30_000 });

  // Viewer: its versions list carries the same count and follows a post made there.
  await page.getByRole("button", { name: /^View v\d+/ }).first().click();
  // Newest first, scoped to the viewer's own list (the panel behind it has one too).
  const versions = page.getByText("Versions", { exact: true }).locator("xpath=..")
    .getByRole("button", { name: /^v\d+/ }).first();
  await expect(versions.getByTestId("comment-badge")).toHaveText(`💬 ${before + 1}`, { timeout: 30_000 });
  await post(page.getByTestId("viewer-comments"), `Viewer count ${Date.now()}`);
  await expect(versions.getByTestId("comment-badge")).toHaveText(`💬 ${before + 2}`, { timeout: 30_000 });
});

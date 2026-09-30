import { test, expect, type Page } from "@playwright/test";

/**
 * Comment threads on a Module and on a shop-drawing revision (Plan V1 §29,
 * migration 0043), against `make seed`'s fixtures: one comment on the first
 * ALF-001 item's first module (the foreman's, no mention) and one on an in-review
 * shop-drawing revision (the manager's, no mention) — neither changes a bell
 * count.
 *
 * These specs add comments, so they are re-runnable without re-seeding (each
 * comment carries its own unique text and is found by it); like the rest of the
 * comments spec they leave the extra rows behind.
 */
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
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

/** Type `text`, then pick `name` from the @ picker, and post. */
async function postMentioning(page: Page, thread: import("@playwright/test").Locator, text: string, who: string, first: string) {
  const input = thread.getByTestId("comment-input");
  await input.click();
  await input.pressSequentially(`${text} @${first}`);
  const picker = page.getByTestId("mention-suggestions");
  await expect(picker.getByText(who)).toBeVisible();
  await picker.getByText(who).click();
  await thread.getByTestId("comment-submit").click();
  await expect(thread.getByTestId("comment-item").filter({ hasText: text })).toBeVisible();
}

test("a module comment mentions a manager, whose notification opens that module's thread", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter: list:comment
  await openFirstAlfredItem(page);

  // The Cutlist tab is the default one; the active module's thread sits under its parts.
  const section = page.getByTestId("module-comments");
  await expect(section).toBeVisible({ timeout: 30_000 });
  await expect(section.getByText("Allow a 3mm scribe on the wall side")).toBeVisible();

  const text = `Module check ${Date.now()}`;
  await postMentioning(page, section.getByTestId("comment-thread"), text, "Rin Park", "Rin");

  // The manager's bell links straight to that module.
  await page.context().clearCookies();
  await login(page, "rin.park@hartwood.test");
  await page.getByTestId("notification-bell").click();
  await page.getByText(text).click();
  await expect(page).toHaveURL(/\/items\/\d+\?tab=cutlist&module=\d+/, { timeout: 30_000 });
  await expect(page.getByTestId("module-comments").getByText(text)).toBeVisible({ timeout: 30_000 });
});

test("a viewer can read a module thread but not post to it", async ({ page }) => {
  await login(page, "sam.ito@hartwood.test"); // viewer: list:read only
  await openFirstAlfredItem(page);
  const section = page.getByTestId("module-comments");
  await expect(section.getByText("Allow a 3mm scribe on the wall side")).toBeVisible({ timeout: 30_000 });
  await expect(section.getByTestId("comment-input")).toHaveCount(0);
  await expect(section.getByText("You can read this thread but not post to it.")).toBeVisible();
});

test("a revision comment mentions the drafter, whose notification opens the drawer's thread", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager: shop_dwgs:comment
  await page.goto("/shop-dwgs?subtab=in_review");
  await page.getByTestId("register-row").first().click(); // any in-review drawing
  await expect(page).toHaveURL(/drawing=\d+/, { timeout: 30_000 });

  // The panel is collapsed until asked for, so it never squeezes the viewer.
  const panel = page.getByTestId("revision-comments");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByTestId("comment-thread")).toHaveCount(0);
  await panel.getByRole("button", { name: /Comments on v\d+/ }).click();

  const text = `Revision check ${Date.now()}`;
  await postMentioning(page, panel.getByTestId("comment-thread"), text, "Noa Lindqvist", "Noa");

  // The drafter's bell opens the drawing with the panel already expanded.
  await page.context().clearCookies();
  await login(page, "noa.lindqvist@hartwood.test");
  await page.getByTestId("notification-bell").click();
  await page.getByText(text).click();
  await expect(page).toHaveURL(/\/shop-dwgs\?.*drawing=\d+.*rev=\d+.*comments=1/, { timeout: 30_000 });
  await expect(
    page.getByTestId("revision-comments").getByText(text),
  ).toBeVisible({ timeout: 30_000 });
});

test("a viewer can read a revision thread but not post to it", async ({ page }) => {
  await login(page, "sam.ito@hartwood.test"); // viewer: shop_dwgs:read only
  await page.goto("/shop-dwgs?subtab=in_review");
  await page.getByTestId("register-row").first().click();
  const panel = page.getByTestId("revision-comments");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await panel.getByRole("button", { name: /Comments on v\d+/ }).click();
  await expect(panel.getByText("You can read this thread but not post to it.")).toBeVisible();
  await expect(panel.getByTestId("comment-input")).toHaveCount(0);
});

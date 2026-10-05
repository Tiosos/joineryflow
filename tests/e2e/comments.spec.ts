import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * Comments + @mentions + in-app notifications (Plan V1 §29, migration 0042),
 * against `make seed`'s fixtures: on ALF-001's first joinery item Noa (drafter)
 * mentions Juno (foreman), Juno replies, Rin (manager) adds a comment; the
 * project has one comment mentioning Noa. So Juno's bell starts at 1 (a
 * mention) and Noa's at 2 (a reply + a mention).
 *
 * The Areas & Rooms card tests use the seed's one comment on the first item's
 * area and one on its room (no mentions, so the bell counts above are
 * unchanged).
 *
 * The first test makes its own mention rather than reading the seeded one, so a second
 * run on the same database passes (the seeded notification stays unread until read).
 */
/** Switch the item editor to its Comments tab and wait until it has *landed*.
 *  The tab is driven by the URL, so on a dev server that is still compiling the
 *  route the click takes a moment — and until then the Cutlist tab's own module
 *  thread is on screen with the same `comment-input` test id. Typing into that
 *  one loses the text when the tab swaps. Waiting for the module thread to go
 *  makes every `comment-input` after this the item's. */
async function openCommentsTab(page: Page) {
  await page.getByRole("tab", { name: "Comments" }).click();
  await expect(page).toHaveURL(/[?&]tab=comments/, { timeout: 30_000 });
  await expect(page.getByTestId("module-comments")).toHaveCount(0);
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

test("a mention reaches the bell and opens the item's Comments tab", async ({ page }) => {
  // The seed's mention of Juno is read by the first run, so the test makes its own: Noa
  // mentions Juno on the first item's thread, then Juno finds it in his bell. (On a fresh
  // database Juno also has the seeded one, so the count is "at least one", not "1".)
  await login(page, "juno.okafor@hartwood.test"); // editor: tracking:comment
  const junoId = (await (await page.request.get("/api/auth/me")).json()).id as number;
  await page.context().clearCookies();

  const note = `Finish check ${Date.now()}`;
  await login(page, "noa.lindqvist@hartwood.test");
  await openFirstAlfredItem(page);
  const itemId = Number(new URL(page.url()).pathname.split("/").pop());
  const posted = await page.request.post("/api/comments", {
    data: { object_type: "item", object_id: itemId, body: `${note} @Juno Okafor`, mentioned_user_ids: [junoId] },
  });
  expect(posted.status()).toBe(201);
  await page.context().clearCookies();

  await login(page, "juno.okafor@hartwood.test");
  const count = page.getByTestId("notification-count");
  await expect(count).toBeVisible({ timeout: 30_000 });
  const unread = Number(await count.textContent());
  expect(unread).toBeGreaterThanOrEqual(1);

  await page.getByTestId("notification-bell").click();
  await page.getByRole("menuitem").count(); // menu is a plain div; assert by text instead
  await page.getByText("Noa Lindqvist mentioned you").first().click();

  await expect(page).toHaveURL(/\/items\/\d+\?tab=comments/, { timeout: 30_000 });
  const thread = page.getByTestId("comment-thread");
  await expect(thread.getByText(note)).toBeVisible();
  // the mention is highlighted, and the reply hangs under its parent
  await expect(thread.locator("span.font-medium", { hasText: "@Juno Okafor" }).first()).toBeVisible();
  await expect(thread.getByText("the left door sits 2mm proud")).toBeVisible();
  await expect(thread.getByText("Client signed off the sample")).toBeVisible();

  // opening it marked that one read
  if (unread === 1) await expect(count).toHaveCount(0, { timeout: 30_000 });
  else await expect(count).toHaveText(String(unread - 1), { timeout: 30_000 });
});

test("drafter mentions a manager through the picker; edit and delete work", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test");
  await openFirstAlfredItem(page);
  await openCommentsTab(page);

  const input = page.getByTestId("comment-input");
  await input.click();
  await input.pressSequentially("Please recheck the plinth height @Rin");
  const picker = page.getByTestId("mention-suggestions");
  await expect(picker.getByText("Rin Park")).toBeVisible();
  await picker.getByText("Rin Park").click();
  await expect(input).toHaveValue("Please recheck the plinth height @Rin Park ");
  await page.getByTestId("comment-submit").click();

  const mine = page
    .getByTestId("comment-item")
    .filter({ hasText: "Please recheck the plinth height" });
  await expect(mine).toBeVisible();
  await expect(mine.locator("span.font-medium", { hasText: "@Rin Park" })).toBeVisible();

  // edit your own comment
  await mine.getByRole("button", { name: "Edit" }).click();
  // in edit mode the text lives in a textarea, so find the row by its input
  const editing = page
    .getByTestId("comment-item")
    .filter({ has: page.getByTestId("comment-edit-input") });
  await editing.getByTestId("comment-edit-input").fill("Plinth height rechecked — 150mm is right.");
  await editing.getByRole("button", { name: "Save" }).click();
  const edited = page
    .getByTestId("comment-item")
    .filter({ hasText: "Plinth height rechecked" });
  await expect(edited).toContainText("edited");

  // the mentioned manager was notified
  await page.context().clearCookies();
  await login(page, "rin.park@hartwood.test");
  await page.getByTestId("notification-bell").click();
  await expect(page.getByText("Noa Lindqvist mentioned you").first()).toBeVisible();
  await page.getByRole("link", { name: "View all" }).click();
  await expect(page).toHaveURL(/\/notifications$/);
  await expect(page.getByText("Plinth height").first()).toBeVisible();

  // delete: a manager may delete someone else's comment
  await openFirstAlfredItem(page);
  await openCommentsTab(page);
  const target = page
    .getByTestId("comment-item")
    .filter({ hasText: "Plinth height rechecked" });
  page.once("dialog", (d) => d.accept());
  await target.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Plinth height rechecked")).toHaveCount(0);
});

test("a viewer can read a thread but not post to it", async ({ page }) => {
  await login(page, "sam.ito@hartwood.test"); // viewer: tracking:read only
  await openFirstAlfredItem(page);
  await openCommentsTab(page);
  await expect(page.getByText("Client signed off the sample")).toBeVisible();
  await expect(page.getByTestId("comment-input")).toHaveCount(0);
  await expect(page.getByText("You can read this thread but not post to it.")).toBeVisible();
});

async function openAlfredProjectPage(page: Page) {
  await page.goto("/projects");
  await page.getByRole("link", { name: "Details →" }).first().click();
  await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 30_000 });
  await expect(page.getByTestId("areas-card")).toBeVisible({ timeout: 30_000 });
}

const badgeCount = async (row: import("@playwright/test").Locator) =>
  Number(((await row.getByTestId("comment-badge").textContent()) ?? "").replace(/\D/g, ""));

test("Areas & Rooms card: counts, an area's and a room's thread, and the count follows a post", async ({
  page,
}) => {
  await login(page, "rin.park@hartwood.test");
  await openAlfredProjectPage(page);
  const card = page.getByTestId("areas-card");

  // the seed left one comment on the first item's area and one on its room. Other specs (and
  // earlier runs) comment on other areas and rooms, so find the rows by the seeded comment
  // rather than taking the first row that has a badge.
  const rowShowing = async (rowsSelector: string, text: string) => {
    const rows = card.locator(rowsSelector).filter({ has: page.getByTestId("comment-badge") });
    await expect(rows.first()).toBeVisible();
    for (let i = 0; i < (await rows.count()); i++) {
      await rows.nth(i).click();
      try {
        await expect(card.getByText(text)).toBeVisible({ timeout: 1_500 });
        return rows.nth(i);
      } catch {
        // not this row
      }
    }
    throw new Error(`no row of ${rowsSelector} shows "${text}"`);
  };

  const areaRow = await rowShowing('[data-testid^="area-row-"]', "Fit-out is still in progress here");
  await expect(card.getByTestId("thread-heading")).toContainText("Area ·");
  await expect(page).toHaveURL(/\?area=\d+/);                       // the selection is in the URL

  const roomRow = await rowShowing('[data-testid^="room-row-"]', "finish sample in this room");
  await expect(card.getByTestId("thread-heading")).toContainText("Room ·");
  await expect(card.getByText("finish sample in this room")).toBeVisible();
  await expect(card.getByText("Fit-out is still in progress here")).toHaveCount(0);

  // posting updates that row's badge without a reload
  const before = await badgeCount(roomRow);
  await card.getByTestId("comment-input").fill(`Sample booked ${Date.now()}`);
  await card.getByTestId("comment-submit").click();
  await expect(roomRow.getByTestId("comment-badge")).toContainText(String(before + 1));
});

test("a mention on an area's or room's thread deep-links the notification to that thread", async ({
  page,
}) => {
  const stamp = Date.now();
  const areaNote = `Area handover note ${stamp}`;
  const roomNote = `Room handover note ${stamp}`;
  await login(page, "noa.lindqvist@hartwood.test");
  await openAlfredProjectPage(page);
  const card = page.getByTestId("areas-card");

  // mention Rin on an area's thread, then on a room's
  for (const [rowSelector, note] of [
    ['[data-testid^="area-row-"]', areaNote],
    ['[data-testid^="room-row-"]', roomNote],
  ] as const) {
    await card.locator(rowSelector).first().click();
    const input = card.getByTestId("comment-input");
    await input.click();
    await input.pressSequentially("@Rin");
    await card.getByTestId("mention-suggestions").getByText("Rin Park").click();
    // Choosing a member re-places the caret in an animation frame; the picker closes only
    // once that has run. Typing before then lands the note's characters out of order (seen
    // on the slower CI runner), so wait for the picker to close.
    await expect(card.getByTestId("mention-suggestions")).toBeHidden();
    await input.pressSequentially(note);
    await card.getByTestId("comment-submit").click();
    await expect(card.getByText(note)).toBeVisible();
  }

  await page.context().clearCookies();
  await login(page, "rin.park@hartwood.test");

  // from another page: the link lands on the card, thread open, card in view
  await page.getByTestId("notification-bell").click();
  await page.getByText(areaNote).click();
  await expect(page).toHaveURL(/\/projects\/\d+\?area=\d+/, { timeout: 30_000 });
  await expect(page.getByTestId("thread-heading")).toContainText("Area ·");
  await expect(page.getByTestId("areas-card").getByText(areaNote)).toBeVisible();
  await expect(page.getByTestId("areas-card")).toBeInViewport();       // it is the last card on the page

  // and while already on this page: the second link switches the thread in place
  await page.getByTestId("notification-bell").click();
  await page.getByText(roomNote).click();
  await expect(page).toHaveURL(/\/projects\/\d+\?room=\d+/, { timeout: 30_000 });
  await expect(page.getByTestId("thread-heading")).toContainText("Room ·");
  await expect(page.getByTestId("areas-card").getByText(roomNote)).toBeVisible();
  await expect(page.getByTestId("areas-card").getByText(areaNote)).toHaveCount(0);
});

test("the project page carries the project's own thread", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/projects");
  await page.getByRole("link", { name: "Details →" }).first().click();
  await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 30_000 });
  await expect(page.getByText("Site access is via the Block B loading dock")).toBeVisible();
});

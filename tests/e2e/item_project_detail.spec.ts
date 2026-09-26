import { test, expect, type Page } from "@playwright/test";

/**
 * Item & Project Detail 2.0 (#11, migration 0036) — frontend built in
 * plan tasks T08-T12 against `make seed`'s T13 fixtures on ALF-001:
 * builder/classification/site address/TG team, 4 contacts, lift access
 * notes + sketch, 2 item queries on the first joinery item (1 open, 1
 * answered), 2 item documents.
 *
 * Like estimating.spec.ts / procurement.spec.ts, this suite is not
 * idempotent against a second run without re-seeding: the "answer the
 * open seeded question" step turns that question into an answered one,
 * so a second run without `make seed` in between won't find an "Answer"
 * button on it.
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
  // First item link in the tracking grid (href like /items/123?tab=cutlist).
  const firstItem = page.locator('a[href^="/items/"]').first();
  await firstItem.waitFor({ timeout: 30_000 });
  await firstItem.click();
  await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 30_000 });
}

test("item editor: Query tab ask+answer, reference fields, Attachments widened to 5 slots, Actions", async ({
  page,
}) => {
  // drafter — list:write, so it can both ask and answer (T09).
  await login(page, "noa.lindqvist@hartwood.test");
  await openFirstAlfredItem(page);

  // Query tab: the seeded open + answered questions (T13) are both visible.
  await page.getByRole("tab", { name: "Query" }).click();
  await expect(
    page.getByText("Client wants to confirm handle finish"),
  ).toBeVisible();
  await expect(
    page.getByText("Can the island bench overhang be increased"),
  ).toBeVisible();

  // Ask a new question.
  await page
    .getByLabel("Ask a question")
    .fill("Does the pantry need a second adjustable shelf?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(
    page.getByText("Does the pantry need a second adjustable shelf?"),
  ).toBeVisible();

  // Answer the still-open seeded question.
  const openQuestion = page.locator("li", {
    hasText: "Client wants to confirm handle finish",
  });
  await openQuestion
    .getByPlaceholder("Write an answer…")
    .fill("Brushed nickel, per the client's email.");
  await openQuestion.getByRole("button", { name: "Answer" }).click();
  await expect(openQuestion.getByText(/Answered by/)).toBeVisible();

  // Reference fields + Cutlist Printed live in the metadata panel, not a
  // separate tab (T09's deliberate simplification).
  await expect(page.getByText("Cutlist printed?")).toBeVisible();
  await expect(page.getByText("Floor Plan", { exact: true })).toBeVisible();
  await expect(page.getByText("RLS", { exact: true })).toBeVisible();
  await expect(page.getByText("Joinery Details", { exact: true })).toBeVisible();

  // Attachments: widened from 3 to 5 named slots (T08/T10). Scoped to the
  // Attachments section, not the whole page — the left metadata panel stays
  // mounted under every tab and has its own "Floor Plan" reference field
  // (T09), and the three Combined-relevant cards now carry a "Combined PDF"
  // badge inside the same heading (T10), so neither an unscoped nor an
  // exact-text match is safe here.
  await page.getByRole("tab", { name: "Attachments" }).click();
  const attachmentsSection = page.locator("section", {
    has: page.getByRole("heading", { name: "Attachments" }),
  });
  for (const label of [
    "CV Production Drawing",
    "SketchUp Model",
    "Cabinet Vision Job",
    "Floor Plan",
    "Site Measure",
  ]) {
    await expect(attachmentsSection.getByText(label)).toBeVisible();
  }

  // Actions tab: Set status reuses the existing StatusPopup (T09). Scope the
  // dialog's own "Close" button to its footer — an unscoped getByRole match
  // is ambiguous against ItemHeader's unrelated "Close editor" (✕) button,
  // which also matches "Close" as a substring of its accessible name.
  await page.getByRole("tab", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Set status" }).click();
  await expect(page.getByText("Add New Status")).toBeVisible();
  await page
    .locator("footer")
    .filter({ hasText: "Close" })
    .getByRole("button", { name: "Close" })
    .click();
  await expect(page.getByText("Add New Status")).toHaveCount(0);
});

test("project page renders seeded contacts and lift access, reachable from /projects and the Tracking modal", async ({
  page,
}) => {
  await login(page, "noa.lindqvist@hartwood.test");

  // T11/T12: reached from the /projects list page's "Details ->" link.
  await page.goto("/projects");
  await page.getByRole("link", { name: "Details →" }).first().click();
  await expect(page).toHaveURL(/\/projects\/\d+$/, { timeout: 30_000 });

  await expect(page.getByText("Meridian Construction Group")).toBeVisible();
  await expect(page.getByText("Priya Nathan")).toBeVisible();
  await expect(
    page.getByText(/Site access via rear laneway/),
  ).toBeVisible();
  await expect(page.getByText("Open sketch")).toBeVisible();

  // T12: also reachable from the Tracking modal's "Info" button.
  await page.goto("/projects");
  await page.getByRole("link", { name: "Alfred Street Renovation", exact: true }).click();
  await expect(page).toHaveURL(/\/tracking\?project_id=\d+/, { timeout: 30_000 });
  await page.getByRole("button", { name: "Info" }).click();
  await page.getByRole("link", { name: "Open full project page →" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+$/, { timeout: 30_000 });
});

test("close-out is gated to manager/admin", async ({ page }) => {
  // A drafter reaches the project page but never sees the Close-out control
  // (Details/close-out is a manual manager/admin route check, narrower than
  // tracking:write — T11).
  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto("/projects");
  await page.getByRole("link", { name: "Details →" }).first().click();
  await expect(page).toHaveURL(/\/projects\/\d+$/, { timeout: 30_000 });
  await expect(
    page.getByRole("button", { name: /^(Close out|Closed|Closing…)$/ }),
  ).toHaveCount(0);
});

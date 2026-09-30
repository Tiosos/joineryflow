import { test, expect, type Page } from "@playwright/test";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
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

// --- Register redesign (migration 0044). Read-only against the seeded ALF-001
// drawings, so safe to re-run without re-seeding. ---

test("register: columns, queue filter, overdue flag and sorting", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/shop-dwgs");

  const table = page.getByTestId("register-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  for (const h of ["Item #", "View", "Description", "Rev", "Type", "Level", "Joinery ID", "Assigned", "Status", "Due date", "Submitted"]) {
    await expect(table.getByRole("columnheader", { name: new RegExp(h, "i") })).toBeVisible();
  }

  // Seeded "Kitchen island": a draft (Being Drawn) two days past its due date.
  const island = page.getByTestId("register-row").filter({ hasText: "Kitchen island" });
  await expect(island).toContainText("ALF-001-");
  await expect(island.getByTestId("overdue")).toBeVisible();
  await expect(island.getByTestId("queue-chip")).toHaveText("Being Drawn");

  // A queue narrows the register, lands in the URL and survives a reload.
  await page.getByTestId("queue-being_drawn").click();
  await expect(page).toHaveURL(/queue=being_drawn/);
  await expect(page.getByTestId("register-row").filter({ hasText: "Kitchen island" })).toHaveCount(1);
  await expect(page.getByTestId("register-row").filter({ hasText: "Hallway storage" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("queue-being_drawn")).toHaveAttribute("aria-current", "true");

  // Sorting flips the column's aria-sort.
  await page.getByTestId("queue-all").click();
  const due = table.getByRole("columnheader", { name: /Due date/i });
  await due.getByRole("button").click();
  await expect(due).toHaveAttribute("aria-sort", "ascending");
  await due.getByRole("button").click();
  await expect(due).toHaveAttribute("aria-sort", "descending");
});

test("register: details panel, then the full-screen viewer and back", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/shop-dwgs");

  await page.getByTestId("register-row").filter({ hasText: "Hallway storage" }).click();
  const panel = page.getByTestId("details-panel");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByText("Current shop drawing details")).toBeVisible();
  await expect(panel.locator("select").first()).toHaveValue("IFC");
  for (const tab of ["Revisions", "Notes", "Attachments", "Status History", "Audit Log"]) {
    await expect(panel.getByRole("tab", { name: tab })).toBeVisible();
  }
  await panel.getByRole("tab", { name: "Status History" }).click();
  // Seeded drawings are inserted with raw SQL, so they have no audit history.
  await expect(panel.getByText("Nothing recorded yet.")).toBeVisible({ timeout: 30_000 });

  // View opens the viewer over the page; zoom steps; Back returns to the register.
  await page.getByTestId("register-row").filter({ hasText: "Hallway storage" })
    .getByTestId("view-drawing").click();
  const viewer = page.getByTestId("drawing-viewer");
  await expect(viewer).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveURL(/viewer=1/);
  await expect(viewer.getByText("Communication")).toBeVisible();
  await expect(viewer.getByTestId("zoom-level")).toHaveText("Fit");
  await viewer.getByRole("button", { name: "Zoom in" }).click();
  await expect(viewer.getByTestId("zoom-level")).toHaveText("125%");
  await viewer.getByRole("button", { name: "Fit" }).click();
  await expect(viewer.getByTestId("zoom-level")).toHaveText("Fit");
  await viewer.getByRole("button", { name: /Back/ }).click();
  await expect(viewer).toHaveCount(0);
  await expect(panel).toBeVisible();
});

test("register: a viewer sees the details read-only", async ({ page }) => {
  await login(page, "sam.ito@hartwood.test"); // viewer: shop_dwgs:read only
  await page.goto("/shop-dwgs");
  await expect(page.getByRole("button", { name: "Upload drawing" })).toHaveCount(0);
  await page.getByTestId("register-row").filter({ hasText: "Hallway storage" }).click();
  const panel = page.getByTestId("details-panel");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByText(/Only the drawing's creator or a manager can edit/)).toBeVisible();
  await expect(panel.locator("select").first()).toBeDisabled();
});

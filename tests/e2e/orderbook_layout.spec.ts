import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer
const PM = "rin.park@hartwood.test"; // manager
const DRAFTER = "noa.lindqvist@hartwood.test";

type Made = { po_id: number; po_number: string };

async function vendorId(page: Page) {
  const suppliers = await (await page.request.get("/api/suppliers")).json();
  return (suppliers.suppliers ?? suppliers.vendors ?? suppliers)[0].vendor_id as number;
}

/** An order of this run's own (its description is unique), made through the API. */
async function newOrder(page: Page, data: Record<string, unknown>): Promise<Made> {
  const r = await page.request.post("/api/orders", {
    data: { vendor_id: await vendorId(page), ...data },
  });
  expect(r.ok()).toBe(true);
  return (await r.json()) as Made;
}

const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

test("the Orders list is grouped by order type, with the old columns and filter buttons", async ({ page }) => {
  await login(page, BUYER);
  const stamp = Date.now();
  const acoustic = await newOrder(page, { description: `Layout acoustic ${stamp}`, category: "Acoustic", quantity: "2", unit_cost: "10.00", total_amount: "20.00" });
  const overdue = await newOrder(page, { description: `Layout overdue ${stamp}`, category: "Board", total_amount: "5.00" });
  const fine = await newOrder(page, { description: `Layout fine ${stamp}`, category: "Board", total_amount: "5.00" });
  try {
    // overdue: ordered, due last week, not arrived
    expect((await page.request.patch(`/api/orders/${overdue.po_id}`,
      { data: { date_ordered: day(-10), due_date: day(-3) } })).ok()).toBe(true);
    await page.goto("/orderbook");

    for (const col of ["Priority", "Requester", "Qty", "Item", "Location", "Pdf", "Project", "Supplier",
      "Stock", "Cost", "Product code", "Required", "Ordered", "Due", "Arrived"]) {
      await expect(page.locator("thead th", { hasText: new RegExp(`^${col}$`) })).toBeVisible({ timeout: 15_000 });
    }
    const group = page.getByTestId("order-group").filter({ hasText: "Acoustic panel" });
    await expect(group.locator('[data-testid="order-row"]', { hasText: `Layout acoustic ${stamp}` })).toHaveCount(1);
    await expect(page.getByTestId("order-group").filter({ hasText: "Board" })
      .locator('[data-testid="order-row"]', { hasText: `Layout fine ${stamp}` })).toHaveCount(1);

    // The buttons whose meaning is not confirmed are there but off.
    await expect(page.getByTestId("orders-view-filters").getByRole("button", { name: "RTO" })).toBeDisabled();

    await expect(async () => {
      await page.getByTestId("orders-view-overdue").click();
      await expect(page.getByTestId("orders-view-overdue")).toHaveAttribute("aria-pressed", "true", { timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    await expect(page.locator('[data-testid="order-row"]', { hasText: `Layout overdue ${stamp}` })).toHaveCount(1);
    await expect(page.locator('[data-testid="order-row"]', { hasText: `Layout fine ${stamp}` })).toHaveCount(0);

    await page.getByTestId("orders-view-clear").click();
    await expect(page.locator('[data-testid="order-row"]', { hasText: `Layout fine ${stamp}` })).toHaveCount(1);

    // My Orders: these were requested by this purchase officer.
    await page.getByTestId("orders-view-mine").click();
    await expect(page.locator('[data-testid="order-row"]', { hasText: `Layout fine ${stamp}` })).toHaveCount(1);
  } finally {
    for (const o of [acoustic, overdue, fine]) await page.request.delete(`/api/orders/${o.po_id}`);
  }
});

test("a row opens the order pop-up with its type's layout, and Close puts the list back", async ({ page }) => {
  await login(page, BUYER);
  const stamp = Date.now();
  const acoustic = await newOrder(page, { description: `Popup acoustic ${stamp}`, category: "Acoustic", quantity: "6", unit_cost: "430.00", total_amount: "2580.00" });
  const contractor = await newOrder(page, { description: `Popup contractor ${stamp}`, category: "Contractor" });
  try {
    await page.goto("/orderbook");
    const row = page.locator('[data-testid="order-row"]', { hasText: `Popup acoustic ${stamp}` });
    await expect(async () => {
      await row.click();
      await expect(page.getByRole("dialog", { name: "Order details" })).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    const dialog = page.getByTestId("order-detail");
    await expect(dialog).toContainText(acoustic.po_number);
    await expect(dialog).toContainText("Board size");
    await expect(dialog).toContainText("2838.00");          // grand total: 2580.00 + 10% GST
    await expect(dialog).not.toContainText("Laminate code");

    // type-specific fields live in `attributes`
    await page.getByTestId("order-attr-colour").fill("Navy");
    await page.getByTestId("order-attr-colour").blur();
    await expect.poll(async () =>
      ((await (await page.request.get(`/api/orders/${acoustic.po_id}`)).json()).attributes ?? {}).colour).toBe("Navy");

    await page.getByRole("button", { name: "Close" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page).not.toHaveURL(/order=/);

    // Contractor-manufacturing shows a description instead
    await page.goto(`/orderbook?order=${contractor.po_number}`);
    await expect(page.getByTestId("order-detail")).toContainText("Description", { timeout: 15_000 });
    await expect(page.getByTestId("order-detail")).not.toContainText("Board size");
    // Create PO! is shown but not built
    await expect(page.getByTestId("order-create-po")).toBeDisabled();
  } finally {
    for (const o of [acoustic, contractor]) await page.request.delete(`/api/orders/${o.po_id}`);
  }
});

test("the Cost centre button opens a collapsible breakdown by material type, open by default", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const a = await newOrder(page, { description: `Breakdown ${stamp}`, category: "Acoustic", total_amount: "123.00" });
  try {
    await page.context().clearCookies();
    await login(page, DRAFTER);   // anyone who can read the Orderbook sees it
    await page.goto("/orderbook");
    await expect(async () => {
      await page.getByTestId("cost-centre-breakdown-open").click();
      await expect(page.getByTestId("cost-breakdown-modal")).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    const group = page.getByTestId("cost-breakdown-group").filter({ hasText: "Acoustic panel" });
    await expect(group).toContainText(a.po_number);                  // open by default
    await group.getByRole("row").first().click();                    // collapse
    await expect(group).not.toContainText(a.po_number);
    await group.getByRole("row").first().click();                    // and open again
    await expect(group).toContainText(a.po_number);
    await expect(page.getByTestId("cost-breakdown-total")).toBeVisible();
  } finally {
    await page.context().clearCookies();
    await login(page, BUYER);
    await page.request.delete(`/api/orders/${a.po_id}`);
  }
});

test("Tracking > Info has a Budget tab for a manager, with the project's material cost; a drafter has none", async ({ page }) => {
  await login(page, PM);
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `BG-${stamp}`, name: `Budget tab ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const o1 = await newOrder(page, { description: `Budget acoustic ${stamp}`, category: "Acoustic", project_id: pid, total_amount: "100.00" });
  const o2 = await newOrder(page, { description: `Budget board ${stamp}`, category: "Board", project_id: pid, total_amount: "50.50" });
  try {
    await page.goto(`/tracking?project_id=${pid}`);
    await expect(async () => {
      await page.getByRole("button", { name: "Info" }).click();
      await expect(page.getByTestId("project-tab-budget")).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    await page.getByTestId("project-tab-budget").click();
    const budget = page.getByTestId("project-budget");
    await expect(budget.getByTestId("cost-breakdown-total")).toHaveText("$150.50", { timeout: 15_000 });
    await expect(budget.getByTestId("cost-breakdown-group").filter({ hasText: "Acoustic panel" })).toContainText(o1.po_number);
    await expect(budget).toContainText("Labour hours");

    // not offered to a drafter, and the API refuses too
    await page.context().clearCookies();
    await login(page, DRAFTER);
    await page.goto(`/tracking?project_id=${pid}`);
    await expect(async () => {
      await page.getByRole("button", { name: "Info" }).click();
      await expect(page.getByTestId("project-tab-stats")).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    await expect(page.getByTestId("project-tab-budget")).toHaveCount(0);
    expect((await page.request.get(`/api/projects/${pid}/budget`)).status()).toBe(403);
  } finally {
    await page.context().clearCookies();
    await login(page, PM);
    for (const o of [o1, o2]) await page.request.delete(`/api/orders/${o.po_id}`);
  }
});

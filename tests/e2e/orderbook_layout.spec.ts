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

    // Po is there but off until what it prints is decided.
    await expect(page.getByTestId("orders-po")).toBeDisabled();

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

test("the priority pill is coloured: High red, Medium amber, Low grey", async ({ page }) => {
  await login(page, BUYER);
  const stamp = Date.now();
  const made: Made[] = [];
  try {
    for (const priority of ["High", "Medium", "Low"]) {
      made.push(await newOrder(page, { description: `Prio ${priority} ${stamp}`, category: "Board", priority }));
    }
    await page.goto("/orderbook");
    const pill = (p: string) =>
      page.locator('[data-testid="order-row"]', { hasText: `Prio ${p} ${stamp}` }).locator("td").first().locator("span");
    await expect(pill("High")).toHaveClass(/b4443d/, { timeout: 15_000 });
    await expect(pill("Medium")).toHaveClass(/c48a2e/);
    await expect(pill("Low")).toHaveClass(/8f8b80/);
  } finally {
    for (const o of made) await page.request.delete(`/api/orders/${o.po_id}`);
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
    // the same three priorities as the New form
    await expect(page.getByTestId("order-priority").locator("option")).toHaveText(["High", "Medium", "Low"]);

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
    // the keyboard works the group too: its button is focusable and Enter collapses it
    const toggle = group.getByRole("button").first();
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(group).not.toContainText(a.po_number);
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByTestId("cost-breakdown-modal")).toContainText("Cost (AUD)");
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

test("RTO shows Approved orders not yet ordered and TBO every open one not yet ordered", async ({ page }) => {
  await login(page, BUYER);
  const stamp = Date.now();
  const pending = await newOrder(page, { description: `Rto pending ${stamp}` });
  const approved = await newOrder(page, { description: `Rto approved ${stamp}` });
  const ordered = await newOrder(page, { description: `Rto ordered ${stamp}` });
  try {
    expect((await page.request.patch(`/api/orders/${approved.po_id}`, { data: { status: "Approved" } })).ok()).toBe(true);
    expect((await page.request.patch(`/api/orders/${ordered.po_id}`,
      { data: { status: "Approved", date_ordered: day(-1) } })).ok()).toBe(true);
    const row = (name: string) => page.locator('[data-testid="order-row"]', { hasText: `${name} ${stamp}` });
    await page.goto("/orderbook");
    await expect(row("Rto pending")).toHaveCount(1, { timeout: 15_000 });

    await expect(async () => {
      await page.getByTestId("orders-view-rto").click();
      await expect(page.getByTestId("orders-view-rto")).toHaveAttribute("aria-pressed", "true", { timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    await expect(row("Rto approved")).toHaveCount(1);
    await expect(row("Rto pending")).toHaveCount(0);       // not decided yet
    await expect(row("Rto ordered")).toHaveCount(0);       // already ordered

    await page.getByTestId("orders-view-tbo").click();
    await expect(row("Rto pending")).toHaveCount(1);
    await expect(row("Rto approved")).toHaveCount(1);
    await expect(row("Rto ordered")).toHaveCount(0);
  } finally {
    for (const o of [pending, approved, ordered]) await page.request.delete(`/api/orders/${o.po_id}`);
  }
});

test("New opens the order form and Create order saves a Pending order", async ({ page }) => {
  await login(page, BUYER);
  const stamp = Date.now();
  const name = `New order ${stamp}`;
  await page.goto("/orderbook");
  await expect(async () => {
    await page.getByTestId("orders-new").click();
    await expect(page.getByTestId("new-order-dialog")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });

  // priority has three levels; "on hold" and "quote" are statuses
  await expect(page.getByTestId("new-order-priority").locator("option")).toHaveText(["High", "Medium", "Low"]);

  // a supplier and a description are needed
  await page.getByTestId("new-order-create").click();
  await expect(page.getByTestId("new-order-error")).toContainText("supplier");

  const supplier = page.getByTestId("new-order-supplier");
  await expect(supplier.locator("option")).not.toHaveCount(1, { timeout: 15_000 });
  await supplier.selectOption({ index: 1 });
  await page.getByTestId("new-order-category").selectOption("Acoustic");
  await page.getByLabel("New order").getByRole("textbox").first().fill(name);   // Description
  await page.getByTestId("new-order-qty").fill("2");
  await page.getByTestId("new-order-qty").blur();                                // fields apply on leaving them
  await page.getByTestId("new-order-cost").fill("10");
  await page.getByTestId("new-order-cost").blur();
  await expect(page.getByTestId("new-order-total")).toHaveValue("20.00");        // follows qty x cost
  await page.getByTestId("order-attr-colour").fill("Navy");
  await page.getByTestId("new-order-create").click();      // straight from typing: the click leaves the field first

  // it opens in the order pop-up, Pending, with what was typed
  await expect(page.getByTestId("order-detail")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("order-status-select")).toHaveValue("Pending");
  const po = (await page.getByTestId("order-detail").locator("h2").innerText()).trim();
  try {
    const list = (await (await page.request.get("/api/orders")).json()).orders as
      { po_number: string; po_id: number; description: string; category: string; total_amount: string;
        attributes: { colour?: string } }[];
    const made = list.find(o => o.po_number === po)!;
    expect(made.description).toBe(name);
    expect(made.category).toBe("Acoustic");
    expect(Number(made.total_amount)).toBe(20);
    expect(made.attributes.colour).toBe("Navy");
  } finally {
    const list = (await (await page.request.get("/api/orders")).json()).orders as { po_number: string; po_id: number }[];
    const made = list.find(o => o.po_number === po);
    if (made) await page.request.delete(`/api/orders/${made.po_id}`);
  }
});

test("Supplier opens the supplier list: add a supplier and edit its details and status", async ({ page }) => {
  await login(page, BUYER);
  const stamp = Date.now();
  const name = `Supplier e2e ${stamp}`;
  const read = async () =>
    ((await (await page.request.get(`/api/suppliers?q=${encodeURIComponent(name)}`)).json()).suppliers as
      { vendor_id: number; name: string; status: string; contact_phone: string | null; payment_terms: string | null }[])[0];
  await page.goto("/orderbook");
  await expect(async () => {
    await page.getByTestId("orders-suppliers").click();
    await expect(page.getByTestId("supplier-modal")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });

  await page.getByTestId("supplier-add").click();
  await page.getByTestId("supplier-name").fill(name);
  await page.getByTestId("supplier-save").click();
  await expect.poll(async () => (await read())?.name).toBe(name);
  try {
    const row = page.getByTestId("supplier-row").filter({ hasText: name });
    await expect(row).toHaveCount(1);
    await row.getByTestId("supplier-edit").click();
    await page.getByTestId("supplier-form").getByLabel("Phone").fill("0400 000 000");
    await page.getByTestId("supplier-form").getByLabel("Payment terms").fill("30 days EOM");
    await page.getByTestId("supplier-save").click();
    await expect.poll(async () => (await read()).payment_terms).toBe("30 days EOM");
    expect((await read()).contact_phone).toBe("0400 000 000");
  } finally {
    // a supplier cannot be deleted: switch it off so it leaves every picker
    await page.request.patch(`/api/suppliers/${(await read()).vendor_id}`, { data: { status: "Inactive" } });
  }
  expect((await read()).status).toBe("Inactive");
});

test("switching the order type in the New form leaves the old type's fields out of the order", async ({ page }) => {
  await login(page, BUYER);
  const name = `Type switch ${Date.now()}`;
  await page.goto("/orderbook");
  await expect(async () => {
    await page.getByTestId("orders-new").click();
    await expect(page.getByTestId("new-order-dialog")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
  const supplier = page.getByTestId("new-order-supplier");
  await expect(supplier.locator("option")).not.toHaveCount(1, { timeout: 15_000 });
  await supplier.selectOption({ index: 1 });
  await page.getByLabel("New order").getByRole("textbox").first().fill(name);   // Description

  // fill a Benchtop-only field, then change to a type that has none of its own
  await page.getByTestId("new-order-category").selectOption("Benchtop");
  await page.getByTestId("order-attr-underside").fill("Aquaban");
  await page.getByTestId("order-attr-underside").blur();
  await page.getByTestId("new-order-category").selectOption("Contractor");
  await expect(page.getByTestId("order-attr-underside")).toHaveCount(0);
  await page.getByTestId("new-order-create").click();

  await expect(page.getByTestId("order-detail")).toBeVisible({ timeout: 15_000 });
  const po = (await page.getByTestId("order-detail").locator("h2").innerText()).trim();
  const list = (await (await page.request.get("/api/orders")).json()).orders as
    { po_number: string; po_id: number; attributes: Record<string, unknown> }[];
  const made = list.find(o => o.po_number === po)!;
  try {
    expect(made.attributes).toEqual({});       // the Benchtop 'underside' was not carried over
  } finally {
    await page.request.delete(`/api/orders/${made.po_id}`);
  }
});

test("a page left open overnight moves Due orders to Over Due at midnight", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const o = await newOrder(page, { description: `Midnight ${stamp}`, category: "Board", total_amount: "5.00" });
  try {
    expect((await page.request.patch(`/api/orders/${o.po_id}`,
      { data: { due_date: day(0), date_ordered: day(-3) } })).ok()).toBe(true);
    // the browser's clock starts a minute before local midnight, then runs past it
    const midnight = new Date(); midnight.setHours(24, 0, 0, 0);
    await page.clock.install({ time: new Date(midnight.getTime() - 60_000) });
    await page.goto("/orderbook?view=overdue");
    const row = page.locator('[data-testid="order-row"]', { hasText: `Midnight ${stamp}` });
    await expect(page.getByTestId("orders-view-overdue")).toHaveAttribute("aria-pressed", "true", { timeout: 15_000 });
    await expect(row).toHaveCount(0);                               // due today: not over due yet
    await page.clock.runFor(120_000);
    await expect(row).toHaveCount(1);                               // after midnight it is
  } finally {
    await page.request.delete(`/api/orders/${o.po_id}`);
  }
});

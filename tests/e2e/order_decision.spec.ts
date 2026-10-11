import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer: reviews and decides pending orders
const PM = "rin.park@hartwood.test"; // manager: may decide too
const DRAFTER = "noa.lindqvist@hartwood.test"; // may raise and edit orders, not decide them

async function switchTo(page: Page, email: string) {
  await page.context().clearCookies();
  await login(page, email);
}

/** What the ledger holds for a cost centre. The Orderbook no longer shows it (the budget is for
 *  managers and admins, in Tracking > Info), but the commitment is still posted and followed. */
async function committed(page: Page, ccId: number) {
  const list = (await (await page.request.get("/api/cost-centers")).json()).cost_centers as
    { cost_center_id: number; committed: string }[];
  return Number(list.find(c => c.cost_center_id === ccId)!.committed);
}

/** An order made through the API (it starts Pending); its own, so a re-run finds only it. */
async function newOrder(page: Page, total: string) {
  const suppliers = await (await page.request.get("/api/suppliers")).json();
  const vendor = (suppliers.suppliers ?? suppliers.vendors ?? suppliers)[0];
  const r = await page.request.post("/api/orders", {
    data: { vendor_id: vendor.vendor_id, description: `Decision e2e ${Date.now()}`, total_amount: total },
  });
  expect(r.ok()).toBe(true);
  return (await r.json()) as { po_id: number; po_number: string };
}

test("a new order is Pending and the purchase officer approves it against a budget", async ({ page }) => {
  await login(page, BUYER);
  const code = `D${Date.now()}`.slice(-12);
  const made = await page.request.post("/api/cost-centers", { data: { code, name: "Decision e2e", budget_amount: "10000" } });
  expect(made.ok()).toBe(true);
  const { cost_center_id: ccId } = (await made.json()) as { cost_center_id: number };
  const order = await newOrder(page, "3000.00");
  try {
    expect(((await (await page.request.get(`/api/orders/${order.po_id}`)).json()) as { status: string }).status).toBe("Pending");
    await page.goto(`/orderbook?order=${order.po_number}`);
    await expect(page.getByTestId("order-status-select")).toHaveValue("Pending", { timeout: 15_000 });

    // The budget the order commits against once it is Approved.
    await expect(async () => {
      await page.getByTestId("order-cost-centre").selectOption({ value: String(ccId) });
      await expect(page.getByTestId("order-cost-centre")).toHaveValue(String(ccId), { timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    expect(await committed(page, ccId)).toBe(0);
    await expect(page.getByTestId("cost-centre-figures")).toHaveCount(0);   // no budget figures in the Orderbook

    await page.getByTestId("order-status-select").selectOption("Approved");
    await expect.poll(() => committed(page, ccId)).toBe(3000);

    // The commitment is posted, so the order's cost centre can no longer move.
    await page.getByTestId("order-cost-centre").selectOption({ label: "None" });
    await expect(page.getByText("already posted against this cost centre")).toBeVisible();

    // Moving it out of Approved gives the budget back.
    await page.getByTestId("order-status-select").selectOption("Hold");
    await expect.poll(() => committed(page, ccId)).toBe(0);
  } finally {
    await page.request.delete(`/api/orders/${order.po_id}`); // cancels it: puts back what the spec added
    await page.request.patch(`/api/cost-centers/${ccId}`, { data: { is_active: false } });
  }
});

test("rejecting an order asks for a reason, which stays on the order", async ({ page }) => {
  await login(page, BUYER);
  const order = await newOrder(page, "800.00");
  try {
    await page.goto(`/orderbook?order=${order.po_number}`);
    await expect(page.getByTestId("order-status-select")).toHaveValue("Pending", { timeout: 15_000 });
    await expect(async () => {
      await page.getByTestId("order-status-select").selectOption("Rejected");
      await expect(page.getByTestId("order-reject-form")).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    await expect(page.getByTestId("order-reject-confirm")).toBeDisabled();   // no reason yet
    await page.getByTestId("order-reject-note").fill("Supplier is not on our list");
    await page.getByTestId("order-reject-confirm").click();
    await expect(page.getByTestId("order-status-select")).toHaveValue("Rejected");
    await expect(page.getByTestId("order-rejection-note")).toContainText("Supplier is not on our list");
  } finally {
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});

test("a drafter can raise and edit an order but not approve or reject it", async ({ page }) => {
  await login(page, BUYER);
  const order = await newOrder(page, "800.00");
  try {
    await switchTo(page, DRAFTER);
    await page.goto(`/orderbook?order=${order.po_number}`);
    const select = page.getByTestId("order-status-select");
    await expect(select).toHaveValue("Pending", { timeout: 15_000 });
    await expect(select.locator('option[value="Approved"]')).toBeDisabled();
    await expect(select.locator('option[value="Rejected"]')).toBeDisabled();
    await expect(select.locator('option[value="Hold"]')).toBeEnabled();
    // the API says the same
    const r = await page.request.patch(`/api/orders/${order.po_id}`, { data: { status: "Approved" } });
    expect(r.status()).toBe(403);
  } finally {
    await switchTo(page, BUYER);
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});

test("a purchase officer sees the cost-centre admin on the Orders tab", async ({ page }) => {
  await login(page, BUYER);
  await page.goto("/orderbook");
  await expect(page.getByTestId("cost-centres")).toContainText("cost centre", { timeout: 15_000 });
  await expect(async () => {
    await page.getByTestId("cost-centre-add").click();
    await expect(page.getByTestId("cost-centre-code")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
  // Adding one is covered by the API tests: there is no way to remove it again.
});

test("a purchase officer renames a cost centre and switches it off", async ({ page }) => {
  await login(page, BUYER);
  // Its own cost centre (the code is unique to the run). There is no way to delete one, so it is
  // left switched off at the end, which keeps it out of every order's selector.
  const code = `E${Date.now()}`.slice(-12);
  const made = await page.request.post("/api/cost-centers", { data: { code, name: "Typo name" } });
  expect(made.ok()).toBe(true);
  const { cost_center_id: id } = (await made.json()) as { cost_center_id: number };
  const read = async () =>
    ((await (await page.request.get("/api/cost-centers")).json()).cost_centers as
      { cost_center_id: number; name: string; is_active: boolean }[]).find(c => c.cost_center_id === id)!;

  await page.goto("/orderbook");
  await expect(async () => {
    await page.getByTestId("cost-centre-manage").click();
    await expect(page.getByTestId("cost-centre-manager")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });

  const row = page.getByTestId("cost-centre-manager").locator("li").filter({
    has: page.locator(`input[data-testid="cost-centre-edit-code"][value="${code}"]`),
  });
  await row.getByTestId("cost-centre-edit-name").fill("Fixed name");
  await row.getByTestId("cost-centre-edit-save").click();
  await expect.poll(async () => (await read()).name).toBe("Fixed name");

  await expect(row.getByTestId("cost-centre-edit-budget")).toHaveCount(0);   // no budget amount to set here

  await row.getByTestId("cost-centre-toggle").click();
  await expect.poll(async () => (await read()).is_active).toBe(false);
  await expect(row).toContainText("inactive");
});

test("the order pop-up shows its cost centre but no budget figures, to anyone", async ({ page }) => {
  await login(page, BUYER);
  const code = `F${Date.now()}`.slice(-12);
  const made = await page.request.post("/api/cost-centers", { data: { code, name: "Figures e2e" } });
  expect(made.ok()).toBe(true);
  const { cost_center_id: ccId } = (await made.json()) as { cost_center_id: number };
  const order = await newOrder(page, "400.00");
  try {
    const set = await page.request.patch(`/api/orders/${order.po_id}`, { data: { cost_center_id: ccId } });
    expect(set.ok()).toBe(true);
    await switchTo(page, PM);
    await page.goto(`/orderbook?order=${order.po_number}`);
    await expect(page.getByTestId("order-cost-centre")).toHaveValue(String(ccId), { timeout: 15_000 });
    await expect(page.getByTestId("order-detail")).not.toContainText("remaining");
    await expect(page.getByTestId("cost-centre-figures")).toHaveCount(0);
  } finally {
    // No way to delete one: switch it off so it stays out of every order's selector.
    await switchTo(page, BUYER);
    await page.request.delete(`/api/orders/${order.po_id}`);
    await page.request.patch(`/api/cost-centers/${ccId}`, { data: { is_active: false } });
  }
});

import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * The budget report (Orderbook > Budget report): every cost centre's budget, committed, spent and
 * remaining with totals, and the orders that have no cost centre. Managers and admins only. Each
 * order and cost centre the spec makes is cancelled / switched off again (a cost centre cannot be
 * deleted), and its own unique code and descriptions are what it asserts on.
 */
const BUYER = "mina.klee@hartwood.test";     // purchase officer: adds cost centres and orders
const MANAGER = "rin.park@hartwood.test";     // approves, reads the report
const DRAFTER = "noa.lindqvist@hartwood.test";

async function switchTo(page: Page, email: string) {
  await page.context().clearCookies();
  await login(page, email);
}

test("the budget report totals each cost centre, lists the unallocated orders, and links to the orders behind a number", async ({ page }) => {
  const stamp = Date.now();
  const code = `BR${String(stamp).slice(-7)}`;
  await login(page, BUYER);
  const suppliers = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const vendor = suppliers.suppliers[0].vendor_id;
  const cc = await page.request.post("/api/cost-centers", { data: { code, name: `Report ${stamp}`, budget_amount: "5000" } });
  expect(cc.status()).toBe(201);
  const ccId = (await cc.json()).cost_center_id as number;
  const make = async (description: string, total: string, cost_center_id: number | null) => {
    const r = await page.request.post("/api/orders", { data: { vendor_id: vendor, description, category: "Board", total_amount: total } });
    expect(r.status()).toBe(201);
    const id = (await r.json()).po_id as number;
    if (cost_center_id !== null) {
      expect((await page.request.patch(`/api/orders/${id}`, { data: { cost_center_id } })).status()).toBe(200);
    }
    return id;
  };
  const onCc = await make(`On the cost centre ${stamp}`, "1234.00", ccId);
  const loose = await make(`No cost centre ${stamp}`, "321.00", null);
  const ids = [onCc, loose];
  try {
    await switchTo(page, MANAGER);
    expect((await page.request.patch(`/api/orders/${onCc}`, { data: { status: "Approved" } })).status()).toBe(200);   // commits 1,234

    await page.goto("/orderbook");
    await page.getByTestId("budget-report-link").click();
    await expect(page).toHaveURL(/\/orderbook\/budget$/, { timeout: 30_000 });
    const row = page.locator(`[data-testid="budget-row"][data-code="${code}"]`);
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText("$5,000.00");        // budget
    await expect(row).toContainText("$1,234.00");        // committed
    await expect(row).toContainText("$3,766.00");        // remaining
    await expect(page.getByTestId("budget-total")).toBeVisible();
    await expect(page.getByTestId("budget-unallocated")).toContainText("with no cost centre");

    // the number on the row opens exactly those orders
    await row.getByRole("link", { name: "1", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/orderbook\\?cost_center=${ccId}$`), { timeout: 30_000 });
    await expect(page.getByTestId("cost-centre-filter")).toContainText(code);
    await expect(page.getByText(`On the cost centre ${stamp}`).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(`No cost centre ${stamp}`)).toHaveCount(0);
    await page.getByRole("button", { name: "Clear the cost centre filter" }).click();
    await expect(page.getByTestId("cost-centre-filter")).toHaveCount(0);

    // and the unallocated number opens the orders with none
    await page.goto("/orderbook/budget");
    await page.getByTestId("budget-unallocated").getByRole("link").click();
    await expect(page).toHaveURL(/\/orderbook\?cost_center=none$/, { timeout: 30_000 });
    await expect(page.getByText(`No cost centre ${stamp}`).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(`On the cost centre ${stamp}`)).toHaveCount(0);
  } finally {
    await switchTo(page, BUYER);
    for (const id of ids) await page.request.delete(`/api/orders/${id}`);               // releases the commitment
    await page.request.patch(`/api/cost-centers/${ccId}`, { data: { is_active: false } });
  }
});

test("only managers and admins see the budget report", async ({ page }) => {
  await login(page, DRAFTER);
  await page.goto("/orderbook");
  await expect(page.getByTestId("orders-panel")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("budget-report-link")).toHaveCount(0);
  await page.goto("/orderbook/budget");
  await expect(page.getByTestId("budget-forbidden")).toBeVisible({ timeout: 30_000 });
  expect((await page.request.get("/api/cost-centers/report")).status()).toBe(403);
});

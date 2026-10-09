import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer: raises orders, sets the limit
const PM = "rin.park@hartwood.test"; // manager: approves

async function switchTo(page: Page, email: string) {
  await page.context().clearCookies();
  await login(page, email);
}

/** An order over the default limit, made through the API; its own, so a re-run finds only it. */
async function newOrder(page: Page, total: string) {
  const suppliers = await (await page.request.get("/api/suppliers")).json();
  const vendor = (suppliers.suppliers ?? suppliers.vendors ?? suppliers)[0];
  const r = await page.request.post("/api/orders", {
    data: { vendor_id: vendor.vendor_id, description: `Approval e2e ${Date.now()}`, total_amount: total },
  });
  expect(r.ok()).toBe(true);
  return (await r.json()) as { po_id: number; po_number: string };
}

test("an order over the limit is requested by one person and approved by another", async ({ page }) => {
  await login(page, BUYER);
  const order = await newOrder(page, "3000.00");
  try {
    await page.goto(`/orderbook?order=${order.po_number}`);
    await expect(page.getByTestId("order-approval")).toBeVisible({ timeout: 15_000 });

    // The budget the approval commits against: the seeded cost centre.
    await expect(async () => {
      await page.getByTestId("order-cost-centre").selectOption({ label: "GEN General" });
      await expect(page.getByTestId("order-cost-centre")).toHaveValue(/\d+/, { timeout: 2_000 });
    }).toPass({ timeout: 20_000 });

    // Not selectable as a plain status, and requesting it is the way in.
    await expect(page.getByTestId("order-status-select").locator('option[value="Approved"]')).toBeDisabled();
    await expect(async () => {
      await page.getByTestId("order-request-approval").click();
      await expect(page.getByTestId("order-approval-pending")).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });

    // The requester gets no Approve button.
    await expect(page.getByTestId("order-approve")).toHaveCount(0);

    // The project manager approves it.
    await switchTo(page, PM);
    await page.goto(`/orderbook?order=${order.po_number}`);
    await page.getByTestId("order-approval-note").fill("Within budget");
    await page.getByTestId("order-approve").click();
    await expect(page.getByTestId("order-approved-by")).toContainText("Approved by Rin Park");
    await expect(page.getByTestId("order-approved-by")).toContainText("Within budget");

    // The commitment is posted, so the order's cost centre can no longer move.
    await page.getByTestId("order-cost-centre").selectOption({ label: "None" });
    await expect(page.getByText("already posted against this cost centre")).toBeVisible();
  } finally {
    await switchTo(page, BUYER);
    await page.request.delete(`/api/orders/${order.po_id}`); // cancels it: puts back what the spec added
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

  await row.getByTestId("cost-centre-toggle").click();
  await expect.poll(async () => (await read()).is_active).toBe(false);
  await expect(row).toContainText("inactive");
});

test("a purchase officer can change the approval limit", async ({ page }) => {
  await login(page, BUYER);
  await page.goto("/orderbook");
  const limit = page.getByTestId("approval-limit");
  await expect(limit).toContainText("need approval", { timeout: 15_000 });
  const before = (await page.request.get("/api/order-settings").then(r => r.json())).approval_threshold as string;
  try {
    await expect(async () => {
      await page.getByTestId("approval-limit-edit").click();
      await expect(page.getByTestId("approval-limit-input")).toBeVisible({ timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    await page.getByTestId("approval-limit-input").fill("5000");
    await page.getByTestId("approval-limit-save").click();
    await expect(limit).toContainText("$5000.00");
  } finally {
    await page.request.put("/api/order-settings", { data: { approval_threshold: before } });
  }
});

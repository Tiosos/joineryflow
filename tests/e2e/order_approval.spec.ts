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
  } finally {
    await switchTo(page, BUYER);
    await page.request.delete(`/api/orders/${order.po_id}`); // cancels it: puts back what the spec added
  }
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

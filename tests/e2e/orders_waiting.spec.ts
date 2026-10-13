import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer: told about orders waiting
const MANAGER = "rin.park@hartwood.test"; // can decide, but is not told
const DRAFTER = "noa.lindqvist@hartwood.test";

async function switchTo(page: Page, email: string) {
  await page.context().clearCookies();
  await login(page, email);
}

async function openBell(page: Page) {
  await page.goto("/orderbook");
  await expect(async () => {
    await page.getByTestId("notification-bell").click();
    await expect(page.getByRole("menu")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
}

test("a pending order waits in the purchase officer's bell until it is decided", async ({ page }) => {
  const stamp = Date.now();
  await login(page, DRAFTER);
  const suppliers = await (await page.request.get("/api/suppliers")).json();
  const vendor = (suppliers.suppliers ?? suppliers.vendors ?? suppliers)[0].vendor_id as number;
  const r = await page.request.post("/api/orders", {
    data: { vendor_id: vendor, description: `Waiting ${stamp}`, category: "Board", total_amount: "9.00" },
  });
  expect(r.ok()).toBe(true);
  const order = (await r.json()) as { po_id: number; po_number: string };
  try {
    // the purchase officer sees it in the bell and the badge, and the link opens the order
    await switchTo(page, BUYER);
    await openBell(page);
    const row = page.getByTestId("order-waiting").filter({ hasText: order.po_number });
    await expect(row).toContainText(`Waiting ${stamp}`);
    await expect(page.getByTestId("notification-count")).toBeVisible();
    await row.click();
    await expect(page).toHaveURL(new RegExp(`order=${order.po_number}`));

    // the full page lists it too
    await page.goto("/notifications");
    await expect(page.getByTestId("orders-waiting-list")).toContainText(order.po_number);

    // a manager can decide but is not told
    await switchTo(page, MANAGER);
    await openBell(page);
    await expect(page.getByTestId("orders-waiting")).toHaveCount(0);

    // deciding it takes it off the purchase officer's list
    await switchTo(page, BUYER);
    expect((await page.request.patch(`/api/orders/${order.po_id}`, { data: { status: "Approved" } })).ok()).toBe(true);
    await openBell(page);
    await expect(page.getByTestId("order-waiting").filter({ hasText: order.po_number })).toHaveCount(0);
  } finally {
    await switchTo(page, BUYER);
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});

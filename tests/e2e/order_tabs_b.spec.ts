import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer

test("the order pop-up's Glass C calculator, Timber order form and TGSolid rows", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const order = (await (await page.request.post("/api/orders", {
    data: { vendor_id: vendors.suppliers[0].vendor_id, description: `1471 x 1000 x 6 - glass ${stamp}`, category: "Board", total_amount: "60.00" },
  })).json()) as { po_id: number; po_number: string };
  let rateId: number | null = null;
  try {
    await page.goto(`/orderbook?order=${order.po_number}`);
    const detail = page.getByTestId("order-detail");
    await expect(detail).toBeVisible();

    // Glass C: the purchase officer adds a rate to the price list, copies the size from the description, ticks it
    await detail.getByTestId("order-tab-Glass C").click();
    await detail.getByTestId("glass-edit-list").click();
    await detail.getByTestId("glass-new-name").fill(`Spec glass ${stamp}`);
    await detail.getByTestId("glass-new-rate").fill("10");
    await detail.getByTestId("glass-new-add").click();
    await detail.getByTestId("glass-edit-list").click();
    const line = detail.getByTestId("glass-line").filter({ hasText: `Spec glass ${stamp}` });
    await expect(line).toBeVisible();
    await detail.getByTestId("glass-copy-size").click();
    await expect(detail.getByTestId("glass-length")).toHaveValue("1471");
    await expect(detail.getByTestId("glass-width")).toHaveValue("1000");
    await expect(detail.getByTestId("glass-thick")).toHaveValue("6");
    await line.getByRole("checkbox").check();
    await expect(line.getByTestId("glass-cost")).toHaveText("$14.71");     // 10.00 per m2 x 1.471 m2
    await expect(detail.getByTestId("glass-total")).toHaveText("$14.71");
    await detail.getByTestId("glass-clear").click();
    await expect(detail.getByTestId("glass-total")).toHaveText("$0.00");
    rateId = ((await (await page.request.get("/api/glass-rates")).json()) as { rates: { glass_rate_id: number; name: string }[] })
      .rates.find(r => r.name === `Spec glass ${stamp}`)!.glass_rate_id;

    // Timber: the Timberwood Panels form is saved and made into a PDF
    await detail.getByTestId("order-tab-Timber").click();
    await detail.getByTestId("timber-face").fill("Oak veneer");
    await detail.getByTestId("timber-face").blur();
    await detail.getByTestId("timber-substrate-tg").check();
    await detail.getByTestId("timber-special_instructions").fill(`Wrap ${stamp}`);
    await detail.getByTestId("timber-special_instructions").blur();
    await detail.getByTestId("timber-create").click();
    const link = detail.getByTestId("timber-form-link");
    await expect(link).toBeVisible();
    const pdf = await page.request.get((await link.getAttribute("href"))!);
    expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
    const saved = await (await page.request.get(`/api/orders/${order.po_id}/timber`)).json();
    expect(saved.face).toBe("Oak veneer");
    expect(saved.substrate_by_tg).toBe(true);
    await detail.getByTestId("timber-clear").click();
    await expect(detail.getByTestId("timber-face")).toHaveValue("");
    await expect(async () => {
      expect((await (await page.request.get(`/api/orders/${order.po_id}/timber`)).json()).face).toBeNull();
    }).toPass();

    // TGSolid: production rows
    await detail.getByTestId("order-tab-TGSolid").click();
    await detail.getByTestId("tg-new-production_start").fill("2026-08-11");
    await detail.getByTestId("tg-new-made_by").fill("Alex");
    await detail.getByTestId("tg-new-location").fill("#3");
    await detail.getByTestId("tg-add").click();
    await expect(detail.getByTestId("tg-row")).toHaveCount(1);
    await expect(detail.getByTestId("tg-row").getByLabel("Made by")).toHaveValue("Alex");
    await detail.getByTestId("tg-remove").click();
    await expect(detail.getByTestId("tg-row")).toHaveCount(0);
  } finally {
    // put back what this spec added: the rate is switched off and the order cancelled
    if (rateId) await page.request.patch(`/api/glass-rates/${rateId}`, { data: { is_active: false } });
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});

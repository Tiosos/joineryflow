import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const BUYER = "mina.klee@hartwood.test"; // purchase officer
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

test("the FILE and PDF boxes hold an order's files; a closed order's files can only be opened", async ({ page }) => {
  const stamp = Date.now();
  await login(page, BUYER);
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const order = (await (await page.request.post("/api/orders", {
    data: { vendor_id: vendors.suppliers[0].vendor_id, description: `Attach ${stamp}`, category: "Board", total_amount: "5.00" },
  })).json()) as { po_id: number; po_number: string };
  try {
    await page.goto(`/orderbook?order=${order.po_number}`);
    const boxes = page.getByTestId("order-attachments");
    await expect(boxes).toBeVisible();

    await boxes.getByTestId("order-attachment-input-PDF").setInputFiles({ name: `quote-${stamp}.pdf`, mimeType: "application/pdf", buffer: PDF });
    await expect(boxes.getByTestId("order-attachments-PDF").getByTestId("order-attachment")).toContainText(`quote-${stamp}.pdf`);
    await expect(boxes.getByTestId("order-attachments-File").getByTestId("order-attachment")).toHaveCount(0);

    // a file the store refuses says so
    await boxes.getByTestId("order-attachment-input-File").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello there, not allowed") });
    await expect(boxes.getByTestId("order-attachment-error")).toContainText("not allowed");

    // a stored file opens
    const link = boxes.getByTestId("order-attachment").first().locator("a");
    const href = await link.getAttribute("href");
    const got = await page.request.get(href!);
    expect(got.ok()).toBe(true);
    expect((await got.body()).subarray(0, 4).toString()).toBe("%PDF");

    // remove it again
    await boxes.getByTestId("order-attachment-remove").click();
    await expect(boxes.getByTestId("order-attachment")).toHaveCount(0);

    // a Cancelled order keeps its files but offers no change
    await boxes.getByTestId("order-attachment-input-File").setInputFiles({ name: `plan-${stamp}.pdf`, mimeType: "application/pdf", buffer: PDF });
    await expect(boxes.getByTestId("order-attachment")).toHaveCount(1);
    expect((await page.request.patch(`/api/orders/${order.po_id}`, { data: { status: "Cancelled" } })).ok()).toBe(true);
    await page.goto(`/orderbook?order=${order.po_number}`);
    await expect(boxes.getByTestId("order-attachment")).toHaveCount(1);
    await expect(boxes.getByTestId("order-attachment-remove")).toHaveCount(0);
    await expect(boxes.getByTestId("order-attachment-input-File")).toHaveCount(0);
  } finally {
    await page.request.delete(`/api/orders/${order.po_id}`);
  }
});

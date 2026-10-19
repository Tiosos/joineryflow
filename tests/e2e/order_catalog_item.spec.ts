import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

test("the order pop-up shows the catalog item behind the product code, read-only, and follows an edited code", async ({ page }) => {
  const stamp = Date.now();
  await login(page);
  const edging = `OCI-E-${stamp}`;
  const glass = `OCI-G-${stamp}`;
  const e = (await (await page.request.post("/api/catalog/edging-materials", {
    data: { sku: edging, description: `Edge ${stamp}`, colour: "Walnut", edge_type: "ABS", roll_length_m: 50, glued: true,
            um: "roll", product_website: "https://example.test/edge" },
  })).json()) as { material_id: number };
  const g = (await (await page.request.post("/api/catalog/glass-materials", {
    data: { sku: glass, description: `Pane ${stamp}`, glass_type: "Float", thickness_mm: 6, um: "m2",
            product_website: "javascript:alert(1)" },
  })).json()) as { material_id: number };
  await page.request.put(`/api/catalog/glass-materials/${g.material_id}/image`, {
    multipart: { file: { name: "g.png", mimeType: "image/png", buffer: PNG } },
  });
  const board = `OCI-B-${stamp}`;
  const b = (await (await page.request.post("/api/catalog/board-materials", {
    data: { code: board, sku: board, description: `Sheet ${stamp}`, colour: "White", sheet_len_mm: 3600, sheet_wid_mm: 1200,
            thickness_mm: 0.7 },
  })).json()) as { material_id: number };
  const vendors = (await (await page.request.get("/api/suppliers")).json()) as { suppliers: { vendor_id: number }[] };
  const order = (await (await page.request.post("/api/orders", {
    data: { vendor_id: vendors.suppliers[0].vendor_id, description: `Catalog item ${stamp}`, category: "Edging", quantity: 1,
            unit_cost: "5.00", total_amount: "5.00", product_code: edging.toLowerCase() },
  })).json()) as { po_id: number; po_number: string };
  try {
    await page.goto(`/orderbook?order=${order.po_number}`);
    const detail = page.getByTestId("order-detail");
    const block = detail.getByTestId("order-catalog-item");
    await expect(block).toBeVisible();
    await expect(block).toContainText("Edging");
    await expect(block.getByTestId("order-catalog-sku")).toHaveText(edging);
    await expect(block.getByTestId("order-catalog-um")).toHaveText("roll");
    await expect(block.getByTestId("order-catalog-field-colour")).toContainText("Walnut");
    await expect(block.getByTestId("order-catalog-field-edge_type")).toContainText("ABS");
    await expect(block.getByTestId("order-catalog-field-roll_length_m")).toContainText("50");
    await expect(block.getByTestId("order-catalog-field-glued")).toContainText("Yes");
    await expect(block.getByTestId("order-catalog-website").getByRole("link")).toHaveAttribute("href", "https://example.test/edge");
    await expect(block.getByTestId("order-catalog-image")).toHaveCount(0);

    // editing the product code swaps the item; a javascript: website is plain text, never a link; the picture loads
    await detail.getByTestId("order-product-code").fill(glass);
    await detail.getByTestId("order-product-code").blur();
    await expect(block.getByTestId("order-catalog-sku")).toHaveText(glass);
    await expect(block).toContainText("Glass");
    await expect(block.getByTestId("order-catalog-field-glass_type")).toContainText("Float");
    await expect(block.getByTestId("order-catalog-website")).toHaveText("javascript:alert(1)");
    await expect(block.getByTestId("order-catalog-website").getByRole("link")).toHaveCount(0);
    const img = block.getByTestId("order-catalog-image");
    await expect(img).toBeVisible();
    await expect(img).toHaveAttribute("alt", new RegExp(glass));
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);

    // a Board shows its sheet size as one line, "length x width x thickness"; with one value missing each shows alone
    await detail.getByTestId("order-product-code").fill(board);
    await detail.getByTestId("order-product-code").blur();
    await expect(block.getByTestId("order-catalog-sku")).toHaveText(board);
    await expect(block.getByTestId("order-catalog-field-sheet_size")).toContainText("3600 x 1200 x 0.7");
    await expect(block.getByTestId("order-catalog-field-sheet_len_mm")).toHaveCount(0);
    await page.request.patch(`/api/catalog/board-materials/${b.material_id}`, { data: { sheet_wid_mm: null } });
    await page.reload();                                                          // the block asks again on a new look
    await expect(block.getByTestId("order-catalog-field-sheet_size")).toHaveCount(0);
    await expect(block.getByTestId("order-catalog-field-sheet_len_mm")).toContainText("3600");
    await expect(block.getByTestId("order-catalog-field-thickness_mm")).toContainText("0.7");

    // a code no catalog row has: nothing shown
    await detail.getByTestId("order-product-code").fill(`nothing-${stamp}`);
    await detail.getByTestId("order-product-code").blur();
    await expect(block).toHaveCount(0);

    // the order did not take any catalog field
    const o = (await (await page.request.get(`/api/orders/${order.po_id}`)).json()) as Record<string, unknown>;
    expect(o.product_code).toBe(`nothing-${stamp}`);
    expect(o).not.toHaveProperty("colour");
  } finally {
    await page.request.delete(`/api/orders/${order.po_id}`);
    await page.request.post(`/api/catalog/edging-materials/${e.material_id}/archive`);
    await page.request.post(`/api/catalog/glass-materials/${g.material_id}/archive`);
    await page.request.post(`/api/catalog/board-materials/${b.material_id}/archive`);
  }
});

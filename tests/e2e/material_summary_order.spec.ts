import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Material Summary → "Order" on a line raises a Pending order for what is not yet on one.
 *
 * Builds everything it needs through the API (a board of its own, linked to a seeded
 * supplier, in a project of its own) and archives the board afterwards, so it passes on a
 * second run against the same database. The order it raises stays, as no order is deleted.
 */
test("a summary line can raise an order for what it still needs, once", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const sku = `E2E-SUM-${stamp}`;
  const api = async (method: "get" | "post" | "patch", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.status() === 204 ? null : r.json();
  };
  const listed = await api("get", "/suppliers");
  const supplier = (listed.suppliers ?? listed as { vendor_id: number; name: string }[])
    .find((v: { name: string }) => v.name === "Plyco");
  expect(supplier, "seeded supplier Plyco").toBeTruthy();
  const board = await api("post", "/catalog/board-materials", {
    code: sku, sku, description: `E2E summary board ${stamp}`, cost_per_sheet: 50,
    default_supplier_id: supplier!.vendor_id,
  });
  try {
    const pid = (await api("post", "/projects", { project_code: `SO-${stamp}`, name: `Summary order ${stamp}` })).id as number;
    const item = await api("post", `/projects/${pid}/items`, { description: `Summary order item ${stamp}` });
    const mod = await api("post", `/items/${item.id}/modules`, { module_no: "1" });
    await api("post", `/modules/${mod.id}/parts`,
      { qty: 2, len_mm: 720, wid_mm: 560, board_material_id: board.material_id });
    const take = await api("post", `/items/${item.id}/material-take/generate`);
    await api("post", `/material-takes/${take.take_id}/approve`);
    await api("post", `/projects/${pid}/material-summary`);

    await page.goto(`/projects/${pid}/procurement?tab=summary`);
    const order = page.getByTestId("summary-order");
    await expect(order).toBeVisible();
    await expect(page.getByText("unconfirmed", { exact: true })).toBeVisible();
    await order.click();
    await expect(page.getByTestId("summary-order-raised")).toContainText("raised (Pending)");
    // Raised, though not placed: the line is covered, so there is nothing left to order.
    await expect(page.getByTestId("summary-order")).toHaveCount(0);
    const po = await page.getByTestId("summary-order-raised").getByRole("link", { name: "Open it" }).getAttribute("href");
    const id = Number(new URL(po!, "http://x").searchParams.get("order"));
    const raised = await api("get", `/orders/${id}`);
    expect(raised).toMatchObject({ status: "Pending", product_code: sku, project_id: pid, vendor_id: supplier!.vendor_id });

    // Placed with the supplier, the order counts as ordered, and the figure links to it.
    await api("patch", `/orders/${id}`, { date_ordered: new Date().toISOString().slice(0, 10) });
    await page.goto(`/projects/${pid}/procurement?tab=summary`);
    await page.getByTestId("summary-ordered-link").click();
    await expect(page.getByTestId("product-code-filter")).toContainText(sku);
    await expect(page.getByText("1 order", { exact: true })).toBeVisible();
    await expect(page.getByText(raised.po_number)).toBeVisible();
  } finally {
    await page.request.post(`/api/catalog/board-materials/${board.material_id}/archive`);
  }
});

test("a line that cannot be ordered says why and links to the Catalog", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const sku = `E2E-SUMB-${stamp}`;
  const api = async (method: "get" | "post", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.status() === 204 ? null : r.json();
  };
  const description = `E2E blocked board ${stamp}`;
  const board = await api("post", "/catalog/board-materials", { code: sku, sku, description });   // no supplier
  try {
    const pid = (await api("post", "/projects", { project_code: `SB-${stamp}`, name: `Summary blocked ${stamp}` })).id as number;
    const item = await api("post", `/projects/${pid}/items`, { description: `Summary blocked item ${stamp}` });
    const mod = await api("post", `/items/${item.id}/modules`, { module_no: "1" });
    await api("post", `/modules/${mod.id}/parts`, { qty: 2, len_mm: 720, wid_mm: 560, board_material_id: board.material_id });
    const take = await api("post", `/items/${item.id}/material-take/generate`);
    await api("post", `/material-takes/${take.take_id}/approve`);
    await api("post", `/projects/${pid}/material-summary`);

    await page.goto(`/projects/${pid}/procurement?tab=summary`);
    await expect(page.getByTestId("summary-order")).toHaveCount(0);
    await expect(page.getByTestId("summary-order-block")).toContainText("No default supplier.");
    await expect(page.getByTestId("summary-blocked")).toContainText("1 line can't be ordered yet (1 no supplier)");
    await page.getByTestId("summary-order-block-link").click();
    await expect(page).toHaveURL(/\/catalog\?tab=board/);
    await expect(page.locator(`tbody input[value="${description}"]`)).toBeVisible({ timeout: 30_000 });
  } finally {
    await page.request.post(`/api/catalog/board-materials/${board.material_id}/archive`);
  }
});

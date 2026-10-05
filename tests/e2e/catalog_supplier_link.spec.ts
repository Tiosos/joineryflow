import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * The Catalog grid's **Supplier link** column sets `default_supplier_id` — the FK
 * Generate Orders groups a won quote's materials by (the free-text Default supplier
 * next to it is not what it reads).
 *
 * Seed facts relied on: BM-101 "19mm Melamine White" is linked to Laminex Australia;
 * BM-203 "25mm Stainless 304 Sheet" has the free text "CDK Stone" and **no** supplier
 * (no vendor of that name), so it is the unlinked demo row; Plyco is a supplier.
 * Every test puts BM-203 back unlinked.
 */

const MANAGER = "rin.park@hartwood.test";
const VIEWER = "sam.ito@hartwood.test";
const ESTIMATOR = "kai.ngata@hartwood.test";

/** The grid row whose Description cell (an input for writers, text for readers) holds `description`. */
function gridRow(page: Page, description: string) {
  return page.locator("tbody tr").filter({
    has: page.locator(`input[value="${description}"], td > span:text-is("${description}")`),
  });
}

async function openBoards(page: Page, q?: string) {
  await page.goto(`/catalog?tab=board${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  await expect(page.getByRole("columnheader", { name: "Supplier link" })).toBeVisible({ timeout: 30_000 });
}

/** The select's current value as the option's label — what a person reads. */
async function shownSupplier(row: ReturnType<typeof gridRow>): Promise<string> {
  const sel = row.getByLabel("Supplier link");
  return (await sel.locator("option:checked").textContent())?.trim() ?? "";
}

async function unlinkViaApi(page: Page, id: number) {
  await page.request.patch(`/api/catalog/board-materials/${id}`, { data: { default_supplier_id: null } });
}

async function boardId(page: Page, sku: string): Promise<number> {
  const body = await (await page.request.get(`/api/catalog/board-materials?q=${encodeURIComponent(sku)}`)).json();
  return body.rows.find((r: { sku: string }) => r.sku === sku).material_id;
}

test("a seeded row shows its supplier; an unlinked row is flagged and counted", async ({ page }) => {
  await login(page, MANAGER);
  await openBoards(page);
  expect(await shownSupplier(gridRow(page, "19mm Melamine White"))).toBe("Laminex Australia");
  expect(await shownSupplier(gridRow(page, "25mm Stainless 304 Sheet"))).toBe("Not linked");
  await expect(page.getByTestId("unlinked-count")).toContainText("have no supplier link");
  // the free text beside it is a different column and is left as it was
  await expect(
    gridRow(page, "25mm Stainless 304 Sheet").locator('input[value="CDK Stone"]'),
  ).toBeVisible();
});

test("picking a supplier links the row, survives a reload, and clearing unlinks it", async ({ page }) => {
  await login(page, MANAGER);
  const id = await boardId(page, "25-SS304");
  try {
    await openBoards(page, "Stainless");
    const row = gridRow(page, "25mm Stainless 304 Sheet");
    await row.getByLabel("Supplier link").selectOption({ label: "Plyco" });
    await expect.poll(async () => {
      const r = await (await page.request.get(`/api/catalog/board-materials/${id}`)).json();
      return r.default_supplier_name;
    }).toBe("Plyco");
    // the free text is untouched by a pick
    expect((await (await page.request.get(`/api/catalog/board-materials/${id}`)).json()).default_supplier)
      .toBe("CDK Stone");

    await page.reload();
    expect(await shownSupplier(gridRow(page, "25mm Stainless 304 Sheet"))).toBe("Plyco");

    await gridRow(page, "25mm Stainless 304 Sheet").getByLabel("Supplier link").selectOption({ label: "Not linked" });
    await expect.poll(async () => {
      const r = await (await page.request.get(`/api/catalog/board-materials/${id}`)).json();
      return r.default_supplier_id;
    }).toBeNull();
  } finally {
    await unlinkViaApi(page, id);
  }
});

test("the 'Not linked' filter narrows the grid, lives in the URL and survives a reload", async ({ page }) => {
  await login(page, MANAGER);
  await openBoards(page);
  await page.getByLabel("Supplier link filter").selectOption("unlinked");
  await expect(page).toHaveURL(/link=unlinked/);
  await expect(gridRow(page, "25mm Stainless 304 Sheet")).toHaveCount(1);
  await expect(gridRow(page, "19mm Melamine White")).toHaveCount(0);

  await page.reload();
  await expect(page.getByLabel("Supplier link filter")).toHaveValue("unlinked");
  await expect(gridRow(page, "19mm Melamine White")).toHaveCount(0);

  await page.getByLabel("Supplier link filter").selectOption("linked");
  await expect(gridRow(page, "19mm Melamine White")).toHaveCount(1);
  await expect(gridRow(page, "25mm Stainless 304 Sheet")).toHaveCount(0);
});

test("a reader sees the supplier names and has no picker", async ({ page }) => {
  await login(page, VIEWER);
  await openBoards(page);
  await expect(page.getByLabel("Supplier link", { exact: true })).toHaveCount(0);
  const cell = gridRow(page, "19mm Melamine White").getByTestId("supplier-link-cell");
  await expect(cell).toHaveText("Laminex Australia");
  await expect(
    gridRow(page, "25mm Stainless 304 Sheet").getByTestId("supplier-unlinked"),
  ).toHaveText("Not linked");
});

test("when the supplier list cannot be read the picker is disabled and says why", async ({ page }) => {
  await login(page, MANAGER);
  await page.route("**/api/suppliers", (route) => route.fulfill({ status: 403, body: "{}" }));
  await openBoards(page);
  await expect(page.getByTestId("suppliers-unreadable")).toBeVisible({ timeout: 15_000 });
  const row = gridRow(page, "19mm Melamine White");
  await expect(row.getByLabel("Supplier link")).toBeDisabled();
  // a linked row still shows its supplier rather than "Not linked"
  expect(await shownSupplier(row)).toBe("Laminex Australia");
});

test("a material linked in the Catalog is ordered from that supplier by Generate Orders", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();
  const sku = `E2E-LINK-${stamp}`;
  const description = `E2E linked board ${stamp}`;

  // 1. A brand-new board, linked to Plyco through the grid.
  const created = await page.request.post("/api/catalog/board-materials", {
    data: { code: sku, sku, description, cost_per_sheet: 50 },
  });
  expect(created.status()).toBe(201);
  const materialId = (await created.json()).material_id as number;
  try {
    await openBoards(page, description);
    await gridRow(page, description).getByLabel("Supplier link").selectOption({ label: "Plyco" });
    await expect.poll(async () => {
      const r = await (await page.request.get(`/api/catalog/board-materials/${materialId}`)).json();
      return r.default_supplier_name;
    }).toBe("Plyco");

    // 2. A won, converted quote that uses it (built through the API).
    const post = async (url: string, data?: unknown) => {
      const r = await page.request.post(`/api${url}`, data === undefined ? {} : { data });
      expect(r.ok(), `${url} -> ${r.status()} ${await r.text()}`).toBe(true);
      return r.json();
    };
    const cust = await post("/customers", { name: `E2E customer ${stamp}` });
    const est = await post("/estimates", { customer_id: cust.customer_id, title: `E2E ${stamp}` });
    const rid = est.current_revision_id as number;
    const line = await post(`/revisions/${rid}/lines`, { description: "Linked board line", qty: 1 });
    await post(`/lines/${line.line_id}/parts`, { material_type: "BOARD", material_id: materialId, qty: 4 });
    for (let i = 0; i < 10; i++) await post(`/revisions/${rid}/advance`);
    await post(`/revisions/${rid}/accept`);
    await post(`/revisions/${rid}/convert`);

    // 3. Generate Orders names Plyco as the supplier, with no unassigned materials.
    await page.goto(`/estimating/${est.estimate_id}`);
    await page.getByTestId("generate-orders-btn").click();
    const dialog = page.getByTestId("order-preview-dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    const group = dialog.getByTestId("order-preview-group");
    await expect(group).toHaveCount(1);
    await expect(group).toContainText("Plyco");
    await expect(group).toContainText(description);
    await expect(dialog).not.toContainText("No default supplier");

    await page.getByTestId("generate-orders-confirm-btn").click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });

    // 4. The draft order exists, with Plyco as its supplier.
    const { orders } = await (await page.request.get("/api/orders")).json();
    const mine = (orders as { attributes?: Record<string, unknown>; vendor_name: string }[]).filter(
      (o) => o.attributes?.generated_from_revision_id === rid,
    );
    expect(mine).toHaveLength(1);
    expect(mine[0].vendor_name).toBe("Plyco");
  } finally {
    await page.request.post(`/api/catalog/board-materials/${materialId}/archive`);
  }
});

test("a quote line whose material has no supplier can be ordered after linking it in the Catalog", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();
  const sku = `E2E-NOSUP-${stamp}`;
  const description = `E2E unlinked board ${stamp}`;

  // An unlinked board on a won, converted quote (built through the API).
  const created = await page.request.post("/api/catalog/board-materials", {
    data: { code: sku, sku, description },
  });
  expect(created.status()).toBe(201);
  const materialId = (await created.json()).material_id as number;
  try {
    const post = async (url: string, data?: unknown) => {
      const r = await page.request.post(`/api${url}`, data === undefined ? {} : { data });
      expect(r.ok(), `${url} -> ${r.status()} ${await r.text()}`).toBe(true);
      return r.json();
    };
    const cust = await post("/customers", { name: `E2E customer ${stamp}` });
    const est = await post("/estimates", { customer_id: cust.customer_id, title: `E2E ${stamp}` });
    const rid = est.current_revision_id as number;
    const line = await post(`/revisions/${rid}/lines`, { description: "Unlinked board line", qty: 1 });
    await post(`/lines/${line.line_id}/parts`, { material_type: "BOARD", material_id: materialId, qty: 3 });
    for (let i = 0; i < 10; i++) await post(`/revisions/${rid}/advance`);
    await post(`/revisions/${rid}/accept`);
    await post(`/revisions/${rid}/convert`);

    // 1. Nothing can be ordered yet: the dialog says why and will not generate.
    await page.goto(`/estimating/${est.estimate_id}`);
    await page.getByTestId("generate-orders-btn").click();
    const dialog = page.getByTestId("order-preview-dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByTestId("order-preview-nothing-orderable")).toBeVisible();
    await expect(page.getByTestId("generate-orders-confirm-btn")).toBeDisabled();
    await dialog.getByRole("button", { name: "Cancel" }).click();

    // 2. Link it in the Catalog.
    await openBoards(page, description);
    await gridRow(page, description).getByLabel("Supplier link", { exact: true }).selectOption({ label: "Plyco" });
    await expect.poll(async () => {
      const r = await (await page.request.get(`/api/catalog/board-materials/${materialId}`)).json();
      return r.default_supplier_name;
    }).toBe("Plyco");

    // 3. The same line now orders — it was never locked out.
    await page.goto(`/estimating/${est.estimate_id}`);
    await page.getByTestId("generate-orders-btn").click();
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByTestId("order-preview-group")).toContainText("Plyco");
    await expect(dialog.getByTestId("order-preview-nothing-orderable")).toHaveCount(0);
    await page.getByTestId("generate-orders-confirm-btn").click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });

    const { orders } = await (await page.request.get("/api/orders")).json();
    const mine = (orders as { attributes?: Record<string, unknown>; vendor_name: string }[]).filter(
      (o) => o.attributes?.generated_from_revision_id === rid,
    );
    expect(mine).toHaveLength(1);
    expect(mine[0].vendor_name).toBe("Plyco");
  } finally {
    await page.request.post(`/api/catalog/board-materials/${materialId}/archive`);
  }
});

test("a selection with nothing to order can be confirmed, and the line is marked ordered", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();

  // A won, converted quote whose only line references no catalog material (labour only).
  const post = async (url: string, data?: unknown) => {
    const r = await page.request.post(`/api${url}`, data === undefined ? {} : { data });
    expect(r.ok(), `${url} -> ${r.status()} ${await r.text()}`).toBe(true);
    return r.json();
  };
  const cust = await post("/customers", { name: `E2E customer ${stamp}` });
  const est = await post("/estimates", { customer_id: cust.customer_id, title: `E2E ${stamp}` });
  const rid = est.current_revision_id as number;
  const line = await post(`/revisions/${rid}/lines`, { description: "Labour only line", qty: 1 });
  for (let i = 0; i < 10; i++) await post(`/revisions/${rid}/advance`);
  await post(`/revisions/${rid}/accept`);
  await post(`/revisions/${rid}/convert`);

  await page.goto(`/estimating/${est.estimate_id}`);
  await expect(page.getByText("Converted — materials can now be ordered from this quote.")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("generate-orders-btn").click();
  const dialog = page.getByTestId("order-preview-dialog");
  await expect(dialog).toBeVisible({ timeout: 15_000 });

  // No supplier groups and nothing unassigned: the confirm button is enabled (it used to be disabled
  // whenever there were no groups) and says there is nothing to order.
  await expect(dialog.getByTestId("order-preview-group")).toHaveCount(0);
  await expect(dialog.getByTestId("order-preview-nothing-orderable")).toHaveCount(0);
  const confirm = page.getByTestId("generate-orders-confirm-btn");
  await expect(confirm).toBeEnabled();
  await expect(confirm).toHaveText("Mark ticked lines done (nothing to order)");
  await confirm.click();
  await expect(dialog).toBeHidden({ timeout: 30_000 });

  // The line is covered: the Generate orders bar is gone and the page says orders were generated
  // (with no "last" — nothing is left to order), and no PO was made.
  await page.reload();
  await expect(page.getByText(/^Orders generated /)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("generate-orders-btn")).toHaveCount(0);
  const pv = await (await page.request.get(`/api/revisions/${rid}/order-preview`)).json();
  expect(pv.lines.find((l: { line_id: number }) => l.line_id === line.line_id).orders_generated_at).not.toBeNull();
  const { orders } = await (await page.request.get("/api/orders")).json();
  const mine = (orders as { attributes?: Record<string, unknown> }[]).filter(
    (o) => o.attributes?.generated_from_revision_id === rid,
  );
  expect(mine).toHaveLength(0);
});

test("a row created from the New dialog can be linked to a supplier at once", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();
  const sku = `E2E-NEW-${stamp}`;
  const description = `E2E new board ${stamp}`;
  await openBoards(page);
  await page.getByRole("button", { name: "+ New" }).click();
  const dialog = page.getByRole("heading", { name: /New board/ }).locator("xpath=..");
  await dialog.getByLabel("Description").fill(description);
  await dialog.getByLabel("SKU").fill(sku);
  await dialog.getByLabel("Code").fill(sku);
  await dialog.getByLabel("Supplier link").selectOption({ label: "Plyco" });
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  const id = await boardId(page, sku);
  try {
    const row = await (await page.request.get(`/api/catalog/board-materials/${id}`)).json();
    expect(row.default_supplier_name).toBe("Plyco");
    // and the grid shows it as linked, not flagged
    await openBoards(page, description);
    expect(await shownSupplier(gridRow(page, description))).toBe("Plyco");
  } finally {
    await page.request.post(`/api/catalog/board-materials/${id}/archive`);
  }
});

test("bulk import links rows by supplier name and lists the ones it could not match", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();
  const a = `E2E-BLK-A-${stamp}`;
  const b = `E2E-BLK-B-${stamp}`;
  await openBoards(page);
  await page.getByRole("button", { name: "Bulk import" }).click();
  await page.getByPlaceholder(/header1,header2/).fill(
    "code,sku,description,default_supplier\n" +
    `${a},${a},E2E bulk match ${stamp},plyco\n` +
    `${b},${b},E2E bulk nomatch ${stamp},Nobody Ltd\n`,
  );
  await page.getByRole("button", { name: /^Import 2 rows$/ }).click();

  const result = page.getByTestId("bulk-import-result");
  await expect(result).toBeVisible({ timeout: 15_000 });
  await expect(result.getByTestId("bulk-import-linked")).toHaveText("1 linked to a supplier.");
  const unlinked = result.getByTestId("bulk-import-unlinked");
  await expect(unlinked).toContainText("Row 2");
  await expect(unlinked).toContainText("Nobody Ltd");
  await expect(unlinked).not.toContainText("Row 1");
  await result.getByRole("button", { name: "Done" }).click();
  await expect(result).toBeHidden();

  const idA = await boardId(page, a);
  const idB = await boardId(page, b);
  try {
    const rowA = await (await page.request.get(`/api/catalog/board-materials/${idA}`)).json();
    const rowB = await (await page.request.get(`/api/catalog/board-materials/${idB}`)).json();
    expect(rowA.default_supplier_name).toBe("Plyco");
    expect(rowB.default_supplier_id).toBeNull();
    expect(rowB.default_supplier).toBe("Nobody Ltd");
  } finally {
    await page.request.post(`/api/catalog/board-materials/${idA}/archive`);
    await page.request.post(`/api/catalog/board-materials/${idB}/archive`);
  }
});

test("a CV import's Create new row can be linked to a supplier", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();
  const code = `E2E-CV-${stamp}`;
  // JO-TP01 is the item the CV specs share: seeded with no modules, and a re-run offers Replace.
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: "JO-TP01" });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  await page.goto(`${href}?tab=cutlist`);
  await page.getByRole("button", { name: /Import from CV/i }).click();
  await page.getByPlaceholder(/Module,Part Name/).fill(
    `Module,Part Name,Qty,Length,Width,Material\n1,Side L,1,720,580,${code}\n`,
  );
  await page.getByRole("button", { name: /^Preview$/ }).click();
  await expect(page.getByText(code).first()).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: /^Create new$/ }).first().click();
  await page.getByPlaceholder(code).fill(code);
  await page.getByPlaceholder(/18mm Particleboard/).fill(`E2E cv board ${stamp}`);
  await page.getByLabel("Supplier link").selectOption({ label: "Plyco" });
  await page.getByRole("button", { name: /^Continue$/ }).click();
  const replace = page.getByRole("checkbox", { name: /Replace existing modules/i });
  await expect(page.getByRole("button", { name: /^Import$/ })).toBeVisible({ timeout: 15_000 });
  if (await replace.count()) await replace.check();
  await page.getByRole("button", { name: /^Import$/ }).click();
  await expect(page.getByText(/imported/i)).toBeVisible({ timeout: 15_000 });

  const id = await boardId(page, code);
  try {
    const created = await (await page.request.get(`/api/catalog/board-materials/${id}`)).json();
    expect(created.default_supplier_name).toBe("Plyco");
  } finally {
    await page.request.post(`/api/catalog/board-materials/${id}/archive`);
    const maps = await (await page.request.get(`/api/catalog/cv-mappings?q=${encodeURIComponent(code)}`)).json();
    for (const m of (maps.mappings ?? maps.rows ?? maps) as { cv_material_mapping_id: number }[]) {
      await page.request.delete(`/api/catalog/cv-mappings/${m.cv_material_mapping_id}`);
    }
  }
});

test("an estimator links a supplier from the Generate Orders dialog and orders", async ({ page }) => {
  // The estimator holds estimating:approve but neither catalog:write nor orderbook:write, so this
  // can only work through the narrow estimating route. Setup (catalog row, quote) is the manager's.
  await login(page, MANAGER);
  const stamp = Date.now();
  const sku = `E2E-EST-${stamp}`;
  const description = `E2E estimator board ${stamp}`;
  const created = await page.request.post("/api/catalog/board-materials", {
    data: { code: sku, sku, description },
  });
  expect(created.status()).toBe(201);
  const materialId = (await created.json()).material_id as number;
  const post = async (url: string, data?: unknown) => {
    const r = await page.request.post(`/api${url}`, data === undefined ? {} : { data });
    expect(r.ok(), `${url} -> ${r.status()} ${await r.text()}`).toBe(true);
    return r.json();
  };
  try {
    const cust = await post("/customers", { name: `E2E customer ${stamp}` });
    const est = await post("/estimates", { customer_id: cust.customer_id, title: `E2E ${stamp}` });
    const rid = est.current_revision_id as number;
    const line = await post(`/revisions/${rid}/lines`, { description: "Estimator line", qty: 1 });
    await post(`/lines/${line.line_id}/parts`, { material_type: "BOARD", material_id: materialId, qty: 2 });
    for (let i = 0; i < 10; i++) await post(`/revisions/${rid}/advance`);
    await post(`/revisions/${rid}/accept`);
    await post(`/revisions/${rid}/convert`);

    // The estimator cannot edit the catalog (the control for why the route is narrow).
    await page.context().clearCookies();
    await login(page, ESTIMATOR);
    const denied = await page.request.patch(`/api/catalog/board-materials/${materialId}`, {
      data: { default_supplier_id: 1 },
    });
    expect(denied.status()).toBe(403);

    await page.goto(`/estimating/${est.estimate_id}`);
    await page.getByTestId("generate-orders-btn").click();
    const dialog = page.getByTestId("order-preview-dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByTestId("order-preview-nothing-orderable")).toBeVisible();
    await expect(page.getByTestId("generate-orders-confirm-btn")).toBeDisabled();

    // Link it from the dialog: the material leaves "no supplier" and a Plyco order appears.
    await dialog.getByTestId(`link-supplier-BOARD-${materialId}`).selectOption({ label: "Plyco" });
    await expect(dialog.getByTestId("order-preview-nothing-orderable")).toHaveCount(0, { timeout: 15_000 });
    await expect(dialog.getByTestId("order-preview-group")).toContainText("Plyco");
    await expect(page.getByTestId("generate-orders-confirm-btn")).toBeEnabled();
    await page.getByTestId("generate-orders-confirm-btn").click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });

    const { orders } = await (await page.request.get("/api/orders")).json();
    const mine = (orders as { attributes?: Record<string, unknown>; vendor_name: string }[]).filter(
      (o) => o.attributes?.generated_from_revision_id === rid,
    );
    expect(mine).toHaveLength(1);
    expect(mine[0].vendor_name).toBe("Plyco");
  } finally {
    await page.context().clearCookies();
    await login(page, MANAGER);
    await page.request.post(`/api/catalog/board-materials/${materialId}/archive`);
  }
});

test("a held-back line can be marked ordered by hand (reason required), and undone", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();
  const sku = `E2E-BYHAND-${stamp}`;
  const created = await page.request.post("/api/catalog/board-materials", {
    data: { code: sku, sku, description: `E2E by-hand board ${stamp}` },
  });
  expect(created.status()).toBe(201);
  const materialId = (await created.json()).material_id as number;
  try {
    const post = async (url: string, data?: unknown) => {
      const r = await page.request.post(`/api${url}`, data === undefined ? {} : { data });
      expect(r.ok(), `${url} -> ${r.status()} ${await r.text()}`).toBe(true);
      return r.json();
    };
    // A won, converted quote whose only line uses a board with no supplier: held back whole.
    const cust = await post("/customers", { name: `E2E customer ${stamp}` });
    const est = await post("/estimates", { customer_id: cust.customer_id, title: `E2E ${stamp}` });
    const rid = est.current_revision_id as number;
    const line = await post(`/revisions/${rid}/lines`, { description: "Ordered-by-phone line", qty: 1 });
    await post(`/lines/${line.line_id}/parts`, { material_type: "BOARD", material_id: materialId, qty: 2 });
    for (let i = 0; i < 10; i++) await post(`/revisions/${rid}/advance`);
    await post(`/revisions/${rid}/accept`);
    await post(`/revisions/${rid}/convert`);
    const lineId = line.line_id as number;

    await page.goto(`/estimating/${est.estimate_id}`);
    await page.getByTestId("generate-orders-btn").click();
    const dialog = page.getByTestId("order-preview-dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByTestId(`order-line-held-${lineId}`)).toBeVisible();
    await expect(page.getByTestId("generate-orders-confirm-btn")).toBeDisabled();

    // The reason is required: Save stays disabled until there is one.
    await dialog.getByTestId(`dismiss-line-${lineId}`).click();
    await expect(dialog.getByTestId("dismiss-save")).toBeDisabled();
    await dialog.getByTestId("dismiss-reason").fill("   ");
    await expect(dialog.getByTestId("dismiss-save")).toBeDisabled();
    await dialog.getByTestId("dismiss-reason").fill("ordered by phone from CDK");
    await dialog.getByTestId("dismiss-save").click();

    // It now reads as ordered by hand, with who and why, and nothing is left to generate.
    const byHand = dialog.getByTestId(`order-line-byhand-${lineId}`);
    await expect(byHand).toContainText("ordered by hand", { timeout: 15_000 });
    await expect(byHand).toContainText("ordered by phone from CDK");
    await expect(dialog.getByTestId(`order-line-${lineId}`)).toBeDisabled();
    await expect(dialog.getByTestId(`order-line-${lineId}`)).not.toBeChecked();
    await expect(dialog.getByTestId("order-preview-nothing-orderable")).toHaveCount(0);
    await expect(page.getByTestId("generate-orders-confirm-btn")).toBeDisabled();
    await dialog.getByRole("button", { name: "Cancel" }).click();

    // The page's own count follows: nothing pending, one line marked, and the button now reviews.
    await expect(page.getByTestId("orders-bar-text")).toHaveText("1 line marked ordered by hand.");
    await expect(page.getByTestId("generate-orders-btn")).toHaveText("Review lines");
    let flags = await (await page.request.get(`/api/revisions/${rid}/order-preview`)).json();
    expect(flags.lines[0].orders_dismissed_reason).toBe("ordered by phone from CDK");
    expect(flags.lines[0].orders_generated_at).toBeNull();

    // Undo: the line is pending (and held back) again, and the bar is back.
    await page.getByTestId("generate-orders-btn").click();
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await dialog.getByTestId(`undo-dismiss-${lineId}`).click();
    await expect(dialog.getByTestId(`order-line-${lineId}`)).toBeEnabled({ timeout: 15_000 });
    await expect(dialog.getByTestId(`order-line-${lineId}`)).toBeChecked();
    await expect(dialog.getByTestId(`order-line-held-${lineId}`)).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByTestId("generate-orders-btn")).toHaveText("Generate orders");
    flags = await (await page.request.get(`/api/revisions/${rid}/order-preview`)).json();
    expect(flags.lines[0].orders_dismissed_at).toBeNull();
  } finally {
    await page.request.post(`/api/catalog/board-materials/${materialId}/archive`);
  }
});

test("a line's materials are ordered separately: the supplied one orders, the other is marked by hand", async ({ page }) => {
  await login(page, MANAGER);
  const stamp = Date.now();
  const made: number[] = [];
  try {
    const suppliers = await (await page.request.get("/api/suppliers")).json();
    const plyco = (suppliers.suppliers ?? suppliers).find((s: { name: string }) => s.name === "Plyco");
    const board = async (tag: string, extra: Record<string, unknown>) => {
      const sku = `E2E-${tag}-${stamp}`;
      const r = await page.request.post("/api/catalog/board-materials", {
        data: { code: sku, sku, description: `E2E ${tag} ${stamp}`, ...extra },
      });
      expect(r.status()).toBe(201);
      const id = (await r.json()).material_id as number;
      made.push(id);
      return id;
    };
    const supplied = await board("SUPPLIED", { default_supplier_id: plyco.vendor_id });
    const orphan = await board("ORPHAN", {});
    const post = async (url: string, data?: unknown) => {
      const r = await page.request.post(`/api${url}`, data === undefined ? {} : { data });
      expect(r.ok(), `${url} -> ${r.status()} ${await r.text()}`).toBe(true);
      return r.json();
    };
    const cust = await post("/customers", { name: `E2E customer ${stamp}` });
    const est = await post("/estimates", { customer_id: cust.customer_id, title: `E2E ${stamp}` });
    const rid = est.current_revision_id as number;
    const line = await post(`/revisions/${rid}/lines`, { description: "Two-material line", qty: 1 });
    await post(`/lines/${line.line_id}/parts`, { material_type: "BOARD", material_id: supplied, qty: 2 });
    await post(`/lines/${line.line_id}/parts`, { material_type: "BOARD", material_id: orphan, qty: 1 });
    for (let i = 0; i < 10; i++) await post(`/revisions/${rid}/advance`);
    await post(`/revisions/${rid}/accept`);
    await post(`/revisions/${rid}/convert`);
    const lineId = line.line_id as number;

    await page.goto(`/estimating/${est.estimate_id}`);
    await page.getByTestId("generate-orders-btn").click();
    const dialog = page.getByTestId("order-preview-dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    // The supplied material is orderable now; the other is flagged, per material.
    await expect(dialog.getByTestId("order-preview-group")).toContainText("Plyco");
    await expect(dialog.getByTestId(`order-line-held-${lineId}`)).toBeVisible();
    const orphanState = dialog.getByTestId(`order-material-state-${lineId}-BOARD-${orphan}`);
    await expect(orphanState).toHaveText("no supplier");
    await expect(dialog.getByTestId(`order-material-state-${lineId}-BOARD-${supplied}`)).toHaveText("to order");
    await expect(page.getByTestId("generate-orders-confirm-btn")).toBeEnabled();

    // Mark just the unsupplied one ordered by hand (reason required).
    await dialog.getByTestId(`dismiss-material-${lineId}-BOARD-${orphan}`).click();
    await expect(dialog.getByTestId("dismiss-save")).toBeDisabled();
    await dialog.getByTestId("dismiss-reason").fill("phoned the stone yard");
    await dialog.getByTestId("dismiss-save").click();
    await expect(orphanState).toContainText("phoned the stone yard", { timeout: 15_000 });
    await expect(dialog.getByTestId(`order-line-held-${lineId}`)).toHaveCount(0);
    await expect(dialog.getByTestId(`order-material-state-${lineId}-BOARD-${supplied}`)).toHaveText("to order");

    // Undo puts it back to pending / no supplier; mark it again, then order the rest.
    await dialog.getByTestId(`undo-dismiss-material-${lineId}-BOARD-${orphan}`).click();
    await expect(orphanState).toHaveText("no supplier", { timeout: 15_000 });
    await dialog.getByTestId(`dismiss-material-${lineId}-BOARD-${orphan}`).click();
    await dialog.getByTestId("dismiss-reason").fill("phoned the stone yard");
    await dialog.getByTestId("dismiss-save").click();
    await expect(orphanState).toContainText("phoned the stone yard", { timeout: 15_000 });

    await page.getByTestId("generate-orders-confirm-btn").click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });

    const { orders } = await (await page.request.get("/api/orders")).json();
    const mine = (orders as { attributes?: Record<string, unknown>; vendor_name: string }[]).filter(
      (o) => o.attributes?.generated_from_revision_id === rid,
    );
    expect(mine).toHaveLength(1);
    expect(mine[0].vendor_name).toBe("Plyco");
    // Nothing is left to order on the quote.
    const pv = await (await page.request.get(`/api/revisions/${rid}/order-preview`)).json();
    expect(pv.lines[0].selected).toBe(false);
    const states = Object.fromEntries(
      pv.lines[0].materials.map((m: { material_id: number; state: string }) => [m.material_id, m.state]),
    );
    expect(states).toEqual({ [supplied]: "generated", [orphan]: "dismissed" });
  } finally {
    for (const id of made) await page.request.post(`/api/catalog/board-materials/${id}/archive`);
  }
});

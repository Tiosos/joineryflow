import { test, expect, type Page } from "@playwright/test";

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
const PASSWORD = "hartwood-dev";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

const MANAGER = "rin.park@hartwood.test";
const VIEWER = "sam.ito@hartwood.test";

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

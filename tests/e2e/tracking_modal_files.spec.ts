import { test, expect, type Page } from "@playwright/test";

/**
 * The Tracking item modal shows the item's SketchUp / CabVision slots and its Document
 * Register (read-only — editing is on the item editor's Attachments tab). These used to
 * be hard-coded placeholders ("—" and "No documents attached for v1.").
 *
 * The one test that binds a slot removes it again, so the seed is left as found.
 */
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

/** Open the modal for the Tracking row whose code is `code`; returns the item id. */
async function openModal(page: Page, code: string): Promise<number> {
  await page.goto("/tracking?project_id=1");
  const row = page.locator('[data-testid="tracking-row"]').filter({ hasText: code });
  await expect(row).toHaveCount(1, { timeout: 30_000 });
  const href = await row.locator('a[href^="/items/"]').first().getAttribute("href");
  const id = Number(href!.split("/")[2]);
  // In dev the page may not be hydrated yet, so retry the click until the modal is up.
  await expect(async () => {
    await row.getByRole("button", { name: "Open item details" }).click();
    await expect(page.getByRole("heading", { name: "Item Details" })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  return id;
}

const modalRegister = (page: Page) => page.getByTestId("modal-register");
const registerRows = (page: Page) => modalRegister(page).getByTestId("modal-register-row");
/** The SketchUp / CabVision value cell: the row's second column, next to its label. */
const slotValue = (page: Page, label: string) =>
  page.getByText(label, { exact: true }).locator("xpath=following-sibling::div");

/** The value cell next to a label, scoped to the modal (the grid behind it has its own headers). */
const modalValue = (page: Page, label: string) =>
  page
    .locator("div.fixed.inset-0")
    .filter({ has: page.getByRole("heading", { name: "Item Details" }) })
    .getByText(label, { exact: true })
    .locator("xpath=following-sibling::div");

test("the modal shows the item's reference fields and JID, read-only, instead of dashes", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  const id = await openModal(page, "JO-K-101");
  const item = await (await page.request.get(`/api/items/${id}`)).json();
  // The seed gives this item real values; without them the checks below would pass on dashes.
  for (const f of ["floor_plan", "rls", "joiery_details", "jid_code", "jid_color"]) {
    expect(item[f], `seed should set ${f} on JO-K-101`).toBeTruthy();
  }
  // cutlist_printed defaults to TRUE for every item; the seed sets this one to FALSE so the
  // modal has to tell the two apart (an open circle here, a tick on the next item).
  expect(item.cutlist_printed).toBe(false);

  await expect(modalValue(page, "Floor Plan")).toHaveText(item.floor_plan, { timeout: 15_000 });
  await expect(modalValue(page, "RLS")).toHaveText(item.rls);
  await expect(modalValue(page, "Joiery Details")).toHaveText(item.joiery_details);
  await expect(modalValue(page, "Cutlist Printed?").locator("span.rounded-full")).toHaveCount(1);
  await expect(modalValue(page, "Cutlist Printed?")).not.toContainText("✓");
  await expect(modalValue(page, "Cutlist Printed?")).not.toContainText("—");
  const jid = page.getByTestId("modal-jid");
  await expect(jid).toContainText(item.jid_code);
  await expect(jid.locator("span[title^='JID color']")).toHaveAttribute("title", `JID color ${item.jid_color}`);
  // read-only: nothing in the modal's details takes input
  await expect(page.locator("div.fixed.inset-0 input")).toHaveCount(0);
});

test("Next shows the next item's own reference fields, not the previous item's", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  const id = await openModal(page, "JO-K-101");
  const first = await (await page.request.get(`/api/items/${id}`)).json();
  await expect(modalValue(page, "Floor Plan")).toHaveText(first.floor_plan, { timeout: 15_000 });
  await page.getByRole("button", { name: /Next ›/ }).click();
  // the other items have no Floor Plan / RLS / Joiery Details (an empty value renders as a
  // dash) and keep the column's default of "printed"
  await expect(modalValue(page, "Floor Plan")).toHaveText("—", { timeout: 15_000 });
  await expect(modalValue(page, "RLS")).toHaveText("—");
  await expect(modalValue(page, "Joiery Details")).toHaveText("—");
  await expect(modalValue(page, "Cutlist Printed?")).toHaveText("✓");
  await expect(page.getByTestId("modal-jid")).not.toContainText(first.jid_code);
});

test("the modal lists the item's register documents, read-only, with Open links", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter: could edit on the item editor
  const id = await openModal(page, "JO-K-101");
  const docs: { document_id: number; label: string | null; file_blob_id: number }[] = await (
    await page.request.get(`/api/items/${id}/documents`)
  ).json();
  expect(docs.length).toBeGreaterThan(0);

  await expect(registerRows(page)).toHaveCount(docs.length, { timeout: 15_000 });
  await expect(page.getByText("No documents attached for v1.")).toHaveCount(0);
  for (let i = 0; i < docs.length; i++) {
    if (docs[i].label) await expect(registerRows(page).nth(i)).toContainText(docs[i].label!);
    await expect(registerRows(page).nth(i).getByRole("link", { name: "Open" })).toHaveAttribute(
      "href", `/api/files/${docs[i].file_blob_id}`,
    );
  }
  // read-only: nothing to type into or press, even for a role that can write
  await expect(modalRegister(page).getByRole("textbox")).toHaveCount(0);
  await expect(modalRegister(page).getByRole("button")).toHaveCount(0);
  await expect(modalRegister(page).getByRole("link", { name: /Manage on Attachments tab/ })).toHaveAttribute(
    "href", `/items/${id}?tab=attachments`,
  );
});

test("Next shows the next item's own documents, not the previous item's", async ({ page }) => {
  await login(page, "rin.park@hartwood.test"); // manager
  await openModal(page, "JO-K-101"); // the only item of ALF-001 with register documents
  await expect(registerRows(page).first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: /Next ›/ }).click();
  await expect(modalRegister(page)).toContainText("No documents in the register.", { timeout: 15_000 });
  await expect(registerRows(page)).toHaveCount(0);
});

test("a bound SketchUp file shows its name with an Open link; an empty slot shows a dash", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test"); // drafter: may bind slots
  const id = await openModal(page, "JO-K-101");
  // The seed binds neither slot. Clear SketchUp first so an earlier run that was killed
  // before its cleanup (a timeout closes the request context) cannot fail this one.
  await page.request.delete(`/api/items/${id}/attachments/sketchup`);
  await page.getByRole("button", { name: "CLOSE", exact: true }).click();
  await openModal(page, "JO-K-101");
  await expect(slotValue(page, "SketchUp File")).toContainText("—", { timeout: 15_000 });
  await expect(slotValue(page, "CabVision File")).toContainText("—");

  // SketchUp 2021+ signature FF FE FF 0E, plus a distinct tail so the blob is new
  const skp = Buffer.concat([Buffer.from([0xff, 0xfe, 0xff, 0x0e]), Buffer.from(`e2e modal ${Date.now()}`)]);
  const up = await page.request.post("/api/files", {
    multipart: { file: { name: "e2e-modal.skp", mimeType: "application/octet-stream", buffer: skp } },
  });
  expect(up.ok(), await up.text()).toBe(true);
  const blob = (await up.json()).file_blob_id;
  try {
    expect((await page.request.post(`/api/items/${id}/attachments/sketchup`, { data: { file_blob_id: blob } })).ok()).toBe(true);
    await page.getByRole("button", { name: "CLOSE", exact: true }).click();
    await openModal(page, "JO-K-101");
    await expect(slotValue(page, "SketchUp File")).toContainText("e2e-modal.skp", { timeout: 15_000 });
    await expect(slotValue(page, "SketchUp File").getByRole("link", { name: "Open" })).toHaveAttribute(
      "href", `/api/files/${blob}`,
    );
    await expect(slotValue(page, "CabVision File")).toContainText("—"); // the other slot is untouched
  } finally {
    await page.request.delete(`/api/items/${id}/attachments/sketchup`);
  }
});

test("a failed load says so instead of showing an empty register", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.route("**/api/items/*/documents", (route) => route.fulfill({ status: 500, body: "boom" }));
  await page.route("**/api/items/*/attachments", (route) => route.fulfill({ status: 500, body: "boom" }));
  await openModal(page, "JO-K-101");
  await expect(modalRegister(page)).toContainText("Couldn't load the document register.", { timeout: 15_000 });
  await expect(modalRegister(page)).not.toContainText("No documents in the register.");
  await expect(slotValue(page, "SketchUp File")).toContainText("Couldn't load");
});

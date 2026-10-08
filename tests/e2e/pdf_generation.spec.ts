import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

async function openFirstAlfredItem(page: Page) {
  await page.goto("/projects");
  await page.getByRole("link", { name: "Alfred Street Renovation", exact: true }).click();
  await expect(page).toHaveURL(/\/tracking\?project_id=\d+/, { timeout: 30_000 });
  // First item link in the tracking grid (href like /items/123?tab=cutlist).
  const firstItem = page.locator('a[href^="/items/"]').first();
  await firstItem.waitFor({ timeout: 30_000 });
  await firstItem.click();
  await expect(page).toHaveURL(/\/items\/\d+/, { timeout: 30_000 });
}

test("pdf generation: drafter prints cutlist + hardware + combined", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await openFirstAlfredItem(page);

  // Footer print bar lives under the tab content; the "Print Cutlist" link is visible.
  await expect(page.getByRole("link", { name: "Print Cutlist" })).toBeVisible({
    timeout: 15_000,
  });

  // Resolve the item ID from the URL so we can hit the print endpoints directly.
  // Anchors carry target="_blank", which spawns a popup that often dodges
  // page.waitForResponse — drive the same routes via the BrowserContext's
  // APIRequestContext so the jf_session cookie is sent automatically.
  const itemMatch = page.url().match(/\/items\/(\d+)/);
  expect(itemMatch).not.toBeNull();
  const itemId = itemMatch![1];
  const request = page.context().request;

  // Print Cutlist — assert a 200 PDF response.
  const cutlistRes = await request.get(`/api/items/${itemId}/cutlist.pdf`, {
    timeout: 30_000,
  });
  expect(cutlistRes.status()).toBe(200);
  expect(cutlistRes.headers()["content-type"]).toContain("application/pdf");
  const cutlistBytes = (await cutlistRes.body()).length;
  expect(cutlistBytes).toBeGreaterThan(500);

  // Print Hardware
  const hardwareRes = await request.get(`/api/items/${itemId}/hardware.pdf`, {
    timeout: 30_000,
  });
  expect(hardwareRes.status()).toBe(200);
  expect(hardwareRes.headers()["content-type"]).toContain("application/pdf");

  // Print Combined PDF (slowest path; allow up to 60 s for WeasyPrint + pypdf merge).
  const combinedRes = await request.get(`/api/items/${itemId}/combined.pdf`, {
    timeout: 60_000,
  });
  expect(combinedRes.status()).toBe(200);
  expect(combinedRes.headers()["content-type"]).toContain("application/pdf");
  const combinedBytes = (await combinedRes.body()).length;
  expect(combinedBytes).toBeGreaterThan(2_000);

  // Sanity-check that the on-page link points at the same endpoint the user would hit.
  const cutlistHref = await page
    .getByRole("link", { name: "Print Cutlist" })
    .getAttribute("href");
  expect(cutlistHref).toBe(`/api/items/${itemId}/cutlist.pdf`);
});

test("attachments tab: drafter uploads a slot then sees populated card", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");

  // A project and item of its own, so the upload never changes a seeded item for later runs
  // (CLAUDE.md section 3). Names and file bytes are unique to the run: `file_blob` is deduplicated by
  // content, so identical bytes would come back under whichever file name was stored first.
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `PG-${stamp}`, name: `Attachment upload ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const item = await page.request.post(`/api/projects/${pid}/items`, {
    data: { description: `Upload target ${stamp}`, code: null, qty: 1 },
  });
  expect(item.status()).toBe(201);
  const itemId = (await item.json()).id as number;

  await page.goto(`/items/${itemId}?tab=attachments`);
  // The slot cards load after the page: wait for the one we use, then take ITS file input. The first
  // file input on the tab can be the Document Register's "Add document" input, which exists earlier.
  const cvHeading = page.getByRole("heading", { name: /CV Production Drawing/ });
  await expect(cvHeading).toBeVisible({ timeout: 30_000 });
  const card = cvHeading.locator("xpath=ancestor::div[.//input[@type='file']][1]");
  await expect(card).toContainText("Empty");

  const fileName = `e2e-upload-${stamp}.pdf`;
  await card.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: "application/pdf",
    buffer: Buffer.from(`%PDF-1.4\n%${stamp}\n` + "x".repeat(150) + "\n%%EOF\n"),
  });

  // The card flips to Populated and shows the file name; the tab's summary counts it.
  await expect(card).toContainText(fileName, { timeout: 15_000 });
  await expect(card).toContainText("Populated");
  await expect(page.getByText("1 of 3 slots populated")).toBeVisible();
  await expect(page.getByTestId("register-row")).toHaveCount(0);       // a slot upload is not a register entry
});

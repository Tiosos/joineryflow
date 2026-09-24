import { test, expect, type Page } from "@playwright/test";

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', "hartwood-dev");
  await page.click('button:has-text("Sign in")');
  await expect(page).toHaveURL(/\/(home|dashboard)$/, { timeout: 30_000 });
}

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
  await openFirstAlfredItem(page);

  // Switch to Attachments tab via the tablist.
  await page.getByRole("tab", { name: "Attachments" }).click();
  await expect(page).toHaveURL(/tab=attachments/, { timeout: 10_000 });

  // The seed pre-populates item 1 with all 3 slots; replacing the cv_drawing should still work.
  const pdfBytes = "%PDF-1.4\n%abc\n" + "x".repeat(150) + "\n%%EOF\n";
  const buf = Buffer.from(pdfBytes);

  // First slot card's hidden file input.
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles({
    name: "e2e-replace.pdf",
    mimeType: "application/pdf",
    buffer: buf,
  });

  // Wait for the card to refresh — the original_filename text should change to e2e-replace.pdf
  await expect(page.getByText("e2e-replace.pdf")).toBeVisible({ timeout: 15_000 });
});

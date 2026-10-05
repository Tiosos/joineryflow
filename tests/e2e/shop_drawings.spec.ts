import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/** A small but valid N-page PDF (correct xref), so pdf.js can really open it. */
function pdfWithPages(n: number): Buffer {
  const objs: string[] = [];
  const kids = Array.from({ length: n }, (_, i) => `${3 + i * 2} 0 R`).join(" ");
  objs.push("<< /Type /Catalog /Pages 2 0 R >>");
  objs.push(`<< /Type /Pages /Kids [${kids}] /Count ${n} >>`);
  for (let i = 0; i < n; i++) {
    // A thick outline as well as text: vector drawing is what CAD output is, and
    // it needs no fonts, so it proves the thumbnail really painted something.
    const content = `4 w 30 30 240 440 re S BT /F1 40 Tf 60 400 Td (Page ${i + 1}) Tj ET`;
    objs.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 500] /Contents ${4 + i * 2} 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>`);
    objs.push(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  }
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => { offsets.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  offsets.forEach((o) => { out += `${String(o).padStart(10, "0")} 00000 n \n`; });
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

test("shop drawings: drafter uploads + manager approves", async ({ page }) => {
  // Drafter uploads + submits.
  await login(page, "noa.lindqvist@hartwood.test");

  await page.goto("/shop-dwgs");
  await expect(page.getByRole("heading", { name: "Shop Drawings" })).toBeVisible();
  await expect(page.getByText(/across \d+ rooms/)).toBeVisible();

  await page.getByRole("button", { name: "Upload drawing" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "e2e-test.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%abc\n" + "x".repeat(200) + "\n%%EOF\n"),
  });
  await page.locator('input[placeholder^="Title"]').fill("E2E test drawing");
  await page.locator('input[placeholder^="Room"]').fill("Kitchen");
  await page.getByLabel("Submit for review immediately").check();
  await page.getByRole("button", { name: "Create drawing" }).click();

  // Drawer auto-opens with the new drawing in the In review subtab.
  await expect(page).toHaveURL(/drawing=\d+/, { timeout: 30_000 });
  await expect(page.getByText("E2E test drawing").first()).toBeVisible();

  // Switch to manager.
  await page.context().clearCookies();
  await login(page, "rin.park@hartwood.test");

  await page.goto("/shop-dwgs?subtab=in_review");
  await page.getByText("E2E test drawing").first().click();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/Approved/i).first()).toBeVisible({ timeout: 10_000 });

  // Now visible in Current.
  await page.goto("/shop-dwgs?subtab=current");
  await expect(page.getByText("E2E test drawing").first()).toBeVisible({ timeout: 10_000 });
});

test("shop drawings: reject requires note and leaves drawing without current revision", async ({ page }) => {
  // Drafter uploads + submits.
  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto("/shop-dwgs");
  await page.getByRole("button", { name: "Upload drawing" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "reject-test.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%xyz\n" + "y".repeat(150) + "\n%%EOF\n"),
  });
  await page.locator('input[placeholder^="Title"]').fill("Reject me");
  await page.locator('input[placeholder^="Room"]').fill("Bathroom");
  await page.getByLabel("Submit for review immediately").check();
  await page.getByRole("button", { name: "Create drawing" }).click();
  await expect(page).toHaveURL(/drawing=\d+/, { timeout: 30_000 });

  // Manager rejects with required note.
  await page.context().clearCookies();
  await login(page, "rin.park@hartwood.test");
  await page.goto("/shop-dwgs?subtab=in_review");
  await page.getByText("Reject me").first().click();
  // Wait for the drawer's action bar (Approve button means rev is pending + we can review).
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await page.locator('input[placeholder^="Reason"]').fill("Missing edge profile");
  await page.getByRole("button", { name: "Confirm reject" }).click();

  await expect(page.getByText(/Rejected/i).first()).toBeVisible({ timeout: 10_000 });

  // No current revision -> drawing absent from Current subtab.
  await page.goto("/shop-dwgs?subtab=current");
  await expect(page.getByText("Reject me")).toHaveCount(0);
});

// --- Register redesign (migration 0044). Read-only against the seeded ALF-001
// drawings, so safe to re-run without re-seeding. ---

test("register: columns, queue filter, overdue flag and sorting", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/shop-dwgs");

  const table = page.getByTestId("register-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  for (const h of ["Item #", "View", "Description", "Rev", "Type", "Level", "Joinery ID", "Assigned", "Status", "Due date", "Submitted"]) {
    await expect(table.getByRole("columnheader", { name: new RegExp(h, "i") })).toBeVisible();
  }

  // Seeded "Kitchen island": a draft (Being Drawn) two days past its due date.
  const island = page.getByTestId("register-row").filter({ hasText: "Kitchen island" });
  await expect(island).toContainText("ALF-001-");
  await expect(island.getByTestId("overdue")).toBeVisible();
  await expect(island.getByTestId("queue-chip")).toHaveText("Being Drawn");

  // A queue narrows the register, lands in the URL and survives a reload.
  await page.getByTestId("queue-being_drawn").click();
  await expect(page).toHaveURL(/queue=being_drawn/);
  await expect(page.getByTestId("register-row").filter({ hasText: "Kitchen island" })).toHaveCount(1);
  await expect(page.getByTestId("register-row").filter({ hasText: "Hallway storage" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("queue-being_drawn")).toHaveAttribute("aria-current", "true");

  // Sorting flips the column's aria-sort.
  await page.getByTestId("queue-all").click();
  const due = table.getByRole("columnheader", { name: /Due date/i });
  await due.getByRole("button").click();
  await expect(due).toHaveAttribute("aria-sort", "ascending");
  await due.getByRole("button").click();
  await expect(due).toHaveAttribute("aria-sort", "descending");
});

test("register: details panel, then the full-screen viewer and back", async ({ page }) => {
  await login(page, "rin.park@hartwood.test");
  await page.goto("/shop-dwgs");

  await page.getByTestId("register-row").filter({ hasText: "Hallway storage" }).click();
  const panel = page.getByTestId("details-panel");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByText("Current shop drawing details")).toBeVisible();
  await expect(panel.locator("select").first()).toHaveValue("IFC");
  for (const tab of ["Revisions", "Notes", "Attachments", "Status History", "Audit Log"]) {
    await expect(panel.getByRole("tab", { name: tab })).toBeVisible();
  }
  await panel.getByRole("tab", { name: "Status History" }).click();
  // Seeded drawings are inserted with raw SQL, so they have no audit history.
  await expect(panel.getByText("Nothing recorded yet.")).toBeVisible({ timeout: 30_000 });

  // View opens the viewer over the page; zoom steps; Back returns to the register.
  await page.getByTestId("register-row").filter({ hasText: "Hallway storage" })
    .getByTestId("view-drawing").click();
  const viewer = page.getByTestId("drawing-viewer");
  await expect(viewer).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveURL(/viewer=1/);
  await expect(viewer.getByText("Communication")).toBeVisible();
  await expect(viewer.getByTestId("zoom-level")).toHaveText("Fit");
  await viewer.getByRole("button", { name: "Zoom in" }).click();
  await expect(viewer.getByTestId("zoom-level")).toHaveText("125%");
  await viewer.getByRole("button", { name: "Fit" }).click();
  await expect(viewer.getByTestId("zoom-level")).toHaveText("Fit");
  await viewer.getByRole("button", { name: /Back/ }).click();
  await expect(viewer).toHaveCount(0);
  await expect(panel).toBeVisible();
});

test("register: a viewer sees the details read-only", async ({ page }) => {
  await login(page, "sam.ito@hartwood.test"); // viewer: shop_dwgs:read only
  await page.goto("/shop-dwgs");
  await expect(page.getByRole("button", { name: "Upload drawing" })).toHaveCount(0);
  await page.getByTestId("register-row").filter({ hasText: "Hallway storage" }).click();
  const panel = page.getByTestId("details-panel");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByText(/Only the drawing's creator or a manager can edit/)).toBeVisible();
  await expect(panel.locator("select").first()).toBeDisabled();
});

// Creates a drawing (as the upload tests above do); a re-run just adds another.
test("viewer: thumbnail strip shows every page and pages the drawing", async ({ page }) => {
  await login(page, "noa.lindqvist@hartwood.test");
  await page.goto("/shop-dwgs");
  await page.getByRole("button", { name: "Upload drawing" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "three-pages.pdf",
    mimeType: "application/pdf",
    buffer: pdfWithPages(3),
  });
  await page.locator('input[placeholder^="Title"]').fill("Thumbnail test drawing");
  await page.getByRole("button", { name: "Create drawing" }).click();
  await expect(page).toHaveURL(/drawing=\d+/, { timeout: 30_000 });

  // A re-run leaves earlier copies behind; the register sorts by number, so the
  // one just created is the last.
  await page.getByTestId("register-row").filter({ hasText: "Thumbnail test drawing" })
    .last().getByTestId("view-drawing").click();
  const strip = page.getByTestId("thumbnail-strip");
  await expect(strip).toBeVisible({ timeout: 30_000 });
  await expect(strip.getByTestId("page-count")).toHaveText("3 pages", { timeout: 30_000 });
  await expect(strip.getByTestId("thumbnail")).toHaveCount(3);
  // Painted, not blank: every thumbnail has dark (non-white) pixels from the outline.
  for (let i = 0; i < 3; i++) {
    await expect.poll(() => strip.locator("canvas").nth(i).evaluate((c: HTMLCanvasElement) => {
      const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
      for (let p = 0; p < d.length; p += 4) if (d[p]! < 100 && d[p + 3]! > 200) return true;
      return false;
    }), { timeout: 30_000 }).toBe(true);
  }

  await expect(strip.getByRole("button", { name: "Go to page 1" })).toHaveAttribute("aria-current", "page");
  await strip.getByRole("button", { name: "Go to page 3" }).click();
  await expect(strip.getByRole("button", { name: "Go to page 3" })).toHaveAttribute("aria-current", "page");
  await expect(page.locator('[data-testid="drawing-viewer"] iframe')).toHaveAttribute("src", /#page=3&/);
});

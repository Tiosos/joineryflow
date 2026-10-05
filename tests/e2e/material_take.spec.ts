import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * Sub-project #12 (D3) — Material Take → Material Summary.
 *
 * The test builds its own fixtures through the API, so it passes on a second run against
 * the same database (a run approves a take and rebuilds the summary, which is exactly the
 * state the seed's draft item and stale line are in). It creates a project of its own (items
 * added to ALF-001 would become the "first item" other specs open, and have no comments or
 * hardware), and in it
 *   - item A: an approved take, a summary built from it, then a v2 approved — a stale line;
 *   - item B: parts and a draft take — it shows under "without an approved take".
 * and then adjusts and approves B's take in the UI and rebuilds the summary.
 */
test("a drafted take can be adjusted and approved, then summarised", async ({ page }) => {
  await login(page);

  const api = async (method: "get" | "post", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.status() === 204 ? null : r.json();
  };
  const boardId = (await api("get", "/catalog/board-materials")).rows[0].material_id as number;
  const stamp = Date.now();
  const project = await api("post", "/projects", { project_code: `TK-${stamp}`, name: `Take fixtures ${stamp}` });
  const pid = project.id as number;
  const itemWithParts = async (description: string) => {
    const item = await api("post", `/projects/${pid}/items`, { description });
    const mod = await api("post", `/items/${item.id}/modules`, { module_no: "1" });
    await api("post", `/modules/${mod.id}/parts`, { qty: 2, len_mm: 720, wid_mm: 560, board_material_id: boardId });
    return item.id as number;
  };
  const takeFor = async (itemId: number) => (await api("post", `/items/${itemId}/material-take/generate`)).take_id as number;

  const itemA = await itemWithParts(`Take fixture A ${stamp}`);
  await api("post", `/material-takes/${await takeFor(itemA)}/approve`);
  await api("post", `/projects/${pid}/material-summary`);
  await api("post", `/material-takes/${await takeFor(itemA)}/approve`);   // v2: the summary line is now stale
  const itemB = await itemWithParts(`Take fixture B ${stamp}`);
  await takeFor(itemB);

  await page.goto(`/projects/${pid}/procurement?tab=summary`);
  await expect(page.getByRole("heading", { name: "Material Summary" })).toBeVisible();
  await expect(page.getByText(/may be outdated/)).toBeVisible();
  await page.getByText(/without an approved take/).click();
  const draftLink = page.locator(`details a[href^="/items/${itemB}"]`);
  const draftHref = await draftLink.getAttribute("href");
  await draftLink.click();
  await expect(page).toHaveURL(/\/items\/\d+\?tab=take/);

  // Draft v1: bump a wastage %, add a manual edging line, approve.
  const edging = `Edge tape white 22mm ${stamp}`;
  const wastage = page.getByRole("textbox", { name: /^Wastage for / }).first();
  await wastage.fill("10");
  await wastage.blur();
  await page.getByRole("textbox", { name: "New line description" }).fill(edging);
  await page.getByRole("textbox", { name: "New line qty" }).fill("12");
  await page.getByRole("button", { name: "Add line" }).click();
  await expect(page.getByText(edging)).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText(/Take v1 · approved/)).toBeVisible();

  // Rebuild: that item leaves the missing list (items with no parts stay on
  // it — they have no take either) and its edging line appears.
  await page.goto(`/projects/${pid}/procurement?tab=summary`);
  await page.getByRole("button", { name: "Rebuild from approved takes" }).click();
  await expect(page.getByRole("button", { name: new RegExp(edging) })).toBeVisible();
  await page.getByText(/without an approved take/).click();
  await expect(page.locator(`details a[href="${draftHref}"]`)).toHaveCount(0);
  await expect(page.getByText(/may be outdated/)).toHaveCount(0);
});

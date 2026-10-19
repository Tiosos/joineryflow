import { test, expect, type Browser, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * A save held under someone else's Controlled Lock (B7 / Q509) is decided by the lock owner, a
 * manager or an admin: the item editor shows what was proposed with Approve / Reject, and the
 * notification bell lists it until it is decided. Everyone else sees neither.
 *
 * Runs in a project of its own with its own item (CLAUDE.md §3: nothing seeded changes) and soft-
 * deletes it afterwards. Users: Noa (drafter) owns the lock, Theo (manager) asks, Rin (manager)
 * decides, Sam (viewer) looks. Bell entries are found by the link to this spec's own item: the
 * seeded request on TRT-014 is in every decider's bell too.
 */
const OWNER = "noa.lindqvist@hartwood.test";
const ASKER = "theo.blake@hartwood.test";
const MANAGER = "rin.park@hartwood.test";
const VIEWER = "sam.ito@hartwood.test";

async function as(browser: Browser, email: string): Promise<Page> {
  const baseURL = test.info().project.use.baseURL;
  const ctx = await browser.newContext({ baseURL });
  const page = await ctx.newPage();
  await login(page, email);
  return page;
}

/** An item in a project of its own, locked by the owner, with a held save from the asker. */
async function heldSave(browser: Browser, label: string) {
  const stamp = Date.now();
  const rin = await as(browser, MANAGER);
  const made = await rin.request.post("/api/projects", {
    data: { project_code: `LR-${stamp}`, name: `Lock request ${label} ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const original = `Original ${stamp}`;
  const created = await rin.request.post(`/api/projects/${pid}/items`, {
    data: { description: original, code: null, qty: 1 },
  });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id as number;

  const noa = await as(browser, OWNER);
  // The first save claims the Controlled Lock for Noa.
  expect((await noa.request.patch(`/api/items/${id}`, { data: { description: original } })).ok()).toBe(true);
  expect((await noa.request.patch(`/api/items/${id}`, { data: { qty: 2 } })).ok()).toBe(true);

  const theo = await as(browser, ASKER);
  const proposed = `Proposed ${stamp}`;
  const held = await theo.request.patch(`/api/items/${id}`, { data: { description: proposed } });
  expect(held.status()).toBe(409);
  const detail = (await held.json()).detail;
  expect(detail.code).toBe("LOCK_REQUEST_CREATED");
  return { id, rid: detail.request_id as number, original, proposed, rin, noa, theo };
}

/** The bell entry for one item (its link), not any entry that happens to mention a field. */
const bellEntry = (page: Page, itemId: number) =>
  page.locator(`[data-testid="lock-request-waiting"][href="/items/${itemId}"]`);

const description = async (page: Page, id: number) =>
  (await (await page.request.get(`/api/items/${id}`)).json()).description as string;

test("the lock owner sees the held save in the bell and the editor, and approving applies it", async ({ browser }) => {
  const h = await heldSave(browser, "approve");
  try {
    const { noa } = h;
    // Bell: counted on the badge and listed, linking to the item.
    await noa.goto("/dashboard");
    await expect(noa.getByTestId("notification-count")).toBeVisible({ timeout: 30_000 });
    await noa.getByTestId("notification-bell").click();
    await expect(bellEntry(noa, h.id)).toBeVisible();
    await expect(bellEntry(noa, h.id)).toContainText("description");
    await bellEntry(noa, h.id).click();
    await expect(noa).toHaveURL(new RegExp(`/items/${h.id}`));

    // Editor banner: who proposed what, then Approve with a note.
    const banner = noa.getByTestId("lock-requests-banner");
    await expect(banner).toBeVisible({ timeout: 30_000 });
    await expect(banner).toContainText("Theo Blake");
    await expect(banner).toContainText(h.proposed);
    await noa.getByTestId(`lock-request-note-${h.rid}`).fill("fine by me");
    await noa.getByTestId(`lock-request-approve-${h.rid}`).click();
    await expect(noa.getByTestId("lock-requests-banner")).toHaveCount(0, { timeout: 30_000 });

    expect(await description(noa, h.id)).toBe(h.proposed);
    const rows = await (await noa.request.get(`/api/items/${h.id}/lock-requests`)).json();
    expect(rows[0]).toMatchObject({ status: "approved", decision_note: "fine by me" });

    // Decided: gone from the bell too.
    await noa.goto("/dashboard");
    await noa.getByTestId("notification-bell").click();
    await expect(bellEntry(noa, h.id)).toHaveCount(0);
  } finally {
    await h.rin.request.delete(`/api/items/${h.id}`);
  }
});

test("a manager rejects a held save, which leaves the item untouched", async ({ browser }) => {
  const h = await heldSave(browser, "reject");
  try {
    await h.rin.goto(`/items/${h.id}`);
    await expect(h.rin.getByTestId("lock-requests-banner")).toBeVisible({ timeout: 30_000 });
    await h.rin.getByTestId(`lock-request-reject-${h.rid}`).click();
    await expect(h.rin.getByTestId("lock-requests-banner")).toHaveCount(0, { timeout: 30_000 });
    expect(await description(h.rin, h.id)).toBe(h.original);
    const rows = await (await h.rin.request.get(`/api/items/${h.id}/lock-requests`)).json();
    expect(rows[0].status).toBe("rejected");
  } finally {
    await h.rin.request.delete(`/api/items/${h.id}`);
  }
});

test("a viewer sees neither a banner nor a bell entry; a manager who asked still may decide it", async ({ browser }) => {
  const h = await heldSave(browser, "others");
  try {
    const viewer = await as(browser, VIEWER);
    await viewer.goto(`/items/${h.id}`);
    await expect(viewer.getByRole("heading", { name: /ITEM #/ })).toBeVisible({ timeout: 30_000 });
    await expect(viewer.getByTestId("lock-requests-banner")).toHaveCount(0);
    await viewer.getByTestId("notification-bell").click();
    await expect(viewer.getByTestId("lock-requests-waiting")).toHaveCount(0);

    // A manager may decide any held save, including one they proposed (as the API already allows).
    await h.theo.goto(`/items/${h.id}`);
    await expect(h.theo.getByTestId("lock-requests-banner")).toBeVisible({ timeout: 30_000 });
  } finally {
    await h.rin.request.delete(`/api/items/${h.id}`);
  }
});

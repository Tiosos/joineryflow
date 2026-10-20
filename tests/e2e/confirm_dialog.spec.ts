import { test, expect, type Page } from "@playwright/test";
import { login } from "./helpers";

/**
 * The shared confirm dialog (components/confirm/ConfirmProvider) replaces window.confirm / prompt
 * for the risky actions. Cancel, Esc and a click outside all leave things as they were; Confirm
 * does the action; a reason dialog keeps Confirm off until the reason is typed (or accepts none
 * when the reason is optional). Own project, item and estimates (CLAUDE.md §3).
 */

const dialog = (page: Page) => page.getByTestId("confirm-dialog");
const confirmBtn = (page: Page) => page.getByTestId("confirm-dialog-confirm");

test("deleting an item asks first: Cancel, Esc and a click outside change nothing; Confirm deletes", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  const made = await page.request.post("/api/projects", {
    data: { project_code: `CD-${stamp}`, name: `Confirm dialog ${stamp}` },
  });
  expect(made.status()).toBe(201);
  const pid = (await made.json()).id as number;
  const created = await page.request.post(`/api/projects/${pid}/items`, {
    data: { description: `Confirm ${stamp}`, code: null, qty: 1 },
  });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id as number;

  await page.goto(`/items/${id}`);
  await expect(page.getByTestId("delete-item")).toBeVisible({ timeout: 30_000 });

  // It opens as a labelled alert dialog with Cancel focused (the safe default), names what goes.
  await page.getByTestId("delete-item").click();
  await expect(dialog(page)).toBeVisible();
  await expect(page.getByRole("alertdialog", { name: /Delete item #/ })).toBeVisible();
  await expect(page.getByTestId("confirm-dialog-message")).toContainText("related parts and cutlist");
  await expect(page.getByTestId("confirm-dialog-cancel")).toBeFocused();

  await page.getByTestId("confirm-dialog-cancel").click();
  await expect(dialog(page)).toHaveCount(0);
  expect((await page.request.get(`/api/items/${id}`)).status()).toBe(200);

  await page.getByTestId("delete-item").click();
  await expect(dialog(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog(page)).toHaveCount(0);
  expect((await page.request.get(`/api/items/${id}`)).status()).toBe(200);

  await page.getByTestId("delete-item").click();
  await expect(dialog(page)).toBeVisible();
  await page.mouse.click(5, 5); // the backdrop
  await expect(dialog(page)).toHaveCount(0);
  expect((await page.request.get(`/api/items/${id}`)).status()).toBe(200);

  await page.getByTestId("delete-item").click();
  await confirmBtn(page).click();
  await expect(page).toHaveURL(new RegExp(`/tracking\\?project_id=${pid}`), { timeout: 30_000 });
  expect((await page.request.get(`/api/items/${id}`)).status()).toBe(404);
});

/** An estimate taken to SUBMITTED through the API, so Reject / Expire are on the page. */
async function submittedEstimate(page: Page, label: string) {
  const call = async (method: "post" | "get", path: string, data?: object) => {
    const r = await page.request[method](`/api${path}`, data ? { data } : undefined);
    expect(r.status(), `${method} ${path}`).toBeLessThan(300);
    return r.json();
  };
  const customer = await call("post", "/customers", { name: `Confirm customer ${Date.now()}` });
  const estimate = await call("post", "/estimates", { customer_id: customer.customer_id, title: `Confirm ${label} ${Date.now()}` });
  const rid = estimate.current_revision_id as number;
  await call("post", `/revisions/${rid}/lines`, { description: "Line", qty: 1 });
  for (let i = 0; i < 14; i++) {
    const rev = await call("get", `/estimates/${estimate.estimate_id}/revisions/${rid}`);
    if (rev.status === "SUBMITTED") break;
    await call("post", `/revisions/${rid}/advance`);
  }
  return { eid: estimate.estimate_id as number, rid, call };
}

test("Reject asks for a reason, which stays on the quote; Expire takes one or none", async ({ page }) => {
  await login(page, "kai.ngata@hartwood.test"); // estimator

  const a = await submittedEstimate(page, "reject");
  await page.goto(`/estimating/${a.eid}`);
  await page.getByTestId("estimate-reject").click();
  await expect(page.getByRole("alertdialog", { name: "Reject this quote?" })).toBeVisible();
  await expect(confirmBtn(page)).toBeDisabled();               // a reason is required
  await page.getByTestId("confirm-dialog-reason").fill("   ");
  await expect(confirmBtn(page)).toBeDisabled();               // spaces are not a reason
  await page.getByTestId("confirm-dialog-reason").fill("Priced out by a competitor");
  await confirmBtn(page).click();
  await expect(dialog(page)).toHaveCount(0);
  await expect.poll(async () => (await a.call("get", `/estimates/${a.eid}/revisions/${a.rid}`)).status, { timeout: 30_000 })
    .not.toBe("SUBMITTED");
  const rejected = await a.call("get", `/estimates/${a.eid}/revisions/${a.rid}`);
  expect(JSON.stringify(rejected)).toContain("Priced out by a competitor");

  const b = await submittedEstimate(page, "expire");
  await page.goto(`/estimating/${b.eid}`);
  await page.getByTestId("expire-btn").click();
  await expect(page.getByRole("alertdialog", { name: "Expire this quote?" })).toBeVisible();
  await expect(confirmBtn(page)).toBeEnabled();                // the reason is optional here
  await confirmBtn(page).click();
  await expect.poll(async () => (await b.call("get", `/estimates/${b.eid}/revisions/${b.rid}`)).status, { timeout: 30_000 })
    .not.toBe("SUBMITTED");

  // Cancel leaves a submitted quote as it was.
  const c = await submittedEstimate(page, "cancel");
  await page.goto(`/estimating/${c.eid}`);
  await page.getByTestId("estimate-reject").click();
  await page.getByTestId("confirm-dialog-cancel").click();
  await expect(dialog(page)).toHaveCount(0);
  expect((await c.call("get", `/estimates/${c.eid}/revisions/${c.rid}`)).status).toBe("SUBMITTED");
});

/**
 * Prompts asked from code, not by a click: a click cannot get a second prompt in while one is open (the
 * backdrop is in the way), so these two cases reach the provider's own API through React's fiber tree.
 */
const FIND_API = `() => {   // plain JS: it runs in the page
  const el = document.querySelector("main") ?? document.body;
  const key = Object.keys(el).find((k) => k.startsWith("__reactFiber$"));
  let f = el[key];
  while (f && !(f.memoizedProps && f.memoizedProps.value && typeof f.memoizedProps.value.askReason === "function")) f = f.return;
  if (!f) throw new Error("no ConfirmProvider above <main>");
  return f.memoizedProps.value;
}`;

test("asking a second prompt in the same tick cancels the first instead of leaving it hanging", async ({ page }) => {
  await login(page);
  const first = await page.evaluate(async (src) => {
    const api = (0, eval)(`(${src})`)();
    const a = api.confirm({ title: "First question" });
    api.confirm({ title: "Second question" });                 // same tick: must settle the first (false)
    return Promise.race([a, new Promise((r) => setTimeout(() => r("hung"), 2000))]);
  }, FIND_API);
  expect(first).toBe(false);
  await expect(page.getByRole("alertdialog", { name: "Second question" })).toBeVisible();
  await page.getByTestId("confirm-dialog-cancel").click();
  await expect(dialog(page)).toHaveCount(0);
});

test("a prompt that replaces another with the same title starts empty", async ({ page }) => {
  await login(page);
  await page.evaluate((src) => {
    const api = (0, eval)(`(${src})`)();
    (window as any).__first = api.askReason({ title: "Why?" });
  }, FIND_API);
  const box = page.getByRole("alertdialog", { name: "Why?" }).locator("textarea");
  await box.fill("a reason typed into the first prompt");
  await page.evaluate((src) => {
    const api = (0, eval)(`(${src})`)();
    (window as any).__second = api.askReason({ title: "Why?" });   // replaces the first
  }, FIND_API);
  expect(await page.evaluate(() => (window as any).__first)).toBeNull();     // the first was cancelled
  await expect(box).toHaveValue("");                                         // and nothing carried over
  await page.getByTestId("confirm-dialog-cancel").click();
  expect(await page.evaluate(() => (window as any).__second)).toBeNull();
});

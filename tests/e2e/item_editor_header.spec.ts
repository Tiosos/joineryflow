import { test, expect } from "@playwright/test";
import { login } from "./helpers";

/**
 * The item editor's header (Delete, close) must stay on screen. A wide Cutlist or Material Take
 * table used to stretch the page past the window and push both buttons off the right edge; the
 * tables now scroll inside their own box. Reads a seeded item and changes nothing.
 */
test.use({ viewport: { width: 1280, height: 800 } });

for (const tab of ["cutlist", "material-take"]) {
  test(`the header stays on screen on the ${tab} tab`, async ({ page }) => {
    await login(page);
    const items = (await (await page.request.get("/api/projects/1/items")).json()).items as { id: number; code: string }[];
    const id = items.find((i) => i.code === "K-101")!.id;
    await page.goto(`/items/${id}?tab=${tab}`);
    await expect(page.getByTestId("delete-item")).toBeVisible();

    const m = await page.evaluate(() => {
      const de = document.documentElement;
      const right = (testId: string) => document.querySelector(`[data-testid="${testId}"]`)!.getBoundingClientRect().right;
      return { over: de.scrollWidth - de.clientWidth, del: right("delete-item"), close: right("close-editor"), vw: innerWidth };
    });
    expect(m.over).toBeLessThanOrEqual(0);                    // the page does not scroll sideways
    expect(m.del).toBeLessThanOrEqual(m.vw);                  // Delete is on screen
    expect(m.close).toBeLessThanOrEqual(m.vw);                // and so is the close button
  });
}

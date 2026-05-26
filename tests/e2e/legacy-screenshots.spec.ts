// Visual baselines for the refined legacy mocks (sub-projects #1-#3 in the
// 2026-05-10 alignment pass). Screenshots write to
// apps/web/screenshots/legacy/<viewport>/<file>.png so they sit alongside
// the existing screenshot-login.spec.ts artifacts.
//
// Run with `make legacy-screenshots` (no live web server needed — uses file://).
//
// Adding a new mock?  Append it to MOCKS below.  Adding a new viewport?
// Append to VIEWPORTS.  No other changes needed.

import { test, expect } from "@playwright/test";
import path from "node:path";

const LEGACY_DIR = path.resolve(__dirname, "../../legacy").replace(/\\/g, "/");
const fileUrl = (name: string) => `file://${LEGACY_DIR}/${name}`;

const MOCKS: { file: string; assertText: string }[] = [
  { file: "_index.html",                           assertText: "Legacy Reference Mocks" },
  { file: "login.html",                            assertText: "Welcome back" },
  { file: "home.html",                             assertText: "Your surfaces" },
  { file: "tracking_dashboard.html",               assertText: "Synced · schema 0020" },
  { file: "drafter_item_editor.html",              assertText: "Item Details" },
  { file: "procurement_orderbook_dashboard.html",  assertText: "Pre-Procurement-Workbench-v1" },
];

const VIEWPORTS: { name: string; width: number; height: number }[] = [
  { name: "mobile",  width: 375,  height: 812 },
  { name: "tablet",  width: 768,  height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
];

test.describe("Legacy mock visual baselines", () => {
  for (const vp of VIEWPORTS) {
    test.describe(`@${vp.name} (${vp.width}x${vp.height})`, () => {
      test.use({ viewport: { width: vp.width, height: vp.height } });

      for (const mock of MOCKS) {
        test(`${mock.file}`, async ({ page }) => {
          await page.goto(fileUrl(mock.file), { waitUntil: "networkidle" });
          // Soft assertion: don't block screenshot if the marker text drifts —
          // the visual baseline is the primary signal.
          await expect
            .soft(page.getByText(mock.assertText).first())
            .toBeVisible({ timeout: 5_000 });
          await page.screenshot({
            path: `screenshots/legacy/${vp.name}/${mock.file.replace(/\.html$/, "")}.png`,
            fullPage: true,
          });
        });
      }
    });
  }
});

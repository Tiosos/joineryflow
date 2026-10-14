import { expect, test } from "@playwright/test";
import { login } from "./helpers";

// The Next proxy gzips the API's JSON for a client that accepts it (the API itself
// sends it plain), and leaves it alone for one that does not.
test("the proxy compresses a large JSON list and respects Accept-Encoding", async ({ page }) => {
  await login(page);

  const gz = await page.request.get("/api/projects", {
    headers: { "accept-encoding": "gzip" },
  });
  expect(gz.ok()).toBeTruthy();
  expect(gz.headers()["content-encoding"]).toBe("gzip");
  expect(gz.headers()["vary"]).toMatch(/accept-encoding/i);
  const rows = await gz.json();
  expect(Array.isArray(rows) ? rows.length : Object.keys(rows).length).toBeGreaterThan(0);

  const plain = await page.request.get("/api/projects", {
    headers: { "accept-encoding": "identity" },
  });
  expect(plain.ok()).toBeTruthy();
  expect(plain.headers()["content-encoding"]).toBeUndefined();
  expect(await plain.json()).toEqual(rows);
});

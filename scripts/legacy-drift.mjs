#!/usr/bin/env node
// Drift-check: compare legacy/*.html against the live source-of-truth in apps/.
// Run via `make check-legacy` (or `node scripts/legacy-drift.mjs`).
//
// Exit code: 0 if all checks pass or only WARN; 1 if any FAIL.
//
// Checks:
//   1. Canonical 6-tab order matches apps/web/components/chrome/TabStrip.tsx.
//   2. Secondary nav (Catalog / Cut Floor / Shop Floor) matches SideBar.tsx links.
//   3. AUTH_ROLE map values are subset of {admin, manager, editor, purchase_officer, viewer}.
//   4. H token usage (--h-*) does not reference tokens absent from globals.css.

import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(resolve(ROOT, p), "utf8");

const LEGACY_FILES = [
  "legacy/home.html",
  "legacy/tracking_dashboard.html",
  "legacy/drafter_item_editor.html",
  "legacy/procurement_orderbook_dashboard.html",
];

const VALID_AUTH_ROLES = new Set([
  "admin",
  "manager",
  "editor",
  "purchase_officer",
  "viewer",
]);

// ──────────────────────────────────────────────────────────────────────────
// Source-of-truth extraction
// ──────────────────────────────────────────────────────────────────────────

function liveTabs() {
  const src = read("apps/web/components/chrome/TabStrip.tsx");
  // Match `{ href: "/foo", label: "Bar" }` entries inside the TABS const.
  const out = [];
  const re = /label:\s*"([^"]+)"/g;
  let m;
  while ((m = re.exec(src)) !== null) out.push(m[1]);
  return out;
}

function liveSecondaryLinks() {
  const src = read("apps/web/components/chrome/SideBar.tsx");
  // Match the visible label text inside <Link> children at the top of SideBar.
  const out = [];
  const re = />\s*([A-Z][A-Za-z ]+?)\s*<\/Link>/g;
  let m;
  while ((m = re.exec(src)) !== null) out.push(m[1].trim());
  return out;
}

function liveTokens() {
  const src = read("apps/web/app/globals.css");
  const out = new Set();
  const re = /--h-[a-z0-9-]+/g;
  let m;
  while ((m = re.exec(src)) !== null) out.add(m[0]);
  return out;
}

// ──────────────────────────────────────────────────────────────────────────
// Per-file checks
// ──────────────────────────────────────────────────────────────────────────

// Extract tab labels in document order. Each tab is `<div class="h-tab[ active]">LABEL</div>`
// (sometimes with onclick / title attrs in between). The refined convention is:
//   first 6 labels = primary 6-tab IA · next 3 labels = secondary nav (Catalog/Cut Floor/Shop Floor).
function extractTabLabels(html) {
  const re = /class="h-tab(?:\s+active)?"[^>]*>([^<]+?)<\/div>/g;
  const out = [];
  let m;
  while ((m = re.exec(html)) !== null) out.push(m[1].trim());
  return out;
}

function usesChromePartial(html) {
  return /<script\s+src=['"]_chrome\.js['"]/.test(html);
}

function checkTabOrder(html, canonical) {
  if (usesChromePartial(html)) {
    return { level: "PASS", note: "delegated to _chrome.js" };
  }
  const all = extractTabLabels(html);
  if (all.length === 0) return { level: "FAIL", note: "no .h-tab elements found" };
  const primary = all.slice(0, canonical.length);
  const got = primary.join(" · ");
  const want = canonical.join(" · ");
  if (got === want) return { level: "PASS", note: got };
  return { level: "FAIL", note: `got "${got}" want "${want}"` };
}

function checkSecondaryNav(html, canonical) {
  if (usesChromePartial(html)) {
    return { level: "PASS", note: "delegated to _chrome.js" };
  }
  const all = extractTabLabels(html);
  // Primary nav consumes 6 labels; secondary should be the next 3.
  const secondary = all.slice(6, 6 + canonical.length);
  if (secondary.length < canonical.length) {
    return { level: "WARN", note: "no secondary .h-tabs rail" };
  }
  const got = secondary.join(" · ");
  const want = canonical.join(" · ");
  if (got === want) return { level: "PASS", note: got };
  return { level: "FAIL", note: `got "${got}" want "${want}"` };
}

// Validate the shared partial. Runs ONCE, not per HTML file.
function checkChromePartial(canonicalTabs, canonicalSecondary) {
  const path = resolve(ROOT, "legacy/_chrome.js");
  if (!existsSync(path)) {
    return [
      ["partial      ", { level: "WARN", note: "legacy/_chrome.js absent (legacy mode)" }],
    ];
  }
  const src = read("legacy/_chrome.js");
  const checks = [];

  // TABS array — match `label: "..."` lines after `const TABS = [`.
  const tabsM = src.match(/const TABS\s*=\s*\[([\s\S]*?)\];/);
  if (!tabsM) {
    checks.push(["partial tabs ", { level: "FAIL", note: "TABS const not found" }]);
  } else {
    const labels = [...tabsM[1].matchAll(/label:\s*"([^"]+)"/g)].map((x) => x[1]);
    const got = labels.join(" · ");
    const want = canonicalTabs.join(" · ");
    checks.push([
      "partial tabs ",
      got === want
        ? { level: "PASS", note: got }
        : { level: "FAIL", note: `got "${got}" want "${want}"` },
    ]);
  }

  // SECONDARY array — same pattern.
  const secM = src.match(/const SECONDARY\s*=\s*\[([\s\S]*?)\];/);
  if (!secM) {
    checks.push(["partial 2nd  ", { level: "FAIL", note: "SECONDARY const not found" }]);
  } else {
    const labels = [...secM[1].matchAll(/label:\s*"([^"]+)"/g)].map((x) => x[1]);
    const got = labels.join(" · ");
    const want = canonicalSecondary.join(" · ");
    checks.push([
      "partial 2nd  ",
      got === want
        ? { level: "PASS", note: got }
        : { level: "FAIL", note: `got "${got}" want "${want}"` },
    ]);
  }

  // H_AUTH_ROLE values must be subset of valid 5.
  const roleM = src.match(/H_AUTH_ROLE\s*=\s*\{([\s\S]*?)\}/);
  if (!roleM) {
    checks.push(["partial role ", { level: "FAIL", note: "H_AUTH_ROLE not found" }]);
  } else {
    const values = [...roleM[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
    const bad = values.filter((v) => !VALID_AUTH_ROLES.has(v));
    checks.push([
      "partial role ",
      bad.length === 0
        ? { level: "PASS", note: `${values.length} mappings, all valid auth_roles` }
        : { level: "FAIL", note: `unknown values: ${bad.join(", ")}` },
    ]);
  }

  return checks;
}

function checkAuthRoleMap(html) {
  // Look for AUTH_ROLE = { ... } or H_AUTH_ROLE = { ... }
  const m = html.match(/H?_?AUTH_ROLE\s*=\s*\{([^}]+)\}/);
  if (!m) return { level: "WARN", note: "no AUTH_ROLE map (ok for non-home pages)" };
  const values = [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
  const bad = values.filter((v) => !VALID_AUTH_ROLES.has(v));
  if (bad.length === 0)
    return { level: "PASS", note: `all values in {${[...VALID_AUTH_ROLES].join(",")}}` };
  return { level: "FAIL", note: `unknown values: ${bad.join(", ")}` };
}

function checkTokens(html, validTokens) {
  const used = new Set();
  const re = /--h-[a-z0-9-]+/g;
  let m;
  while ((m = re.exec(html)) !== null) used.add(m[0]);
  // Tokens defined locally in the legacy file (it has its own :root) are also fine.
  const localDefs = new Set();
  const defRe = /(--h-[a-z0-9-]+)\s*:/g;
  while ((m = defRe.exec(html)) !== null) localDefs.add(m[1]);

  const orphans = [...used].filter(
    (t) => !validTokens.has(t) && !localDefs.has(t)
  );
  if (orphans.length === 0)
    return { level: "PASS", note: `${used.size} tokens, all resolved` };
  return {
    level: "WARN",
    note: `tokens not in globals.css: ${orphans.slice(0, 5).join(", ")}${orphans.length > 5 ? "…" : ""}`,
  };
}

// ──────────────────────────────────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────────────────────────────────

const tabs = liveTabs();
const secondary = liveSecondaryLinks();
const tokens = liveTokens();

console.log(`\nDrift check — ${new Date().toISOString().slice(0, 10)}\n`);
console.log(`Canonical tabs    : ${tabs.join(" · ")}`);
console.log(`Canonical sidebar : ${secondary.join(" · ")}`);
console.log(`Canonical tokens  : ${tokens.size} declared in globals.css\n`);

const ICON = { PASS: "OK ", WARN: "!! ", FAIL: "XX " };
let failures = 0;
let warnings = 0;

// Shared partial — single source of truth for tabs/secondary/role mapping.
console.log("legacy/_chrome.js");
for (const [name, r] of checkChromePartial(tabs, secondary)) {
  console.log(`  ${ICON[r.level]} ${name} ${r.note}`);
  if (r.level === "FAIL") failures++;
  if (r.level === "WARN") warnings++;
}
console.log();

for (const file of LEGACY_FILES) {
  const path = resolve(ROOT, file);
  if (!existsSync(path)) {
    console.log(`${ICON.FAIL} ${file} — file not found`);
    failures++;
    continue;
  }
  const html = read(file);
  const checks = [
    ["tab order   ", checkTabOrder(html, tabs)],
    ["secondary   ", checkSecondaryNav(html, secondary)],
    ["auth_role   ", checkAuthRoleMap(html)],
    ["tokens      ", checkTokens(html, tokens)],
  ];
  console.log(file);
  for (const [name, r] of checks) {
    console.log(`  ${ICON[r.level]} ${name} ${r.note}`);
    if (r.level === "FAIL") failures++;
    if (r.level === "WARN") warnings++;
  }
  console.log();
}

const summary = `Summary: ${failures} fail, ${warnings} warn`;
console.log(summary);
if (failures > 0) {
  console.log("\nFAIL — fix the items above before merging.\n");
  process.exit(1);
}
console.log("\nOK — legacy mocks are in sync with apps/.\n");
process.exit(0);

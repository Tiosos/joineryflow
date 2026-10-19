#!/usr/bin/env node
// Every <button> in apps/web declares its `type`. A button without one submits the
// form it sits in, so adding a <form> around old markup silently turns a Cancel or
// Close into a submit. Run in CI (Web typecheck job) or `node scripts/check-button-types.mjs`.
//
// Exit code: 0 when every <button> has a type attribute, 1 listing file:line otherwise.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve, dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const WEB = join(ROOT, "apps/web");
const SKIP = new Set(["node_modules", ".next", ".turbo"]);

function* tsxFiles(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* tsxFiles(p);
    else if (name.endsWith(".tsx")) yield p;
  }
}

/** Index just past the `>` that closes the opening tag starting at `i`, skipping `{…}` and quotes. */
function endOfTag(src, i) {
  let depth = 0;
  let quote = null;
  for (; i < src.length; i++) {
    const c = src[i];
    if (quote) {
      if (c === quote && src[i - 1] !== "\\") quote = null;
    } else if (depth > 0 && (c === '"' || c === "'" || c === "`")) quote = c;
    else if (c === "{") depth++;
    else if (c === "}") depth--;
    else if (c === ">" && depth === 0) return i + 1;
  }
  return -1;
}

const missing = [];
for (const file of tsxFiles(WEB)) {
  const src = readFileSync(file, "utf8");
  for (const m of src.matchAll(/<button\b/g)) {
    const end = endOfTag(src, m.index + m[0].length);
    if (end < 0) continue;
    const tag = src.slice(m.index, end);
    // `type` as a whole attribute name, not inside a {…} expression or another word.
    const attrs = tag.replace(/\{(?:[^{}]|\{[^{}]*\})*\}/g, "{}");
    if (!/\stype\s*=/.test(attrs)) {
      const line = src.slice(0, m.index).split("\n").length;
      missing.push(`${relative(ROOT, file)}:${line}`);
    }
  }
}

if (missing.length) {
  console.error(`${missing.length} <button> without a type attribute (use type="button", or type="submit" to submit a form):`);
  for (const m of missing) console.error(`  ${m}`);
  process.exit(1);
}
console.log("check-button-types: every <button> declares a type");

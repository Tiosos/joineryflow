import type { Mentionable } from "@/lib/comments-types";

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// A name only counts as mentioned when nothing word-like follows it, so
// "@Sam" is not read out of "@Samantha".
const NOT_WORD_AFTER = "(?![\\p{L}\\p{N}])";

/** Ids of the members whose `@Full Name` still appears in `text`. The body's
 *  `@Name` is what the user sees; this is what the API is told. Derived at
 *  submit time, so deleting an inserted mention un-mentions it. */
export function mentionedIds(text: string, members: Mentionable[]): number[] {
  return members
    .filter((m) => new RegExp(`@${escapeRe(m.full_name)}${NOT_WORD_AFTER}`, "u").test(text))
    .map((m) => m.id);
}

/** Split a stored body into plain / mention runs, longest name first so
 *  "@Ann Lee" wins over "@Ann". Only names the API confirmed as mentions are
 *  highlighted — a typed "@Someone" that was never notified stays plain. */
export function splitByMentions(
  body: string,
  names: string[],
): { text: string; mention: boolean }[] {
  const clean = names.filter(Boolean).sort((a, b) => b.length - a.length);
  if (clean.length === 0) return [{ text: body, mention: false }];
  const re = new RegExp(`(@(?:${clean.map(escapeRe).join("|")})${NOT_WORD_AFTER})`, "gu");
  return body
    .split(re)
    .filter((p) => p !== "")
    .map((p) => ({ text: p, mention: p.startsWith("@") && clean.some((n) => p === `@${n}`) }));
}

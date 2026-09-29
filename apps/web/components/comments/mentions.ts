import type { Mentionable } from "@/lib/comments-types";

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// A name only counts as mentioned when nothing word-like follows it, so
// "@Sam" is not read out of "@Samantha".
const NOT_WORD_AFTER = "(?![\\p{L}\\p{N}])";

/** Ids of the members whose `@Full Name` still appears in `text`. The body's
 *  `@Name` is what the user sees; this is what the API is told. Derived at
 *  submit time, so deleting an inserted mention un-mentions it.
 *
 *  Longest names first, and each match is blanked out of what remains, so with
 *  both "Ann" and "Ann Lee" on the roster, `@Ann Lee` mentions only Ann Lee —
 *  not also Ann. Two members with the very same name cannot be told apart by
 *  text alone: one match is consumed, so only the first is mentioned. */
export function mentionedIds(text: string, members: Mentionable[]): number[] {
  let remaining = text;
  const ids: number[] = [];
  for (const m of [...members].sort((a, b) => b.full_name.length - a.full_name.length)) {
    const re = new RegExp(`@${escapeRe(m.full_name)}${NOT_WORD_AFTER}`, "u");
    if (re.test(remaining)) {
      ids.push(m.id);
      remaining = remaining.replace(re, " ");
    }
  }
  return ids;
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

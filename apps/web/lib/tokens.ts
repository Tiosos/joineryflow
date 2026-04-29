/**
 * Hartwood (H) design palette - the canonical token reference for JoineryFlow.
 *
 * The actual color values are owned by the CSS custom properties declared in
 * `app/globals.css` and surfaced to Tailwind via the `@theme` block. This
 * module re-exports the same tokens for use in inline styles, SVG fills, or
 * anywhere a JS-side string is needed.
 */
export const H = {
  bg: "var(--color-h-bg)",
  surface: "var(--color-h-surface)",
  ink: "var(--color-h-ink)",
  muted: "var(--color-h-muted)",
  line: "var(--color-h-line)",
  accent: "var(--color-h-accent)",
  good: "var(--color-h-good)",
  warn: "var(--color-h-warn)",
  bad: "var(--color-h-bad)",
  mono: "h-mono",
} as const;

export type HToken = keyof typeof H;

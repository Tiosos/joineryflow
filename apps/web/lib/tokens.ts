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
  surfaceAlt: "var(--color-h-surface-alt)",
  ink: "var(--color-h-ink)",
  ink2: "var(--color-h-ink2)",
  ink3: "var(--color-h-ink3)",
  ink4: "var(--color-h-ink4)",
  muted: "var(--color-h-muted)",
  line: "var(--color-h-line)",
  accent: "var(--color-h-accent)",
  accentSoft: "var(--color-h-accent-soft)",
  good: "var(--color-h-good)",
  warn: "var(--color-h-warn)",
  bad: "var(--color-h-bad)",
  info: "var(--color-h-info)",
  mono: "h-mono",
} as const;

export type HToken = keyof typeof H;

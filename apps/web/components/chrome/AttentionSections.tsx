"use client";

import Link from "next/link";

import { formatLocalTs } from "@/components/comments/format";
import { ATTENTION_KINDS, ATTENTION_ORDER, groupAttention, type AttentionItem, type AttentionKind } from "@/lib/attention";

/** The "waiting for you" sections (Q613), one per kind, shared by the bell and the notifications page.
 *  Derived by the API on every call, so there is nothing to mark read. */
export function AttentionSections({
  items,
  totals,
  variant,
  preview = 6,
  onNavigate,
}: {
  items: AttentionItem[];
  totals: Partial<Record<AttentionKind, number>>;
  variant: "bell" | "page";
  /** Bell only: how many rows of each kind to show. */
  preview?: number;
  onNavigate?: () => void;
}) {
  const by = groupAttention(items);
  return (
    <>
      {ATTENTION_ORDER.map((kind) => {
        const total = totals[kind] ?? 0;
        if (total === 0) return null;
        const meta = ATTENTION_KINDS[kind];
        const rows = variant === "bell" ? (by.get(kind) ?? []).slice(0, preview) : (by.get(kind) ?? []);
        const more = total - rows.length;
        return variant === "bell" ? (
          <div key={kind} data-testid={meta.section} className="border-b border-h-line">
            <div className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wider text-h-muted">
              {meta.heading(total)}
            </div>
            <ul>
              {rows.map((a) => (
                <li key={a.key}>
                  <Link
                    href={a.url}
                    onClick={onNavigate}
                    data-testid={meta.row}
                    className="block px-3 py-1.5 text-sm text-h-ink hover:bg-h-bg"
                  >
                    <span className="block truncate">{a.title}</span>
                    {a.detail && <span className="block truncate text-xs text-h-muted">{a.detail}</span>}
                  </Link>
                </li>
              ))}
            </ul>
            {meta.all ? (
              <Link
                href={meta.all.href}
                onClick={onNavigate}
                className="block px-3 pb-2 text-xs text-h-muted hover:text-h-ink"
              >
                {more > 0 ? `+${more} more · ${meta.all.bell}` : `${meta.all.bell[0].toUpperCase()}${meta.all.bell.slice(1)}`}
              </Link>
            ) : (
              more > 0 && (
                <Link
                  href="/notifications"
                  onClick={onNavigate}
                  className="block px-3 pb-2 text-xs text-h-muted hover:text-h-ink"
                >
                  {`+${more} more`}
                </Link>
              )
            )}
          </div>
        ) : (
          <section key={kind} data-testid={meta.pageList} className="grid gap-2">
            <h2 className="text-sm font-semibold text-h-ink">{meta.heading(total)}</h2>
            <ul className="grid gap-2">
              {rows.map((a) => (
                <li key={a.key}>
                  <Link
                    href={a.url}
                    className="block rounded border border-h-line bg-h-surface px-3 py-2 text-sm text-h-ink hover:bg-h-bg"
                  >
                    {a.title}
                    {a.created_at && <span className="text-xs text-h-muted">{` · ${formatLocalTs(a.created_at)}`}</span>}
                    {a.detail && <span className="mt-0.5 block text-sm">{a.detail}</span>}
                  </Link>
                </li>
              ))}
            </ul>
            {meta.all && more > 0 ? (
              <Link href={meta.all.href} className="text-xs text-h-muted hover:text-h-ink">
                {meta.all.page(total)}
              </Link>
            ) : (
              more > 0 && <p className="text-xs text-h-muted">{`${more} more not shown`}</p>
            )}
          </section>
        );
      })}
    </>
  );
}

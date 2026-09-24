"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";

import { errorText, summaryApi } from "@/lib/material-take-fetch";
import { UNIT_LABEL, type CurrentSummary, type SummaryLine } from "@/lib/material-take-types";

// Project Material Summary (sub-project #12, Plan V1 §20). Confirmation is
// advisory (Q499): Procurement may act on an unconfirmed summary.
export function MaterialSummaryPanel({ projectId, canEdit, canConfirm }: {
  projectId: number;
  canEdit: boolean;
  canConfirm: boolean;
}) {
  const [data, setData] = useState<CurrentSummary | null>(null);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await summaryApi.current(projectId));
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <p className="text-sm text-h-muted">{error ?? "Loading…"}</p>;
  const s = data.summary;
  const draft = s?.status === "draft";
  const staleCount = s?.lines.filter((l) => l.stale).length ?? 0;

  return (
    <div className="grid gap-4">
      {error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-h-ink">Material Summary</h2>
        {s && (
          <span className="rounded border border-h-line px-2 py-0.5 text-xs text-h-muted">
            #{s.summary_id} · {s.status === "confirmed" ? "Confirmed" : "Unconfirmed"}
          </span>
        )}
        <div className="ml-auto flex gap-2">
          {canEdit && (
            <button type="button" disabled={busy} onClick={() => act(() => summaryApi.build(projectId))}
              className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink disabled:opacity-50">
              {s ? "Rebuild from approved takes" : "Build summary"}
            </button>
          )}
          {s && draft && canConfirm && (
            <button type="button" disabled={busy} onClick={() => act(() => summaryApi.confirm(s.summary_id))}
              className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
              Confirm
            </button>
          )}
        </div>
      </div>

      {staleCount > 0 && (
        <p className="rounded border border-h-line bg-h-surface px-3 py-2 text-sm text-h-ink">
          {`${staleCount} ${staleCount === 1 ? "line" : "lines"} may be outdated — an item's take has changed since this summary was built. Rebuild to refresh.`}
        </p>
      )}

      {data.missing_takes.length > 0 && (
        <details className="rounded border border-h-line bg-h-surface px-3 py-2 text-sm">
          <summary className="cursor-pointer text-h-ink">
            {data.missing_takes.length} item{data.missing_takes.length === 1 ? "" : "s"} without an approved take
          </summary>
          <ul className="mt-2 grid gap-1">
            {data.missing_takes.map((m) => (
              <li key={m.item_id}>
                <Link href={`/items/${m.item_id}?tab=take`} className="text-h-accent">
                  <span className="h-mono">{m.num}</span> {m.description}
                </Link>
              </li>
            ))}
          </ul>
        </details>
      )}

      {!s && <p className="text-sm text-h-muted">No summary yet.</p>}

      {s && (
        <table className="w-full rounded border border-h-line bg-h-surface text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-h-muted">
            <tr>
              <th className="px-3 py-1.5">Material</th>
              <th className="px-3 py-1.5 text-right">Consolidated</th>
              <th className="px-3 py-1.5 text-right">Nest</th>
              <th className="px-3 py-1.5 text-right">Confirmed</th>
              <th className="px-3 py-1.5 text-right">On order</th>
              <th className="px-3 py-1.5 text-right">Received</th>
              <th className="px-3 py-1.5">Note</th>
            </tr>
          </thead>
          <tbody>
            {s.lines.map((l) => (
              <Fragment key={l.line_id}>
                <SummaryRow line={l} editable={draft && canEdit} expanded={open.has(l.line_id)}
                  toggle={() => setOpen((o) => {
                    const n = new Set(o);
                    if (n.has(l.line_id)) n.delete(l.line_id);
                    else n.add(l.line_id);
                    return n;
                  })}
                  save={(changes) => act(() => summaryApi.patchLine(s.summary_id, l.line_id, changes))} />
                {open.has(l.line_id) && l.sources.map((src) => (
                  <tr key={`${l.line_id}-${src.item_id}`} className="text-xs text-h-muted">
                    <td className="py-1 pl-8 pr-3">
                      <Link href={`/items/${src.item_id}?tab=take`} className="hover:text-h-ink">
                        <span className="h-mono">{src.num}</span> {src.description}
                      </Link>{" "}
                      · take v{src.take_version}
                    </td>
                    <td className="h-mono px-3 py-1 text-right">{src.qty}</td>
                    <td colSpan={5} />
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SummaryRow({ line, editable, expanded, toggle, save }: {
  line: SummaryLine;
  editable: boolean;
  expanded: boolean;
  toggle: () => void;
  save: (changes: { qty_confirmed?: string | null; note?: string | null }) => void;
}) {
  const [qty, setQty] = useState(line.qty_confirmed ?? "");
  const [note, setNote] = useState(line.note ?? "");
  useEffect(() => {
    setQty(line.qty_confirmed ?? "");
    setNote(line.note ?? "");
  }, [line]);
  const unit = UNIT_LABEL[line.unit];

  return (
    <tr className="border-t border-h-line align-top">
      <td className="px-3 py-1.5">
        <button type="button" onClick={toggle} aria-expanded={expanded} className="text-left text-h-ink">
          {expanded ? "▾" : "▸"} {line.description}
        </button>
        {line.stale && <span className="ml-2 rounded bg-h-bg px-1.5 text-xs text-h-muted">outdated</span>}
      </td>
      <td className="h-mono px-3 py-1.5 text-right text-h-ink">{line.qty_consolidated} {unit}</td>
      <td className="h-mono px-3 py-1.5 text-right text-h-muted">
        {line.nest_sheets != null ? `${line.nest_sheets} sheets` : "—"}
      </td>
      <td className="px-3 py-1.5 text-right">
        {editable ? (
          <input aria-label={`Confirmed qty for ${line.description}`} inputMode="decimal"
            placeholder={line.qty_consolidated} value={qty} onChange={(e) => setQty(e.target.value)}
            onBlur={() => qty !== (line.qty_confirmed ?? "") && save({ qty_confirmed: qty || null })}
            className="h-mono w-24 rounded border border-h-line bg-white px-2 py-0.5 text-right text-sm" />
        ) : (
          <span className="h-mono text-h-ink">{line.qty_confirmed ?? "—"}</span>
        )}
      </td>
      <td className="h-mono px-3 py-1.5 text-right text-h-muted">{line.qty_on_order ?? "—"}</td>
      <td className="h-mono px-3 py-1.5 text-right text-h-muted">{line.qty_received ?? "—"}</td>
      <td className="px-3 py-1.5">
        {editable ? (
          <input aria-label={`Note for ${line.description}`} value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => note !== (line.note ?? "") && save({ note: note || null })}
            className="w-full rounded border border-h-line bg-white px-2 py-0.5 text-sm" />
        ) : (
          <span className="text-h-muted">{line.note}</span>
        )}
      </td>
    </tr>
  );
}

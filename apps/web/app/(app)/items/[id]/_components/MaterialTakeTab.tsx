"use client";

import { useCallback, useEffect, useState } from "react";

import { errorText, takeApi } from "@/lib/material-take-fetch";
import {
  UNIT_LABEL,
  type CurrentTake,
  type Take,
  type TakeLine,
  type TakeVersion,
  type Unit,
} from "@/lib/material-take-types";

// Material Take (sub-project #12, Plan V1 §19). Editing needs drafter+,
// approving needs `list` approve — the same three roles today.
const EDITORS = ["drafter", "manager", "admin"];

export function MaterialTakeTab({ itemId, currentUserRole }: {
  itemId: number;
  currentUserRole: string | null;
}) {
  const canEdit = EDITORS.includes(currentUserRole ?? "");
  const [cur, setCur] = useState<CurrentTake | null>(null);
  const [history, setHistory] = useState<TakeVersion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, h] = await Promise.all([takeApi.current(itemId), takeApi.history(itemId)]);
      setCur(c);
      setHistory(h);
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, [itemId]);

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

  if (!cur) {
    return <p className="text-sm text-h-muted">{error ?? "Loading…"}</p>;
  }

  return (
    <div className="grid gap-4">
      {error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

      {cur.outdated && cur.approved && (
        <div className="rounded border border-h-line bg-h-surface px-3 py-2 text-sm">
          <p className="text-h-ink">
            <strong>Outdated.</strong>{" "}
            {`This item's parts or hardware have changed since take v${cur.approved.version} was approved.`}
          </p>
          {canEdit && (
            <div className="mt-2 flex gap-2">
              {(["no_impact", "partial", "full"] as const).map((o) => (
                <button key={o} type="button" disabled={busy || (o !== "no_impact" && !!cur.draft)}
                  onClick={() => act(() => takeApi.review(cur.approved!.take_id, o))}
                  className="rounded border border-h-line px-2 py-1 text-xs text-h-ink disabled:opacity-50">
                  {o === "no_impact" ? "No impact" : o === "partial" ? "Partial impact" : "Full impact"}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {!cur.draft && canEdit && (
        <div>
          <button type="button" disabled={busy} onClick={() => act(() => takeApi.generate(itemId))}
            className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
            {cur.approved ? `Start v${cur.approved.version + 1}` : "Generate material take"}
          </button>
        </div>
      )}

      {cur.draft && (
        <TakeTable take={cur.draft} editable={canEdit} busy={busy} act={act}
          onApprove={() => act(() => takeApi.approve(cur.draft!.take_id))} />
      )}
      {cur.approved && <TakeTable take={cur.approved} editable={false} busy={busy} act={act} />}
      {!cur.draft && !cur.approved && !canEdit && (
        <p className="text-sm text-h-muted">No material take yet.</p>
      )}

      {history.length > 0 && (
        <div className="text-xs text-h-muted">
          Versions:{" "}
          {history.map((h) => `v${h.version} ${h.status}`).join(" · ")}
        </div>
      )}
    </div>
  );
}

function TakeTable({ take, editable, busy, act, onApprove }: {
  take: Take;
  editable: boolean;
  busy: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
  onApprove?: () => void;
}) {
  const [adding, setAdding] = useState({ description: "", unit: "m" as Unit, qty: "" });

  return (
    <section className="rounded border border-h-line bg-h-surface">
      <header className="flex items-center gap-3 border-b border-h-line px-3 py-2">
        <h3 className="text-sm font-semibold text-h-ink">
          Take v{take.version} <span className="font-normal text-h-muted">· {take.status}</span>
        </h3>
        {editable && take.status === "draft" && (
          <div className="ml-auto flex gap-2">
            <button type="button" disabled={busy} onClick={() => act(() => takeApi.regenerate(take.take_id))}
              className="rounded border border-h-line px-2 py-1 text-xs text-h-ink disabled:opacity-50">
              Regenerate
            </button>
            <button type="button" disabled={busy} onClick={onApprove}
              className="rounded bg-h-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50">
              Approve
            </button>
          </div>
        )}
      </header>
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-h-muted">
          <tr>
            <th className="px-3 py-1.5">Material</th>
            <th className="px-3 py-1.5 text-right">Generated</th>
            <th className="px-3 py-1.5 text-right">Wastage %</th>
            <th className="px-3 py-1.5 text-right">Qty</th>
            <th className="px-3 py-1.5">Unit</th>
            <th className="px-3 py-1.5">Note</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {take.lines.map((l) => (
            <LineRow key={l.line_id} line={l} takeId={take.take_id} editable={editable} act={act} />
          ))}
          {take.lines.length === 0 && (
            <tr><td colSpan={7} className="px-3 py-2 text-h-muted">No lines — this item has no parts or hardware.</td></tr>
          )}
        </tbody>
      </table>
      {editable && (
        <form className="flex flex-wrap items-end gap-2 border-t border-h-line px-3 py-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!adding.description.trim() || !adding.qty) return;
            act(() => takeApi.addLine(take.take_id, adding)).then(() =>
              setAdding({ description: "", unit: "m", qty: "" }));
          }}>
          <input aria-label="New line description" placeholder="Add a line — e.g. edge tape, finishing"
            value={adding.description} onChange={(e) => setAdding({ ...adding, description: e.target.value })}
            className="min-w-64 flex-1 rounded border border-h-line bg-white px-2 py-1 text-sm" />
          <input aria-label="New line qty" inputMode="decimal" placeholder="Qty" value={adding.qty}
            onChange={(e) => setAdding({ ...adding, qty: e.target.value })}
            className="h-mono w-20 rounded border border-h-line bg-white px-2 py-1 text-sm" />
          <select aria-label="New line unit" value={adding.unit}
            onChange={(e) => setAdding({ ...adding, unit: e.target.value as Unit })}
            className="rounded border border-h-line bg-white px-2 py-1 text-sm">
            {(Object.keys(UNIT_LABEL) as Unit[]).map((u) => <option key={u} value={u}>{UNIT_LABEL[u]}</option>)}
          </select>
          <button type="submit" disabled={busy}
            className="rounded border border-h-line px-2 py-1 text-xs text-h-ink disabled:opacity-50">Add line</button>
        </form>
      )}
    </section>
  );
}

function LineRow({ line, takeId, editable, act }: {
  line: TakeLine;
  takeId: number;
  editable: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [wastage, setWastage] = useState(line.wastage_pct);
  const [qty, setQty] = useState(line.qty);
  const [note, setNote] = useState(line.note ?? "");
  useEffect(() => {
    setWastage(line.wastage_pct);
    setQty(line.qty);
    setNote(line.note ?? "");
  }, [line]);

  const save = (changes: Record<string, string | null>) =>
    act(() => takeApi.patchLine(takeId, line.line_id, changes));
  const cell = "h-mono w-20 rounded border border-h-line bg-white px-2 py-0.5 text-right text-sm";

  return (
    <tr className="border-t border-h-line">
      <td className="px-3 py-1.5 text-h-ink">
        {line.description}
        {line.source === "manual" && <span className="ml-2 text-xs text-h-muted">manual</span>}
      </td>
      <td className="h-mono px-3 py-1.5 text-right text-h-muted">{line.qty_generated ?? "—"}</td>
      <td className="px-3 py-1.5 text-right">
        {editable ? (
          <input aria-label={`Wastage for ${line.description}`} inputMode="decimal" className={cell}
            value={wastage} onChange={(e) => setWastage(e.target.value)}
            onBlur={() => wastage !== line.wastage_pct && save({ wastage_pct: wastage })} />
        ) : <span className="h-mono">{line.wastage_pct}</span>}
      </td>
      <td className="px-3 py-1.5 text-right">
        {editable ? (
          <input aria-label={`Qty for ${line.description}`} inputMode="decimal" className={cell}
            value={qty} onChange={(e) => setQty(e.target.value)}
            onBlur={() => qty !== line.qty && save({ qty })} />
        ) : <span className="h-mono text-h-ink">{line.qty}</span>}
      </td>
      <td className="px-3 py-1.5 text-h-muted">{UNIT_LABEL[line.unit]}</td>
      <td className="px-3 py-1.5">
        {editable ? (
          <input aria-label={`Note for ${line.description}`} value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => note !== (line.note ?? "") && save({ note: note || null })}
            className="w-full rounded border border-h-line bg-white px-2 py-0.5 text-sm" />
        ) : <span className="text-h-muted">{line.note}</span>}
      </td>
      <td className="px-3 py-1.5 text-right">
        {editable && line.source === "manual" && (
          <button type="button" onClick={() => act(() => takeApi.deleteLine(takeId, line.line_id))}
            className="text-xs text-h-muted hover:text-h-ink">Remove</button>
        )}
      </td>
    </tr>
  );
}

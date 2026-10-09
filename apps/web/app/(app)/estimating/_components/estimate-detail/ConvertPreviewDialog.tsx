"use client";

import { useState } from "react";
import type { Line } from "@/lib/estimating-types";
import { fmtMoney } from "./shared";

interface ConvertPreviewDialogProps {
  estimateNo: string;
  lines: Line[];
  busy: boolean;
  onConfirm: (includeLineIds: number[]) => void;
  onCancel: () => void;
}

export function ConvertPreviewDialog({
  estimateNo, lines, busy, onConfirm, onCancel,
}: ConvertPreviewDialogProps) {
  // Q490's PM review-and-select screen: every line starts selected (nothing
  // re-entered that's already known), and deselecting one just means it
  // doesn't become a Joinery Item — the rest of the handover is unaffected.
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(lines.map((l) => l.line_id)),
  );
  const selectedLines = lines.filter((l) => selected.has(l.line_id));
  const items = selectedLines.length;
  const parts = selectedLines.reduce((acc, l) => acc + l.parts.length, 0);
  const hardware = selectedLines.reduce((acc, l) => acc + l.hardware.length, 0);
  const labour = selectedLines.reduce(
    (acc, l) => acc + l.labour.filter((x) => parseFloat(x.hours) > 0).length, 0,
  );

  function toggle(lineId: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(lineId)) next.delete(lineId);
      else next.add(lineId);
      return next;
    });
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <div
        className="w-full max-w-md space-y-3 rounded border border-h-line bg-white p-5 shadow-xl"
        data-testid="convert-preview-dialog"
      >
        <h2 className="text-lg font-semibold text-h-ink">
          Convert {estimateNo} to project
        </h2>
        <p className="text-sm text-h-muted">
          Choose which lines become Joinery Items. This materialises the
          selection into items, parts, hardware lines, and labour
          assignments. The new project will reference this revision.
        </p>
        <ul className="max-h-48 space-y-1 overflow-y-auto rounded border border-h-line p-2 text-sm">
          {lines.map((l) => (
            <li key={l.line_id} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selected.has(l.line_id)}
                onChange={() => toggle(l.line_id)}
                data-testid={`convert-line-${l.line_id}`}
              />
              <span className="flex-1">{l.description}</span>
              <span className="font-mono text-h-muted">{fmtMoney(l.total_sell)}</span>
            </li>
          ))}
        </ul>
        <dl className="grid grid-cols-2 gap-y-2 rounded border border-h-line bg-h-surface p-3 text-sm">
          <dt className="text-h-muted">Items to create</dt>
          <dd className="text-right font-mono">{items}</dd>
          <dt className="text-h-muted">Parts</dt>
          <dd className="text-right font-mono">{parts}</dd>
          <dt className="text-h-muted">Hardware lines</dt>
          <dd className="text-right font-mono">{hardware}</dd>
          <dt className="text-h-muted">Labour assignments</dt>
          <dd className="text-right font-mono">{labour}</dd>
        </dl>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-h-line bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(Array.from(selected))}
            disabled={busy || selected.size === 0}
            className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
            data-testid="convert-confirm-btn"
          >
            {busy ? "Converting…" : "Convert"}
          </button>
        </div>
      </div>
    </div>
  );
}

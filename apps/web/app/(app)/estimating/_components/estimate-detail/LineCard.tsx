"use client";

import { useState } from "react";
import type { Line, LineHardware, LinePart, StageKey } from "@/lib/estimating-types";
import { CatalogMap, fmtMoney, isPartKind, CallApiFn, PickerPayload } from "./shared";
import { LineEditRow } from "./LineEditRow";
import { PartRow } from "./PartRow";
import { HardwareRow } from "./HardwareRow";
import { CatalogPicker } from "./CatalogPicker";
import { LabourEditor } from "./LabourEditor";

interface LineCardProps {
  line: Line;
  isDraft: boolean;
  catalogs: CatalogMap;
  onChanged: () => Promise<void>;
  onClone: (line: Line) => Promise<void>;
  callApi: CallApiFn;
}

export function LineCard({ line, isDraft, catalogs, onChanged, onClone, callApi }: LineCardProps) {
  const [showPicker, setShowPicker] = useState(false);
  const [showLabour, setShowLabour] = useState(false);
  const [editing, setEditing] = useState(false);

  async function addFromPicker(payload: PickerPayload) {
    if (isPartKind(payload.kind)) {
      const r = await callApi("POST", `/api/lines/${line.line_id}/parts`, {
        material_type: payload.kind,
        material_id: payload.material_id,
        qty: payload.qty,
        len_mm: payload.len_mm ?? undefined,
        wid_mm: payload.wid_mm ?? undefined,
        paint_instruction: payload.paint_instruction,
        comment: payload.comment ?? undefined,
      });
      if (r.ok) {
        await onChanged();
        setShowPicker(false);
      }
    } else {
      const r = await callApi("POST", `/api/lines/${line.line_id}/hardware`, {
        material_type: payload.kind,
        material_id: payload.material_id,
        qty: payload.qty,
        comment: payload.comment ?? undefined,
      });
      if (r.ok) {
        await onChanged();
        setShowPicker(false);
      }
    }
  }

  async function setLabour(stage: StageKey, hours: number) {
    const r = await callApi("POST", `/api/lines/${line.line_id}/labour`, {
      stage_key: stage,
      hours,
    });
    if (r.ok) await onChanged();
  }

  async function deleteLine() {
    if (!window.confirm(`Delete line "${line.description}"?`)) return;
    const r = await callApi("DELETE", `/api/lines/${line.line_id}`);
    if (r.ok) await onChanged();
  }

  async function patchPart(p: LinePart, qty: number) {
    if (!Number.isFinite(qty) || qty <= 0) return;
    const r = await callApi("PATCH", `/api/estimate-parts/${p.part_id}`, { qty });
    if (r.ok) await onChanged();
  }

  async function removePart(p: LinePart) {
    const r = await callApi("DELETE", `/api/estimate-parts/${p.part_id}`);
    if (r.ok) await onChanged();
  }

  async function patchHardware(h: LineHardware, qty: number) {
    if (!Number.isFinite(qty) || qty <= 0) return;
    const r = await callApi("PATCH", `/api/hardware/${h.hw_id}`, { qty });
    if (r.ok) await onChanged();
  }

  async function removeHardware(h: LineHardware) {
    const r = await callApi("DELETE", `/api/hardware/${h.hw_id}`);
    if (r.ok) await onChanged();
  }

  return (
    <div
      className="rounded border border-h-line bg-h-surface p-4"
      data-testid={`line-card-${line.line_id}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          {isDraft ? (
            <span className="cursor-move text-h-muted" title="Drag to reorder">⋮⋮</span>
          ) : null}
          <span className="text-xs font-mono text-h-muted">#{line.seq}</span>
          {editing ? null : (
            <span className="font-medium text-h-ink">{line.description}</span>
          )}
        </div>
        <div className="text-right">
          <div className="font-mono text-sm text-h-ink">{fmtMoney(line.total_sell)}</div>
          <div className="font-mono text-xs text-h-muted">
            {parseFloat(line.qty)} {line.unit} × {fmtMoney(line.unit_sell)}
          </div>
        </div>
      </div>

      {editing && isDraft ? (
        <LineEditRow
          line={line}
          callApi={callApi}
          onSaved={async () => { setEditing(false); await onChanged(); }}
          onCancel={() => setEditing(false)}
        />
      ) : null}

      <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-h-muted">
        <span>Material: {fmtMoney(line.material_cost)}</span>
        <span>Labour: {fmtMoney(line.labour_cost)}</span>
        <span>Total cost: {fmtMoney(line.total_cost)}</span>
      </div>

      {line.parts.length > 0 || line.hardware.length > 0 || line.labour.length > 0 ? (
        <div className="mt-3 space-y-1 border-t border-h-line pt-3 text-xs">
          {line.parts.map((p) => (
            <PartRow
              key={p.part_id}
              part={p}
              isDraft={isDraft}
              onPatch={(qty) => patchPart(p, qty)}
              onRemove={() => removePart(p)}
            />
          ))}
          {line.hardware.map((h) => (
            <HardwareRow
              key={h.hw_id}
              hardware={h}
              isDraft={isDraft}
              onPatch={(qty) => patchHardware(h, qty)}
              onRemove={() => removeHardware(h)}
            />
          ))}
          {line.labour.map((l) => (
            <div key={l.labour_id} className="flex justify-between gap-2">
              <span>
                <span className="font-mono text-h-muted">{l.stage_key}</span>{" "}
                {parseFloat(l.hours)} hr × {fmtMoney(l.rate_snapshot)}/hr
              </span>
              <span className="flex items-center gap-2">
                <span className="font-mono">{fmtMoney(l.cost_extended)}</span>
                {isDraft ? (
                  <button
                    type="button"
                    onClick={() => setLabour(l.stage_key, 0)}
                    className="text-red-700 hover:text-red-900"
                    title="Remove labour"
                  >
                    ×
                  </button>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {isDraft ? (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-h-line pt-3">
          <button
            type="button"
            onClick={() => setShowPicker((s) => !s)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`add-material-${line.line_id}`}
          >
            + Material
          </button>
          <button
            type="button"
            onClick={() => setShowLabour((s) => !s)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`add-labour-${line.line_id}`}
          >
            + Labour
          </button>
          <button
            type="button"
            onClick={() => setEditing((s) => !s)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`edit-line-${line.line_id}`}
          >
            ✎ Edit
          </button>
          <button
            type="button"
            onClick={() => onClone(line)}
            className="rounded border border-h-line bg-white px-2 py-1 text-xs hover:bg-gray-50"
            data-testid={`clone-line-${line.line_id}`}
          >
            ⎘ Clone
          </button>
          <button
            type="button"
            onClick={deleteLine}
            className="ml-auto rounded border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-800 hover:bg-red-100"
          >
            Delete line
          </button>
        </div>
      ) : null}

      {showPicker ? (
        <CatalogPicker
          catalogs={catalogs}
          onPick={addFromPicker}
          onClose={() => setShowPicker(false)}
        />
      ) : null}
      {showLabour ? (
        <LabourEditor line={line} onSet={setLabour} onClose={() => setShowLabour(false)} />
      ) : null}
    </div>
  );
}

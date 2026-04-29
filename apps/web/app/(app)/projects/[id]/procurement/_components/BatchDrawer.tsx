"use client";

import { useEffect, useState } from "react";
import type { BatchOut } from "@/lib/procurement-types";
import { ProcFetch } from "@/lib/procurement-fetch";
import { AllocationEditor } from "./AllocationEditor";
import { BatchStatusPill } from "@/components/procurement/BatchStatusPill";

interface Props {
  projectId: number;
  initial?: Partial<BatchOut>;
  batchId: number | null;
  canWrite: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export function BatchDrawer({ projectId, initial, batchId, canWrite, onClose, onSaved }: Props) {
  const [batch, setBatch] = useState<Partial<BatchOut>>(initial ?? {});
  const [err, setErr]     = useState<string | null>(null);

  useEffect(() => {
    if (batchId == null) return;
    fetch(`/api/batches/${batchId}`, { credentials: "include" })
      .then(r => r.json())
      .then(setBatch)
      .catch(e => setErr(String(e)));
  }, [batchId]);

  async function save() {
    setErr(null);
    try {
      if (batchId == null) {
        await ProcFetch.createBatch({ ...batch, project_id: projectId });
      } else {
        await ProcFetch.patchBatch(batchId, batch);
      }
      onSaved();
      onClose();
    } catch (e) { setErr(String(e)); }
  }

  function field<K extends keyof BatchOut>(k: K, v: BatchOut[K]) {
    setBatch(prev => ({ ...prev, [k]: v }));
  }

  return (
    <aside
      role="dialog" data-testid="batch-drawer"
      className="fixed inset-y-0 right-0 z-30 w-[520px] overflow-y-auto border-l border-h-line bg-h-surface p-4 shadow-xl"
    >
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-h-ink">
          {batchId == null ? "New batch" : `Batch #${batchId}`}
          {batch.status && <span className="ml-2"><BatchStatusPill status={batch.status} /></span>}
        </h2>
        <button onClick={onClose} aria-label="Close drawer" className="text-h-muted hover:text-h-ink">✕</button>
      </header>

      {err && <p className="text-sm text-h-bad">{err}</p>}

      <div className="grid gap-2">
        <label className="grid gap-1 text-sm">
          <span className="text-h-muted">Material type</span>
          <select
            value={batch.material_type ?? ""}
            onChange={e => field("material_type", e.target.value as BatchOut["material_type"])}
            disabled={!canWrite || batchId != null}
            data-testid="batch-material-type"
            className="rounded border border-h-line bg-h-bg px-2 py-1"
          >
            <option value="">—</option>
            {["BOARD","HARDWARE","CUSTOM","BENCHTOP","APPLIANCE","HIRE"].map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          <span className="text-h-muted">Material id</span>
          <input
            type="number"
            value={String(batch.material_id ?? "")}
            onChange={e => field("material_id", Number(e.target.value))}
            disabled={!canWrite || batchId != null}
            data-testid="batch-material-id"
            className="rounded border border-h-line bg-h-bg px-2 py-1 h-mono"
          />
        </label>
        {(["supplier","po_ref"] as const).map(k => (
          <label key={k} className="grid gap-1 text-sm">
            <span className="text-h-muted">{k.replace("_"," ")}</span>
            <input
              value={String(batch[k] ?? "")}
              onChange={e => field(k, e.target.value)}
              disabled={!canWrite}
              data-testid={`batch-${k}`}
              className="rounded border border-h-line bg-h-bg px-2 py-1"
            />
          </label>
        ))}
        <div className="grid grid-cols-2 gap-2">
          {(["qty_ordered","qty_received"] as const).map(k => (
            <label key={k} className="grid gap-1 text-sm">
              <span className="text-h-muted">{k.replace("_"," ")}</span>
              <input
                type="number"
                value={String(batch[k] ?? "")}
                onChange={e => field(k, e.target.value as never)}
                disabled={!canWrite}
                data-testid={`batch-${k}`}
                className="rounded border border-h-line bg-h-bg px-2 py-1 h-mono"
              />
            </label>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {(["ordered_date","eta_date","received_date"] as const).map(k => (
            <label key={k} className="grid gap-1 text-sm">
              <span className="text-h-muted">{k.replace("_date","")}</span>
              <input
                type="date"
                value={String(batch[k] ?? "")}
                onChange={e => field(k, e.target.value as never)}
                disabled={!canWrite}
                data-testid={`batch-${k}`}
                className="rounded border border-h-line bg-h-bg px-2 py-1 h-mono"
              />
            </label>
          ))}
        </div>
        <label className="grid gap-1 text-sm">
          <span className="text-h-muted">Notes</span>
          <textarea
            value={String(batch.notes ?? "")}
            onChange={e => field("notes", e.target.value)}
            disabled={!canWrite}
            data-testid="batch-notes"
            className="rounded border border-h-line bg-h-bg px-2 py-1"
          />
        </label>

        {canWrite && (
          <div className="flex gap-2">
            <button onClick={save} data-testid="save-batch" className="rounded bg-h-accent px-3 py-1 text-sm text-white">
              Save
            </button>
            {batchId != null && batch.status !== "CANCELLED" && (
              <button
                onClick={async () => {
                  if (!confirm("Cancel this batch?")) return;
                  const r = await ProcFetch.cancelBatch(batchId);
                  if (!r.ok) setErr(await r.text());
                  else { onSaved(); onClose(); }
                }}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-bad"
              >Cancel batch</button>
            )}
          </div>
        )}
      </div>

      {batchId != null && (
        <section className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-h-ink">Allocations</h3>
          <AllocationEditor batchId={batchId} canWrite={canWrite} />
        </section>
      )}
    </aside>
  );
}

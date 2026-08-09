"use client";

import { useState } from "react";

import { createCutPlan, optimiseProject } from "@/lib/cut-floor-fetch";
import type { OptimiseOut, OptimiseStrategy } from "@/lib/cut-floor-types";
import { SheetCanvas } from "./SheetCanvas";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

interface OptimiseDialogProps {
  projects: Project[];
  defaultProjectId: number | null;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export function OptimiseDialog({
  projects,
  defaultProjectId,
  onClose,
  onSaved,
}: OptimiseDialogProps) {
  const [projectId, setProjectId] = useState<number | null>(
    defaultProjectId ?? projects[0]?.id ?? null,
  );
  const [name, setName] = useState("Optimised nest");
  const [materialSku, setMaterialSku] = useState("18-PB");
  const [sheetLen, setSheetLen] = useState(2440);
  const [sheetWid, setSheetWid] = useState(1220);
  const [kerf, setKerf] = useState(3);
  const [strategy, setStrategy] = useState<OptimiseStrategy>("maxrects");

  const [result, setResult] = useState<OptimiseOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runOptimise() {
    if (projectId === null) return;
    setBusy(true);
    setError(null);
    try {
      const out = await optimiseProject(projectId, {
        name,
        material_sku: materialSku,
        sheet_len_mm: sheetLen,
        sheet_wid_mm: sheetWid,
        kerf_mm: kerf,
        strategy,
      });
      setResult(out);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveAsPlan() {
    if (projectId === null || result === null) return;
    setBusy(true);
    setError(null);
    try {
      await createCutPlan(projectId, result.proposal);
      await onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Optimise cut plan"
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg border border-h-line bg-h-bg p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-lg font-medium text-h-ink">
          Optimise nest
          <span className="ml-2 font-mono text-xs uppercase text-h-muted">
            stub
          </span>
        </h2>

        {result === null ? (
          <div className="grid gap-3">
            <div>
              <label className="block text-sm text-h-muted">Project</label>
              <select
                value={projectId ?? ""}
                onChange={(e) =>
                  setProjectId(e.target.value ? Number(e.target.value) : null)
                }
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.project_code} — {p.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm text-h-muted">Plan name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              />
            </div>

            <div>
              <label className="block text-sm text-h-muted">
                Material SKU
              </label>
              <input
                value={materialSku}
                onChange={(e) => setMaterialSku(e.target.value)}
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 font-mono text-sm text-h-ink"
              />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-sm text-h-muted">
                  Sheet length (mm)
                </label>
                <input
                  type="number"
                  min={1}
                  value={sheetLen}
                  onChange={(e) => setSheetLen(Number(e.target.value))}
                  className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
                />
              </div>
              <div>
                <label className="block text-sm text-h-muted">
                  Sheet width (mm)
                </label>
                <input
                  type="number"
                  min={1}
                  value={sheetWid}
                  onChange={(e) => setSheetWid(Number(e.target.value))}
                  className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
                />
              </div>
              <div>
                <label className="block text-sm text-h-muted">Kerf (mm)</label>
                <input
                  type="number"
                  min={0}
                  value={kerf}
                  onChange={(e) => setKerf(Number(e.target.value))}
                  className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-h-muted">Algorithm</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as OptimiseStrategy)}
                className="w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              >
                <option value="maxrects">MaxRects (best yield)</option>
                <option value="naive">Naive shelf (baseline)</option>
              </select>
            </div>

            <p className="text-xs text-h-muted">
              Nests every part in the project across as many sheets as needed;
              parts larger than the sheet are skipped. Preview the result before
              saving it as a cut plan.
            </p>

            {error && (
              <div className="rounded border border-red-500 bg-red-50 p-2 text-xs text-red-900">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-ink hover:bg-h-surface"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={busy || projectId === null}
                onClick={runOptimise}
                className="rounded border border-h-accent bg-h-accent px-3 py-1 text-sm text-h-bg disabled:opacity-50"
              >
                {busy ? "Optimising…" : "Optimise"}
              </button>
            </div>
          </div>
        ) : (
          <div className="grid gap-3">
            <div className="flex flex-wrap gap-4 rounded-lg border border-h-line bg-h-surface px-3 py-2 text-sm">
              <span className="text-h-ink">
                <span className="font-medium">{result.summary.placed}</span>
                <span className="text-h-muted"> placed</span>
              </span>
              <span className="text-h-ink">
                <span className="font-medium">{result.summary.skipped}</span>
                <span className="text-h-muted"> skipped</span>
              </span>
              <span className="text-h-ink">
                <span className="font-medium">
                  {Math.round(result.summary.utilization_pct * 100)}%
                </span>
                <span className="text-h-muted"> utilisation</span>
              </span>
              <span className="text-h-muted">
                {result.summary.total_parts} parts ·{" "}
                {result.summary.sheets_used} sheet
                {result.summary.sheets_used === 1 ? "" : "s"}
              </span>
            </div>

            {result.summary.skipped > 0 && (
              <details className="rounded-lg border border-h-line bg-h-surface px-3 py-2 text-sm">
                <summary className="cursor-pointer text-h-muted">
                  {result.summary.skipped} part
                  {result.summary.skipped === 1 ? "" : "s"} skipped
                </summary>
                <ul className="mt-2 flex flex-col gap-1 text-xs text-h-ink">
                  {result.summary.skipped_reasons.map((s, i) => (
                    <li key={i}>
                      <span className="font-mono">{s.label}</span>
                      <span className="text-h-muted"> — {s.reason}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <div className="flex flex-col gap-3">
              {result.proposal.sheets.map((sheet) => (
                <SheetCanvas
                  key={sheet.sheet_no}
                  sheetNo={sheet.sheet_no}
                  materialSku={sheet.material_sku}
                  slots={sheet.slots.map((s) => ({
                    x: s.x,
                    y: s.y,
                    w: s.w,
                    h: s.h,
                    label: s.label ?? null,
                  }))}
                  extent={{ width: sheetLen, height: sheetWid }}
                />
              ))}
            </div>

            {error && (
              <div className="rounded border border-red-500 bg-red-50 p-2 text-xs text-red-900">
                {error}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setResult(null)}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-ink hover:bg-h-surface"
              >
                ← Back
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-muted hover:text-h-ink"
              >
                Discard
              </button>
              <button
                type="button"
                disabled={busy || result.summary.placed === 0}
                onClick={saveAsPlan}
                className="rounded border border-h-accent bg-h-accent px-3 py-1 text-sm text-h-bg disabled:opacity-50"
              >
                {busy ? "Saving…" : "Save as plan"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

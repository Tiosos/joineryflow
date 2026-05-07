"use client";

import { useState } from "react";
import { commitCvImport, previewCvImport } from "@/lib/cv-fetch";
import type {
  CvCommitResolution,
  CvPreviewOut,
} from "@/lib/cv-types";
import { UnknownCodeRow } from "./UnknownCodeRow";

type Phase = "upload" | "resolve" | "commit" | "done";

interface Props {
  itemId: number;
  itemHasModules: boolean;
  existingModuleCount: number;
  onClose: () => void;
}

export function CvImportDialog({
  itemId,
  itemHasModules,
  existingModuleCount,
  onClose,
}: Props) {
  const [phase, setPhase] = useState<Phase>("upload");
  const [pasteText, setPasteText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CvPreviewOut | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, CvCommitResolution>>({});
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [doneSummary, setDoneSummary] = useState<string | null>(null);

  async function onPreview() {
    setErr(null);
    setBusy(true);
    try {
      const fd = new FormData();
      if (file) {
        fd.append("file", file);
      } else if (pasteText.trim()) {
        fd.append("body", pasteText);
      } else {
        setErr("Paste CSV text or pick a file.");
        setBusy(false);
        return;
      }
      const out = await previewCvImport(itemId, fd);
      setPreview(out);
      setResolutions({});
      if (out.unknown_codes.length === 0) {
        setPhase("commit");
      } else {
        setPhase("resolve");
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setErr(msg);
    } finally {
      setBusy(false);
    }
  }

  function setResolution(cv_code: string, r: CvCommitResolution) {
    setResolutions((prev) => ({ ...prev, [cv_code]: r }));
  }

  function allUnknownsResolved(): boolean {
    if (!preview) return false;
    return preview.unknown_codes.every((u) => !!resolutions[u.cv_code]);
  }

  async function onCommit() {
    if (!preview) return;
    setErr(null);
    setBusy(true);
    try {
      const out = await commitCvImport(
        itemId,
        preview.run_id,
        {
          resolutions: Object.values(resolutions),
          replace,
        },
        replace ? "replace" : undefined,
      );
      setDoneSummary(
        `${out.modules_created} module${out.modules_created === 1 ? "" : "s"}, ` +
        `${out.parts_created} part${out.parts_created === 1 ? "" : "s"} imported.`,
      );
      setPhase("done");
      setTimeout(() => onClose(), 1500);
    } catch (e: unknown) {
      const detail = (e as { detail?: { code?: string } })?.detail;
      const status = (e as { status?: number })?.status;
      if (status === 409 && detail?.code === "ITEM_NOT_EMPTY") {
        setErr(
          'Item already has modules. Tick "Replace existing modules" and try again.',
        );
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[720px] max-h-[85vh] overflow-y-auto rounded-lg bg-h-bg p-6 shadow-xl">
        <header className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-h-ink">
            Import from Cabinet Vision
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-h-muted hover:text-h-ink"
          >
            Close
          </button>
        </header>

        <ol className="mb-4 flex items-center gap-2 text-xs text-h-muted">
          <li className={phase === "upload" ? "font-semibold text-h-ink" : ""}>
            1. Upload
          </li>
          <li>·</li>
          <li className={phase === "resolve" ? "font-semibold text-h-ink" : ""}>
            2. Resolve
          </li>
          <li>·</li>
          <li className={phase === "commit" || phase === "done" ? "font-semibold text-h-ink" : ""}>
            3. Confirm
          </li>
        </ol>

        {err && (
          <div className="mb-3 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
            {err}
          </div>
        )}

        {phase === "upload" && (
          <div className="space-y-3">
            <p className="text-sm text-h-muted">
              Paste a CV part-list CSV below, or pick a .csv file (≤ 1 MB).
            </p>
            <textarea
              rows={10}
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder="Module,Part Name,Qty,Length,Width,Material&#10;1,Side L,1,720,580,18-PB"
              className="w-full rounded-md border border-h-line bg-h-bg px-3 py-2 font-mono text-xs"
            />
            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".csv,.txt,text/csv"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={busy || (!pasteText.trim() && !file)}
                onClick={onPreview}
                className="rounded-md bg-h-accent px-4 py-1 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? "Parsing…" : "Preview"}
              </button>
            </div>
          </div>
        )}

        {phase === "resolve" && preview && (
          <div className="space-y-3">
            <SummaryStrip preview={preview} />
            <p className="text-sm text-h-muted">
              Resolve {preview.unknown_codes.length} unknown code(s) before importing.
            </p>
            <div className="divide-y divide-h-line rounded-md border border-h-line">
              {preview.unknown_codes.map((u) => (
                <UnknownCodeRow
                  key={u.cv_code}
                  unknown={u}
                  resolution={resolutions[u.cv_code]}
                  onChange={(r) => setResolution(u.cv_code, r)}
                />
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPhase("upload")}
                className="rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm"
              >
                Back
              </button>
              <button
                type="button"
                disabled={!allUnknownsResolved()}
                onClick={() => setPhase("commit")}
                className="rounded-md bg-h-accent px-4 py-1 text-sm font-medium text-white disabled:opacity-50"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {phase === "commit" && preview && (
          <div className="space-y-3">
            <SummaryStrip preview={preview} />
            <p className="text-sm text-h-ink">
              Import {totalImportableParts(preview, resolutions)} parts in{" "}
              {preview.modules.length} module{preview.modules.length === 1 ? "" : "s"} into this item?
            </p>

            {itemHasModules && (
              <label className="flex items-start gap-2 rounded-md border border-h-line bg-h-surface p-3 text-sm">
                <input
                  type="checkbox"
                  checked={replace}
                  onChange={(e) => setReplace(e.target.checked)}
                  className="mt-1"
                />
                <span>
                  <strong>Replace existing modules.</strong> This item already has{" "}
                  {existingModuleCount} module{existingModuleCount === 1 ? "" : "s"}; checking this box will{" "}
                  <em>delete them</em> before importing the new parts. Without it, the import will fail.
                </span>
              </label>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() =>
                  preview.unknown_codes.length > 0
                    ? setPhase("resolve")
                    : setPhase("upload")
                }
                className="rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm"
              >
                Back
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={onCommit}
                className="rounded-md bg-h-accent px-4 py-1 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? "Importing…" : "Import"}
              </button>
            </div>
          </div>
        )}

        {phase === "done" && (
          <div className="space-y-2 text-center">
            <p className="text-base font-medium text-h-ink">{doneSummary}</p>
            <p className="text-sm text-h-muted">Reloading the cutlist…</p>
          </div>
        )}
      </div>
    </div>
  );
}


function SummaryStrip({ preview }: { preview: CvPreviewOut }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border border-h-line bg-h-surface px-3 py-2 text-sm">
      <span><strong>{preview.summary.row_count}</strong> rows</span>
      <span className="text-green-700">{preview.summary.mapped} mapped</span>
      <span className="text-blue-700">{preview.summary.synonym} synonym</span>
      <span className="text-amber-700">{preview.summary.unknown} unknown</span>
      <span className="text-red-700">{preview.summary.invalid} invalid</span>
    </div>
  );
}


function totalImportableParts(
  preview: CvPreviewOut,
  resolutions: Record<string, CvCommitResolution>,
): number {
  const skipped = new Set(
    Object.values(resolutions)
      .filter((r) => r.action === "skip")
      .map((r) => r.cv_code),
  );
  let count = 0;
  for (const m of preview.modules) {
    for (const p of m.parts) {
      if (skipped.has(p.cv_code)) continue;
      count += 1;
    }
  }
  return count;
}

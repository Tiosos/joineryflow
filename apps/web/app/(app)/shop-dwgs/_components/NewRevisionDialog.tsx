"use client";

import { useState } from "react";

import { uploadFile } from "@/lib/file-upload";
import { addRevision } from "@/lib/shop-drawings-fetch";

interface Props {
  drawingId: number;
  onClose: () => void;
  onAdded: () => Promise<void>;
}

export default function NewRevisionDialog({ drawingId, onClose, onAdded }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!file) { setErr("Pick a file."); return; }
    setBusy(true); setErr(null);
    try {
      const blob = await uploadFile(file);
      await addRevision(drawingId, blob.file_blob_id);
      await onAdded();
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-5 shadow-xl">
        <h3 className="text-lg font-semibold text-h-ink">Upload new revision</h3>
        <p className="mt-1 text-xs text-h-muted">A new revision lands as Draft. Submit for review when ready.</p>
        <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
               className="mt-4 block w-full text-sm" />
        {err && <p className="mt-3 text-xs text-rose-700">{err}</p>}
        <div className="mt-5 flex items-center justify-end gap-2">
          <button onClick={onClose} className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {busy ? "Uploading…" : "Add revision"}
          </button>
        </div>
      </div>
    </div>
  );
}

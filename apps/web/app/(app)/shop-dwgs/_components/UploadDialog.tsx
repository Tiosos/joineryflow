"use client";

import { useState } from "react";

import { uploadFile } from "@/lib/file-upload";
import { createDrawing } from "@/lib/shop-drawings-fetch";

interface Props {
  projectId: number;
  onClose: () => void;
  onCreated: (drawingId: number) => void;
}

export default function UploadDialog({ projectId, onClose, onCreated }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [room, setRoom] = useState("");
  const [submitImmediately, setSubmitImmediately] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!file || !title.trim()) {
      setErr("File and title are required.");
      return;
    }
    setBusy(true); setErr(null);
    try {
      const blob = await uploadFile(file);
      const detail = await createDrawing({
        projectId,
        title: title.trim(),
        room: room.trim() || null,
        fileBlobId: blob.file_blob_id,
        submitImmediately,
      });
      onCreated(detail.drawing_id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-5 shadow-xl">
        <h3 className="text-lg font-semibold text-h-ink">Upload shop drawing</h3>
        <div className="mt-4 space-y-3">
          <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                 className="block w-full text-sm" />
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (required)"
                 className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink" />
          <input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="Room (optional, e.g. Kitchen)"
                 className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink" />
          <label className="flex items-center gap-2 text-sm text-h-ink">
            <input type="checkbox" checked={submitImmediately} onChange={(e) => setSubmitImmediately(e.target.checked)} />
            Submit for review immediately
          </label>
          {err && <p className="text-xs text-rose-700">{err}</p>}
        </div>
        <div className="mt-5 flex items-center justify-end gap-2">
          <button onClick={onClose} className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {busy ? "Uploading…" : "Create drawing"}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useRef, useState } from "react";

import {
  bindAttachment,
  clearAttachment,
} from "@/lib/attachments-fetch";
import type { AttachmentSlot } from "@/lib/attachments-types";
import { KIND_LABELS } from "@/lib/attachments-types";
import { uploadFile } from "@/lib/file-upload";

interface Props {
  itemId: number;
  slot: AttachmentSlot;
  canWrite: boolean;
  onChanged: () => Promise<void>;
}

function formatSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 102.4) / 10} KB`;
  return `${Math.round(bytes / (102.4 * 1024)) / 10} MB`;
}

function ddmmyyyy(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export default function AttachmentSlotCard({ itemId, slot, canWrite, onChanged }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const populated = slot.file_blob_id != null;

  const pickFile = () => {
    inputRef.current?.click();
  };

  const onFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const blob = await uploadFile(file);
      await bindAttachment(itemId, slot.kind, blob.file_blob_id);
      await onChanged();
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const onDelete = async () => {
    if (!confirm(`Remove the ${KIND_LABELS[slot.kind]} attachment? This action is logged.`)) return;
    setBusy(true);
    setErr(null);
    try {
      await clearAttachment(itemId, slot.kind);
      await onChanged();
    } catch (ex) {
      setErr(String(ex));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`rounded-lg border p-4 ${populated ? "border-h-line bg-h-surface" : "border-dashed border-h-line bg-h-surface/40"}`}>
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-h-ink">{KIND_LABELS[slot.kind]}</h3>
        <span className="text-xs text-h-muted">{populated ? "Populated" : "Empty"}</span>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <span className="text-2xl" aria-hidden>📄</span>
        {populated ? (
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-h-ink">{slot.original_filename}</p>
            <p className="mt-0.5 text-xs text-h-muted">
              {formatSize(slot.byte_size)} · {slot.uploaded_by_name ?? "—"} · {ddmmyyyy(slot.uploaded_at)}
            </p>
          </div>
        ) : (
          <p className="flex-1 text-sm text-h-muted">No file uploaded.</p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {populated && (
          <a
            href={`/api/files/${slot.file_blob_id}`}
            target="_blank"
            rel="noopener"
            className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40"
          >
            Open
          </a>
        )}
        {canWrite && (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={pickFile}
              className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {populated ? (busy ? "Replacing…" : "Replace") : (busy ? "Uploading…" : "Upload")}
            </button>
            {populated && (
              <button
                type="button"
                disabled={busy}
                onClick={onDelete}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-rose-700 hover:bg-h-line/40 disabled:opacity-50"
              >
                Delete
              </button>
            )}
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={onFileChosen}
          className="hidden"
        />
      </div>

      {err && <p className="mt-3 text-xs text-rose-700">{err}</p>}
    </div>
  );
}

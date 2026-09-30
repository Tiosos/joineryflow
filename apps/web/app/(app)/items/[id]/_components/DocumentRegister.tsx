"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  bindDocument,
  listDocuments,
  patchDocument,
  unbindDocument,
} from "@/lib/item-documents-fetch";
import { uploadFile } from "@/lib/file-upload";
import type { ItemDocumentOut } from "@/lib/pm-types";

import { lockFromError } from "./cutlist/moduleLock";

interface Props {
  itemId: number;
  /** `list:write` — drafter, manager, admin, editor. The API decides; this hides controls. */
  canWrite: boolean;
  /** Why a lock on the item refuses writes (from `moduleLockReason`), or null. */
  lockReason: string | null;
}

function formatSize(bytes: number | null): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 102.4) / 10} KB`;
  return `${Math.round(bytes / (102.4 * 1024)) / 10} MB`;
}

function ddmmyyyy(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export default function DocumentRegister({ itemId, canWrite, lockReason }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [docs, setDocs] = useState<ItemDocumentOut[] | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const locked = !!lockReason;

  const refresh = useCallback(async () => {
    setLoadErr(null);
    try {
      setDocs(await listDocuments(itemId));
    } catch (e) {
      setLoadErr(String(e));
    }
  }, [itemId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  /** Run one write; a lock refusal from a stale page shows the server's reason. */
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(lockFromError(e) ?? (e instanceof Error ? e.message : String(e)));
    } finally {
      await refresh();
      setBusy(false);
    }
  };

  const onFileChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Append: after the last existing document (ties at 0 are how a new item starts).
    const next = docs && docs.length ? Math.max(...docs.map((d) => d.sort_order)) + 1 : 0;
    await run(async () => {
      const blob = await uploadFile(file);
      await bindDocument(itemId, blob.file_blob_id, null, next);
    });
    if (inputRef.current) inputRef.current.value = "";
  };

  const rename = (doc: ItemDocumentOut, label: string) =>
    run(async () => {
      await patchDocument(doc.document_id, { label: label.trim() === "" ? null : label.trim() });
    });

  const remove = (doc: ItemDocumentOut) => {
    if (!confirm(`Remove "${doc.label || doc.original_filename || "this document"}" from the register? This action is logged.`)) return;
    return run(() => unbindDocument(doc.document_id));
  };

  /** Move one row by `delta`. Equal sort_orders are common (new documents default to 0),
   *  so the whole list is renumbered 0..n-1 and only rows whose number changed are patched. */
  const move = (index: number, delta: -1 | 1) => {
    if (!docs) return;
    const to = index + delta;
    if (to < 0 || to >= docs.length) return;
    const reordered = [...docs];
    [reordered[index], reordered[to]] = [reordered[to], reordered[index]];
    return run(async () => {
      for (let i = 0; i < reordered.length; i++) {
        if (reordered[i].sort_order !== i) {
          await patchDocument(reordered[i].document_id, { sort_order: i });
        }
      }
    });
  };

  return (
    <section className="space-y-3" data-testid="document-register">
      <header className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold text-h-ink">Document register</h2>
          <p className="mt-1 text-sm text-h-muted">
            {docs == null
              ? " "
              : `${docs.length} ${docs.length === 1 ? "document" : "documents"} · PDF, PNG or JPEG`}
          </p>
        </div>
        {canWrite && (
          <>
            <button
              type="button"
              disabled={busy || locked}
              title={lockReason ?? undefined}
              onClick={() => inputRef.current?.click()}
              className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {busy ? "Working…" : "Add document"}
            </button>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              onChange={onFileChosen}
              className="hidden"
            />
          </>
        )}
      </header>

      {loadErr && <p className="text-sm text-rose-700">{loadErr}</p>}
      {!docs && !loadErr && <p className="text-sm text-h-muted">Loading…</p>}
      {docs && docs.length === 0 && (
        <p className="rounded-lg border border-dashed border-h-line bg-h-surface/40 p-4 text-sm text-h-muted">
          No documents in the register.
        </p>
      )}

      {docs && docs.length > 0 && (
        <ul className="divide-y divide-h-line rounded-lg border border-h-line bg-h-surface">
          {docs.map((doc, i) => (
            <li key={doc.document_id} data-testid="register-row" className="flex items-center gap-3 p-3">
              <span className="text-xl" aria-hidden>📄</span>
              <div className="min-w-0 flex-1">
                {canWrite ? (
                  <LabelField
                    doc={doc}
                    disabled={busy || locked}
                    title={lockReason ?? undefined}
                    onCommit={(v) => rename(doc, v)}
                  />
                ) : (
                  <p className="truncate text-sm text-h-ink">{doc.label || doc.original_filename}</p>
                )}
                <p className="mt-0.5 truncate text-xs text-h-muted">
                  {doc.original_filename ?? "—"} · {formatSize(doc.byte_size)} ·{" "}
                  {doc.uploaded_by_name ?? "—"} · {ddmmyyyy(doc.uploaded_at)}
                </p>
              </div>
              <a
                href={`/api/files/${doc.file_blob_id}`}
                target="_blank"
                rel="noopener"
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40"
              >
                Open
              </a>
              {canWrite && (
                <>
                  <button
                    type="button"
                    aria-label="Move up"
                    disabled={busy || locked || i === 0}
                    title={lockReason ?? undefined}
                    onClick={() => move(i, -1)}
                    className="rounded border border-h-line px-2 py-1.5 text-sm text-h-ink hover:bg-h-line/40 disabled:opacity-50"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label="Move down"
                    disabled={busy || locked || i === docs.length - 1}
                    title={lockReason ?? undefined}
                    onClick={() => move(i, 1)}
                    className="rounded border border-h-line px-2 py-1.5 text-sm text-h-ink hover:bg-h-line/40 disabled:opacity-50"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    disabled={busy || locked}
                    title={lockReason ?? undefined}
                    onClick={() => remove(doc)}
                    className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-rose-700 hover:bg-h-line/40 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {err && <p className="text-xs text-rose-700" data-testid="register-error">{err}</p>}
    </section>
  );
}

/** Commit-on-blur label. Resyncs to the server's value, and skips an unchanged blur
 *  (a bare tab-through must not write an audit row). */
function LabelField({
  doc,
  disabled,
  title,
  onCommit,
}: {
  doc: ItemDocumentOut;
  disabled: boolean;
  title?: string;
  onCommit: (label: string) => Promise<void> | undefined;
}) {
  const server = doc.label ?? "";
  const [value, setValue] = useState(server);
  const latest = useRef(server);
  latest.current = server;
  useEffect(() => setValue(server), [server]);
  return (
    <input
      value={value}
      disabled={disabled}
      title={title}
      placeholder={doc.original_filename ?? "Label"}
      maxLength={128}
      aria-label="Document label"
      onChange={(e) => setValue(e.target.value)}
      onBlur={async () => {
        if (value.trim() !== server) await onCommit(value);
        // a refused save leaves the server's label unchanged: show it, not the rejected text
        setValue(latest.current);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
      className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm text-h-ink hover:border-h-line focus:border-h-line disabled:opacity-60"
    />
  );
}

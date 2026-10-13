"use client";

import { useCallback, useEffect, useState } from "react";

type Attachment = {
  attachment_id: number;
  attachment_type: "File" | "PDF";
  file_name: string;
  file_size_bytes: number | null;
  uploaded_by_name: string | null;
};

const BOXES = [
  { type: "File", label: "FILE", accept: ".pdf,.png,.jpg,.jpeg,.skp,.cvj" },
  { type: "PDF", label: "PDF", accept: ".pdf,application/pdf" },
] as const;

/**
 * The order pop-up's FILE and PDF boxes: supporting files on this order (`/orders/{id}/attachments`,
 * `orderbook:write` to change). Both take what the shared file store takes (PDF, PNG, JPEG, .skp,
 * .cvj, 25 MB); the PDF box takes PDF only. A Cancelled / Delivered order's files can be opened
 * but not changed.
 */
export function OrderAttachments({
  poId, canEdit, locked, onChanged,
}: { poId: number; canEdit: boolean; locked: boolean; onChanged: () => void }) {
  const [rows, setRows] = useState<Attachment[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `/api/orders/${poId}/attachments`;
  const editable = canEdit && !locked;

  const load = useCallback(() => {
    fetch(base, { cache: "no-store" })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((b: { attachments: Attachment[] }) => setRows(b.attachments))
      .catch(e => setErr(`Could not load the files: ${e}`));
  }, [base]);
  useEffect(() => { load(); }, [load]);

  async function call(req: Promise<Response>) {
    setErr(null); setBusy(true);
    const res = await req.catch(() => null);
    setBusy(false);
    if (!res || !res.ok) {
      const body = res ? await res.json().catch(() => null) : null;
      const msg = res?.status === 413 ? "That file is over 25 MB"
        : res?.status === 415 ? "That type of file is not allowed here (PDF, PNG, JPEG, SketchUp, Cabinet Vision; the PDF box takes a PDF)"
        : body?.detail?.code === "ORDER_LOCKED" ? "This order is closed: its files cannot change"
        : "Could not save the file";
      setErr(msg);
      return;
    }
    setRows(((await res.json()) as { attachments: Attachment[] }).attachments);
    onChanged();
  }

  function upload(type: string, file: File | undefined) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("attachment_type", type);
    void call(fetch(base, { method: "POST", body: fd }));
  }

  return (
    <div data-testid="order-attachments" className="grid gap-1.5">
      <div className="grid grid-cols-2 gap-3">
        {BOXES.map(b => (
          <div key={b.type} data-testid={`order-attachments-${b.type}`} className="grid content-start gap-1 rounded border border-dashed border-h-line p-2 text-h-muted">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-h-ink">{b.label}</div>
            {rows.filter(r => r.attachment_type === b.type).map(r => (
              <div key={r.attachment_id} data-testid="order-attachment" className="flex items-center gap-1">
                <a href={`${base}/${r.attachment_id}/download`} target="_blank" rel="noreferrer"
                  className="min-w-0 flex-1 truncate text-h-accent hover:underline" title={r.uploaded_by_name ? `Added by ${r.uploaded_by_name}` : undefined}>
                  {r.file_name}
                </a>
                {editable && (
                  <button type="button" aria-label={`Remove ${r.file_name}`} data-testid="order-attachment-remove" disabled={busy}
                    onClick={() => void call(fetch(`${base}/${r.attachment_id}`, { method: "DELETE" }))}
                    className="rounded border border-h-line bg-h-bg px-1.5 text-h-muted hover:text-h-ink">−</button>
                )}
              </div>
            ))}
            {rows.every(r => r.attachment_type !== b.type) && <div>None</div>}
            {editable && (
              <label className="w-fit cursor-pointer rounded border border-h-line bg-h-bg px-2 py-0.5 text-h-ink hover:bg-h-surface">
                {busy ? "Uploading…" : "+ Add"}
                <input type="file" accept={b.accept} className="sr-only" data-testid={`order-attachment-input-${b.type}`} disabled={busy}
                  onChange={e => { upload(b.type, e.target.files?.[0]); e.target.value = ""; }} />
              </label>
            )}
          </div>
        ))}
      </div>
      {err && <p role="alert" data-testid="order-attachment-error" className="text-[#b4443d]">{err}</p>}
    </div>
  );
}

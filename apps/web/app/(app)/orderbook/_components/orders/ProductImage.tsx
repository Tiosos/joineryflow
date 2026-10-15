"use client";

import { useState } from "react";

/** The old pop-up's Product image box: one PNG or JPEG per order, kept in the shared file store. */
export function ProductImage({
  poId, hasImage, canEdit, onChanged,
}: { poId: number; hasImage: boolean; canEdit: boolean; onChanged: () => void }) {
  const [version, setVersion] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const url = `/api/orders/${poId}/image?v=${version}`;

  async function upload(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(`/api/orders/${poId}/image`, { method: "PUT", body: fd }).catch(() => null);
    if (!r || !r.ok) { setErr(r?.status === 415 ? "A picture must be a PNG or JPEG" : r?.status === 409 ? "This order is closed" : "Could not save the picture"); return; }
    setErr(null); setVersion(v => v + 1); onChanged();
  }
  async function remove() {
    const r = await fetch(`/api/orders/${poId}/image`, { method: "DELETE" }).catch(() => null);
    if (!r || !r.ok) { setErr("Could not remove the picture"); return; }
    setErr(null); setVersion(v => v + 1); onChanged();
  }

  return (
    <div data-testid="order-image-box" className="grid gap-1">
      <div className="flex h-28 items-center justify-center overflow-hidden rounded border border-h-line bg-h-bg text-h-muted">
        {hasImage
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={url} alt="Product" data-testid="order-image" className="max-h-full max-w-full object-contain" />
          : canEdit
            ? <label className="cursor-pointer px-2 text-center hover:text-h-ink">+ Product image
                <input type="file" accept="image/png,image/jpeg" className="sr-only" data-testid="order-image-file" aria-label="Product image"
                  onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} /></label>
            : <span>Product image</span>}
      </div>
      {hasImage && canEdit && <button type="button" onClick={() => void remove()} data-testid="order-image-remove" className="text-[10px] text-h-muted underline hover:text-h-ink">remove</button>}
      {err && <p role="alert" className="text-[#b4443d]">{err}</p>}
    </div>
  );
}

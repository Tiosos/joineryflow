"use client";

import { useState } from "react";

/** A board's one picture (PNG or JPEG, shared file store): thumbnail, replace, remove. */
export default function BoardImageCell({
  mid, hasImage, canWrite, onChanged,
}: { mid: number; hasImage: boolean; canWrite: boolean; onChanged: () => void }) {
  const [version, setVersion] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const url = `/api/catalog/board-materials/${mid}/image`;

  async function upload(file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(url, { method: "PUT", body: fd }).catch(() => null);
    if (!r || !r.ok) { setErr(r?.status === 415 ? "PNG or JPEG only" : "Could not save"); return; }
    setErr(null); setVersion((v) => v + 1); onChanged();
  }
  async function remove() {
    const r = await fetch(url, { method: "DELETE" }).catch(() => null);
    if (!r || !r.ok) { setErr("Could not remove"); return; }
    setErr(null); setVersion((v) => v + 1); onChanged();
  }

  return (
    <div className="flex items-center gap-2">
      {hasImage && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={`${url}?v=${version}`} alt="Board" data-testid="board-image" className="h-8 w-8 rounded object-cover" />
      )}
      {canWrite && (
        <label className="cursor-pointer text-xs text-h-muted underline hover:text-h-ink">
          {hasImage ? "replace" : "+ image"}
          <input type="file" accept="image/png,image/jpeg" className="sr-only" aria-label="Board image"
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
        </label>
      )}
      {hasImage && canWrite && (
        <button type="button" onClick={() => void remove()} className="text-xs text-h-muted underline hover:text-h-ink">remove</button>
      )}
      {err && <span role="alert" className="text-xs text-rose-700">{err}</span>}
    </div>
  );
}

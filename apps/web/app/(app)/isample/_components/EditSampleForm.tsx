"use client";

import { useState } from "react";

import { patchSample } from "@/lib/samples-fetch";
import type { Sample } from "@/lib/samples-types";

interface Props {
  sample: Sample;
  onSaved: () => Promise<void>;
  onCancel: () => void;
}

export default function EditSampleForm({ sample, onSaved, onCancel }: Props) {
  const [title, setTitle] = useState(sample.title);
  const [room, setRoom] = useState(sample.room ?? "");
  const [hex, setHex] = useState(sample.hex_swatch);
  const [supplier, setSupplier] = useState(sample.supplier ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await patchSample(sample.sample_id, {
        title: title.trim() !== sample.title ? title.trim() : undefined,
        room: (room || null) !== sample.room ? (room || null) : undefined,
        hex_swatch: hex !== sample.hex_swatch ? hex : undefined,
        supplier: (supplier || null) !== sample.supplier ? (supplier || null) : undefined,
      });
      await onSaved();
      onCancel();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 rounded-md border border-h-line bg-h-surface p-3">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        className="block w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
      />
      <input
        value={room}
        onChange={(e) => setRoom(e.target.value)}
        placeholder="Room"
        className="block w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
      />
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={hex}
          onChange={(e) => setHex(e.target.value)}
          className="h-9 w-12 cursor-pointer rounded border border-h-line"
        />
        <input
          value={hex}
          onChange={(e) => setHex(e.target.value)}
          placeholder="#aabbcc"
          className="block w-32 rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink h-mono"
        />
      </div>
      <input
        value={supplier}
        onChange={(e) => setSupplier(e.target.value)}
        placeholder="Supplier"
        className="block w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
      />
      {err && <p className="text-xs text-rose-700">{err}</p>}
      <div className="flex items-center gap-2">
        <button type="button" disabled={busy} onClick={submit}
                className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onCancel}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">
          Cancel
        </button>
      </div>
    </div>
  );
}

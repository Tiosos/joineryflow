"use client";

import { useState } from "react";

import { uploadFile } from "@/lib/file-upload";
import { createSample } from "@/lib/samples-fetch";

interface Project { id: number; project_code: string; name: string; }

interface Props {
  projects: Project[];
  defaultProjectId: number | null;
  onClose: () => void;
  onCreated: (sampleId: number) => void;
}

export default function NewSampleDialog(p: Props) {
  const [projectId, setProjectId] = useState<number | null>(p.defaultProjectId);
  const [title, setTitle] = useState("");
  const [room, setRoom] = useState("");
  const [hex, setHex] = useState("#cccccc");
  const [supplier, setSupplier] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (projectId == null || !title.trim()) {
      setErr("Project and title are required.");
      return;
    }
    setBusy(true); setErr(null);
    try {
      let photoBlobId: number | null = null;
      if (photo) {
        const blob = await uploadFile(photo);
        photoBlobId = blob.file_blob_id;
      }
      const sample = await createSample({
        projectId, title: title.trim(),
        room: room.trim() || null, hex_swatch: hex,
        supplier: supplier.trim() || null,
        photo_file_blob_id: photoBlobId,
      });
      p.onCreated(sample.sample_id);
    } catch (e) {
      setErr(String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30" onClick={p.onClose}>
      <div onClick={(e) => e.stopPropagation()} className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-5 shadow-xl">
        <h3 className="text-lg font-semibold text-h-ink">New sample</h3>
        <div className="mt-4 space-y-3">
          <select
            value={projectId ?? ""}
            onChange={(e) => setProjectId(Number(e.target.value))}
            className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
          >
            {p.projects.map((proj) => (
              <option key={proj.id} value={proj.id}>{proj.project_code} · {proj.name}</option>
            ))}
          </select>
          <input
            value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (required)"
            className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
          />
          <input
            value={room} onChange={(e) => setRoom(e.target.value)}
            placeholder="Room (optional, e.g. L3 / Reception)"
            className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
          />
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={hex}
              onChange={(e) => setHex(e.target.value)}
              className="h-10 w-14 cursor-pointer rounded border border-h-line"
            />
            <input
              value={hex} onChange={(e) => setHex(e.target.value)}
              placeholder="#aabbcc"
              className="block w-32 rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink h-mono"
            />
            <span className="text-xs text-h-muted">Hex swatch</span>
          </div>
          <input
            value={supplier} onChange={(e) => setSupplier(e.target.value)}
            placeholder="Supplier (optional)"
            className="block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
          />
          <div>
            <label className="text-xs text-h-muted">Photo (optional, PNG/JPEG):</label>
            <input
              type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg"
              onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm"
            />
          </div>
          {err && <p className="text-xs text-rose-700">{err}</p>}
        </div>
        <div className="mt-5 flex items-center justify-end gap-2">
          <button onClick={p.onClose} className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {busy ? "Creating…" : "Create sample"}
          </button>
        </div>
      </div>
    </div>
  );
}

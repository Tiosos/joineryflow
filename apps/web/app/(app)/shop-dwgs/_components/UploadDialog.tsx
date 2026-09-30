"use client";

import { useState } from "react";

import type { Mentionable } from "@/lib/comments-types";
import { uploadFile } from "@/lib/file-upload";
import { createDrawing } from "@/lib/shop-drawings-fetch";
import type { DrawingType } from "@/lib/shop-drawings-types";

interface Props {
  projectId: number;
  roster: Mentionable[];
  onClose: () => void;
  onCreated: (drawingId: number) => void;
}

const field =
  "block w-full rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink";

export default function UploadDialog({ projectId, roster, onClose, onCreated }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [room, setRoom] = useState("");
  const [type, setType] = useState<DrawingType>("IFA");
  const [level, setLevel] = useState("");
  const [joineryId, setJoineryId] = useState("");
  const [zone, setZone] = useState("");
  const [roomNo, setRoomNo] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [dueDate, setDueDate] = useState("");
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
        register: {
          type,
          level: level.trim() || null,
          joinery_id: joineryId.trim() || null,
          zone: zone.trim() || null,
          room_no: roomNo.trim() || null,
          assigned_to: assignedTo ? Number(assignedTo) : null,
          due_date: dueDate || null,
        },
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
      <div onClick={(e) => e.stopPropagation()} className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-h-line bg-h-bg p-5 shadow-xl">
        <h3 className="text-lg font-semibold text-h-ink">Upload shop drawing</h3>
        <p className="mt-1 text-xs text-h-muted">The register number is assigned automatically.</p>
        <div className="mt-4 space-y-3">
          <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                 className="block w-full text-sm" />
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (required)" className={field} />
          <div className="grid grid-cols-2 gap-3">
            <input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="Room (optional, e.g. Kitchen)" className={field} />
            <select aria-label="Type" value={type} onChange={(e) => setType(e.target.value as DrawingType)} className={field}>
              <option value="IFA">IFA — issued for approval</option>
              <option value="IFC">IFC — issued for construction</option>
            </select>
          </div>
          <div className="grid grid-cols-4 gap-3">
            <input value={level} onChange={(e) => setLevel(e.target.value)} placeholder="Level" className={field} />
            <input value={joineryId} onChange={(e) => setJoineryId(e.target.value)} placeholder="Joinery ID" className={field} />
            <input value={zone} onChange={(e) => setZone(e.target.value)} placeholder="Zone" className={field} />
            <input value={roomNo} onChange={(e) => setRoomNo(e.target.value)} placeholder="Rm no." className={field} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <select aria-label="Assigned to" value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className={field}>
              <option value="">Unassigned</option>
              {roster.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
            </select>
            <input type="date" aria-label="Due date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className={field} />
          </div>
          <label className="flex items-center gap-2 text-sm text-h-ink">
            <input type="checkbox" checked={submitImmediately} onChange={(e) => setSubmitImmediately(e.target.checked)} />
            Submit for review immediately
          </label>
          {err && <p className="text-xs text-h-bad">{err}</p>}
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

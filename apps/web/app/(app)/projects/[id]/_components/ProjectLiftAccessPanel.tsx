"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ProjectLiftAccessOut } from "@/lib/pm-types";
import { liftAccessApi } from "@/lib/project-lift-access-fetch";
import { uploadFile } from "@/lib/file-upload";

interface Props {
  projectId: number;
  liftAccess: ProjectLiftAccessOut | null;
  /** tracking:write — {editor, drafter, manager, admin}. */
  canEdit: boolean;
}

export function ProjectLiftAccessPanel({ projectId, liftAccess, canEdit }: Props) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [notes, setNotes] = useState(liftAccess?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sketchId = liftAccess?.sketch_file_blob_id ?? null;

  // PUT is a full overwrite — always send the current notes value alongside
  // whichever field is actually changing (see project-lift-access-fetch.ts).
  async function save(nextNotes: string, nextSketchId: number | null) {
    setBusy(true);
    setError(null);
    try {
      await liftAccessApi.upsert(projectId, { notes: nextNotes || null, sketch_file_blob_id: nextSketchId });
      router.refresh();
    } catch {
      setError("Failed to save");
    } finally {
      setBusy(false);
    }
  }

  async function onNotesBlur() {
    if (notes === (liftAccess?.notes ?? "")) return;
    await save(notes, sketchId);
  }

  async function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const blob = await uploadFile(file);
      await save(notes, blob.file_blob_id);
    } catch {
      setError("Upload failed");
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function removeSketch() {
    if (!confirm("Remove the lift access sketch?")) return;
    await save(notes, null);
  }

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Lift &amp; Access</h2>

      <label className="mb-1 block text-xs text-h-muted">Notes</label>
      <textarea
        value={notes}
        disabled={!canEdit}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={onNotesBlur}
        rows={4}
        className="w-full resize-y rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink disabled:opacity-60"
      />

      <div className="mt-3 flex items-center gap-2">
        {sketchId != null ? (
          <>
            <a
              href={`/api/files/${sketchId}`}
              target="_blank"
              rel="noopener"
              className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40"
            >
              Open sketch
            </a>
            {canEdit && (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => inputRef.current?.click()}
                  className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink hover:bg-h-line/40 disabled:opacity-50"
                >
                  Replace
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={removeSketch}
                  className="rounded border border-h-line px-3 py-1.5 text-sm text-rose-700 hover:bg-h-line/40 disabled:opacity-50"
                >
                  Remove
                </button>
              </>
            )}
          </>
        ) : (
          canEdit && (
            <button
              type="button"
              disabled={busy}
              onClick={() => inputRef.current?.click()}
              className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              {busy ? "Uploading…" : "Upload sketch"}
            </button>
          )
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf,.png,image/png,.jpg,.jpeg,image/jpeg"
          onChange={onFileChosen}
          className="hidden"
        />
      </div>

      {error && <p className="mt-2 text-xs text-rose-700">{error}</p>}
    </section>
  );
}

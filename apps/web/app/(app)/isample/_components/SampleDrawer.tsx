"use client";

import { useEffect, useState } from "react";

import { clearSamplePhoto, getSample } from "@/lib/samples-fetch";
import type { Sample } from "@/lib/samples-types";

import EditSampleForm from "./EditSampleForm";
import ReviewActions from "./ReviewActions";
import SampleIdChip from "./SampleIdChip";
import SampleStatusPill from "./SampleStatusPill";
import SampleSwatch from "./SampleSwatch";

interface Me { id: number; auth_role: string; }

interface Props {
  sampleId: number;
  me: Me;
  onClose: () => void;
  onChanged: () => void;
  onUploadPhotoClick: () => void;
}

function ddmmyyyy(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

export default function SampleDrawer(props: Props) {
  const [sample, setSample] = useState<Sample | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const refresh = async () => {
    setError(null);
    try {
      setSample(await getSample(props.sampleId));
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => { refresh(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [props.sampleId]);

  const handleClearPhoto = async () => {
    await clearSamplePhoto(props.sampleId);
  };

  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[640px] flex-col overflow-y-auto border-l border-h-line bg-h-bg shadow-lg">
      <header className="flex items-start justify-between gap-3 border-b border-h-line p-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <SampleIdChip sampleId={props.sampleId} />
            {sample && <SampleStatusPill status={sample.status} archived={sample.archived_at != null} />}
          </div>
          <h2 className="mt-2 truncate text-lg font-semibold text-h-ink">{sample?.title ?? "Loading…"}</h2>
          {sample && (
            <p className="text-sm text-h-muted">
              {sample.project_code}{sample.room ? ` · ${sample.room}` : ""}
            </p>
          )}
        </div>
        <button onClick={props.onClose} aria-label="Close drawer"
                className="rounded p-1 text-h-muted hover:bg-h-line/40 hover:text-h-ink">
          ✕
        </button>
      </header>

      {error && <p className="p-4 text-sm text-rose-700">{error}</p>}

      {sample && (
        <div className="space-y-4 p-4">
          {/* Large swatch / photo */}
          <div className="aspect-square max-h-[520px] w-full overflow-hidden rounded-md border border-h-line">
            <SampleSwatch hexSwatch={sample.hex_swatch} photoFileBlobId={sample.photo_file_blob_id} />
          </div>

          {/* Metadata */}
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between"><dt className="text-h-muted">Hex</dt><dd className="h-mono text-h-ink">{sample.hex_swatch}</dd></div>
            {sample.supplier && <div className="flex justify-between"><dt className="text-h-muted">Supplier</dt><dd className="text-h-ink">{sample.supplier}</dd></div>}
            <div className="flex justify-between"><dt className="text-h-muted">Created by</dt><dd className="text-h-ink">{sample.created_by_name ?? "—"} · {ddmmyyyy(sample.created_at)}</dd></div>
            {sample.reviewed_by && (
              <div className="flex justify-between"><dt className="text-h-muted">Reviewed by</dt><dd className="text-h-ink">{sample.reviewed_by_name ?? "—"} · {ddmmyyyy(sample.reviewed_at)}</dd></div>
            )}
            {sample.review_note && (
              <div className="rounded bg-h-line/20 p-2 text-h-ink">
                <span className="text-xs text-h-muted">Note: </span>{sample.review_note}
              </div>
            )}
            {sample.archived_at && (
              <div className="flex justify-between"><dt className="text-h-muted">Archived</dt><dd className="text-h-ink">{ddmmyyyy(sample.archived_at)}</dd></div>
            )}
          </dl>

          {editing ? (
            <EditSampleForm sample={sample} onSaved={async () => { await refresh(); props.onChanged(); }} onCancel={() => setEditing(false)} />
          ) : (
            <ReviewActions
              sample={sample}
              me={props.me}
              onAfter={async () => { await refresh(); props.onChanged(); }}
              onEditClick={() => setEditing(true)}
              onUploadPhotoClick={props.onUploadPhotoClick}
              onClearPhotoClick={handleClearPhoto}
            />
          )}
        </div>
      )}
    </aside>
  );
}

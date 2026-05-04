"use client";

import type { Sample } from "@/lib/samples-types";

import SampleIdChip from "./SampleIdChip";
import SampleStatusPill from "./SampleStatusPill";
import SampleSwatch from "./SampleSwatch";

function ddmmyyyy(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

function truncate(text: string | null, max: number): string {
  if (!text) return "";
  if (text.length <= max) return text;
  return text.slice(0, max - 1) + "…";
}

interface Props { sample: Sample; onClick: () => void; }

export default function SampleCard({ sample, onClick }: Props) {
  const archived = sample.archived_at != null;
  const decisionText = sample.review_note
    ? truncate(sample.review_note, 30)
    : `${sample.created_by_name ?? "—"} · ${ddmmyyyy(sample.created_at)}`;
  const decisionPerson = sample.reviewed_by_name ?? sample.created_by_name ?? "—";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Open sample ${sample.title}`}
      className="group block w-full overflow-hidden rounded-lg border border-h-line bg-h-surface text-left transition hover:border-h-accent/60 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-h-accent"
    >
      <div className="relative aspect-square">
        <SampleSwatch hexSwatch={sample.hex_swatch} photoFileBlobId={sample.photo_file_blob_id} />
        <div className="absolute left-2 top-2"><SampleStatusPill status={sample.status} archived={archived} /></div>
        <div className="absolute right-2 top-2"><SampleIdChip sampleId={sample.sample_id} /></div>
      </div>
      <div className="space-y-1 p-3">
        <div className="truncate text-sm font-semibold text-h-ink">{sample.title}</div>
        <p className="truncate text-xs text-h-muted">
          {sample.project_code}{sample.room ? ` · ${sample.room}` : ""}
        </p>
        <p className="h-mono truncate text-xs text-h-muted">
          {decisionPerson} · {decisionText}
        </p>
      </div>
    </button>
  );
}

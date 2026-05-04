"use client";

import { useEffect, useState } from "react";

import { listLedger } from "@/lib/samples-fetch";
import type { LedgerEntry, LedgerResp } from "@/lib/samples-types";

interface Props {
  projectId: number;
  onSampleClick: (sampleId: number) => void;
}

const PAGE_SIZE = 50;

function ts(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, "0");
  const mn = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm}/${yyyy} ${hh}:${mn}`;
}

function humanize(entry: LedgerEntry): string {
  const sid = `#SAM-${String(entry.sample_id).padStart(4, "0")}`;
  switch (entry.event) {
    case "sample.create":
      return `Created sample ${sid}${entry.payload?.title ? ` (${entry.payload.title})` : ""}`;
    case "sample.update":
      return `Updated sample ${sid} — ${entry.payload?.field ?? ""}`;
    case "sample.approve":
      return `Approved sample ${sid}${entry.payload?.review_note ? ` — “${entry.payload.review_note}”` : ""}`;
    case "sample.reject":
      return `Rejected sample ${sid} — “${entry.payload?.review_note ?? ""}”`;
    case "sample.archive":
      return `Archived sample ${sid}`;
    case "sample.upload_photo":
      return entry.payload?.replaced_file_blob_id
        ? `Replaced photo for sample ${sid}`
        : `Uploaded photo for sample ${sid}`;
    case "sample.clear_photo":
      return `Cleared photo for sample ${sid}`;
    default:
      return `${entry.event} on sample ${sid}`;
  }
}

export default function ApprovalLedger({ projectId, onSampleClick }: Props) {
  const [resp, setResp] = useState<LedgerResp | null>(null);
  const [page, setPage] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    listLedger(projectId, PAGE_SIZE, page * PAGE_SIZE)
      .then(setResp)
      .catch((e) => setError(String(e)));
  }, [projectId, page]);

  if (error) return <p className="text-sm text-rose-700">{error}</p>;
  if (!resp) return <p className="text-sm text-h-muted">Loading ledger…</p>;

  const totalPages = Math.max(1, Math.ceil(resp.total / PAGE_SIZE));

  return (
    <div className="space-y-3">
      <p className="text-sm text-h-muted">{resp.total} ledger entries · page {page + 1} of {totalPages}</p>
      <ol className="divide-y divide-h-line border border-h-line rounded-md">
        {resp.entries.map((e) => (
          <li key={e.id} className="flex items-baseline gap-3 px-3 py-2 text-sm">
            <span className="h-mono shrink-0 text-xs text-h-muted">{ts(e.created_at)}</span>
            <span className="shrink-0 text-h-ink">{e.actor_name ?? "—"}</span>
            <button
              type="button"
              onClick={() => onSampleClick(e.sample_id)}
              className="flex-1 truncate text-left text-h-ink hover:text-h-accent"
            >
              {humanize(e)}
            </button>
          </li>
        ))}
        {resp.entries.length === 0 && <li className="px-3 py-4 text-sm text-h-muted">No ledger entries.</li>}
      </ol>
      <div className="flex items-center justify-end gap-2">
        <button type="button" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm disabled:opacity-50">
          Previous
        </button>
        <button type="button" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)}
                className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm disabled:opacity-50">
          Next
        </button>
      </div>
    </div>
  );
}

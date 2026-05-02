"use client";

import { useEffect, useMemo, useState } from "react";

import type { DrawingDetail } from "@/lib/shop-drawings-types";
import { getDrawing } from "@/lib/shop-drawings-fetch";

import RevisionHistoryStrip from "./RevisionHistoryStrip";
import StatusPill from "./StatusPill";

interface Me {
  id: number;
  auth_role: string;
}

interface Props {
  drawingId: number;
  initialRevId: number | null;
  me: Me;
  onClose: () => void;
  onChanged: () => void;
  onSelectRevision: (revId: number) => void;
  renderActions: (
    detail: DrawingDetail,
    selectedRevId: number,
    refresh: () => Promise<void>,
  ) => React.ReactNode;
}

export default function DrawingDrawer(props: Props) {
  const [detail, setDetail] = useState<DrawingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const d = await getDrawing(props.drawingId);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.drawingId]);

  const selectedRevId = useMemo(() => {
    if (!detail) return 0;
    if (
      props.initialRevId &&
      detail.revisions.some((r) => r.revision_id === props.initialRevId)
    ) {
      return props.initialRevId;
    }
    return detail.revisions[0]?.revision_id ?? 0;
  }, [detail, props.initialRevId]);

  const selectedRev = detail?.revisions.find((r) => r.revision_id === selectedRevId);

  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[640px] flex-col border-l border-h-line bg-h-bg shadow-lg">
      <header className="flex items-start justify-between gap-3 border-b border-h-line p-4">
        <div className="min-w-0">
          <p className="h-mono text-xs text-h-muted">
            #SD-{String(props.drawingId).padStart(4, "0")} · {detail?.project_code ?? "…"}
          </p>
          <h2 className="truncate text-lg font-semibold text-h-ink">
            {detail?.title ?? "Loading…"}
          </h2>
          {detail?.room && <p className="text-sm text-h-muted">{detail.room}</p>}
        </div>
        <button
          onClick={props.onClose}
          className="rounded p-1 text-h-muted hover:bg-h-line/40 hover:text-h-ink"
          aria-label="Close drawer"
        >
          ✕
        </button>
      </header>

      {error && <p className="p-4 text-sm text-red-600">{error}</p>}

      {selectedRev && (
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 overflow-hidden border-b border-h-line bg-h-line/20">
            {selectedRev.file_mime === "application/pdf" ? (
              <iframe
                title={`drawing ${props.drawingId} rev ${selectedRev.rev_no}`}
                src={`/api/files/${selectedRev.file_blob_id}#zoom=fit`}
                className="h-full w-full"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/api/files/${selectedRev.file_blob_id}`}
                  alt={`drawing ${props.drawingId} rev ${selectedRev.rev_no}`}
                  className="max-h-full max-w-full"
                />
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 px-3 py-2">
            <span className="text-sm text-h-ink">v{selectedRev.rev_no}</span>
            <StatusPill status={selectedRev.status} />
            {selectedRev.review_note && (
              <span className="truncate text-xs text-h-muted">
                Note: {selectedRev.review_note}
              </span>
            )}
            <a
              href={`/api/files/${selectedRev.file_blob_id}`}
              download
              className="ml-auto text-xs text-h-accent hover:underline"
            >
              Download
            </a>
          </div>

          {detail && (
            <RevisionHistoryStrip
              revisions={detail.revisions}
              selectedId={selectedRevId}
              onSelect={props.onSelectRevision}
            />
          )}

          {detail && (
            <footer className="flex flex-wrap items-center gap-2 p-3">
              {props.renderActions(detail, selectedRevId, async () => {
                await refresh();
                props.onChanged();
              })}
            </footer>
          )}
        </div>
      )}
    </aside>
  );
}

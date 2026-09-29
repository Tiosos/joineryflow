"use client";

import { useCallback, useEffect, useState } from "react";

import { CommentThread } from "@/components/comments/CommentThread";
import { can } from "@/lib/permissions";
import type { DrawingDetail } from "@/lib/shop-drawings-types";
import { getDrawing } from "@/lib/shop-drawings-fetch";
import type { Me } from "@/lib/session";

import RevisionHistoryStrip from "./RevisionHistoryStrip";
import StatusPill from "./StatusPill";

interface Props {
  drawingId: number;
  initialRevId: number | null;
  /** Open the selected revision's comment thread on arrival — a notification
   *  for a revision comment links here with `?comments=1`. */
  commentsOpen?: boolean;
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
  const [selectedRevId, setSelectedRevId] = useState<number>(props.initialRevId ?? 0);
  const [commentsOpen, setCommentsOpen] = useState(props.commentsOpen ?? false);

  // The URL named a revision (a notification followed while this drawer is
  // already open, back/forward): follow it. After a click of ours the URL
  // catches up to what is already selected, so this changes nothing.
  useEffect(() => {
    if (props.initialRevId) setSelectedRevId(props.initialRevId);
  }, [props.initialRevId]);
  useEffect(() => {
    if (props.commentsOpen) setCommentsOpen(true);
  }, [props.commentsOpen, props.initialRevId]);

  const refresh = useCallback(async () => {
    try {
      const d = await getDrawing(props.drawingId);
      setDetail(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [props.drawingId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // When detail loads, snap selectedRevId to a valid revision if the current one doesn't match.
  useEffect(() => {
    if (!detail) return;
    if (selectedRevId && detail.revisions.some((r) => r.revision_id === selectedRevId)) return;
    const fallback = detail.revisions[0]?.revision_id ?? 0;
    if (fallback) setSelectedRevId(fallback);
  }, [detail, selectedRevId]);

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
              onSelect={(rev) => { setSelectedRevId(rev); props.onSelectRevision(rev); }}
            />
          )}

          <section data-testid="revision-comments" className="border-t border-h-line">
            <button
              type="button"
              onClick={() => setCommentsOpen((o) => !o)}
              aria-expanded={commentsOpen}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium text-h-ink hover:bg-h-surface"
            >
              <span>Comments on v{selectedRev.rev_no}</span>
              <span aria-hidden className="text-h-muted">{commentsOpen ? "▾" : "▸"}</span>
            </button>
            {commentsOpen && (
              <div className="max-h-72 overflow-y-auto border-t border-h-line p-3">
                <CommentThread
                  key={selectedRev.revision_id}
                  objectType="revision"
                  objectId={selectedRev.revision_id}
                  currentUserId={props.me.id}
                  currentUserRole={props.me.auth_role}
                  canComment={can(props.me, "shop_dwgs", "comment")}
                />
              </div>
            )}
          </section>

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

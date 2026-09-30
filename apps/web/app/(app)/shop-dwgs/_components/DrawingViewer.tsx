"use client";

import { useCallback, useEffect, useState } from "react";

import { CommentThread } from "@/components/comments/CommentThread";
import type { Mentionable } from "@/lib/comments-types";
import { can } from "@/lib/permissions";
import type { Me } from "@/lib/session";
import { getDrawing } from "@/lib/shop-drawings-fetch";
import type { DrawingDetail } from "@/lib/shop-drawings-types";

import { queueOfDetail } from "./DetailsPanel";
import QueueChip from "./QueueChip";
import { fmtDate } from "./RegisterTable";
import ReviewActions from "./ReviewActions";
import StatusPill from "./StatusPill";
import ThumbnailStrip from "./ThumbnailStrip";

interface Props {
  drawingId: number;
  initialRevId: number | null;
  me: Me;
  roster: Mentionable[];
  onClose: () => void;
  onChanged: () => void;
  onSelectRevision: (revId: number) => void;
}

const ZOOMS = [50, 75, 100, 125, 150, 200, 300];

/** Full-screen drawing viewer: the drawing on the left, and everything about
 *  it — versions, communication, key facts, review actions — on the right.
 *
 *  The drawing is the browser's own PDF viewer (zoom via `#zoom=`, paging via
 *  `#page=`) or, for images, CSS scaling. The thumbnail strip is rendered by
 *  pdf.js (`ThumbnailStrip`) and only drives that embedded viewer. */
export default function DrawingViewer(props: Props) {
  const { me, onClose } = props;
  const [detail, setDetail] = useState<DrawingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRevId, setSelectedRevId] = useState<number>(props.initialRevId ?? 0);
  // null = fit to page
  const [zoom, setZoom] = useState<number | null>(null);
  // Page last chosen from the thumbnail strip; a different revision starts at 1.
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [selectedRevId]);

  const refresh = useCallback(async () => {
    try { setDetail(await getDrawing(props.drawingId)); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [props.drawingId]);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { if (props.initialRevId) setSelectedRevId(props.initialRevId); }, [props.initialRevId]);

  useEffect(() => {
    if (!detail) return;
    if (selectedRevId && detail.revisions.some((r) => r.revision_id === selectedRevId)) return;
    const fallback = detail.revisions[0]?.revision_id ?? 0;
    if (fallback) setSelectedRevId(fallback);
  }, [detail, selectedRevId]);

  useEffect(() => {
    // Escape closes the viewer — but not while it is closing a mention picker or
    // cancelling an edit inside a comment box.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if ((e.target as HTMLElement | null)?.closest("input, textarea, select")) return;
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rev = detail?.revisions.find((r) => r.revision_id === selectedRevId);
  const latest = detail?.revisions[0];
  const isPdf = rev?.file_mime === "application/pdf";
  const step = (dir: 1 | -1) => {
    const cur = zoom ?? 100;
    const next = dir === 1 ? ZOOMS.find((z) => z > cur) : [...ZOOMS].reverse().find((z) => z < cur);
    if (next) setZoom(next);
  };
  const fileUrl = rev ? `/api/files/${rev.file_blob_id}` : "";

  const btn = "rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink hover:bg-h-surface-alt disabled:opacity-40";

  return (
    <div data-testid="drawing-viewer" role="dialog" aria-label="Drawing viewer"
         className="fixed inset-0 z-50 flex flex-col bg-h-bg">
      <header className="flex flex-wrap items-center gap-3 border-b border-h-line bg-h-surface px-4 py-2">
        <button type="button" onClick={props.onClose} className={btn}>← Back</button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-h-ink">
            <span className="h-mono">{detail?.drawing_no ?? "—"}</span> — {detail?.title ?? "Loading…"}
          </p>
        </div>
        {rev && <span className="h-mono rounded bg-h-surface-alt px-1.5 py-0.5 text-xs text-h-ink2">v{rev.rev_no}</span>}
        {detail && <QueueChip queue={queueOfDetail(detail)} />}
        <div className="flex items-center gap-1">
          <button type="button" aria-label="Zoom out" onClick={() => step(-1)} className={btn}>−</button>
          <span className="h-mono w-12 text-center text-xs text-h-ink2" data-testid="zoom-level">{zoom ? `${zoom}%` : "Fit"}</span>
          <button type="button" aria-label="Zoom in" onClick={() => step(1)} className={btn}>+</button>
          <button type="button" onClick={() => setZoom(null)} className={btn}>Fit</button>
          {rev && <a href={fileUrl} download className={btn} aria-label="Download">↓</a>}
        </div>
      </header>

      {error && <p className="p-4 text-sm text-h-bad">{error}</p>}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {rev && isPdf && <ThumbnailStrip url={fileUrl} page={page} onPage={setPage} />}
        <main className="min-h-0 flex-1 overflow-auto bg-h-line/20">
          {rev && isPdf && (
            <iframe
              key={`${rev.revision_id}-${zoom ?? "fit"}-${page}`}
              title={`drawing ${props.drawingId} v${rev.rev_no}`}
              // navpanes=0: Chrome's own thumbnail panel would sit beside ours.
              src={`${fileUrl}#page=${page}&zoom=${zoom ?? "page-fit"}&navpanes=0`}
              className="h-full w-full"
            />
          )}
          {rev && !isPdf && (
            <div className="flex min-h-full min-w-full items-center justify-center p-4">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={fileUrl}
                alt={`drawing ${props.drawingId} v${rev.rev_no}`}
                style={zoom ? { width: `${zoom}%`, maxWidth: "none" } : undefined}
                className={zoom ? "" : "max-h-full max-w-full"}
              />
            </div>
          )}
        </main>

        <aside className="w-full shrink-0 space-y-4 overflow-y-auto border-t border-h-line bg-h-surface p-4 lg:w-[340px] lg:border-l lg:border-t-0">
          {detail && rev && latest && (
            <>
              <section>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-h-muted">The current status</p>
                <p className="h-mono mt-1 text-base font-semibold text-h-ink">{detail.drawing_no ?? "—"}</p>
                <p className="text-sm text-h-ink2">{detail.title}</p>
              </section>

              <section>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-h-muted">Versions</p>
                <ol className="space-y-1">
                  {detail.revisions.map((r, i) => {
                    const active = r.revision_id === selectedRevId;
                    return (
                      <li key={r.revision_id}>
                        <button
                          type="button"
                          onClick={() => { setSelectedRevId(r.revision_id); props.onSelectRevision(r.revision_id); }}
                          aria-current={active ? "true" : undefined}
                          className={`flex w-full items-center gap-2 rounded border px-2.5 py-1.5 text-left text-sm ${
                            active ? "border-h-good bg-h-good/10" : "border-h-line hover:bg-h-surface-alt"
                          }`}
                        >
                          <span className="h-mono font-medium text-h-ink">v{r.rev_no}</span>
                          <StatusPill status={r.status} />
                          {i === 0 && <span className="rounded bg-h-good/15 px-1.5 text-[10px] font-semibold uppercase text-h-good">Latest</span>}
                          {active && <span className="ml-auto text-[11px] text-h-muted">Viewing</span>}
                        </button>
                      </li>
                    );
                  })}
                </ol>
                {rev.review_note && (
                  <p className="mt-2 rounded bg-h-surface-alt p-2 text-xs text-h-ink2">Review note: {rev.review_note}</p>
                )}
              </section>

              <section data-testid="viewer-comments">
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-h-muted">Communication</p>
                <CommentThread
                  key={rev.revision_id}
                  objectType="revision"
                  objectId={rev.revision_id}
                  currentUserId={me.id}
                  currentUserRole={me.auth_role}
                  canComment={can(me, "shop_dwgs", "comment")}
                  onMutated={props.onChanged}
                  roster={props.roster}
                />
              </section>

              <section>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-h-muted">Drawing info</p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                  <dt className="text-h-muted">Level</dt><dd className="text-right text-h-ink">{detail.level ?? "—"}</dd>
                  <dt className="text-h-muted">Joinery ID</dt><dd className="h-mono text-right text-h-ink">{detail.joinery_id ?? "—"}</dd>
                  <dt className="text-h-muted">Type</dt><dd className="text-right text-h-ink">{detail.type}</dd>
                  <dt className="text-h-muted">Assigned to</dt><dd className="text-right text-h-ink">{detail.assigned_to_name ?? "Unassigned"}</dd>
                  <dt className="text-h-muted">Due date</dt><dd className="text-right text-h-ink">{fmtDate(detail.due_date)}</dd>
                </dl>
              </section>

              <footer className="flex flex-wrap items-center gap-2 border-t border-h-line pt-3">
                <ReviewActions
                  detail={detail}
                  selectedRev={rev}
                  me={me}
                  onAfter={async () => { await refresh(); props.onChanged(); }}
                />
              </footer>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

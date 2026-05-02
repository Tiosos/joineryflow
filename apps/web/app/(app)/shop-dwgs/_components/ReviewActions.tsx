"use client";

import { useState } from "react";

import type { DrawingDetail, Revision } from "@/lib/shop-drawings-types";
import {
  archiveDrawing,
  transitionRevision,
} from "@/lib/shop-drawings-fetch";

import NewRevisionDialog from "./NewRevisionDialog";

interface Me { id: number; auth_role: string; }

interface Props {
  detail: DrawingDetail;
  selectedRev: Revision;
  me: Me;
  onAfter: () => Promise<void>;
}

const APPROVER_ROLES = new Set(["drafter", "manager", "admin"]);
const WRITER_ROLES   = new Set(["drafter", "manager", "admin", "editor"]);

export default function ReviewActions({ detail, selectedRev, me, onAfter }: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [newRevOpen, setNewRevOpen] = useState(false);

  if (detail.archived_at) {
    return <span className="text-sm text-h-muted">This drawing is archived.</span>;
  }

  const isUploader = selectedRev.uploaded_by === me.id;
  const canApprove = APPROVER_ROLES.has(me.auth_role) && !isUploader;
  const canWrite   = WRITER_ROLES.has(me.auth_role);
  const canArchive = me.auth_role === "manager" || me.auth_role === "admin";

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); await onAfter(); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex w-full flex-wrap items-center gap-2">
      {selectedRev.status === "draft" && isUploader && (
        <button disabled={busy} onClick={() => run(() => transitionRevision(detail.drawing_id, selectedRev.revision_id, "submit"))}
                className="rounded bg-h-accent px-3 py-1.5 text-sm text-white disabled:opacity-50">
          Submit for review
        </button>
      )}
      {selectedRev.status === "pending" && isUploader && (
        <button disabled={busy} onClick={() => run(() => transitionRevision(detail.drawing_id, selectedRev.revision_id, "withdraw"))}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink disabled:opacity-50">
          Withdraw
        </button>
      )}
      {selectedRev.status === "pending" && canApprove && (
        <>
          <button disabled={busy} onClick={() => run(() => transitionRevision(detail.drawing_id, selectedRev.revision_id, "approve"))}
                  className="rounded bg-emerald-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            Approve
          </button>
          {!showRejectInput ? (
            <button disabled={busy} onClick={() => setShowRejectInput(true)}
                    className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-rose-700 disabled:opacity-50">
              Reject
            </button>
          ) : (
            <div className="flex w-full items-center gap-2">
              <input
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                placeholder="Reason for rejection (required)"
                className="flex-1 rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
              />
              <button
                disabled={busy || !rejectNote.trim()}
                onClick={() => run(async () => {
                  await transitionRevision(detail.drawing_id, selectedRev.revision_id, "reject", rejectNote.trim());
                  setShowRejectInput(false);
                  setRejectNote("");
                })}
                className="rounded bg-rose-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
                Confirm reject
              </button>
              <button onClick={() => { setShowRejectInput(false); setRejectNote(""); }}
                      className="text-xs text-h-muted hover:text-h-ink">Cancel</button>
            </div>
          )}
        </>
      )}
      {selectedRev.status === "pending" && !canApprove && !isUploader && (
        <span className="text-xs text-h-muted">Awaiting reviewer.</span>
      )}
      {selectedRev.status === "pending" && isUploader && (
        <span className="text-xs text-h-muted">You uploaded this revision; another reviewer must approve.</span>
      )}

      {canWrite && !detail.archived_at && (
        <span className="ml-auto" />
      )}
      {canWrite && !detail.archived_at && (
        <button disabled={busy} onClick={() => setNewRevOpen(true)}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink disabled:opacity-50">
          Upload new revision
        </button>
      )}
      {canArchive && (
        <button disabled={busy}
                onClick={() => {
                  if (!confirm("Archive this drawing? It will move to the Archive subtab.")) return;
                  run(() => archiveDrawing(detail.drawing_id));
                }}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-muted hover:text-h-ink disabled:opacity-50">
          Archive drawing
        </button>
      )}

      {err && <p className="w-full text-xs text-rose-700">{err}</p>}

      {newRevOpen && (
        <NewRevisionDialog
          drawingId={detail.drawing_id}
          onClose={() => setNewRevOpen(false)}
          onAdded={onAfter}
        />
      )}
    </div>
  );
}

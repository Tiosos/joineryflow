"use client";

import { useState } from "react";

import {
  approveSample,
  archiveSample,
  rejectSample,
} from "@/lib/samples-fetch";
import type { Sample } from "@/lib/samples-types";

interface Me { id: number; auth_role: string; }

interface Props {
  sample: Sample;
  me: Me;
  onAfter: () => Promise<void>;
  onEditClick: () => void;
  onUploadPhotoClick: () => void;
  onClearPhotoClick: () => Promise<void>;
}

const APPROVER_ROLES = new Set(["drafter", "manager", "admin"]);
const MANAGER_ROLES = new Set(["manager", "admin"]);

export default function ReviewActions(p: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectNote, setRejectNote] = useState("");

  const isCreator = p.sample.created_by === p.me.id;
  const isManager = MANAGER_ROLES.has(p.me.auth_role);
  const canApprove = APPROVER_ROLES.has(p.me.auth_role) && !isCreator;
  const canEdit = isCreator || isManager;
  const canArchive = isCreator || isManager;
  const archived = p.sample.archived_at != null;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await fn(); await p.onAfter(); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  if (archived) {
    return <p className="text-sm text-h-muted">This sample is archived.</p>;
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {p.sample.status === "pending" && canApprove && (
        <>
          <button type="button" disabled={busy}
                  onClick={() => run(() => approveSample(p.sample.sample_id))}
                  className="rounded bg-emerald-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            Approve
          </button>
          {!showRejectInput ? (
            <button type="button" disabled={busy} onClick={() => setShowRejectInput(true)}
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
              <button type="button"
                      disabled={busy || !rejectNote.trim()}
                      onClick={() => run(async () => {
                        await rejectSample(p.sample.sample_id, rejectNote.trim());
                        setShowRejectInput(false);
                        setRejectNote("");
                      })}
                      className="rounded bg-rose-600 px-3 py-1.5 text-sm text-white disabled:opacity-50">
                Confirm reject
              </button>
              <button type="button" onClick={() => { setShowRejectInput(false); setRejectNote(""); }}
                      className="text-xs text-h-muted hover:text-h-ink">Cancel</button>
            </div>
          )}
        </>
      )}
      {p.sample.status === "pending" && isCreator && (
        <span className="text-xs text-h-muted">You created this sample; another reviewer must approve.</span>
      )}

      {canEdit && (
        <button type="button" onClick={p.onEditClick}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">
          Edit
        </button>
      )}
      {canEdit && (
        <button type="button" onClick={p.onUploadPhotoClick}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-ink">
          {p.sample.photo_file_blob_id ? "Replace photo" : "Upload photo"}
        </button>
      )}
      {canEdit && p.sample.photo_file_blob_id != null && (
        <button type="button" disabled={busy} onClick={() => run(p.onClearPhotoClick)}
                className="rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-rose-700 disabled:opacity-50">
          Clear photo
        </button>
      )}
      {canArchive && (
        <button type="button" disabled={busy}
                onClick={() => {
                  if (!confirm("Archive this sample?")) return;
                  run(() => archiveSample(p.sample.sample_id));
                }}
                className="ml-auto rounded border border-h-line bg-h-surface px-3 py-1.5 text-sm text-h-muted hover:text-h-ink disabled:opacity-50">
          Archive
        </button>
      )}

      {err && <p className="w-full text-xs text-rose-700">{err}</p>}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemOut, LockRequestOut } from "@/lib/pm-types";
import { PM, ApiError } from "@/lib/pm-fetch";

interface Props {
  item: ItemOut;
  currentUserId: number | null;
  currentUserRole: string | null;
}

/** Same rule as the API's `decide_lock_request`, plus the roles its approve / reject routes accept
 *  (`require_drafter`): the lock owner, a manager or an admin, and only drafter, manager or admin. */
function canDecide(item: ItemOut, userId: number | null, role: string | null): boolean {
  if (role !== "drafter" && role !== "manager" && role !== "admin") return false;
  return role === "manager" || role === "admin" || (userId != null && item.cutlist_owner_id === userId);
}

const REFUSALS: Record<string, string> = {
  ALREADY_DECIDED: "Someone has already decided this request.",
  HARD_LOCKED: "The item is Hard-locked: a held save cannot be applied until a manager unlocks it.",
  APPROVAL_LOCKED: "The item is Approved: a held save cannot be applied until its status moves off Approved.",
};

function refusal(e: unknown): string {
  if (e instanceof ApiError) {
    const detail = (e.body as { detail?: unknown } | undefined)?.detail;
    const code = typeof detail === "object" && detail !== null ? (detail as { code?: string }).code : undefined;
    if (code && REFUSALS[code]) return REFUSALS[code];
    if (e.status === 403) return "Only the lock owner, a manager or an admin can decide this request.";
    if (e.status === 404) return "This request or item no longer exists.";
  }
  return "Could not save the decision.";
}

function show(v: unknown): string {
  if (v === null || v === undefined || v === "") return "(empty)";
  return typeof v === "string" ? v : JSON.stringify(v);
}

/**
 * A non-owner's save on a Controlled-Lock item is held as a request (B7 / Q509). This is where the
 * lock owner, a manager or an admin sees what was proposed and approves or rejects it. Shown only
 * to those people, only while a request is pending; the notification bell lists the same
 * requests (derived from the same table, so a decided request leaves both).
 */
export function LockRequestsBanner({ item, currentUserId, currentUserRole }: Props) {
  const router = useRouter();
  const allowed = canDecide(item, currentUserId, currentUserRole);
  const [rows, setRows] = useState<LockRequestOut[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await PM.pendingLockRequests(item.id));
    } catch {
      // A failed read just leaves the banner out; the next visit retries.
    }
  }, [item.id]);

  useEffect(() => {
    if (allowed) void load();
  }, [allowed, load]);

  async function decide(r: LockRequestOut, decision: "approve" | "reject") {
    setBusyId(r.request_id);
    setError(null);
    try {
      await PM.decideLockRequest(r.request_id, decision, notes[r.request_id]?.trim() || null);
      await load();
      // The bell lists the same requests: tell it to re-read now rather than at its next poll.
      window.dispatchEvent(new Event("jf:notifications-changed"));
      // An approved save changed the item: re-read it.
      router.refresh();
    } catch (e) {
      setError(refusal(e));
      await load();
    } finally {
      setBusyId(null);
    }
  }

  if (!allowed || rows.length === 0) return null;

  return (
    <section
      role="alert"
      data-testid="lock-requests-banner"
      className="grid gap-3 rounded-md border border-h-warn bg-h-warn/10 p-3 text-sm text-h-ink"
    >
      <p className="font-medium">
        {rows.length === 1
          ? "A save is held for your decision"
          : `${rows.length} saves are held for your decision`}
        <span className="font-normal text-h-muted"> — someone edited this item while it is locked.</span>
      </p>
      {error && (
        <p data-testid="lock-request-error" className="text-xs text-h-bad">
          {error}
        </p>
      )}
      <ul className="grid gap-3">
        {rows.map((r) => (
          <li
            key={r.request_id}
            data-testid={`lock-request-${r.request_id}`}
            className="grid gap-2 rounded border border-h-line bg-h-surface p-2"
          >
            <p>
              <strong>{r.requested_by_name ?? "Someone"}</strong> proposes:
            </p>
            <ul className="grid gap-0.5 text-xs">
              {Object.entries(r.requested_changes).map(([field, value]) => (
                <li key={field}>
                  <span className="h-mono text-h-muted">{field}</span> → {show(value)}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                aria-label="Note (optional)"
                placeholder="Note (optional)"
                data-testid={`lock-request-note-${r.request_id}`}
                value={notes[r.request_id] ?? ""}
                onChange={(e) => setNotes((n) => ({ ...n, [r.request_id]: e.target.value }))}
                className="min-w-48 flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-xs"
              />
              <button
                type="button"
                data-testid={`lock-request-approve-${r.request_id}`}
                disabled={busyId !== null}
                onClick={() => void decide(r, "approve")}
                className="rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-ink hover:bg-h-line/40 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                type="button"
                data-testid={`lock-request-reject-${r.request_id}`}
                disabled={busyId !== null}
                onClick={() => void decide(r, "reject")}
                className="rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-ink hover:bg-h-line/40 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

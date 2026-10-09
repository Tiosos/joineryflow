"use client";

import { useState } from "react";
import type { OrderDetail as OrderDetailType } from "@/lib/orders-types";
import { approvalErrorMessage, money } from "./shared";

/**
 * PO approval. The server decides whether an order `needs_approval` (total over the workspace
 * limit, or the project manager's flag); this only renders the state and calls the approval
 * routes. A plain status change is refused by the API for such an order.
 */
export function ApprovalSection({
  order, threshold, meId, canRequest, canApprove, canFlag, onFlag, onChanged,
}: {
  order: OrderDetailType;
  threshold: string | null;
  meId: number | null;
  canRequest: boolean;
  canApprove: boolean;
  canFlag: boolean;
  onFlag: (flag: boolean) => void;
  onChanged: (updated: OrderDetailType) => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!order.needs_approval && !canFlag) return null;

  async function act(action: "request" | "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/orders/${order.po_id}/approval/${action}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(action === "request" ? {} : { note: note.trim() || null }),
      });
      if (!res.ok) {
        setError(approvalErrorMessage(res, await res.json().catch(() => null)));
        return;
      }
      setNote("");
      onChanged((await res.json()) as OrderDetailType);
    } catch {
      setError("Failed — check your connection");
    } finally {
      setBusy(false);
    }
  }

  const requestable = order.status === "Draft" || order.status === "Rejected";
  const mine = meId != null && order.approval_requested_by === meId;

  return (
    <section data-testid="order-approval" className="mb-3 grid gap-1.5 rounded border border-h-line bg-h-bg p-2">
      <p className="text-h-muted">
        {threshold != null ? `Orders over ${money(threshold, null)} need approval, ` : "Orders over the approval limit need approval, "}
        and so does any order the project manager flags.
      </p>
      {canFlag && !order.locked && (
        <label className="flex items-center gap-2 text-h-ink">
          <input
            type="checkbox"
            data-testid="order-requires-approval"
            checked={order.requires_approval}
            onChange={e => onFlag(e.target.checked)}
          />
          Needs approval whatever the total (project manager)
        </label>
      )}
      {order.needs_approval && (
        <div className="grid gap-1.5">
          {requestable && (
            <div className="flex flex-wrap items-center gap-2">
              {order.status === "Rejected" && (
                <span className="text-[#b4443d]">
                  Rejected{order.approval_decided_by_name ? ` by ${order.approval_decided_by_name}` : ""}
                  {order.approval_note ? `: ${order.approval_note}` : ""}
                </span>
              )}
              {canRequest && (
                <button
                  type="button"
                  disabled={busy}
                  data-testid="order-request-approval"
                  onClick={() => void act("request")}
                  className="rounded border border-h-line bg-h-surface px-2 py-1 text-h-ink hover:bg-h-bg"
                >
                  Request approval
                </button>
              )}
            </div>
          )}
          {order.status === "Pending" && (
            <>
              <p data-testid="order-approval-pending" className="text-h-ink">
                Waiting for approval — requested
                {order.approval_requested_by_name ? ` by ${order.approval_requested_by_name}` : ""}.
              </p>
              {/* Set when an approved order's total was raised and it was sent back. */}
              {order.approval_note && <p data-testid="order-approval-reason" className="text-h-muted">{order.approval_note}</p>}
              {canApprove && mine && (
                <p className="text-h-muted">You requested this order, so someone else must approve it.</p>
              )}
              {canApprove && !mine && (
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    value={note}
                    onChange={e => setNote(e.target.value)}
                    placeholder="Note (required to reject)"
                    data-testid="order-approval-note"
                    className="min-w-[14rem] rounded border border-h-line bg-h-surface px-2 py-1"
                  />
                  <button
                    type="button" disabled={busy} data-testid="order-approve"
                    onClick={() => void act("approve")}
                    className="rounded border border-h-line bg-h-surface px-2 py-1 text-[#3f7d48] hover:bg-h-bg"
                  >
                    Approve
                  </button>
                  <button
                    type="button" disabled={busy} data-testid="order-reject"
                    onClick={() => void act("reject")}
                    className="rounded border border-h-line bg-h-surface px-2 py-1 text-[#b4443d] hover:bg-h-bg"
                  >
                    Reject
                  </button>
                </div>
              )}
            </>
          )}
          {order.status === "Approved" && order.approval_decided_at && (
            <p data-testid="order-approved-by" className="text-[#3f7d48]">
              Approved{order.approval_decided_by_name ? ` by ${order.approval_decided_by_name}` : ""}
              {order.approval_note ? `: ${order.approval_note}` : ""}
            </p>
          )}
        </div>
      )}
      {error && <p data-testid="order-approval-error" className="text-[#b4443d]">{error}</p>}
    </section>
  );
}

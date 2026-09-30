"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { PM, ApiError } from "@/lib/pm-fetch";
import { StatusPopup } from "@/app/(app)/tracking/_components/StatusPopup";
import { lockFromError, moduleLockReason } from "./cutlist/moduleLock";

// PATCH /items/{id}/status and /items/{id}/lifecycle/{stage_key} both gate on
// tracking:write, which per the RBAC matrix is {editor, drafter, manager, admin}.
const CAN_ACT = new Set(["editor", "drafter", "manager", "admin"]);

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ActionsTab({
  item,
  currentUserId,
  currentUserRole,
}: {
  item: ItemOut;
  currentUserId: number | null;
  currentUserRole: string | null;
}) {
  const router = useRouter();
  const canAct = CAN_ACT.has(currentUserRole ?? "");
  // Hard Lock and someone else's Controlled Lock refuse a status or stage-date
  // change; the Approval Lock does not (status is how it is cleared).
  const lockReason = canAct
    ? moduleLockReason(item, currentUserId, currentUserRole, "status")
    : null;
  const [statusOpen, setStatusOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reqDone = item.stages["REQ"]?.done_date ?? null;

  async function markReqDone() {
    setBusy(true);
    setError(null);
    try {
      await PM.patchItemLifecycle(item.id, "REQ", { done_date: todayIso() });
      router.refresh();
    } catch (e) {
      setError(
        lockFromError(e, "status") ??
          (e instanceof ApiError ? `Failed (${e.status})` : "Failed to mark REQ done"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {error && (
        <div className="col-span-full rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </div>
      )}
      {!canAct && (
        <p className="col-span-full text-sm text-h-muted">
          Your role can view this item's actions but not trigger them.
        </p>
      )}

      {lockReason && (
        <p
          data-testid="actions-locked"
          className="col-span-full rounded bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          {lockReason}
        </p>
      )}

      <ActionCard
        label="Set status"
        description="Open the status dialog and log a status change with a note."
        disabled={!canAct || !!lockReason}
        onClick={() => setStatusOpen(true)}
      />

      <ActionCard
        label={reqDone ? `REQ marked done (${reqDone})` : "Mark REQ done today"}
        description="Sets the REQ lifecycle stage's done_date to today."
        disabled={!canAct || !!lockReason || busy || !!reqDone}
        onClick={markReqDone}
      />

      <ActionLinkCard
        label="Jump to Orderbook"
        description="Open this item's project in the Orderbook."
        href={`/orderbook?project=${item.project_id}`}
      />

      {/* Print Cutlist / Hardware / Combined PDF already live in the footer
          below, on every tab — not duplicated here. */}

      {statusOpen && (
        <StatusPopup
          itemId={item.id}
          currentUserId={currentUserId}
          currentUserRole={currentUserRole}
          onClose={() => setStatusOpen(false)}
          onUpdated={() => router.refresh()}
        />
      )}
    </div>
  );
}

function ActionCard({
  label,
  description,
  disabled,
  onClick,
}: {
  label: string;
  description: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded-lg border border-h-line bg-h-surface p-4 text-left hover:bg-h-line/20 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <p className="text-sm font-medium text-h-ink">{label}</p>
      <p className="mt-1 text-xs text-h-muted">{description}</p>
    </button>
  );
}

function ActionLinkCard({
  label,
  description,
  href,
}: {
  label: string;
  description: string;
  href: string;
}) {
  return (
    <a
      href={href}
      className="rounded-lg border border-h-line bg-h-surface p-4 text-left hover:bg-h-line/20"
    >
      <p className="text-sm font-medium text-h-ink">{label}</p>
      <p className="mt-1 text-xs text-h-muted">{description}</p>
    </a>
  );
}

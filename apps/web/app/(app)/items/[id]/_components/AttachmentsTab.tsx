"use client";

import { useCallback, useEffect, useState } from "react";

import { getAttachments } from "@/lib/attachments-fetch";
import type { AttachmentsBundle } from "@/lib/attachments-types";
import { ATTACHMENT_KINDS, COMBINED_PDF_KINDS } from "@/lib/attachments-types";
import type { ItemOut } from "@/lib/pm-types";
import { attachmentsCountLabel } from "@/lib/print";

import AttachmentSlotCard from "./AttachmentSlotCard";
import DocumentRegister from "./DocumentRegister";
import { moduleLockReason } from "./cutlist/moduleLock";

const WRITER_ROLES = new Set(["drafter", "manager", "admin"]);
// The register is gated `list:write` alone, so editors may write it too (attachment
// slots also require drafter+). Mirrors the API; the API decides.
const REGISTER_WRITER_ROLES = new Set(["drafter", "manager", "admin", "editor"]);

interface Props {
  item: ItemOut;
  currentUserId: number | null;
  currentUserRole: string | null;
}

export default function AttachmentsTab({ item, currentUserId, currentUserRole }: Props) {
  const itemId = item.id;
  const [bundle, setBundle] = useState<AttachmentsBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canWrite = currentUserRole != null && WRITER_ROLES.has(currentUserRole);
  const canWriteRegister = currentUserRole != null && REGISTER_WRITER_ROLES.has(currentUserRole);
  // Hard, Approval and someone else's Controlled Lock refuse a slot or register write;
  // the API decides, this only says why the controls are off.
  const anyLockReason =
    canWrite || canWriteRegister ? moduleLockReason(item, currentUserId, currentUserRole) : null;
  const lockReason = canWrite ? anyLockReason : null;
  const registerLockReason = canWriteRegister ? anyLockReason : null;

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const next = await getAttachments(itemId);
      setBundle(next);
    } catch (e) {
      setError(String(e));
    }
  }, [itemId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold text-h-ink">Attachments</h2>
        <p className="mt-1 text-sm text-h-muted">{attachmentsCountLabel(bundle)}</p>
      </header>

      {anyLockReason && (
        <p
          data-testid="attachments-locked"
          className="rounded-md border border-h-line bg-h-surface px-3 py-2 text-xs text-h-muted"
        >
          {anyLockReason}
        </p>
      )}

      {error && <p className="text-sm text-rose-700">{error}</p>}

      {!bundle && !error && <p className="text-sm text-h-muted">Loading…</p>}

      {bundle && (
        <div className="space-y-3">
          {ATTACHMENT_KINDS.map((kind) => {
            const slot = bundle.slots.find((s) => s.kind === kind);
            if (!slot) return null;
            return (
              <AttachmentSlotCard
                key={kind}
                itemId={itemId}
                slot={slot}
                canWrite={canWrite}
                lockReason={lockReason}
                onChanged={refresh}
                usedByCombined={COMBINED_PDF_KINDS.includes(kind)}
              />
            );
          })}
        </div>
      )}

      <DocumentRegister itemId={itemId} canWrite={canWriteRegister} lockReason={registerLockReason} />
    </section>
  );
}

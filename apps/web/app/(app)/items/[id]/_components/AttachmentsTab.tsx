"use client";

import { useCallback, useEffect, useState } from "react";

import { getAttachments } from "@/lib/attachments-fetch";
import type { AttachmentsBundle } from "@/lib/attachments-types";
import { ATTACHMENT_KINDS } from "@/lib/attachments-types";
import { attachmentsCountLabel } from "@/lib/print";

import AttachmentSlotCard from "./AttachmentSlotCard";

const WRITER_ROLES = new Set(["drafter", "manager", "admin"]);

interface Props {
  itemId: number;
  currentUserRole: string | null;
}

export default function AttachmentsTab({ itemId, currentUserRole }: Props) {
  const [bundle, setBundle] = useState<AttachmentsBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canWrite = currentUserRole != null && WRITER_ROLES.has(currentUserRole);

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
                onChanged={refresh}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

"use client";
import { useState, useEffect } from "react";
import type { ItemOut, HardwareCatalogOut, AvailabilityOut } from "@/lib/pm-types";
import { PM } from "@/lib/pm-fetch";
import { Pantry } from "./Pantry";
import { Cart } from "./Cart";
import { AddFromGlobalModal } from "./AddFromGlobalModal";
import { moduleLockReason } from "../cutlist/moduleLock";

interface HardwareTabProps {
  item: ItemOut;
  currentUserId: number | null;
  currentUserRole: string | null;
}

export function HardwareTab({ item, currentUserId, currentUserRole }: HardwareTabProps) {
  // Hardware lines are written under `require_drafter()` — mirror it, the API decides.
  const canWrite =
    currentUserRole === "drafter" || currentUserRole === "manager" || currentUserRole === "admin";
  const lockReason = moduleLockReason(item, currentUserId, currentUserRole);
  const [catalog, setCatalog] = useState<HardwareCatalogOut | null>(null);
  const [availability, setAvailability] = useState<AvailabilityOut | null>(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const [cat, avail] = await Promise.all([
        PM.catalog("", item.project_id).catch(() => null),
        PM.availability("", item.id).catch(() => null),
      ]);
      setCatalog(cat);
      setAvailability(avail);
      setLoading(false);
    }
    load();
  }, [item.id, item.project_id]);

  function refreshCatalog() {
    PM.catalog("", item.project_id)
      .then(setCatalog)
      .catch(() => { /* keep existing catalog */ });
  }

  function refreshAvailability() {
    PM.availability("", item.id)
      .then(setAvailability)
      .catch(() => { /* keep existing availability */ });
  }

  function refreshAll() {
    refreshCatalog();
    refreshAvailability();
  }

  if (loading) {
    return <div className="text-sm text-h-muted">Loading hardware…</div>;
  }

  return (
    <>
      {canWrite && lockReason && (
        <p
          data-testid="hardware-locked"
          className="mb-3 rounded-md border border-h-line bg-h-surface px-3 py-2 text-xs text-h-muted"
        >
          {lockReason}
        </p>
      )}
    <div className="flex gap-4">
      <Pantry
        item={item}
        catalog={catalog}
        onOpenModal={() => setAddModalOpen(true)}
        onRefresh={refreshAll}
        lockReason={lockReason}
      />
      <Cart
        item={item}
        availability={availability}
        onRefresh={refreshAll}
        lockReason={lockReason}
      />
      {addModalOpen && (
        <AddFromGlobalModal
          projectId={item.project_id}
          onClose={() => setAddModalOpen(false)}
          onAdded={() => {
            refreshCatalog();
            setAddModalOpen(false);
          }}
        />
      )}
    </div>
    </>
  );
}

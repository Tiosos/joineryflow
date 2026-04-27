"use client";
import { useState, useEffect } from "react";
import type { ItemOut, HardwareCatalogOut, AvailabilityOut } from "@/lib/pm-types";
import { PM } from "@/lib/pm-fetch";
import { Pantry } from "./Pantry";
import { Cart } from "./Cart";
import { AddFromGlobalModal } from "./AddFromGlobalModal";

interface HardwareTabProps {
  item: ItemOut;
}

export function HardwareTab({ item }: HardwareTabProps) {
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
    PM.catalog("", item.project_id).catch(() => null).then(setCatalog);
  }

  function refreshAvailability() {
    PM.availability("", item.id).catch(() => null).then(setAvailability);
  }

  function refreshAll() {
    refreshCatalog();
    refreshAvailability();
  }

  if (loading) {
    return <div className="text-sm text-h-muted">Loading hardware…</div>;
  }

  return (
    <div className="flex gap-4">
      <Pantry
        item={item}
        catalog={catalog}
        onOpenModal={() => setAddModalOpen(true)}
        onRefresh={refreshAll}
      />
      <Cart
        item={item}
        availability={availability}
        onRefresh={refreshAll}
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
  );
}

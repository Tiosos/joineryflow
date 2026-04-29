"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { TrackingGrid } from "@/components/pm/TrackingGrid";
import { AvailabilityDrawer } from "@/components/procurement/AvailabilityDrawer";
import type { TrackingItemRow } from "@/lib/pm-types";

interface Props {
  items: TrackingItemRow[];
  canEdit: boolean;
  projectId: number;
}

export function TrackingClient({ items, canEdit, projectId }: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const drawer = sp.get("drawer");
  const itemIdParam = sp.get("itemId");
  const drawerItemId =
    drawer === "item-availability" && itemIdParam
      ? Number(itemIdParam)
      : null;

  function buildUrl(next: URLSearchParams): string {
    const qs = next.toString();
    return qs ? `/tracking?${qs}` : "/tracking";
  }

  function openAvailability(itemId: number) {
    const next = new URLSearchParams(sp.toString());
    next.set("project_id", String(projectId));
    next.set("drawer", "item-availability");
    next.set("itemId", String(itemId));
    router.push(buildUrl(next));
  }

  function closeDrawer() {
    const next = new URLSearchParams(sp.toString());
    next.delete("drawer");
    next.delete("itemId");
    router.push(buildUrl(next));
  }

  return (
    <>
      <TrackingGrid
        items={items}
        canEdit={canEdit}
        onOpenAvailability={openAvailability}
      />
      <AvailabilityDrawer itemId={drawerItemId} onClose={closeDrawer} />
    </>
  );
}

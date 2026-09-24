"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { ProjectOut, TrackingItemRow } from "@/lib/pm-types";
import type { Me } from "@/lib/session";
import { AvailabilityDrawer } from "@/components/procurement/AvailabilityDrawer";
import { TrackingMetrics } from "./TrackingMetrics";
import { ProjectInfoBar } from "./ProjectInfoBar";
import { ItemsTable } from "./ItemsTable";
import { ItemDetailModal } from "./ItemDetailModal";
import { ProjectDetailModal } from "./ProjectDetailModal";
import { StatusPopup } from "./StatusPopup";
import { CreateOrderDialog } from "./CreateOrderDialog";
import { can } from "@/lib/permissions";
import { BulkStatusDialog } from "./BulkStatusDialog";

interface Props {
  project: ProjectOut;
  projects: ProjectOut[];
  items: TrackingItemRow[];
  me: Me | null;
  canEdit: boolean;
  procurementReady: boolean;
}

type QuickFilter = "my" | "deleted" | "void" | "tgsolid" | "orders" | "overdue" | "installed" | null;

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function TrackingClient({
  project,
  projects,
  items,
  me,
  canEdit,
  procurementReady,
}: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const [quick, setQuick] = useState<QuickFilter>(null);
  const [cutlistQuery, setCutlistQuery] = useState("");
  const [freeQuery, setFreeQuery] = useState("");
  const [showRowCount, setShowRowCount] = useState(true);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [itemModalId, setItemModalId] = useState<number | null>(null);
  const [statusPopupId, setStatusPopupId] = useState<number | null>(null);
  // Q425: raised from the O/BOOK sub-tab's Create Order button.
  const [createOrderOpen, setCreateOrderOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
  const [bulkBanner, setBulkBanner] = useState<string | null>(null);

  const drawerKind = sp.get("drawer");
  const drawerItemIdRaw = sp.get("itemId");
  const drawerItemId =
    drawerKind === "item-availability" && drawerItemIdRaw
      ? Number(drawerItemIdRaw)
      : null;

  function setDrawerItemId(id: number | null) {
    const next = new URLSearchParams(sp.toString());
    next.set("project_id", String(project.id));
    if (id == null) {
      next.delete("drawer");
      next.delete("itemId");
    } else {
      next.set("drawer", "item-availability");
      next.set("itemId", String(id));
    }
    const qs = next.toString();
    router.push(qs ? `/tracking?${qs}` : "/tracking");
  }

  const today = todayISO();

  const visibleItems = useMemo(() => {
    if (!quick) return items;
    const matches = (it: TrackingItemRow) => {
      switch (quick) {
        case "my":
          return me ? it.cutlist_owner_id === me.id : false;
        case "void":
          return it.status === "VOID";
        case "overdue":
          return Object.values(it.stages).some(
            (s) => s.due_date && !s.done_date && s.due_date < today,
          );
        case "installed":
          return Boolean(it.stages.INST?.done_date);
        case "deleted":
        case "tgsolid":
        case "orders":
          return false;
      }
    };
    // The quick filters judge Joinery Items. A related part rides with its
    // parent (Q420) instead of being tested on stages it can never have
    // (Q419) or on a cutlist owner it never gets — so the list stays
    // self-consistent and no child is left without its parent row.
    const kept = new Set(
      items.filter((it) => it.row_type !== "related_part" && matches(it)).map((it) => it.id),
    );
    return items.filter((it) =>
      it.row_type === "related_part"
        ? it.parent_item_id != null && kept.has(it.parent_item_id)
        : kept.has(it.id),
    );
  }, [items, quick, me, today]);

  function refresh() {
    router.refresh();
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectVisible(ids: number[], select: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (select) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  return (
    <div className="grid gap-3">
      <ProjectInfoBar
        project={project}
        projects={projects}
        onOpenInfo={() => setProjectModalOpen(true)}
        onOpenProcurement={() => router.push(`/projects/${project.id}/procurement`)}
        canEdit={canEdit}
        procurementReady={procurementReady}
      />

      <TrackingMetrics items={items} />

      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-h-line bg-h-surface p-2">
        <Chip label="My Entries" active={quick === "my"} onClick={() => setQuick(quick === "my" ? null : "my")} disabled={!me} />
        <Chip label="Deleted" active={quick === "deleted"} onClick={() => setQuick(quick === "deleted" ? null : "deleted")} disabled title="Backend field not exposed" />
        <Chip label="Void" active={quick === "void"} onClick={() => setQuick(quick === "void" ? null : "void")} />
        <Chip label="Tg Solid" active={quick === "tgsolid"} onClick={() => setQuick(quick === "tgsolid" ? null : "tgsolid")} disabled title="Backend field not exposed" />
        <Chip label="Orders" active={quick === "orders"} onClick={() => setQuick(quick === "orders" ? null : "orders")} disabled title="Backend wiring pending" />
        <span className="mx-1 h-4 w-px bg-h-line" />
        <Chip label="Overdue" tone="bad" active={quick === "overdue"} onClick={() => setQuick(quick === "overdue" ? null : "overdue")} />
        <Chip label="Installed" tone="good" active={quick === "installed"} onClick={() => setQuick(quick === "installed" ? null : "installed")} />
        <button
          type="button"
          onClick={refresh}
          className="ml-1 rounded border border-h-line bg-h-surface px-2 py-1 text-xs text-h-muted hover:text-h-ink"
          title="Refresh data from server"
        >
          ↻
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-h-line bg-h-surface p-2">
        <input
          type="search"
          placeholder="Cutlist #"
          value={cutlistQuery}
          onChange={(e) => setCutlistQuery(e.target.value)}
          className="w-28 rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
        />
        <input
          type="search"
          placeholder="Search items, rooms, codes…"
          value={freeQuery}
          onChange={(e) => setFreeQuery(e.target.value)}
          className="min-w-[200px] flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink"
        />
      </div>

      {canEdit ? (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-h-line bg-h-surface px-3 py-1.5 text-xs text-h-muted">
          <span>
            {selectedIds.size === 0
              ? "Tip: tick rows to apply a bulk status."
              : `${selectedIds.size} selected`}
          </span>
          <button
            type="button"
            onClick={() => setBulkDialogOpen(true)}
            disabled={selectedIds.size === 0}
            className="rounded bg-h-accent px-2 py-0.5 text-[11px] font-semibold text-white disabled:opacity-40"
          >
            Apply status…
          </button>
          {selectedIds.size > 0 ? (
            <button
              type="button"
              onClick={clearSelection}
              className="rounded border border-h-line bg-h-bg px-2 py-0.5 text-[11px] text-h-muted hover:text-h-ink"
            >
              Clear selection
            </button>
          ) : null}
          {bulkBanner ? (
            <span className="ml-auto rounded bg-[#e4efe5] px-2 py-0.5 text-[11px] text-[#3f7d48]">
              {bulkBanner}
            </span>
          ) : null}
        </div>
      ) : null}

      <ItemsTable
        items={visibleItems}
        projectId={project.id}
        canCreateOrder={can(me, "orderbook", "write")}
        onCreateOrder={() => setCreateOrderOpen(true)}
        cutlistQuery={cutlistQuery}
        freeQuery={freeQuery}
        onOpenItem={(id) => setItemModalId(id)}
        onOpenStatus={(id) => setStatusPopupId(id)}
        onOpenAvailability={(id) => setDrawerItemId(id)}
        selectedIds={canEdit ? selectedIds : undefined}
        onToggleSelect={canEdit ? toggleSelect : undefined}
        onToggleSelectVisible={canEdit ? toggleSelectVisible : undefined}
      />

      <div className="flex items-center gap-2 text-xs text-h-muted">
        <button
          type="button"
          onClick={() => setShowRowCount(true)}
          className={`rounded border border-h-line px-2 py-0.5 ${showRowCount ? "bg-h-bg text-h-ink" : "bg-h-surface"}`}
        >
          Show
        </button>
        <button
          type="button"
          onClick={() => setShowRowCount(false)}
          className={`rounded border border-h-line px-2 py-0.5 ${!showRowCount ? "bg-h-bg text-h-ink" : "bg-h-surface"}`}
        >
          Hide
        </button>
        {showRowCount ? (
          <span className="font-mono">Total rows: {visibleItems.length}</span>
        ) : null}
        <span className="ml-auto opacity-70">
          Click a CUTLIST number to open the full item editor. Click ▶ for a quick preview modal.
        </span>
      </div>

      <AvailabilityDrawer
        itemId={drawerItemId}
        onClose={() => setDrawerItemId(null)}
        projectId={project.id}
      />

      <ItemDetailModal
        itemId={itemModalId}
        items={visibleItems}
        onClose={() => setItemModalId(null)}
        onNavigate={(id) => setItemModalId(id)}
      />
      <ProjectDetailModal
        project={projectModalOpen ? project : null}
        onClose={() => setProjectModalOpen(false)}
      />
      <StatusPopup
        itemId={statusPopupId}
        onClose={() => setStatusPopupId(null)}
        onUpdated={refresh}
      />
      {createOrderOpen && (
        <CreateOrderDialog
          projectId={project.id}
          items={items}
          onClose={() => setCreateOrderOpen(false)}
        />
      )}

      <BulkStatusDialog
        open={bulkDialogOpen}
        itemIds={Array.from(selectedIds)}
        onClose={() => setBulkDialogOpen(false)}
        onApplied={(result) => {
          const parts: string[] = [`${result.updated} updated`];
          if (result.not_found.length > 0) parts.push(`${result.not_found.length} not found`);
          if (result.cross_workspace.length > 0)
            parts.push(`${result.cross_workspace.length} skipped (workspace)`);
          setBulkBanner(parts.join(" · "));
          clearSelection();
          refresh();
        }}
      />
    </div>
  );
}

interface ChipProps {
  label: string;
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  tone?: "bad" | "good";
  title?: string;
}

function Chip({ label, active, onClick, disabled, tone, title }: ChipProps) {
  const toneClass =
    tone === "bad"
      ? active
        ? "bg-[#f2dcd9] text-[#b4443d] border-[#b4443d]"
        : "border-h-line text-[#b4443d] hover:bg-[#f2dcd9]/30"
      : tone === "good"
      ? active
        ? "bg-[#e4efe5] text-[#3f7d48] border-[#3f7d48]"
        : "border-h-line text-[#3f7d48] hover:bg-[#e4efe5]/30"
      : active
      ? "bg-h-ink text-white border-h-ink"
      : "border-h-line text-h-muted hover:text-h-ink";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`rounded-full border px-2.5 py-1 text-xs transition disabled:cursor-not-allowed disabled:opacity-40 ${toneClass}`}
    >
      {label}
    </button>
  );
}

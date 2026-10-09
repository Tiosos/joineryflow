"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { OrderPreview, OrderPreviewLine } from "@/lib/estimating-types";
import { listSupplierOptions } from "@/lib/catalog-fetch";
import type { SupplierOption } from "@/lib/catalog-types";
import { fmtMoney } from "./shared";

interface OrderPreviewDialogProps {
  preview: OrderPreview;
  busy: boolean;
  onConfirm: (includeLineIds: number[]) => void;
  onCancel: () => void;
  /** A line was marked / un-marked "ordered by hand": the page's own counts are stale. */
  onChanged?: () => void;
}

export function OrderPreviewDialog({ preview: initial, busy, onConfirm, onCancel, onChanged }: OrderPreviewDialogProps) {
  // The quote lines to order now are the PM's choice; the supplier groups below
  // are always the server's answer for exactly that selection, so ticking a line
  // re-asks it. Lines an earlier run covered stay visible but cannot be ticked.
  const [preview, setPreview] = useState(initial);
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(initial.lines.filter((l) => l.selected).map((l) => l.line_id)),
  );
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  // Several quick ticks fire several requests; only the newest may write.
  const refreshSeq = useRef(0);

  // For the "Link supplier" shortcut on an unassigned material. null = not loaded or
  // unreadable (`GET /suppliers` needs orderbook:read): the shortcut is then disabled.
  const [suppliers, setSuppliers] = useState<SupplierOption[] | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [linkingKey, setLinkingKey] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    listSupplierOptions()
      .then((l) => live && setSuppliers(l))
      .catch(() => live && setSuppliers(null));
    return () => {
      live = false;
    };
  }, []);

  // "Ordered by hand": a line the PM ordered outside the system leaves the pending set.
  // One line at a time (`dismissing`), a required reason, and it can be undone.
  const [dismissing, setDismissing] = useState<number | null>(null);
  // The same, for a single material on a line.
  const [dismissingMat, setDismissingMat] = useState<
    { lineId: number; type: string; id: number } | null
  >(null);
  const [reason, setReason] = useState("");
  const [lineBusy, setLineBusy] = useState(false);
  const [lineError, setLineError] = useState<string | null>(null);

  // After either change the server decides which lines are pending: re-read them (a
  // default preview carries every line's current state), keep the PM's own ticks that
  // are still valid, and re-ask for the groups of that selection.
  async function afterLineChange(lineId: number, restored: boolean) {
    const mine = ++refreshSeq.current;
    try {
      const r = await fetch(`/api/revisions/${preview.revision_id}/order-preview`);
      if (mine !== refreshSeq.current) return;
      if (!r.ok) throw new Error(`order-preview → ${r.status}`);
      const fresh = (await r.json()) as OrderPreview;
      const pending = new Set(fresh.lines.filter((l) => l.selected).map((l) => l.line_id));
      const next = new Set<number>();
      selected.forEach((id) => pending.has(id) && next.add(id));
      if (restored && pending.has(lineId)) next.add(lineId);
      setSelected(next);
      setPreview({ ...fresh, groups: [], unassigned: [] });
      setRefreshError(null);
      if (next.size > 0) await refreshFor(next);
    } catch (e) {
      if (mine !== refreshSeq.current) return;
      setRefreshError(e instanceof Error ? e.message : "Could not refresh the preview");
    }
    onChanged?.();
  }

  async function changeLine(lineId: number, method: "POST" | "DELETE") {
    setLineBusy(true);
    setLineError(null);
    try {
      const r = await fetch(
        `/api/revisions/${preview.revision_id}/lines/${lineId}/order-dismissal`,
        method === "POST"
          ? {
              method,
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ reason: reason.trim() }),
            }
          : { method },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        const code = body?.detail?.code;
        setLineError(
          code === "ALREADY_GENERATED"
            ? "A run has already ordered this line — refreshing."
            : code === "ALREADY_DISMISSED"
              ? "Someone already marked this line ordered by hand — refreshing."
              : code === "NOT_DISMISSED"
                ? "This line is no longer marked ordered by hand — refreshing."
                : `Could not ${method === "POST" ? "mark" : "undo"} the line (${r.status}).`,
        );
      } else {
        setDismissing(null);
        setReason("");
      }
      // Either way the server's answer is the truth now.
      await afterLineChange(lineId, method === "DELETE");
    } catch {
      setLineError("Could not reach the server — nothing was changed.");
    } finally {
      setLineBusy(false);
    }
  }

  async function changeMaterial(
    lineId: number, type: string, materialId: number, method: "POST" | "DELETE",
  ) {
    setLineBusy(true);
    setLineError(null);
    try {
      const r = await fetch(
        `/api/revisions/${preview.revision_id}/lines/${lineId}/materials/${type}/${materialId}/order-dismissal`,
        method === "POST"
          ? {
              method,
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ reason: reason.trim() }),
            }
          : { method },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        const code = body?.detail?.code;
        setLineError(
          code === "ALREADY_GENERATED"
            ? "A run has already ordered this material — refreshing."
            : code === "ALREADY_DISMISSED"
              ? "Someone already marked this material ordered by hand — refreshing."
              : code === "NOT_DISMISSED"
                ? "This material is no longer marked ordered by hand — refreshing."
                : `Could not ${method === "POST" ? "mark" : "undo"} the material (${r.status}).`,
        );
      } else {
        setDismissingMat(null);
        setReason("");
      }
      await afterLineChange(lineId, method === "DELETE");
    } catch {
      setLineError("Could not reach the server — nothing was changed.");
    } finally {
      setLineBusy(false);
    }
  }

  function toggle(lineId: number) {
    const next = new Set(selected);
    if (next.has(lineId)) next.delete(lineId);
    else next.add(lineId);
    setSelected(next);
    return refreshFor(next);
  }

  async function refreshFor(next: Set<number>) {
    const mine = ++refreshSeq.current;
    setRefreshError(null);
    if (next.size === 0) {
      // Nothing selected cannot be asked of the API (no ids means "all pending").
      setRefreshing(false);
      setPreview((p) => ({ ...p, groups: [], unassigned: [] }));
      return;
    }
    setRefreshing(true);
    try {
      const qs = Array.from(next).map((id) => `include_line_ids=${id}`).join("&");
      const r = await fetch(`/api/revisions/${preview.revision_id}/order-preview?${qs}`);
      if (mine !== refreshSeq.current) return;
      if (!r.ok) throw new Error(`order-preview → ${r.status}`);
      setPreview((await r.json()) as OrderPreview);
    } catch (e) {
      if (mine !== refreshSeq.current) return;
      setRefreshError(e instanceof Error ? e.message : "Could not refresh the preview");
    } finally {
      if (mine === refreshSeq.current) setRefreshing(false);
    }
  }

  // Give a supplier-less material its supplier (the narrow estimating route, not the
  // Catalog's), then re-ask the server: the material leaves "no supplier" and its
  // held-back lines become orderable.
  async function linkSupplier(material: OrderPreviewLine, supplierId: number) {
    const key = `${material.material_type}-${material.material_id}`;
    setLinkingKey(key);
    setLinkError(null);
    try {
      const r = await fetch(`/api/revisions/${preview.revision_id}/link-supplier`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          material_type: material.material_type,
          material_id: material.material_id,
          supplier_id: supplierId,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        const code = body?.detail?.code;
        setLinkError(
          code === "ALREADY_LINKED"
            ? "Someone already linked a supplier to this material — refreshing."
            : code === "UNKNOWN_SUPPLIER"
              ? "That supplier is no longer available."
              : `Could not link the supplier (${r.status}).`,
        );
      }
      // Either way the server's answer is the truth now.
      if (selected.size > 0) await refreshFor(selected);
    } catch {
      setLinkError("Could not link the supplier (network error).");
    } finally {
      setLinkingKey(null);
    }
  }

  const ready = !busy && !refreshing && !refreshError && selected.size > 0
    && (preview.groups.length > 0 || preview.unassigned.length === 0);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40">
      <div
        className="w-full max-w-lg space-y-3 rounded border border-h-line bg-white p-5 shadow-xl"
        data-testid="order-preview-dialog"
      >
        <h2 className="text-lg font-semibold text-h-ink">Generate orders</h2>
        <p className="text-sm text-h-muted">
          Tick the quote lines to order now — the rest can be generated later.
          One draft purchase order per supplier is made from the ticked lines&apos;
          material breakdown at today&apos;s catalog pricing. Review before
          creating them — each PO can still be edited in the Orderbook
          afterwards.
        </p>
        <ul
          className="max-h-36 space-y-1 overflow-y-auto rounded border border-h-line p-2 text-sm"
          data-testid="order-preview-lines"
        >
          {preview.lines.map((l) => {
            const covered = l.orders_generated_at != null;
            const byHand = l.orders_dismissed_at != null;
            const done = covered || byHand;
            return (
              <li key={l.line_id}>
               <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.has(l.line_id)}
                  disabled={done}
                  onChange={() => toggle(l.line_id)}
                  data-testid={`order-line-${l.line_id}`}
                />
                <span className={`flex-1 ${done ? "text-h-muted" : ""}`}>{l.description}</span>
                {l.held_back && selected.has(l.line_id) ? (
                  <span
                    className="whitespace-nowrap rounded-full border border-amber-300 bg-amber-50 px-1.5 text-xs text-amber-900"
                    data-testid={`order-line-held-${l.line_id}`}
                  >
                    some materials have no supplier
                  </span>
                ) : null}
                <span
                  className="whitespace-nowrap text-xs text-h-muted"
                  data-testid={byHand ? `order-line-byhand-${l.line_id}` : undefined}
                  title={byHand ? (l.orders_dismissed_reason ?? undefined) : undefined}
                >
                  {covered
                    ? `ordered ${new Date(l.orders_generated_at as string).toLocaleDateString()}`
                    : byHand
                      ? `ordered by hand ${new Date(l.orders_dismissed_at as string).toLocaleDateString()}`
                        + (l.orders_dismissed_by_name ? ` by ${l.orders_dismissed_by_name}` : "")
                        + (l.orders_dismissed_reason ? ` — ${l.orders_dismissed_reason}` : "")
                      : `× ${l.qty} ${l.unit}`}
                </span>
                {byHand ? (
                  <button
                    type="button"
                    onClick={() => void changeLine(l.line_id, "DELETE")}
                    disabled={lineBusy}
                    className="whitespace-nowrap text-xs text-h-accent underline disabled:opacity-50"
                    data-testid={`undo-dismiss-${l.line_id}`}
                  >
                    Undo
                  </button>
                ) : !covered ? (
                  <button
                    type="button"
                    onClick={() => {
                      setDismissing(dismissing === l.line_id ? null : l.line_id);
                      setDismissingMat(null);
                      setReason("");
                      setLineError(null);
                    }}
                    disabled={lineBusy}
                    className="whitespace-nowrap text-xs text-h-accent underline disabled:opacity-50"
                    data-testid={`dismiss-line-${l.line_id}`}
                  >
                    {l.materials && l.materials.length > 1 ? "All by hand…" : "Ordered by hand…"}
                  </button>
                ) : null}
               </div>
               {l.materials && l.materials.length > 1 && !covered && !byHand ? (
                <ul className="ml-6 mt-0.5 space-y-0.5" data-testid={`order-line-materials-${l.line_id}`}>
                  {l.materials.map((m) => {
                    const mKey = `${m.material_type}-${m.material_id}`;
                    return (
                      <li
                        key={mKey}
                        className="flex items-center gap-2 text-xs text-h-muted"
                        data-testid={`order-material-${l.line_id}-${mKey}`}
                      >
                        <span className="flex-1">{m.sku ?? m.description ?? mKey} × {m.qty}</span>
                        <span
                          data-testid={`order-material-state-${l.line_id}-${mKey}`}
                          title={m.orders_dismissed_reason ?? undefined}
                        >
                          {m.state === "generated"
                            ? `ordered ${new Date(m.orders_generated_at as string).toLocaleDateString()}`
                            : m.state === "dismissed"
                              ? `ordered by hand${m.orders_dismissed_by_name ? ` by ${m.orders_dismissed_by_name}` : ""}`
                                + (m.orders_dismissed_reason ? ` — ${m.orders_dismissed_reason}` : "")
                              : m.no_supplier ? "no supplier" : "to order"}
                        </span>
                        {m.state === "dismissed" ? (
                          <button
                            type="button"
                            onClick={() => void changeMaterial(l.line_id, m.material_type, m.material_id, "DELETE")}
                            disabled={lineBusy}
                            className="whitespace-nowrap text-h-accent underline disabled:opacity-50"
                            data-testid={`undo-dismiss-material-${l.line_id}-${mKey}`}
                          >
                            Undo
                          </button>
                        ) : m.state === "pending" ? (
                          <button
                            type="button"
                            onClick={() => {
                              const same = dismissingMat?.lineId === l.line_id
                                && dismissingMat.type === m.material_type && dismissingMat.id === m.material_id;
                              setDismissingMat(same ? null : { lineId: l.line_id, type: m.material_type, id: m.material_id });
                              setDismissing(null);
                              setReason("");
                              setLineError(null);
                            }}
                            disabled={lineBusy}
                            className="whitespace-nowrap text-h-accent underline disabled:opacity-50"
                            data-testid={`dismiss-material-${l.line_id}-${mKey}`}
                          >
                            Ordered by hand…
                          </button>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
               ) : null}
              </li>
            );
          })}
        </ul>
        {dismissing !== null || dismissingMat !== null ? (
          <form
            className="space-y-2 rounded border border-h-line bg-h-bg p-2 text-sm"
            data-testid="dismiss-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!reason.trim()) return;
              if (dismissingMat !== null) {
                void changeMaterial(dismissingMat.lineId, dismissingMat.type, dismissingMat.id, "POST");
              } else if (dismissing !== null) {
                void changeLine(dismissing, "POST");
              }
            }}
          >
            <label className="block text-xs text-h-muted" htmlFor="dismiss-reason">
              How was it ordered? (required — nothing in the system can see this order, so
              this note is the only record)
            </label>
            <input
              id="dismiss-reason"
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. ordered by phone from Plyco, PO 1234"
              className="w-full rounded border border-h-line bg-white px-2 py-1"
              data-testid="dismiss-reason"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={lineBusy || !reason.trim()}
                className="rounded bg-h-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                data-testid="dismiss-save"
              >
                {lineBusy ? "Saving…" : "Mark ordered by hand"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDismissing(null);
                  setDismissingMat(null);
                  setReason("");
                }}
                className="rounded border border-h-line px-3 py-1 text-xs text-h-muted"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : null}
        {lineError ? (
          <p className="text-sm text-red-800" data-testid="dismiss-error">
            {lineError}
          </p>
        ) : null}
        {refreshError ? (
          <p className="text-sm text-red-800" data-testid="order-preview-error">
            Could not refresh the preview ({refreshError}). Tick a line again to retry.
          </p>
        ) : null}
        <div
          className={`max-h-72 space-y-3 overflow-y-auto ${refreshing ? "opacity-50" : ""}`}
          data-testid="order-preview-groups"
        >
          {preview.groups.length === 0 ? (
            <p className="text-sm text-h-muted">
              {selected.size === 0
                ? "No lines ticked."
                : "Nothing to order — no ticked line has a real material link."}
            </p>
          ) : (
            preview.groups.map((g) => (
              <div key={g.supplier_id} className="rounded border border-h-line p-3" data-testid="order-preview-group">
                <div className="mb-1 flex items-center justify-between text-sm font-medium text-h-ink">
                  <span>{g.supplier_name ?? `Vendor #${g.supplier_id}`}</span>
                  <span className="rounded-full border border-h-line px-1.5 py-0.5 text-xs text-h-muted">
                    {g.category}
                  </span>
                </div>
                <ul className="space-y-0.5 text-xs text-h-muted">
                  {g.lines.map((l) => (
                    <li key={`${l.material_type}-${l.material_id}`} className="flex justify-between gap-2">
                      <span className="truncate">
                        {l.description ?? l.sku ?? "material"} × {l.qty} {l.unit}
                        {l.archived ? " (archived in catalog)" : ""}
                      </span>
                      <span className="font-mono whitespace-nowrap">{fmtMoney(l.unit_cost)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
          {preview.unassigned.length > 0 ? (
            <div className="rounded border border-amber-300 bg-amber-50 p-3">
              <div className="mb-1 text-sm font-medium text-amber-900">
                No default supplier — the lines using these are held back whole. Link a
                supplier here (or in the Catalog) and they become orderable
              </div>
              <ul className="space-y-0.5 text-xs text-amber-900">
                {preview.unassigned.map((l) => {
                  const key = `${l.material_type}-${l.material_id}`;
                  return (
                    <li key={key} className="flex items-center justify-between gap-2 py-0.5">
                      <span className="truncate">
                        {l.description ?? l.sku ?? "material"} × {l.qty} {l.unit}
                      </span>
                      <select
                        aria-label={`Link supplier for ${l.description ?? l.sku ?? "material"}`}
                        data-testid={`link-supplier-${key}`}
                        value=""
                        disabled={suppliers == null || linkingKey != null || refreshing}
                        onChange={(e) => {
                          if (e.target.value) void linkSupplier(l, Number(e.target.value));
                        }}
                        className="max-w-[10rem] rounded border border-amber-300 bg-white px-1 py-0.5 text-xs text-amber-900"
                      >
                        <option value="">{linkingKey === key ? "Linking…" : "Link supplier…"}</option>
                        {(suppliers ?? []).map((sp) => (
                          <option key={sp.vendor_id} value={sp.vendor_id}>{sp.name}</option>
                        ))}
                      </select>
                    </li>
                  );
                })}
              </ul>
              {linkError ? (
                <p className="mt-1 text-xs text-red-800" data-testid="link-supplier-error">{linkError}</p>
              ) : null}
              {suppliers == null ? (
                <p className="mt-1 text-xs text-amber-900">
                  The supplier list couldn&apos;t be read, so suppliers can&apos;t be linked from here.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
        {!refreshing && !refreshError && selected.size > 0
          && preview.groups.length === 0 && preview.unassigned.length > 0 ? (
          <p className="text-sm text-amber-900" data-testid="order-preview-nothing-orderable">
            Nothing can be generated yet — every ticked line uses a material with no
            supplier. Link a supplier to each material above (or in the Catalog); the lines
            stay orderable.
          </p>
        ) : null}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-h-line bg-white px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(Array.from(selected))}
            disabled={!ready}
            className="rounded bg-green-700 px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
            data-testid="generate-orders-confirm-btn"
          >
            {busy
              ? "Generating…"
              : preview.groups.length === 0
                ? "Mark ticked lines done (nothing to order)"
                : `Generate ${preview.groups.length} order${preview.groups.length === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>
    </div>
  );
}

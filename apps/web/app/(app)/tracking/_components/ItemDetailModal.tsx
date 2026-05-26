"use client";

import { useEffect, useMemo, useState } from "react";
import type { ItemOut, TrackingItemRow } from "@/lib/pm-types";

interface Props {
  itemId: number | null;
  items: TrackingItemRow[];
  onClose: () => void;
  onNavigate: (id: number) => void;
}

type DetailTab = "details" | "log" | "actions" | "query";

export function ItemDetailModal({ itemId, items, onClose, onNavigate }: Props) {
  const [item, setItem] = useState<ItemOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<DetailTab>("details");

  useEffect(() => {
    if (itemId === null) {
      setItem(null);
      setTab("details");
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`/api/items/${itemId}`, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<ItemOut>) : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setItem)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [itemId]);

  const nav = useMemo(() => {
    if (itemId === null) return { prev: null as number | null, next: null as number | null, idx: -1, total: 0 };
    const idx = items.findIndex((i) => i.id === itemId);
    return {
      idx,
      total: items.length,
      prev: idx > 0 ? items[idx - 1].id : null,
      next: idx >= 0 && idx < items.length - 1 ? items[idx + 1].id : null,
    };
  }, [itemId, items]);

  if (itemId === null) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-h-line bg-h-surface shadow-xl">
        {/* Title bar */}
        <header className="relative flex items-center justify-center border-b border-h-line bg-[#1f2937] px-5 py-2.5">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute left-3 top-1/2 -translate-y-1/2 rounded p-1 text-white/90 hover:bg-white/10"
          >
            ✕
          </button>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white">
            Item Details
          </h2>
        </header>

        {loading ? (
          <div className="p-10 text-center text-h-muted">Loading…</div>
        ) : error ? (
          <div className="p-10 text-center text-[#b4443d]">{error}</div>
        ) : !item ? (
          <div className="p-10 text-center text-h-muted">Not found.</div>
        ) : (
          <>
            {/* Item header strip */}
            <div className="grid grid-cols-[1fr_auto_auto] gap-3 border-b border-h-line bg-h-bg px-5 py-3">
              <div className="text-lg font-semibold text-h-ink">
                {item.description ?? "—"}
              </div>
              <div className="rounded border border-h-line bg-h-surface px-3 py-1 text-center">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
                  JID
                </div>
              </div>
              <div className="rounded border border-h-line bg-h-surface px-3 py-1 text-center">
                <div className="font-mono text-sm font-semibold text-h-ink">
                  {item.code ?? "—"}
                </div>
              </div>
            </div>

            {/* Tab bar */}
            <nav className="grid grid-cols-4 border-b border-h-line bg-h-bg">
              {(["details", "log", "actions", "query"] as DetailTab[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`border-b-2 px-4 py-2 text-sm font-medium capitalize transition ${
                    tab === t
                      ? "border-[#3f7d48] bg-h-surface text-h-ink"
                      : "border-transparent text-h-muted hover:text-h-ink"
                  }`}
                >
                  {t}
                </button>
              ))}
            </nav>

            {/* Body */}
            <div className="grid max-h-[60vh] gap-0 overflow-y-auto p-5">
              {tab === "details" ? <DetailsPanel item={item} /> : null}
              {tab === "log" ? <LogPanel item={item} /> : null}
              {tab === "actions" ? <StubPanel label="Actions" /> : null}
              {tab === "query" ? <StubPanel label="Query" /> : null}
            </div>

            {/* Footer */}
            <footer className="flex items-center justify-center gap-3 border-t border-h-line bg-h-bg px-5 py-3">
              <button
                type="button"
                onClick={() => nav.prev != null && onNavigate(nav.prev)}
                disabled={nav.prev == null}
                className="rounded border border-h-line bg-h-surface px-4 py-1.5 text-sm text-h-ink hover:bg-h-bg disabled:cursor-not-allowed disabled:opacity-40"
              >
                ‹ Previous
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded bg-[#3f7d48] px-6 py-1.5 text-sm font-semibold text-white hover:opacity-90"
              >
                CLOSE
              </button>
              <button
                type="button"
                onClick={() => nav.next != null && onNavigate(nav.next)}
                disabled={nav.next == null}
                className="rounded border border-h-line bg-h-surface px-4 py-1.5 text-sm text-h-ink hover:bg-h-bg disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next ›
              </button>
              {nav.total > 0 ? (
                <span className="ml-3 text-[11px] font-mono text-h-muted">
                  {nav.idx + 1} of {nav.total}
                </span>
              ) : null}
            </footer>
          </>
        )}
      </div>
    </div>
  );
}

function DetailsPanel({ item }: { item: ItemOut }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Left column */}
      <div className="grid gap-1">
        <Field label="Level" value={item.level} />
        <Field label="Room Number" value={item.room_no} />
        <Field label="Rm Description" value={item.room_desc} />
        <Field label="Floor Plan" value={null} disabled />
        <Field label="RLS" value={null} disabled />
        <Field label="Joiery Details" value={null} disabled />

        <CheckRow label="Painting Required?" checked={item.painting_required} />
        <CheckRow label="Solid Surface Req?" checked={item.solid_surface_required} />
        <CheckRow label="Cutlist Printed?" checked={null} disabled />

        <Field label="Group ID" value={item.group_id} mono />
        <Field label="Item ID" value={String(item.id)} mono />

        <Field
          label="Estimator Notes"
          value={item.estimator_notes}
          textarea
        />
      </div>

      {/* Right column */}
      <div className="grid gap-1">
        <Field label="SketchUp File" value={null} disabled rightPlaceholder="—" />
        <Field label="CabVision File" value={null} disabled rightPlaceholder="—" />

        <div className="mt-2 rounded border border-h-line bg-h-bg p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
            Document Register{" "}
            <span className="text-h-ink/40">(for current item)</span>
          </div>
          <div className="mt-2 grid h-48 place-items-center rounded border border-dashed border-h-line text-xs text-h-muted">
            No documents attached for v1.
          </div>
        </div>
      </div>
    </div>
  );
}

function LogPanel({ item }: { item: ItemOut }) {
  if (item.edit_log.length === 0) {
    return <div className="p-6 text-center text-h-muted">No edits recorded for this item.</div>;
  }
  return (
    <ul className="grid gap-1">
      {item.edit_log.map((row) => (
        <li
          key={row.log_id}
          className="grid grid-cols-[auto_auto_1fr] gap-x-3 rounded border border-h-line bg-h-surface px-3 py-2 text-xs"
        >
          <span className="font-mono tabular-nums text-h-muted">
            {row.ts.replace("T", " ").slice(0, 16)}
          </span>
          <span className="text-h-ink">{row.actor_name ?? "—"}</span>
          <span className="text-h-muted">
            <span className="font-mono">{row.field}</span>:{" "}
            <span className="font-mono">{row.old_value ?? "∅"}</span>{" "}
            →{" "}
            <span className="font-mono">{row.new_value ?? "∅"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function StubPanel({ label }: { label: string }) {
  return (
    <div className="grid h-40 place-items-center text-center text-h-muted">
      <div>
        <div className="text-sm font-semibold text-h-ink">{label}</div>
        <div className="mt-1 text-xs">Coming soon.</div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  disabled,
  mono,
  textarea,
  rightPlaceholder,
}: {
  label: string;
  value: string | number | null;
  disabled?: boolean;
  mono?: boolean;
  textarea?: boolean;
  rightPlaceholder?: string;
}) {
  const display = value == null || value === "" ? (rightPlaceholder ?? "—") : String(value);
  const valueClass = `flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-sm ${
    disabled ? "text-h-muted/60" : "text-h-ink"
  } ${mono ? "font-mono tabular-nums" : ""}`;
  return (
    <div className="grid grid-cols-[140px_1fr] items-start gap-2">
      <label className={`rounded bg-[#e6efe5] px-2 py-1 text-right text-xs font-medium text-h-ink ${disabled ? "opacity-60" : ""}`}>
        {label}
      </label>
      {textarea ? (
        <div className="grid grid-cols-[140px_1fr] gap-2 col-span-1">
          {/* nothing — fallthrough below */}
        </div>
      ) : null}
      {textarea ? (
        <textarea
          readOnly
          value={display}
          rows={2}
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
        />
      ) : (
        <div className={valueClass}>{display}</div>
      )}
    </div>
  );
}

function CheckRow({
  label,
  checked,
  disabled,
}: {
  label: string;
  checked: boolean | null | undefined;
  disabled?: boolean;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] items-center gap-2">
      <label className={`rounded bg-[#e6efe5] px-2 py-1 text-right text-xs font-medium text-h-ink ${disabled ? "opacity-60" : ""}`}>
        {label}
      </label>
      <div className="px-2">
        {checked == null ? (
          <span className="text-h-muted">—</span>
        ) : checked ? (
          <span className="text-[#3f7d48] text-sm">✓</span>
        ) : (
          <span className="inline-block h-3 w-3 rounded-full border border-h-line" />
        )}
      </div>
    </div>
  );
}

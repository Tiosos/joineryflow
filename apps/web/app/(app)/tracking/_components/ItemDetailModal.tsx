"use client";

import { useEffect, useMemo, useState } from "react";
import { getAttachments } from "@/lib/attachments-fetch";
import type { AttachmentSlot } from "@/lib/attachments-types";
import { listDocuments } from "@/lib/item-documents-fetch";
import type { ItemDocumentOut, ItemOut, TrackingItemRow } from "@/lib/pm-types";

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
        <ItemFiles itemId={item.id} />
      </div>
    </div>
  );
}

type Loaded<T> = { state: "loading" } | { state: "error" } | { state: "ok"; value: T };

/** SketchUp / CabVision slots and the Document Register, read-only. Editing lives on the
 *  item editor's Attachments tab. Both reads are `list:read`, the gate `GET /items/{id}`
 *  above already needs. A failed read says so rather than looking like "nothing attached". */
function ItemFiles({ itemId }: { itemId: number }) {
  const [slots, setSlots] = useState<Loaded<AttachmentSlot[]>>({ state: "loading" });
  const [docs, setDocs] = useState<Loaded<ItemDocumentOut[]>>({ state: "loading" });

  useEffect(() => {
    let stale = false; // Previous / Next changes the item: only the newest request may write
    setSlots({ state: "loading" });
    setDocs({ state: "loading" });
    getAttachments(itemId)
      .then((b) => !stale && setSlots({ state: "ok", value: b.slots }))
      .catch(() => !stale && setSlots({ state: "error" }));
    listDocuments(itemId)
      .then((d) => !stale && setDocs({ state: "ok", value: d }))
      .catch(() => !stale && setDocs({ state: "error" }));
    return () => {
      stale = true;
    };
  }, [itemId]);

  const slot = (kind: "sketchup" | "cabvision") =>
    slots.state === "ok" ? slots.value.find((s) => s.kind === kind) : undefined;

  return (
    <>
      <SlotRow label="SketchUp File" slot={slot("sketchup")} status={slots.state} />
      <SlotRow label="CabVision File" slot={slot("cabvision")} status={slots.state} />

      <div className="mt-2 rounded border border-h-line bg-h-bg p-3" data-testid="modal-register">
        <div className="flex items-baseline justify-between">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-h-muted">
            Document Register{" "}
            <span className="text-h-ink/40">(for current item)</span>
          </div>
          <a
            href={`/items/${itemId}?tab=attachments`}
            className="text-[11px] text-h-accent hover:underline"
          >
            Manage on Attachments tab →
          </a>
        </div>
        <div className="mt-2 max-h-48 overflow-y-auto rounded border border-h-line bg-h-surface">
          {docs.state === "loading" ? (
            <div className="p-4 text-center text-xs text-h-muted">Loading…</div>
          ) : docs.state === "error" ? (
            <div className="p-4 text-center text-xs text-[#b4443d]">
              Couldn&apos;t load the document register.
            </div>
          ) : docs.value.length === 0 ? (
            <div className="p-4 text-center text-xs text-h-muted">No documents in the register.</div>
          ) : (
            <ul className="divide-y divide-h-line">
              {docs.value.map((d) => (
                <li key={d.document_id} data-testid="modal-register-row" className="flex items-center gap-2 px-2 py-1.5 text-xs">
                  <span className="min-w-0 flex-1 truncate text-h-ink" title={d.original_filename ?? undefined}>
                    {d.label || d.original_filename || "—"}
                  </span>
                  <a
                    href={`/api/files/${d.file_blob_id}`}
                    target="_blank"
                    rel="noopener"
                    className="shrink-0 rounded border border-h-line px-2 py-0.5 text-h-ink hover:bg-h-bg"
                  >
                    Open
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

function SlotRow({
  label,
  slot,
  status,
}: {
  label: string;
  slot: AttachmentSlot | undefined;
  status: Loaded<unknown>["state"];
}) {
  const file = slot?.file_blob_id != null ? slot : null;
  return (
    <div className="grid grid-cols-[140px_1fr] items-start gap-2">
      <label className="rounded bg-[#e6efe5] px-2 py-1 text-right text-xs font-medium text-h-ink">
        {label}
      </label>
      <div className="flex min-w-0 items-center gap-2 rounded border border-h-line bg-h-bg px-2 py-1 text-sm">
        {file ? (
          <>
            <span className="min-w-0 flex-1 truncate text-h-ink" title={file.original_filename ?? undefined}>
              {file.original_filename}
            </span>
            <a
              href={`/api/files/${file.file_blob_id}`}
              target="_blank"
              rel="noopener"
              className="shrink-0 rounded border border-h-line px-2 py-0.5 text-xs text-h-ink hover:bg-h-surface"
            >
              Open
            </a>
          </>
        ) : status === "error" ? (
          <span className="text-xs text-[#b4443d]">Couldn&apos;t load</span>
        ) : (
          <span className="text-h-muted/60">{status === "loading" ? "…" : "—"}</span>
        )}
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

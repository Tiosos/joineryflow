"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { PM } from "@/lib/pm-fetch";
import type {
  ItemOut,
  HardwareLineOut,
  AvailabilityOut,
  AvailabilityStatus,
} from "@/lib/pm-types";

interface CartProps {
  item: ItemOut;
  availability: AvailabilityOut | null;
  onRefresh: () => void;
}

export function Cart({ item, availability, onRefresh }: CartProps) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [lines, setLines] = useState<HardwareLineOut[]>(item.hardware_lines);

  useEffect(() => {
    setLines(item.hardware_lines);
  }, [item.hardware_lines]);

  if (lines.length === 0) {
    return (
      <div className="flex-1 rounded-lg border border-h-line bg-h-surface p-8 text-center text-sm text-h-muted">
        No hardware on this item yet — add from the pantry.
      </div>
    );
  }

  const grouped = lines.reduce<Record<string, HardwareLineOut[]>>((acc, l) => {
    const key = l.catalog_supplier ?? "Other";
    return { ...acc, [key]: [...(acc[key] ?? []), l] };
  }, {});

  async function deleteLine(lineId: number) {
    let snapshot: HardwareLineOut[] = [];
    setLines((current) => {
      snapshot = current;
      return current.filter((x) => x.id !== lineId);
    });
    try {
      await PM.deleteHardwareLine(lineId);
      setError(null);
      router.refresh();
      onRefresh();
    } catch {
      setLines(snapshot);
      setError("Failed to delete line");
    }
  }

  function getAvailStatus(lineId: number): AvailabilityStatus {
    return (
      availability?.lines.find((l) => l.line_id === lineId)?.status ?? "none"
    );
  }

  return (
    <div className="flex-1 flex flex-col gap-4 rounded-lg border border-h-line bg-h-surface p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-h-muted">
        Cart
      </h3>
      {error && <p className="text-xs text-h-bad">{error}</p>}
      {Object.entries(grouped).map(([supplier, supplierLines]) => (
        <div key={supplier}>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-h-muted">
            {supplier}
          </p>
          {supplierLines.map((line) => (
            <CartLine
              key={line.id}
              line={line}
              availStatus={getAvailStatus(line.id)}
              onDelete={deleteLine}
              onError={setError}
              onRefresh={() => {
                router.refresh();
                onRefresh();
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

interface CartLineProps {
  line: HardwareLineOut;
  availStatus: AvailabilityStatus;
  onDelete: (id: number) => Promise<void>;
  onError: (msg: string) => void;
  onRefresh: () => void;
}

const AVAIL_COLOR: Record<AvailabilityStatus, string> = {
  ready: "text-h-good",
  ordered: "text-h-warn",
  none: "text-h-muted",
};

const AVAIL_LABEL: Record<AvailabilityStatus, string> = {
  ready: "ready",
  ordered: "ordered",
  none: "no orders",
};

function CartLine({
  line,
  availStatus,
  onDelete,
  onError,
  onRefresh,
}: CartLineProps) {
  const [qty, setQty] = useState(line.qty);
  const [note, setNote] = useState(line.note ?? "");
  const qtyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (qtyTimer.current) clearTimeout(qtyTimer.current);
    };
  }, []);

  function adjustQty(delta: number) {
    const next = Math.max(1, qty + delta);
    setQty(next);
    if (qtyTimer.current) clearTimeout(qtyTimer.current);
    qtyTimer.current = setTimeout(async () => {
      try {
        await PM.patchHardwareLine(line.id, { qty: next });
        onRefresh();
      } catch {
        onError("Failed to update quantity");
        setQty(qty);
      }
    }, 300);
  }

  async function patchNote() {
    const trimmed = note.trim();
    try {
      await PM.patchHardwareLine(line.id, { note: trimmed || null });
      onRefresh();
    } catch {
      onError("Failed to save note");
      setNote(line.note ?? "");
    }
  }

  return (
    <div
      data-testid="cart-line"
      className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 rounded px-2 py-1.5 hover:bg-h-bg border-b border-h-line/30 last:border-0"
    >
      {/* Description */}
      <p className="truncate text-sm text-h-ink">
        {line.catalog_description ?? "—"}
      </p>

      {/* Qty stepper */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => adjustQty(-1)}
          className="flex h-6 w-6 items-center justify-center rounded border border-h-line text-sm text-h-muted hover:text-h-ink"
        >
          −
        </button>
        <span className="w-6 text-center font-mono text-sm text-h-ink">
          {qty}
        </span>
        <button
          type="button"
          onClick={() => adjustQty(1)}
          className="flex h-6 w-6 items-center justify-center rounded border border-h-line text-sm text-h-muted hover:text-h-ink"
        >
          +
        </button>
      </div>

      {/* Note + availability */}
      <div className="flex flex-col gap-0.5">
        <input
          type="text"
          placeholder="Note…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={patchNote}
          className="w-28 rounded border border-h-line bg-h-bg px-1.5 py-0.5 text-xs text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
        />
        <span className={`text-xs ${AVAIL_COLOR[availStatus]}`}>
          {AVAIL_LABEL[availStatus]}
        </span>
      </div>

      {/* Delete */}
      <button
        type="button"
        onClick={() => onDelete(line.id)}
        aria-label="Remove hardware line"
        className="px-1 text-h-muted transition-colors hover:text-h-bad"
      >
        –
      </button>
    </div>
  );
}

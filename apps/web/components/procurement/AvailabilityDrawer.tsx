"use client";

import { useEffect, useState } from "react";
import { MaterialTypeTag } from "./MaterialTypeTag";
import { EtaPill } from "./EtaPill";
import type { MaterialType } from "@/lib/procurement-types";

interface AvailabilityLine {
  line_id: number;
  material_type: MaterialType;
  material_id: number | null;
  qty_needed: number;
  qty_allocated_to_line: number;
  qty_on_order: number;
  earliest_eta: string | null;
}

interface AvailabilityResponse {
  item_id: number;
  ready: boolean;
  blocked: boolean;
  lines: AvailabilityLine[];
}

interface Props {
  itemId: number | null;
  onClose: () => void;
}

export function AvailabilityDrawer({ itemId, onClose }: Props) {
  const [data, setData] = useState<AvailabilityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (itemId == null) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/items/${itemId}/availability`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) {
          throw new Error(`Failed (${r.status})`);
        }
        return (await r.json()) as AvailabilityResponse;
      })
      .then((j) => {
        if (cancelled) return;
        setData(j);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load availability");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [itemId]);

  if (itemId == null) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/30"
      onClick={onClose}
      data-testid="availability-drawer"
    >
      <aside
        className="h-full w-full max-w-md overflow-y-auto bg-h-surface p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-h-ink">
            Item availability
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-h-muted hover:bg-h-bg"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {loading && (
          <div className="text-sm text-h-muted">Loading…</div>
        )}
        {error && (
          <div className="rounded border border-h-bad/30 bg-h-bad/10 p-3 text-sm text-h-bad">
            {error}
          </div>
        )}
        {data && (
          <div className="space-y-3">
            <div className="text-sm">
              {data.ready ? (
                <span className="text-h-good">All hardware ready</span>
              ) : data.blocked ? (
                <span className="text-h-bad">Blocked on materials</span>
              ) : (
                <span className="text-h-muted">Pending allocation</span>
              )}
            </div>
            <ul className="space-y-2">
              {data.lines.map((l) => {
                const shortfall = Math.max(
                  0,
                  l.qty_needed - l.qty_allocated_to_line,
                );
                return (
                  <li
                    key={l.line_id}
                    className="rounded border border-h-line p-3"
                    data-testid="availability-line"
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <MaterialTypeTag type={l.material_type} />
                      <span className="font-mono text-xs text-h-muted">
                        #{l.line_id}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-1 font-mono text-xs text-h-ink">
                      <div>
                        Need: <span className="tabular-nums">{l.qty_needed}</span>
                      </div>
                      <div>
                        Alloc:{" "}
                        <span className="tabular-nums">
                          {l.qty_allocated_to_line}
                        </span>
                      </div>
                      <div>
                        On order:{" "}
                        <span className="tabular-nums">{l.qty_on_order}</span>
                      </div>
                      <div>
                        Short:{" "}
                        <span
                          className={
                            shortfall > 0
                              ? "tabular-nums text-h-bad"
                              : "tabular-nums text-h-muted"
                          }
                        >
                          {shortfall}
                        </span>
                      </div>
                    </div>
                    {l.earliest_eta && (
                      <div className="mt-2">
                        <EtaPill eta={l.earliest_eta} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}

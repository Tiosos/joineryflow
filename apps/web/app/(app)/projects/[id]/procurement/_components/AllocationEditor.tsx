"use client";

import { useEffect, useState } from "react";
import { ProcFetch } from "@/lib/procurement-fetch";
import type { AllocationListOut, AllocationOut } from "@/lib/procurement-types";

interface Props { batchId: number; canWrite: boolean; }

export function AllocationEditor({ batchId, canWrite }: Props) {
  const [data, setData]   = useState<AllocationListOut | null>(null);
  const [lineId, setLine] = useState("");
  const [qty, setQty]     = useState("1");
  const [err, setErr]     = useState<string | null>(null);

  async function refresh() {
    try { setData(await ProcFetch.listAllocations(batchId)); }
    catch (e) { setErr(String(e)); }
  }
  useEffect(() => { refresh(); }, [batchId]);

  async function add() {
    setErr(null);
    try {
      await ProcFetch.createAllocation(batchId, {
        item_hardware_line_id: Number(lineId),
        qty_allocated: Number(qty),
      });
      setLine(""); setQty("1");
      await refresh();
    } catch (e) { setErr(String(e)); }
  }

  async function del(a: AllocationOut) {
    await ProcFetch.deleteAllocation(a.allocation_id);
    await refresh();
  }

  if (!data) return <p className="text-sm text-h-muted">Loading allocations…</p>;
  const remaining = Number(data.qty_remaining);

  return (
    <div className="grid gap-2">
      <p className="text-xs text-h-muted">
        Allocated <span className="h-mono">{data.qty_allocated_total}</span> /
        received <span className="h-mono">{data.qty_received}</span> ·
        remaining <span className={["h-mono", remaining > 0 ? "text-h-warn" : "text-h-good"].join(" ")}>{remaining}</span>
      </p>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase text-h-muted">
          <tr><th className="text-left">Item</th><th className="text-right">Qty</th><th /></tr>
        </thead>
        <tbody>
          {data.allocations.map(a => (
            <tr key={a.allocation_id} className="border-t border-h-line">
              <td className="py-1">{a.item_code ?? "—"} · {a.item_description ?? ""}</td>
              <td className="text-right h-mono">{Number(a.qty_allocated)}</td>
              <td className="text-right">
                {canWrite && (
                  <button onClick={() => del(a)} className="text-h-bad hover:underline" aria-label="Delete allocation">
                    remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {canWrite && (
        <div className="flex gap-2">
          <input
            type="number"
            value={lineId}
            onChange={e => setLine(e.target.value)}
            placeholder="line_id"
            className="w-32 rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
            data-testid="alloc-line-id"
          />
          <input
            type="number"
            value={qty}
            onChange={e => setQty(e.target.value)}
            placeholder="qty"
            className="w-24 rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
            data-testid="alloc-qty"
          />
          <button
            onClick={add}
            data-testid="alloc-add"
            className="rounded bg-h-accent px-2 py-1 text-sm text-white"
          >+ Allocate</button>
          {err && <span className="text-xs text-h-bad">{err}</span>}
        </div>
      )}
    </div>
  );
}

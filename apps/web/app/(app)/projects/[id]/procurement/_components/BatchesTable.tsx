"use client";

import { useEffect, useState } from "react";
import type { BatchOut } from "@/lib/procurement-types";
import { ProcFetch } from "@/lib/procurement-fetch";
import { BatchStatusPill } from "@/components/procurement/BatchStatusPill";
import { EtaPill } from "@/components/procurement/EtaPill";
import { BatchDrawer } from "./BatchDrawer";

interface Props {
  projectId: number;
  canWrite: boolean;
  sp: Record<string, string | undefined>;
}

export function BatchesTable({ projectId, canWrite, sp }: Props) {
  const [rows, setRows] = useState<BatchOut[]>([]);
  const [editId, setEditId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  const orderInitial = sp.action === "order" && sp.material_type && sp.material_id
    ? {
        material_type: sp.material_type as BatchOut["material_type"],
        material_id:   Number(sp.material_id),
      }
    : undefined;

  async function refresh() {
    const qs = new URLSearchParams({ project_id: String(projectId) });
    setRows((await ProcFetch.listBatches(qs)).batches);
  }
  useEffect(() => { refresh(); }, [projectId]);
  // Auto-open the create drawer if we landed via "Order more"
  useEffect(() => { if (orderInitial) setCreating(true); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  return (
    <>
      <div className="mb-3 flex justify-end">
        {canWrite && (
          <button
            data-testid="new-batch"
            onClick={() => setCreating(true)}
            className="rounded bg-h-accent px-3 py-1 text-sm text-white"
          >+ New batch</button>
        )}
      </div>
      <table className="w-full text-sm">
        <thead className="bg-h-bg text-xs uppercase text-h-muted">
          <tr>
            <th className="px-2 py-1 text-left">PO</th>
            <th className="px-2 py-1 text-left">Supplier</th>
            <th className="px-2 py-1 text-left">Material</th>
            <th className="px-2 py-1 text-right">Ordered</th>
            <th className="px-2 py-1 text-right">Received</th>
            <th className="px-2 py-1 text-right">Allocated</th>
            <th className="px-2 py-1 text-left">ETA</th>
            <th className="px-2 py-1 text-left">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(b => (
            <tr
              key={b.batch_id}
              className="border-t border-h-line cursor-pointer hover:bg-h-bg"
              onClick={() => setEditId(b.batch_id)}
              data-testid="batch-row"
            >
              <td className="px-2 py-1 h-mono">{b.po_ref ?? "—"}</td>
              <td className="px-2 py-1">{b.supplier ?? "—"}</td>
              <td className="px-2 py-1">{b.material_type} #{b.material_id}</td>
              <td className="px-2 py-1 text-right h-mono">{Number(b.qty_ordered)}</td>
              <td className="px-2 py-1 text-right h-mono">{Number(b.qty_received)}</td>
              <td className="px-2 py-1 text-right h-mono">{Number(b.qty_allocated)}</td>
              <td className="px-2 py-1"><EtaPill eta={b.eta_date} /></td>
              <td className="px-2 py-1"><BatchStatusPill status={b.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {(editId != null || creating) && (
        <BatchDrawer
          projectId={projectId}
          batchId={editId}
          initial={creating ? orderInitial : undefined}
          canWrite={canWrite}
          onClose={() => { setEditId(null); setCreating(false); }}
          onSaved={refresh}
        />
      )}
    </>
  );
}

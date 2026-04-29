"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { BatchStatusPill } from "@/components/procurement/BatchStatusPill";
import { EtaPill } from "@/components/procurement/EtaPill";
import { ProcFetch } from "@/lib/procurement-fetch";
import type { QueueRow } from "@/lib/procurement-types";

const STATUSES = ["OPEN","IN_TRANSIT","DELIVERED","CANCELLED"] as const;

interface Props { initial: { status?: string; supplier?: string; project_id?: string; }; }

export function QueueClient({ initial }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const [rows, setRows] = useState<QueueRow[]>([]);
  const [err, setErr]   = useState<string | null>(null);
  const status   = params.get("status")   ?? initial.status   ?? "";
  const supplier = params.get("supplier") ?? initial.supplier ?? "";

  useEffect(() => {
    const qs = new URLSearchParams();
    if (status)   qs.set("status", status);
    if (supplier) qs.set("supplier", supplier);
    ProcFetch.queue(qs)
      .then(b => setRows(b.rows))
      .catch(e => setErr(String(e)));
  }, [status, supplier]);

  function setParam(k: string, v: string) {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v); else next.delete(k);
    router.push(`?${next.toString()}`);
  }

  const grouped = new Map<string, QueueRow[]>();
  for (const r of rows) {
    const key = r.supplier ?? "(no supplier)";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(r);
  }

  return (
    <>
      <div className="flex flex-wrap gap-2 rounded-lg border border-h-line bg-h-surface p-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-h-muted">Status</span>
          <select
            value={status}
            onChange={e => setParam("status", e.target.value)}
            className="rounded border border-h-line bg-h-bg px-2 py-1"
          >
            <option value="">All</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <input
          type="search"
          value={supplier}
          onChange={e => setParam("supplier", e.target.value)}
          placeholder="Supplier"
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
        />
      </div>

      {err && <p className="text-sm text-h-bad">{err}</p>}

      {[...grouped.entries()].map(([sup, batches]) => (
        <section key={sup} className="rounded-lg border border-h-line bg-h-surface">
          <h2 className="border-b border-h-line px-3 py-2 text-sm font-semibold text-h-ink">{sup}</h2>
          <table className="w-full text-sm">
            <thead className="bg-h-bg text-xs uppercase text-h-muted">
              <tr>
                <th className="px-2 py-1 text-left">PO</th>
                <th className="px-2 py-1 text-left">Project</th>
                <th className="px-2 py-1 text-left">Material</th>
                <th className="px-2 py-1 text-right">Ordered</th>
                <th className="px-2 py-1 text-right">Received</th>
                <th className="px-2 py-1 text-left">ETA</th>
                <th className="px-2 py-1 text-left">Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {batches.map(b => (
                <tr key={b.batch_id} className="border-t border-h-line">
                  <td className="px-2 py-1 h-mono">{b.po_ref ?? "—"}</td>
                  <td className="px-2 py-1">{b.project_code} · {b.project_name}</td>
                  <td className="px-2 py-1">{b.material_name ?? `${b.material_type} #${b.material_id}`}</td>
                  <td className="px-2 py-1 text-right h-mono">{Number(b.qty_ordered)}</td>
                  <td className="px-2 py-1 text-right h-mono">{Number(b.qty_received)}</td>
                  <td className="px-2 py-1"><EtaPill eta={b.eta_date} /></td>
                  <td className="px-2 py-1"><BatchStatusPill status={b.status} /></td>
                  <td className="px-2 py-1 text-right">
                    <Link
                      href={`/projects/${b.project_id}/procurement?tab=batches&batch_id=${b.batch_id}`}
                      className="text-h-accent hover:underline"
                    >Open</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </>
  );
}

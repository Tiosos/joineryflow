"use client";

import { useEffect, useState } from "react";
import type { ProjectMaterialsOut, MaterialType } from "@/lib/procurement-types";
import { ProcFetch } from "@/lib/procurement-fetch";
import { ShortfallPill } from "@/components/procurement/ShortfallPill";
import { EtaPill } from "@/components/procurement/EtaPill";
import { MaterialTypeTag } from "@/components/procurement/MaterialTypeTag";

const TYPES: MaterialType[] = ["BOARD","HARDWARE","CUSTOM","BENCHTOP","APPLIANCE","HIRE"];

interface Props {
  projectId: number;
  canWrite: boolean;
  sp: Record<string, string | undefined>;
}

export function ProjectMaterialsTable({ projectId }: Props) {
  const [data, setData] = useState<ProjectMaterialsOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<MaterialType>>(new Set(TYPES));

  useEffect(() => {
    let alive = true;
    ProcFetch.projectMaterials(projectId)
      .then(d => { if (alive) setData(d); })
      .catch(e => { if (alive) setErr(String(e)); });
    return () => { alive = false; };
  }, [projectId]);

  if (err)   return <p className="text-sm text-h-bad">{err}</p>;
  if (!data) return <p className="text-sm text-h-muted">Loading…</p>;

  const grouped = Object.fromEntries(
    TYPES.map(t => [t, data.rows.filter(r => r.material_type === t)])
  ) as Record<MaterialType, ProjectMaterialsOut["rows"]>;

  function toggle(t: MaterialType) {
    const next = new Set(open);
    next.has(t) ? next.delete(t) : next.add(t);
    setOpen(next);
  }

  return (
    <div className="grid gap-4">
      {TYPES.map(t => {
        const rows = grouped[t];
        if (rows.length === 0) return null;
        const isOpen = open.has(t);
        return (
          <section key={t} className="rounded-lg border border-h-line bg-h-surface">
            <button
              type="button"
              onClick={() => toggle(t)}
              className="flex w-full items-center justify-between border-b border-h-line px-3 py-2 text-left"
            >
              <span className="flex items-center gap-2">
                <MaterialTypeTag type={t} />
                <span className="text-sm text-h-muted">{rows.length} item(s)</span>
              </span>
              <span className="text-h-muted">{isOpen ? "▾" : "▸"}</span>
            </button>
            {isOpen && (
              <table className="w-full text-sm">
                <thead className="bg-h-bg text-xs uppercase text-h-muted">
                  <tr>
                    <th className="px-2 py-1 text-left">Material</th>
                    <th className="px-2 py-1 text-right">Demand</th>
                    <th className="px-2 py-1 text-right">On order</th>
                    <th className="px-2 py-1 text-right">Received</th>
                    <th className="px-2 py-1 text-right">Allocated</th>
                    <th className="px-2 py-1 text-left">Shortfall</th>
                    <th className="px-2 py-1 text-left">ETA</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={`${r.material_type}-${r.material_id}`} className="border-t border-h-line">
                      <td className="px-2 py-1">
                        {r.name}
                        {r.sku ? <span className="ml-2 h-mono text-xs text-h-muted">{r.sku}</span> : null}
                      </td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_demand)}</td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_on_order)}</td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_received)}</td>
                      <td className="px-2 py-1 text-right h-mono">{Number(r.qty_allocated)}</td>
                      <td className="px-2 py-1"><ShortfallPill qty={Number(r.shortfall)} /></td>
                      <td className="px-2 py-1"><EtaPill eta={r.earliest_eta} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}
    </div>
  );
}

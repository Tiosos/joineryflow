"use client";

import { useEffect, useState } from "react";

import { deleteCvMapping, listCvMappings } from "@/lib/catalog-fetch";
import type { CvMappingListResp } from "@/lib/catalog-types";

import NewMappingDialog from "./NewMappingDialog";

interface Props { canWrite: boolean; }

export default function MappingPanel({ canWrite }: Props) {
  const [list, setList] = useState<CvMappingListResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setLoading(true); setErr(null);
    listCvMappings()
      .then(setList)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [tick]);

  const onDelete = async (mid: number) => {
    if (!window.confirm("Delete this mapping?")) return;
    try { await deleteCvMapping(mid); setTick((n) => n + 1); }
    catch (e) { window.alert(String(e)); }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        {canWrite && (
          <button onClick={() => setNewOpen(true)}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm text-white">
            + New mapping
          </button>
        )}
      </div>
      {loading && <p className="text-sm text-h-muted">Loading…</p>}
      {err && <p className="text-sm text-rose-700">{err}</p>}
      <div className="overflow-x-auto rounded border border-h-line">
        <table className="min-w-full text-sm">
          <thead className="bg-h-surface text-h-muted">
            <tr className="text-left">
              <th className="px-3 py-2">CV code</th>
              <th className="px-3 py-2">Target table</th>
              <th className="px-3 py-2">Target description</th>
              <th className="px-3 py-2">Notes</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {list?.rows.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-h-muted">No mappings yet.</td></tr>
            )}
            {(list?.rows ?? []).map((r) => (
              <tr key={r.cv_material_mapping_id} className="border-t border-h-line">
                <td className="px-3 py-1 font-mono">{r.cv_code}</td>
                <td className="px-3 py-1">{r.target_material_table}</td>
                <td className="px-3 py-1">{r.target_description ?? "—"}</td>
                <td className="px-3 py-1 text-h-muted">{r.notes ?? ""}</td>
                <td className="px-3 py-1">
                  {canWrite && (
                    <button onClick={() => onDelete(r.cv_material_mapping_id)}
                            className="text-xs text-rose-700 hover:underline">
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {newOpen && (
        <NewMappingDialog
          onClose={() => setNewOpen(false)}
          onCreated={() => { setNewOpen(false); setTick((n) => n + 1); }}
        />
      )}
    </div>
  );
}

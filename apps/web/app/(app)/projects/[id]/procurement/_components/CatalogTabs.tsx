"use client";

import { useEffect, useState } from "react";

const TYPES = ["board","hardware","custom_made","benchtop","appliance","hire"] as const;
type CatType = typeof TYPES[number];

// Correct field mappings per API (Task 11) — all use 'description', hire has 'project_id'
const CREATE_FIELDS: Record<CatType, string[]> = {
  board:       ["code", "description", "sku"],
  hardware:    ["sku", "description"],
  custom_made: ["internal_ref", "description", "sku"],
  benchtop:    ["slab_id", "description", "sku"],
  appliance:   ["model_number", "description", "sku"],
  hire:        ["contract_ref", "project_id", "description", "sku"],
};

interface Props {
  canWrite: boolean;
  catalogType?: string;
}

export function CatalogTabs({ canWrite, catalogType }: Props) {
  const initial = (TYPES as readonly string[]).includes(catalogType ?? "")
    ? (catalogType as CatType) : "hardware";
  const [type, setType] = useState<CatType>(initial);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    try {
      const r = await fetch(`/api/catalogs/${type}`, { credentials: "include" });
      if (!r.ok) throw new Error(await r.text());
      setRows((await r.json()).rows);
    } catch (e) { setErr(String(e)); }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [type]);

  async function create() {
    // Coerce project_id to number for hire type
    const payload = { ...draft };
    if (type === "hire" && payload.project_id) {
      payload.project_id = String(Number(payload.project_id));
    }

    const r = await fetch(`/api/catalogs/${type}`, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) { setErr(await r.text()); return; }
    setDraft({});
    refresh();
  }

  return (
    <div className="grid gap-3">
      <nav className="flex gap-1 border-b border-h-line">
        {TYPES.map(t => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={[
              "px-3 py-2 text-sm capitalize",
              t === type ? "border-b-2 border-h-accent text-h-ink" : "text-h-muted hover:text-h-ink",
            ].join(" ")}
          >{t.replace("_"," ")}</button>
        ))}
      </nav>

      {err && <p className="text-sm text-h-bad">{err}</p>}

      <table className="w-full text-sm">
        <thead className="bg-h-bg text-xs uppercase text-h-muted">
          <tr>
            {Object.keys(rows[0] ?? {}).filter(k => k !== "type").map(k => (
              <th key={k} className="px-2 py-1 text-left">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-h-line">
              {Object.entries(r).filter(([k]) => k !== "type").map(([k,v]) => (
                <td key={k} className="px-2 py-1">{String(v ?? "—")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {canWrite && (
        <div className="flex gap-2">
          {CREATE_FIELDS[type].map(f => (
            <input
              key={f}
              value={draft[f] ?? ""}
              onChange={e => setDraft(d => ({ ...d, [f]: e.target.value }))}
              placeholder={f === "project_id" ? "project_id (numeric)" : f}
              className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm"
            />
          ))}
          <button onClick={create} className="rounded bg-h-accent px-3 py-1 text-sm text-white">+ Add</button>
        </div>
      )}
    </div>
  );
}

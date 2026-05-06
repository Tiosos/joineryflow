"use client";

import { useEffect, useState } from "react";

import { createCvMapping, listCatalog } from "@/lib/catalog-fetch";
import type { CatalogRow, CatalogSlug, CatalogTable } from "@/lib/catalog-types";

interface Props {
  onClose: () => void;
  onCreated: () => void;
}

const TABLE_OPTIONS: { table: CatalogTable; slug: CatalogSlug; label: string }[] = [
  { table: "board_materials",    slug: "board-materials",    label: "Board" },
  { table: "hardware_materials", slug: "hardware-materials", label: "Hardware" },
  { table: "custom_made",        slug: "custom-made",        label: "Custom" },
  { table: "benchtop_materials", slug: "benchtop-materials", label: "Benchtop" },
  { table: "appliances",         slug: "appliances",         label: "Appliances" },
  { table: "equipment_hire",     slug: "equipment-hire",     label: "Equipment Hire" },
];

export default function NewMappingDialog(p: Props) {
  const [cvCode, setCvCode] = useState("");
  const [table, setTable] = useState<CatalogTable>("board_materials");
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<CatalogRow[]>([]);
  const [pickedId, setPickedId] = useState<number | null>(null);
  const [pickedLabel, setPickedLabel] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const slug = TABLE_OPTIONS.find((o) => o.table === table)!.slug;
    listCatalog({ slug, q: search || null })
      .then((r) => setResults(r.rows))
      .catch(() => setResults([]));
  }, [table, search]);

  const onPick = (r: CatalogRow) => {
    setPickedId((r.material_id ?? r.hire_id) as number);
    setPickedLabel(`${r.description} · ${r.sku}`);
  };

  const onSubmit = async () => {
    if (!cvCode || pickedId == null) {
      setErr("CV code and a target row are required"); return;
    }
    setBusy(true); setErr(null);
    try {
      await createCvMapping({
        cv_code: cvCode,
        target_material_table: table,
        target_material_id: pickedId,
        notes: notes || null,
      });
      p.onCreated();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/50">
      <div className="max-h-[80vh] w-[560px] overflow-auto rounded-md bg-h-surface p-6 text-h-ink">
        <h2 className="mb-4 text-lg font-semibold">+ New CV mapping</h2>
        <div className="space-y-3">
          <Field label="CV code">
            <input value={cvCode} onChange={(e) => setCvCode(e.target.value)}
                   placeholder="e.g. 18-PB"
                   className="w-full rounded border border-h-line px-2 py-1 text-sm font-mono" />
          </Field>
          <Field label="Target table">
            <select value={table} onChange={(e) => {
              setTable(e.target.value as CatalogTable);
              setPickedId(null); setPickedLabel(null);
            }} className="w-full rounded border border-h-line px-2 py-1 text-sm">
              {TABLE_OPTIONS.map((o) => (
                <option key={o.table} value={o.table}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Search target">
            <input value={search} onChange={(e) => setSearch(e.target.value)}
                   placeholder="Type description or SKU…"
                   className="w-full rounded border border-h-line px-2 py-1 text-sm" />
          </Field>
          {pickedLabel && (
            <div className="rounded border border-h-accent/30 bg-h-accent/10 px-2 py-1 text-xs">
              Picked: <span className="font-medium">{pickedLabel}</span>
            </div>
          )}
          <div className="max-h-40 overflow-y-auto rounded border border-h-line">
            {results.length === 0 && (
              <p className="px-3 py-2 text-xs text-h-muted">No matches.</p>
            )}
            {results.slice(0, 20).map((r) => {
              const id = (r.material_id ?? r.hire_id) as number;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => onPick(r)}
                  className={`block w-full px-3 py-1 text-left text-sm hover:bg-h-surface ${
                    pickedId === id ? "bg-h-accent/15" : ""
                  }`}
                >
                  <span className="font-medium">{r.description}</span>{" "}
                  <span className="font-mono text-xs text-h-muted">{r.sku}</span>
                </button>
              );
            })}
          </div>
          <Field label="Notes (optional)">
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                      className="h-20 w-full rounded border border-h-line px-2 py-1 text-sm" />
          </Field>
        </div>
        {err && <p className="mt-3 text-xs text-rose-700">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={p.onClose} className="rounded border border-h-line px-3 py-1 text-sm">Cancel</button>
          <button onClick={onSubmit} disabled={busy || !cvCode || pickedId == null}
                  className="rounded bg-h-accent px-3 py-1 text-sm text-white disabled:opacity-50">
            {busy ? "Saving…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-h-muted">{label}</span>
      {children}
    </label>
  );
}

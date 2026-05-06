"use client";

import { useState } from "react";

import { createRow } from "@/lib/catalog-fetch";
import type { CatalogSlug } from "@/lib/catalog-types";

import type { CatalogTab } from "./CatalogClient";

interface Project { id: number; project_code: string; name: string; }

interface Props {
  tab: CatalogTab;
  slug: CatalogSlug;
  projects: Project[];
  onClose: () => void;
  onCreated: () => void;
}

const LEGACY_FIELD: Record<Exclude<CatalogTab, "cv-mappings">, { key: string; label: string } | null> = {
  board: { key: "code", label: "Code" },
  hardware: null,
  custom_made: { key: "internal_ref", label: "Internal ref" },
  benchtop: { key: "slab_id", label: "Slab id" },
  appliance: { key: "model_number", label: "Model number" },
  hire: { key: "contract_ref", label: "Contract ref" },
};

export default function NewCatalogRowDialog(p: Props) {
  if (p.tab === "cv-mappings") return null;
  const legacy = LEGACY_FIELD[p.tab];

  const [description, setDescription] = useState("");
  const [sku, setSku] = useState("");
  const [legacyVal, setLegacyVal] = useState("");
  const [supplier, setSupplier] = useState("");
  const [leadTime, setLeadTime] = useState("");
  const [synonyms, setSynonyms] = useState("");
  const [projectId, setProjectId] = useState<number | "">(p.tab === "hire" ? (p.projects[0]?.id ?? "") : "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async () => {
    setBusy(true); setErr(null);
    const body: Record<string, unknown> = {
      description, sku,
      synonyms: synonyms.split(/\s*,\s*/).filter(Boolean),
    };
    if (legacy) body[legacy.key] = legacyVal;
    if (supplier) body.default_supplier = supplier;
    if (leadTime !== "") body.default_lead_time_days = Number(leadTime);
    if (p.tab === "hire") {
      if (projectId === "") { setErr("Project is required"); setBusy(false); return; }
      body.project_id = projectId;
    }
    try {
      await createRow(p.slug, body);
      p.onCreated();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/50">
      <div className="w-[480px] rounded-md bg-h-surface p-6 text-h-ink">
        <h2 className="mb-4 text-lg font-semibold">+ New {p.tab}</h2>
        <div className="space-y-3">
          <Field label="Description">
            <input value={description} onChange={(e) => setDescription(e.target.value)}
                   className="w-full rounded border border-h-line px-2 py-1 text-sm" />
          </Field>
          <Field label="SKU">
            <input value={sku} onChange={(e) => setSku(e.target.value)}
                   className="w-full rounded border border-h-line px-2 py-1 text-sm font-mono" />
          </Field>
          {legacy && (
            <Field label={legacy.label}>
              <input value={legacyVal} onChange={(e) => setLegacyVal(e.target.value)}
                     className="w-full rounded border border-h-line px-2 py-1 text-sm" />
            </Field>
          )}
          <Field label="Default supplier">
            <input value={supplier} onChange={(e) => setSupplier(e.target.value)}
                   className="w-full rounded border border-h-line px-2 py-1 text-sm" />
          </Field>
          <Field label="Default lead time (days)">
            <input type="number" value={leadTime} onChange={(e) => setLeadTime(e.target.value)}
                   className="w-full rounded border border-h-line px-2 py-1 text-sm" />
          </Field>
          <Field label="Synonyms (comma-separated)">
            <input value={synonyms} onChange={(e) => setSynonyms(e.target.value)}
                   className="w-full rounded border border-h-line px-2 py-1 text-sm" />
          </Field>
          {p.tab === "hire" && (
            <Field label="Project">
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : "")}
                className="w-full rounded border border-h-line px-2 py-1 text-sm"
              >
                <option value="">Pick a project…</option>
                {p.projects.map((pp) => (
                  <option key={pp.id} value={pp.id}>{pp.project_code} — {pp.name}</option>
                ))}
              </select>
            </Field>
          )}
        </div>
        {err && <p className="mt-3 text-xs text-rose-700">{err}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={p.onClose} className="rounded border border-h-line px-3 py-1 text-sm">Cancel</button>
          <button onClick={onSubmit} disabled={busy || !description || !sku || (legacy != null && !legacyVal)}
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

"use client";

import { useState } from "react";

import { createRow } from "@/lib/catalog-fetch";
import type { CatalogSlug, SupplierOption } from "@/lib/catalog-types";

import { BOARD_TEXT_FIELDS } from "./boardFields";
import { EDGING_NUMBER_FIELDS, EDGING_TEXT_FIELDS } from "./edgingFields";
import { BENCHTOP_NUMBER_FIELDS, BENCHTOP_TEXT_FIELDS } from "./benchtopFields";
import { GLASS_NUMBER_FIELDS, GLASS_TEXT_FIELDS } from "./glassFields";
import { TIMBER_NUMBER_FIELDS, TIMBER_TEXT_FIELDS } from "./timberFields";
import { CUSTOM_TEXT_FIELDS } from "./customFields";
import { HARDWARE_TEXT_FIELDS } from "./hardwareFields";
import type { MaterialTab } from "./CatalogClient";

interface Project { id: number; project_code: string; name: string; }

interface Props {
  tab: MaterialTab;
  slug: CatalogSlug;
  /** The type of the tab the item is added from; the new item starts with it. */
  productType?: string | null;
  projects: Project[];
  /** null while loading or when the list could not be read (the picker is then disabled). */
  suppliers: SupplierOption[] | null;
  onClose: () => void;
  onCreated: () => void;
}

const LEGACY_FIELD: Record<MaterialTab, { key: string; label: string } | null> = {
  board: { key: "code", label: "Code" },
  hardware: null,
  custom_made: { key: "internal_ref", label: "Internal ref" },
  benchtop: { key: "slab_id", label: "Slab id" },
  appliance: { key: "model_number", label: "Model number" },
  hire: { key: "contract_ref", label: "Contract ref" },
  edging: null,
  glass: null,
  timber: null,
};

export default function NewCatalogRowDialog(p: Props) {
  // Parent (CatalogClient) gates rendering on tab !== "cv-mappings".
  const legacy = LEGACY_FIELD[p.tab];

  const [description, setDescription] = useState("");
  const [sku, setSku] = useState("");
  const [legacyVal, setLegacyVal] = useState("");
  const [supplier, setSupplier] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [leadTime, setLeadTime] = useState("");
  const [synonyms, setSynonyms] = useState("");
  const [projectId, setProjectId] = useState<number | "">(p.tab === "hire" ? (p.projects[0]?.id ?? "") : "");
  const [boardVals, setBoardVals] = useState<Record<string, string>>({});
  const [edgingVals, setEdgingVals] = useState<Record<string, string>>({});
  const [glued, setGlued] = useState(false);
  const [glassVals, setGlassVals] = useState<Record<string, string>>({});
  const [timberVals, setTimberVals] = useState<Record<string, string>>({});
  const [shaped, setShaped] = useState(false);
  const [benchVals, setBenchVals] = useState<Record<string, string>>({});
  const [hwVals, setHwVals] = useState<Record<string, string>>({});
  const [customVals, setCustomVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async () => {
    setBusy(true); setErr(null);
    const body: Record<string, unknown> = {
      description, sku,
      synonyms: synonyms.split(/\s*,\s*/).filter(Boolean),
    };
    if (legacy) body[legacy.key] = legacyVal;
    if (p.productType) body.product_type = p.productType;
    if (p.tab === "board") for (const f of BOARD_TEXT_FIELDS) if (boardVals[f.key]?.trim()) body[f.key] = boardVals[f.key].trim();
    if (p.tab === "edging") {
      for (const f of EDGING_TEXT_FIELDS) if (edgingVals[f.key]?.trim()) body[f.key] = edgingVals[f.key].trim();
      for (const f of EDGING_NUMBER_FIELDS) if (edgingVals[f.key]?.trim()) body[f.key] = Number(edgingVals[f.key]);
      body.glued = glued;
    }
    if (p.tab === "glass") {
      for (const f of GLASS_TEXT_FIELDS) if (glassVals[f.key]?.trim()) body[f.key] = glassVals[f.key].trim();
      for (const f of GLASS_NUMBER_FIELDS) if (glassVals[f.key]?.trim()) body[f.key] = Number(glassVals[f.key]);
      body.shaped = shaped;
    }
    if (p.tab === "timber") {
      for (const f of TIMBER_TEXT_FIELDS) if (timberVals[f.key]?.trim()) body[f.key] = timberVals[f.key].trim();
      for (const f of TIMBER_NUMBER_FIELDS) if (timberVals[f.key]?.trim()) body[f.key] = Number(timberVals[f.key]);
    }
    if (p.tab === "hardware") for (const f of HARDWARE_TEXT_FIELDS) if (hwVals[f.key]?.trim()) body[f.key] = hwVals[f.key].trim();
    if (p.tab === "custom_made") for (const f of CUSTOM_TEXT_FIELDS) if (customVals[f.key]?.trim()) body[f.key] = customVals[f.key].trim();
    if (p.tab === "benchtop") {
      for (const f of BENCHTOP_TEXT_FIELDS) if (benchVals[f.key]?.trim()) body[f.key] = benchVals[f.key].trim();
      for (const f of BENCHTOP_NUMBER_FIELDS) if (benchVals[f.key]?.trim()) body[f.key] = Number(benchVals[f.key]);
      body.shaped = shaped;
    }
    if (supplier) body.default_supplier = supplier;
    if (supplierId) body.default_supplier_id = Number(supplierId);
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
      <div className="max-h-[90vh] w-[480px] overflow-y-auto rounded-md bg-h-surface p-6 text-h-ink">
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
          {p.tab === "hardware" && HARDWARE_TEXT_FIELDS.map((f) => (
            <Field key={f.key} label={f.label}>
              <input value={hwVals[f.key] ?? ""} onChange={(e) => setHwVals((v) => ({ ...v, [f.key]: e.target.value }))}
                     className="w-full rounded border border-h-line px-2 py-1 text-sm" />
            </Field>
          ))}
          {p.tab === "custom_made" && CUSTOM_TEXT_FIELDS.map((f) => (
            <Field key={f.key} label={f.label}>
              <input value={customVals[f.key] ?? ""} onChange={(e) => setCustomVals((v) => ({ ...v, [f.key]: e.target.value }))}
                     className="w-full rounded border border-h-line px-2 py-1 text-sm" />
            </Field>
          ))}
          {p.tab === "benchtop" && (
            <>
              {BENCHTOP_TEXT_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input value={benchVals[f.key] ?? ""} onChange={(e) => setBenchVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
              {BENCHTOP_NUMBER_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input type="number" step={f.step} value={benchVals[f.key] ?? ""}
                         onChange={(e) => setBenchVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
              <Field label="Shaped">
                <input type="checkbox" checked={shaped} onChange={(e) => setShaped(e.target.checked)} />
              </Field>
            </>
          )}
          {p.tab === "glass" && (
            <>
              {GLASS_TEXT_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input value={glassVals[f.key] ?? ""} onChange={(e) => setGlassVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
              {GLASS_NUMBER_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input type="number" step="0.01" value={glassVals[f.key] ?? ""}
                         onChange={(e) => setGlassVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
              <Field label="Shaped">
                <input type="checkbox" checked={shaped} onChange={(e) => setShaped(e.target.checked)} />
              </Field>
            </>
          )}
          {p.tab === "timber" && (
            <>
              {TIMBER_TEXT_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input value={timberVals[f.key] ?? ""} onChange={(e) => setTimberVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
              {TIMBER_NUMBER_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input type="number" step="0.01" value={timberVals[f.key] ?? ""}
                         onChange={(e) => setTimberVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
            </>
          )}
          {p.tab === "edging" && (
            <>
              {EDGING_TEXT_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input value={edgingVals[f.key] ?? ""} onChange={(e) => setEdgingVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
              {EDGING_NUMBER_FIELDS.map((f) => (
                <Field key={f.key} label={f.label}>
                  <input type="number" step="0.01" value={edgingVals[f.key] ?? ""}
                         onChange={(e) => setEdgingVals((v) => ({ ...v, [f.key]: e.target.value }))}
                         className="w-full rounded border border-h-line px-2 py-1 text-sm" />
                </Field>
              ))}
              <Field label="Glued">
                <input type="checkbox" checked={glued} onChange={(e) => setGlued(e.target.checked)} />
              </Field>
            </>
          )}
          {p.tab === "board" && BOARD_TEXT_FIELDS.map((f) => (
            <Field key={f.key} label={f.label}>
              <input value={boardVals[f.key] ?? ""} onChange={(e) => setBoardVals((v) => ({ ...v, [f.key]: e.target.value }))}
                     className="w-full rounded border border-h-line px-2 py-1 text-sm" />
            </Field>
          ))}
          <Field label="Default supplier">
            <input value={supplier} onChange={(e) => setSupplier(e.target.value)}
                   className="w-full rounded border border-h-line px-2 py-1 text-sm" />
          </Field>
          <Field label="Supplier link">
            <select
              aria-label="Supplier link"
              value={supplierId}
              disabled={p.suppliers == null}
              onChange={(e) => setSupplierId(e.target.value)}
              className="w-full rounded border border-h-line px-2 py-1 text-sm"
            >
              <option value="">Not linked</option>
              {(p.suppliers ?? []).map((s) => (
                <option key={s.vendor_id} value={s.vendor_id}>
                  {s.name}{s.status && s.status !== "Active" ? ` (${s.status.toLowerCase()})` : ""}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-h-muted">
              {p.suppliers == null
                ? "The supplier list couldn't be read, so this row will start unlinked."
                : "Generate Orders orders from the linked supplier; an unlinked row holds its quote lines back."}
            </span>
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

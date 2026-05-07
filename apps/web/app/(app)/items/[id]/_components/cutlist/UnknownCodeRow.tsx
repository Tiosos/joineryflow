"use client";

import { useState } from "react";
import type {
  CatalogTable,
  CvCommitResolution,
  CvUnknownCode,
  SimpleCatalogTable,
} from "@/lib/cv-types";

type Mode = "use_existing" | "create_new" | "skip" | null;

const SIMPLE_TABLES: SimpleCatalogTable[] = [
  "board_materials",
  "hardware_materials",
  "custom_made",
  "benchtop_materials",
  "appliances",
];

const TABLE_LABEL: Record<CatalogTable, string> = {
  board_materials: "Board",
  hardware_materials: "Hardware",
  custom_made: "Custom-made",
  benchtop_materials: "Benchtop",
  appliances: "Appliance",
  equipment_hire: "Equipment hire",
};

interface Props {
  unknown: CvUnknownCode;
  resolution: CvCommitResolution | undefined;
  onChange: (r: CvCommitResolution) => void;
}

export function UnknownCodeRow({ unknown, resolution, onChange }: Props) {
  const [mode, setMode] = useState<Mode>(resolution?.action ?? null);
  const [targetTable, setTargetTable] = useState<SimpleCatalogTable>(
    (unknown.suggested_table as SimpleCatalogTable) || "board_materials",
  );
  const [sku, setSku] = useState("");
  const [description, setDescription] = useState("");

  function pickSkip() {
    setMode("skip");
    onChange({ action: "skip", cv_code: unknown.cv_code });
  }

  function pickCreateNew() {
    setMode("create_new");
    if (sku.trim() && description.trim()) {
      onChange({
        action: "create_new",
        cv_code: unknown.cv_code,
        target_table: targetTable,
        sku: sku.trim(),
        description: description.trim(),
      });
    }
  }

  function pickUseExisting() {
    setMode("use_existing");
  }

  function commitCreateNew() {
    if (!sku.trim() || !description.trim()) return;
    onChange({
      action: "create_new",
      cv_code: unknown.cv_code,
      target_table: targetTable,
      sku: sku.trim(),
      description: description.trim(),
    });
  }

  return (
    <div className="grid grid-cols-[180px_1fr] gap-3 p-3">
      <div>
        <div className="font-mono text-sm text-h-ink">{unknown.cv_code}</div>
        <div className="text-xs text-h-muted">
          {unknown.occurrences} row{unknown.occurrences === 1 ? "" : "s"}
        </div>
        <div className="mt-2 flex gap-1">
          <button
            type="button"
            onClick={pickUseExisting}
            disabled
            className={pillClass(mode === "use_existing")}
            title="Coming soon — search existing catalog rows"
          >
            Use existing
          </button>
          <button
            type="button"
            onClick={pickCreateNew}
            className={pillClass(mode === "create_new")}
          >
            Create new
          </button>
          <button
            type="button"
            onClick={pickSkip}
            className={pillClass(mode === "skip")}
          >
            Skip
          </button>
        </div>
      </div>

      <div className="text-sm">
        {mode === "skip" && (
          <p className="text-h-muted">Rows with this code will be omitted from the import.</p>
        )}

        {mode === "use_existing" && (
          <p className="text-h-muted">
            Use existing catalog row picker ships in #7c. For now, choose <em>Create new</em> or{" "}
            <em>Skip</em>.
          </p>
        )}

        {mode === "create_new" && (
          <div className="space-y-2">
            <label className="block">
              <span className="text-xs text-h-muted">Target table</span>
              <select
                value={targetTable}
                onChange={(e) => setTargetTable(e.target.value as SimpleCatalogTable)}
                onBlur={commitCreateNew}
                className="mt-1 block w-full rounded-md border border-h-line bg-h-bg px-2 py-1 text-sm"
              >
                {SIMPLE_TABLES.map((t) => (
                  <option key={t} value={t}>{TABLE_LABEL[t]}</option>
                ))}
              </select>
              <span className="block text-xs text-h-muted mt-1">
                Equipment Hire requires a project — open{" "}
                <a className="underline" href="/catalog?tab=hire" target="_blank">/catalog</a>{" "}
                to add one, then return.
              </span>
            </label>
            <label className="block">
              <span className="text-xs text-h-muted">SKU</span>
              <input
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                onBlur={commitCreateNew}
                placeholder={unknown.cv_code}
                className="mt-1 block w-full rounded-md border border-h-line bg-h-bg px-2 py-1 text-sm font-mono"
              />
            </label>
            <label className="block">
              <span className="text-xs text-h-muted">Description</span>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onBlur={commitCreateNew}
                placeholder="e.g. 18mm Particleboard White"
                className="mt-1 block w-full rounded-md border border-h-line bg-h-bg px-2 py-1 text-sm"
              />
            </label>
          </div>
        )}

        {mode === null && (
          <p className="text-h-muted">Pick an action.</p>
        )}
      </div>
    </div>
  );
}


function pillClass(active: boolean): string {
  return [
    "rounded-full border px-3 py-0.5 text-xs",
    active
      ? "border-h-accent bg-h-accent text-white"
      : "border-h-line bg-h-bg text-h-muted hover:text-h-ink disabled:opacity-50",
  ].join(" ");
}

"use client";

import { CheckRow, Row, TextRow } from "./DetailRows";

/**
 * The left side of the order pop-up that changes with the order type (Q503: the type-specific
 * fields live in `attributes`). Acoustic panel and Benchtop have their own fields; every other type,
 * Contractor-manufacturing included, shows the order's description instead.
 */
const ACOUSTIC: [key: string, label: string][] = [
  ["colour", "Colour"], ["substrate", "Substrate"], ["finish", "Finish"],
  ["sided", "Sided"], ["grain", "Grain"], ["rating", "Rating"], ["hmr", "HMR"],
];

const BENCHTOP: [key: string, label: string][] = [
  ["colour", "Colour"], ["underside", "Underside"], ["edge_details", "Edge details"],
  ["laminate_supplier", "Laminate supp"], ["finish", "Finish"], ["laminate_code", "Laminate code"],
  ["joins", "Joins"], ["cable_entry", "Cable entry"],
];

export function hasTypeFields(category: string): boolean {
  return category === "Acoustic" || category === "Benchtop";
}

export function OrderTypeFields({ category, attributes, canEdit, onSave }: {
  category: string;
  attributes: Record<string, unknown>;
  canEdit: boolean;
  /** Writes the whole `attributes` object with one key changed. */
  onSave: (key: string, value: string | boolean) => Promise<boolean>;
}) {
  const text = (k: string) => (attributes[k] == null ? null : String(attributes[k]));
  const size = (label: string, keys: [string, string, string], extra?: [string, string]) => (
    <Row label={label}>
      <div className="flex items-center gap-1.5">
        {keys.map((k, i) => (
          <SizeBox key={k} value={text(k)} canEdit={canEdit} placeholder={["L", "W", "T"][i]}
            testId={`order-attr-${k}`} onSave={v => onSave(k, v)} />
        ))}
        {extra && (
          <>
            <span className="text-h-muted">{extra[1]}</span>
            <SizeBox value={text(extra[0])} canEdit={canEdit} placeholder="1" testId={`order-attr-${extra[0]}`}
              onSave={v => onSave(extra[0], v)} />
          </>
        )}
      </div>
    </Row>
  );
  const rows = (fields: [string, string][]) => fields.map(([k, label]) => (
    <TextRow key={k} label={label} value={text(k)} canEdit={canEdit} testId={`order-attr-${k}`}
      onSave={v => onSave(k, v)} />
  ));

  if (category === "Acoustic") {
    return (
      <>
        {size("Board size L × W × T", ["board_length", "board_width", "board_thickness"])}
        {rows(ACOUSTIC)}
      </>
    );
  }
  if (category === "Benchtop") {
    return (
      <>
        {size("Bench size L × W × T", ["bench_length", "bench_width", "bench_thickness"], ["bench_pcs", "Pcs"])}
        {rows(BENCHTOP)}
        <CheckRow label="SHP" value={attributes.shp === true} canEdit={canEdit}
          testId="order-attr-shp" onSave={v => onSave("shp", v)} />
      </>
    );
  }
  return null;
}

function SizeBox({ value, canEdit, placeholder, testId, onSave }: {
  value: string | null; canEdit: boolean; placeholder: string; testId: string;
  onSave: (v: string) => Promise<boolean>;
}) {
  if (!canEdit) return <span className="h-mono w-14">{value || "—"}</span>;
  return (
    <input
      defaultValue={value ?? ""}
      key={value ?? ""}
      placeholder={placeholder}
      inputMode="decimal"
      data-testid={testId}
      onBlur={async e => {
        const el = e.target;
        if (el.value !== (value ?? "") && !(await onSave(el.value))) el.value = value ?? "";
      }}
      className="h-mono w-16 rounded border border-h-line bg-h-bg px-1 py-0.5 text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
    />
  );
}

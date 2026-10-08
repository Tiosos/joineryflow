"use client";

import Link from "next/link";
import { useState } from "react";
import { MaterialKind, CatalogMap, ALL_KINDS, KIND_LABEL, KIND_SLUG, PickerPayload } from "./shared";

interface CatalogPickerProps {
  catalogs: CatalogMap;
  onPick: (payload: PickerPayload) => Promise<void>;
  onClose: () => void;
}

export function CatalogPicker({ catalogs, onPick, onClose }: CatalogPickerProps) {
  const [kind, setKind] = useState<MaterialKind>("BOARD");
  const [search, setSearch] = useState("");
  const [qty, setQty] = useState("1");
  const [lenMm, setLenMm] = useState("");
  const [widMm, setWidMm] = useState("");
  const [paint, setPaint] = useState<PickerPayload["paint_instruction"]>("NONE");
  const [comment, setComment] = useState("");

  const rows = catalogs[kind] ?? [];
  const q = search.trim().toLowerCase();
  const filtered = q
    ? rows.filter((r) => r.sku.toLowerCase().includes(q) || r.description.toLowerCase().includes(q))
    : rows;

  async function pick(materialId: number) {
    const qtyNum = Number(qty);
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) return;
    const lenNum = lenMm ? Number(lenMm) : null;
    const widNum = widMm ? Number(widMm) : null;
    await onPick({
      kind,
      material_id: materialId,
      qty: qtyNum,
      len_mm: kind === "BOARD" ? lenNum : null,
      wid_mm: kind === "BOARD" ? widNum : null,
      paint_instruction: kind === "BOARD" ? paint : "NONE",
      comment: comment.trim() || undefined,
    });
  }

  return (
    <div className="mt-2 rounded border border-h-line bg-white p-3 text-xs" data-testid="catalog-picker">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex flex-wrap gap-1">
          {ALL_KINDS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={`rounded border px-2 py-0.5 ${
                kind === k
                  ? "border-h-accent bg-h-accent text-white"
                  : "border-h-line bg-white hover:bg-gray-50"
              }`}
              data-testid={`picker-kind-${k}`}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
        <button type="button" onClick={onClose} className="text-h-muted hover:text-h-ink">×</button>
      </div>

      <div className="mb-2 flex flex-wrap gap-2">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search SKU or description"
          className="flex-1 min-w-[160px] rounded border border-h-line px-2 py-1"
          data-testid="picker-search"
        />
        <label className="flex items-center gap-1">
          <span className="text-h-muted">Qty</span>
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="w-16 rounded border border-h-line px-1 font-mono"
            data-testid="picker-qty"
          />
        </label>
        {kind === "BOARD" ? (
          <>
            <label className="flex items-center gap-1">
              <span className="text-h-muted">L (mm)</span>
              <input
                type="number"
                min="0"
                value={lenMm}
                onChange={(e) => setLenMm(e.target.value)}
                className="w-16 rounded border border-h-line px-1 font-mono"
                data-testid="picker-len"
              />
            </label>
            <label className="flex items-center gap-1">
              <span className="text-h-muted">W (mm)</span>
              <input
                type="number"
                min="0"
                value={widMm}
                onChange={(e) => setWidMm(e.target.value)}
                className="w-16 rounded border border-h-line px-1 font-mono"
              />
            </label>
            <label className="flex items-center gap-1">
              <span className="text-h-muted">Paint</span>
              <select
                value={paint}
                onChange={(e) => setPaint(e.target.value as PickerPayload["paint_instruction"])}
                className="rounded border border-h-line px-1 py-0.5"
              >
                <option value="NONE">None</option>
                <option value="SINGLE_SIDE">Single side</option>
                <option value="DOUBLE_SIDE">Double side</option>
                <option value="EDGE_ONLY">Edge only</option>
              </select>
            </label>
          </>
        ) : null}
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Comment (optional)"
          className="flex-1 min-w-[120px] rounded border border-h-line px-2 py-1"
        />
      </div>

      <div className="max-h-64 overflow-y-auto rounded border border-h-line bg-white">
        {filtered.length === 0 ? (
          <div className="p-3 text-h-muted">
            {rows.length === 0 ? (
              <>
                No {KIND_LABEL[kind].toLowerCase()} rows.{" "}
                <Link href={`/catalog?tab=${KIND_SLUG[kind]}`} className="text-h-accent underline">
                  Add some in Catalog
                </Link>
                .
              </>
            ) : (
              "No matches for search."
            )}
          </div>
        ) : (
          <ul className="divide-y divide-h-line">
            {filtered.map((row) => (
              <li key={row.material_id}>
                <button
                  type="button"
                  onClick={() => pick(row.material_id)}
                  className="block w-full px-2 py-1 text-left hover:bg-gray-100"
                  data-testid={`picker-pick-${row.material_id}`}
                >
                  <span className="font-mono">{row.sku}</span> — {row.description}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

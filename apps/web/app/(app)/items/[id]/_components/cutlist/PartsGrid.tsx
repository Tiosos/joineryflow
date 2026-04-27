"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { PM } from "@/lib/pm-fetch";
import type { ModuleOut, PartOut, PatchPartIn, PaintInstruction } from "@/lib/pm-types";

interface PartsGridProps {
  module: ModuleOut;
}

type PartRow = PartOut & { _saved?: boolean; _saving?: boolean };

export function PartsGrid({ module }: PartsGridProps) {
  const router = useRouter();
  const [rows, setRows] = useState<PartRow[]>(module.parts);
  const [error, setError] = useState<string | null>(null);

  async function patchCell(partId: number, field: keyof PatchPartIn, value: unknown) {
    // Snapshot the specific field value BEFORE optimistic update
    const prevValue = rows.find((p) => p.id === partId)?.[field as keyof PartRow];

    // Optimistic update — only this part, only this field
    setRows((r) =>
      r.map((p) => (p.id === partId ? { ...p, [field]: value, _saved: false } : p))
    );

    try {
      await PM.patchPart(partId, { [field]: value } as PatchPartIn);
      setRows((r) =>
        r.map((p) => (p.id === partId ? { ...p, _saved: true } : p))
      );
      setError(null);
      router.refresh();
    } catch {
      // v1: inline error banner instead of toast — wire to a toast primitive in a future task
      // Rollback only this field on this part
      setRows((r) =>
        r.map((p) => (p.id === partId ? { ...p, [field]: prevValue } : p))
      );
      setError(`Failed to save ${String(field)}`);
    }
  }

  async function addRow() {
    try {
      const newPart = await PM.createPart(module.id, { part_name: "", qty: 1 });
      setRows((r) => [...r, { ...newPart, _saved: true }]);
      setError(null);
      router.refresh(); // keep server state in sync
    } catch {
      setError("Failed to add part");
    }
  }

  async function deleteRow(partId: number) {
    const prev = rows;
    setRows((r) => r.filter((p) => p.id !== partId));
    try {
      await PM.deletePart(partId);
      setError(null);
      router.refresh();
    } catch {
      setRows(prev);
      setError("Failed to delete part");
    }
  }

  return (
    <div className="flex-1 overflow-x-auto">
      {error && <p className="mb-2 text-xs text-h-bad">{error}</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-h-line text-left text-xs text-h-muted">
            <th className="w-6 pb-2 pr-2" /> {/* checkbox */}
            <th className="pb-2 pr-2 font-medium">Qty</th>
            <th className="pb-2 pr-2 font-medium min-w-[120px]">Part name</th>
            <th className="pb-2 pr-2 font-medium">L (mm)</th>
            <th className="pb-2 pr-2 font-medium">W (mm)</th>
            <th className="pb-2 pr-2 font-medium min-w-[100px]">Material</th>
            <th className="pb-2 pr-2 font-medium">Edge</th>
            <th className="pb-2 pr-2 font-medium">Colour</th>
            <th className="pb-2 pr-2 font-medium">Paint</th>
            <th className="pb-2 pr-2 font-medium">Comment</th>
            <th className="pb-2" /> {/* delete */}
          </tr>
        </thead>
        <tbody>
          {rows.map((part) => (
            <PartRowComponent
              key={part.id}
              part={part}
              onPatch={patchCell}
              onDelete={deleteRow}
            />
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={addRow}
        className="mt-3 rounded border border-dashed border-h-line px-3 py-1.5 text-sm text-h-muted hover:border-h-accent hover:text-h-ink transition-colors"
      >
        + Add row
      </button>
    </div>
  );
}

// Sub-component for a single part row — owns cell-level state for local editing
interface PartRowComponentProps {
  part: PartRow;
  onPatch: (id: number, field: keyof PatchPartIn, value: unknown) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

function PartRowComponent({ part, onPatch, onDelete }: PartRowComponentProps) {
  return (
    <tr
      data-testid="part-row"
      data-saved={part._saved ? "true" : undefined}
      className={[
        "border-b border-h-line/50",
        part.is_rev_c ? "bg-h-accent/15" : "",
      ].join(" ")}
    >
      {/* Checkbox — noop v1 */}
      <td className="py-1 pr-2">
        <input type="checkbox" className="rounded border-h-line" readOnly />
      </td>

      <td className="py-1 pr-1">
        <CellInput
          key={String(part.qty)}
          data-field="qty"
          type="number"
          defaultValue={String(part.qty)}
          onCommit={(v) => onPatch(part.id, "qty", Number(v) || 1)}
          className="w-12"
        />
      </td>

      <td className="py-1 pr-1">
        <CellInput
          key={String(part.part_name)}
          data-field="part_name"
          defaultValue={part.part_name ?? ""}
          onCommit={(v) => onPatch(part.id, "part_name", v)}
          className="min-w-[110px]"
        />
      </td>

      <td className="py-1 pr-1">
        <CellInput
          key={String(part.len_mm ?? "")}
          data-field="len_mm"
          type="number"
          defaultValue={part.len_mm !== null ? String(part.len_mm) : ""}
          onCommit={(v) => onPatch(part.id, "len_mm", v === "" ? null : Number(v))}
          className="w-16"
        />
      </td>

      <td className="py-1 pr-1">
        <CellInput
          key={String(part.wid_mm ?? "")}
          data-field="wid_mm"
          type="number"
          defaultValue={part.wid_mm !== null ? String(part.wid_mm) : ""}
          onCommit={(v) => onPatch(part.id, "wid_mm", v === "" ? null : Number(v))}
          className="w-16"
        />
      </td>

      {/* board_material: display-only in v1 — server resolves via FK JOIN; PatchPartIn uses board_material_id (FK int), not a free-text field */}
      <td className="py-1 pr-1">
        <span
          data-field="board_material"
          className="block px-1 py-0.5 text-sm text-h-muted min-w-[90px]"
        >
          {part.board_material ?? "—"}
        </span>
      </td>

      <td className="py-1 pr-1">
        <CellInput
          key={String(part.edge)}
          data-field="edge"
          defaultValue={part.edge ?? ""}
          onCommit={(v) => onPatch(part.id, "edge", v || null)}
          className="w-16"
        />
      </td>

      <td className="py-1 pr-1">
        <CellInput
          key={String(part.colour)}
          data-field="colour"
          defaultValue={part.colour ?? ""}
          onCommit={(v) => onPatch(part.id, "colour", v || null)}
          className="w-20"
        />
      </td>

      <td className="py-1 pr-1">
        <PaintSelect
          defaultValue={part.paint_instruction}
          onCommit={(v) => onPatch(part.id, "paint_instruction", v)}
        />
      </td>

      <td className="py-1 pr-1">
        <CellInput
          key={String(part.comment)}
          data-field="comment"
          defaultValue={part.comment ?? ""}
          onCommit={(v) => onPatch(part.id, "comment", v || null)}
          className="min-w-[80px]"
        />
      </td>

      <td className="py-1">
        <button
          type="button"
          onClick={() => onDelete(part.id)}
          className="px-1.5 text-h-muted hover:text-h-bad transition-colors"
          aria-label="Delete part"
        >
          –
        </button>
      </td>
    </tr>
  );
}

interface CellInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onCommit: (value: string) => void;
}

function CellInput({ onCommit, className, defaultValue, ...props }: CellInputProps) {
  const [value, setValue] = useState(String(defaultValue ?? ""));
  const savedRef = useRef(String(defaultValue ?? ""));

  function handleBlur() {
    if (value !== savedRef.current) {
      onCommit(value);
      savedRef.current = value;
    }
  }

  return (
    <input
      {...props}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={handleBlur}
      className={[
        "rounded border border-transparent bg-transparent px-1 py-0.5 text-sm text-h-ink",
        "hover:border-h-line focus:border-h-accent focus:outline-none focus:bg-h-bg",
        "transition-colors",
        className ?? "",
      ].join(" ")}
    />
  );
}

const PAINT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "—" },
  { value: "NONE", label: "None" },
  { value: "DOUBLE_SIDE", label: "Double side" },
  { value: "SINGLE_SIDE", label: "Single side" },
  { value: "EDGE_ONLY", label: "Edge only" },
];

interface PaintSelectProps {
  defaultValue: string | null;
  onCommit: (value: string | null) => void;
}

function PaintSelect({ defaultValue, onCommit }: PaintSelectProps) {
  const [value, setValue] = useState(defaultValue ?? "");

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const v = e.target.value;
    setValue(v);
    onCommit(v === "" ? null : (v as PaintInstruction));
  }

  return (
    <select
      value={value}
      onChange={handleChange}
      className="rounded border border-transparent bg-transparent px-1 py-0.5 text-sm text-h-ink hover:border-h-line focus:border-h-accent focus:outline-none focus:bg-h-bg transition-colors w-24"
    >
      {PAINT_OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

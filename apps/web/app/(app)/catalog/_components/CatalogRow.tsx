"use client";

import { useEffect, useRef, useState } from "react";

import { archiveRow, patchRow } from "@/lib/catalog-fetch";
import type { CatalogRow as Row, CatalogSlug, SupplierOption } from "@/lib/catalog-types";

import BoardImageCell from "./BoardImageCell";
import PurchaseHistoryPanel from "./PurchaseHistoryPanel";
import { BOARD_NUMBER_FIELDS, BOARD_TEXT_FIELDS } from "./boardFields";
import { EDGING_NUMBER_FIELDS, EDGING_TEXT_FIELDS } from "./edgingFields";
import { BENCHTOP_NUMBER_FIELDS, BENCHTOP_TEXT_FIELDS } from "./benchtopFields";
import { GLASS_NUMBER_FIELDS, GLASS_TEXT_FIELDS } from "./glassFields";
import { TIMBER_NUMBER_FIELDS, TIMBER_TEXT_FIELDS } from "./timberFields";
import { CUSTOM_TEXT_FIELDS } from "./customFields";
import { HIRE_TEXT_FIELDS } from "./hireFields";
import { APPLIANCE_TEXT_FIELDS } from "./applianceFields";
import { HARDWARE_TEXT_FIELDS } from "./hardwareFields";
import type { MaterialTab } from "./CatalogClient";
import { useConfirm } from "@/components/confirm/ConfirmProvider";
import { useUndo } from "@/components/undo/UndoProvider";

interface Props {
  tab: MaterialTab;
  slug: CatalogSlug;
  row: Row;
  canWrite: boolean;
  /** null while loading or when the list could not be read (picker is then disabled). */
  suppliers: SupplierOption[] | null;
  onChanged: () => void;
  /** The grid's column count: the purchase history row spans it. */
  colCount: number;
}

const LEGACY_COL_KEY: Record<MaterialTab, keyof Row | null> = {
  board: "code",
  hardware: null,
  custom_made: "internal_ref",
  benchtop: "slab_id",
  appliance: "model_number",
  hire: "contract_ref",
  edging: null,
  glass: null,
  timber: null,
};

function Cell({
  value, onSave, canWrite, type = "text", step, label,
}: {
  value: string | number | null;
  onSave: (v: string) => void | Promise<void>;
  canWrite: boolean;
  type?: "text" | "number";
  step?: string;
  label?: string;
}) {
  const [local, setLocal] = useState(value == null ? "" : String(value));
  // What the server holds as far as this cell knows: the prop, until we save something newer.
  // Comparing with the prop alone skips a second edit made before the grid reloads.
  const saved = useRef(value == null ? "" : String(value));
  useEffect(() => {
    const fresh = value == null ? "" : String(value);
    const was = saved.current;
    saved.current = fresh;
    // A reload landing while the user is mid-edit must not overwrite what they typed.
    setLocal((cur) => (cur === was || cur === fresh ? fresh : cur));
  }, [value]);

  if (!canWrite) return <span>{local || "—"}</span>;

  return (
    <input
      type={type}
      step={step}
      aria-label={label}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={() => {
        if (local !== saved.current) { saved.current = local; void onSave(local); }
      }}
      className="w-full bg-transparent px-1 py-0.5 text-sm focus:bg-h-surface focus:outline focus:outline-1 focus:outline-h-line"
    />
  );
}

/** The real supplier link — what Generate Orders groups by. A row with no link
 *  is flagged, because its materials come back "unassigned" there. */
function SupplierLink({
  row, canWrite, suppliers, busy, onPick,
}: {
  row: Row;
  canWrite: boolean;
  suppliers: SupplierOption[] | null;
  busy: boolean;
  onPick: (id: number | null) => void;
}) {
  const linked = row.default_supplier_id != null;
  if (!canWrite) {
    return linked
      ? <span>{row.default_supplier_name ?? "—"}</span>
      : <span className="text-h-warn" data-testid="supplier-unlinked">Not linked</span>;
  }
  const list = suppliers ?? [];
  // Keep the current link selectable even if the list has not loaded (or failed),
  // so the select never shows "Not linked" for a row that is linked.
  const missing = linked && !list.some((s) => s.vendor_id === row.default_supplier_id);
  return (
    <select
      aria-label="Supplier link"
      value={row.default_supplier_id ?? ""}
      disabled={busy || suppliers == null}
      onChange={(e) => onPick(e.target.value === "" ? null : Number(e.target.value))}
      className={
        "w-full rounded border border-h-line bg-transparent px-1 py-0.5 text-sm "
        + (linked ? "" : "text-h-warn")
      }
    >
      <option value="">Not linked</option>
      {missing && (
        <option value={row.default_supplier_id!}>{row.default_supplier_name ?? `#${row.default_supplier_id}`}</option>
      )}
      {list.map((s) => (
        <option key={s.vendor_id} value={s.vendor_id}>
          {s.name}{s.status && s.status !== "Active" ? ` (${s.status.toLowerCase()})` : ""}
        </option>
      ))}
    </select>
  );
}

export default function CatalogRow({ tab, slug, row, canWrite, suppliers, onChanged, colCount }: Props) {
  const { confirm } = useConfirm();
  const { defer, notify } = useUndo();
  const mid = row.material_id ?? row.hire_id;
  if (mid == null) {
    // Defensive: shouldn't happen — every catalog row has either material_id (5 tables)
    // or hire_id (equipment_hire). Render an empty row rather than crashing.
    return null;
  }
  const legacyKey = LEGACY_COL_KEY[tab];
  const legacyVal = legacyKey ? (row[legacyKey] as string | null | undefined) ?? "" : "—";
  const [busy, setBusy] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const save = async (patch: Record<string, unknown>) => {
    setBusy(true);
    try {
      await patchRow(slug, mid, patch);
      onChanged();
    } catch (e) {
      notify(`Could not save the change: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const onArchive = async () => {
    if (!(await confirm({ title: "Archive this row?", message: "It leaves the catalog lists; it is archived, not deleted.", confirmLabel: "Archive" }))) return;
    setBusy(true);
    defer({
      message: "Archived the row",
      run: async () => { await archiveRow(slug, mid); onChanged(); },
      onSettle: () => setBusy(false),
    });
  };

  return (
    <>
    <tr className="border-t border-h-line">
      <td className="px-3 py-1">
        <Cell value={row.description} canWrite={canWrite}
              onSave={(v) => save({ description: v })} />
      </td>
      <td className="px-3 py-1">
        <Cell value={row.product_type} label="Type" canWrite={canWrite}
              onSave={(v) => save({ product_type: v.trim() || null })} />
      </td>
      <td className="px-3 py-1 font-mono">
        <Cell value={row.sku} canWrite={canWrite}
              onSave={(v) => save({ sku: v })} />
      </td>
      <td className="px-3 py-1">
        {legacyKey
          ? <Cell value={legacyVal as string} canWrite={canWrite}
                  onSave={(v) => save({ [legacyKey]: v })} />
          : <span className="text-h-muted">—</span>}
      </td>
      <td className="px-3 py-1">
        <Cell value={row.default_supplier} canWrite={canWrite}
              onSave={(v) => save({ default_supplier: v || null })} />
      </td>
      <td className="px-3 py-1" data-testid="supplier-link-cell">
        <SupplierLink row={row} canWrite={canWrite} suppliers={suppliers} busy={busy}
                      onPick={(id) => save({ default_supplier_id: id })} />
      </td>
      <td className="px-3 py-1 w-20">
        <Cell value={row.default_lead_time_days} type="number" canWrite={canWrite}
              onSave={(v) => save({ default_lead_time_days: v === "" ? null : Number(v) })} />
      </td>
      <td className="px-3 py-1 w-24">
        <Cell value={row.unit_cost} type="number" step="0.0001" label="Unit cost" canWrite={canWrite}
              onSave={(v) => save({ unit_cost: v === "" ? null : Number(v) })} />
      </td>
      {tab === "board" && BOARD_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "board" && BOARD_NUMBER_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1 w-24">
          <Cell value={(row[f.key] as number | null | undefined) ?? null} type="number" step={f.step} label={f.label}
                canWrite={canWrite} onSave={(v) => save({ [f.key]: v === "" ? null : Number(v) })} />
        </td>
      ))}
      {tab === "edging" && EDGING_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "edging" && EDGING_NUMBER_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1 w-24">
          <Cell value={(row[f.key] as number | null | undefined) ?? null} type="number" step="0.01" label={f.label}
                canWrite={canWrite} onSave={(v) => save({ [f.key]: v === "" ? null : Number(v) })} />
        </td>
      ))}
      {tab === "edging" && (
        <td className="px-3 py-1 text-center">
          <input type="checkbox" checked={row.glued ?? false} disabled={!canWrite || busy}
                 onChange={(e) => save({ glued: e.target.checked })} aria-label="Glued" />
        </td>
      )}
      {tab === "glass" && GLASS_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "glass" && GLASS_NUMBER_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1 w-24">
          <Cell value={(row[f.key] as number | null | undefined) ?? null} type="number" step="0.01" label={f.label}
                canWrite={canWrite} onSave={(v) => save({ [f.key]: v === "" ? null : Number(v) })} />
        </td>
      ))}
      {tab === "glass" && (
        <td className="px-3 py-1 text-center">
          <input type="checkbox" checked={row.shaped ?? false} disabled={!canWrite || busy}
                 onChange={(e) => save({ shaped: e.target.checked })} aria-label="Shaped" />
        </td>
      )}
      {tab === "timber" && TIMBER_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "timber" && TIMBER_NUMBER_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1 w-24">
          <Cell value={(row[f.key] as number | null | undefined) ?? null} type="number" step="0.01" label={f.label}
                canWrite={canWrite} onSave={(v) => save({ [f.key]: v === "" ? null : Number(v) })} />
        </td>
      ))}
      {tab === "benchtop" && BENCHTOP_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "benchtop" && BENCHTOP_NUMBER_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1 w-24">
          <Cell value={(row[f.key] as number | null | undefined) ?? null} type="number" step={f.step} label={f.label}
                canWrite={canWrite} onSave={(v) => save({ [f.key]: v === "" ? null : Number(v) })} />
        </td>
      ))}
      {tab === "benchtop" && (
        <td className="px-3 py-1 text-center">
          <input type="checkbox" checked={row.shaped ?? false} disabled={!canWrite || busy}
                 onChange={(e) => save({ shaped: e.target.checked })} aria-label="Shaped" />
        </td>
      )}
      {tab === "hardware" && HARDWARE_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "custom_made" && CUSTOM_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "hire" && HIRE_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {tab === "appliance" && APPLIANCE_TEXT_FIELDS.map((f) => (
        <td key={f.key} className="px-3 py-1">
          <Cell value={(row[f.key] as string | null | undefined) ?? null} label={f.label} canWrite={canWrite}
                onSave={(v) => save({ [f.key]: v.trim() || null })} />
        </td>
      ))}
      {(tab === "board" || tab === "edging" || tab === "glass" || tab === "timber" || tab === "benchtop" || tab === "hardware"
        || tab === "custom_made" || tab === "hire" || tab === "appliance") && (
        <td className="px-3 py-1">
          <BoardImageCell slug={slug} mid={mid} hasImage={row.has_image ?? false} canWrite={canWrite && !row.archived_at}
                          onChanged={onChanged} />
        </td>
      )}
      <td className="px-3 py-1">
        <Cell value={row.synonyms.join(", ")} canWrite={canWrite}
              onSave={(v) => save({ synonyms: v.split(/\s*,\s*/).filter(Boolean) })} />
      </td>
      {(tab === "board" || tab === "benchtop") && (
        <td className="px-3 py-1 text-center">
          <input
            type="checkbox"
            checked={row.grain_locked ?? false}
            disabled={!canWrite || busy}
            onChange={(e) => save({ grain_locked: e.target.checked })}
            aria-label="Grain locked"
          />
        </td>
      )}
      <td className="px-3 py-1 text-xs text-h-muted">
        {row.archived_at ? "Archived" : "Active"}
      </td>
      <td className="whitespace-nowrap px-3 py-1">
        <button type="button" data-testid="catalog-row-history" aria-expanded={historyOpen}
                onClick={() => setHistoryOpen((o) => !o)}
                className="mr-3 text-xs text-h-accent hover:underline">
          History
        </button>
        {canWrite && !row.archived_at && (
          <button type="button" data-testid="catalog-row-archive" onClick={onArchive} disabled={busy}
                  className="text-xs text-rose-700 hover:underline disabled:opacity-50">
            Archive
          </button>
        )}
      </td>
    </tr>
    {historyOpen && (
      <tr className="bg-h-bg">
        <td colSpan={colCount}><PurchaseHistoryPanel slug={slug} mid={mid} /></td>
      </tr>
    )}
    </>
  );
}

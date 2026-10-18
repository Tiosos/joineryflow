"use client";

import { useEffect, useState } from "react";
import { apiCall } from "@/lib/api";
import type { OrderCatalogItem, OrderCatalogItems } from "@/lib/order-tabs-types";
import { TABLE_LABEL, type TableKey } from "../../../catalog/_components/tables";
import { APPLIANCE_TEXT_FIELDS } from "../../../catalog/_components/applianceFields";
import { BENCHTOP_NUMBER_FIELDS, BENCHTOP_TEXT_FIELDS } from "../../../catalog/_components/benchtopFields";
import { BOARD_TEXT_FIELDS } from "../../../catalog/_components/boardFields";
import { CUSTOM_TEXT_FIELDS } from "../../../catalog/_components/customFields";
import { EDGING_NUMBER_FIELDS, EDGING_TEXT_FIELDS } from "../../../catalog/_components/edgingFields";
import { GLASS_NUMBER_FIELDS, GLASS_TEXT_FIELDS } from "../../../catalog/_components/glassFields";
import { HARDWARE_TEXT_FIELDS } from "../../../catalog/_components/hardwareFields";
import { HIRE_TEXT_FIELDS } from "../../../catalog/_components/hireFields";
import { TIMBER_NUMBER_FIELDS, TIMBER_TEXT_FIELDS } from "../../../catalog/_components/timberFields";

/** The labels the catalog grids use for a field key (the keys that mean the same thing share a label in every grid). */
const LABELS: Record<string, string> = Object.fromEntries(
  [
    ...BOARD_TEXT_FIELDS, ...BENCHTOP_TEXT_FIELDS, ...BENCHTOP_NUMBER_FIELDS, ...HARDWARE_TEXT_FIELDS,
    ...EDGING_TEXT_FIELDS, ...EDGING_NUMBER_FIELDS, ...GLASS_TEXT_FIELDS, ...GLASS_NUMBER_FIELDS,
    ...TIMBER_TEXT_FIELDS, ...TIMBER_NUMBER_FIELDS, ...CUSTOM_TEXT_FIELDS, ...APPLIANCE_TEXT_FIELDS, ...HIRE_TEXT_FIELDS,
  ].map(f => [f.key, f.label]),
);
LABELS.glued = "Glued";
LABELS.shaped = "Shaped";

/** A product website is a link only when it is an http(s) URL; anything else (`javascript:`...) is shown as plain text. */
export function safeHttpUrl(s: string | null | undefined): string | null {
  if (!s) return null;
  try {
    const u = new URL(s.trim());
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch { return null; }
}

function shown(v: string | number | boolean | null): string | null {
  if (v === null || v === "") return null;
  return typeof v === "boolean" ? (v ? "Yes" : "No") : String(v);
}

const typeLabel = (t: string) => TABLE_LABEL[t as TableKey] ?? t;

/**
 * The catalog item behind the order's product code (HOME tab, beside the picture and description): read-only, taken
 * from the catalog on every look and never stored on the order. Shows nothing when the code matches no catalog row.
 */
export function CatalogItemBlock({ poId, productCode }: { poId: number; productCode: string | null }) {
  // The answer is kept with the (order, code) it was asked for, so an edited code never shows the old item.
  const key = `${poId}|${(productCode ?? "").trim()}`;
  const [got, setGot] = useState<{ key: string; items: OrderCatalogItem[] } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    apiCall<OrderCatalogItems>(`/api/orders/${poId}/catalog-item`)
      .then(d => { if (live) { setGot({ key, items: d.items }); setFailed(null); } })
      .catch(() => { if (live) setFailed(key); });
    return () => { live = false; };
  }, [poId, key]);

  if (failed === key) return <p role="alert" className="text-[#b4443d]">Could not load the catalog item</p>;
  if (!got || got.key !== key || got.items.length === 0) return null;
  const [it, ...others] = got.items;
  const href = safeHttpUrl(it.product_website);
  const rows = Object.entries(it.fields).map(([k, v]) => [k, shown(v)] as const).filter(([, v]) => v !== null);
  return (
    <section data-testid="order-catalog-item" className="grid gap-2 rounded border border-h-line p-2">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-h-muted">
        {`Catalog item: ${typeLabel(it.type)}${it.product_type ? ` (${it.product_type})` : ""}`}
        {it.archived && <span data-testid="order-catalog-archived">{" · archived"}</span>}
      </p>
      <div className="grid grid-cols-[6rem_1fr] gap-3">
        <div className="flex h-24 items-center justify-center overflow-hidden rounded border border-h-line bg-h-bg text-h-muted">
          {it.has_image
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={`/api/orders/${poId}/catalog-item/image?n=0&v=${it.type}-${it.id}`} alt={`Catalog picture of ${it.sku ?? it.description ?? "the item"}`}
                data-testid="order-catalog-image" className="max-h-full max-w-full object-contain" />
            : <span>No picture</span>}
        </div>
        <dl className="grid grid-cols-[7rem_1fr] gap-x-2 gap-y-0.5">
          <dt className="text-h-muted">SKU</dt><dd data-testid="order-catalog-sku" className="h-mono">{it.sku ?? "—"}</dd>
          <dt className="text-h-muted">Description</dt><dd data-testid="order-catalog-description">{it.description ?? "—"}</dd>
          <dt className="text-h-muted">UM</dt><dd data-testid="order-catalog-um">{it.um ?? "—"}</dd>
          <dt className="text-h-muted">Website</dt>
          <dd data-testid="order-catalog-website" className="break-all">
            {href
              ? <a href={href} target="_blank" rel="noopener noreferrer" className="underline">{it.product_website}</a>
              : (it.product_website ?? "—")}
          </dd>
          {rows.map(([k, v]) => (
            <div key={k} className="contents" data-testid={`order-catalog-field-${k}`}>
              <dt className="text-h-muted">{LABELS[k] ?? k}</dt><dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      {others.length > 0 && (
        <p data-testid="order-catalog-others" className="text-h-muted">
          {`${others.length} other catalog ${others.length === 1 ? "item shares" : "items share"} this code: `}
          {others.map(o => `${typeLabel(o.type)}${o.archived ? " (archived)" : ""} ${o.description ?? o.sku ?? ""}`.trim()).join(", ")}
        </p>
      )}
    </section>
  );
}

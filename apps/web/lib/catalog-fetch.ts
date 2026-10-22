import type {
  BulkImportResp,
  ByTypeResp,
  ProductTypesResp,
  PurchaseHistory,
  CatalogListResp,
  CatalogRow,
  CatalogSlug,
  CvMapping,
  CvMappingListResp,
  SupplierOption,
} from "./catalog-types";

const headers = { "Content-Type": "application/json" };

export async function listCatalog(args: {
  slug: CatalogSlug;
  q?: string | null;
  supplier?: string | null;
  archived?: boolean;
}): Promise<CatalogListResp> {
  const sp = new URLSearchParams();
  if (args.q) sp.set("q", args.q);
  if (args.supplier) sp.set("supplier", args.supplier);
  if (args.archived) sp.set("archived", "true");
  const url = `/api/catalog/${args.slug}${sp.size ? `?${sp.toString()}` : ""}`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`listCatalog: ${res.status}`);
  return res.json();
}

/** Every supplier of the workspace, for the supplier-link picker. `GET /suppliers`
 *  needs `orderbook:read`, a different grant from the grid's `catalog:write`. */
export async function listSupplierOptions(): Promise<SupplierOption[]> {
  const res = await fetch("/api/suppliers", { credentials: "include", cache: "no-store" });
  if (!res.ok) throw new Error(`listSuppliers: ${res.status}`);
  const body = await res.json();
  return body.suppliers ?? [];
}

export async function createRow(slug: CatalogSlug, body: Record<string, unknown>): Promise<CatalogRow> {
  const res = await fetch(`/api/catalog/${slug}`, {
    method: "POST", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createRow: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function patchRow(slug: CatalogSlug, mid: number, body: Record<string, unknown>): Promise<CatalogRow> {
  const res = await fetch(`/api/catalog/${slug}/${mid}`, {
    method: "PATCH", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patchRow: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function archiveRow(slug: CatalogSlug, mid: number): Promise<CatalogRow> {
  const res = await fetch(`/api/catalog/${slug}/${mid}/archive`, {
    method: "POST", credentials: "include", keepalive: true,
  });
  if (!res.ok) throw new Error(`archiveRow: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function bulkImport(slug: CatalogSlug, rows: Record<string, unknown>[]): Promise<BulkImportResp> {
  const res = await fetch(`/api/catalog/${slug}/bulk`, {
    method: "POST", credentials: "include", headers, body: JSON.stringify({ rows }),
  });
  if (!res.ok) throw new Error(`bulkImport: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function listCvMappings(q?: string | null): Promise<CvMappingListResp> {
  const url = q ? `/api/catalog/cv-mappings?q=${encodeURIComponent(q)}` : "/api/catalog/cv-mappings";
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`listCvMappings: ${res.status}`);
  return res.json();
}

export async function createCvMapping(body: {
  cv_code: string;
  target_material_table: string;
  target_material_id: number;
  notes?: string | null;
}): Promise<CvMapping> {
  const res = await fetch("/api/catalog/cv-mappings", {
    method: "POST", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createCvMapping: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function patchCvMapping(mid: number, body: Record<string, unknown>): Promise<CvMapping> {
  const res = await fetch(`/api/catalog/cv-mappings/${mid}`, {
    method: "PATCH", credentials: "include", headers, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patchCvMapping: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function deleteCvMapping(mid: number): Promise<void> {
  const res = await fetch(`/api/catalog/cv-mappings/${mid}`, {
    method: "DELETE", credentials: "include",
  });
  if (!res.ok) throw new Error(`deleteCvMapping: ${res.status}`);
}

export async function listProductTypes(archived = false): Promise<ProductTypesResp> {
  const res = await fetch(`/api/catalog/product-types${archived ? "?archived=true" : ""}`, { credentials: "include" });
  if (!res.ok) throw new Error(`listProductTypes: ${res.status}`);
  return res.json();
}

/** The items of one product type across the six tables; `productType` null means "no type". */
export async function listByType(args: {
  productType: string | null;
  q?: string | null;
  supplier?: string | null;
  archived?: boolean;
}): Promise<ByTypeResp> {
  const sp = new URLSearchParams();
  if (args.productType == null) sp.set("untyped", "true"); else sp.set("product_type", args.productType);
  if (args.q) sp.set("q", args.q);
  if (args.supplier) sp.set("supplier", args.supplier);
  if (args.archived) sp.set("archived", "true");
  const res = await fetch(`/api/catalog/by-type?${sp.toString()}`, { credentials: "include" });
  if (!res.ok) throw new Error(`listByType: ${res.status}`);
  return res.json();
}

/** What the workspace has paid for the row's SKU (needs catalog and orderbook read). */
export async function getPurchaseHistory(slug: CatalogSlug, mid: number): Promise<PurchaseHistory> {
  const res = await fetch(`/api/catalog/${slug}/${mid}/purchase-history`, { credentials: "include", cache: "no-store" });
  if (res.status === 403) throw new Error("forbidden");
  if (!res.ok) throw new Error(`purchaseHistory: ${res.status}`);
  return res.json();
}

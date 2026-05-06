import type {
  BulkImportResp,
  CatalogListResp,
  CatalogRow,
  CatalogSlug,
  CvMapping,
  CvMappingListResp,
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
    method: "POST", credentials: "include",
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

import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";
import type { EstimateDetail } from "@/lib/estimating-types";

import EstimateDetailClient from "../_components/EstimateDetailClient";

const COOKIE_NAME = "jf_session";
const API = process.env.API_URL ?? "http://api:8000";

interface PageProps {
  params: Promise<{ eid: string }>;
}

async function fetchEstimate(tok: string, eid: number): Promise<EstimateDetail | null> {
  const r = await fetch(`${API}/estimates/${eid}`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  if (!r.ok) return null;
  return (await r.json()) as EstimateDetail;
}

interface CatalogRow {
  material_id: number;
  sku: string;
  description: string;
  default_supplier?: string | null;
}

async function fetchCatalog(tok: string, slug: string): Promise<CatalogRow[]> {
  const r = await fetch(`${API}/catalog/${slug}`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  if (!r.ok) return [];
  const body = (await r.json()) as { rows?: CatalogRow[] } | CatalogRow[];
  return Array.isArray(body) ? body : (body.rows ?? []);
}

export default async function Page({ params }: PageProps) {
  const p = await params;
  const eid = Number(p.eid);
  if (!Number.isFinite(eid)) notFound();

  const me = await fetchMe();
  if (!me) redirect("/login");

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";

  const [estimate, boards, customs, benchtops, hardware, appliances] = await Promise.all([
    fetchEstimate(tok, eid),
    fetchCatalog(tok, "board-materials"),
    fetchCatalog(tok, "custom-made"),
    fetchCatalog(tok, "benchtop-materials"),
    fetchCatalog(tok, "hardware-materials"),
    fetchCatalog(tok, "appliances"),
  ]);
  if (!estimate) notFound();

  return (
    <EstimateDetailClient
      me={me}
      estimate={estimate}
      catalogs={{
        BOARD: boards,
        CUSTOM: customs,
        BENCHTOP: benchtops,
        HARDWARE: hardware,
        APPLIANCE: appliances,
      }}
    />
  );
}

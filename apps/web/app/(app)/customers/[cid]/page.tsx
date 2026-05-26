import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";
import type { Customer, EstimateSummary } from "@/lib/estimating-types";

import CustomerDetailClient from "./_components/CustomerDetailClient";

const COOKIE_NAME = "jf_session";
const API = process.env.API_URL ?? "http://api:8000";

interface PageProps {
  params: Promise<{ cid: string }>;
}

async function fetchCustomer(tok: string, cid: number): Promise<Customer | null> {
  const r = await fetch(`${API}/customers/${cid}`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  if (!r.ok) return null;
  return (await r.json()) as Customer;
}

async function fetchEstimates(
  tok: string,
  cid: number,
  subtab: "active" | "archive",
): Promise<EstimateSummary[]> {
  const r = await fetch(
    `${API}/estimates?customer_id=${cid}&subtab=${subtab}`,
    {
      headers: { cookie: `${COOKIE_NAME}=${tok}` },
      cache: "no-store",
    },
  );
  if (!r.ok) return [];
  const body = (await r.json()) as { estimates: EstimateSummary[] };
  return body.estimates;
}

export default async function Page({ params }: PageProps) {
  const p = await params;
  const cid = Number(p.cid);
  if (!Number.isFinite(cid)) notFound();

  const me = await fetchMe();
  if (!me) redirect("/login");

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";

  const [customer, active, archive] = await Promise.all([
    fetchCustomer(tok, cid),
    fetchEstimates(tok, cid, "active"),
    fetchEstimates(tok, cid, "archive"),
  ]);
  if (!customer) notFound();

  return (
    <CustomerDetailClient
      me={me}
      customer={customer}
      activeEstimates={active}
      archivedEstimates={archive}
    />
  );
}

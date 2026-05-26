import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe, SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";
import type {
  Customer,
  EstimateSummary,
} from "@/lib/estimating-types";

import EstimatingClient from "./_components/EstimatingClient";
const API = process.env.API_URL ?? "http://api:8000";

interface PageProps {
  searchParams: Promise<{
    subtab?: string;
    q?: string;
    customer?: string;
    status?: string;
  }>;
}

async function fetchEstimates(
  tok: string,
  subtab: string,
  q?: string,
  customer?: string,
  status?: string,
): Promise<EstimateSummary[]> {
  const params = new URLSearchParams({ subtab });
  if (q) params.set("q", q);
  if (customer) params.set("customer_id", customer);
  if (status) params.set("status", status);
  const r = await fetch(`${API}/estimates?${params.toString()}`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  if (!r.ok) return [];
  const body = (await r.json()) as { estimates: EstimateSummary[] };
  return body.estimates;
}

async function fetchCustomers(tok: string): Promise<Customer[]> {
  const r = await fetch(`${API}/customers`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  if (!r.ok) return [];
  return (await r.json()) as Customer[];
}

export default async function Page({ searchParams }: PageProps) {
  const sp = await searchParams;
  const me = await fetchMe();
  if (!me) redirect("/login");

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";
  const subtab = sp.subtab === "archive" ? "archive" : "active";

  const [estimates, customers] = await Promise.all([
    fetchEstimates(tok, subtab, sp.q, sp.customer, sp.status),
    fetchCustomers(tok),
  ]);

  return (
    <EstimatingClient
      me={me}
      initialEstimates={estimates}
      customers={customers}
      initialSubtab={subtab}
      initialQ={sp.q ?? ""}
    />
  );
}

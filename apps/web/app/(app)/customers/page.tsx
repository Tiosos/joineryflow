import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";
import type { Customer } from "@/lib/estimating-types";

import CustomersClient from "./_components/CustomersClient";

const COOKIE_NAME = "jf_session";
const API = process.env.API_URL ?? "http://api:8000";

interface PageProps {
  searchParams: Promise<{
    q?: string;
    include_archived?: string;
  }>;
}

async function fetchCustomers(
  tok: string,
  q?: string,
  includeArchived = false,
): Promise<Customer[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (includeArchived) params.set("include_archived", "true");
  const r = await fetch(`${API}/customers?${params.toString()}`, {
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
  const includeArchived = sp.include_archived === "true";
  const customers = await fetchCustomers(tok, sp.q, includeArchived);

  return (
    <CustomersClient
      me={me}
      initialCustomers={customers}
      initialQ={sp.q ?? ""}
      initialIncludeArchived={includeArchived}
    />
  );
}

import { redirect } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { getSessionCookie } from "@/lib/session";
import { SESSION_COOKIE_NAME } from "@/lib/session-cookie";
import { ItemLabelClient } from "./_components/ItemLabelClient";

// Deliberately outside the (app) route group: this page prints a bare QR
// label, not the app chrome. Still auth-gated — proxy.ts's PUBLIC list is
// path-based, not route-group-based, so /items/[id]/label still redirects
// to /login without a session.
async function fetchItem(id: number): Promise<ItemOut | null> {
  const tok = await getSessionCookie();
  if (!tok) return null;
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/items/${id}`, {
    headers: { cookie: `${SESSION_COOKIE_NAME}=${tok}` },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as ItemOut;
}

export default async function ItemLabelPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idStr } = await params;
  const id = Number(idStr);
  if (isNaN(id)) redirect("/dashboard");

  const item = await fetchItem(id);
  if (!item) {
    return <div className="p-6 text-h-muted">Item not found.</div>;
  }

  return (
    <ItemLabelClient
      itemId={id}
      itemNumber={item.item_number}
      code={item.code}
      description={item.description}
    />
  );
}

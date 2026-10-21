import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";

import { BudgetReport } from "./_components/BudgetReport";

/**
 * The budget across every cost centre (managers and admins; the API's 403 is the real control).
 * It sits under the Orderbook rather than on the tab strip: the budget informs, it never blocks an
 * order, and it is the Orderbook's own money.
 */
export const metadata: Metadata = { title: "Budget report" };

export default async function Page() {
  const me = await fetchMe();
  if (!me) redirect("/login");
  const allowed = me.auth_role === "manager" || me.auth_role === "admin";
  return (
    <div className="grid gap-4">
      <header className="flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-h-ink">Budget report</h1>
        <Link href="/orderbook" className="text-sm text-h-muted hover:text-h-ink">Back to the Orderbook</Link>
      </header>
      {allowed
        ? <BudgetReport />
        : <p data-testid="budget-forbidden" className="text-sm text-h-muted">The budget is for managers and admins.</p>}
    </div>
  );
}

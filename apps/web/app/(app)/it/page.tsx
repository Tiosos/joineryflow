import { fetchMe } from "@/lib/session";
import { redirect } from "next/navigation";

import { LabourRatesPanel } from "./_components/LabourRatesPanel";
import { SearchHealthPanel } from "./_components/SearchHealthPanel";
import { WorkerRosterPanel } from "./_components/WorkerRosterPanel";

export default async function ITPage() {
  const me = await fetchMe();
  if (me?.auth_role !== "admin") redirect("/dashboard");
  return (
    <section className="grid gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-h-ink">IT Management</h1>
        <p className="text-sm text-h-muted">Admin-only.</p>
      </header>
      <WorkerRosterPanel />
      <LabourRatesPanel />
      <SearchHealthPanel />
    </section>
  );
}

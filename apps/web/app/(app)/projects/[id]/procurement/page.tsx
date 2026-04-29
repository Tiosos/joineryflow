import { fetchMe } from "@/lib/session";
import { redirect } from "next/navigation";
import { ProcurementTabs } from "./_components/ProcurementTabs";

interface Search {
  tab?: "materials" | "batches" | "catalog";
  catalog_type?: string;
  material_type?: string;
  material_id?: string;
  batch_id?: string;
  action?: "order" | "allocate";
  line_id?: string;
}

export default async function ProjectProcurementPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const me = await fetchMe();
  if (!me) {
    redirect("/login");
  }
  const { id } = await params;
  const sp = await searchParams;
  const tab = sp.tab ?? "materials";
  const pid = Number(id);
  const canWrite =
    !!me &&
    (me.auth_role === "admin" ||
      me.auth_role === "manager" ||
      me.auth_role === "drafter" ||
      me.auth_role === "purchase_officer");
  return (
    <div className="grid gap-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-h-ink">Procurement</h1>
        <p className="text-xs text-h-muted">Project #{pid}</p>
      </header>
      <ProcurementTabs
        projectId={pid}
        tab={tab}
        canWrite={canWrite}
        sp={sp as Record<string, string | undefined>}
      />
    </div>
  );
}

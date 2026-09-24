import { can, fetchMe } from "@/lib/session";
import { redirect } from "next/navigation";
import { ProcurementTabs } from "./_components/ProcurementTabs";

interface Search {
  tab?: "materials" | "summary" | "batches" | "catalog";
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
  // `materials` + `batches` gate on the `orderbook` module; the `catalog` tab
  // writes through `/catalog/{slug}`, which gates on the `catalog` module —
  // the two role sets differ (purchase_officer is read-only on catalog, editor
  // is read-only on orderbook), so they are threaded separately.
  const canWrite = can(me, "orderbook", "write");
  const canWriteCatalog = can(me, "catalog", "write");
  // The Material Summary (#12) gates on `list`: building needs drafter+ (the
  // API adds require_drafter), confirming needs `list` approve.
  const canEditSummary =
    can(me, "list", "write") && ["drafter", "manager", "admin"].includes(me.auth_role);
  const canConfirmSummary = can(me, "list", "approve");
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
        canWriteCatalog={canWriteCatalog}
        canEditSummary={canEditSummary}
        canConfirmSummary={canConfirmSummary}
        sp={sp as Record<string, string | undefined>}
      />
    </div>
  );
}

import { fetchMe } from "@/lib/session";
import { redirect } from "next/navigation";
import ProcurementTabs from "./_components/ProcurementTabs";

interface ProcurementPageProps {
  params: Promise<{ id: string }>;
}

export default async function ProcurementPage({ params }: ProcurementPageProps) {
  const me = await fetchMe();
  if (!me) {
    redirect("/login");
  }

  const { id } = await params;

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-bold px-6 py-4">Procurement</h1>
      <ProcurementTabs projectId={id} userRole={me.auth_role} />
    </div>
  );
}

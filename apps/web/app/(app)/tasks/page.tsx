import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { TaskPanel } from "@/components/tasks/TaskPanel";
import { can, fetchMe } from "@/lib/session";

export const metadata: Metadata = { title: "Tasks" };

export default async function TasksPage({
  searchParams,
}: {
  searchParams: Promise<{ task?: string }>;
}) {
  const me = await fetchMe();
  if (!me) redirect("/login");
  const sp = await searchParams;
  const highlight = sp.task && /^\d+$/.test(sp.task) ? Number(sp.task) : null;
  return (
    <div className="grid max-w-3xl gap-4">
      <h1 className="text-lg font-semibold text-h-ink">Tasks</h1>
      <TaskPanel
        scope={{ kind: "mine" }}
        meId={me.id}
        meRole={me.auth_role}
        highlight={highlight}
        canCreate
      />
    </div>
  );
}

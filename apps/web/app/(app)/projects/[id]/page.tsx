import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import type { ProjectOut } from "@/lib/pm-types";
import { can, fetchMe, SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";
import { ProjectHeader } from "./_components/ProjectHeader";
import { ProjectDetailsPanel } from "./_components/ProjectDetailsPanel";
import { ProjectContactsPanel } from "./_components/ProjectContactsPanel";
import { ProjectLiftAccessPanel } from "./_components/ProjectLiftAccessPanel";
import { ProjectLabourHoursCard } from "./_components/ProjectLabourHoursCard";

async function fetchProject(id: number, cookieHeader: string): Promise<ProjectOut | null> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/projects/${id}`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as ProjectOut;
}

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idStr } = await params;
  const id = Number(idStr);
  if (isNaN(id)) redirect("/projects");

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";
  const cookieHeader = `${COOKIE_NAME}=${tok}`;

  const [project, me] = await Promise.all([
    fetchProject(id, cookieHeader),
    fetchMe(),
  ]);

  if (!project) {
    return <div className="p-6 text-h-muted">Project not found.</div>;
  }

  // PATCH /projects/{id} (Details) and close-out are manager/admin only —
  // a manual route check, not the tracking:write RBAC row. Contacts and
  // lift access reuse tracking:write, which is one role wider (editor too).
  const canEditDetails = me?.auth_role === "manager" || me?.auth_role === "admin";
  const canEditTracking = can(me, "tracking", "write");

  return (
    <div className="grid gap-4">
      <ProjectHeader project={project} canCloseOut={canEditDetails} />

      <div className="grid gap-4 lg:grid-cols-3">
        <ProjectDetailsPanel project={project} canEdit={canEditDetails} />
        <ProjectContactsPanel
          projectId={project.id}
          contacts={project.contacts}
          canEdit={canEditTracking}
        />
        <ProjectLiftAccessPanel
          projectId={project.id}
          liftAccess={project.lift_access}
          canEdit={canEditTracking}
        />
      </div>

      <ProjectLabourHoursCard hours={project.labour_hours} />
    </div>
  );
}

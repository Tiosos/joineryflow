import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import type { ProjectOut } from "@/lib/pm-types";
import type { ActualCosts, ProjectContract } from "@/lib/project-contract-types";
import { can, fetchMe, SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";
import { ProjectHeader } from "./_components/ProjectHeader";
import { ProjectDetailsPanel } from "./_components/ProjectDetailsPanel";
import { ProjectContactsPanel } from "./_components/ProjectContactsPanel";
import { ProjectLiftAccessPanel } from "./_components/ProjectLiftAccessPanel";
import { ProjectLabourHoursCard } from "./_components/ProjectLabourHoursCard";
import { ProjectFinancialsCard } from "./_components/ProjectFinancialsCard";
import { ProjectCommentsCard } from "./_components/ProjectCommentsCard";
import { ProjectAreasCommentsCard } from "./_components/ProjectAreasCommentsCard";

async function fetchProject(id: number, cookieHeader: string): Promise<ProjectOut | null> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/projects/${id}`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as ProjectOut;
}

// null when the project predates Q491 or wasn't created from a converted
// estimate — no project_contract row exists yet, which is not an error.
async function fetchContract(id: number, cookieHeader: string): Promise<ProjectContract | null> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/projects/${id}/contract`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as ProjectContract;
}

async function fetchActualCosts(id: number, cookieHeader: string): Promise<ActualCosts> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/projects/${id}/actual-costs`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) {
    return { project_id: id, materials_actual: "0", labour_actual: "0", total_actual: "0", labour_by_item: {} };
  }
  return (await r.json()) as ActualCosts;
}

// `?area=<id>` / `?room=<id>` open that thread on the Areas & Rooms card — what
// a notification for an Area or Room comment links to.
function initialSelection(sp: {
  area?: string;
  room?: string;
}): { type: "area" | "room"; id: number } | null {
  const room = Number(sp.room);
  if (sp.room && Number.isInteger(room) && room > 0) return { type: "room", id: room };
  const area = Number(sp.area);
  if (sp.area && Number.isInteger(area) && area > 0) return { type: "area", id: area };
  return null;
}

export default async function ProjectDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ area?: string; room?: string }>;
}) {
  const { id: idStr } = await params;
  const sp = await searchParams;
  const id = Number(idStr);
  if (isNaN(id)) redirect("/projects");

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";
  const cookieHeader = `${COOKIE_NAME}=${tok}`;

  const [project, me, contract, actualCosts] = await Promise.all([
    fetchProject(id, cookieHeader),
    fetchMe(),
    fetchContract(id, cookieHeader),
    fetchActualCosts(id, cookieHeader),
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

      <ProjectFinancialsCard
        projectId={project.id}
        contract={contract}
        actualCosts={actualCosts}
        canEdit={canEditTracking}
      />

      <ProjectLabourHoursCard hours={project.labour_hours} />

      <ProjectCommentsCard
        projectId={project.id}
        currentUserId={me?.id ?? null}
        currentUserRole={me?.auth_role ?? null}
        canComment={can(me, "tracking", "comment")}
      />

      <ProjectAreasCommentsCard
        projectId={project.id}
        currentUserId={me?.id ?? null}
        currentUserRole={me?.auth_role ?? null}
        canComment={can(me, "tracking", "comment")}
        initialSelection={initialSelection(sp)}
      />
    </div>
  );
}

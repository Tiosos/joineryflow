import { cookies } from "next/headers";
import { TrackingClient } from "./_components/TrackingClient";
import type {
  ProjectListOut,
  ProjectOut,
  TrackingGridOut,
} from "@/lib/pm-types";
import { fetchMe, SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";

interface SearchParams {
  project_id?: string;
}

async function apiGet<T>(path: string, cookieHeader: string): Promise<T | null> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}${path}`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as T;
}

export default async function TrackingPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";
  const cookieHeader = `${COOKIE_NAME}=${tok}`;

  const [me, projectList] = await Promise.all([
    fetchMe(),
    apiGet<ProjectListOut>("/projects", cookieHeader),
  ]);

  const projects = projectList?.projects ?? [];

  const pid =
    sp.project_id != null && sp.project_id !== ""
      ? Number(sp.project_id)
      : projects[0]?.id ?? null;

  if (pid == null || Number.isNaN(pid)) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
        No projects available in this workspace yet.
      </div>
    );
  }

  const [project, grid] = await Promise.all([
    apiGet<ProjectOut>(`/projects/${pid}`, cookieHeader),
    apiGet<TrackingGridOut>(`/projects/${pid}/items`, cookieHeader),
  ]);

  if (!project) {
    return <div className="p-6 text-h-muted">Project not found.</div>;
  }

  const canEdit =
    me?.auth_role === "drafter" ||
    me?.auth_role === "manager" ||
    me?.auth_role === "admin";
  const procurementReady =
    process.env.NEXT_PUBLIC_PROCUREMENT_UI_READY === "1";

  return (
    <TrackingClient
      project={project}
      projects={projects}
      items={grid?.items ?? []}
      me={me}
      canEdit={canEdit}
      procurementReady={procurementReady}
    />
  );
}

import type { Metadata } from "next";
import { cookies } from "next/headers";
import { AllProjectsTracking } from "./_components/AllProjectsTracking";
import { TrackingClient } from "./_components/TrackingClient";
import type {
  CardFilter,
  ProjectListOut,
  ProjectOut,
  TrackingAllOut,
  TrackingGridOut,
} from "@/lib/pm-types";
import { fetchMe, SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";

interface SearchParams {
  project_id?: string;
  deleted?: string;
  /** `all`: Tracking's All projects scope (Q633). */
  scope?: string;
  filter?: string;
  status?: string;
  stage?: string;
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

export const metadata: Metadata = { title: "Tracking" };

export default async function TrackingPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";
  const cookieHeader = `${COOKIE_NAME}=${tok}`;

  // Q633: a dashboard card opens the items it counted, across projects.
  if (sp.scope === "all") {
    const filter = (["overdue", "in_optimisation", "awaiting_install"] as const).find((f) => f === sp.filter) ?? null;
    const qs = new URLSearchParams();
    if (filter) qs.set("filter", filter satisfies CardFilter);
    if (sp.status) qs.set("status", sp.status);
    if (sp.stage) qs.set("stage", sp.stage);
    const all = await apiGet<TrackingAllOut>(`/tracking/items${qs.size ? `?${qs}` : ""}`, cookieHeader);
    if (!all) return <div className="p-6 text-h-muted">Unable to load items.</div>;
    return <AllProjectsTracking filter={filter} items={all.items} today={new Date().toISOString().slice(0, 10)} />;
  }

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

  const deletedView = sp.deleted === "1";

  const [project, grid] = await Promise.all([
    apiGet<ProjectOut>(`/projects/${pid}`, cookieHeader),
    apiGet<TrackingGridOut>(
      `/projects/${pid}/items${deletedView ? "?deleted=true" : ""}`,
      cookieHeader,
    ),
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
      deletedView={deletedView}
    />
  );
}

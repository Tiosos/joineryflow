import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe, SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";
import type { ProjectListOut, TrackingGridOut } from "@/lib/pm-types";

import ListClient from "./_components/ListClient";

const API = process.env.API_URL ?? "http://api:8000";

interface SearchParams {
  project_id?: string;
}

async function apiGet<T>(path: string, cookieHeader: string): Promise<T | null> {
  const r = await fetch(`${API}${path}`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as T;
}

export default async function ListPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const me = await fetchMe();
  if (!me) redirect("/login");

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";
  const cookieHeader = `${COOKIE_NAME}=${tok}`;

  const projectList = await apiGet<ProjectListOut>("/projects", cookieHeader);
  const projects = projectList?.projects ?? [];

  if (projects.length === 0) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
        No projects available in this workspace yet.
      </div>
    );
  }

  const pid =
    sp.project_id != null && sp.project_id !== ""
      ? Number(sp.project_id)
      : projects[0].id;

  const grid = await apiGet<TrackingGridOut>(`/projects/${pid}/items`, cookieHeader);

  return (
    <ListClient
      projects={projects}
      items={grid?.items ?? []}
      selectedProjectId={pid}
    />
  );
}

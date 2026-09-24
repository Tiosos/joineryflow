import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe, SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";
import type { ProjectListOut, TrackingGridOut } from "@/lib/pm-types";
import type { CutlistDetailOut, CutlistListOut } from "@/lib/cutlist-types";

import CutlistClient from "./_components/CutlistClient";

const API = process.env.API_URL ?? "http://api:8000";

interface SearchParams {
  project_id?: string;
  /** Q478: the open cutlist is in the URL, so a deep link (and a Q545 tab) restores it. */
  cutlist?: string;
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

  // The grid is here for the link picker: an item can hold at most one cutlist
  // (Q411), so the candidates are the project's Joinery Items with none yet.
  // `cutlist_id` on the row is what C2 added, so no extra endpoint is needed.
  const [cutlistList, grid] = await Promise.all([
    apiGet<CutlistListOut>(`/projects/${pid}/cutlists`, cookieHeader),
    apiGet<TrackingGridOut>(`/projects/${pid}/items`, cookieHeader),
  ]);

  const openId = sp.cutlist != null && sp.cutlist !== "" ? Number(sp.cutlist) : null;
  const open =
    openId != null
      ? await apiGet<CutlistDetailOut>(`/cutlists/${openId}`, cookieHeader)
      : null;

  return (
    <CutlistClient
      me={me}
      projects={projects}
      selectedProjectId={pid}
      cutlists={cutlistList?.cutlists ?? []}
      unlinkedItems={(grid?.items ?? []).filter(
        (i) => i.row_type !== "related_part" && i.cutlist_id == null,
      )}
      open={open}
    />
  );
}

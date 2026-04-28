import { cookies } from "next/headers";
import { TrackingGrid } from "@/components/pm/TrackingGrid";
import { TrackingFilters } from "@/components/pm/TrackingFilters";
import type { ProjectOut, TrackingGridOut } from "@/lib/pm-types";
import { fetchMe } from "@/lib/session";

const COOKIE_NAME = "jf_session";

interface SearchParams {
  project_id?: string;
  status?: string;
  stage?: string;
  q?: string;
}

async function fetchProject(
  pid: number,
  cookieHeader: string,
): Promise<ProjectOut | null> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/projects/${pid}`, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as ProjectOut;
}

async function fetchGrid(
  pid: number,
  qs: URLSearchParams,
  cookieHeader: string,
): Promise<TrackingGridOut | null> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const url = `${apiUrl}/projects/${pid}/items${qs.toString() ? `?${qs}` : ""}`;
  const r = await fetch(url, {
    headers: { cookie: cookieHeader },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as TrackingGridOut;
}

export default async function TrackingPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  const pid = sp.project_id ? Number(sp.project_id) : null;

  if (!pid) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
        Pick a project from the sidebar to view its tracking grid.
      </div>
    );
  }

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";
  const cookieHeader = `${COOKIE_NAME}=${tok}`;

  const qs = new URLSearchParams();
  if (sp.status) qs.set("status", sp.status);
  if (sp.stage) qs.set("stage", sp.stage);
  if (sp.q) qs.set("q", sp.q);

  const me = await fetchMe();
  const [project, grid] = await Promise.all([
    fetchProject(pid, cookieHeader),
    fetchGrid(pid, qs, cookieHeader),
  ]);

  if (!project) {
    return <div className="p-6 text-h-muted">Project not found.</div>;
  }

  const canEdit =
    me?.auth_role === "drafter" ||
    me?.auth_role === "manager" ||
    me?.auth_role === "admin";

  return (
    <div className="grid gap-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-xl font-semibold text-h-ink">{project.name}</h1>
          <p className="font-mono text-xs text-h-muted">{project.project_code}</p>
        </div>
        {process.env.NEXT_PUBLIC_PROCUREMENT_UI_READY === "1" && (
          <button
            type="button"
            className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink hover:bg-h-bg"
          >
            Open Procurement
          </button>
        )}
      </header>

      <TrackingFilters />

      {grid && grid.items.length > 0 ? (
        <TrackingGrid items={grid.items} canEdit={canEdit} />
      ) : (
        <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
          No items match your filters.
        </div>
      )}
    </div>
  );
}

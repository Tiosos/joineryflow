import Link from "next/link";
import { cookies } from "next/headers";
import type { ProjectListOut } from "@/lib/pm-types";
import { fetchMe } from "@/lib/session";
import { SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session-cookie";
import { CreateProjectDrawer } from "./_components/CreateProjectDrawer";


async function fetchProjects(): Promise<ProjectListOut> {
  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value;
  if (!tok) return { projects: [] };
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/projects`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return { projects: [] };
  return (await r.json()) as ProjectListOut;
}

export default async function ProjectsPage() {
  const me = await fetchMe();
  const { projects } = await fetchProjects();
  const canCreate =
    me?.auth_role === "manager" || me?.auth_role === "admin";

  return (
    <div className="grid gap-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-h-ink">Projects</h1>
        {canCreate && <CreateProjectDrawer />}
      </header>

      <div className="overflow-x-auto rounded-lg border border-h-line bg-h-surface">
        <table className="w-full text-sm">
          <thead className="bg-h-bg text-h-muted">
            <tr>
              <th className="px-3 py-2 text-left font-mono text-xs uppercase">
                Code
              </th>
              <th className="px-3 py-2 text-left font-mono text-xs uppercase">
                Name
              </th>
              <th className="px-3 py-2 text-left font-mono text-xs uppercase">
                PM
              </th>
              <th className="px-3 py-2 text-left font-mono text-xs uppercase">
                Status
              </th>
              <th className="px-3 py-2 text-right font-mono text-xs uppercase">
                Items
              </th>
              <th className="px-3 py-2 text-left font-mono text-xs uppercase">
                Install
              </th>
              <th className="px-3 py-2 text-left font-mono text-xs uppercase" />
            </tr>
          </thead>
          <tbody>
            {projects.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-3 py-8 text-center text-h-muted"
                >
                  No projects yet.
                </td>
              </tr>
            ) : (
              projects.map((p) => (
                <tr
                  key={p.id}
                  className="border-t border-h-line hover:bg-h-bg"
                >
                  <td className="px-3 py-2 font-mono text-h-muted">
                    {p.project_code}
                  </td>
                  <td className="px-3 py-2 text-h-ink">
                    <Link
                      href={`/tracking?project_id=${p.id}`}
                      className="hover:text-h-accent"
                    >
                      {p.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-h-muted">
                    {p.pm_name ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-h-muted">
                    {p.status ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-h-ink">
                    {p.item_count}
                  </td>
                  <td className="px-3 py-2 font-mono text-h-muted">
                    {p.install_start ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      href={`/projects/${p.id}`}
                      className="text-xs text-h-accent hover:underline"
                    >
                      Details →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

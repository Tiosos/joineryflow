import { cookies } from "next/headers";
import { ProjectSidebar } from "./ProjectSidebar";
import type { ProjectListOut } from "@/lib/pm-types";
import { SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session-cookie";

const API = process.env.API_URL ?? "http://api:8000";

async function fetchProjects(
  tok: string,
  fav: boolean,
): Promise<ProjectListOut> {
  const r = await fetch(`${API}/projects?fav=${fav}`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  });
  if (!r.ok) return { projects: [] };
  return r.json() as Promise<ProjectListOut>;
}

export async function SideBar() {
  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value ?? "";

  const [all, favs] = await Promise.all([
    fetchProjects(tok, false).catch(() => ({ projects: [] })),
    fetchProjects(tok, true).catch(() => ({ projects: [] })),
  ]);

  return (
    <div className="flex flex-col">
      <ProjectSidebar all={all.projects} favourites={favs.projects} />
    </div>
  );
}

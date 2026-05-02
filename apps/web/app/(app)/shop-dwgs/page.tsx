import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { fetchMe } from "@/lib/session";
import type { ProjectListOut } from "@/lib/pm-types";
import type { Subtab } from "@/lib/shop-drawings-types";
import ShopDwgsClient from "./_components/ShopDwgsClient";

const COOKIE_NAME = "jf_session";

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

interface PageProps {
  searchParams: Promise<{
    subtab?: string;
    project?: string;
    room?: string;
    q?: string;
    drawing?: string;
    rev?: string;
  }>;
}

export default async function Page({ searchParams }: PageProps) {
  const sp = await searchParams;
  const me = await fetchMe();
  if (!me) {
    redirect("/login");
  }

  const { projects } = await fetchProjects();

  const subtab: Subtab =
    sp.subtab === "in_review" || sp.subtab === "archive"
      ? sp.subtab
      : "current";
  const projectId = sp.project ? Number(sp.project) : (projects[0]?.id ?? null);

  return (
    <ShopDwgsClient
      me={me}
      projects={projects.map((p) => ({
        id: p.id,
        project_code: p.project_code,
        name: p.name,
      }))}
      initialProjectId={projectId}
      initialSubtab={subtab}
      initialRoom={sp.room ?? null}
      initialQ={sp.q ?? null}
      initialDrawingId={sp.drawing ? Number(sp.drawing) : null}
      initialRevId={sp.rev ? Number(sp.rev) : null}
    />
  );
}

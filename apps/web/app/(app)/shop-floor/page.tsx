import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";

import { ShopFloorClient } from "./_components/ShopFloorClient";

const COOKIE_NAME = "jf_session";

interface PageProps {
  searchParams: Promise<{ project?: string }>;
}

export default async function ShopFloorPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const me = await fetchMe();
  if (!me) {
    redirect("/login");
  }

  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value;
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const projectsRes = tok
    ? await fetch(`${apiUrl}/projects`, {
        headers: { cookie: `${COOKIE_NAME}=${tok}` },
        cache: "no-store",
      }).catch(() => null)
    : null;
  const projects: { id: number; project_code: string; name: string }[] =
    projectsRes && projectsRes.ok
      ? (await projectsRes.json()).projects
      : [];

  const projectId = sp.project ? Number(sp.project) : (projects[0]?.id ?? null);

  return (
    <ShopFloorClient
      me={me}
      projects={projects}
      initialProjectId={projectId}
    />
  );
}

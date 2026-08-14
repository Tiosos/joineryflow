import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";
import { SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session-cookie";

import { CutFloorClient } from "./_components/CutFloorClient";


interface PageProps {
  searchParams: Promise<{
    date?: string;
    project?: string;
  }>;
}

function todayIso(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default async function CutFloorPage({ searchParams }: PageProps) {
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

  const date = sp.date && /^\d{4}-\d{2}-\d{2}$/.test(sp.date)
    ? sp.date
    : todayIso();
  const projectId = sp.project ? Number(sp.project) : null;

  return (
    <CutFloorClient
      me={me}
      projects={projects}
      initialDate={date}
      initialProjectId={projectId}
    />
  );
}

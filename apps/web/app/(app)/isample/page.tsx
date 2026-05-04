import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";

import ISampleClient from "./_components/ISampleClient";

const COOKIE_NAME = "jf_session";

interface PageProps {
  searchParams: Promise<{
    subtab?: string;
    project?: string;
    q?: string;
    status?: string;
    supplier?: string;
    sample?: string;
    new?: string;
  }>;
}

export default async function Page({ searchParams }: PageProps) {
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
    projectsRes && projectsRes.ok ? (await projectsRes.json()).projects : [];

  const subtab: "board" | "ledger" | "archive" =
    sp.subtab === "ledger" || sp.subtab === "archive" ? sp.subtab : "board";
  const projectId = sp.project ? Number(sp.project) : (projects[0]?.id ?? null);

  return (
    <ISampleClient
      me={me}
      projects={projects}
      initialProjectId={projectId}
      initialSubtab={subtab}
      initialQ={sp.q ?? null}
      initialStatus={sp.status ?? null}
      initialSupplier={sp.supplier ?? null}
      initialSampleId={sp.sample ? Number(sp.sample) : null}
      initialNewOpen={sp.new === "1"}
    />
  );
}

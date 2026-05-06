import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";

import CatalogClient from "./_components/CatalogClient";

const COOKIE_NAME = "jf_session";

interface PageProps {
  searchParams: Promise<{
    tab?: string;
    q?: string;
    supplier?: string;
    archived?: string;
    project?: string;
  }>;
}

const VALID_TABS = [
  "board",
  "hardware",
  "custom_made",
  "benchtop",
  "appliance",
  "hire",
  "cv-mappings",
] as const;

type CatalogTab = (typeof VALID_TABS)[number];

export default async function Page({ searchParams }: PageProps) {
  const sp = await searchParams;
  const me = await fetchMe();
  if (!me) redirect("/login");

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

  const tab: CatalogTab = (VALID_TABS as readonly string[]).includes(sp.tab ?? "")
    ? (sp.tab as CatalogTab)
    : "board";

  return (
    <CatalogClient
      me={me}
      projects={projects}
      initialTab={tab}
      initialQ={sp.q ?? null}
      initialSupplier={sp.supplier ?? null}
      initialArchived={sp.archived === "true"}
      initialProjectId={sp.project ? Number(sp.project) : null}
    />
  );
}

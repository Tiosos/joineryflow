import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";
import { SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session-cookie";

import { QcDashboardClient } from "./_components/QcDashboardClient";

interface PageProps {
  searchParams: Promise<{ project?: string; from?: string; to?: string }>;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export default async function QcPage({ searchParams }: PageProps) {
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

  const projectId = sp.project && /^\d+$/.test(sp.project) ? Number(sp.project) : null;
  let dateFrom = sp.from && ISO_DATE.test(sp.from) ? sp.from : "";
  let dateTo = sp.to && ISO_DATE.test(sp.to) ? sp.to : "";
  // ISO dates sort as strings. An inverted range is a 422 from the API, so a
  // hand-edited link drops the range rather than opening on an error.
  if (dateFrom && dateTo && dateFrom > dateTo) {
    dateFrom = "";
    dateTo = "";
  }
  return (
    <QcDashboardClient
      projects={projects}
      initial={{ projectId, dateFrom, dateTo }}
    />
  );
}

import { redirect } from "next/navigation";

import { fetchMe } from "@/lib/session";

import { StationClient } from "./_components/StationClient";

interface PageProps {
  params: Promise<{ worker_id: string }>;
}

export default async function StationPage({ params }: PageProps) {
  const { worker_id: widStr } = await params;
  const workerId = Number(widStr);
  if (Number.isNaN(workerId)) redirect("/shop-floor");

  const me = await fetchMe();
  if (!me) {
    redirect("/login");
  }

  return <StationClient me={me} workerId={workerId} />;
}

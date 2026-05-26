import { cookies } from "next/headers";
import { MetricCard } from "@/components/pm/MetricCard";
import { MyDayList } from "@/components/pm/MyDayList";
import { DeliveriesList } from "@/components/pm/DeliveriesList";
import { TeamActivityFeed } from "@/components/pm/TeamActivityFeed";
import { TeamCard } from "@/components/pm/TeamCard";
import type { HomeDashboardOut, TeamOut } from "@/lib/pm-types";
import { SESSION_COOKIE_NAME as COOKIE_NAME } from "@/lib/session";

async function apiGet<T>(path: string, tok: string): Promise<T | null> {
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}${path}`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as T;
}

export default async function DashboardPage() {
  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value;
  if (!tok) {
    return <div className="p-6 text-h-muted">Unable to load dashboard.</div>;
  }
  const [data, team] = await Promise.all([
    apiGet<HomeDashboardOut>("/home/dashboard", tok),
    apiGet<TeamOut>("/workspace/team", tok),
  ]);
  if (!data) {
    return <div className="p-6 text-h-muted">Unable to load dashboard.</div>;
  }
  return (
    <div className="grid gap-6">
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {data.metrics.map((m) => (
          <MetricCard key={m.key} label={m.label} value={m.value} href={m.href} />
        ))}
      </section>
      <section className="grid gap-6 lg:grid-cols-2">
        <MyDayList items={data.my_day} />
        <DeliveriesList items={data.deliveries_today} />
      </section>
      {team && team.members.length > 0 ? <TeamCard members={team.members} /> : null}
      <TeamActivityFeed rows={data.team_activity} />
    </div>
  );
}

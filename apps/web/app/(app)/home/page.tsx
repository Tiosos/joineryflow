import { cookies } from "next/headers";
import { MetricCard } from "@/components/pm/MetricCard";
import { MyDayList } from "@/components/pm/MyDayList";
import { DeliveriesList } from "@/components/pm/DeliveriesList";
import { TeamActivityFeed } from "@/components/pm/TeamActivityFeed";
import type { HomeDashboardOut } from "@/lib/pm-types";

const COOKIE_NAME = "jf_session";

async function fetchDashboard(): Promise<HomeDashboardOut | null> {
  const c = await cookies();
  const tok = c.get(COOKIE_NAME)?.value;
  if (!tok) return null;
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/home/dashboard`, {
    headers: { cookie: `${COOKIE_NAME}=${tok}` },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as HomeDashboardOut;
}

export default async function HomePage() {
  const data = await fetchDashboard();
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
      <TeamActivityFeed rows={data.team_activity} />
    </div>
  );
}

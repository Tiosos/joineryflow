import { fetchMe } from "@/lib/session";

export default async function Page() {
  const me = await fetchMe();
  return (
    <section>
      <h1 className="text-2xl font-semibold text-h-ink">Dashboard</h1>
      <p className="text-sm text-h-muted">
        Stub. Welcome, {me?.full_name ?? "user"}.
      </p>
    </section>
  );
}

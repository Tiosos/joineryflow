import { fetchMe } from "@/lib/session";
import { redirect } from "next/navigation";

export default async function ITPage() {
  const me = await fetchMe();
  if (me?.auth_role !== "admin") redirect("/dashboard");
  return (
    <section>
      <h1 className="text-2xl font-semibold text-h-ink">IT Management</h1>
      <p className="text-sm text-h-muted">Stub. Admin-only.</p>
    </section>
  );
}

import { fetchMe } from "@/lib/session";

export default async function Page() {
  const me = await fetchMe();
  return (
    <section>
      <h1 className="text-2xl font-semibold text-h-ink">Tracking</h1>
      <p className="text-sm text-h-muted">
        Stub. Implemented in PM Workbench sub-project.
      </p>
      {me?.auth_role === "purchase_officer" && (
        <p className="mt-4 text-sm text-h-accent">
          Read-only + comment mode (Purchase Officer).
        </p>
      )}
    </section>
  );
}

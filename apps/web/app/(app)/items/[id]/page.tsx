import { redirect } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { fetchMe, getSessionCookie } from "@/lib/session";
import { SESSION_COOKIE_NAME } from "@/lib/session-cookie";
import { ItemHeader } from "./_components/ItemHeader";
import { ItemMetadataPanel } from "./_components/ItemMetadataPanel";
import { EditorTabs } from "./_components/EditorTabs";
import { SoftLockBanner } from "./_components/SoftLockBanner";
import { EditorFooter } from "./_components/EditorFooter";

async function fetchItem(id: number): Promise<ItemOut | null> {
  const tok = await getSessionCookie();
  if (!tok) return null;
  const apiUrl = process.env.API_URL ?? "http://api:8000";
  const r = await fetch(`${apiUrl}/items/${id}`, {
    headers: { cookie: `${SESSION_COOKIE_NAME}=${tok}` },
    cache: "no-store",
  }).catch(() => null);
  if (!r || !r.ok) return null;
  return (await r.json()) as ItemOut;
}

export default async function ItemEditorPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { id: idStr } = await params;
  const id = Number(idStr);
  if (isNaN(id)) redirect("/dashboard");

  const sp = await searchParams;
  const tab = sp.tab ?? "cutlist";

  const [item, me] = await Promise.all([
    fetchItem(id),
    fetchMe(),
  ]);

  if (!item) {
    return <div className="p-6 text-h-muted">Item not found.</div>;
  }

  return (
    <div className="grid gap-4">
      <ItemHeader item={item} />
      {item.lock_warning && (
        <SoftLockBanner warning={item.lock_warning} />
      )}
      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <ItemMetadataPanel item={item} />
        <EditorTabs item={item} active={tab} currentUserRole={me?.auth_role ?? null} />
      </div>
      <EditorFooter
        item={item}
        currentUserId={me?.id ?? null}
        currentUserRole={me?.auth_role ?? null}
      />
    </div>
  );
}

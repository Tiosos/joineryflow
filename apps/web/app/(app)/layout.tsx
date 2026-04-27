import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { fetchMe } from "@/lib/session";
import { HAppChrome } from "@/components/chrome/HAppChrome";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const me = await fetchMe();
  if (!me) redirect("/login");
  const h = await headers();
  const pathname = h.get("x-pathname") ?? "";
  const editorMode = pathname.startsWith("/items/");
  return (
    <HAppChrome user={me} editorMode={editorMode}>
      {children}
    </HAppChrome>
  );
}

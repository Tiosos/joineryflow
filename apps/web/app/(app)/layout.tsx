import { redirect } from "next/navigation";
import { fetchMe } from "@/lib/session";
import { HAppChrome } from "@/components/chrome/HAppChrome";
import { SideBar } from "@/components/chrome/SideBar";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const me = await fetchMe();
  if (!me) redirect("/login");
  return (
    <HAppChrome user={me} sidebar={<SideBar />}>
      {children}
    </HAppChrome>
  );
}

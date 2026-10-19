import { redirect } from "next/navigation";
import { fetchMe } from "@/lib/session";
import { HAppChrome } from "@/components/chrome/HAppChrome";
import { SideBar } from "@/components/chrome/SideBar";
import { ConfirmProvider } from "@/components/confirm/ConfirmProvider";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const me = await fetchMe();
  if (!me) redirect("/login");
  return (
    <ConfirmProvider>
      <HAppChrome user={me} sidebar={<SideBar />}>
        {children}
      </HAppChrome>
    </ConfirmProvider>
  );
}

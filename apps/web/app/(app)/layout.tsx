import { redirect } from "next/navigation";
import { fetchMe } from "@/lib/session";
import { HAppChrome } from "@/components/chrome/HAppChrome";
import { SideBar } from "@/components/chrome/SideBar";
import { ConfirmProvider } from "@/components/confirm/ConfirmProvider";
import { UndoProvider } from "@/components/undo/UndoProvider";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const me = await fetchMe();
  if (!me) redirect("/login");
  return (
    <ConfirmProvider>
      <UndoProvider>
        <HAppChrome user={me} sidebar={<SideBar />}>
          {children}
        </HAppChrome>
      </UndoProvider>
    </ConfirmProvider>
  );
}

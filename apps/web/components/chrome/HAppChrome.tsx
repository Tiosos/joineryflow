import type { Me } from "@/lib/session";
import { TopBar } from "./TopBar";
import { TabStrip } from "./TabStrip";
import { SideBar } from "./SideBar";

interface HAppChromeProps {
  user: Me;
  children: React.ReactNode;
}

export function HAppChrome({ user, children }: HAppChromeProps) {
  return (
    <div className="min-h-screen bg-h-bg">
      <TopBar user={user} />
      <TabStrip />
      <div className="flex">
        <SideBar />
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

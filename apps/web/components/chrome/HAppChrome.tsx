import type { Me } from "@/lib/session";
import { TopBar } from "./TopBar";
import { TabStrip } from "./TabStrip";
import { SideBar } from "./SideBar";

interface HAppChromeProps {
  user: Me;
  editorMode?: boolean;
  children: React.ReactNode;
}

export function HAppChrome({ user, editorMode, children }: HAppChromeProps) {
  return (
    <div className="min-h-screen bg-h-bg">
      <TopBar user={user} editorMode={editorMode} />
      {!editorMode && <TabStrip />}
      <div className="flex">
        {!editorMode && <SideBar />}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

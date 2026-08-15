"use client";

import { usePathname } from "next/navigation";
import type { Me } from "@/lib/session";
import { TopBar } from "./TopBar";
import { TabStrip } from "./TabStrip";

interface HAppChromeProps {
  user: Me;
  /** Server-rendered sidebar, passed as a slot from the layout. */
  sidebar: React.ReactNode;
  children: React.ReactNode;
}

const SIDEBAR_ROUTES = ["/dashboard", "/tracking", "/shop-dwgs"];

function showsSidebar(pathname: string): boolean {
  return SIDEBAR_ROUTES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

export function HAppChrome({ user, sidebar, children }: HAppChromeProps) {
  const pathname = usePathname();
  const editorMode = pathname.startsWith("/items/");
  const renderSidebar = !editorMode && showsSidebar(pathname);
  return (
    <div className="min-h-screen bg-h-bg">
      <TopBar user={user} editorMode={editorMode} />
      {!editorMode && <TabStrip user={user} />}
      <div className="flex">
        {renderSidebar && sidebar}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

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

// Tracking and Shop Dwgs are not listed: each has its own project switcher (Tracking's header
// bar, Shop Dwgs' filter row), and their tables need the width.
const SIDEBAR_ROUTES = ["/dashboard"];

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
        {/* The item editor needs `min-w-0`: a wide Cutlist or Material Take table would otherwise stretch
            <main> past the window and push the header's Delete and close buttons off-screen. The tables
            scroll inside their own box instead. */}
        <main className={editorMode ? "min-w-0 flex-1 p-6" : "flex-1 p-6"}>{children}</main>
      </div>
    </div>
  );
}

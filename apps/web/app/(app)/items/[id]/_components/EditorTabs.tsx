"use client";

import { useRouter, usePathname } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { CutlistTab } from "./cutlist/CutlistTab";
import { HardwareTab } from "./hardware/HardwareTab";
import { LogTab } from "./LogTab";

interface EditorTabsProps {
  item: ItemOut;
  active: string;
}

const TABS = ["cutlist", "hardware", "board", "log"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Record<Tab, string> = {
  cutlist: "Cutlist",
  hardware: "Hardware",
  board: "Board",
  log: "Log",
};

export function EditorTabs({ item, active }: EditorTabsProps) {
  const router = useRouter();
  const pathname = usePathname();

  const current = (TABS.includes(active as Tab) ? active : "cutlist") as Tab;

  function switchTab(tab: Tab) {
    router.push(`${pathname}?tab=${tab}`);
  }

  return (
    <div className="flex flex-col gap-0">
      <div role="tablist" className="flex border-b border-h-line">
        {TABS.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={current === tab}
            onClick={() => switchTab(tab)}
            className={[
              "px-4 py-2 text-sm capitalize",
              current === tab
                ? "border-b-2 border-h-accent font-medium text-h-ink"
                : "text-h-muted hover:text-h-ink",
            ].join(" ")}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      <div className="pt-4">
        {current === "cutlist" && <CutlistTab item={item} />}
        {current === "hardware" && <HardwareTab item={item} />}
        {current === "board" && (
          <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
            Board view ships in v2 with Cabinet Vision integration.
          </div>
        )}
        {current === "log" && <LogTab rows={item.edit_log} />}
      </div>
    </div>
  );
}

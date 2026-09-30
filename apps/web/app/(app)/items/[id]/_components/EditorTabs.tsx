"use client";

import { useRouter, usePathname } from "next/navigation";
import type { ItemOut } from "@/lib/pm-types";
import { CutlistTab } from "./cutlist/CutlistTab";
import { HardwareTab } from "./hardware/HardwareTab";
import { LogTab } from "./LogTab";
import AttachmentsTab from "./AttachmentsTab";
import { BoardTab } from "./BoardTab";
import { MaterialTakeTab } from "./MaterialTakeTab";
import { ActionsTab } from "./ActionsTab";
import { QueryTab } from "./QueryTab";
import { QcTab } from "./QcTab";
import { CommentThread } from "@/components/comments/CommentThread";

interface EditorTabsProps {
  item: ItemOut;
  active: string;
  currentUserRole: string | null;
  currentUserId: number | null;
  /** `tracking:comment` — comments on an item are gated by Tracking's grant. */
  canComment: boolean;
  /** `list:comment` — a module's thread is governed by the Cutlist's own grant. */
  canCommentOnModule: boolean;
}

const TABS = [
  "cutlist",
  "hardware",
  "board",
  "take",
  "attachments",
  "actions",
  "query",
  "comments",
  "qc",
  "log",
] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Record<Tab, string> = {
  cutlist: "Cutlist",
  hardware: "Hardware",
  board: "Board",
  take: "Material Take",
  attachments: "Attachments",
  actions: "Actions",
  query: "Query",
  comments: "Comments",
  qc: "QC",
  log: "Log",
};

export function EditorTabs({
  item,
  active,
  currentUserRole,
  currentUserId,
  canComment,
  canCommentOnModule,
}: EditorTabsProps) {
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
        {current === "cutlist" && (
          <CutlistTab
            item={item}
            currentUserId={currentUserId}
            currentUserRole={currentUserRole}
            canComment={canCommentOnModule}
          />
        )}
        {current === "hardware" && (
          <HardwareTab
            item={item}
            currentUserId={currentUserId}
            currentUserRole={currentUserRole}
          />
        )}
        {current === "board" && <BoardTab itemId={item.id} />}
        {current === "take" && (
          <MaterialTakeTab itemId={item.id} currentUserRole={currentUserRole} />
        )}
        {current === "attachments" && (
          <AttachmentsTab itemId={item.id} currentUserRole={currentUserRole} />
        )}
        {current === "actions" && (
          <ActionsTab
            item={item}
            currentUserId={currentUserId}
            currentUserRole={currentUserRole}
          />
        )}
        {current === "query" && (
          <QueryTab itemId={item.id} currentUserRole={currentUserRole} />
        )}
        {current === "comments" && (
          <CommentThread
            objectType="item"
            objectId={item.id}
            currentUserId={currentUserId}
            currentUserRole={currentUserRole}
            canComment={canComment}
          />
        )}
        {current === "qc" && (
          <QcTab itemId={item.id} currentUserRole={currentUserRole} />
        )}
        {current === "log" && <LogTab rows={item.edit_log} />}
      </div>
    </div>
  );
}

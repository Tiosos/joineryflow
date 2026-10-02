"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CommentThread } from "@/components/comments/CommentThread";
import type { ItemOut } from "@/lib/pm-types";
import { ModuleTree } from "./ModuleTree";
import { PartsGrid } from "./PartsGrid";
import { CvImportDialog } from "./CvImportDialog";
import { DeleteModuleDialog } from "./DeleteModuleDialog";
import { moduleLockReason } from "./moduleLock";

interface CutlistTabProps {
  item: ItemOut;
  currentUserId: number | null;
  currentUserRole: string | null;
  /** `list:comment` — a module's thread is governed by the Cutlist's own grant. */
  canComment: boolean;
}

/** `?module=<id>` selects a module — a notification for a module comment links
 *  to it. Anything that is not the id of one of this item's modules is ignored. */
function moduleFrom(params: URLSearchParams, item: ItemOut): number | null {
  const id = Number(params.get("module"));
  return Number.isInteger(id) && item.modules.some((m) => m.id === id) ? id : null;
}

export function CutlistTab({
  item,
  currentUserId,
  currentUserRole,
  canComment,
}: CutlistTabProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const importOpen = searchParams.get("import") === "cv";

  const urlModuleId = moduleFrom(searchParams, item);
  const [activeModuleId, setActiveModuleId] = useState<number | null>(
    urlModuleId ?? item.modules[0]?.id ?? null
  );

  // The URL changed without a click of ours (a notification followed while
  // already on this page, back/forward): follow it. After our own click this
  // just re-sets what is already selected.
  useEffect(() => {
    if (urlModuleId !== null) setActiveModuleId(urlModuleId);
  }, [urlModuleId]);

  // A click sets state and URL together, synchronously (`history.replaceState`,
  // which Next integrates with `useSearchParams`) — the same reasoning the
  // Areas & Rooms card documents: a router round trip would leave the previous
  // module's comment box on screen, typed into and then thrown away.
  function selectModule(id: number) {
    setActiveModuleId(id);
    // A module missing from the item's list was only just created: ModuleTree
    // adds one, calls `router.refresh()` and selects it in the same tick. A
    // `replaceState` there raced that refresh and the refreshed list never
    // arrived, leaving the empty state on screen. The URL only matters for
    // links, and this module has none yet.
    if (!item.modules.some((m) => m.id === id)) return;
    const next = new URLSearchParams(searchParams.toString());
    next.set("module", String(id));
    window.history.replaceState(null, "", `${pathname}?${next}`);
  }

  const activeModule = item.modules.find((m) => m.id === activeModuleId) ?? null;

  // `DELETE /modules/{id}` is gated `require_drafter()` — mirror it, the API decides.
  const canDeleteModule =
    currentUserRole === "drafter" || currentUserRole === "manager" || currentUserRole === "admin";
  const lockReason = moduleLockReason(item, currentUserId, currentUserRole);
  const [deleting, setDeleting] = useState(false);

  // The module is gone: refresh the list and select a neighbour. The URL is left
  // alone on purpose — a `replaceState` right after `router.refresh()` is the
  // race that once dropped the refreshed list (see `selectModule`); a stale
  // `?module=` is ignored because `moduleFrom` only accepts ids still in the item.
  function onModuleDeleted() {
    const gone = activeModule?.id;
    setDeleting(false);
    setActiveModuleId(item.modules.find((m) => m.id !== gone)?.id ?? null);
    router.refresh();
  }

  function openImport() {
    const sp = new URLSearchParams(searchParams.toString());
    sp.set("tab", "cutlist");
    sp.set("import", "cv");
    router.push(`?${sp.toString()}`);
  }

  function closeImport() {
    const sp = new URLSearchParams(searchParams.toString());
    sp.delete("import");
    router.push(`?${sp.toString()}`);
    router.refresh();
  }

  return (
    <>
      {canDeleteModule && lockReason && (
        <p
          data-testid="cutlist-locked"
          className="mb-3 rounded-md border border-h-line bg-h-surface px-3 py-2 text-xs text-h-muted"
        >
          {lockReason}
        </p>
      )}
      <div className="mb-3 flex items-center justify-end">
        <button
          type="button"
          onClick={openImport}
          disabled={lockReason !== null}
          title={lockReason ?? undefined}
          className="rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm font-medium text-h-ink hover:bg-h-surface disabled:cursor-not-allowed disabled:opacity-50"
        >
          Import from CV
        </button>
      </div>

      {item.modules.length === 0 ? (
        <div className="flex gap-4">
          <ModuleTree
            itemId={item.id}
            modules={item.modules}
            activeModuleId={null}
            onSelect={selectModule}
            lockReason={lockReason}
          />
          <div className="flex-1 rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
            Add a module to start the cutlist, or click <strong>Import from CV</strong>.
          </div>
        </div>
      ) : (
        <div className="flex gap-4">
          <ModuleTree
            itemId={item.id}
            modules={item.modules}
            activeModuleId={activeModuleId}
            onSelect={selectModule}
            lockReason={lockReason}
          />
          {activeModule ? (
            <div className="flex min-w-0 flex-1 flex-col gap-6">
              {canDeleteModule && (
                <div className="-mb-3 flex items-center justify-between gap-3">
                  <h3 className="truncate text-sm font-semibold text-h-ink">
                    {activeModule.name ?? "Untitled module"}
                  </h3>
                  <button
                    type="button"
                    data-testid="delete-module"
                    disabled={lockReason !== null}
                    title={lockReason ?? undefined}
                    onClick={() => setDeleting(true)}
                    className="shrink-0 rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm text-h-bad hover:bg-h-surface disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Delete module
                  </button>
                </div>
              )}
              <PartsGrid key={activeModule.id} module={activeModule} lockReason={lockReason} />
              <section
                data-testid="module-comments"
                className="rounded-lg border border-h-line bg-h-surface p-4"
              >
                <h3 className="mb-3 text-sm font-semibold text-h-ink">
                  Comments on {activeModule.name ?? "this module"}
                </h3>
                <CommentThread
                  key={activeModule.id}
                  objectType="module"
                  objectId={activeModule.id}
                  currentUserId={currentUserId}
                  currentUserRole={currentUserRole}
                  canComment={canComment}
                  onMutated={() => router.refresh()}
                />
              </section>
            </div>
          ) : (
            <div className="flex-1 text-sm text-h-muted">Select a module.</div>
          )}
        </div>
      )}

      {deleting && activeModule && (
        <DeleteModuleDialog
          moduleId={activeModule.id}
          moduleName={activeModule.name}
          onClose={() => setDeleting(false)}
          onDeleted={onModuleDeleted}
        />
      )}

      {importOpen && (
        <CvImportDialog
          itemId={item.id}
          itemHasModules={item.modules.length > 0}
          existingModuleCount={item.modules.length}
          onClose={closeImport}
        />
      )}
    </>
  );
}

"use client";
import { useEffect, useState } from "react";
import { PM } from "@/lib/pm-fetch";
import type { ModuleDeleteImpact } from "@/lib/pm-types";

interface Props {
  moduleId: number;
  moduleName: string | null;
  onClose: () => void;
  /** Called once the module is gone; the caller refreshes and re-selects. */
  onDeleted: () => void;
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** Confirm step before deleting one module. Deleting a module deletes its parts
 *  and any comments on it (a comment cascades with the module it is on), so the
 *  dialog says how many — read fresh when it opens, not from what the tab loaded.
 *  Advisory only: the API does not refuse the delete either way. */
export function DeleteModuleDialog({ moduleId, moduleName, onClose, onDeleted }: Props) {
  // "error" means the lookup failed — say so rather than imply the module is empty.
  const [impact, setImpact] = useState<ModuleDeleteImpact | "error" | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setImpact(null);
    PM.moduleDeleteImpact(moduleId)
      .then((i) => live && setImpact(i))
      .catch(() => live && setImpact("error"));
    return () => {
      live = false;
    };
  }, [moduleId]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function confirmDelete() {
    setBusy(true);
    setErr(null);
    try {
      await PM.deleteModule(moduleId);
      onDeleted();
    } catch (e: unknown) {
      const status = (e as { status?: number })?.status;
      // Already gone (another tab, another user): the goal is met.
      if (status === 404) {
        onDeleted();
        return;
      }
      setErr(status === 403 ? "You don't have permission to delete modules." : "Failed to delete the module.");
      setBusy(false);
    }
  }

  const empty = impact !== null && impact !== "error" && impact.parts === 0 && impact.live_comments === 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-module-title"
        data-testid="delete-module-dialog"
        className="w-[480px] rounded-lg bg-h-bg p-6 shadow-xl"
      >
        <h2 id="delete-module-title" className="mb-3 text-lg font-semibold text-h-ink">
          Delete {moduleName ? `“${moduleName}”` : "this module"}?
        </h2>

        {impact === null && <p className="text-sm text-h-muted">Checking what this will delete…</p>}

        {impact === "error" && (
          <p
            data-testid="delete-module-check-failed"
            className="rounded-lg border border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          >
            Couldn&apos;t check what this module contains. Deleting it also deletes its
            parts and any comments on it.
          </p>
        )}

        {impact !== null && impact !== "error" && (
          <p
            data-testid="delete-module-impact"
            className={
              empty
                ? "text-sm text-h-ink"
                : "rounded-lg border border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-900"
            }
          >
            {empty ? (
              "This module is empty."
            ) : (
              <>
                This permanently deletes the module and its{" "}
                <strong>{plural(impact.parts, "part")}</strong> and{" "}
                <strong>{plural(impact.live_comments, "comment")}</strong>. It can&apos;t be undone.
              </>
            )}
          </p>
        )}

        {err && <p className="mt-3 text-sm text-h-bad">{err}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-h-line bg-h-bg px-3 py-1 text-sm text-h-ink disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={confirmDelete}
            disabled={busy || impact === null}
            className="rounded-md bg-h-bad px-4 py-1 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? "Deleting…" : "Delete module"}
          </button>
        </div>
      </div>
    </div>
  );
}

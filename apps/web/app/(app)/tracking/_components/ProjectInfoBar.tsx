"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ProjectOut } from "@/lib/pm-types";

interface Props {
  project: ProjectOut;
  projects: ProjectOut[];
  onOpenInfo: () => void;
  onOpenProcurement: () => void;
  canEdit: boolean;
  procurementReady: boolean;
}

type Scope = "all" | "fav";

export function ProjectInfoBar({
  project,
  projects,
  onOpenInfo,
  onOpenProcurement,
  canEdit,
  procurementReady,
}: Props) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [scope, setScope] = useState<Scope>("all");
  const [isFav, setIsFav] = useState(project.is_favourite);
  const [pending, setPending] = useState(false);

  const visible = scope === "fav" ? projects.filter((p) => p.is_favourite) : projects;

  async function toggleFavourite() {
    if (pending) return;
    setPending(true);
    const next = !isFav;
    setIsFav(next);
    try {
      const r = await fetch(`/api/projects/${project.id}/favourites`, {
        method: next ? "POST" : "DELETE",
        cache: "no-store",
      });
      if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
    } catch {
      setIsFav(!next);
    } finally {
      setPending(false);
    }
  }

  function selectProject(pid: number) {
    setMenuOpen(false);
    router.push(`/tracking?project_id=${pid}`);
  }

  return (
    <div className="rounded-lg border border-h-line bg-h-surface p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-h-ink px-2 py-0.5 font-mono text-sm font-semibold text-white">
          {project.project_code}
        </span>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg"
          >
            <span>{project.name}</span>
            <span className="text-h-muted">▾</span>
          </button>
          {menuOpen ? (
            <div
              className="absolute left-0 top-full z-30 mt-1 w-72 rounded-lg border border-h-line bg-h-surface shadow-lg"
              onMouseLeave={() => setMenuOpen(false)}
            >
              <div className="flex items-center gap-1 border-b border-h-line p-2">
                <button
                  type="button"
                  onClick={() => setScope("fav")}
                  className={`flex-1 rounded px-2 py-1 text-xs ${
                    scope === "fav"
                      ? "bg-h-ink text-white"
                      : "border border-h-line text-h-muted hover:bg-h-bg"
                  }`}
                >
                  ★ FAV
                </button>
                <button
                  type="button"
                  onClick={() => setScope("all")}
                  className={`flex-1 rounded px-2 py-1 text-xs ${
                    scope === "all"
                      ? "bg-h-ink text-white"
                      : "border border-h-line text-h-muted hover:bg-h-bg"
                  }`}
                >
                  ALL
                </button>
              </div>
              <ul className="max-h-72 overflow-y-auto py-1">
                {visible.length === 0 ? (
                  <li className="px-3 py-2 text-xs text-h-muted">
                    No projects in scope.
                  </li>
                ) : (
                  visible.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => selectProject(p.id)}
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-h-bg ${
                          p.id === project.id
                            ? "bg-h-accent/10 text-h-ink"
                            : "text-h-ink"
                        }`}
                      >
                        <span className={p.is_favourite ? "text-h-accent" : "text-h-muted"}>
                          ★
                        </span>
                        <span className="flex-1 truncate">{p.name}</span>
                        <span className="font-mono text-[10px] text-h-muted">
                          {p.project_code}
                        </span>
                      </button>
                    </li>
                  ))
                )}
              </ul>
            </div>
          ) : null}
        </div>

        <button
          type="button"
          onClick={toggleFavourite}
          disabled={pending}
          className={`rounded border px-2 py-1 text-sm transition ${
            isFav
              ? "border-h-accent bg-h-accent/10 text-h-accent"
              : "border-h-line text-h-muted hover:bg-h-bg"
          }`}
          title={isFav ? "Remove from favourites" : "Add to favourites"}
        >
          ★
        </button>

        <button
          type="button"
          onClick={onOpenInfo}
          className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg"
        >
          Info
        </button>

        <span className="ml-2 text-xs text-h-muted">PM</span>
        <span className="rounded border border-h-line bg-h-bg px-2 py-0.5 font-mono text-xs text-h-ink">
          {project.pm_name ?? "—"}
        </span>

        <span className="flex-1" />

        {procurementReady ? (
          <button
            type="button"
            onClick={onOpenProcurement}
            className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg"
          >
            🛒 Open Procurement
          </button>
        ) : null}

        <button
          type="button"
          disabled={!canEdit}
          className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg disabled:cursor-not-allowed disabled:opacity-50"
          title={canEdit ? "Edit item (open item editor)" : "Read-only role"}
        >
          Edit item
        </button>

        <button
          type="button"
          disabled={!canEdit}
          className="rounded bg-h-accent px-3 py-1 text-sm text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          title={canEdit ? "+ New item (needs API hookup)" : "Read-only role"}
        >
          + New item
        </button>
      </div>
    </div>
  );
}

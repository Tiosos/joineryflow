"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import type { ProjectOut } from "@/lib/pm-types";

interface ProjectSidebarProps {
  all: ProjectOut[];
  favourites: ProjectOut[];
}

export function ProjectSidebar({ all, favourites }: ProjectSidebarProps) {
  const [tab, setTab] = useState<"FAV" | "ALL">("ALL");
  const [query, setQuery] = useState("");
  const router = useRouter();
  const params = useSearchParams();
  const activePid = params.get("project_id");

  const projects = tab === "FAV" ? favourites : all;
  const filtered = query
    ? projects.filter(
        (p) =>
          p.name.toLowerCase().includes(query.toLowerCase()) ||
          p.project_code.toLowerCase().includes(query.toLowerCase()),
      )
    : projects;

  async function toggleFav(pid: number, on: boolean) {
    await fetch(`/api/projects/${pid}/favourites`, {
      method: on ? "POST" : "DELETE",
    });
    router.refresh();
  }

  return (
    <aside
      data-testid="project-sidebar"
      className="w-64 shrink-0 border-r border-h-line bg-h-surface min-h-screen"
    >
      {/* FAV / ALL toggle */}
      <div className="flex border-b border-h-line">
        {(["ALL", "FAV"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`flex-1 py-2 text-xs font-medium transition-colors ${
              tab === t
                ? "bg-h-accent text-white"
                : "text-h-muted hover:text-h-ink hover:bg-h-bg"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="p-2 border-b border-h-line">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search projects..."
          className="w-full px-2 py-1 text-sm bg-h-bg border border-h-line rounded text-h-ink placeholder:text-h-muted"
        />
      </div>

      {/* Project list */}
      <ul className="overflow-y-auto" role="list">
        {filtered.length === 0 ? (
          <li className="px-3 py-4 text-xs text-h-muted text-center">
            {tab === "FAV" ? "No favourites yet." : "No projects."}
          </li>
        ) : (
          filtered.map((p) => {
            const isActive = activePid === String(p.id);
            return (
              <li
                key={p.id}
                className={`flex items-center px-2 py-1.5 border-b border-h-line/50 ${
                  isActive ? "bg-h-accent/10" : "hover:bg-h-bg"
                }`}
              >
                <button
                  type="button"
                  onClick={() => toggleFav(p.id, !p.is_favourite)}
                  aria-label={p.is_favourite ? "Unfavourite" : "Favourite"}
                  className="px-1 text-h-accent shrink-0"
                >
                  {p.is_favourite ? "★" : "☆"}
                </button>
                <Link
                  href={`/tracking?project_id=${p.id}`}
                  className="flex-1 min-w-0 px-1 text-sm text-h-ink truncate"
                >
                  <span className="font-mono text-xs text-h-muted">
                    {p.project_code}
                  </span>
                  {" · "}
                  <span>{p.name}</span>
                </Link>
              </li>
            );
          })
        )}
      </ul>
    </aside>
  );
}

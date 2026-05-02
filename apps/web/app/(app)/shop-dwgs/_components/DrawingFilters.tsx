"use client";

import { useState } from "react";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

interface Props {
  projects: Project[];
  selectedProjectId: number | null;
  selectedRoom: string | null;
  searchValue: string;
  rooms: string[];
  onProjectChange: (id: number) => void;
  onRoomChange: (room: string | null) => void;
  onSearchChange: (q: string) => void;
}

export default function DrawingFilters(p: Props) {
  const [search, setSearch] = useState(p.searchValue);

  return (
    <div className="flex flex-wrap items-center gap-3 py-3">
      <input
        type="search"
        placeholder="Search title…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onBlur={() => p.onSearchChange(search)}
        onKeyDown={(e) => {
          if (e.key === "Enter") p.onSearchChange(search);
        }}
        className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink placeholder:text-h-muted"
      />
      <select
        value={p.selectedProjectId ?? ""}
        onChange={(e) => p.onProjectChange(Number(e.target.value))}
        className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
      >
        {p.projects.map((proj) => (
          <option key={proj.id} value={proj.id}>
            {proj.project_code} · {proj.name}
          </option>
        ))}
      </select>
      <select
        value={p.selectedRoom ?? ""}
        onChange={(e) => p.onRoomChange(e.target.value || null)}
        className="rounded-md border border-h-line bg-h-surface px-2.5 py-1.5 text-sm text-h-ink"
      >
        <option value="">All rooms</option>
        {p.rooms.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
    </div>
  );
}

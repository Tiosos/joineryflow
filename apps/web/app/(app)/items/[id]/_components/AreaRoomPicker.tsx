"use client";

import { useEffect, useState } from "react";

export interface RoomRow {
  room_id: number;
  area_id: number;
  rm_no: string;
  rm_desc: string | null;
  sort_order: number;
  item_count: number;
}

export interface AreaRow {
  area_id: number;
  project_id: number;
  name: string;
  sort_order: number;
  created_at: string;
  item_count: number;
  rooms: RoomRow[];
}

/**
 * Area and Room selectors, replacing the free-text Stage / Room # / Room
 * Description inputs (Plan V1 Q454/Q455, migration `0026`).
 *
 * Room is nested under Area (Q552), so the room list is always the chosen
 * area's — and changing area clears the room, because the old one belonged to
 * the area being left and the composite FK would refuse the pair.
 *
 * Both carry a "+ New…" option (Q457: areas are created per project), so a
 * drafter meeting a room that does not exist yet can add it without leaving
 * the item. The server writes the legacy `stage` / `rm_no` / `rm_desc` columns
 * alongside the FKs, so everything still reading those keeps working.
 */
export function AreaRoomPicker({
  projectId,
  areaId,
  roomId,
  canEdit,
  onChange,
}: {
  projectId: number;
  areaId: number | null;
  roomId: number | null;
  canEdit: boolean;
  onChange: (next: { area_id?: number; room_id?: number }) => Promise<boolean>;
}) {
  const [areas, setAreas] = useState<AreaRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const r = await fetch(`/api/projects/${projectId}/areas`, { cache: "no-store" });
    if (r.ok) setAreas((await r.json()).areas ?? []);
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const area = areas.find((a) => a.area_id === areaId) ?? null;
  const rooms = area?.rooms ?? [];

  async function pickArea(value: string) {
    setError(null);
    if (value === "__new__") {
      const name = window.prompt("New area name (e.g. Joinery Lab, Block B)");
      if (!name?.trim()) return;
      setBusy(true);
      try {
        const r = await fetch(`/api/projects/${projectId}/areas`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name: name.trim() }),
        });
        const body = await r.json().catch(() => null);
        // 409 AREA_EXISTS hands back the id, so a racing duplicate just selects it.
        const newId = r.ok ? body?.area_id : body?.detail?.area_id;
        if (newId == null) {
          setError(`Could not create the area (${r.status})`);
          return;
        }
        await load();
        await onChange({ area_id: newId });
      } finally {
        setBusy(false);
      }
      return;
    }
    if (value === "") return;
    setBusy(true);
    try {
      await onChange({ area_id: Number(value) });
    } finally {
      setBusy(false);
    }
  }

  async function pickRoom(value: string) {
    setError(null);
    if (area == null) return;
    if (value === "__new__") {
      const rmNo = window.prompt("New room number (e.g. 057)");
      if (!rmNo?.trim()) return;
      const rmDesc = window.prompt("Room description (optional)") ?? "";
      setBusy(true);
      try {
        const r = await fetch(`/api/areas/${area.area_id}/rooms`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            rm_no: rmNo.trim(),
            rm_desc: rmDesc.trim() || null,
          }),
        });
        const body = await r.json().catch(() => null);
        const newId = r.ok ? body?.room_id : body?.detail?.room_id;
        if (newId == null) {
          setError(`Could not create the room (${r.status})`);
          return;
        }
        await load();
        await onChange({ room_id: newId });
      } finally {
        setBusy(false);
      }
      return;
    }
    if (value === "") return;
    setBusy(true);
    try {
      await onChange({ room_id: Number(value) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-3">
      <label className="block">
        <span className="mb-1 block text-xs font-medium uppercase text-h-muted">
          Area
        </span>
        <select
          value={areaId ?? ""}
          disabled={!canEdit || busy}
          onChange={(e) => pickArea(e.target.value)}
          className={selectCls}
        >
          <option value="">— not set —</option>
          {areas.map((a) => (
            <option key={a.area_id} value={a.area_id}>
              {a.name}
            </option>
          ))}
          {canEdit && <option value="__new__">+ New area…</option>}
        </select>
      </label>

      <label className="block">
        <span className="mb-1 block text-xs font-medium uppercase text-h-muted">
          Room
        </span>
        <select
          value={roomId ?? ""}
          disabled={!canEdit || busy || area == null}
          onChange={(e) => pickRoom(e.target.value)}
          className={selectCls}
          title={area == null ? "Choose an area first — rooms belong to one" : undefined}
        >
          <option value="">— not set —</option>
          {rooms.map((r) => (
            <option key={r.room_id} value={r.room_id}>
              {r.rm_no}
              {r.rm_desc ? ` · ${r.rm_desc}` : ""}
            </option>
          ))}
          {canEdit && area != null && <option value="__new__">+ New room…</option>}
        </select>
      </label>

      {error && <span className="text-xs text-[#b4443d]">{error}</span>}
    </div>
  );
}

const selectCls =
  "w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent disabled:opacity-50";

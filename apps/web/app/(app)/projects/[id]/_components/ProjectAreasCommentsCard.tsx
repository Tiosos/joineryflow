"use client";

import { useCallback, useEffect, useState } from "react";

import { CommentThread } from "@/components/comments/CommentThread";
import { commentsApi } from "@/lib/comments-fetch";
import type { AreaWithRooms, CommentCounts } from "@/lib/comments-types";

type Selection = { type: "area" | "room"; id: number };

function CountBadge({ n }: { n: number }) {
  if (!n) return null;
  return (
    <span
      data-testid="comment-badge"
      className="rounded-full bg-h-accent-soft px-1.5 text-[10px] font-semibold text-h-ink"
      title={`${n} comment${n === 1 ? "" : "s"}`}
    >
      💬 {n}
    </span>
  );
}

/** The Areas & Rooms card on `/projects/[id]` (Plan V1 §29): a project's areas
 *  with their rooms, each with its comment count, and the selected one's
 *  thread beside it. Area and Room have no page of their own, so this is where
 *  their threads live; the selection is kept in the URL (`?area=` / `?room=`),
 *  which is what a notification for one deep-links to. */
export function ProjectAreasCommentsCard({
  projectId,
  currentUserId,
  currentUserRole,
  canComment,
  initialSelection,
}: {
  projectId: number;
  currentUserId: number | null;
  currentUserRole: string | null;
  canComment: boolean;
  initialSelection: Selection | null;
}) {
  const [areas, setAreas] = useState<AreaWithRooms[] | null>(null);
  const [counts, setCounts] = useState<CommentCounts>({ areas: {}, rooms: {} });
  const [selected, setSelected] = useState<Selection | null>(initialSelection);
  const [error, setError] = useState<string | null>(null);

  const loadCounts = useCallback(async () => {
    try {
      setCounts(await commentsApi.counts(projectId));
    } catch {
      // Counts are decoration: a failed refresh keeps the last known ones.
    }
  }, [projectId]);

  useEffect(() => {
    commentsApi
      .areas(projectId)
      .then((a) => {
        setAreas(a);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load areas"));
    void loadCounts();
  }, [projectId, loadCounts]);

  function select(s: Selection) {
    setSelected(s);
    // Keep the URL shareable without re-running the whole server page.
    window.history.replaceState(null, "", `?${s.type}=${s.id}`);
  }

  const area =
    selected?.type === "area" ? areas?.find((a) => a.area_id === selected.id) : undefined;
  const roomParent =
    selected?.type === "room"
      ? areas?.find((a) => a.rooms.some((r) => r.room_id === selected.id))
      : undefined;
  const room = roomParent?.rooms.find((r) => r.room_id === selected?.id);
  const stale = !!areas && !!selected && !area && !room;

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4" data-testid="areas-card">
      <h2 className="mb-3 text-sm font-semibold text-h-ink">Areas &amp; Rooms</h2>

      {error && <p className="text-sm text-red-800">{error}</p>}
      {!areas && !error && <p className="text-sm text-h-muted">Loading…</p>}
      {areas && areas.length === 0 && (
        <p className="text-sm text-h-muted">
          No areas yet — they are created from an item&apos;s Area picker.
        </p>
      )}

      {areas && areas.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <ul className="grid content-start gap-1" data-testid="areas-list">
            {areas.map((a) => (
              <li key={a.area_id}>
                <button
                  type="button"
                  data-testid={`area-row-${a.area_id}`}
                  aria-current={selected?.type === "area" && selected.id === a.area_id}
                  onClick={() => select({ type: "area", id: a.area_id })}
                  className={[
                    "flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-sm",
                    selected?.type === "area" && selected.id === a.area_id
                      ? "bg-h-accent-soft font-medium text-h-ink"
                      : "text-h-ink hover:bg-h-bg",
                  ].join(" ")}
                >
                  <span>
                    {a.name}{" "}
                    <span className="text-xs text-h-muted">
                      · {a.item_count} item{a.item_count === 1 ? "" : "s"}
                    </span>
                  </span>
                  <CountBadge n={counts.areas[a.area_id] ?? 0} />
                </button>
                {a.rooms.length > 0 && (
                  <ul className="ml-4 grid gap-1 border-l border-h-line pl-2">
                    {a.rooms.map((r) => (
                      <li key={r.room_id}>
                        <button
                          type="button"
                          data-testid={`room-row-${r.room_id}`}
                          aria-current={selected?.type === "room" && selected.id === r.room_id}
                          onClick={() => select({ type: "room", id: r.room_id })}
                          className={[
                            "flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-sm",
                            selected?.type === "room" && selected.id === r.room_id
                              ? "bg-h-accent-soft font-medium text-h-ink"
                              : "text-h-ink hover:bg-h-bg",
                          ].join(" ")}
                        >
                          <span>
                            {r.rm_no}
                            {r.rm_desc && <span className="text-xs text-h-muted"> {r.rm_desc}</span>}
                          </span>
                          <CountBadge n={counts.rooms[r.room_id] ?? 0} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>

          <div className="min-w-0">
            {!selected && (
              <p className="text-sm text-h-muted">Select an area or room to see its comments.</p>
            )}
            {stale && (
              <p className="text-sm text-h-muted">
                That area or room no longer exists. Pick one from the list.
              </p>
            )}
            {selected && (area || room) && (
              <div className="grid gap-3">
                <h3 className="text-sm font-medium text-h-ink" data-testid="thread-heading">
                  {area
                    ? `Area · ${area.name}`
                    : `Room · ${room!.rm_no}${room!.rm_desc ? ` ${room!.rm_desc}` : ""} (in ${roomParent!.name})`}
                </h3>
                <CommentThread
                  key={`${selected.type}-${selected.id}`}
                  objectType={selected.type}
                  objectId={selected.id}
                  currentUserId={currentUserId}
                  currentUserRole={currentUserRole}
                  canComment={canComment}
                  onMutated={loadCounts}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

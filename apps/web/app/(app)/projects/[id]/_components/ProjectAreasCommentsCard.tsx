"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { CommentThread } from "@/components/comments/CommentThread";
import { commentsApi } from "@/lib/comments-fetch";
import type { CommentCounts, Mentionable } from "@/lib/comments-types";
import type { AreaRow } from "../../../items/[id]/_components/AreaRoomPicker";

type Selection = { type: "area" | "room"; id: number };

/** `?room=<id>` wins over `?area=<id>`; anything that is not a positive integer
 *  is ignored. The URL is the only place the selection lives. */
function selectionFrom(params: URLSearchParams): Selection | null {
  for (const type of ["room", "area"] as const) {
    const raw = params.get(type);
    const id = Number(raw);
    if (raw && Number.isInteger(id) && id > 0) return { type, id };
  }
  return null;
}

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
 *  their threads live.
 *
 *  The selection lives in the URL (`?area=` / `?room=`) so it can be linked to,
 *  and a notification for an Area or Room comment links straight to it — also
 *  when followed while already on this page. A click sets local state and the
 *  URL together, synchronously (`history.replaceState`, which Next integrates
 *  with `useSearchParams`): a server round trip (`router.replace`) would leave
 *  the previous thread's input on screen until it landed, typed into and then
 *  thrown away, and two quick clicks would race their landings. A URL change
 *  that did not come from a click is synced back into state. */
export function ProjectAreasCommentsCard({
  projectId,
  currentUserId,
  currentUserRole,
  canComment,
}: {
  projectId: number;
  currentUserId: number | null;
  currentUserRole: string | null;
  canComment: boolean;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlSelection = selectionFrom(searchParams);
  const urlKey = urlSelection ? `${urlSelection.type}-${urlSelection.id}` : "";

  const cardRef = useRef<HTMLElement>(null);
  const ownClick = useRef(false);
  const [selected, setSelected] = useState<Selection | null>(urlSelection);
  const [areas, setAreas] = useState<AreaRow[] | null>(null);
  const [counts, setCounts] = useState<CommentCounts>({ areas: {}, rooms: {} });
  const [roster, setRoster] = useState<Mentionable[] | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const refetchedFor = useRef<Set<string>>(new Set());

  // Two quick posts fire two refreshes; only the latest request may write, so a
  // slow earlier one cannot put an older, lower count back.
  const countsSeq = useRef(0);
  const loadCounts = useCallback(async () => {
    const mine = ++countsSeq.current;
    try {
      const c = await commentsApi.counts(projectId);
      if (mine === countsSeq.current) setCounts(c);
    } catch {
      // Counts are decoration: a failed refresh keeps the last known ones.
    }
  }, [projectId]);

  const loadAreas = useCallback(() => {
    return fetch(`/api/projects/${projectId}/areas`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`Failed to load areas (${r.status})`);
        setAreas((await r.json()).areas ?? []);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load areas"));
  }, [projectId]);

  useEffect(() => {
    void loadAreas();
    void loadCounts();
  }, [loadAreas, loadCounts]);

  // Fetched once for the card, not once per thread (each row click remounts the
  // thread). Until it arrives the thread fetches its own, so nothing waits on it.
  useEffect(() => {
    commentsApi.mentionable().then(setRoster).catch(() => setRoster([]));
  }, []);

  // The URL changed (a notification link, back/forward, a shared URL): follow it.
  // After our own click this just re-sets what is already selected.
  useEffect(() => {
    setSelected(urlSelection);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the URL's selection
  }, [urlKey]);

  // A link that selects something can land with the card below the fold, since
  // it is the last card on the page — bring it into view. A click on a row is
  // already in view and must not scroll.
  const loaded = areas !== null;
  useEffect(() => {
    if (!urlKey || !loaded) return;
    if (ownClick.current) {
      ownClick.current = false;
      return;
    }
    cardRef.current?.scrollIntoView({ block: "start" });
  }, [urlKey, loaded]);

  function select(s: Selection) {
    setSelected(s);
    // Only flag it as ours when the URL really changes (it does, synchronously,
    // just below); otherwise the flag would linger and swallow the next genuine
    // deep link's scroll.
    ownClick.current = urlKey !== `${s.type}-${s.id}`;
    const next = new URLSearchParams(searchParams.toString());
    next.delete("area");
    next.delete("room");
    next.set(s.type, String(s.id));
    window.history.replaceState(null, "", `${pathname}?${next}`);
  }

  const area =
    selected?.type === "area" ? areas?.find((a) => a.area_id === selected.id) : undefined;
  const roomParent =
    selected?.type === "room"
      ? areas?.find((a) => a.rooms.some((r) => r.room_id === selected.id))
      : undefined;
  const room = roomParent?.rooms.find((r) => r.room_id === selected?.id);
  const selectedKey = selected ? `${selected.type}-${selected.id}` : "";
  const stale = !!areas && !!selected && !area && !room;

  // A link can name an area or room created after this page loaded (a colleague
  // added it and mentioned us). Look once before calling it deleted.
  useEffect(() => {
    if (!stale || !selectedKey || refetchedFor.current.has(selectedKey)) return;
    refetchedFor.current.add(selectedKey);
    void loadAreas();
    void loadCounts();
  }, [stale, selectedKey, loadAreas, loadCounts]);

  return (
    <section
      ref={cardRef}
      className="rounded-lg border border-h-line bg-h-surface p-4"
      data-testid="areas-card"
    >
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
                  roster={roster}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

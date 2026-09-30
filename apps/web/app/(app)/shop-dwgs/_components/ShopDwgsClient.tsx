"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { commentsApi } from "@/lib/comments-fetch";
import type { Mentionable } from "@/lib/comments-types";
import { can } from "@/lib/permissions";
import { listDrawings } from "@/lib/shop-drawings-fetch";
import type { DrawingList, Queue } from "@/lib/shop-drawings-types";
import type { Me } from "@/lib/session";

import DetailsPanel from "./DetailsPanel";
import DrawingFilters from "./DrawingFilters";
import DrawingViewer from "./DrawingViewer";
import QueueRail from "./QueueRail";
import RegisterTable from "./RegisterTable";
import UploadDialog from "./UploadDialog";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

interface Props {
  me: Me;
  projects: Project[];
  initialProjectId: number | null;
  initialQueue: Queue;
  initialMine: boolean;
  initialRoom: string | null;
  initialQ: string | null;
  initialDrawingId: number | null;
  initialRevId: number | null;
  initialViewer: boolean;
}

const EMPTY_QUEUES = {
  being_drawn: 0, internal_review: 0, update_required: 0, completed: 0,
  awaiting_submission: 0, submitted: 0, archive: 0,
};

export default function ShopDwgsClient(props: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const [list, setList] = useState<DrawingList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [roster, setRoster] = useState<Mentionable[]>([]);

  const projectId = props.initialProjectId;
  const queue = props.initialQueue;
  const mine = props.initialMine;
  const room = props.initialRoom;
  const q = props.initialQ;
  const canUpload = can(props.me, "shop_dwgs", "write");

  // One roster for the assignee pickers and every comment thread on the page.
  // Kept in component state, not a module cache, so it can't outlive a logout.
  useEffect(() => {
    commentsApi.mentionable().then(setRoster).catch(() => setRoster([]));
  }, []);

  // Only the newest request may write: a slow answer for an earlier filter must
  // not overwrite the list for the one on screen.
  const load = useCallback((live: { on: boolean }, quiet = false) => {
    if (projectId == null) { setList(null); return; }
    if (!quiet) setLoading(true);
    setError(null);
    listDrawings({ projectId, queue, room, q, assignedTo: mine ? props.me.id : null })
      .then((l) => { if (live.on) setList(l); })
      .catch((e: unknown) => { if (live.on) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (live.on) setLoading(false); });
  }, [projectId, queue, room, q, mine, props.me.id]);

  useEffect(() => {
    const live = { on: true };
    load(live);
    return () => { live.on = false; };
  }, [load]);

  // After an edit / review action: refetch without flashing "Loading…".
  const refreshList = useCallback(() => { load({ on: true }, true); }, [load]);

  const updateUrl = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(sp?.toString() ?? "");
      for (const [k, v] of Object.entries(patch)) {
        if (v == null || v === "") next.delete(k);
        else next.set(k, v);
      }
      router.replace(`/shop-dwgs?${next.toString()}`);
    },
    [router, sp]
  );

  const rooms = useMemo(() => {
    const set = new Set<string>();
    for (const d of list?.drawings ?? []) if (d.room) set.add(d.room);
    return Array.from(set).sort();
  }, [list]);

  const counts = list?.queues ?? EMPTY_QUEUES;
  const total = list?.total ?? 0;
  const headerText = projectId
    ? `${total} drawings across ${list?.distinct_rooms ?? 0} rooms · ${list?.awaiting_review ?? 0} awaiting review`
    : "Pick a project to view drawings.";

  const drawingId = props.initialDrawingId;

  return (
    // `w-0 min-w-full`: the chrome's <main> is a flex child without min-w-0, so the
    // register's wide table would otherwise stretch the whole page instead of
    // scrolling inside its own wrapper. This gives the section no intrinsic
    // width of its own while still filling whatever <main> is given.
    <section className="w-0 min-w-full space-y-2">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-h-ink">Shop Drawings</h1>
          <p className="mt-1 text-sm text-h-muted">{headerText}</p>
        </div>
        {projectId != null && canUpload && (
          <button onClick={() => setUploadOpen(true)}
                  className="rounded bg-h-accent px-3 py-1.5 text-sm text-white">
            Upload drawing
          </button>
        )}
      </header>

      <DrawingFilters
        projects={props.projects}
        selectedProjectId={projectId}
        selectedRoom={room}
        searchValue={q ?? ""}
        rooms={rooms}
        onProjectChange={(id) =>
          updateUrl({ project: String(id), drawing: null, rev: null, viewer: null, room: null, queue: null })
        }
        onRoomChange={(r) => updateUrl({ room: r })}
        onSearchChange={(s) => updateUrl({ q: s || null })}
      />

      {error && <p className="text-sm text-h-bad">{error}</p>}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <QueueRail
          queue={queue}
          counts={counts}
          total={total}
          mine={mine}
          onQueue={(next) => updateUrl({ queue: next === "all" ? null : next, drawing: null, rev: null, viewer: null })}
          onMine={(on) => updateUrl({ mine: on ? "1" : null })}
        />

        <div className="flex min-w-0 flex-1 flex-col gap-4 xl:flex-row xl:items-start">
          <div className="min-w-0 flex-1">
            {loading && !list && <p className="text-sm text-h-muted">Loading…</p>}
            {list && (
              <RegisterTable
                drawings={list.drawings}
                selectedId={drawingId}
                onSelect={(id) => updateUrl({ drawing: String(id), rev: null, viewer: null, comments: null })}
                onView={(id) => updateUrl({ drawing: String(id), rev: null, viewer: "1", comments: null })}
              />
            )}
          </div>

          {drawingId != null && !props.initialViewer && (
            <DetailsPanel
              drawingId={drawingId}
              initialRevId={props.initialRevId}
              commentsOpen={sp?.get("comments") === "1"}
              me={props.me}
              roster={roster}
              onClose={() => updateUrl({ drawing: null, rev: null, comments: null, viewer: null })}
              onChanged={refreshList}
              onSelectRevision={(rev) => updateUrl({ rev: String(rev) })}
              onView={(rev) => updateUrl({ rev: String(rev), viewer: "1" })}
            />
          )}
        </div>
      </div>

      {drawingId != null && props.initialViewer && (
        <DrawingViewer
          drawingId={drawingId}
          initialRevId={props.initialRevId}
          me={props.me}
          roster={roster}
          onClose={() => updateUrl({ viewer: null })}
          onChanged={refreshList}
          onSelectRevision={(rev) => updateUrl({ rev: String(rev) })}
        />
      )}

      {uploadOpen && projectId != null && (
        <UploadDialog
          projectId={projectId}
          roster={roster}
          onClose={() => setUploadOpen(false)}
          onCreated={(id) => {
            setUploadOpen(false);
            // Land on the register queue the new drawing belongs to, with its details open.
            updateUrl({ drawing: String(id), rev: null, viewer: null, queue: null });
            refreshList();
          }}
        />
      )}
    </section>
  );
}

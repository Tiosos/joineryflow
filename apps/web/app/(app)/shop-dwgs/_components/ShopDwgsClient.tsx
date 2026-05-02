"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { DrawingList, Subtab } from "@/lib/shop-drawings-types";
import { listDrawings } from "@/lib/shop-drawings-fetch";
import type { Me } from "@/lib/session";

import DrawingCard from "./DrawingCard";
import DrawingDrawer from "./DrawingDrawer";
import DrawingFilters from "./DrawingFilters";
import ReviewActions from "./ReviewActions";
import SubtabStrip from "./SubtabStrip";
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
  initialSubtab: Subtab;
  initialRoom: string | null;
  initialQ: string | null;
  initialDrawingId: number | null;
  initialRevId: number | null;
}

export default function ShopDwgsClient(props: Props) {
  const router = useRouter();
  const sp = useSearchParams();

  const [list, setList] = useState<DrawingList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const projectId = props.initialProjectId;
  const subtab = props.initialSubtab;
  const room = props.initialRoom;
  const q = props.initialQ;

  useEffect(() => {
    if (projectId == null) {
      setList(null);
      return;
    }
    setLoading(true);
    setError(null);
    listDrawings({ projectId, subtab, room, q })
      .then(setList)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e))
      )
      .finally(() => setLoading(false));
  }, [projectId, subtab, room, q]);

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

  const headerCounts = list ?? {
    total: 0,
    awaiting_review: 0,
    distinct_rooms: 0,
    drawings: [],
  };
  const headerText = projectId
    ? `${headerCounts.total} drawings across ${headerCounts.distinct_rooms} rooms · ${headerCounts.awaiting_review} awaiting review`
    : "Pick a project to view drawings.";

  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-h-ink">Shop Drawings</h1>
          <p className="mt-1 text-sm text-h-muted">{headerText}</p>
        </div>
        {projectId != null && (
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
          updateUrl({ project: String(id), drawing: null, rev: null, room: null })
        }
        onRoomChange={(r) => updateUrl({ room: r })}
        onSearchChange={(s) => updateUrl({ q: s || null })}
      />

      <SubtabStrip
        current={subtab}
        onChange={(s) => updateUrl({ subtab: s, drawing: null, rev: null })}
        counts={{
          total: headerCounts.total,
          awaiting_review: headerCounts.awaiting_review,
        }}
      />

      {loading && <p className="text-sm text-h-muted">Loading…</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {list && list.drawings.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.drawings.map((d) => (
            <DrawingCard
              key={d.drawing_id}
              card={d}
              onClick={() => updateUrl({ drawing: String(d.drawing_id), rev: null })}
            />
          ))}
        </div>
      )}
      {list && list.drawings.length === 0 && (
        <p className="py-12 text-center text-sm text-h-muted">
          No drawings here yet.
        </p>
      )}

      {props.initialDrawingId != null && (
        <DrawingDrawer
          drawingId={props.initialDrawingId}
          initialRevId={props.initialRevId}
          me={props.me}
          onClose={() => updateUrl({ drawing: null, rev: null })}
          onChanged={() => {
            if (projectId != null) {
              listDrawings({ projectId, subtab, room, q })
                .then(setList)
                .catch((e: unknown) =>
                  setError(e instanceof Error ? e.message : String(e))
                );
            }
          }}
          onSelectRevision={(rev) => updateUrl({ rev: String(rev) })}
          renderActions={(detail, selectedRevId, refresh) => {
            const rev = detail.revisions.find((r) => r.revision_id === selectedRevId);
            if (!rev) return null;
            return <ReviewActions detail={detail} selectedRev={rev} me={props.me} onAfter={refresh} />;
          }}
        />
      )}

      {uploadOpen && projectId != null && (
        <UploadDialog
          projectId={projectId}
          onClose={() => setUploadOpen(false)}
          onCreated={(drawingId) => {
            setUploadOpen(false);
            updateUrl({ drawing: String(drawingId), rev: null, subtab: "in_review" });
          }}
        />
      )}
    </section>
  );
}

"use client";

import { useEffect, useState } from "react";

import {
  completeAssignment,
  fetchRecentCompletions,
  fetchWorkerQueue,
  startAssignment,
  undoCompletion,
} from "@/lib/shop-floor-fetch";
import type {
  RecentCompletionOut,
  StationCard as StationCardOut,
  StationOut,
} from "@/lib/shop-floor-types";

interface MeShape {
  id: number;
  auth_role: string;
}

interface Props {
  me: MeShape;
  workerId: number;
}

const POLL_MS = 15_000;
const UNDO_WINDOW_MS = 5 * 60 * 1000;


export function StationClient({ me, workerId }: Props) {
  const [station, setStation] = useState<StationOut | null>(null);
  const [recent, setRecent] = useState<RecentCompletionOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [markDoneTarget, setMarkDoneTarget] = useState<StationCardOut | null>(null);

  const isAssignedWorker = me.id === workerId;

  async function refresh() {
    try {
      setError(null);
      const [s, r] = await Promise.all([
        fetchWorkerQueue(workerId),
        fetchRecentCompletions(workerId),
      ]);
      setStation(s);
      setRecent(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    void refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workerId]);

  async function start(card: StationCardOut) {
    try {
      await startAssignment(card.assignment_id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function undo(c: RecentCompletionOut) {
    try {
      await undoCompletion(c.log_id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-12 text-center text-h-muted">
        Loading station…
      </div>
    );
  }
  if (!station) {
    return (
      <div className="rounded-lg border border-h-line bg-h-surface p-12 text-center text-h-muted">
        {error ?? "Station unavailable."}
      </div>
    );
  }

  const cards = station.cards;
  const active = cards[0];
  const upcoming = cards.slice(1);

  return (
    <div className="grid gap-4">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-medium text-h-ink">
            {station.worker_name}
          </h1>
          <div className="font-mono text-xs uppercase text-h-muted">
            shop-floor station
          </div>
        </div>
        <div className="font-mono text-sm text-h-muted">
          {new Date().toLocaleString()}
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-red-500 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {recent.length > 0 && isAssignedWorker && (
        <UndoBannerStack rows={recent} onUndo={undo} />
      )}

      {!active ? (
        <div className="rounded-lg border border-h-line bg-h-surface p-12 text-center text-h-muted">
          Nothing assigned. Ask your foreman.
        </div>
      ) : (
        <section className="rounded-2xl border border-h-line bg-h-surface p-6">
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="rounded-full bg-h-accent px-3 py-1 text-sm font-medium uppercase tracking-wide text-h-bg">
              {active.stage_key}
            </span>
            <span className="font-mono text-sm text-h-muted">
              {active.project_code} · #{active.item_number}
            </span>
            {active.code && (
              <span className="font-mono text-sm text-h-ink">{active.code}</span>
            )}
          </div>
          <div className="mt-3 text-3xl font-medium leading-tight text-h-ink">
            {active.description ?? "—"}
          </div>
          {(active.room_no || active.room_desc) && (
            <div className="mt-1 text-sm text-h-muted">
              {active.room_no} · {active.room_desc}
            </div>
          )}
          {active.note && (
            <div className="mt-3 rounded border border-h-line bg-h-bg p-3 text-sm text-h-ink">
              {active.note}
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-3">
            {active.status === "assigned" && (
              <button
                type="button"
                onClick={() => start(active)}
                className="rounded-lg border border-h-accent bg-h-accent px-6 py-3 text-base font-medium text-h-bg hover:opacity-90"
              >
                Start {active.stage_key}
              </button>
            )}
            {active.status === "in_progress" && (
              <button
                type="button"
                onClick={() => setMarkDoneTarget(active)}
                className="rounded-lg border-2 border-emerald-600 bg-emerald-600 px-8 py-4 text-lg font-semibold uppercase tracking-wide text-white hover:opacity-90"
              >
                Mark {active.stage_key} done
              </button>
            )}
          </div>
        </section>
      )}

      {upcoming.length > 0 && (
        <section className="rounded-lg border border-h-line bg-h-surface p-3">
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-h-muted">
            Upcoming · {upcoming.length}
          </h2>
          <ol className="flex flex-col gap-2">
            {upcoming.map((card) => (
              <li
                key={card.assignment_id}
                className="flex flex-wrap items-baseline gap-2 rounded border border-h-line bg-h-bg p-2"
              >
                <span className="rounded-full border border-h-line px-2 py-0.5 text-xs uppercase tracking-wide text-h-muted">
                  {card.stage_key}
                </span>
                <span className="font-mono text-xs text-h-muted">
                  {card.project_code} · #{card.item_number}
                </span>
                <span className="text-sm text-h-ink">
                  {card.description ?? "—"}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {markDoneTarget && (
        <MarkDoneDialog
          card={markDoneTarget}
          onClose={() => setMarkDoneTarget(null)}
          onCompleted={async () => {
            setMarkDoneTarget(null);
            await refresh();
          }}
        />
      )}
    </div>
  );
}


function UndoBannerStack({
  rows,
  onUndo,
}: {
  rows: RecentCompletionOut[];
  onUndo: (row: RecentCompletionOut) => void | Promise<void>;
}) {
  const now = Date.now();
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => {
        const completed = new Date(r.completed_at).getTime();
        const remainingMs = Math.max(0, UNDO_WINDOW_MS - (now - completed));
        const mins = Math.ceil(remainingMs / 60_000);
        return (
          <div
            key={r.log_id}
            className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-500 bg-amber-50 p-3 text-sm text-amber-900"
          >
            <span className="font-medium">
              {r.stage_key} done on item #{r.item_number}
            </span>
            <span className="text-xs">
              · {mins} min{mins === 1 ? "" : "s"} left to undo
            </span>
            <button
              type="button"
              onClick={() => onUndo(r)}
              className="ml-auto rounded border border-amber-700 px-3 py-1 text-xs text-amber-900 hover:bg-amber-100"
            >
              Undo
            </button>
          </div>
        );
      })}
    </div>
  );
}


function MarkDoneDialog({
  card,
  onClose,
  onCompleted,
}: {
  card: StationCardOut;
  onClose: () => void;
  onCompleted: () => void | Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await completeAssignment(card.assignment_id, {
        note: note || null,
      });
      await onCompleted();
    } catch (e) {
      const err = e as Error & { detail?: { code?: string; missing?: string[] } };
      if (err.detail?.code === "STAGE_OUT_OF_ORDER") {
        setError(
          `Stage out of order — finish first: ${(err.detail.missing ?? []).join(", ")}`,
        );
      } else {
        setError(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Mark stage done"
        className="w-full max-w-xl rounded-2xl border border-h-line bg-h-bg p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-2xl font-semibold text-h-ink">
          Mark {card.stage_key} done?
        </h2>
        <p className="mt-1 text-sm text-h-muted">
          Item #{card.item_number} · {card.description ?? "—"}
        </p>

        <label className="mt-4 block text-sm text-h-muted">
          Note (optional)
        </label>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          className="mt-1 w-full rounded border border-h-line bg-h-surface px-3 py-2 text-base text-h-ink"
          autoFocus
        />

        {error && (
          <div className="mt-3 rounded border border-red-500 bg-red-50 p-3 text-sm text-red-900">
            {error}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-h-line px-5 py-3 text-base text-h-ink hover:bg-h-surface"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={submit}
            className="rounded-lg border-2 border-emerald-600 bg-emerald-600 px-6 py-3 text-base font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Marking…" : "Confirm done"}
          </button>
        </div>
      </div>
    </div>
  );
}

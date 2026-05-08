"use client";

import { useEffect, useState } from "react";

import {
  cancelAssignment,
  createAssignment,
  fetchBoard,
  fetchProjectWorkers,
  patchAssignment,
} from "@/lib/shop-floor-fetch";
import type {
  AssignmentOut,
  BoardCard,
  BoardOut,
  ShopFloorStage,
  WorkerOut,
} from "@/lib/shop-floor-types";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

interface MeShape {
  id: number;
  auth_role: string;
}

interface Props {
  me: MeShape;
  projects: Project[];
  initialProjectId: number | null;
}

const STAGE_ORDER: ShopFloorStage[] = ["DOWN", "CNC", "EDGED", "PAINTED", "MADE"];
const STAGE_LABEL: Record<ShopFloorStage, string> = {
  DOWN: "Marked Down",
  CNC: "CNC Cut",
  EDGED: "Edge Banded",
  PAINTED: "Painted",
  MADE: "Assembled",
};

const POLL_MS = 15_000;

function canMutate(role: string): boolean {
  return ["admin", "manager", "editor", "drafter"].includes(role);
}

function statusPill(status: string | undefined): string {
  if (!status) return "bg-h-line text-h-ink";
  if (status === "in_progress") return "bg-h-accent text-h-bg";
  if (status === "assigned") return "bg-h-line text-h-ink";
  return "bg-h-surface text-h-muted";
}

export function ShopFloorClient({ me, projects, initialProjectId }: Props) {
  const [projectId, setProjectId] = useState<number | null>(initialProjectId);
  const [board, setBoard] = useState<BoardOut | null>(null);
  const [workers, setWorkers] = useState<WorkerOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [assignTarget, setAssignTarget] = useState<BoardCard | null>(null);

  const mutator = canMutate(me.auth_role);

  async function refresh() {
    if (projectId === null) {
      setBoard(null);
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const [b, w] = await Promise.all([
        fetchBoard(projectId),
        fetchProjectWorkers(projectId),
      ]);
      setBoard(b);
      setWorkers(w);
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
  }, [projectId]);

  async function reassign(a: AssignmentOut, newWorkerId: number) {
    try {
      await patchAssignment(a.assignment_id, { worker_id: newWorkerId });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function cancel(a: AssignmentOut) {
    if (!confirm("Cancel this assignment?")) return;
    try {
      await cancelAssignment(a.assignment_id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="grid gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-medium text-h-ink">Shop Floor</h1>
        <span className="font-mono text-xs uppercase text-h-muted">
          foreman office board
        </span>
        <select
          value={projectId ?? ""}
          onChange={(e) =>
            setProjectId(e.target.value ? Number(e.target.value) : null)
          }
          className="ml-auto rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.project_code} — {p.name}
            </option>
          ))}
        </select>
      </header>

      {error && (
        <div className="rounded-lg border border-red-500 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
          Loading board…
        </div>
      ) : board === null ? (
        <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
          Pick a project to view its shop-floor board.
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-5">
          {STAGE_ORDER.map((stage) => {
            const cards = board.columns[stage] ?? [];
            return (
              <section
                key={stage}
                className="rounded-lg border border-h-line bg-h-surface p-3"
              >
                <header className="mb-2 flex items-baseline justify-between">
                  <div className="text-sm font-medium text-h-ink">
                    {STAGE_LABEL[stage]}
                  </div>
                  <span className="font-mono text-xs text-h-muted">
                    {cards.length}
                  </span>
                </header>

                <ol className="flex flex-col gap-2">
                  {cards.map((card) => (
                    <li
                      key={card.item_id}
                      className="rounded border border-h-line bg-h-bg p-2"
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-mono text-xs text-h-muted">
                          #{card.item_number}
                        </span>
                        {card.code && (
                          <span className="font-mono text-xs text-h-ink">
                            {card.code}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-sm text-h-ink line-clamp-2">
                        {card.description ?? "—"}
                      </div>

                      {card.assignment ? (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span
                            className={[
                              "rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide",
                              statusPill(card.assignment.status),
                            ].join(" ")}
                          >
                            {card.assignment.status}
                          </span>
                          <span className="text-xs text-h-muted">
                            {card.assignment.worker_name ??
                              `worker #${card.assignment.worker_id}`}
                          </span>
                          {mutator && (
                            <div className="ml-auto flex gap-1">
                              <select
                                value={card.assignment.worker_id}
                                onChange={(e) =>
                                  reassign(
                                    card.assignment!,
                                    Number(e.target.value),
                                  )
                                }
                                className="rounded border border-h-line bg-h-surface px-1 py-0.5 text-[11px] text-h-ink"
                                aria-label="Reassign"
                              >
                                {workers.map((w) => (
                                  <option key={w.id} value={w.id}>
                                    {w.full_name}
                                  </option>
                                ))}
                              </select>
                              <button
                                type="button"
                                onClick={() => cancel(card.assignment!)}
                                className="rounded border border-h-line px-1 text-[11px] text-h-muted hover:text-h-ink"
                                aria-label="Cancel"
                              >
                                ×
                              </button>
                            </div>
                          )}
                        </div>
                      ) : (
                        mutator && (
                          <button
                            type="button"
                            onClick={() => setAssignTarget(card)}
                            className="mt-2 w-full rounded border border-dashed border-h-line px-2 py-1 text-xs text-h-muted hover:bg-h-surface hover:text-h-ink"
                          >
                            + Assign worker
                          </button>
                        )
                      )}
                    </li>
                  ))}
                  {cards.length === 0 && (
                    <li className="py-4 text-center text-xs text-h-muted">
                      Empty
                    </li>
                  )}
                </ol>
              </section>
            );
          })}
        </div>
      )}

      {assignTarget && projectId && (
        <AssignDialog
          card={assignTarget}
          workers={workers}
          projectId={projectId}
          onClose={() => setAssignTarget(null)}
          onAssigned={async () => {
            setAssignTarget(null);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

interface AssignDialogProps {
  card: BoardCard;
  workers: WorkerOut[];
  projectId: number;
  onClose: () => void;
  onAssigned: () => void | Promise<void>;
}

function AssignDialog({
  card,
  workers,
  projectId,
  onClose,
  onAssigned,
}: AssignDialogProps) {
  const [workerId, setWorkerId] = useState<number | null>(
    workers[0]?.id ?? null,
  );
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (workerId === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await createAssignment(projectId, card.item_id, {
        stage_key: card.next_stage_key,
        worker_id: workerId,
        note: note || null,
      });
      await onAssigned();
    } catch (e) {
      const err = e as Error & { detail?: { code?: string; assignment_id?: number } };
      if (err.detail?.code === "ACTIVE_ASSIGNMENT_EXISTS") {
        setError(
          `This item already has an active ${card.next_stage_key} assignment (#${err.detail.assignment_id}).`,
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Assign worker"
        className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-1 text-lg font-medium text-h-ink">
          Assign · {card.next_stage_key}
        </h2>
        <p className="mb-3 text-sm text-h-muted">
          Item #{card.item_number} {card.code ? ` · ${card.code}` : ""}
        </p>

        <label className="block text-sm text-h-muted">Worker</label>
        <select
          value={workerId ?? ""}
          onChange={(e) =>
            setWorkerId(e.target.value ? Number(e.target.value) : null)
          }
          className="mb-3 w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
        >
          {workers.length === 0 && <option value="">No workers</option>}
          {workers.map((w) => (
            <option key={w.id} value={w.id}>
              {w.full_name}
            </option>
          ))}
        </select>

        <label className="block text-sm text-h-muted">Note (optional)</label>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          className="mb-3 w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
        />

        {error && (
          <div className="mb-3 rounded border border-red-500 bg-red-50 p-2 text-xs text-red-900">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-h-line px-3 py-1 text-sm text-h-ink hover:bg-h-surface"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={submitting || workerId === null}
            onClick={submit}
            className="rounded border border-h-accent bg-h-accent px-3 py-1 text-sm text-h-bg disabled:opacity-50"
          >
            {submitting ? "Assigning…" : "Assign"}
          </button>
        </div>
      </div>
    </div>
  );
}

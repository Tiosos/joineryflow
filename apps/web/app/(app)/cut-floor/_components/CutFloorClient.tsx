"use client";

import { useEffect, useMemo, useState } from "react";

import {
  cancelCutSchedule,
  createCutSchedule,
  listCutPlansForProject,
  listCutSchedules,
  patchCutSchedule,
  reorderCutSchedules,
} from "@/lib/cut-floor-fetch";
import type {
  CutPlanSummary,
  CutScheduleOut,
  CutScheduleStatus,
} from "@/lib/cut-floor-types";

interface Project {
  id: number;
  project_code: string;
  name: string;
}

interface MeShape {
  id: number;
  auth_role: string;
  full_name?: string | null;
}

interface CutFloorClientProps {
  me: MeShape;
  projects: Project[];
  initialDate: string;
  initialProjectId: number | null;
}

function statusPillClass(status: CutScheduleStatus): string {
  switch (status) {
    case "planned":
      return "bg-h-line text-h-ink";
    case "running":
      return "bg-h-accent text-h-bg";
    case "done":
      return "bg-h-surface text-h-muted line-through";
    case "cancelled":
      return "bg-h-surface text-h-muted";
  }
}

function shiftDay(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, (m ?? 1) - 1, d ?? 1));
  dt.setUTCDate(dt.getUTCDate() + days);
  const yy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(dt.getUTCDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function canMutate(role: string): boolean {
  return ["admin", "manager", "drafter", "editor"].includes(role);
}

function canApprove(role: string): boolean {
  return ["admin", "manager", "drafter"].includes(role);
}

export function CutFloorClient({
  me,
  projects,
  initialDate,
  initialProjectId,
}: CutFloorClientProps) {
  const [date, setDate] = useState<string>(initialDate);
  const [projectId, setProjectId] = useState<number | null>(initialProjectId);
  const [rows, setRows] = useState<CutScheduleOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [draggingId, setDraggingId] = useState<number | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const data = await listCutSchedules({
        date,
        projectId: projectId ?? undefined,
      });
      setRows(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, projectId]);

  async function start(row: CutScheduleOut) {
    try {
      await patchCutSchedule(row.id, { status: "running" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function done(row: CutScheduleOut) {
    try {
      await patchCutSchedule(row.id, { status: "done" });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function cancel(row: CutScheduleOut) {
    if (!confirm(`Cancel schedule for "${row.cut_plan_name}"?`)) return;
    try {
      await cancelCutSchedule(row.id);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function onDragStart(id: number) {
    setDraggingId(id);
  }

  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  async function onDrop(targetId: number) {
    if (draggingId === null || draggingId === targetId) {
      setDraggingId(null);
      return;
    }
    const ids = rows.map((r) => r.id);
    const fromIdx = ids.indexOf(draggingId);
    const toIdx = ids.indexOf(targetId);
    if (fromIdx === -1 || toIdx === -1) {
      setDraggingId(null);
      return;
    }
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, draggingId);
    setDraggingId(null);
    try {
      await reorderCutSchedules({
        scheduled_for: date,
        ordered_ids: ids,
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const mutator = canMutate(me.auth_role);
  const approver = canApprove(me.auth_role);

  return (
    <div className="grid gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-medium text-h-ink">Cut Floor</h1>
        <span className="font-mono text-xs uppercase text-h-muted">
          machine team daily list
        </span>
      </header>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-h-line bg-h-surface px-3 py-2">
        <button
          type="button"
          onClick={() => setDate(shiftDay(date, -1))}
          className="rounded border border-h-line px-2 py-1 text-sm text-h-ink hover:bg-h-bg"
          aria-label="Previous day"
        >
          ←
        </button>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
        />
        <button
          type="button"
          onClick={() => setDate(shiftDay(date, 1))}
          className="rounded border border-h-line px-2 py-1 text-sm text-h-ink hover:bg-h-bg"
          aria-label="Next day"
        >
          →
        </button>

        <select
          value={projectId ?? ""}
          onChange={(e) =>
            setProjectId(e.target.value ? Number(e.target.value) : null)
          }
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
        >
          <option value="">All projects</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.project_code} — {p.name}
            </option>
          ))}
        </select>

        <div className="ml-auto">
          {mutator && (
            <button
              type="button"
              onClick={() => setAddOpen(true)}
              className="rounded border border-h-accent bg-h-accent px-3 py-1 text-sm text-h-bg hover:opacity-90"
            >
              + Add to {date === initialDate ? "today" : date}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
          Loading schedule…
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-h-line bg-h-surface p-8 text-center text-h-muted">
          Nothing scheduled for {date}.
        </div>
      ) : (
        <ol className="flex flex-col gap-2">
          {rows.map((row) => (
            <li
              key={row.id}
              draggable={mutator}
              onDragStart={() => onDragStart(row.id)}
              onDragOver={onDragOver}
              onDrop={() => onDrop(row.id)}
              className={[
                "flex flex-wrap items-center gap-3 rounded-lg border border-h-line bg-h-surface px-3 py-2",
                draggingId === row.id ? "opacity-60" : "",
                mutator ? "cursor-move" : "",
              ].join(" ")}
            >
              <span
                className={[
                  "rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
                  statusPillClass(row.status),
                ].join(" ")}
              >
                {row.status}
              </span>
              <span className="font-mono text-xs text-h-muted">
                pri {row.priority}
              </span>
              <span className="text-sm font-medium text-h-ink">
                {row.cut_plan_name ?? `plan #${row.cut_plan_id}`}
              </span>
              <span className="text-xs text-h-muted">
                {row.assigned_to_full_name ?? "unassigned"}
              </span>

              <div className="ml-auto flex gap-2">
                {mutator && row.status === "planned" && (
                  <button
                    type="button"
                    onClick={() => start(row)}
                    className="rounded border border-h-line px-2 py-1 text-xs text-h-ink hover:bg-h-bg"
                  >
                    Start
                  </button>
                )}
                {mutator && row.status === "running" && approver && (
                  <button
                    type="button"
                    onClick={() => done(row)}
                    className="rounded border border-h-accent bg-h-accent px-2 py-1 text-xs text-h-bg hover:opacity-90"
                  >
                    Mark done
                  </button>
                )}
                {mutator &&
                  (row.status === "planned" || row.status === "running") && (
                    <button
                      type="button"
                      onClick={() => cancel(row)}
                      className="rounded border border-h-line px-2 py-1 text-xs text-h-muted hover:text-h-ink"
                    >
                      Cancel
                    </button>
                  )}
              </div>
            </li>
          ))}
        </ol>
      )}

      {addOpen && (
        <AddPlanDialog
          projects={projects}
          defaultDate={date}
          onClose={() => setAddOpen(false)}
          onCreated={async () => {
            setAddOpen(false);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

interface AddPlanDialogProps {
  projects: Project[];
  defaultDate: string;
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}

function AddPlanDialog({
  projects,
  defaultDate,
  onClose,
  onCreated,
}: AddPlanDialogProps) {
  const [pickedProject, setPickedProject] = useState<number | null>(
    projects[0]?.id ?? null,
  );
  const [plans, setPlans] = useState<CutPlanSummary[]>([]);
  const [pickedPlan, setPickedPlan] = useState<number | null>(null);
  const [scheduledFor, setScheduledFor] = useState(defaultDate);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (pickedProject === null) {
      setPlans([]);
      return;
    }
    let cancelled = false;
    listCutPlansForProject(pickedProject)
      .then((data) => {
        if (cancelled) return;
        setPlans(data);
        setPickedPlan(data[0]?.id ?? null);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [pickedProject]);

  async function submit() {
    if (pickedPlan === null) return;
    setSubmitting(true);
    setError(null);
    try {
      await createCutSchedule({
        cut_plan_id: pickedPlan,
        scheduled_for: scheduledFor,
      });
      await onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const projectOptions = useMemo(() => projects, [projects]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Add cut plan to schedule"
        className="w-full max-w-md rounded-lg border border-h-line bg-h-bg p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-lg font-medium text-h-ink">
          Add to schedule
        </h2>

        <label className="block text-sm text-h-muted">Project</label>
        <select
          value={pickedProject ?? ""}
          onChange={(e) =>
            setPickedProject(e.target.value ? Number(e.target.value) : null)
          }
          className="mb-3 w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
        >
          {projectOptions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.project_code} — {p.name}
            </option>
          ))}
        </select>

        <label className="block text-sm text-h-muted">Cut plan</label>
        <select
          value={pickedPlan ?? ""}
          onChange={(e) =>
            setPickedPlan(e.target.value ? Number(e.target.value) : null)
          }
          className="mb-3 w-full rounded border border-h-line bg-h-surface px-2 py-1 text-sm text-h-ink"
        >
          {plans.length === 0 && <option value="">No plans yet</option>}
          {plans.map((p) => (
            <option key={p.id} value={p.id}>
              #{p.id} {p.name} · {p.sheet_count} sheet
              {p.sheet_count === 1 ? "" : "s"}
            </option>
          ))}
        </select>

        <label className="block text-sm text-h-muted">Scheduled for</label>
        <input
          type="date"
          value={scheduledFor}
          onChange={(e) => setScheduledFor(e.target.value)}
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
            disabled={submitting || pickedPlan === null}
            onClick={submit}
            className="rounded border border-h-accent bg-h-accent px-3 py-1 text-sm text-h-bg disabled:opacity-50"
          >
            {submitting ? "Adding…" : "Add"}
          </button>
        </div>
      </div>
    </div>
  );
}

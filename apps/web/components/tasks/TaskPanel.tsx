"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CommentThread } from "@/components/comments/CommentThread";
import { useConfirm } from "@/components/confirm/ConfirmProvider";
import { useUndo } from "@/components/undo/UndoProvider";
import { commentsApi } from "@/lib/comments-fetch";
import { taskErrorText, tasksApi } from "@/lib/tasks-fetch";
import { TASK_STATUS_LABEL, type CreateTaskBody, type TaskOut, type TaskStatus } from "@/lib/tasks-types";

export type TaskScope =
  | { kind: "mine" }
  | { kind: "item"; itemId: number }
  | { kind: "project"; projectId: number }
  | { kind: "cutlist"; cutlistId: number };

/** The target a task made here points at (none on the My tasks page). */
function targetOf(scope: TaskScope): Pick<CreateTaskBody, "project_id" | "item_id" | "cutlist_id"> {
  switch (scope.kind) {
    case "item": return { item_id: scope.itemId };
    case "project": return { project_id: scope.projectId };
    case "cutlist": return { cutlist_id: scope.cutlistId };
    default: return {};
  }
}

interface Props {
  scope: TaskScope;
  meId: number;
  meRole: string;
  /** Row id to highlight (the bell links to `/tasks?task=`). */
  highlight?: number | null;
  /** May this person create tasks here at all (the API still decides). */
  canCreate: boolean;
}

type Filter = "mine" | "active" | "done" | "cancelled";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "mine", label: "My tasks" },
  { key: "active", label: "All to do" },
  { key: "done", label: "Done" },
  { key: "cancelled", label: "Cancelled" },
];

const STATUSES: TaskStatus[] = ["open", "in_progress", "done", "cancelled"];

function todayLocal(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function targetHref(t: TaskOut): string | null {
  if (t.item_id != null) return `/items/${t.item_id}`;
  if (t.project_id != null) return `/projects/${t.project_id}`;
  return null;
}

/** Tasks (Plan V1 §10, Q524): "My tasks" on `/tasks`, and one item's tasks in the item editor. */
export function TaskPanel({ scope, meId, meRole, highlight, canCreate }: Props) {
  const { confirm, askText } = useConfirm();
  const { notify } = useUndo();
  const [filter, setFilter] = useState<Filter>("mine");
  const [rows, setRows] = useState<TaskOut[] | null>(null);
  // The task a link (the bell, a search hit) points at, when the current list does not hold it
  // (someone else's, unassigned, or already done): it is shown pinned above the list.
  const [linked, setLinked] = useState<TaskOut | null | "gone">(null);
  // The task whose comment thread is open (one at a time). A link to a task opens its own.
  const [thread, setThread] = useState<number | null>(highlight ?? null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const mine = scope.kind === "mine";
  const itemId = scope.kind === "item" ? scope.itemId : null;
  const projectId = scope.kind === "project" ? scope.projectId : null;
  const cutlistId = scope.kind === "cutlist" ? scope.cutlistId : null;
  const load = useCallback(async () => {
    try {
      const r = itemId != null ? await tasksApi.forItem(itemId)
        : projectId != null ? await tasksApi.list({ projectId, limit: 200 })
        : cutlistId != null ? await tasksApi.list({ cutlistId, limit: 200 })
        : filter === "mine" ? await tasksApi.list({ assignee: "me", status: "active" })
        : await tasksApi.list({ status: filter === "active" ? "active" : filter });
      setRows(r.items);
      setError(null);
    } catch (e) {
      setError(taskErrorText(e));
    }
  }, [itemId, projectId, cutlistId, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (highlight == null || !mine) return;
    if (rows?.some((t) => t.task_id === highlight)) {
      setLinked(null);
      return;
    }
    if (rows === null) return;
    let live = true;
    tasksApi.get(highlight).then((t) => live && setLinked(t)).catch(() => live && setLinked("gone"));
    return () => {
      live = false;
    };
  }, [highlight, mine, rows]);

  const mayChange = (t: TaskOut) =>
    meRole === "admin" || meRole === "manager" || t.created_by === meId || t.assignee_id === meId;

  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      await load();
      window.dispatchEvent(new Event("jf:notifications-changed")); // the bell's count
    } catch (e) {
      notify(taskErrorText(e));
      await load();
    }
  }

  async function rename(t: TaskOut) {
    const title = await askText({ title: "Rename task", label: "Title", initial: t.title, required: true });
    if (title === null || title === t.title) return;
    await run(() => tasksApi.patch(t.task_id, { title, expected_versions: { title: t.field_versions.title ?? 0 } }));
  }

  async function cancel(t: TaskOut) {
    if (!(await confirm({
      title: "Cancel this task?",
      message: `"${t.title}" will be marked cancelled. You can reopen it later.`,
      confirmLabel: "Cancel task",
      cancelLabel: "Keep it",
    }))) return;
    await run(() => tasksApi.setStatus(t.task_id, "cancelled"));
  }

  const today = todayLocal();
  const shown = linked && linked !== "gone" ? [linked, ...(rows ?? [])] : (rows ?? []);

  return (
    <div className="grid gap-3" data-testid="task-panel">
      <div className="flex flex-wrap items-center gap-2">
        {mine && FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
            className={[
              "rounded border px-2 py-1 text-xs",
              filter === f.key
                ? "border-h-accent bg-h-accent text-white"
                : "border-h-line text-h-muted hover:text-h-ink",
            ].join(" ")}
          >
            {f.label}
          </button>
        ))}
        {canCreate && (
          <button
            type="button"
            data-testid="task-new"
            onClick={() => setAdding((a) => !a)}
            className="ml-auto rounded bg-h-accent px-3 py-1 text-xs font-medium text-white"
          >
            {adding ? "Close" : "New task"}
          </button>
        )}
      </div>

      {adding && (
        <NewTask
          meId={meId}
          target={targetOf(scope)}
          onCreated={async () => {
            setAdding(false);
            await load();
            window.dispatchEvent(new Event("jf:notifications-changed"));
          }}
        />
      )}

      {error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
      {rows === null && !error && <p className="text-sm text-h-muted">Loading…</p>}
      {linked === "gone" && (
        <p className="text-sm text-h-muted" data-testid="task-gone">That task is not available.</p>
      )}
      {rows !== null && shown.length === 0 && (
        <p className="text-sm text-h-muted" data-testid="tasks-empty">No tasks here.</p>
      )}

      <ul className="grid gap-2">
        {shown.map((t) => {
          const href = targetHref(t);
          const closed = t.status === "done" || t.status === "cancelled";
          const overdue = !closed && t.due_date != null && t.due_date < today;
          return (
            <li
              key={t.task_id}
              data-testid="task-row"
              data-task-id={t.task_id}
              className={[
                "rounded border px-3 py-2",
                highlight === t.task_id ? "border-h-accent bg-h-bg" : "border-h-line bg-h-surface",
              ].join(" ")}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className={closed ? "text-h-muted line-through" : "font-medium text-h-ink"}>
                  {t.title}
                </span>
                <select
                  aria-label={`Status of ${t.title}`}
                  value={t.status}
                  disabled={!mayChange(t)}
                  onChange={(e) => {
                    const next = e.target.value as TaskStatus;
                    if (next === "cancelled") void cancel(t);
                    else void run(() => tasksApi.setStatus(t.task_id, next));
                  }}
                  className="ml-auto rounded border border-h-line bg-h-surface px-1 py-0.5 text-xs"
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{TASK_STATUS_LABEL[s]}</option>
                  ))}
                </select>
                {mayChange(t) && !closed && (
                  <button
                    type="button"
                    onClick={() => void rename(t)}
                    className="text-xs text-h-muted hover:text-h-ink"
                  >
                    Rename
                  </button>
                )}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-h-muted">
                <span>{t.assignee_name ? `For ${t.assignee_name}` : "Unassigned"}</span>
                {t.due_date && (
                  <span className={overdue ? "font-medium text-red-700" : "h-mono"}>
                    {`${overdue ? "Overdue · " : "Due "}${t.due_date}`}
                  </span>
                )}
                {t.target_label && (
                  href ? (
                    <Link href={href} className="hover:text-h-ink">
                      {`${t.target_type === "item" ? "Item" : t.target_type === "project" ? "Project" : "Cutlist"} ${t.target_label}`}
                    </Link>
                  ) : (
                    <span>{`Cutlist ${t.target_label}`}</span>
                  )
                )}
                <span>{`From ${t.created_by_name ?? "someone"}`}</span>
              </div>
              {t.description && <p className="mt-1 whitespace-pre-wrap text-sm text-h-ink">{t.description}</p>}
              <button
                type="button"
                data-testid="task-comments-toggle"
                aria-expanded={thread === t.task_id}
                onClick={() => setThread(thread === t.task_id ? null : t.task_id)}
                className="mt-1 text-xs text-h-muted hover:text-h-ink"
              >
                {t.comment_count > 0 ? `Comments (${t.comment_count})` : "Comments"}
              </button>
              {thread === t.task_id && (
                <div className="mt-2 border-t border-h-line pt-2" data-testid="task-thread">
                  <CommentThread
                    objectType="task"
                    objectId={t.task_id}
                    currentUserId={meId}
                    currentUserRole={meRole}
                    canComment={t.can_comment}
                    onMutated={() => void load()}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function NewTask({
  meId,
  target,
  onCreated,
}: {
  meId: number;
  target: ReturnType<typeof targetOf>;
  onCreated: () => Promise<void>;
}) {
  const { notify } = useUndo();
  const [team, setTeam] = useState<{ id: number; full_name: string | null }[]>([]);
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState<string>(String(meId));
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void commentsApi.mentionable().then(setTeam).catch(() => setTeam([]));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      await tasksApi.create({
        title: title.trim(),
        description: description.trim() || null,
        assignee_id: assignee === "" ? null : Number(assignee),
        due_date: due || null,
        ...target,
      });
      await onCreated();
    } catch (err) {
      notify(taskErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-2 rounded border border-h-line bg-h-surface p-3" data-testid="task-form">
      <input
        aria-label="Task title"
        placeholder="What needs doing?"
        value={title}
        maxLength={200}
        onChange={(e) => setTitle(e.target.value)}
        className="rounded border border-h-line px-2 py-1 text-sm"
      />
      <textarea
        aria-label="Task details"
        placeholder="Details (optional)"
        value={description}
        maxLength={5000}
        rows={2}
        onChange={(e) => setDescription(e.target.value)}
        className="rounded border border-h-line px-2 py-1 text-sm"
      />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-1 text-h-muted">
          For
          <select
            aria-label="Assign to"
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            className="rounded border border-h-line bg-h-surface px-1 py-0.5"
          >
            <option value="">Unassigned</option>
            {team.map((m) => (
              <option key={m.id} value={m.id}>{m.id === meId ? "Me" : (m.full_name ?? `User ${m.id}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-h-muted">
          Due
          <input
            type="date"
            aria-label="Due date"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            className="rounded border border-h-line px-1 py-0.5"
          />
        </label>
        <button
          type="submit"
          disabled={busy || !title.trim()}
          className="ml-auto rounded bg-h-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          Add task
        </button>
      </div>
    </form>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";

import { itemQueriesApi } from "@/lib/item-queries-fetch";
import type { ItemOut, ItemQueryOut } from "@/lib/pm-types";

import { lockFromError, lockMessage, moduleLockReason } from "./cutlist/moduleLock";

// item_queries/routes.py gates answering on `list:write` alone (no
// require_drafter on top, unlike AttachmentsTab/MaterialTakeTab) — per the
// RBAC matrix that's {drafter, manager, admin, editor}, one role wider than
// those two tabs' WRITER_ROLES/EDITORS sets.
const CAN_ANSWER = new Set(["drafter", "manager", "admin", "editor"]);

function formatTs(ts: string | null): string {
  if (!ts) return "—";
  return ts.replace("T", " ").slice(0, 16);
}

export function QueryTab({
  item,
  currentUserId,
  currentUserRole,
}: {
  item: ItemOut;
  currentUserId: number | null;
  currentUserRole: string | null;
}) {
  const itemId = item.id;
  const canAnswer = CAN_ANSWER.has(currentUserRole ?? "");
  // Answering answers to the Hard Lock and someone else's Controlled Lock (not the
  // Approval Lock). *Asking* answers to the Hard Lock only — anyone with list:read
  // may put a question to the lock's owner. The API decides; this only shows it.
  const answerLock = canAnswer ? moduleLockReason(item, currentUserId, currentUserRole, "records") : null;
  const askLock = item.hard_locked_at ? lockMessage("HARD_LOCKED", undefined, "records") : null;
  const [queries, setQueries] = useState<ItemQueryOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await itemQueriesApi.list(itemId);
      setQueries(rows.slice().sort((a, b) => b.asked_at.localeCompare(a.asked_at)));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load queries");
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function askQuestion(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await itemQueriesApi.ask(itemId, question.trim());
      setQuestion("");
      await load();
    } catch (e) {
      setError(lockFromError(e, "records") ?? (e instanceof Error ? e.message : "Failed to ask question"));
    } finally {
      setBusy(false);
    }
  }

  if (!queries) {
    return <p className="text-sm text-h-muted">{error ?? "Loading…"}</p>;
  }

  return (
    <div className="grid gap-4">
      {error && (
        <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      )}

      {(answerLock || askLock) && (
        <div
          className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          data-testid="queries-locked"
        >
          {askLock ?? answerLock}
        </div>
      )}

      <form onSubmit={askQuestion} className="flex flex-wrap items-end gap-2">
        <div className="min-w-64 flex-1">
          <label className="mb-1 block text-xs text-h-muted" htmlFor="new-query-question">
            Ask a question
          </label>
          <input
            id="new-query-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. Which finish for the island bench?"
            disabled={!!askLock}
            className="w-full rounded border border-h-line bg-white px-2 py-1.5 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={busy || !question.trim() || !!askLock}
          title={askLock ?? undefined}
          className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Ask
        </button>
      </form>

      {queries.length === 0 && (
        <p className="text-sm text-h-muted">No questions on this item yet.</p>
      )}

      <ul className="grid gap-3">
        {queries.map((q) => (
          <QueryRow
            key={q.query_id}
            query={q}
            canAnswer={canAnswer}
            lockReason={askLock ?? answerLock}
            onChanged={load}
          />
        ))}
      </ul>
    </div>
  );
}

function QueryRow({
  query,
  canAnswer,
  lockReason,
  onChanged,
}: {
  query: ItemQueryOut;
  canAnswer: boolean;
  lockReason: string | null;
  onChanged: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [answer, setAnswer] = useState(query.answer ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const answered = query.answer != null;

  async function submit() {
    if (!answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (answered) {
        await itemQueriesApi.editAnswer(query.query_id, answer.trim());
      } else {
        await itemQueriesApi.answer(query.query_id, answer.trim());
      }
      setEditing(false);
      await onChanged();
    } catch (e) {
      setError(lockFromError(e, "records") ?? (e instanceof Error ? e.message : "Failed to save answer"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded border border-h-line bg-h-surface p-3">
      <p className="text-sm text-h-ink">{query.question}</p>
      <p className="mt-1 text-xs text-h-muted">
        Asked by {query.asked_by_name ?? "—"} · {formatTs(query.asked_at)}
      </p>

      {answered && !editing && (
        <div className="mt-2 rounded bg-h-bg px-2 py-1.5 text-sm text-h-ink">
          {query.answer}
          <p className="mt-1 text-xs text-h-muted">
            Answered by {query.answered_by_name ?? "—"} · {formatTs(query.answered_at)}
          </p>
        </div>
      )}

      {canAnswer && (editing || !answered) && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={2}
            placeholder="Write an answer…"
            disabled={!!lockReason}
            className="min-w-64 flex-1 rounded border border-h-line bg-white px-2 py-1 text-sm"
          />
          <button
            type="button"
            disabled={busy || !answer.trim() || !!lockReason}
            title={lockReason ?? undefined}
            onClick={submit}
            className="rounded bg-h-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
          >
            {answered ? "Save" : "Answer"}
          </button>
          {editing && (
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setAnswer(query.answer ?? "");
              }}
              className="rounded border border-h-line px-2 py-1 text-xs text-h-ink"
            >
              Cancel
            </button>
          )}
        </div>
      )}

      {canAnswer && answered && !editing && (
        <button
          type="button"
          onClick={() => setEditing(true)}
          disabled={!!lockReason}
          title={lockReason ?? undefined}
          className="mt-2 text-xs text-h-muted hover:text-h-ink disabled:opacity-50"
        >
          Edit answer
        </button>
      )}

      {error && <p className="mt-1 text-xs text-rose-700">{error}</p>}
    </li>
  );
}

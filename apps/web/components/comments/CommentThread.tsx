"use client";

import { useCallback, useEffect, useState } from "react";

import { commentsApi } from "@/lib/comments-fetch";
import type { CommentObjectType, CommentOut, Mentionable } from "@/lib/comments-types";
import { formatLocalTs } from "./format";
import { MentionTextarea } from "./MentionTextarea";
import { mentionedIds, splitByMentions } from "./mentions";

function errorMessage(e: unknown, fallback: string): string {
  const code = e instanceof Error ? e.message : "";
  if (code === "BAD_MENTION")
    return "Someone you mentioned can't be notified — they may no longer have access here.";
  if (code === "PARENT_DELETED") return "That comment was deleted.";
  if (code === "COMMENT_DELETED") return "That comment was deleted.";
  return code || fallback;
}

/** The thread on one Project / Area / Room / Joinery Item / Module / shop-drawing
 *  revision (Plan V1 §29).
 *
 *  `canComment` mirrors the `comment` grant on the object's own module —
 *  `tracking`, except `list` for a module and `shop_dwgs` for a revision; the
 *  API enforces it either way.
 *  Editing is author-only; deleting is the author or a manager / admin. */
export function CommentThread({
  objectType,
  objectId,
  currentUserId,
  currentUserRole,
  canComment,
  onMutated,
  roster,
}: {
  objectType: CommentObjectType;
  objectId: number;
  currentUserId: number | null;
  currentUserRole: string | null;
  canComment: boolean;
  /** Called after a post, reply, edit or delete has succeeded and the thread
   *  has reloaded — lets a parent refresh anything derived from it (counts). */
  onMutated?: () => void;
  /** The workspace roster, when the parent already has it. The Areas & Rooms
   *  card remounts a thread on every row click; passing it in saves a
   *  `/workspace/team` request per click. Deliberately not cached across
   *  mounts in a module: that would outlive a logout and show the previous
   *  user's team to the next one. */
  roster?: Mentionable[];
}) {
  const [comments, setComments] = useState<CommentOut[] | null>(null);
  const [fetchedMembers, setMembers] = useState<Mentionable[]>([]);
  const members = roster ?? fetchedMembers;
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const t = await commentsApi.list(objectType, objectId);
      setComments(t.comments);
      setError(null);
    } catch (e) {
      setError(errorMessage(e, "Failed to load comments"));
    }
  }, [objectType, objectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (roster) return;
    // Without the roster the picker just stays off; commenting still works.
    commentsApi.mentionable().then(setMembers).catch(() => setMembers([]));
  }, [roster]);

  const mentionable = members.filter((m) => m.id !== currentUserId);

  const changed = useCallback(async () => {
    await load();
    onMutated?.();
  }, [load, onMutated]);

  async function post(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await commentsApi.create(objectType, objectId, text.trim(), mentionedIds(text, mentionable));
      setText("");
      await changed();
    } catch (err) {
      setError(errorMessage(err, "Failed to post comment"));
    } finally {
      setBusy(false);
    }
  }

  if (!comments) {
    return <p className="text-sm text-h-muted">{error ?? "Loading…"}</p>;
  }

  return (
    <div className="grid gap-4" data-testid="comment-thread">
      {error && (
        <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
          {error}
        </div>
      )}

      {canComment ? (
        <form onSubmit={post} className="grid gap-2">
          <label className="text-xs text-h-muted" htmlFor={`new-comment-${objectType}-${objectId}`}>
            Add a comment — type @ to mention someone
          </label>
          <MentionTextarea
            value={text}
            onChange={setText}
            members={mentionable}
            placeholder="Write a comment…"
            testId="comment-input"
            id={`new-comment-${objectType}-${objectId}`}
          />
          <div>
            <button
              type="submit"
              data-testid="comment-submit"
              disabled={busy || !text.trim()}
              className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Comment
            </button>
          </div>
        </form>
      ) : (
        <p className="text-xs text-h-muted">You can read this thread but not post to it.</p>
      )}

      {comments.length === 0 && <p className="text-sm text-h-muted">No comments yet.</p>}

      <ul className="grid gap-3">
        {comments.map((c) => (
          <li key={c.comment_id} className="grid gap-2">
            <CommentItem
              comment={c}
              members={mentionable}
              currentUserId={currentUserId}
              currentUserRole={currentUserRole}
              canComment={canComment}
              canReply
              onChanged={changed}
              onError={setError}
            />
            {c.replies.length > 0 && (
              <ul className="ml-6 grid gap-2 border-l border-h-line pl-3">
                {c.replies.map((r) => (
                  <li key={r.comment_id}>
                    <CommentItem
                      comment={r}
                      members={mentionable}
                      currentUserId={currentUserId}
                      currentUserRole={currentUserRole}
                      canComment={canComment}
                      canReply={false}
                      onChanged={changed}
                      onError={setError}
                    />
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CommentItem({
  comment,
  members,
  currentUserId,
  currentUserRole,
  canComment,
  canReply,
  onChanged,
  onError,
}: {
  comment: CommentOut;
  members: Mentionable[];
  currentUserId: number | null;
  currentUserRole: string | null;
  canComment: boolean;
  canReply: boolean;
  onChanged: () => Promise<void>;
  onError: (msg: string | null) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "reply">("view");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const isAuthor = currentUserId != null && comment.author_id === currentUserId;
  const canDelete =
    canComment && (isAuthor || currentUserRole === "manager" || currentUserRole === "admin");

  async function run(fn: () => Promise<unknown>, fallback: string) {
    setBusy(true);
    onError(null);
    try {
      await fn();
      setMode("view");
      setDraft("");
      await onChanged();
    } catch (e) {
      onError(errorMessage(e, fallback));
    } finally {
      setBusy(false);
    }
  }

  if (comment.deleted) {
    return (
      <div className="rounded border border-dashed border-h-line px-3 py-2 text-sm italic text-h-muted">
        This comment was deleted.
      </div>
    );
  }

  const names = comment.mentions.map((m) => m.full_name ?? "");

  return (
    <div className="rounded border border-h-line bg-h-surface p-3" data-testid="comment-item">
      <p className="text-xs text-h-muted">
        <span className="font-medium text-h-ink">{comment.author_name ?? "Former user"}</span>
        {" · "}
        {formatLocalTs(comment.created_at)}
        {comment.edited_at && " · edited"}
      </p>

      {mode === "edit" ? (
        <div className="mt-2 grid gap-2">
          <MentionTextarea value={draft} onChange={setDraft} members={members} testId="comment-edit-input" />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !draft.trim()}
              onClick={() =>
                run(
                  () => commentsApi.edit(comment.comment_id, draft.trim(), mentionedIds(draft, members)),
                  "Failed to save comment",
                )
              }
              className="rounded bg-h-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => setMode("view")}
              className="rounded border border-h-line px-2 py-1 text-xs text-h-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <p className="mt-1 whitespace-pre-wrap text-sm text-h-ink">
          {splitByMentions(comment.body, names).map((p, i) =>
            p.mention ? (
              <span key={i} className="rounded bg-h-accent-soft px-0.5 font-medium">
                {p.text}
              </span>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </p>
      )}

      {mode === "reply" && (
        <div className="mt-2 grid gap-2">
          <MentionTextarea
            value={draft}
            onChange={setDraft}
            members={members}
            placeholder="Write a reply…"
            testId="comment-reply-input"
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !draft.trim()}
              onClick={() =>
                run(
                  () => commentsApi.reply(comment.comment_id, draft.trim(), mentionedIds(draft, members)),
                  "Failed to post reply",
                )
              }
              className="rounded bg-h-accent px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              Reply
            </button>
            <button
              type="button"
              onClick={() => setMode("view")}
              className="rounded border border-h-line px-2 py-1 text-xs text-h-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === "view" && (
        <div className="mt-2 flex gap-3 text-xs text-h-muted">
          {canComment && canReply && (
            <button type="button" className="hover:text-h-ink" onClick={() => setMode("reply")}>
              Reply
            </button>
          )}
          {canComment && isAuthor && (
            <button
              type="button"
              className="hover:text-h-ink"
              onClick={() => {
                setDraft(comment.body);
                setMode("edit");
              }}
            >
              Edit
            </button>
          )}
          {canDelete && (
            <button
              type="button"
              className="hover:text-rose-700"
              onClick={() => {
                if (window.confirm("Delete this comment?")) {
                  void run(() => commentsApi.remove(comment.comment_id), "Failed to delete comment");
                }
              }}
            >
              Delete
            </button>
          )}
        </div>
      )}
    </div>
  );
}

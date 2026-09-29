import type {
  CommentCounts,
  CommentObjectType,
  CommentOut,
  CommentThread,
  Mentionable,
  NotificationList,
} from "./comments-types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const detail = body?.detail;
    // `detail` is a string, or {code, ...} (BAD_MENTION, NOT_AUTHOR, …) —
    // coercing the object straight into Error's message gives "[object Object]".
    const message =
      typeof detail === "string" ? detail :
      typeof detail?.code === "string" ? detail.code :
      `${init?.method ?? "GET"} ${path} failed: ${r.status}`;
    throw new Error(message);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export const commentsApi = {
  list: (objectType: CommentObjectType, objectId: number) =>
    call<CommentThread>(`/api/comments?object_type=${objectType}&object_id=${objectId}`),
  create: (objectType: CommentObjectType, objectId: number, body: string, mentionedUserIds: number[]) =>
    call<CommentOut>("/api/comments", jsonInit("POST", {
      object_type: objectType, object_id: objectId, body, mentioned_user_ids: mentionedUserIds,
    })),
  reply: (parentId: number, body: string, mentionedUserIds: number[]) =>
    call<CommentOut>("/api/comments", jsonInit("POST", {
      parent_id: parentId, body, mentioned_user_ids: mentionedUserIds,
    })),
  edit: (commentId: number, body: string, mentionedUserIds: number[]) =>
    call<CommentOut>(`/api/comments/${commentId}`, jsonInit("PATCH", {
      body, mentioned_user_ids: mentionedUserIds,
    })),
  remove: (commentId: number) =>
    call<void>(`/api/comments/${commentId}`, { method: "DELETE" }),
  counts: (projectId: number) =>
    call<CommentCounts>(`/api/projects/${projectId}/comment-counts`),
  mentionable: async (): Promise<Mentionable[]> => {
    const t = await call<{ members: Mentionable[] }>("/api/workspace/team");
    return t.members;
  },
};

export const notificationsApi = {
  list: (opts: { unreadOnly?: boolean; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (opts.unreadOnly) qs.set("unread_only", "true");
    if (opts.limit) qs.set("limit", String(opts.limit));
    return call<NotificationList>(`/api/notifications?${qs}`);
  },
  markRead: (id: number) => call<void>(`/api/notifications/${id}/read`, { method: "POST" }),
  markAllRead: () => call<{ marked: number }>("/api/notifications/read-all", { method: "POST" }),
};

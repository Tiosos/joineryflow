import type {
  CommentCounts,
  CommentObjectType,
  CommentOut,
  CommentThread,
  Mentionable,
  NotificationList,
} from "./comments-types";
import { apiCall, jsonInit } from "./api";

export const commentsApi = {
  list: (objectType: CommentObjectType, objectId: number) =>
    apiCall<CommentThread>(`/api/comments?object_type=${objectType}&object_id=${objectId}`),
  create: (objectType: CommentObjectType, objectId: number, body: string, mentionedUserIds: number[]) =>
    apiCall<CommentOut>("/api/comments", jsonInit("POST", {
      object_type: objectType, object_id: objectId, body, mentioned_user_ids: mentionedUserIds,
    })),
  reply: (parentId: number, body: string, mentionedUserIds: number[]) =>
    apiCall<CommentOut>("/api/comments", jsonInit("POST", {
      parent_id: parentId, body, mentioned_user_ids: mentionedUserIds,
    })),
  edit: (commentId: number, body: string, mentionedUserIds: number[]) =>
    apiCall<CommentOut>(`/api/comments/${commentId}`, jsonInit("PATCH", {
      body, mentioned_user_ids: mentionedUserIds,
    })),
  remove: (commentId: number) =>
    apiCall<void>(`/api/comments/${commentId}`, { method: "DELETE" }),
  counts: (projectId: number) =>
    apiCall<CommentCounts>(`/api/projects/${projectId}/comment-counts`),
  mentionable: async (): Promise<Mentionable[]> => {
    const t = await apiCall<{ members: Mentionable[] }>("/api/workspace/team");
    return t.members;
  },
};

export const notificationsApi = {
  list: (opts: { unreadOnly?: boolean; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (opts.unreadOnly) qs.set("unread_only", "true");
    if (opts.limit) qs.set("limit", String(opts.limit));
    return apiCall<NotificationList>(`/api/notifications?${qs}`);
  },
  markRead: (id: number) => apiCall<void>(`/api/notifications/${id}/read`, { method: "POST" }),
  markAllRead: () => apiCall<{ marked: number }>("/api/notifications/read-all", { method: "POST" }),
};

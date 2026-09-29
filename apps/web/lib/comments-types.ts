// Mirrors apps/api/app/comments/schemas.py and notifications/schemas.py
// (migrations 0042 + 0043, Plan V1 §29). Timestamps arrive as ISO strings.

export type CommentObjectType =
  | "project"
  | "area"
  | "room"
  | "item"
  | "module"
  | "revision";

export interface CommentMention {
  user_id: number;
  full_name: string | null;
}

export interface CommentOut {
  comment_id: number;
  object_type: CommentObjectType;
  object_id: number;
  parent_comment_id: number | null;
  author_id: number | null;
  author_name: string | null;
  /** Blank when `deleted` — a deleted comment survives only as a placeholder
   *  in front of replies that outlived it. */
  body: string;
  created_at: string;
  edited_at: string | null;
  deleted: boolean;
  mentions: CommentMention[];
  replies: CommentOut[];
}

export interface CommentThread {
  comments: CommentOut[];
}

export interface NotificationOut {
  notification_id: number;
  kind: "mention" | "reply";
  created_at: string;
  read_at: string | null;
  actor_id: number | null;
  actor_name: string | null;
  comment_id: number;
  excerpt: string;
  object_type: CommentObjectType;
  object_id: number;
  object_label: string | null;
  /** null only when the link cannot be built. Area / Room open the project
   *  page's card, a module the item editor's Cutlist tab, a revision the
   *  shop-drawings drawer. */
  url: string | null;
}

export interface NotificationList {
  notifications: NotificationOut[];
  unread_count: number;
}

/** Live comment counts per area / room of one project (absent = none). */
export interface CommentCounts {
  areas: Record<number, number>;
  rooms: Record<number, number>;
}

/** The slice of `/workspace/team` the mention picker needs. */
export interface Mentionable {
  id: number;
  full_name: string;
  auth_role: string;
}

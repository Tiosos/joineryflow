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

/** An order still `Pending`, waiting for the purchase officer's decision. Derived on read: it has no
 *  read state and leaves the list when the order is decided or cancelled. */
export interface OrderWaiting {
  po_id: number;
  po_number: string;
  description: string | null;
  vendor_name: string | null;
  requester_name: string | null;
  created_at: string;
  url: string;
}

/** A held save on a Controlled-Lock item, still pending, that this user may decide (the lock owner,
 *  a manager, an admin). Derived on read: no read state, it leaves the list when decided. */
export interface LockRequestWaiting {
  request_id: number;
  item_id: number;
  item_number: number | null;
  project_code: string | null;
  requested_by_name: string | null;
  /** The item fields the held save would change. */
  fields: string[];
  created_at: string;
  url: string;
}

export interface NotificationList {
  notifications: NotificationOut[];
  unread_count: number;
  /** Purchase officers only; left out of the reply for everyone else. */
  orders_waiting?: OrderWaiting[];
  orders_waiting_count?: number;
  /** Drafters, managers and admins only; left out of the reply for everyone else. */
  lock_requests_waiting?: LockRequestWaiting[];
  lock_requests_waiting_count?: number;
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

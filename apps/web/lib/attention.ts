// The bell's "waiting for you" list (Q613): mirrors apps/api/app/notifications/attention.py.
// Derived on every call by the API: no read state, an item leaves when decided or done.

export type AttentionKind = "lock_request" | "variation" | "order" | "task";

export interface AttentionItem {
  kind: AttentionKind;
  /** "<kind>:<id>", unique within the list. */
  key: string;
  title: string;
  detail: string | null;
  url: string;
  created_at: string | null;
}

/** Per-kind wording and test ids, in the order the API returns the kinds. */
export const ATTENTION_KINDS: Record<
  AttentionKind,
  {
    heading: (total: number) => string;
    section: string;
    row: string;
    pageList: string;
    /** Where "all of them" lives, when somewhere does. */
    all: { href: string; bell: string; page: (total: number) => string } | null;
  }
> = {
  lock_request: {
    heading: (n) => `Held saves waiting for your decision (${n})`,
    section: "lock-requests-waiting",
    row: "lock-request-waiting",
    pageList: "lock-requests-waiting-list",
    all: null,
  },
  variation: {
    heading: (n) => `Variations awaiting your approval (${n})`,
    section: "variations-waiting",
    row: "variation-waiting",
    pageList: "variations-waiting-list",
    all: null,
  },
  order: {
    heading: (n) => `Orders waiting for your decision (${n})`,
    section: "orders-waiting",
    row: "order-waiting",
    pageList: "orders-waiting-list",
    all: { href: "/orderbook?status=Pending", bell: "all pending orders", page: (n) => `All ${n} pending orders` },
  },
  task: {
    heading: (n) => `Your tasks (${n})`,
    section: "tasks-open",
    row: "task-open",
    pageList: "tasks-open-list",
    all: { href: "/tasks", bell: "all my tasks", page: (n) => `All ${n} tasks` },
  },
};

export const ATTENTION_ORDER: AttentionKind[] = ["lock_request", "variation", "order", "task"];

export function groupAttention(items: AttentionItem[]): Map<AttentionKind, AttentionItem[]> {
  const by = new Map<AttentionKind, AttentionItem[]>();
  for (const k of ATTENTION_ORDER) by.set(k, []);
  for (const i of items) by.get(i.kind)?.push(i);
  return by;
}

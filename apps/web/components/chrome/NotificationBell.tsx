"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { notificationsApi } from "@/lib/comments-fetch";
import type { LockRequestWaiting, NotificationOut, OrderWaiting } from "@/lib/comments-types";

const POLL_MS = 60_000;
const PREVIEW = 6;

export function notificationText(n: NotificationOut): string {
  const who = n.actor_name ?? "Someone";
  return n.kind === "mention" ? `${who} mentioned you` : `${who} replied to your comment`;
}

/** Top-bar inbox (Plan V1 §29 / Q521: in-app only). Polls once a minute and on
 *  window focus — there is no push channel, by decision. */
export function NotificationBell() {
  const router = useRouter();
  const boxRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationOut[]>([]);
  const [waiting, setWaiting] = useState<OrderWaiting[]>([]);
  const [waitingCount, setWaitingCount] = useState(0);
  const [lockWaiting, setLockWaiting] = useState<LockRequestWaiting[]>([]);
  const [lockCount, setLockCount] = useState(0);
  // Orders and lock requests waiting for a decision count on the badge too; they have no read
  // state, they leave when decided. So the badge is "need attention", not "unread".
  const badge = unread + waitingCount + lockCount;
  const shownWaiting = waiting.slice(0, PREVIEW);
  const shownLock = lockWaiting.slice(0, PREVIEW);
  const showEmpty = items.length === 0 && waitingCount === 0 && lockCount === 0;

  const refresh = useCallback(async () => {
    try {
      const r = await notificationsApi.list({ limit: PREVIEW });
      setUnread(r.unread_count);
      setItems(r.notifications);
      setWaiting(r.orders_waiting ?? []);
      setWaitingCount(r.orders_waiting_count ?? 0);
      setLockWaiting(r.lock_requests_waiting ?? []);
      setLockCount(r.lock_requests_waiting_count ?? 0);
    } catch {
      // A failed poll keeps the last known state; the next tick retries.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), POLL_MS);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    // A page that changed what is waiting (the lock-request banner) asks for an immediate re-read.
    window.addEventListener("jf:notifications-changed", onFocus);
    return () => {
      clearInterval(t);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("jf:notifications-changed", onFocus);
    };
  }, [refresh]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function openOne(n: NotificationOut) {
    setOpen(false);
    if (!n.read_at) await notificationsApi.markRead(n.notification_id).catch(() => {});
    await refresh();
    if (n.url) router.push(n.url);
  }

  async function readAll() {
    await notificationsApi.markAllRead().catch(() => {});
    await refresh();
  }

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        aria-label={badge > 0 ? `Notifications, ${badge} need attention` : "Notifications"}
        aria-expanded={open}
        data-testid="notification-bell"
        onClick={() => {
          setOpen((o) => !o);
          void refresh();
        }}
        className="relative rounded px-2 py-1 text-sm text-h-muted hover:text-h-ink"
      >
        <span aria-hidden>🔔</span>
        {badge > 0 && (
          <span
            data-testid="notification-count"
            className="absolute -right-1 -top-1 min-w-4 rounded-full bg-h-accent px-1 text-center text-[10px] font-semibold leading-4 text-white"
          >
            {badge > 99 ? "99+" : badge}
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-30 mt-1 w-80 overflow-hidden rounded border border-h-line bg-h-surface shadow"
        >
          <div className="flex items-center justify-between border-b border-h-line px-3 py-2 text-xs">
            <span className="font-semibold text-h-ink">Notifications</span>
            {unread > 0 && (
              <button type="button" onClick={readAll} className="text-h-muted hover:text-h-ink">
                Mark all read
              </button>
            )}
          </div>
          {lockCount > 0 && (
            <div data-testid="lock-requests-waiting" className="border-b border-h-line">
              <div className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wider text-h-muted">
                {`Held saves waiting for your decision (${lockCount})`}
              </div>
              <ul>
                {shownLock.map((l) => (
                  <li key={l.request_id}>
                    <Link
                      href={l.url}
                      onClick={() => setOpen(false)}
                      data-testid="lock-request-waiting"
                      className="block px-3 py-1.5 text-sm text-h-ink hover:bg-h-bg"
                    >
                      <span className="h-mono">{l.item_number != null ? `#${l.item_number}` : `Item ${l.item_id}`}</span>
                      <span className="text-xs text-h-muted">
                        {` · ${l.project_code ?? "no project"}${l.requested_by_name ? ` · ${l.requested_by_name}` : ""}`}
                      </span>
                      <span className="block truncate text-xs text-h-muted">{`Changes ${l.fields.join(", ")}`}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              {lockCount > shownLock.length && (
                <Link
                  href="/notifications"
                  onClick={() => setOpen(false)}
                  className="block px-3 pb-2 text-xs text-h-muted hover:text-h-ink"
                >
                  {`+${lockCount - shownLock.length} more`}
                </Link>
              )}
            </div>
          )}
          {waitingCount > 0 && (
            <div data-testid="orders-waiting" className="border-b border-h-line">
              <div className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wider text-h-muted">
                {`Orders waiting for your decision (${waitingCount})`}
              </div>
              <ul>
                {shownWaiting.map((o) => (
                  <li key={o.po_id}>
                    <Link
                      href={o.url}
                      onClick={() => setOpen(false)}
                      data-testid="order-waiting"
                      className="block px-3 py-1.5 text-sm text-h-ink hover:bg-h-bg"
                    >
                      <span className="h-mono">{o.po_number}</span>
                      <span className="text-xs text-h-muted">
                        {` · ${o.vendor_name ?? "no supplier"}${o.requester_name ? ` · ${o.requester_name}` : ""}`}
                      </span>
                      <span className="block truncate text-xs text-h-muted">{o.description}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              <Link
                href="/orderbook?status=Pending"
                onClick={() => setOpen(false)}
                className="block px-3 pb-2 text-xs text-h-muted hover:text-h-ink"
              >
                {waitingCount > shownWaiting.length
                  ? `+${waitingCount - shownWaiting.length} more · all pending orders`
                  : "All pending orders"}
              </Link>
            </div>
          )}
          {showEmpty && <p className="px-3 py-4 text-sm text-h-muted">Nothing yet.</p>}
          {items.length > 0 && (
            <ul>
              {items.map((n) => (
                <li key={n.notification_id}>
                  <button
                    type="button"
                    onClick={() => void openOne(n)}
                    className={[
                      "block w-full border-b border-h-line px-3 py-2 text-left text-sm hover:bg-h-bg",
                      n.read_at ? "text-h-muted" : "text-h-ink",
                    ].join(" ")}
                  >
                    <span className={n.read_at ? "" : "font-medium"}>{notificationText(n)}</span>
                    {n.object_label && (
                      <span className="text-xs text-h-muted"> · {n.object_label}</span>
                    )}
                    <span className="mt-0.5 block truncate text-xs text-h-muted">{n.excerpt}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Link
            href="/notifications"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-center text-xs text-h-muted hover:text-h-ink"
          >
            View all
          </Link>
        </div>
      )}
    </div>
  );
}

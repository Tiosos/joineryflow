"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { notificationsApi } from "@/lib/comments-fetch";
import type { NotificationOut } from "@/lib/comments-types";

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

  const refresh = useCallback(async () => {
    try {
      const r = await notificationsApi.list({ limit: PREVIEW });
      setUnread(r.unread_count);
      setItems(r.notifications);
    } catch {
      // A failed poll keeps the last known state; the next tick retries.
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), POLL_MS);
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => {
      clearInterval(t);
      window.removeEventListener("focus", onFocus);
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
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        data-testid="notification-bell"
        onClick={() => {
          setOpen((o) => !o);
          void refresh();
        }}
        className="relative rounded px-2 py-1 text-sm text-h-muted hover:text-h-ink"
      >
        <span aria-hidden>🔔</span>
        {unread > 0 && (
          <span
            data-testid="notification-count"
            className="absolute -right-1 -top-1 min-w-4 rounded-full bg-h-accent px-1 text-center text-[10px] font-semibold leading-4 text-white"
          >
            {unread > 99 ? "99+" : unread}
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
          {items.length === 0 ? (
            <p className="px-3 py-4 text-sm text-h-muted">Nothing yet.</p>
          ) : (
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

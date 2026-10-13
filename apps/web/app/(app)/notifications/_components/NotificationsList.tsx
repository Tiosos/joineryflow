"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { notificationText } from "@/components/chrome/NotificationBell";
import { formatLocalTs } from "@/components/comments/format";
import { notificationsApi } from "@/lib/comments-fetch";
import type { NotificationOut, OrderWaiting } from "@/lib/comments-types";

const PAGE = 100;

export function NotificationsList() {
  const router = useRouter();
  const [rows, setRows] = useState<NotificationOut[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [waiting, setWaiting] = useState<OrderWaiting[]>([]);
  const [waitingCount, setWaitingCount] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await notificationsApi.list({ unreadOnly, limit: PAGE });
      setRows(r.notifications);
      setUnread(r.unread_count);
      setWaiting(r.orders_waiting ?? []);
      setWaitingCount(r.orders_waiting_count ?? 0);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load notifications");
    }
  }, [unreadOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  async function open(n: NotificationOut) {
    if (!n.read_at) await notificationsApi.markRead(n.notification_id).catch(() => {});
    if (n.url) router.push(n.url);
  }

  return (
    <div className="grid max-w-3xl gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-h-ink">
          Notifications{unread > 0 && <span className="ml-2 text-sm text-h-muted">{unread} unread</span>}
        </h1>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-1 text-h-muted">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(e) => setUnreadOnly(e.target.checked)}
            />
            Unread only
          </label>
          {unread > 0 && (
            <button
              type="button"
              onClick={async () => {
                await notificationsApi.markAllRead().catch(() => {});
                await load();
              }}
              className="rounded border border-h-line px-2 py-1 text-xs text-h-ink"
            >
              Mark all read
            </button>
          )}
        </div>
      </div>

      {waitingCount > 0 && (
        <section data-testid="orders-waiting-list" className="grid gap-2">
          <h2 className="text-sm font-semibold text-h-ink">
            {`Orders waiting for your decision (${waitingCount})`}
          </h2>
          <ul className="grid gap-2">
            {waiting.map((o) => (
              <li key={o.po_id}>
                <Link
                  href={o.url}
                  className="block rounded border border-h-line bg-h-surface px-3 py-2 text-sm text-h-ink hover:bg-h-bg"
                >
                  <span className="h-mono">{o.po_number}</span>
                  <span className="text-xs text-h-muted">
                    {` · ${o.vendor_name ?? "no supplier"}${o.requester_name ? ` · ${o.requester_name}` : ""} · ${formatLocalTs(o.created_at)}`}
                  </span>
                  <span className="mt-0.5 block text-sm">{o.description}</span>
                </Link>
              </li>
            ))}
          </ul>
          {waitingCount > waiting.length && (
            <Link href="/orderbook?status=Pending" className="text-xs text-h-muted hover:text-h-ink">
              {`All ${waitingCount} pending orders`}
            </Link>
          )}
        </section>
      )}

      {error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
      {!rows && !error && <p className="text-sm text-h-muted">Loading…</p>}
      {rows && rows.length === 0 && waitingCount === 0 && (
        <p className="text-sm text-h-muted">
          {unreadOnly ? "Nothing unread." : "No notifications yet."}
        </p>
      )}

      <ul className="grid gap-2">
        {rows?.map((n) => (
          <li key={n.notification_id}>
            <button
              type="button"
              onClick={() => void open(n)}
              className={[
                "block w-full rounded border border-h-line bg-h-surface px-3 py-2 text-left text-sm hover:bg-h-bg",
                n.read_at ? "text-h-muted" : "text-h-ink",
              ].join(" ")}
            >
              <span className={n.read_at ? "" : "font-medium"}>{notificationText(n)}</span>
              {n.object_label && <span className="text-xs text-h-muted"> · {n.object_label}</span>}
              <span className="mt-0.5 block text-xs text-h-muted">
                {formatLocalTs(n.created_at)}
              </span>
              <span className="mt-1 block text-sm">{n.excerpt}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

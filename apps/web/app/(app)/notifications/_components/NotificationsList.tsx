"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { notificationText } from "@/components/chrome/NotificationBell";
import { formatLocalTs } from "@/components/comments/format";
import { notificationsApi } from "@/lib/comments-fetch";
import type { NotificationOut } from "@/lib/comments-types";

const PAGE = 100;

export function NotificationsList() {
  const router = useRouter();
  const [rows, setRows] = useState<NotificationOut[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await notificationsApi.list({ unreadOnly, limit: PAGE });
      setRows(r.notifications);
      setUnread(r.unread_count);
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
    else await load();
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

      {error && <div className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
      {!rows && !error && <p className="text-sm text-h-muted">Loading…</p>}
      {rows && rows.length === 0 && (
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
              disabled={!n.url && !!n.read_at}
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

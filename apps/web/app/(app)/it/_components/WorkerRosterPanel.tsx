"use client";

import { useEffect, useState } from "react";

import {
  fetchUserList,
  patchUserShopWorker,
} from "@/lib/shop-floor-fetch";
import type { UserAdminOut } from "@/lib/shop-floor-types";

export function WorkerRosterPanel() {
  const [users, setUsers] = useState<UserAdminOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Set<number>>(new Set());

  async function refresh() {
    try {
      setError(null);
      const rows = await fetchUserList();
      setUsers(rows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function toggle(u: UserAdminOut) {
    const next = !u.is_shop_worker;
    setPending((prev) => new Set(prev).add(u.id));
    setUsers((prev) =>
      prev.map((row) =>
        row.id === u.id ? { ...row, is_shop_worker: next } : row,
      ),
    );
    try {
      await patchUserShopWorker(u.id, next);
    } catch (e) {
      setError((e as Error).message);
      // Revert optimistic update.
      setUsers((prev) =>
        prev.map((row) =>
          row.id === u.id ? { ...row, is_shop_worker: !next } : row,
        ),
      );
    } finally {
      setPending((prev) => {
        const n = new Set(prev);
        n.delete(u.id);
        return n;
      });
    }
  }

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <header className="mb-3">
        <h2 className="text-lg font-medium text-h-ink">Shop-worker roster</h2>
        <p className="text-sm text-h-muted">
          Toggle which workspace users appear in the shop-floor worker
          picker. Only admins can change these flags.
        </p>
      </header>

      {error && (
        <div className="mb-3 rounded border border-red-500 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-6 text-center text-sm text-h-muted">
          Loading users…
        </div>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-h-muted">
              <th className="pb-2 pr-3">Name</th>
              <th className="pb-2 pr-3">Email</th>
              <th className="pb-2 pr-3">Role</th>
              <th className="pb-2 pr-3">Active</th>
              <th className="pb-2 text-center">Shop worker</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-h-line">
                <td className="py-2 pr-3 text-h-ink">{u.full_name}</td>
                <td className="py-2 pr-3 text-h-muted">{u.email}</td>
                <td className="py-2 pr-3 font-mono text-xs text-h-muted">
                  {u.auth_role}
                </td>
                <td className="py-2 pr-3">
                  {u.is_active ? (
                    <span className="text-h-ink">yes</span>
                  ) : (
                    <span className="text-h-muted">no</span>
                  )}
                </td>
                <td className="py-2 text-center">
                  <input
                    type="checkbox"
                    checked={u.is_shop_worker}
                    disabled={pending.has(u.id) || !u.is_active}
                    onChange={() => toggle(u)}
                    className="h-4 w-4 cursor-pointer disabled:cursor-not-allowed"
                    aria-label={`Toggle shop worker for ${u.full_name}`}
                  />
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={5} className="py-4 text-center text-h-muted">
                  No users.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </section>
  );
}

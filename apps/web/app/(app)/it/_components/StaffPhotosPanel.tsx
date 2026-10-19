"use client";

import { useEffect, useState } from "react";
import { apiCall } from "@/lib/api";
import type { UserAdminOut } from "@/lib/shop-floor-types";

/** The small photo shown in front of a name in the PO staff list. Admin-only, like the rest of /it. */
export function StaffPhotosPanel() {
  const [users, setUsers] = useState<UserAdminOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Bumped after a change so the browser fetches the new picture instead of the cached one.
  const [version, setVersion] = useState(0);

  const load = () => apiCall<UserAdminOut[]>("/api/users").then(setUsers).catch(e => setError((e as Error).message));
  useEffect(() => { void load(); }, []);

  async function upload(u: UserAdminOut, file: File) {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch(`/api/users/${u.id}/photo`, { method: "PUT", body: fd }).catch(() => null);
    if (!r || !r.ok) { setError(r?.status === 415 ? "A photo must be a PNG or JPEG" : "Could not save the photo"); return; }
    setError(null); setVersion(v => v + 1); await load();
  }

  async function remove(u: UserAdminOut) {
    const r = await fetch(`/api/users/${u.id}/photo`, { method: "DELETE" }).catch(() => null);
    if (!r || !r.ok) { setError("Could not remove the photo"); return; }
    setError(null); setVersion(v => v + 1); await load();
  }

  return (
    <section data-testid="staff-photos" className="rounded-lg border border-h-line bg-h-surface p-4">
      <header className="mb-3">
        <h2 className="text-lg font-medium text-h-ink">Staff photos</h2>
        <p className="text-sm text-h-muted">A small PNG or JPEG shown in front of a name in the purchase order&apos;s staff list.</p>
      </header>
      {error && <div role="alert" className="mb-3 rounded border border-red-500 bg-red-50 p-3 text-sm text-red-900">{error}</div>}
      <table className="w-full border-collapse text-sm">
        <thead><tr className="text-left text-xs uppercase tracking-wide text-h-muted">
          <th className="pb-2 pr-3">Photo</th><th className="pb-2 pr-3">Name</th><th className="pb-2" /></tr></thead>
        <tbody>
          {users.filter(u => u.is_active).map(u => (
            <tr key={u.id} data-testid="staff-photo-row" className="border-t border-h-line">
              <td className="py-2 pr-3">
                {u.has_photo
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={`/api/purchase-orders/staff/${u.id}/photo?v=${version}`} alt="" className="h-8 w-8 rounded-full object-cover" />
                  : <span className="grid h-8 w-8 place-items-center rounded-full bg-h-bg text-xs text-h-muted">—</span>}
              </td>
              <td className="py-2 pr-3 text-h-ink">{u.full_name}</td>
              <td className="py-2 text-right">
                <label className="cursor-pointer rounded border border-h-line bg-h-bg px-2 py-1 text-xs text-h-ink hover:bg-h-surface">
                  {u.has_photo ? "Replace" : "Add photo"}
                  <input type="file" accept="image/png,image/jpeg" className="sr-only" aria-label={`Photo for ${u.full_name}`}
                    onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(u, f); }} />
                </label>
                {u.has_photo && <button data-testid={`staff-photo-remove-${u.id}`} type="button" onClick={() => void remove(u)} className="ml-2 text-xs text-h-muted underline hover:text-h-ink">Remove</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

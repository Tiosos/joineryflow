"use client";

import { useEffect, useState } from "react";

import { SECONDARY_TABS, TABS } from "@/components/chrome/TabStrip";
import { PermissionGroups } from "@/lib/permission-groups-fetch";
import { ALL_ACTIONS, ALL_MODULES, type GroupOut } from "@/lib/permission-groups-types";

/**
 * "View as role": a read-only picture of what each role may do, taken from the live system groups
 * (the engine's source of truth, not the shipped defaults). Per-object rules (uploader is not the
 * approver, locks, creator-or-manager) are not grants, so they are not shown here.
 */
export function ViewAsRolePanel() {
  const [groups, setGroups] = useState<GroupOut[] | null>(null);
  const [role, setRole] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    PermissionGroups.list()
      .then((all) => {
        const system = all.filter((g) => g.is_system);
        setGroups(system);
        setRole((cur) => cur || system[0]?.name || "");
      })
      .catch((e) => setError(String(e)));
  }, []);

  const group = groups?.find((g) => g.name === role) ?? null;
  const has = (module: string, action: string) =>
    group?.grants.some((g) => g.module === module && g.action === action) ?? false;
  const seen = (tabs: typeof TABS) => tabs.filter((t) => has(t.module, "read")).map((t) => t.label);

  return (
    <div className="rounded border border-h-line bg-h-surface p-4" data-testid="view-as-role">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-h-ink">View as role</h2>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          aria-label="Role"
          data-testid="view-as-role-select"
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
        >
          {(groups ?? []).map((g) => (
            <option key={g.group_id} value={g.name}>{g.name}</option>
          ))}
        </select>
      </div>
      <p className="mt-1 text-sm text-h-muted">
        What the system group of this role grants right now. Read only: change grants in Permission groups above.
      </p>
      {error && <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
      {group && (
        <>
          <div className="mt-3 grid gap-1 text-sm" data-testid="view-as-role-tabs">
            <div><span className="text-h-muted">Main tabs: </span>{seen(TABS).join(" · ") || "none"}</div>
            <div><span className="text-h-muted">Second row: </span>{[...new Set(seen(SECONDARY_TABS))].join(" · ") || "none"}</div>
            <div><span className="text-h-muted">IT page: </span>{has("it_management", "read") ? "yes (read)" : "no"}</div>
          </div>
          <div className="mt-3 overflow-x-auto rounded border border-h-line">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-h-muted">
                  <th className="border-b border-h-line px-3 py-2">Module</th>
                  {ALL_ACTIONS.map((a) => (
                    <th key={a} className="border-b border-h-line px-3 py-2 text-center">{a}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ALL_MODULES.map((m) => (
                  <tr key={m} className="border-b border-h-line last:border-b-0">
                    <td className="px-3 py-1.5 font-mono text-xs text-h-ink">{m}</td>
                    {ALL_ACTIONS.map((a) => (
                      <td
                        key={a}
                        data-testid={`view-as-role-${m}-${a}`}
                        className="px-3 py-1.5 text-center"
                        aria-label={`${m} ${a}: ${has(m, a) ? "yes" : "no"}`}
                      >
                        {has(m, a) ? "✔" : <span className="text-h-ink4">—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

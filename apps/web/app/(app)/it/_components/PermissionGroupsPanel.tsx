"use client";

import { useEffect, useMemo, useState } from "react";

import { PermissionGroups, ApiError } from "@/lib/permission-groups-fetch";
import {
  ALL_ACTIONS,
  ALL_MODULES,
  type GroupOut,
  type MembershipOut,
} from "@/lib/permission-groups-types";
import { fetchUserList } from "@/lib/shop-floor-fetch";
import type { UserAdminOut } from "@/lib/shop-floor-types";
import { PM } from "@/lib/pm-fetch";
import type { ProjectOut } from "@/lib/pm-types";

function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const body = e.body as { detail?: unknown } | undefined;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail && "code" in detail) {
      return String((detail as { code: unknown }).code);
    }
    return `Failed (${e.status})`;
  }
  return "Failed";
}

/** module -> Set of actions currently checked, for the grants grid. */
type GrantMap = Record<string, Set<string>>;

function grantsToMap(grants: { module: string; action: string }[]): GrantMap {
  const map: GrantMap = {};
  for (const m of ALL_MODULES) map[m] = new Set();
  for (const g of grants) {
    if (!map[g.module]) map[g.module] = new Set();
    map[g.module].add(g.action);
  }
  return map;
}

function mapsEqual(a: GrantMap, b: GrantMap): boolean {
  for (const m of ALL_MODULES) {
    const sa = a[m] ?? new Set();
    const sb = b[m] ?? new Set();
    if (sa.size !== sb.size) return false;
    for (const act of sa) if (!sb.has(act)) return false;
  }
  return true;
}

/**
 * RBAC-engine admin UI (Plan V1 §3.4, Q466–473) — the panel `/it` has never
 * had. `apps/api/app/permission_groups/` has served this API since
 * migration `0037`; IT could only configure access by calling it directly.
 */
export function PermissionGroupsPanel() {
  const [groups, setGroups] = useState<GroupOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [creating, setCreating] = useState(false);
  const [detailDirty, setDetailDirty] = useState(false);
  const [users, setUsers] = useState<UserAdminOut[]>([]);
  const [projects, setProjects] = useState<ProjectOut[]>([]);

  useEffect(() => {
    void fetchUserList().then(setUsers).catch(() => {});
    void PM.projects().then((r) => setProjects(r.projects)).catch(() => {});
  }, []);

  function selectGroup(id: number) {
    if (detailDirty && !window.confirm("Discard unsaved grant changes?")) return;
    setDetailDirty(false);
    setSelectedId(id);
  }

  async function refreshGroups(keepSelection = true) {
    try {
      setError(null);
      const rows = await PermissionGroups.list();
      setGroups(rows);
      if (!keepSelection || !rows.some((g) => g.group_id === selectedId)) {
        setSelectedId(rows[0]?.group_id ?? null);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshGroups(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createGroup() {
    const name = newGroupName.trim();
    if (!name) return;
    if (detailDirty && !window.confirm("Discard unsaved grant changes?")) return;
    setCreating(true);
    setError(null);
    try {
      const group = await PermissionGroups.create({ name });
      setNewGroupName("");
      setDetailDirty(false);
      await refreshGroups(false);
      setSelectedId(group.group_id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setCreating(false);
    }
  }

  const selected = groups.find((g) => g.group_id === selectedId) ?? null;

  return (
    <section className="rounded-lg border border-h-line bg-h-surface p-4">
      <header className="mb-3">
        <h2 className="text-lg font-medium text-h-ink">Permission groups</h2>
        <p className="text-sm text-h-muted">
          The Dynamic RBAC engine's groups, grants and memberships. The 7
          seeded system groups mirror the auth roles and cannot be deleted;
          add a custom group for anything narrower.
        </p>
      </header>

      {error && (
        <div className="mb-3 rounded border border-red-500 bg-red-50 p-3 text-sm text-red-900">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-6 text-center text-sm text-h-muted">Loading groups…</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-[240px_1fr]">
          <div>
            <ul className="divide-y divide-h-line rounded border border-h-line">
              {groups.map((g) => (
                <li key={g.group_id}>
                  <button
                    type="button"
                    onClick={() => selectGroup(g.group_id)}
                    className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-h-bg ${
                      g.group_id === selectedId ? "bg-h-bg font-medium text-h-ink" : "text-h-ink"
                    }`}
                  >
                    <span>{g.name}</span>
                    <span className="flex items-center gap-2 text-xs text-h-muted">
                      {g.is_system && (
                        <span className="rounded-full border border-h-line px-1.5 py-0.5">
                          system
                        </span>
                      )}
                      {g.grants.length}
                    </span>
                  </button>
                </li>
              ))}
              {groups.length === 0 && (
                <li className="px-3 py-4 text-center text-sm text-h-muted">No groups yet.</li>
              )}
            </ul>

            <div className="mt-3 flex gap-2">
              <input
                type="text"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && createGroup()}
                placeholder="New group name"
                className="w-full rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink focus:outline-none focus:ring-1 focus:ring-h-accent"
              />
              <button
                type="button"
                onClick={createGroup}
                disabled={creating || !newGroupName.trim()}
                className="rounded border border-h-line px-3 py-1 text-sm text-h-ink hover:bg-h-bg disabled:opacity-50"
              >
                {creating ? "…" : "Create"}
              </button>
            </div>
          </div>

          {selected ? (
            <GroupDetail
              group={selected}
              users={users}
              projects={projects}
              onChanged={() => void refreshGroups(true)}
              onDeleted={() => void refreshGroups(false)}
              onError={setError}
              onDirtyChange={setDetailDirty}
            />
          ) : (
            <div className="rounded border border-h-line p-6 text-center text-sm text-h-muted">
              Select a group to see its grants and members.
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function GroupDetail({
  group,
  users,
  projects,
  onChanged,
  onDeleted,
  onError,
  onDirtyChange,
}: {
  group: GroupOut;
  users: UserAdminOut[];
  projects: ProjectOut[];
  onChanged: () => void;
  onDeleted: () => void;
  onError: (msg: string) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const savedGrants = useMemo(() => grantsToMap(group.grants), [group]);
  const [grants, setGrants] = useState<GrantMap>(savedGrants);
  const [savingGrants, setSavingGrants] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Reset local edits whenever a different group is selected, or the server
  // copy changes underneath us (e.g. after Save). The parent guards the
  // selection change itself with a confirm when dirty (see selectGroup).
  useEffect(() => {
    setGrants(grantsToMap(group.grants));
  }, [group]);

  const dirty = !mapsEqual(grants, savedGrants);

  useEffect(() => {
    onDirtyChange(dirty);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty]);

  function toggle(mod: string, action: string) {
    setGrants((prev) => {
      const next: GrantMap = {};
      for (const m of ALL_MODULES) next[m] = new Set(prev[m]);
      const set = next[mod];
      if (set.has(action)) set.delete(action);
      else set.add(action);
      return next;
    });
  }

  async function saveGrants() {
    setSavingGrants(true);
    try {
      const flat = ALL_MODULES.flatMap((m) =>
        Array.from(grants[m] ?? []).map((action) => ({ module: m, action })),
      );
      await PermissionGroups.setGrants(group.group_id, { grants: flat });
      onChanged();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setSavingGrants(false);
    }
  }

  async function removeGroup() {
    if (!window.confirm(`Delete group "${group.name}"?`)) return;
    setDeleting(true);
    try {
      await PermissionGroups.remove(group.group_id);
      onDeleted();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-medium text-h-ink">
          {group.name}
          {group.is_system && (
            <span className="ml-2 rounded-full border border-h-line px-1.5 py-0.5 text-xs text-h-muted">
              system
            </span>
          )}
        </h3>
        {!group.is_system && (
          <button
            type="button"
            onClick={removeGroup}
            disabled={deleting}
            className="rounded border border-h-line px-2 py-1 text-xs text-h-bad hover:bg-h-bg disabled:opacity-50"
          >
            {deleting ? "…" : "Delete group"}
          </button>
        )}
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-sm font-medium text-h-ink">Grants</h4>
          <button
            type="button"
            onClick={saveGrants}
            disabled={!dirty || savingGrants}
            className="rounded bg-h-accent px-3 py-1 text-xs font-medium text-white disabled:opacity-40"
          >
            {savingGrants ? "Saving…" : "Save grants"}
          </button>
        </div>
        <div className="overflow-x-auto rounded border border-h-line">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-h-muted">
                <th className="border-b border-h-line px-3 py-2">Module</th>
                {ALL_ACTIONS.map((a) => (
                  <th key={a} className="border-b border-h-line px-3 py-2 text-center">
                    {a}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ALL_MODULES.map((m) => (
                <tr key={m} className="border-b border-h-line last:border-b-0">
                  <td className="px-3 py-1.5 font-mono text-xs text-h-ink">{m}</td>
                  {ALL_ACTIONS.map((a) => (
                    <td key={a} className="px-3 py-1.5 text-center">
                      <input
                        type="checkbox"
                        checked={grants[m]?.has(a) ?? false}
                        onChange={() => toggle(m, a)}
                        className="h-4 w-4 cursor-pointer"
                        aria-label={`${m} ${a}`}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <MembershipsPanel
        groupId={group.group_id}
        users={users}
        projects={projects}
        onError={onError}
      />
    </div>
  );
}

function MembershipsPanel({
  groupId,
  users,
  projects,
  onError,
}: {
  groupId: number;
  users: UserAdminOut[];
  projects: ProjectOut[];
  onError: (msg: string) => void;
}) {
  const [memberships, setMemberships] = useState<MembershipOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState("");
  const [selectedProject, setSelectedProject] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      setMemberships(await PermissionGroups.listMemberships(groupId));
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    PermissionGroups.listMemberships(groupId)
      .then((rows) => {
        if (!cancelled) setMemberships(rows);
      })
      .catch((e) => {
        if (!cancelled) onError(errorMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId]);

  async function addMembership() {
    if (!selectedUser) return;
    setAdding(true);
    try {
      await PermissionGroups.addMembership(groupId, {
        user_id: Number(selectedUser),
        project_id: selectedProject ? Number(selectedProject) : null,
      });
      setSelectedUser("");
      setSelectedProject("");
      await refresh();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setAdding(false);
    }
  }

  async function removeMembership(mid: number) {
    setRemovingId(mid);
    try {
      await PermissionGroups.removeMembership(mid);
      await refresh();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <div>
      <h4 className="mb-2 text-sm font-medium text-h-ink">Members</h4>
      {loading ? (
        <div className="py-3 text-center text-sm text-h-muted">Loading members…</div>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-h-muted">
              <th className="border-b border-h-line pb-1 pr-3">User</th>
              <th className="border-b border-h-line pb-1 pr-3">Scope</th>
              <th className="border-b border-h-line pb-1" />
            </tr>
          </thead>
          <tbody>
            {memberships.map((m) => (
              <tr key={m.membership_id} className="border-b border-h-line last:border-b-0">
                <td className="py-1.5 pr-3 text-h-ink">{m.user_full_name}</td>
                <td className="py-1.5 pr-3 text-h-muted">
                  {m.project_code ?? "workspace-wide"}
                </td>
                <td className="py-1.5 text-right">
                  <button
                    type="button"
                    onClick={() => removeMembership(m.membership_id)}
                    disabled={removingId === m.membership_id}
                    className="text-xs text-h-bad hover:underline disabled:opacity-50"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {memberships.length === 0 && (
              <tr>
                <td colSpan={3} className="py-3 text-center text-h-muted">
                  No members yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={selectedUser}
          onChange={(e) => setSelectedUser(e.target.value)}
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
        >
          <option value="">Add user…</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name}
            </option>
          ))}
        </select>
        <select
          value={selectedProject}
          onChange={(e) => setSelectedProject(e.target.value)}
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
        >
          <option value="">Workspace-wide</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.project_code}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={addMembership}
          disabled={adding || !selectedUser}
          className="rounded border border-h-line px-3 py-1 text-sm text-h-ink hover:bg-h-bg disabled:opacity-50"
        >
          {adding ? "…" : "Add"}
        </button>
      </div>
    </div>
  );
}

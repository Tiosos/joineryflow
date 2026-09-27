"use client";

import { useCallback, useEffect, useState } from "react";

import { qcApi } from "@/lib/qc-fetch";
import type { ChecklistItemOut, DefectOut, ReworkOut } from "@/lib/qc-types";

// Mirrors apps/api/app/auth/permissions.py's qc row: admin/manager/editor
// can write (raise a defect, add/toggle a checklist item, log rework);
// resolving a defect or closing rework is qc:approve — admin/manager only,
// same shape as shop_floor's drafter-is-downstream pattern.
const CAN_WRITE = new Set(["admin", "manager", "editor"]);
const CAN_APPROVE = new Set(["admin", "manager"]);

function formatTs(ts: string | null): string {
  if (!ts) return "—";
  return ts.replace("T", " ").slice(0, 16);
}

export function QcTab({
  itemId,
  currentUserRole,
}: {
  itemId: number;
  currentUserRole: string | null;
}) {
  const canWrite = CAN_WRITE.has(currentUserRole ?? "");
  const canApprove = CAN_APPROVE.has(currentUserRole ?? "");

  return (
    <div className="grid gap-6">
      <DefectsSection itemId={itemId} canWrite={canWrite} canApprove={canApprove} />
      <ChecklistSection itemId={itemId} canWrite={canWrite} />
      <ReworkSection itemId={itemId} canWrite={canWrite} canApprove={canApprove} />
    </div>
  );
}

// ============================================================================
// Defects
// ============================================================================

function DefectsSection({
  itemId,
  canWrite,
  canApprove,
}: {
  itemId: number;
  canWrite: boolean;
  canApprove: boolean;
}) {
  const [defects, setDefects] = useState<DefectOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await qcApi.listDefects(itemId);
      setDefects(rows);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load defects");
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function raiseDefect(e: React.FormEvent) {
    e.preventDefault();
    if (!description.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await qcApi.createDefect(itemId, description.trim());
      setDescription("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to raise defect");
    } finally {
      setBusy(false);
    }
  }

  async function resolve(d: DefectOut) {
    setError(null);
    try {
      await qcApi.resolveDefect(d.defect_id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resolve defect");
    }
  }

  const open = (defects ?? []).filter((d) => d.status === "open");
  const resolved = (defects ?? []).filter((d) => d.status === "resolved");

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-h-ink">Defects</h2>
      {error && <div className="mb-2 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

      {canWrite && (
        <form onSubmit={raiseDefect} className="mb-3 flex flex-wrap items-end gap-2">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the defect…"
            className="min-w-64 flex-1 rounded border border-h-line bg-white px-2 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !description.trim()}
            className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Raise
          </button>
        </form>
      )}

      {defects === null ? (
        <p className="text-sm text-h-muted">Loading…</p>
      ) : defects.length === 0 ? (
        <p className="text-sm text-h-muted">No defects raised on this item.</p>
      ) : (
        <ul className="grid gap-2">
          {[...open, ...resolved].map((d) => (
            <li
              key={d.defect_id}
              className="rounded border border-h-line bg-h-surface p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm text-h-ink">{d.description}</p>
                <span
                  className={
                    "shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide " +
                    (d.status === "open" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800")
                  }
                >
                  {d.status}
                </span>
              </div>
              <p className="mt-1 text-xs text-h-muted">
                {d.stage_key ? `${d.stage_key} · ` : ""}
                Raised by {d.created_by_name ?? "—"} · {formatTs(d.created_at)}
              </p>
              {d.status === "resolved" && (
                <p className="mt-1 text-xs text-h-muted">
                  Resolved by {d.resolved_by_name ?? "—"} · {formatTs(d.resolved_at)}
                  {d.resolved_note ? ` — ${d.resolved_note}` : ""}
                </p>
              )}
              {d.status === "open" && canApprove && (
                <button
                  type="button"
                  onClick={() => resolve(d)}
                  className="mt-2 rounded border border-h-line px-2 py-1 text-xs text-h-ink hover:bg-h-bg"
                >
                  Mark resolved
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ============================================================================
// Checklist
// ============================================================================

function ChecklistSection({ itemId, canWrite }: { itemId: number; canWrite: boolean }) {
  const [items, setItems] = useState<ChecklistItemOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await qcApi.listChecklist(itemId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load checklist");
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function addItem(e: React.FormEvent) {
    e.preventDefault();
    if (!label.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await qcApi.addChecklistItem(itemId, label.trim());
      setLabel("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add checklist item");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(row: ChecklistItemOut) {
    setError(null);
    try {
      await qcApi.toggleChecklistItem(row.checklist_item_id, !row.is_checked);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update checklist item");
    }
  }

  async function remove(row: ChecklistItemOut) {
    setError(null);
    try {
      await qcApi.removeChecklistItem(row.checklist_item_id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove checklist item");
    }
  }

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold text-h-ink">QC Checklist</h2>
      {error && <div className="mb-2 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

      {canWrite && (
        <form onSubmit={addItem} className="mb-3 flex flex-wrap items-end gap-2">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Doors align flush"
            className="min-w-64 flex-1 rounded border border-h-line bg-white px-2 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !label.trim()}
            className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Add
          </button>
        </form>
      )}

      {items === null ? (
        <p className="text-sm text-h-muted">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-h-muted">No checklist items yet.</p>
      ) : (
        <ul className="grid gap-1">
          {items.map((row) => (
            <li
              key={row.checklist_item_id}
              className="flex items-center gap-2 rounded border border-h-line bg-h-surface px-3 py-2"
            >
              <input
                type="checkbox"
                checked={row.is_checked}
                disabled={!canWrite}
                onChange={() => toggle(row)}
              />
              <span
                className={"flex-1 text-sm " + (row.is_checked ? "text-h-muted line-through" : "text-h-ink")}
              >
                {row.label}
              </span>
              {row.is_checked && (
                <span className="text-xs text-h-muted">
                  {row.checked_by_name ?? "—"} · {formatTs(row.checked_at)}
                </span>
              )}
              {canWrite && (
                <button
                  type="button"
                  onClick={() => remove(row)}
                  className="text-xs text-h-muted hover:text-h-ink"
                  aria-label="Remove"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ============================================================================
// Rework
// ============================================================================

function ReworkSection({
  itemId,
  canWrite,
  canApprove,
}: {
  itemId: number;
  canWrite: boolean;
  canApprove: boolean;
}) {
  const [rows, setRows] = useState<ReworkOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await qcApi.listRework(itemId));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load rework");
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function close(r: ReworkOut) {
    setError(null);
    try {
      await qcApi.closeRework(r.rework_id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to close rework");
    }
  }

  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-h-ink">Rework</h2>
        {canWrite && !adding && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="text-xs text-h-accent hover:underline"
          >
            + Log rework
          </button>
        )}
      </div>
      {error && <div className="mb-2 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}

      {adding && (
        <ReworkForm
          onCancel={() => setAdding(false)}
          onSubmit={async (body) => {
            await qcApi.createRework(itemId, body);
            setAdding(false);
            await load();
          }}
        />
      )}

      {rows === null ? (
        <p className="text-sm text-h-muted">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-h-muted">No rework logged on this item.</p>
      ) : (
        <ul className="grid gap-2">
          {rows.map((r) => (
            <li key={r.rework_id} className="rounded border border-h-line bg-h-surface p-3">
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-medium text-h-ink capitalize">{r.kind} rework</span>
                <span
                  className={
                    "shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide " +
                    (r.status === "open" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800")
                  }
                >
                  {r.status}
                </span>
              </div>
              <p className="mt-1 text-sm text-h-ink">
                <span className="text-h-muted">Cause:</span> {r.cause}
              </p>
              <p className="text-sm text-h-ink">
                <span className="text-h-muted">Scope:</span> {r.scope}
              </p>
              {(r.responsibility || r.cost) && (
                <p className="text-sm text-h-ink">
                  {r.responsibility && <span className="text-h-muted">Responsibility:</span>} {r.responsibility}
                  {r.responsibility && r.cost ? " · " : ""}
                  {r.cost && <span className="text-h-muted">Cost:</span>} {r.cost && `$${r.cost}`}
                </p>
              )}
              <p className="mt-1 text-xs text-h-muted">
                Logged by {r.created_by_name ?? "—"} · {formatTs(r.created_at)}
              </p>
              {r.status === "closed" && (
                <p className="mt-1 text-xs text-h-muted">
                  Closed by {r.closed_by_name ?? "—"} · {formatTs(r.closed_at)}
                  {r.closed_note ? ` — ${r.closed_note}` : ""}
                </p>
              )}
              {r.status === "open" && canApprove && (
                <button
                  type="button"
                  onClick={() => close(r)}
                  className="mt-2 rounded border border-h-line px-2 py-1 text-xs text-h-ink hover:bg-h-bg"
                >
                  Close
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ReworkForm({
  onCancel,
  onSubmit,
}: {
  onCancel: () => void;
  onSubmit: (body: {
    kind: string;
    cause: string;
    scope: string;
    responsibility?: string | null;
    cost?: string | null;
  }) => Promise<void>;
}) {
  const [kind, setKind] = useState<"internal" | "full">("internal");
  const [cause, setCause] = useState("");
  const [scope, setScope] = useState("");
  const [responsibility, setResponsibility] = useState("");
  const [cost, setCost] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!cause.trim() || !scope.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        kind,
        cause: cause.trim(),
        scope: scope.trim(),
        responsibility: responsibility.trim() || null,
        cost: cost.trim() || null,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to log rework");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mb-3 grid gap-2 rounded border border-h-line bg-white p-3">
      <div className="flex flex-wrap gap-2">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as "internal" | "full")}
          className="rounded border border-h-line px-2 py-1 text-sm"
        >
          <option value="internal">Internal Rework</option>
          <option value="full">Full Rework</option>
        </select>
        <input
          value={responsibility}
          onChange={(e) => setResponsibility(e.target.value)}
          placeholder="Responsibility (optional)"
          className="min-w-40 flex-1 rounded border border-h-line px-2 py-1 text-sm"
        />
        <input
          value={cost}
          onChange={(e) => setCost(e.target.value)}
          placeholder="Cost (optional)"
          className="w-32 rounded border border-h-line px-2 py-1 text-sm"
        />
      </div>
      <input
        value={cause}
        onChange={(e) => setCause(e.target.value)}
        placeholder="Cause *"
        className="rounded border border-h-line px-2 py-1 text-sm"
      />
      <input
        value={scope}
        onChange={(e) => setScope(e.target.value)}
        placeholder="Scope — what needs to be redone *"
        className="rounded border border-h-line px-2 py-1 text-sm"
      />
      {error && <p className="text-xs text-red-700">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy || !cause.trim() || !scope.trim()}
          className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Log
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-h-line px-3 py-1.5 text-sm text-h-ink"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

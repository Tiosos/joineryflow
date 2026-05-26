"use client";

import { useState } from "react";
import type { TeamMemberOut, WorkStatus } from "@/lib/pm-types";

interface Props {
  members: TeamMemberOut[];
}

const STATUS_LABEL: Record<WorkStatus, string> = {
  IN: "In",
  ON_SITE: "On site",
  SHOP: "Shop",
  WFH: "WFH",
  OFF: "Off",
};

const STATUS_COLOUR: Record<WorkStatus, string> = {
  IN: "#3f7d48",
  ON_SITE: "#3d6b8a",
  SHOP: "#c96442",
  WFH: "#c48a2e",
  OFF: "#8f8b80",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function avatarColour(seed: string): string {
  const palette = ["#3d6b8a", "#3f7d48", "#7a5193", "#b4443d", "#c48a2e", "#6f7a51", "#8f8b80", "#c96442"];
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}

export function TeamCard({ members }: Props) {
  const [editorOpen, setEditorOpen] = useState(false);
  const [statusList, setStatusList] = useState(members);

  function applyUpdate(updated: TeamMemberOut) {
    setStatusList((prev) =>
      prev.map((m) => (m.id === updated.id ? { ...updated, is_self: m.is_self } : m)),
    );
  }

  const liveMe = statusList.find((m) => m.is_self) ?? null;
  const liveOthers = statusList.filter((m) => !m.is_self);

  return (
    <section className="rounded-lg border border-h-line bg-h-surface">
      <header className="flex items-center gap-3 border-b border-h-line px-4 py-3">
        <h2 className="text-sm font-semibold text-h-ink">Team</h2>
        <span className="rounded-full bg-h-bg px-2 py-0.5 text-[10px] text-h-muted">
          Today · {members.length}
        </span>
      </header>

      {liveMe ? (
        <div className="flex items-center gap-3 border-b border-h-line bg-h-accent/5 px-4 py-3">
          <Avatar
            name={liveMe.full_name}
            workStatus={liveMe.work_status}
            colour={avatarColour(liveMe.full_name)}
            size={36}
          />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-h-ink">
              You · {liveMe.full_name}
            </div>
            <div className="text-xs text-h-muted">
              {liveMe.work_status ? (
                <>
                  <span
                    className="font-semibold"
                    style={{ color: STATUS_COLOUR[liveMe.work_status] }}
                  >
                    {STATUS_LABEL[liveMe.work_status]}
                  </span>
                  {liveMe.location_label ? <> · {liveMe.location_label}</> : null}
                </>
              ) : (
                <span className="italic">No status set</span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setEditorOpen(true)}
            className="rounded border border-h-line bg-h-surface px-3 py-1 text-xs text-h-ink hover:bg-h-bg"
          >
            ✎ Update status
          </button>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-0 sm:grid-cols-4 lg:grid-cols-6">
        {liveOthers.map((m) => (
          <div
            key={m.id}
            className="flex flex-col items-center gap-1 border-b border-r border-h-line p-3 text-center"
          >
            <Avatar
              name={m.full_name}
              workStatus={m.work_status}
              colour={avatarColour(m.full_name)}
              size={32}
            />
            <div className="truncate text-xs font-medium text-h-ink" title={m.full_name}>
              {m.full_name.split(/\s+/)[0]}
            </div>
            <div
              className="text-[10px] font-semibold"
              style={{ color: m.work_status ? STATUS_COLOUR[m.work_status] : "#8f8b80" }}
            >
              {m.work_status ? STATUS_LABEL[m.work_status] : "—"}
            </div>
            <div className="truncate text-[10px] text-h-muted" title={m.location_label ?? ""}>
              {m.location_label ?? ""}
            </div>
          </div>
        ))}
      </div>

      {editorOpen && liveMe ? (
        <StatusEditor
          current={liveMe}
          onClose={() => setEditorOpen(false)}
          onSaved={(updated) => {
            applyUpdate(updated);
            setEditorOpen(false);
          }}
        />
      ) : null}
    </section>
  );
}

function Avatar({
  name,
  workStatus,
  colour,
  size,
}: {
  name: string;
  workStatus: WorkStatus | null;
  colour: string;
  size: number;
}) {
  const dotColour = workStatus ? STATUS_COLOUR[workStatus] : "#c1beb4";
  const dotSize = Math.round(size * 0.32);
  return (
    <div
      className="relative inline-flex items-center justify-center rounded-full font-semibold text-white"
      style={{ background: colour, width: size, height: size, fontSize: Math.round(size * 0.4) }}
      title={name}
    >
      {initials(name)}
      <span
        className="absolute rounded-full border-2 border-h-surface"
        style={{
          background: dotColour,
          width: dotSize,
          height: dotSize,
          right: -2,
          bottom: -2,
        }}
        aria-label={workStatus ? STATUS_LABEL[workStatus] : "no status"}
      />
    </div>
  );
}

function StatusEditor({
  current,
  onClose,
  onSaved,
}: {
  current: TeamMemberOut;
  onClose: () => void;
  onSaved: (m: TeamMemberOut) => void;
}) {
  const [pick, setPick] = useState<WorkStatus | "">(current.work_status ?? "");
  const [loc, setLoc] = useState(current.location_label ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSubmitting(true);
    setError(null);
    try {
      const r = await fetch("/api/me/status", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          work_status: pick === "" ? null : pick,
          location_label: loc.trim() === "" ? null : loc.trim(),
        }),
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as TeamMemberOut;
      onSaved({ ...data, is_self: true });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setSubmitting(false);
    }
  }

  const OPTIONS: WorkStatus[] = ["IN", "ON_SITE", "SHOP", "WFH", "OFF"];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md overflow-hidden rounded-lg border border-h-line bg-h-surface shadow-xl">
        <header className="border-b border-h-line bg-h-bg px-5 py-3">
          <div className="text-sm font-semibold text-h-ink">Update my status</div>
          <div className="text-[11px] text-h-muted">{current.full_name}</div>
        </header>
        <div className="grid gap-3 p-5">
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-h-muted">
              Status
            </div>
            <div className="grid grid-cols-5 gap-1">
              {OPTIONS.map((o) => (
                <button
                  key={o}
                  type="button"
                  onClick={() => setPick(o)}
                  className={`rounded border px-2 py-2 text-xs font-medium transition ${
                    pick === o
                      ? "border-h-accent bg-h-accent text-white"
                      : "border-h-line text-h-ink hover:bg-h-bg"
                  }`}
                >
                  {STATUS_LABEL[o]}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setPick("")}
              className="mt-1 text-[10px] text-h-muted hover:text-h-ink"
            >
              Clear
            </button>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-h-muted">
              Location / what you're doing
            </label>
            <input
              type="text"
              value={loc}
              onChange={(e) => setLoc(e.target.value)}
              placeholder="e.g. Office · Drafting"
              className="w-full rounded border border-h-line bg-h-surface px-2 py-1.5 text-sm text-h-ink"
            />
          </div>
          {error ? <div className="text-xs text-[#b4443d]">{error}</div> : null}
        </div>
        <footer className="flex justify-end gap-2 border-t border-h-line bg-h-bg px-4 py-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-h-line bg-h-surface px-3 py-1 text-sm text-h-ink hover:bg-h-bg"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={save}
            className="rounded bg-h-accent px-3 py-1 text-sm text-white hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </footer>
      </div>
    </div>
  );
}

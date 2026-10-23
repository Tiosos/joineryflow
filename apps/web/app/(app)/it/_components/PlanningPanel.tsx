"use client";

import { useCallback, useEffect, useState } from "react";

export function PlanningPanel() {
  const [days, setDays] = useState("3");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/workspace/planning");
      if (!r.ok) {
        setError(`Load failed (${r.status})`);
        return;
      }
      setDays(String(((await r.json()) as { at_risk_days: number }).at_risk_days));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const r = await fetch("/api/workspace/planning", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ at_risk_days: Number(days) }),
      });
      if (!r.ok) {
        setError(r.status === 422 ? "Enter a whole number of days from 0 to 90." : `Save failed (${r.status})`);
        return;
      }
      setDays(String(((await r.json()) as { at_risk_days: number }).at_risk_days));
      setSavedAt(new Date().toLocaleTimeString());
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded border border-h-line bg-h-surface p-4">
      <h2 className="text-lg font-semibold text-h-ink">Planning</h2>
      <p className="mt-1 text-sm text-h-muted">
        A stage is <strong>at risk</strong> when it is due within this many days and an earlier stage of the item is
        not done. Overdue and Delayed do not depend on it.
      </p>
      {loading ? (
        <p className="mt-3 text-sm text-h-muted">Loading…</p>
      ) : (
        <>
          <label className="mt-3 flex max-w-[12rem] flex-col text-xs">
            <span className="font-medium uppercase tracking-wide text-h-muted">At risk window (days)</span>
            <input
              type="number"
              min={0}
              max={90}
              step={1}
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="mt-1 rounded border border-h-line bg-white px-2 py-1 font-mono text-sm"
              data-testid="at-risk-days"
            />
          </label>
          {error ? (
            <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
          ) : null}
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
              data-testid="save-planning-btn"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            {savedAt ? <span className="text-xs text-h-muted">Saved at {savedAt}</span> : null}
          </div>
        </>
      )}
    </div>
  );
}

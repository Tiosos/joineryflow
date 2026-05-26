"use client";

import { useCallback, useEffect, useState } from "react";

import type { LabourRate, StageKey } from "@/lib/estimating-types";

const STAGE_KEYS: StageKey[] = [
  "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED",
  "PAINTED", "MADE", "DEL", "INST",
];

export function LabourRatesPanel() {
  const [rates, setRates] = useState<Record<StageKey, string>>(() =>
    Object.fromEntries(STAGE_KEYS.map((sk) => [sk, "0"])) as Record<StageKey, string>,
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/it/labour-rates");
      if (!r.ok) {
        setError(`Load failed (${r.status})`);
        return;
      }
      const rows = (await r.json()) as LabourRate[];
      setRates((cur) => {
        const next: Record<StageKey, string> = { ...cur };
        for (const row of rows) next[row.stage_key] = row.hourly_rate;
        return next;
      });
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
      const r = await fetch("/api/it/labour-rates", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rates: STAGE_KEYS.map((sk) => ({
            stage_key: sk,
            hourly_rate: rates[sk] || "0",
          })),
        }),
      });
      if (!r.ok) {
        setError(`Save failed (${r.status})`);
        return;
      }
      const fresh = (await r.json()) as LabourRate[];
      setRates((cur) => {
        const next: Record<StageKey, string> = { ...cur };
        for (const row of fresh) next[row.stage_key] = row.hourly_rate;
        return next;
      });
      setSavedAt(new Date().toLocaleTimeString());
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded border border-h-line bg-h-surface p-4">
      <h2 className="text-lg font-semibold text-h-ink">Labour rates</h2>
      <p className="mt-1 text-sm text-h-muted">
        Hourly rate per lifecycle stage. Used for estimating labour cost roll-up.
      </p>
      {loading ? (
        <p className="mt-3 text-sm text-h-muted">Loading…</p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-5">
            {STAGE_KEYS.map((sk) => (
              <label key={sk} className="flex flex-col text-xs">
                <span className="font-medium uppercase tracking-wide text-h-muted">
                  {sk}
                </span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  value={rates[sk]}
                  onChange={(e) =>
                    setRates((cur) => ({ ...cur, [sk]: e.target.value }))
                  }
                  className="mt-1 rounded border border-h-line bg-white px-2 py-1 font-mono text-sm"
                  data-testid={`labour-rate-${sk}`}
                />
              </label>
            ))}
          </div>
          {error ? (
            <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </div>
          ) : null}
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="rounded bg-h-accent px-3 py-1.5 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
              data-testid="save-rates-btn"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            {savedAt ? (
              <span className="text-xs text-h-muted">Saved at {savedAt}</span>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}

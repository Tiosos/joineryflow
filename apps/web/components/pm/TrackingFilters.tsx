"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const STATUS_OPTIONS = ["", "CLEAR", "VOID", "NOTE!", "LIVE", "APPROVED", "HOLD"] as const;
const STAGE_OPTIONS = [
  "", "REQ", "SM", "LISTED", "DOWN", "CNC", "EDGED", "PAINTED", "MADE", "DEL", "INST",
] as const;

export function TrackingFilters() {
  const router = useRouter();
  const params = useSearchParams();

  const [status, setStatus] = useState(params.get("status") ?? "");
  const [stage, setStage] = useState(params.get("stage") ?? "");
  const [query, setQuery] = useState(params.get("q") ?? "");

  // Track whether this is the first mount so the debounce doesn't fire
  // immediately on mount (which would cancel any concurrent navigation).
  const hasMounted = useRef(false);

  function pushParams(updates: Record<string, string>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    router.push(`?${next.toString()}`);
  }

  // Debounce free-text search — skip on initial mount to avoid pushing
  // the same URL that was just loaded (which would cancel any concurrent
  // navigation away from this page).
  useEffect(() => {
    if (!hasMounted.current) {
      hasMounted.current = true;
      return;
    }
    const t = setTimeout(() => pushParams({ q: query }), 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-h-line bg-h-surface p-3">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-h-muted">Status</span>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            pushParams({ status: e.target.value });
          }}
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s || "All"}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 text-sm">
        <span className="text-h-muted">Stage</span>
        <select
          value={stage}
          onChange={(e) => {
            setStage(e.target.value);
            pushParams({ stage: e.target.value });
          }}
          className="rounded border border-h-line bg-h-bg px-2 py-1 text-h-ink"
        >
          {STAGE_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s || "All"}
            </option>
          ))}
        </select>
      </label>

      <input
        type="search"
        placeholder="Search code or description..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="min-w-[200px] flex-1 rounded border border-h-line bg-h-bg px-2 py-1 text-sm text-h-ink"
      />
    </div>
  );
}

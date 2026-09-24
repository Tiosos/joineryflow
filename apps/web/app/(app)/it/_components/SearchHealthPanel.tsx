"use client";

import { useCallback, useEffect, useState } from "react";

import type { SearchHealth } from "@/lib/search-types";

/** Global Search status (sub-project #11): is Meilisearch up, and how far
 *  behind is the index? A growing outbox with an old head means the
 *  search-worker is stuck or down. */
export function SearchHealthPanel() {
  const [health, setHealth] = useState<SearchHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const r = await fetch("/api/search/health");
    if (!r.ok) {
      setError(`Load failed (${r.status})`);
      return;
    }
    setHealth((await r.json()) as SearchHealth);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="rounded border border-h-line bg-h-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-h-ink">Search</h2>
        <button type="button" onClick={load} className="text-xs text-h-accent">
          Refresh
        </button>
      </div>
      <p className="mt-1 text-sm text-h-muted">
        Meilisearch status and the queue of changes waiting to be indexed.
      </p>
      {error && (
        <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      )}
      {health && (
        <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wide text-h-muted">Index</dt>
            <dd className={health.meili === "ok" ? "text-h-ink" : "text-red-800"}>
              {health.meili === "ok" ? "Available" : "Down"}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-h-muted">Waiting</dt>
            <dd className="h-mono text-h-ink">{health.outbox_depth}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-h-muted">Oldest</dt>
            <dd className="h-mono text-h-ink">
              {health.oldest_enqueued_at
                ? new Date(health.oldest_enqueued_at).toLocaleString()
                : "—"}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}

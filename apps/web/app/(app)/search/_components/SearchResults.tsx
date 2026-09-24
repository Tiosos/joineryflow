"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { search, SearchUnavailableError } from "@/lib/search-fetch";
import {
  TYPE_LABELS,
  type SearchResponse,
  type SearchType,
} from "@/lib/search-types";

const PAGE = 20;

function isType(t: string | null): t is SearchType {
  return t != null && t in TYPE_LABELS;
}

export function SearchResults(props: {
  initialQ: string;
  initialType: string | null;
  initialArchived: boolean;
}) {
  const router = useRouter();
  const [q, setQ] = useState(props.initialQ);
  const [type, setType] = useState<SearchType | null>(
    isType(props.initialType) ? props.initialType : null,
  );
  const [archived, setArchived] = useState(props.initialArchived);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Keep the URL in step so a results view is shareable and reloadable.
  useEffect(() => {
    const qs = new URLSearchParams();
    if (q.trim()) qs.set("q", q.trim());
    if (type) qs.set("type", type);
    if (archived) qs.set("include_archived", "true");
    router.replace(`/search?${qs}`, { scroll: false });
  }, [q, type, archived, router]);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setData(null);
      return;
    }
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      try {
        setData(await search({
          q: term,
          types: type ? [type] : undefined,
          includeArchived: archived,
          limit: PAGE,
          offset,
          signal: ctl.signal,
        }));
        setError(null);
      } catch (e) {
        if (ctl.signal.aborted) return;
        setData(null);
        setError(e instanceof SearchUnavailableError
          ? "Search is temporarily unavailable. The per-page filters still work."
          : "Search failed.");
      }
    }, 200);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [q, type, archived, offset]);

  const counts = data?.type_counts ?? {};
  const allCount = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0);

  function chip(label: string, value: SearchType | null, n: number) {
    const on = type === value;
    return (
      <button
        key={label}
        type="button"
        onClick={() => {
          setType(value);
          setOffset(0);
        }}
        className={`rounded-full border px-3 py-1 text-xs ${
          on ? "border-h-accent bg-h-accent text-white" : "border-h-line text-h-ink hover:bg-h-bg"
        }`}
      >
        {label} <span className={on ? "" : "text-h-muted"}>{n}</span>
      </button>
    );
  }

  return (
    <section className="grid gap-4">
      <header className="grid gap-3">
        <h1 className="text-2xl font-semibold text-h-ink">Search</h1>
        <input
          type="search"
          autoFocus
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
          placeholder="Number, code, name or description"
          aria-label="Search query"
          className="w-full max-w-xl rounded border border-h-line bg-h-surface px-3 py-2 text-sm text-h-ink"
        />
        <div className="flex flex-wrap items-center gap-2">
          {chip("All", null, allCount)}
          {(Object.keys(TYPE_LABELS) as SearchType[])
            .filter((t) => counts[t])
            .map((t) => chip(TYPE_LABELS[t], t, counts[t] ?? 0))}
          <label className="ml-2 flex items-center gap-1 text-xs text-h-muted">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => {
                setArchived(e.target.checked);
                setOffset(0);
              }}
            />
            Include archived
          </label>
        </div>
      </header>

      {error && <p className="rounded bg-h-surface px-3 py-2 text-sm text-h-muted">{error}</p>}
      {data && data.hits.length === 0 && (
        <p className="text-sm text-h-muted">No matches for “{q.trim()}”.</p>
      )}

      {data && data.hits.length > 0 && (
        <ul className="divide-y divide-h-line rounded border border-h-line bg-h-surface">
          {data.hits.map((h) => {
            const body = (
              <>
                <div className="flex items-baseline gap-2">
                  <span className="text-[11px] uppercase tracking-wide text-h-muted">
                    {TYPE_LABELS[h.type]}
                  </span>
                  {h.codes[0] && <span className="h-mono text-xs text-h-muted">{h.codes[0]}</span>}
                  <span className="text-sm font-medium text-h-ink">{h.title}</span>
                  {h.archived && (
                    <span className="rounded bg-h-bg px-1.5 text-[11px] text-h-muted">archived</span>
                  )}
                  {h.status && <span className="ml-auto text-xs text-h-muted">{h.status}</span>}
                </div>
                {h.subtitle && <div className="text-xs text-h-muted">{h.subtitle}</div>}
              </>
            );
            return (
              <li key={`${h.type}-${h.entity_id}`}>
                {h.url ? (
                  <Link href={h.url} className="block px-4 py-2 hover:bg-h-bg">{body}</Link>
                ) : (
                  <div className="px-4 py-2">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {data && data.total > PAGE && (
        <div className="flex items-center gap-3 text-sm">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
            className="rounded border border-h-line px-3 py-1 disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-h-muted">
            {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
          </span>
          <button
            type="button"
            disabled={offset + PAGE >= data.total}
            onClick={() => setOffset(offset + PAGE)}
            className="rounded border border-h-line px-3 py-1 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </section>
  );
}

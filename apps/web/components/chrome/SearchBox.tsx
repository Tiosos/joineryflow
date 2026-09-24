"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { search, SearchUnavailableError } from "@/lib/search-fetch";
import { TYPE_LABELS, type SearchHit } from "@/lib/search-types";

const DEBOUNCE_MS = 200;
const DROPDOWN_LIMIT = 8;

/** Top-bar global search (sub-project #11). `/` focuses it from anywhere
 *  that is not already a text field; Enter opens the highlighted hit, or the
 *  full results page when nothing is highlighted. */
export function SearchBox() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      e.preventDefault();
      inputRef.current?.focus();
    }
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, []);

  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setHits([]);
      setError(null);
      return;
    }
    const ctl = new AbortController();
    const t = setTimeout(async () => {
      try {
        const r = await search({ q: term, limit: DROPDOWN_LIMIT, signal: ctl.signal });
        setHits(r.hits);
        setError(null);
        setActive(-1);
      } catch (e) {
        if (ctl.signal.aborted) return;
        setHits([]);
        setError(e instanceof SearchUnavailableError
          ? "Search is temporarily unavailable."
          : "Search failed.");
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [q]);

  // Group in hit order, keeping each hit's flat index for keyboard nav.
  const groups = useMemo(() => {
    const out: { type: SearchHit["type"]; items: { hit: SearchHit; i: number }[] }[] = [];
    hits.forEach((hit, i) => {
      let g = out.find((x) => x.type === hit.type);
      if (!g) out.push((g = { type: hit.type, items: [] }));
      g.items.push({ hit, i });
    });
    return out;
  }, [hits]);

  function go(hit: SearchHit | undefined) {
    if (!hit?.url) return;
    setOpen(false);
    router.push(hit.url);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0) return go(hits[active]);
      const term = q.trim();
      if (term) {
        setOpen(false);
        router.push(`/search?q=${encodeURIComponent(term)}`);
      }
    }
  }

  const showDropdown = open && q.trim() !== "";

  return (
    <div ref={boxRef} className="relative w-80">
      <input
        ref={inputRef}
        type="search"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder="Search  ( / )"
        aria-label="Search"
        className="w-full rounded border border-h-line bg-h-bg px-3 py-1.5 text-sm text-h-ink placeholder:text-h-muted focus:outline-none focus:ring-1 focus:ring-h-accent"
      />
      {showDropdown && (
        <div
          role="listbox"
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[70vh] overflow-y-auto rounded border border-h-line bg-h-surface shadow-lg"
        >
          {error && <p className="px-3 py-2 text-sm text-h-muted">{error}</p>}
          {!error && hits.length === 0 && (
            <p className="px-3 py-2 text-sm text-h-muted">No matches.</p>
          )}
          {groups.map((g) => (
            <div key={g.type}>
              <div className="px-3 pt-2 text-[11px] font-medium uppercase tracking-wide text-h-muted">
                {TYPE_LABELS[g.type]}
              </div>
              {g.items.map(({ hit, i }) => (
                <button
                  key={`${hit.type}-${hit.entity_id}`}
                  type="button"
                  role="option"
                  aria-selected={i === active}
                  disabled={!hit.url}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(hit)}
                  className={`block w-full px-3 py-1.5 text-left disabled:cursor-default ${
                    i === active ? "bg-h-bg" : ""
                  }`}
                >
                  <div className="flex items-baseline gap-2">
                    {hit.codes[0] && (
                      <span className="h-mono text-xs text-h-muted">{hit.codes[0]}</span>
                    )}
                    <span className="truncate text-sm text-h-ink">{hit.title}</span>
                  </div>
                  {hit.subtitle && (
                    <div className="truncate text-xs text-h-muted">{hit.subtitle}</div>
                  )}
                </button>
              ))}
            </div>
          ))}
          {hits.length > 0 && (
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                router.push(`/search?q=${encodeURIComponent(q.trim())}`);
              }}
              className="block w-full border-t border-h-line px-3 py-2 text-left text-xs text-h-accent"
            >
              All results for “{q.trim()}” →
            </button>
          )}
        </div>
      )}
    </div>
  );
}

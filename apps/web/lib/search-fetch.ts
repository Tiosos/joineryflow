import type { SearchResponse, SearchType } from "./search-types";

/** Thrown when the API answers 503 SEARCH_UNAVAILABLE. */
export class SearchUnavailableError extends Error {}

export async function search(p: {
  q: string;
  types?: SearchType[];
  includeArchived?: boolean;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
}): Promise<SearchResponse> {
  const qs = new URLSearchParams({ q: p.q });
  if (p.types?.length) qs.set("types", p.types.join(","));
  if (p.includeArchived) qs.set("include_archived", "true");
  if (p.limit != null) qs.set("limit", String(p.limit));
  if (p.offset) qs.set("offset", String(p.offset));
  const r = await fetch(`/api/search?${qs}`, { signal: p.signal });
  if (r.status === 503) throw new SearchUnavailableError();
  if (!r.ok) throw new Error(`search failed: ${r.status}`);
  return r.json();
}

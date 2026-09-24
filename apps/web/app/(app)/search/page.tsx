import { SearchResults } from "./_components/SearchResults";

interface SearchParams {
  q?: string;
  type?: string;
  include_archived?: string;
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const sp = await searchParams;
  return (
    <SearchResults
      initialQ={sp.q ?? ""}
      initialType={sp.type ?? null}
      initialArchived={sp.include_archived === "true"}
    />
  );
}

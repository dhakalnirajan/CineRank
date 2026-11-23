import { useQuery } from "@tanstack/react-query";
import { Search, SearchX } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { PosterGridSkeleton } from "../components/feedback/Skeletons";
import { PosterGrid } from "../components/media/PosterGrid";
import { PageHeader } from "../components/ui/PageHeader";
import { useAuth } from "../features/auth/AuthProvider";
import { GENRES } from "../features/catalogue/genres";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function SearchPage() {
  useDocumentTitle("Search");
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const [input, setInput] = useState(query);
  const debounced = useDebouncedValue(input, 350);

  useEffect(() => {
    setInput(query);
  }, [query]);

  useEffect(() => {
    const trimmed = debounced.trim();
    if (trimmed === query) {
      return;
    }
    const params = new URLSearchParams(searchParams);
    if (trimmed) {
      params.set("q", trimmed);
    } else {
      params.delete("q");
    }
    setSearchParams(params, { replace: true });
  }, [debounced, query, searchParams, setSearchParams]);

  const results = useQuery({
    queryKey: queryKeys.search(query),
    queryFn: ({ signal }) => api.search(query, 24, signal),
    enabled: query.length > 0,
  });

  const facets = useQuery({
    queryKey: queryKeys.facets,
    queryFn: ({ signal }) => api.catalogueFacets(signal),
    staleTime: 5 * 60_000,
    enabled: query.length === 0,
  });

  const personalized = useQuery({
    queryKey: queryKeys.home(user?.id ?? 0, 12),
    queryFn: ({ signal }) => api.home(user?.id ?? 0, 12, signal),
    staleTime: 60_000,
    enabled: Boolean(user) && query.length === 0,
  });
  const preview = useQuery({
    queryKey: queryKeys.cataloguePreview,
    queryFn: ({ signal }) => api.listMovies({ limit: 12 }, signal),
    staleTime: 60_000,
    enabled: !user && query.length === 0,
  });

  const genres = Array.isArray(facets.data?.genres) && facets.data.genres.length > 0
    ? facets.data.genres.slice(0, 8).map((entry) => entry.value)
    : [...GENRES.slice(0, 8)];
  const suggestions = user ? (personalized.data?.for_you ?? []) : (preview.data?.items ?? []);
  const suggestionsLoading = user ? personalized.isLoading : preview.isLoading;
  const suggestionsError = user ? personalized.isError : preview.isError;

  return (
    <div className="page-shell py-12">
      <PageHeader title="Find something to watch" />

      <div className="relative mb-10 max-w-3xl">
        <Search
          className="pointer-events-none absolute left-5 top-1/2 size-5 -translate-y-1/2 text-white/40"
          aria-hidden="true"
        />
        <input
          type="search"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Search by title"
          aria-label="Search films and series by title"
          autoComplete="off"
          enterKeyHint="search"
          className="h-16 w-full rounded-none border border-line-strong bg-[#161616] pl-14 pr-5 text-lg text-white placeholder:text-white/40 transition-colors hover:border-white focus:border-white"
        />
      </div>

      {query.length === 0 ? (
        <div className="space-y-10">
          <section aria-labelledby="discover-genres">
            <h2 id="discover-genres" className="type-rail-title text-white">
              Start with a genre
            </h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {genres.map((genre) => (
                <Link
                  key={genre}
                  to={`/explore?genre=${encodeURIComponent(genre)}`}
                  className="border border-white/15 bg-white/[0.02] px-3 py-1.5 text-xs font-medium text-white/65 transition-colors hover:border-white/40 hover:text-white"
                >
                  {genre}
                </Link>
              ))}
            </div>
          </section>

          <section aria-labelledby="discover-suggestions">
            <h2 id="discover-suggestions" className="type-rail-title text-white">
              {user ? "Picked for you" : "Worth a look"}
            </h2>
            {suggestionsLoading ? <PosterGridSkeleton count={10} /> : null}
            {suggestionsError ? (
              <p className="mt-4 text-sm text-white/50">
                Suggestions are unavailable right now. Try a search instead.
              </p>
            ) : null}
            {suggestions.length > 0 ? (
              <div className="mt-5">
                <PosterGrid items={suggestions} />
              </div>
            ) : null}
          </section>
        </div>
      ) : null}

      {query.length > 0 && results.isLoading ? <PosterGridSkeleton count={10} /> : null}

      {query.length > 0 && results.isError ? (
        <ErrorState
          title="We couldn't search right now"
          message={
            isApiError(results.error) ? results.error.message : "Please try again in a moment."
          }
          onRetry={() => void results.refetch()}
        />
      ) : null}

      {results.data && results.data.count === 0 ? (
        <EmptyState
          icon={SearchX}
          title={`No results for "${results.data.query}"`}
          message="Check the spelling or try a shorter title."
        />
      ) : null}

      {results.data && results.data.count > 0 ? (
        <div>
          <p className="meta-numeric mb-6 text-sm text-white/60">
            {results.data.count} {results.data.count === 1 ? "result" : "results"} for{" "}
            <span className="text-white">"{results.data.query}"</span>
          </p>
          <PosterGrid items={results.data.results} />
        </div>
      ) : null}
    </div>
  );
}

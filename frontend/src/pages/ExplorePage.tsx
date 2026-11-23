import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Compass } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { PosterGridSkeleton } from "../components/feedback/Skeletons";
import { PosterGrid } from "../components/media/PosterGrid";
import { Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { GENRES } from "../features/catalogue/genres";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { cn } from "../utils/cn";
import { uniqueByTitleId } from "../utils/collections";

type MediaFilter = "movie" | "tv" | null;

const PAGE_SIZE = 50;

export default function ExplorePage() {
  useDocumentTitle("Explore");
  const [searchParams, setSearchParams] = useSearchParams();
  const [resetKey, setResetKey] = useState(0);
  const [conflict, setConflict] = useState(false);

  const rawMedia = searchParams.get("media_type");
  const mediaType: MediaFilter = rawMedia === "movie" || rawMedia === "tv" ? rawMedia : null;
  const genre = searchParams.get("genre");

  const facets = useQuery({
    queryKey: queryKeys.facets,
    queryFn: ({ signal }) => api.catalogueFacets(signal),
    staleTime: 5 * 60_000,
  });

  const query = useInfiniteQuery({
    queryKey: queryKeys.catalogue({ mediaType, genre }, resetKey),
    queryFn: ({ pageParam, signal }) =>
      api.listMovies(
        { limit: PAGE_SIZE, cursor: pageParam, genre, mediaType },
        signal,
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const updateFilter = (next: { mediaType?: MediaFilter; genre?: string | null }) => {
    const params = new URLSearchParams(searchParams);
    if (next.mediaType !== undefined) {
      if (next.mediaType) {
        params.set("media_type", next.mediaType);
      } else {
        params.delete("media_type");
      }
    }
    if (next.genre !== undefined) {
      if (next.genre) {
        params.set("genre", next.genre);
      } else {
        params.delete("genre");
      }
    }
    setSearchParams(params, { replace: true });
  };

  const facetMedia = Array.isArray(facets.data?.media_types)
    ? facets.data.media_types
    : [];
  const availableMedia = new Set(
    facetMedia.length > 0 ? facetMedia.map((entry) => entry.value) : ["movie"],
  );
  const mediaOptions: { value: MediaFilter; label: string }[] = [
    { value: null, label: "All" },
    { value: "movie", label: "Films" },
  ];
  if (availableMedia.has("tv")) {
    mediaOptions.push({ value: "tv", label: "TV" });
  }
  const genreOptions = Array.isArray(facets.data?.genres) && facets.data.genres.length > 0
    ? facets.data.genres.map((entry) => entry.value).slice(0, 16)
    : [...GENRES];

  useEffect(() => {
    if (isApiError(query.error) && query.error.status === 409) {
      setConflict(true);
    }
  }, [query.error]);

  useEffect(() => {
    setConflict(false);
  }, [mediaType, genre]);

  useEffect(() => {
    if (facets.data && mediaType === "tv" && !availableMedia.has("tv")) {
      const params = new URLSearchParams(searchParams);
      params.delete("media_type");
      setSearchParams(params, { replace: true });
    }
  }, [availableMedia, facets.data, mediaType, searchParams, setSearchParams]);

  const items = uniqueByTitleId(query.data?.pages.flatMap((page) => page.items) ?? []);

  return (
    <div className="page-shell py-12">
      <PageHeader
        title="Explore"
        description="Browse the catalogue by media type and genre."
      />

      <div className="mb-10 space-y-5 border-b border-white/10 pb-6">
        <div
          className="inline-flex w-fit border border-white/20"
          role="group"
          aria-label="Media type"
        >
          {mediaOptions.map((option) => {
            const active = mediaType === option.value;
            return (
              <button
                key={option.label}
                type="button"
                aria-pressed={active}
                onClick={() => updateFilter({ mediaType: option.value })}
                className={cn(
                  "px-5 py-2 text-sm font-semibold transition-colors",
                  active
                    ? "bg-white text-black"
                    : "text-white/60 hover:bg-white/10 hover:text-white",
                )}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        <div>
          <p className="type-badge mb-3 text-white/40">Genre</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Genre">
            <button
              type="button"
              aria-pressed={!genre}
              onClick={() => updateFilter({ genre: null })}
              className={cn(
                "border px-3 py-1.5 text-xs font-medium transition-colors",
                !genre
                  ? "border-accent bg-accent text-white"
                  : "border-white/15 bg-white/[0.02] text-white/60 hover:border-white/35 hover:text-white",
              )}
            >
              All genres
            </button>
            {genreOptions.map((value) => {
              const active = genre === value;
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => updateFilter({ genre: active ? null : value })}
                  className={cn(
                    "border px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "border-accent bg-accent text-white"
                      : "border-white/15 bg-white/[0.02] text-white/60 hover:border-white/35 hover:text-white",
                  )}
                >
                  {value}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {conflict ? (
        <div className="mb-6">
          <InlineNotice
            tone="warning"
            action={
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setConflict(false);
                  setResetKey((current) => current + 1);
                }}
              >
                Refresh
              </Button>
            }
          >
            This list changed while you were browsing. Refresh to see the latest
            titles.
          </InlineNotice>
        </div>
      ) : null}

      {query.isLoading ? <PosterGridSkeleton count={12} /> : null}

      {query.isError && !query.data ? (
        <ErrorState
          title="We couldn't load these titles"
          message={
            isApiError(query.error)
              ? query.error.message
              : "Please try again in a moment."
          }
          onRetry={() => void query.refetch()}
        />
      ) : null}

      {query.data && items.length === 0 ? (
        <EmptyState
          icon={Compass}
          title="No titles match these filters"
          message="Try another genre or clear the filters."
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setSearchParams({}, { replace: true });
              }}
            >
              Clear filters
            </Button>
          }
        />
      ) : null}

      {items.length > 0 ? <PosterGrid items={items} /> : null}

      {items.length > 0 ? (
        <div className="mt-12 flex flex-col items-center gap-4">
          {query.isFetchingNextPage ? (
            <p className="text-sm text-muted" role="status">
              Loading more titles
            </p>
          ) : null}

          {query.isError && query.data && !conflict ? (
            <InlineNotice
              tone="error"
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void query.fetchNextPage()}
                >
                  Retry
                </Button>
              }
            >
              {isApiError(query.error)
                ? query.error.message
                : "Couldn't load more titles. Please try again."}
            </InlineNotice>
          ) : null}

          {query.hasNextPage && !conflict ? (
            <Button
              variant="secondary"
              loading={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
            >
              Load more
            </Button>
          ) : null}

          {!query.hasNextPage && items.length > 0 && !conflict ? (
            <p className="text-sm text-faint">You've reached the end.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

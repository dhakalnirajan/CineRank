import { useQuery } from "@tanstack/react-query";
import { Bookmark } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { PosterGridSkeleton } from "../components/feedback/Skeletons";
import { PosterCard } from "../components/media/PosterCard";
import { buttonClasses, Button } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { useRemoveFromWatchlist, useWatchlist } from "../features/watchlist/useWatchlist";
import { useAuth } from "../features/auth/AuthProvider";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { displayTitle } from "../utils/displayTitle";
import { formatDate } from "../utils/format";

export default function WatchlistPage() {
  useDocumentTitle("Watchlist");
  const { user } = useAuth();
  const watchlist = useWatchlist();
  const remove = useRemoveFromWatchlist();
  const suggestions = useQuery({
    queryKey: queryKeys.home(user?.id ?? 0, 12),
    queryFn: ({ signal }) => api.home(user?.id ?? 0, 12, signal),
    enabled: Boolean(user) && watchlist.data?.length === 0,
    staleTime: 60_000,
  });

  return (
    <div className="page-shell py-12">
      <PageHeader
        eyebrow="Saved"
        title="Watchlist"
        description={
          watchlist.data
            ? watchlist.data.length + " " + (watchlist.data.length === 1 ? "title" : "titles") + " saved."
            : "Keep track of what you want to watch."
        }
        actions={
          <Link to="/explore" className={buttonClasses("secondary", "sm")}>
            Find more titles
          </Link>
        }
      />

      {remove.isError ? (
        <div className="mb-6">
          <InlineNotice tone="error">
            {isApiError(remove.error)
              ? remove.error.message
              : "Couldn't remove that title. Please try again."}
          </InlineNotice>
        </div>
      ) : null}

      {watchlist.isLoading ? <PosterGridSkeleton count={10} /> : null}

      {watchlist.isError ? (
        <ErrorState
          title="We couldn't load your watchlist"
          message={
            isApiError(watchlist.error)
              ? watchlist.error.message
              : "Please try again in a moment."
          }
          onRetry={() => void watchlist.refetch()}
        />
      ) : null}

      {watchlist.data && watchlist.data.length === 0 ? (
        <div className="space-y-12">
          <EmptyState
            icon={Bookmark}
            title="Your watchlist is ready when you are"
            message="Save a title here and it will be waiting for your next movie night."
            action={
              <Link to="/explore" className={buttonClasses("primary", "md")}>
                Explore the catalogue
              </Link>
            }
          />
          {suggestions.data && suggestions.data.for_you.length > 0 ? (
            <PosterRow
              title="Start here"
              subtitle="A few picks you can save in one click."
              items={suggestions.data.for_you.slice(0, 8)}
            />
          ) : null}
        </div>
      ) : null}

      {watchlist.data && watchlist.data.length > 0 ? (
        <ul className="grid grid-cols-2 gap-x-2.5 gap-y-9 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {watchlist.data.map((entry) => {
            const titleId = entry.title.title_id;
            const isRemoving =
              remove.isPending && remove.variables === titleId;

            return (
              <li key={titleId}>
                <PosterCard item={entry.title} />
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-xs text-white/40">
                    {formatDate(entry.created_at) ?? "Saved"}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={isRemoving}
                    onClick={() => remove.mutate(titleId)}
                    aria-label={`Remove ${displayTitle(entry.title)} from watchlist`}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
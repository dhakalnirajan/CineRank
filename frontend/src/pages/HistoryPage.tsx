import { useQuery } from "@tanstack/react-query";
import { History, Star } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { Skeleton } from "../components/feedback/Skeletons";
import { buttonClasses } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { useAuth } from "../features/auth/AuthProvider";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { displayTitle } from "../utils/displayTitle";
import { formatDate } from "../utils/format";
import { getTitleUrl } from "../utils/titleRoute";

export default function HistoryPage() {
  useDocumentTitle("Rating history");
  const { user } = useAuth();
  const history = useQuery({
    queryKey: queryKeys.history(user?.id ?? 0),
    queryFn: ({ signal }) => api.history(user?.id ?? 0, 100, signal),
    enabled: Boolean(user),
  });

  return (
    <div className="page-shell py-12">
      <PageHeader
        eyebrow="Your activity"
        title="Rating history"
        description="Ratings you've given, newest first."
        actions={
          <Link to="/explore" className={buttonClasses("secondary", "sm")}>
            Find something to rate
          </Link>
        }
      />

      {history.isLoading ? (
        <div className="space-y-3" role="status" aria-label="Loading rating history">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-16 w-full" />
          ))}
        </div>
      ) : null}

      {history.isError ? (
        <ErrorState
          title="We couldn't load your ratings"
          message={
            isApiError(history.error) ? history.error.message : "Please try again in a moment."
          }
          onRetry={() => void history.refetch()}
        />
      ) : null}

      {history.data && history.data.items.length === 0 ? (
        <EmptyState
          icon={History}
          title="No ratings yet"
          message="Rate a title and it will show up here."
          action={
            <Link to="/explore" className={buttonClasses("primary", "md")}>
              Find a title to rate
            </Link>
          }
        />
      ) : null}

      {history.data && history.data.items.length > 0 ? (
        <ul className="divide-y divide-white/10 border border-white/10 bg-[#0c0c0c]">
          {history.data.items.map((item) => (
            <li key={`${item.title_id}-${item.timestamp}`}>
              <Link
                to={getTitleUrl(item)}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 transition-colors hover:bg-white/5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">
                    {displayTitle(item)}
                  </p>
                  <p className="mt-1 text-xs text-white/40">
                    {formatDate(item.timestamp) ?? "Unknown date"}
                  </p>
                </div>
                <span className="meta-numeric inline-flex items-center gap-1.5 text-sm text-ink">
                  <Star className="size-4 fill-accent text-accent" aria-hidden="true" />
                  {item.rating.toFixed(1)}
                  <span className="text-white/40">/ 5</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

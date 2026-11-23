import { useQuery } from "@tanstack/react-query";
import { Compass, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { PosterGridSkeleton } from "../components/feedback/Skeletons";
import { PageHeader } from "../components/ui/PageHeader";
import { buttonClasses } from "../components/ui/Button";
import { RecommendationCard } from "../features/recommendations/RecommendationCard";
import { useAuth } from "../features/auth/AuthProvider";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { formatDate } from "../utils/format";

const RECOMMENDATION_COUNT = 24;

export default function RecommendationsPage() {
  useDocumentTitle("For you");
  const { user } = useAuth();
  const recommendations = useQuery({
    queryKey: queryKeys.recommendations(user?.id ?? 0, RECOMMENDATION_COUNT),
    queryFn: ({ signal }) => api.recommendations(RECOMMENDATION_COUNT, signal),
    enabled: Boolean(user),
    staleTime: 30_000,
  });

  return (
    <div className="page-shell py-10 sm:py-12">
      <PageHeader
        eyebrow="Picked around your taste"
        title="For you"
        description="A ranked selection shaped by your ratings and activity. Your feedback helps refine future picks."
        actions={
          <Link to="/explore" className={buttonClasses("secondary", "sm")}>
            Explore all titles
          </Link>
        }
      />

      {recommendations.isLoading ? <PosterGridSkeleton count={12} /> : null}

      {recommendations.isError ? (
        <ErrorState
          title={isApiError(recommendations.error) && recommendations.error.status === 503
            ? "Your picks need a moment"
            : "We couldn't load your recommendations"}
          message={isApiError(recommendations.error) && recommendations.error.status === 503
            ? "Personalized picks aren't available right now. You can still explore the catalogue."
            : isApiError(recommendations.error)
              ? recommendations.error.message
              : "Please try again in a moment."}
          onRetry={() => void recommendations.refetch()}
          action={
            <Link to="/explore" className={buttonClasses("secondary", "md")}>
              Browse the catalogue
            </Link>
          }
        />
      ) : null}

      {recommendations.data && recommendations.data.items.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title="Your next picks are still taking shape"
          message="Rate a few titles or explore the catalogue. We'll use your activity to shape future recommendations."
          action={
            <Link to="/explore" className={buttonClasses("primary", "md")}>
              <Compass className="size-4" aria-hidden="true" />
              Explore titles
            </Link>
          }
        />
      ) : null}

      {recommendations.data && recommendations.data.items.length > 0 ? (
        <>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 text-xs text-white/45">
            <span>{recommendations.data.items.length} recommendations</span>
            <span>Updated {formatDate(recommendations.data.generated_at) ?? "recently"}</span>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-7 sm:grid-cols-3 sm:gap-x-4 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
            {recommendations.data.items.map((item) => (
              <RecommendationCard key={item.title_id} item={item} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

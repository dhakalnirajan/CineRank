import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { Compass } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import {
  HomeHeroSkeleton,
  PosterGridSkeleton,
  RecommendationRowSkeleton,
} from "../components/feedback/Skeletons";
import { PosterGrid } from "../components/media/PosterGrid";
import { PosterRow } from "../components/media/PosterRow";
import { buttonClasses } from "../components/ui/Button";
import { PageHeader } from "../components/ui/PageHeader";
import { useAuth } from "../features/auth/AuthProvider";
import { HeroCarousel } from "../features/home/HeroCarousel";
import { ForYouRow } from "../features/home/ForYouRow";
import { genreRowLabel } from "../features/home/labels";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import type { MoviePage } from "../types/api";
import { isRenderableImageUrl } from "../utils/format";

const HOME_K = 18;

export default function HomePage() {
  useDocumentTitle("Home");
  const { status, user, retryUser } = useAuth();

  const homeQuery = useQuery({
    queryKey: queryKeys.home(user?.id ?? 0, HOME_K),
    queryFn: ({ signal }) => api.home(user?.id ?? 0, HOME_K, signal),
    enabled: Boolean(user),
  });

  const previewQuery = useQuery({
    queryKey: queryKeys.cataloguePreview,
    queryFn: ({ signal }) => api.listMovies({ limit: 12 }, signal),
    enabled: status === "anonymous",
    staleTime: 60_000,
  });

  if (status === "loading") {
    return (
      <div>
        <HomeHeroSkeleton />
        <div className="page-shell space-y-10 py-12">
          <RecommendationRowSkeleton />
          <RecommendationRowSkeleton />
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="page-shell pb-16 pt-28">
        <ErrorState
          title="We couldn't load your account"
          message="Please try again in a moment."
          onRetry={retryUser}
        />
      </div>
    );
  }

  if (!user) {
    return <AnonymousHome preview={previewQuery} />;
  }

  if (homeQuery.isPending) {
    return (
      <div>
        <HomeHeroSkeleton />
        <div className="page-shell space-y-10 py-12">
          <RecommendationRowSkeleton />
          <RecommendationRowSkeleton />
        </div>
      </div>
    );
  }

  if (homeQuery.isError) {
    const unavailable = isApiError(homeQuery.error) && homeQuery.error.status === 503;
    return (
      <div className="page-shell pb-16 pt-28">
        <ErrorState
          title={unavailable ? "Your picks need a moment" : "We couldn't load your picks"}
          message={
            unavailable
              ? "Recommendations aren't ready yet. Browse the catalogue in the meantime."
              : isApiError(homeQuery.error)
                ? homeQuery.error.message
                : "Please try again in a moment."
          }
          onRetry={() => void homeQuery.refetch()}
          action={
            <Link to="/explore" className={buttonClasses("secondary", "md")}>
              Browse the catalogue
            </Link>
          }
        />
      </div>
    );
  }

  const data = homeQuery.data;
  const forYou = data.for_you;
  const popular = data.popular;
  const recentlyAdded = data.recently_added ?? [];
  const genreRows = Object.entries(data.genres).filter(([, items]) => items.length > 0);
  const hasRecommendations =
    forYou.length > 0 || popular.length > 0 || recentlyAdded.length > 0 || genreRows.length > 0;

  return (
    <div>
      {forYou.length > 0 ? (
        <HeroCarousel items={forYou} />
      ) : null}

      <div
        className="page-shell space-y-14 pb-12 pt-28"
      >
        {!hasRecommendations ? (
          <EmptyState
            icon={Compass}
            title="Your recommendations are still warming up"
            message="Rate a few titles and we'll find your next favorite."
            action={
              <Link to="/explore" className={buttonClasses("primary", "md")}>
                Explore titles
              </Link>
            }
          />
        ) : null}

        {forYou.length > 0 ? (
          <ForYouRow
            userId={user.id}
            items={forYou}
            nextCursor={data.next_cursor}
            action={
              <Link to="/recommendations" className="text-xs font-semibold text-white/65 transition-colors hover:text-white">
                See all
              </Link>
            }
          />
        ) : null}

        {popular.length > 0 ? (
          <PosterRow
            title="Popular now"
            subtitle="What other viewers are enjoying."
            items={popular}
          />
        ) : null}

        {recentlyAdded.length > 0 ? (
          <PosterRow
            title="Recently added"
            subtitle="New titles added to the CineRank catalogue."
            items={recentlyAdded}
          />
        ) : null}

        {genreRows.map(([key, items]) => (
          <PosterRow key={key} title={genreRowLabel(key)} items={items} />
        ))}
      </div>
    </div>
  );
}

interface AnonymousHomeProps {
  preview: UseQueryResult<MoviePage, Error>;
}

function AnonymousHome({ preview }: AnonymousHomeProps) {
  const previewItems = preview.data?.items ?? [];
  const featured = previewItems[0];
  const backdrop = isRenderableImageUrl(featured?.backdrop_path ?? featured?.poster_path);

  return (
    <div>
      <section className="relative isolate flex min-h-[38rem] items-end overflow-hidden sm:min-h-[42rem] lg:min-h-[46rem]">
        <div className="absolute inset-0 -z-10 bg-black">
          {backdrop ? (
            <img
              src={backdrop}
              alt=""
              loading="eager"
              fetchPriority="high"
              decoding="async"
              className="size-full object-cover object-center"
            />
          ) : (
            <div className="hero-art size-full" />
          )}
          <div className="billboard-shade-mobile absolute inset-0 sm:hidden" aria-hidden="true" />
          <div className="billboard-shade absolute inset-0 hidden sm:block" aria-hidden="true" />
        </div>

        <div className="page-shell w-full pb-16 pt-36 lg:pb-24">
          <div className="max-w-2xl animate-fade-up">
            <p className="type-badge text-accent">
              CineRank
            </p>
            <h1 className="type-hero text-shadow-hero mt-3 text-white">
              Find your next favorite.
            </h1>
            <p className="mt-5 max-w-lg text-base leading-relaxed text-white/70">
              Recommendations shaped by what you love, not what's trending.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/explore" className={buttonClasses("primary", "lg")}>
                Browse the catalogue
              </Link>
              <Link to="/register" className={buttonClasses("secondary", "lg")}>
                Create an account
              </Link>
            </div>
            <p className="mt-5 text-sm text-white/50">
              Already have an account?{" "}
              <Link to="/login" className="text-white underline underline-offset-4 hover:text-white/80">
                Sign in
              </Link>
            </p>
          </div>
        </div>
      </section>

      <div className="page-shell py-14">
        <PageHeader
          title="Worth a look"
          actions={
            <Link to="/explore" className={buttonClasses("secondary", "sm")}>
              View all
            </Link>
          }
        />

        {preview.isLoading ? <PosterGridSkeleton count={8} /> : null}

        {preview.isError ? (
          <ErrorState
            title="We couldn't load these titles"
            message={
              isApiError(preview.error)
                ? preview.error.message
                : "Please try again in a moment."
            }
            onRetry={() => void preview.refetch()}
          />
        ) : null}

        {preview.data && preview.data.items.length === 0 ? (
          <EmptyState
            icon={Compass}
            title="No titles yet"
            message="Please check back soon."
          />
        ) : null}

        {preview.data && preview.data.items.length > 0 ? (
          <PosterGrid items={preview.data.items} />
        ) : null}
      </div>
    </div>
  );
}

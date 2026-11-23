import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarDays, Clapperboard, Clock3, Film, Star, Tv } from "lucide-react";
import { useEffect } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { ErrorState } from "../components/feedback/ErrorState";
import { PosterGridSkeleton, Skeleton } from "../components/feedback/Skeletons";
import { Backdrop } from "../components/media/Backdrop";
import { Poster } from "../components/media/Poster";
import { PosterRow } from "../components/media/PosterRow";
import { buttonClasses } from "../components/ui/Button";
import { useAuth } from "../features/auth/AuthProvider";
import { useTitleClick } from "../features/interactions/useInteraction";
import { RatingForm } from "../features/ratings/RatingForm";
import { WatchlistButton } from "../features/watchlist/WatchlistButton";
import { WatchedButton } from "../features/watched/WatchedButton";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { displayTitle } from "../utils/displayTitle";
import {
  formatRating,
  formatRuntime,
  formatYear,
  mediaLabel,
  parseGenres,
  parsePeople,
} from "../utils/format";
import { getTitleUrl } from "../utils/titleRoute";

interface TitlePageProps {
  mediaType: "movie" | "tv";
}

export default function TitlePage({ mediaType }: TitlePageProps) {
  const { serialNumber = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();

  const titleQuery = useQuery({
    queryKey: queryKeys.title(mediaType, serialNumber),
    queryFn: ({ signal }) => api.getTitle(mediaType, serialNumber, signal),
    enabled: Boolean(serialNumber),
  });

  useEffect(() => {
    if (!titleQuery.data) {
      return;
    }
    const canonicalPath = getTitleUrl(titleQuery.data);
    if (location.pathname !== canonicalPath) {
      navigate(canonicalPath, { replace: true });
    }
  }, [location.pathname, navigate, titleQuery.data]);

  const history = useQuery({
    queryKey: queryKeys.history(user?.id ?? 0),
    queryFn: ({ signal }) => api.history(user?.id ?? 0, 200, signal),
    enabled: Boolean(user),
  });

  const similar = useQuery({
    queryKey: queryKeys.similarTitles(mediaType, serialNumber),
    queryFn: ({ signal }) => api.similarTitles(mediaType, serialNumber, 10, signal),
    enabled: Boolean(titleQuery.data),
    staleTime: 60_000,
  });

  const expandSimilar = useMutation({
    mutationFn: (vars: { mediaType: "movie" | "tv"; serialNumber: string }) =>
      api.similarTitles(vars.mediaType, vars.serialNumber, 24),
  });

  useTitleClick(titleQuery.data ? titleQuery.data.title_id : null);
  useDocumentTitle(titleQuery.data ? displayTitle(titleQuery.data) : "Title");

  if (!serialNumber || (titleQuery.isError && isApiError(titleQuery.error) && titleQuery.error.status === 404)) {
    return (
      <div className="page-shell py-20">
        <EmptyState
          icon={Clapperboard}
          title="Title not found"
          message="This title isn't here. It may have been removed, or the link may be wrong."
          action={
            <Link to="/explore" className={buttonClasses("primary", "md")}>
              Browse the catalogue
            </Link>
          }
        />
      </div>
    );
  }

  if (titleQuery.isLoading) {
    return (
      <div>
        <Skeleton className="h-[46vh] min-h-[20rem] w-full rounded-none" />
        <div className="page-shell -mt-40 relative">
          <div className="grid gap-8 sm:grid-cols-[11rem_minmax(0,1fr)] lg:grid-cols-[17rem_minmax(0,1fr)]">
            <Skeleton className="poster-frame w-32 rounded-none sm:w-full" />
            <div className="space-y-4 pt-8">
              <Skeleton className="h-4 w-40 rounded-none" />
              <Skeleton className="h-14 w-3/4 rounded-none" />
              <Skeleton className="h-4 w-1/2 rounded-none" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (titleQuery.isError || !titleQuery.data) {
    return (
      <div className="page-shell py-20">
        <ErrorState
          title="We couldn't load this title"
          message={
            isApiError(titleQuery.error)
              ? titleQuery.error.message
              : "Please try again in a moment."
          }
          onRetry={() => void titleQuery.refetch()}
        />
      </div>
    );
  }

  const movie = titleQuery.data;
  const title = displayTitle(movie);
  const genres = parseGenres(movie.genres);
  const directors = parsePeople(movie.directors_json);
  const cast = parsePeople(movie.cast_json);
  const personalRating =
    history.data?.items.find((item) => item.title_id === movie.title_id)?.rating ?? null;
  const externalRating = formatRating(movie.vote_average);
  const runtime = formatRuntime(movie.runtime);
  const year = formatYear(movie.year);
  const meta = [year, mediaLabel(movie.media_type)].filter(
    (value): value is string => Boolean(value),
  );
  const expandedData = expandSimilar.data;
  const expansionForCurrent = Boolean(
    expandedData && similar.data && expandedData.title_id === similar.data.title_id,
  );
  const expandedSimilar = expansionForCurrent && expandedData ? expandedData.items : [];
  const initialSimilar = similar.data?.items ?? [];
  const initialSimilarIds = new Set(initialSimilar.map((item) => item.title_id));
  const similarItems = [
    ...initialSimilar,
    ...expandedSimilar.filter((item) => !initialSimilarIds.has(item.title_id)),
  ];
  const expansionForCurrentTitle =
    expandSimilar.variables?.mediaType === mediaType &&
    expandSimilar.variables?.serialNumber === serialNumber;
  const loadMoreSimilar = () => {
    if (!similar.data || expandSimilar.isPending || expansionForCurrent) {
      return;
    }
    expandSimilar.mutate({ mediaType, serialNumber });
  };

  return (
    <div>
      <div className="relative">
        <Backdrop
          src={movie.backdrop_path}
          title={title}
          className="h-[58vh] max-h-[40rem] min-h-[24rem] w-full"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/50 to-black/20" aria-hidden="true" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/30 to-transparent" aria-hidden="true" />
      </div>

      <div className="page-shell relative -mt-48 pb-16 sm:-mt-56">
        <div className="grid gap-6 sm:grid-cols-[11rem_minmax(0,1fr)] lg:grid-cols-[17rem_minmax(0,1fr)] lg:gap-10">
          <Poster
            src={movie.poster_path}
            title={title}
            year={year}
            genre={genres[0] ?? null}
            priority
            className="w-32 border border-white/10 sm:w-full"
          />
          <div className="pt-1 lg:pt-24">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
              {mediaLabel(movie.media_type)}
            </p>
            <h1 className="text-shadow-hero mt-3 text-4xl font-bold leading-[1.05] text-white sm:text-5xl lg:text-6xl">
              {title}
            </h1>
            {meta.length > 0 ? (
              <p className="meta-numeric mt-4 flex flex-wrap items-center gap-2 text-sm text-white/65">
                {meta.map((value, index) => (
                  <span key={`${value}-${index}`} className="flex items-center gap-2">
                    {index > 0 ? (
                      <span aria-hidden="true" className="h-3 w-px bg-white/25" />
                    ) : null}
                    {value}
                  </span>
                ))}
              </p>
            ) : null}

            {genres.length > 0 ? (
              <ul aria-label="Genres" className="mt-4 flex flex-wrap gap-2">
                {genres.map((genre) => (
                  <li key={genre}>
                    <Link
                      to={`/explore?genre=${encodeURIComponent(genre)}`}
                      className="inline-flex border border-white/20 bg-white/[0.03] px-2.5 py-1 text-xs font-medium text-white/70 transition-colors hover:border-white/40 hover:text-white"
                    >
                      {genre}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : null}

            <div className="mt-7 flex max-w-md flex-col gap-3 sm:flex-row sm:items-start">
              <div className="sm:w-64">
                <WatchlistButton titleId={movie.title_id} size="md" />
                <WatchedButton titleId={movie.title_id} size="md" />
              </div>
            </div>
          </div>
        </div>

        <div className="mt-14 grid gap-12 lg:grid-cols-[minmax(0,1fr)_21rem]">
          <div className="space-y-10">
            <section aria-labelledby="overview-heading">
              <h2 id="overview-heading" className="text-xl font-semibold text-white">
                Overview
              </h2>
              {movie.overview ? (
                <p className="mt-3 max-w-3xl text-[0.9375rem] leading-relaxed text-white/70">
                  {movie.overview}
                </p>
              ) : (
                <p className="mt-3 text-sm text-white/40">No overview yet.</p>
              )}
            </section>

            {directors.length > 0 ? (
              <section aria-labelledby="directors-heading">
                <h2 id="directors-heading" className="text-xl font-semibold text-white">
                  Direction
                </h2>
                <p className="mt-3 text-sm text-white/70">
                  {directors.map((person) => person.name).join(", ")}
                </p>
              </section>
            ) : null}

            {cast.length > 0 ? (
              <section aria-labelledby="cast-heading">
                <h2 id="cast-heading" className="text-xl font-semibold text-white">
                  Cast
                </h2>
                <ul className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
                  {cast.slice(0, 12).map((person, index) => (
                    <li
                      key={`${person.name}-${index}`}
                      className="flex flex-col border-b border-white/10 pb-3"
                    >
                      <span className="text-sm text-white">{person.name}</span>
                      {person.role ? (
                        <span className="mt-0.5 text-xs text-white/40">{person.role}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>

          <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
            {user ? (
              history.isLoading ? (
                <Skeleton className="h-52 w-full rounded-none" />
              ) : (
                <RatingForm titleId={movie.title_id} initialRating={personalRating} />
              )
            ) : (
              <div className="border border-white/10 bg-[#0c0c0c] p-5">
                <h2 className="text-base font-semibold text-white">Your rating</h2>
                <p className="mt-2 text-sm leading-relaxed text-white/60">
                  Sign in to rate this title and add it to your watchlist. Ratings shape your
                  personal recommendations.
                </p>
                <Link
                  to={`/login?redirect=${encodeURIComponent(getTitleUrl(movie))}`}
                  className={buttonClasses("primary", "sm", "mt-4")}
                >
                  Sign in to rate
                </Link>
              </div>
            )}

            {history.isError && user ? (
              <p className="text-xs text-warning" role="status">
                Your previous rating could not be loaded. You can still submit a new one.
              </p>
            ) : null}

            <div className="border border-white/10 bg-[#0c0c0c] p-5">
              <h2 className="text-base font-semibold text-white">Details</h2>
              <dl className="mt-4 space-y-3 text-sm">
                {externalRating ? (
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="flex items-center gap-2 text-white/50">
                      <Star
                        aria-hidden="true"
                        className="h-4 w-4 shrink-0 fill-amber-400 text-amber-400"
                        strokeWidth={1.75}
                      />
                      External rating
                    </dt>
                    <dd className="meta-numeric text-white">
                      {externalRating}
                      {typeof movie.vote_count === "number" ? (
                        <span className="ml-1 text-xs text-white/40">
                          ({movie.vote_count.toLocaleString()} votes)
                        </span>
                      ) : null}
                    </dd>
                  </div>
                ) : null}
                {year ? (
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="flex items-center gap-2 text-white/50">
                      <CalendarDays
                        aria-hidden="true"
                        className="h-4 w-4 shrink-0 text-white/35"
                        strokeWidth={1.75}
                      />
                      Release year
                    </dt>
                    <dd className="meta-numeric text-white">{year}</dd>
                  </div>
                ) : null}
                {runtime ? (
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="flex items-center gap-2 text-white/50">
                      <Clock3
                        aria-hidden="true"
                        className="h-4 w-4 shrink-0 text-white/35"
                        strokeWidth={1.75}
                      />
                      Runtime
                    </dt>
                    <dd className="text-white">{runtime}</dd>
                  </div>
                ) : null}
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="flex items-center gap-2 text-white/50">
                    {movie.media_type === "tv" ? (
                      <Tv
                        aria-hidden="true"
                        className="h-4 w-4 shrink-0 text-white/35"
                        strokeWidth={1.75}
                      />
                    ) : (
                      <Film
                        aria-hidden="true"
                        className="h-4 w-4 shrink-0 text-white/35"
                        strokeWidth={1.75}
                      />
                    )}
                    Type
                  </dt>
                  <dd className="text-white">{mediaLabel(movie.media_type)}</dd>
                </div>
              </dl>
              <p className="mt-4 text-xs leading-relaxed text-white/40">
                Rated by other viewers.
              </p>
            </div>
          </aside>
        </div>

        <div className="mt-16">
          {similar.isLoading ? (
            <>
              <h2 className="text-xl font-semibold text-white">More like this</h2>
              <div className="mt-5">
                <PosterGridSkeleton count={5} />
              </div>
            </>
          ) : null}

          {similar.isError ? (
            <div role="status">
              <h2 className="text-xl font-semibold text-white">More like this</h2>
              <div className="mt-3 flex flex-col items-start gap-3">
                <p className="text-sm text-white/60">Couldn't load similar titles right now.</p>
                <button
                  type="button"
                  className={buttonClasses("secondary", "sm")}
                  onClick={() => void similar.refetch()}
                >
                  Retry
                </button>
              </div>
            </div>
          ) : null}

          {similar.data && similarItems.length === 0 ? (
            <div>
              <h2 className="text-xl font-semibold text-white">More like this</h2>
              <p className="mt-3 text-sm text-white/55">No close matches yet.</p>
            </div>
          ) : null}

          {similar.data && similarItems.length > 0 ? (
            <PosterRow
              title="More like this"
              items={similarItems}
              onNearEnd={loadMoreSimilar}
              trailing={
                expandSimilar.isPending && expansionForCurrentTitle ? (
                  <p className="w-36 shrink-0 self-center text-xs text-white/45" role="status">
                    Loading more titles
                  </p>
                ) : expandSimilar.isError && expansionForCurrentTitle ? (
                  <button
                    type="button"
                    className={buttonClasses("ghost", "sm", "shrink-0 self-center")}
                    onClick={loadMoreSimilar}
                  >
                    Retry
                  </button>
                ) : null
              }
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

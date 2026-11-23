import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonClasses } from "../../components/ui/Button";
import { cn } from "../../utils/cn";
import { displayTitle } from "../../utils/displayTitle";
import { isRenderableImageUrl } from "../../utils/format";
import { getTitleUrl } from "../../utils/titleRoute";
import { WatchlistButton } from "../watchlist/WatchlistButton";
import type { RecommendationItem } from "../../types/api";
import {
  formatYear,
  parseGenres,
  recommendationReason,
} from "../../utils/format";

interface HomeHeroProps {
  item: RecommendationItem;
  backdropPath?: string | null;
}

export function HomeHero({ item, backdropPath }: HomeHeroProps) {
  const title = displayTitle(item);
  const year = formatYear(item.year);
  const genres = parseGenres(item.genres).slice(0, 3);
  const reason = recommendationReason(item.reason);
  const meta = [year].filter((value): value is string => Boolean(value));
  const imageUrl = isRenderableImageUrl(backdropPath ?? item.poster_path);
  const usingPoster = !isRenderableImageUrl(backdropPath);

  return (
    <section className="relative isolate flex min-h-[36rem] items-end overflow-hidden sm:min-h-[40rem] lg:min-h-[46rem]">
      <div className="absolute inset-0 -z-10 bg-black">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt=""
            loading="eager"
            fetchPriority="high"
            decoding="async"
            className={cn(
              "size-full object-cover",
              usingPoster ? "scale-110 object-top blur-[1px]" : "object-center",
            )}
          />
        ) : (
          <div className="hero-art relative size-full overflow-hidden">
            <span
              aria-hidden="true"
              className="absolute right-[4%] top-[16%] hidden max-w-[48%] text-right font-display text-[clamp(4rem,9vw,9rem)] font-black leading-[0.82] tracking-[-0.06em] text-white/[0.045] lg:block"
            >
              {title}
            </span>
          </div>
        )}
        <div
          className="billboard-shade-mobile absolute inset-0 sm:hidden"
          aria-hidden="true"
        />
        <div
          className="billboard-shade absolute inset-0 hidden sm:block"
          aria-hidden="true"
        />
      </div>

      <div className="page-shell w-full pb-14 pt-36 sm:pb-16 lg:pb-24">
        <div className="max-w-2xl animate-fade-up">
          <p className="type-badge text-accent">Top pick for you</p>
          <h1 className="type-hero text-shadow-hero mt-3 text-white">
            {title}
          </h1>
          {meta.length > 0 ? (
            <p className="meta-numeric mt-4 flex flex-wrap items-center gap-2 text-sm text-white/70">
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
                    className="inline-flex border border-white/20 bg-black/30 px-2.5 py-1 text-xs font-medium text-white/75 transition-colors hover:border-white/40 hover:text-white"
                  >
                    {genre}
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
          {item.overview ? (
            <p className="mt-4 line-clamp-3 max-w-xl text-sm leading-relaxed text-white/75 sm:text-base">
              {item.overview}
            </p>
          ) : null}
          {reason ? (
            <p className="mt-3 max-w-lg text-xs leading-relaxed text-white/50">
              {reason}
            </p>
          ) : null}
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <div className="min-w-[12rem]">
              <WatchlistButton titleId={item.title_id} size="lg" />
            </div>
            <Link
              to={getTitleUrl(item)}
              className={buttonClasses("primary", "lg")}
            >
              View details
              <ArrowRight className="size-5" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

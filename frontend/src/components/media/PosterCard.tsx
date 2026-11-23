import { BookmarkPlus, BookmarkCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useImpression } from "../../features/interactions/useInteraction";
import { cn } from "../../utils/cn";
import { displayTitle } from "../../utils/displayTitle";
import { formatYear, parseGenres } from "../../utils/format";
import { getTitleUrl } from "../../utils/titleRoute";
import { Poster } from "./Poster";
import type { CardTitle } from "./cardTypes";

interface PosterCardProps {
  item: CardTitle;
  className?: string;
  priority?: boolean;
}

export function PosterCard({ item, className, priority = false }: PosterCardProps) {
  const impressionRef = useImpression(item.title_id);
  const title = displayTitle(item);
  const year = formatYear(item.year);
  const genre = parseGenres(item.genres)[0] ?? null;

  return (
    <article
      ref={impressionRef}
      className={cn("group relative min-w-0", className)}
    >
      <Link
        to={getTitleUrl(item)}
        className="block rounded-poster focus-visible:outline-offset-4"
        aria-label={`${title}${year ? `, ${year}` : ""}`}
      >
        <div className="overflow-hidden rounded-poster bg-raised">
          <Poster
            src={item.poster_path}
            title={title}
            year={year}
            genre={genre}
            priority={priority}
            className="transition-transform duration-[var(--motion-slow)] ease-[var(--ease-out)] group-hover:scale-[1.04] group-focus-visible:scale-[1.04]"
          />
        </div>
        <h3 className="type-card-title mt-3 line-clamp-2 text-white transition-colors group-hover:text-white/80">
          {title}
        </h3>
        {year || genre ? (
          <p className="type-meta mt-1.5 flex flex-wrap items-center gap-2 text-white/50">
            {year ? <span className="meta-numeric">{year}</span> : null}
            {genre ? (
              <span className="inline-flex border border-white/15 bg-white/[0.03] px-2 py-0.5 text-[0.6875rem] font-medium text-white/60">
                {genre}
              </span>
            ) : null}
          </p>
        ) : null}
      </Link>

      {/* Floating action bar - appears on hover */}
      <div
        className={cn(
          "absolute right-2 top-2 grid gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10",
          className,
        )}
      >
        {/* Watchlist button */}
        <button
          type="button"
          aria-pressed={false}
          aria-label="Add to watchlist"
          title="Add to watchlist"
          onClick={() => {}}
          className={cn(
            "rounded-full border border-white/25 bg-black/70 text-white/85 backdrop-blur-sm size-8 place-items-center transition-colors hover:border-white/60 hover:bg-black hover:text-white focus-visible:opacity-100 disabled:cursor-not-allowed disabled:opacity-40"
          )}
        >
          <BookmarkPlus className="size-4" aria-hidden="true" />
        </button>

        {/* Watched button */}
        <button
          type="button"
          aria-pressed={false}
          aria-label="Mark as watched"
          title="Mark as watched"
          onClick={() => {}}
          className={cn(
            "rounded-full border border-white/25 bg-black/70 text-white/85 backdrop-blur-sm size-8 place-items-center transition-colors hover:border-white/60 hover:bg-black hover:text-white focus-visible:opacity-100 disabled:cursor-not-allowed disabled:opacity-40"
          )}
        >
          <BookmarkCheck className="size-4" aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}
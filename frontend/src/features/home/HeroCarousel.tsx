import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "../../utils/cn";
import { WatchlistButton } from "../watchlist/WatchlistButton";
import { buttonClasses } from "../../components/ui/Button";
import { formatYear } from "../../utils/format";
import { Poster } from "../../components/media/Poster";
import type { Movie } from "../../types/api";

const SLIDE_COUNT = 10;
const AUTO_SLIDE_INTERVAL = 5000;

interface HeroCarouselProps {
  items: Movie[];
}

export function HeroCarousel({ items }: HeroCarouselProps) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const navigate = useNavigate();

  const goToSlide = (index: number) => {
    setCurrentSlide(Math.max(0, Math.min(SLIDE_COUNT - 1, index)));
  };

  const nextSlide = () => {
    setCurrentSlide((prev) => (prev + 1) % SLIDE_COUNT);
  };

  useEffect(() => {
    const timeoutId = setInterval(nextSlide, AUTO_SLIDE_INTERVAL);

    return () => {
      clearInterval(timeoutId);
    };
  }, []);

  const currentItem = items[currentSlide] || items[0] || {} as Movie;
  const title = currentItem.title || "Top Pick";
  const displayYear = currentItem.year ?? null;
  const year = displayYear != null ? formatYear(displayYear) : "";

  return (
    <section className="relative isolate flex min-h-[42rem] items-end overflow-hidden sm:min-h-[46rem] lg:min-h-[52rem]">
      <div className="absolute inset-0 -z-10 bg-black">
        <Poster
          src={currentItem.poster_path}
          title={title}
          year={year}
          genre={currentItem.genres ? currentItem.genres.split("|")[0] ?? null : null}
        />
      </div>

      <div className="page-shell w-full pb-14 pt-36 sm:pb-16 lg:pb-24">
        <div className="max-w-2xl animate-fade-up">
          <p className="type-badge text-accent">Top picks for you</p>
          <h1 className="type-hero text-shadow-hero mt-3 text-white">
            {title}
          </h1>
          {year ? (
            <p className="meta-numeric mt-4 flex flex-wrap items-center gap-2 text-sm text-white/70">
              {year}
            </p>
          ) : null}
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <div className="min-w-[12rem]">
              <WatchlistButton titleId={currentItem.title_id} size="lg" />
            </div>
            <button
              onClick={() => {
                const serial = currentItem.serial_number || "tt0000000";
                navigate(`/movie/${serial}`);
              }}
              className={buttonClasses("primary", "lg")}
            >
              View details
            </button>
          </div>
        </div>
      </div>

      {/* Dot navigation */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
        {Array.from({ length: SLIDE_COUNT }, (_, i) => (
          <button
            key={i}
            type="button"
            className={cn(
              "bg-white/20 rounded-full p-2 hover:bg-white/30 transition-colors",
              currentSlide === i ? "bg-white" : "",
              "size-3",
            )}
            onClick={() => goToSlide(i)}
            aria-label={`Go to slide ${i + 1}`}
          />
        ))}
      </div>
    </section>
  );
}
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/endpoints";
import { isApiError } from "../../api/errors";
import { queryKeys } from "../../api/queryKeys";
import { Poster } from "../../components/media/Poster";
import { useAuth } from "../auth/AuthProvider";
import { useImpression } from "../interactions/useInteraction";
import type { InteractionEventType, RecommendationItem } from "../../types/api";
import { displayTitle } from "../../utils/displayTitle";
import { cn } from "../../utils/cn";
import { formatYear, parseGenres, recommendationReason } from "../../utils/format";
import { getTitleUrl } from "../../utils/titleRoute";

type Feedback = Extract<InteractionEventType, "like" | "dislike">;

interface RecommendationCardProps {
  item: RecommendationItem;
}

export function RecommendationCard({ item }: RecommendationCardProps) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const impressionRef = useImpression(item.title_id);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const title = displayTitle(item);
  const year = formatYear(item.year);
  const genre = parseGenres(item.genres)[0] ?? null;
  const reason = recommendationReason(item.reason);

  const mutation = useMutation({
    mutationFn: (eventType: Feedback) => api.recordInteraction(item.title_id, eventType),
    onSuccess: (_result, eventType) => {
      setFeedback(eventType);
      if (user) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.recommendations(user.id, 24) });
        void queryClient.invalidateQueries({ queryKey: ["home", user.id] });
      }
    },
  });

  return (
    <article ref={impressionRef} className="group flex min-w-0 flex-col border border-white/10 bg-[#0b0b0b]">
      <Link
        to={getTitleUrl(item)}
        className="block focus-visible:outline-offset-[-3px]"
        aria-label={`${title}${year ? `, ${year}` : ""}`}
      >
        <Poster
          src={item.poster_path}
          title={title}
          year={year}
          genre={genre}
          className="w-full rounded-none transition-transform duration-300 group-hover:brightness-110"
        />
      </Link>
      <div className="flex flex-1 flex-col p-3 sm:p-4">
        <Link to={getTitleUrl(item)} className="line-clamp-2 font-semibold text-white hover:text-white/75">
          {title}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          {year ? <span className="meta-numeric text-xs text-white/45">{year}</span> : null}
          {genre ? (
            <span className="border border-white/10 px-1.5 py-0.5 text-[0.625rem] font-medium uppercase tracking-[0.08em] text-white/55">
              {genre}
            </span>
          ) : null}
        </div>
        {reason ? <p className="mt-3 min-h-10 text-xs leading-relaxed text-white/60">{reason}</p> : null}
        <div className="mt-auto flex items-center justify-between gap-2 border-t border-white/10 pt-3" role="group" aria-label={`Feedback for ${title}`}>
          <span className="text-[0.6875rem] text-white/40" aria-live="polite">
            {feedback ? "Thanks, that helps." : "Good pick?"}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className={cn(
                "inline-flex size-8 items-center justify-center rounded-control border transition-colors duration-[var(--motion-fast)] disabled:cursor-not-allowed disabled:opacity-60",
                feedback === "like"
                  ? "border-accent/70 bg-accent/15 text-white"
                  : "border-white/10 text-white/55 hover:border-white/30 hover:text-white",
              )}
              aria-pressed={feedback === "like"}
              aria-label={`Recommend more like ${title}`}
              title="More like this"
              disabled={mutation.isPending || feedback !== null}
              onClick={() => mutation.mutate("like")}
            >
              <ThumbsUp className="size-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              className={cn(
                "inline-flex size-8 items-center justify-center rounded-control border transition-colors duration-[var(--motion-fast)] disabled:cursor-not-allowed disabled:opacity-60",
                feedback === "dislike"
                  ? "border-danger/60 bg-danger/10 text-danger"
                  : "border-white/10 text-white/55 hover:border-white/30 hover:text-white",
              )}
              aria-pressed={feedback === "dislike"}
              aria-label={`Show fewer like ${title}`}
              title="Fewer like this"
              disabled={mutation.isPending || feedback !== null}
              onClick={() => mutation.mutate("dislike")}
            >
              <ThumbsDown className="size-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
        {mutation.isError ? (
          <p className="mt-2 text-xs text-danger" role="alert">
            {isApiError(mutation.error) ? mutation.error.message : "Couldn't save your feedback."}
          </p>
        ) : null}
      </div>
    </article>
  );
}

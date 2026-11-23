import { BookmarkPlus, BookmarkCheck } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { buttonClasses } from "../../components/ui/Button";
import { isApiError } from "../../api/errors";
import { cn } from "../../utils/cn";
import { useAuth } from "../auth/AuthProvider";
import { useAddToWatchlist, useRemoveFromWatchlist, useWatchlist } from "./useWatchlist";

interface WatchlistButtonProps {
  titleId: string;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function WatchlistButton({ titleId, className, size = "md" }: WatchlistButtonProps) {
  const { status } = useAuth();
  const location = useLocation();
  const watchlist = useWatchlist();
  const add = useAddToWatchlist();
  const remove = useRemoveFromWatchlist();

  if (status !== "authenticated") {
    const redirect = encodeURIComponent(`${location.pathname}${location.search}`);
    return (
      <Link
        to={`/login?redirect=${redirect}`}
        className={buttonClasses("secondary", size, className)}
      >
        <BookmarkPlus className="size-4" aria-hidden="true" />
        Sign in to save
      </Link>
    );
  }

  const inWatchlist = Boolean(
    watchlist.data?.some((entry) => entry.title.title_id === titleId),
  );
  const pending = add.isPending || remove.isPending;
  const error = add.error ?? remove.error;

  return (
    <div className={cn("space-y-2", className)}>
      <button
        type="button"
        aria-pressed={inWatchlist}
        disabled={pending}
        onClick={() => {
          if (inWatchlist) {
            remove.mutate(titleId);
          } else {
            add.mutate(titleId);
          }
        }}
        className={buttonClasses(inWatchlist ? "ghost" : "secondary", size, "w-full border-line-strong")}
      >
        {inWatchlist ? (
          <BookmarkCheck className="size-4" aria-hidden="true" />
        ) : (
          <BookmarkPlus className="size-4" aria-hidden="true" />
        )}
        {pending
          ? inWatchlist
            ? "Removing..."
            : "Saving..."
          : inWatchlist
            ? "In watchlist"
            : "Add to watchlist"}
      </button>
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {isApiError(error) ? error.message : "Couldn't update your watchlist. Please try again."}
        </p>
      ) : null}
    </div>
  );
}

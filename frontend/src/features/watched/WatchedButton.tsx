import { BookmarkCheck, BookmarkPlus } from "lucide-react";
import { useLocation } from "react-router-dom";
import { buttonClasses } from "../../components/ui/Button";
import { isApiError } from "../../api/errors";
import { cn } from "../../utils/cn";
import { useAuth } from "../auth/AuthProvider";
import { useAddToWatched, useRemoveFromWatched, useWatchedEntry } from "./useWatched";

interface WatchedButtonProps {
  titleId: string;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function WatchedButton({ titleId, className, size = "md" }: WatchedButtonProps) {
  const { status } = useAuth();
  const location = useLocation();
  const watched = useWatchedEntry(titleId);
  const add = useAddToWatched();
  const remove = useRemoveFromWatched();

  if (status !== "authenticated") {
    return (
      <button
        type="button"
        className={buttonClasses("secondary", size, className)}
        onClick={() => {
          const redirect = encodeURIComponent(`${location.pathname}${location.search}`);
          window.location.href = `/login?redirect=${redirect}`;
        }}
      >
        <BookmarkPlus className="size-4" aria-hidden="true" />
        Sign in to save
      </button>
    );
  }

  const inWatched = watched.data?.title_id === titleId;
  const pending = add.isPending || remove.isPending;
  const error = add.error ?? remove.error;

  return (
    <div className={cn("space-y-2", className)}>
      <button
        type="button"
        aria-pressed={inWatched}
        disabled={pending}
        onClick={() => {
          if (inWatched) {
            remove.mutate(titleId);
          } else {
            add.mutate(titleId);
          }
        }}
        className={buttonClasses(
          inWatched ? "ghost" : "secondary",
          size,
          "w-full border-line-strong",
        )}
      >
        {inWatched ? (
          <BookmarkCheck className="size-4" aria-hidden="true" />
        ) : (
          <BookmarkPlus className="size-4" aria-hidden="true" />
        )}
        {pending
          ? inWatched
            ? "Removing..."
            : "Saving..."
          : inWatched
            ? "In watched"
            : "Add to watched"}
      </button>
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {isApiError(error) ? error.message : "Couldn't update your watched. Please try again."}
        </p>
      ) : null}
    </div>
  );
}
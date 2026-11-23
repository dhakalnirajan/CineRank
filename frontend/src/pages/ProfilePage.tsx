import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bookmark,
  CalendarDays,
  History,
  LogOut,
  Star,
  SlidersHorizontal,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/feedback/EmptyState";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { ErrorState } from "../components/feedback/ErrorState";
import { PosterGridSkeleton } from "../components/feedback/Skeletons";
import { Poster } from "../components/media/Poster";
import { Button } from "../components/ui/Button";
import { TextField } from "../components/ui/TextField";
import { useAuth } from "../features/auth/AuthProvider";
import { useWatchlist } from "../features/watchlist/useWatchlist";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { displayTitle } from "../utils/displayTitle";
import { formatDate, formatYear, parseGenres } from "../utils/format";
import { getTitleUrl } from "../utils/titleRoute";
import { mediaUrl } from "../utils/mediaUrl";

type ProfileTab = "history" | "watchlist";

interface ProfileCardItem {
  title_id: string;
  serial_number: string;
  media_type: string;
  title: string;
  display_title?: string;
  genres?: string;
  year?: number | null;
  poster_path?: string | null;
}

export default function ProfilePage() {
  useDocumentTitle("Profile");
  const { user, signOut } = useAuth();
  const history = useQuery({
    queryKey: queryKeys.history(user?.id ?? 0),
    queryFn: ({ signal }) => api.history(user?.id ?? 0, 200, signal),
    enabled: Boolean(user),
  });
  const watchlist = useWatchlist();
  const queryClient = useQueryClient();

  const sessions = useQuery({
    queryKey: ["auth", "sessions"],
    queryFn: ({ signal }) => api.sessions(signal),
    enabled: Boolean(user),
    staleTime: 30_000,
  });

  const revokeSession = useMutation({
    mutationFn: (sessionId: string) => api.revokeSession(sessionId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
  const logoutOtherSessions = useMutation({
    mutationFn: () => api.logoutOtherSessions(),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
  const resendVerification = useMutation({
    mutationFn: () => api.requestEmailVerification(),
  });

  const [editing, setEditing] = useState(false);
  const [username, setUsername] = useState(user?.username ?? "");
  const [email, setEmail] = useState(user?.email ?? "");

  useEffect(() => {
    if (!user || editing) return;
    setUsername(user.username);
    setEmail(user.email ?? "");
  }, [user, editing]);

  const onCancelEdit = () => {
    setEditing(false);
    setUsername(user.username);
    setEmail(user.email ?? "");
    setCurrentPassword("");
    setPassword("");
    setConfirmPassword("");
  };

  const onSubmitEdit = async () => {
    if (!user) return;
    setFormError(null);
    setSuccessMessage(null);
    try {
      await api.updateProfile(user.id, {
        username: username.trim(),
        email: email.trim() ? email.trim() : null,
        current_password: currentPassword || undefined,
        password: password ? password : undefined,
      });
      setSuccessMessage("Profile updated.");
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.me });
    } catch (err) {
      setFormError("Couldn't update your profile right now.");
    }
  };

  const tasteGenres = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of history.data?.items ?? []) {
      for (const genre of parseGenres(item.genres)) {
        counts.set(genre, (counts.get(genre) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5);
  }, [history.data]);

  if (!user) {
    return null;
  }

  const historyCount = history.data?.count ?? 0;
  const watchlistCount = watchlist.data?.length ?? 0;

  function LibraryCard({
    item,
    metaLabel,
  }: {
    item: ProfileCardItem;
    metaLabel: string;
  }) {
    const title = displayTitle(item);
    const year = formatYear(item.year);
    const genre = parseGenres(item.genres)[0] ?? null;

    return (
      <li key={item.title_id} className="min-w-0">
        <Link
          to={getTitleUrl(item)}
          className="group flex h-full flex-col rounded-xl border border-white/10 bg-[#0c0c0c] p-3 transition-[transform,border_color,background_color] duration-[var(--motion-base)] hover:-translate-y-1 hover:border-white/25 hover:bg-white/[0.04] focus-visible:outline-offset-4"
        >
          <div className="relative overflow-hidden rounded-lg bg-raised">
            <Poster
              src={item.poster_path}
              title={title}
              year={year}
              genre={genre}
              className="transition-transform duration-[var(--motion-slow)] ease-[var(--ease-out)] group-hover:scale-[1.03]"
            />
          </div>

          <div className="flex flex-1 flex-col px-0.5 pb-1 pt-3">
            <h3 className="type-card-title line-clamp-2 text-white transition-colors group-hover:text-white/85">
              {title}
            </h3>
            <p className="type-meta mt-auto pt-2.5 text-white/40">
              {metaLabel}
            </p>
            {genre ? (
              <span className="mt-2.5 w-fit border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[0.6875rem] font-medium text-white/55">
                {genre}
              </span>
            ) : null}
          </div>
        </Link>
      </li>
    );
  }

  function HistoryItem({
    item,
  }: {
    item: History["items"][0];
  }) {
    return (
      <li key={`${item.title_id}-${item.timestamp}`} className="min-w-0">
        <Link
          to={getTitleUrl(item)}
          className="group flex h-full flex-col rounded-xl border border-white/10 bg-[#0c0c0c] p-3 transition-[transform,border_color,background_color] duration-[var(--motion-base)] hover:-translate-y-1 hover:border-white/25 hover:bg-white/[0.04] focus-visible:outline-offset-4"
        >
          <div className="relative overflow-hidden rounded-lg bg-raised">
            <Poster
              src={item.poster_path}
              title={item.title}
              year={item.year}
              genre={item.genres ? item.genres.split("|")[0] : null}
              className="transition-transform duration-[var(--motion-slow)] ease-[var(--ease-out)] group-hover:scale-[1.03]"
            />
          </div>

          <div className="flex flex-1 flex-col px-0.5 pb-1 pt-3">
            <h3 className="type-card-title line-clamp-2 text-white transition-colors group-hover:text-white/85">
              {item.title}
            </h3>
            <p className="type-meta mt-auto pt-2.5 text-white/40">
              Rated {item.rating.toFixed(1)}/10 {formatDate(item.timestamp)}
            </p>
            {item.genres ? (
              <span className="mt-2.5 w-fit border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[0.6875rem] font-medium text-white/55">
                {item.genres.split("|")[0]}
              </span>
            ) : null}
          </div>
        </Link>
      </li>
    );
  }

  function WatchedItem({
    item,
  }: {
    item: WatchlistEntry["title"];
  }) {
    return (
      <li key={item.title_id} className="min-w-0">
        <Link
          to={getTitleUrl(item)}
          className="group flex h-full flex-col rounded-xl border border-white/10 bg-[#0c0c0c] p-3 transition-[transform,border_color,background_color] duration-[var(--motion-base)] hover:-translate-y-1 hover:border-white/25 hover:bg-white/[0.04] focus-visible:outline-offset-4"
        >
          <div className="relative overflow-hidden rounded-lg bg-raised">
            <Poster
              src={item.poster_path}
              title={item.title}
              year={item.year}
              genre={item.genres ? item.genres.split("|")[0] : null}
              className="transition-transform duration-[var(--motion-slow)] ease-[var(--ease-out)] group-hover:scale-[1.03]"
            />
          </div>

          <div className="flex flex-1 flex-col px-0.5 pb-1 pt-3">
            <h3 className="type-card-title line-clamp-2 text-white transition-colors group-hover:text-white/85">
              {item.title}
            </h3>
            <p className="type-meta mt-auto pt-2.5 text-white/40">
              Saved {formatDate(item.created_at) ?? "recently"}
            </p>
            {item.genres ? (
              <span className="mt-2.5 w-fit border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[0.6875rem] font-medium text-white/55">
                {item.genres.split("|")[0]}
              </span>
            ) : null}
          </div>
        </Link>
      </li>
    );
  }

  const editingSection = editing ? (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      >
      <section
        className="bg-[#0c0c0c] rounded-2xl border border-white/10 w-full max-w-lg mx-8 p-6 sm:p-8 shadow-lg overflow-y-auto max-h-[90vh]"
        >
        <h2 className="text-lg font-semibold text-white mb-6">Edit Profile</h2>
        <form onSubmit={onSubmitEdit} className="space-y-6"
          >
          <div className="grid grid-cols-2 gap-4 mb-6"
            >
            <TextField
              label="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={true}
            />
            <TextField
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-4 mb-6"
            >
            <TextField
              label="Current password"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
            <TextField
              label="New password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div>
            <Button type="submit" className="w-full"
              >
              Save changes
            </Button>
          </div>
          <div className="flex justify-end"
            >
            <button
              type="button"
              onClick={onCancelEdit}
              className="text-white/60 hover:text-white transition-colors"
              >
              Cancel
            </button>
          </div>
        </form>
      </section>
    </div>
  ) : null;

  return (
    <div className="page-shell py-10 sm:py-12">
      <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#0c0c0c]">
        <div className="h-24 bg-gray-900 sm:h-28">
        </div>
        <div className="relative p-5">
          <div className="-mt-10 flex flex-col gap-5 sm:-mt-12 sm:flex-row sm:items-end sm:justify-between">
            <div className="flex min-w-0 items-end gap-4">
              <div className="relative size-20 shrink-0 overflow-hidden rounded-full border border-white/20 bg-[radial-gradient(circle_at_30%_25%,#f6121d,#5c070b)] ring-4 ring-[#0c0c0c] sm:size-24">
                {user.avatar_url ? (
                  <img
                    src={mediaUrl(user.avatar_url)}
                    alt={`${user.username} avatar`}
                    className="size-full object-cover"
                  />
                ) : (
                  <span className="grid size-full place-items-center text-2xl font-bold uppercase text-white sm:text-3xl">
                    {user.username.slice(0, 1)}
                  </span>
                )
              }
              <div className="min-w-0 pb-1">
                <p className="type-badge text-accent">Your profile</p>
                <h1 className="mt-1.5 truncate text-3xl font-bold text-white sm:text-4xl">
                  {user.username}
                </h1>
                <p className="mt-1 truncate text-sm text-white/50">
                  {user.email ?? "No email on file"}
                </p>
                {tasteGenres.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {tasteGenres.map(([genre]) => (
                      <span
                        key={genre}
                        className="border border-white/10 bg-white/[0.04] px-2.5 py-1 text-xs font-medium text-white/70"
                      >
                        {genre}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>

            <div className="flex w-fit shrink-0 flex-wrap gap-2">
              <Link to="/preferences" className="inline-flex h-10 items-center gap-2 rounded-control border border-white/15 px-3 text-sm font-semibold text-white/80 transition-colors hover:border-white/40 hover:text-white">
                <SlidersHorizontal className="size-4" aria-hidden="true" />
                Taste settings
              </Link>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit profile
              </Button>
              <Button variant="secondary" onClick={signOut}>
                <LogOut className="size-4" aria-hidden="true" />
                Sign out
              </Button>
            </div>
          </div>
        </div>
      </section>

      {editingSection}

      <section aria-labelledby="profile-stats" className="mt-8">
        <h2 id="profile-stats" className="sr-only">
          Your activity
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <button
            type="button"
            className={cn(
              "rounded-xl border border-white/10 bg-[#0c0c0c] p-5 sm:p-6",
              tab === "history"
                ? "border-accent bg-accent text-white"
                : "border-white/10 bg-white/[0.02] text-white/60 hover:border-white/35 hover:text-white",
            )}
            onClick={() => setTab("history")}
          >
            <Star className="size-3 fill-accent text-accent" aria-hidden="true" />
            <span className="sr-only">Titles rated</span>
            {history.isLoading ? "-" : String(historyCount)}
          </button>
          <button
            type="button"
            className={cn(
              "rounded-xl border border-white/10 bg-[#0c0c0c] p-5 sm:p-6",
              tab === "watchlist"
                ? "border-accent bg-accent text-white"
                : "border-white/10 bg-white/[0.02] text-white/60 hover:border-white/35 hover:text-white",
            )}
            onClick={() => setTab("watchlist")}
          >
            <Bookmark className="size-3" aria-hidden="true" />
            <span className="sr-only">Watchlist</span>
            {watchlist.isLoading ? "-" : String(watchlistCount)}
          </button>
          <button
            type="button"
            className="rounded-xl border border-white/10 bg-[#0c0c0c] p-5 sm:p-6"
          >
            <CalendarDays className="size-3" aria-hidden="true" />
            <span className="sr-only">Member since</span>
            {formatDate(user.created_at) ?? "Unknown"}
          </button>
        </div>
      </section>

      <section className="mt-10" aria-label="Your library">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-4">
          <span className="type-meta text-white/40">
            {tab === "history"
              ? `${historyCount} ${historyCount === 1 ? "rating" : "ratings"}`
              : `${watchlistCount} ${watchlistCount === 1 ? "title" : "titles"} saved`}
          </span>
        </div>

        <div className="mt-6">
          {tab === "history" ? (
            <div>
              {history.isLoading ? (
                <PosterGridSkeleton count={10} />
              ) : history.isError ? (
                <ErrorState
                  title="We couldn't load your ratings"
                  message={isApiError(history.error)
                    ? history.error.message
                    : "Please try again in a moment."}
                  onRetry={() => void history.refetch()}
                />
              ) : history.data?.items.length === 0 ? (
                <EmptyState
                  icon={History}
                  title="No ratings yet"
                  message="Rate a few titles and your history will appear here."
                />
              ) : (
                <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                  {history.data?.items.map((item) => HistoryItem({ item }))}
                </ul>
              )}
            </div>
          ) : (
            <div>
              {watchlist.isLoading ? (
                <PosterGridSkeleton count={10} />
              ) : watchlist.isError ? (
                <ErrorState
                  title="We couldn't load your watchlist"
                  message={isApiError(watchlist.error)
                    ? watchlist.error.message
                    : "Please try again in a moment."}
                  onRetry={() => void watchlist.refetch()}
                />
              ) : watchlist.data?.length === 0 ? (
                <EmptyState
                  icon={Bookmark}
                  title="Nothing saved yet"
                  message="Save a title from Explore and it will show up here."
                />
              ) : (
                <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                  {watchlist.data?.map((entry) => WatchedItem({ item: entry.title }))}
                </ul>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
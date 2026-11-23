import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/endpoints";
import type { Movie } from "../../types/api";
import { cn } from "../../utils/cn";
import { parseGenres } from "../../utils/format";
import { useAuth } from "../../features/auth/AuthProvider";
import { buttonClasses } from "../ui/Button";
import { AccountMenu } from "./AccountMenu";
import { Logo } from "./Logo";
import { SearchInput } from "./SearchInput";
import { navItems } from "./navItems";

interface SearchHit {
  id: string;
  to: string;
  title: string;
  displayTitle: string | undefined;
  year: number | null;
  rating: number | null;
  type: string;
  genre: string | null;
  poster: string | null;
}

function makeSearchHit(m: Movie): SearchHit {
  const raw = m.title ?? "";
  const genre = parseGenres(m.genres)[0] ?? null;
  return {
    id: m.title_id,
    to: `/${m.media_type}/${m.serial_number}`,
    title: raw,
    displayTitle: m.display_title ?? undefined,
    year: m.year,
    rating: m.vote_average,
    type: m.media_type === "tv" ? "Series" : "Movie",
    genre,
    poster: m.poster_path,
  };
}

export function Header() {
  const { status, user, signOut } = useAuth();
  const location = useLocation();
  const isHome = location.pathname === "/";
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [location.pathname]);

  const visibleNavItems = navItems.filter(
    (item) => !item.requiresAuth || status === "authenticated",
  );
  const solid = scrolled || !isHome;
  const barSurface = solid
    ? "border-b border-zinc-800/80 bg-[#0A0A0A]/95 backdrop-blur-md"
    : "border-b border-transparent bg-gradient-to-b from-black/90 via-black/45 to-transparent";

  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 260);
    return () => window.clearTimeout(timer);
  }, [query]);

  const searchQueryString = debouncedQuery.length >= 2 ? debouncedQuery : undefined;
  const searchQueryStringStable = useMemo(() => searchQueryString, [searchQueryString]);

  const {
    data: searchData,
    isLoading: searchLoading,
    error: searchError,
  } = useQuery({
    queryKey: ["header-search", searchQueryStringStable],
    queryFn: ({ signal }) =>
      searchQueryStringStable
        ? api.search(searchQueryStringStable, 8, signal)
        : Promise.resolve({ query: "", count: 0, results: [] }),
    enabled: Boolean(searchQueryStringStable),
    staleTime: 0,
    retry: false,
  });

  const hits = useMemo(() => {
    if (!searchData) return [];
    const results = searchData.results ?? [];
    return results.slice(0, 8).map(makeSearchHit);
  }, [searchData]);

  const moreAvailable = useMemo(
    () => Boolean(searchData && searchData.count > (searchData.results?.length ?? 0)),
    [searchData],
  );

  const open = searchOpen && query.trim().length >= 2;
  const loading = query.trim().length >= 2 && (searchLoading || debouncedQuery !== query.trim());

  const handleChange = useCallback((value: string) => {
    setQuery(value);
    setSearchOpen(value.trim().length >= 2);
  }, []);

  const handleClear = useCallback(() => {
    setQuery("");
    setDebouncedQuery("");
    setSearchOpen(false);
  }, []);

  const handleClose = useCallback(() => setSearchOpen(false), []);

  const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setSearchOpen(false);
      event.currentTarget.blur();
    } else if (event.key === "Enter" && query.trim().length >= 2) {
      setSearchOpen(true);
    }
  }, [query]);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 h-[var(--header-height)] transition-colors duration-300",
        barSurface,
      )}
      aria-label="Site header"
    >
      <div className="page-shell flex h-full items-center gap-3 sm:gap-4 lg:gap-6">
        <div className="flex shrink-0 items-center gap-3 xl:gap-5">
          <Logo compact />

          <nav
            aria-label="Primary"
            className="hidden items-center gap-1 border-l border-white/10 pl-4 lg:flex"
          >
            {visibleNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "relative px-2.5 py-1.5 text-[0.8125rem] font-medium transition-colors duration-[var(--motion-fast)] after:absolute after:inset-x-3 after:-bottom-0.5 after:h-0.5 after:origin-left after:bg-orange-500 after:transition-transform after:content-['']",
                    isActive
                      ? "text-white after:scale-x-100"
                      : "text-white/60 after:scale-x-0 hover:text-white",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex min-w-0 flex-1 items-center justify-center sm:px-2">
          <div className="w-full max-w-[24rem]">
            <SearchInput
              value={query}
              onChange={handleChange}
              onClear={handleClear}
              onKeyDown={handleKeyDown}
              loading={Boolean(loading)}
              hits={hits}
              moreAvailable={Boolean(moreAvailable)}
              open={open}
              onClose={handleClose}
              error={searchError ? "Search could not be completed. Try again." : null}
            />
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 lg:min-w-[13rem]">
          {status === "authenticated" && user ? (
            <AccountMenu
              username={user.username}
              email={user.email}
              avatarUrl={user.avatar_url}
              onSignOut={signOut}
            />
          ) : status === "anonymous" ? (
            <>
              <Link to="/login" className={buttonClasses("ghost", "sm")}>
                Sign in
              </Link>
              <Link
                to="/register"
                className={cn(buttonClasses("primary", "sm"), "hidden sm:inline-flex")}
              >
                Join CineRank
              </Link>
            </>
          ) : (
            <div
              className="flex h-8 w-24 items-center justify-end"
              aria-hidden="true"
            >
              <span className="size-7 animate-pulse rounded-full bg-white/10" />
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

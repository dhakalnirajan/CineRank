import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { WatchlistButton } from "../../features/watchlist/WatchlistButton";

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

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLInputElement>) => void;
  loading: boolean;
  hits: SearchHit[];
  moreAvailable: boolean;
  open: boolean;
  onClose: () => void;
  error?: string | null;
}

function displayText(hit: SearchHit): string {
  return hit.displayTitle ?? hit.title;
}

export function SearchInput({
  value,
  onChange,
  onClear,
  onKeyDown,
  loading,
  hits,
  moreAvailable,
  open,
  onClose,
  error,
}: SearchInputProps) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const [activeIndex, setActiveIndex] = useState<number>(-1);


  const normalizedQuery = useMemo(() => {
    const raw = value.trim();
    if (!raw) return "";
    return raw.replace(/^(a|an|the)\s+/i, "");
  }, [value]);

  const hasQuery = normalizedQuery.length > 0;

  const scrollActiveIntoView = useCallback((index: number) => {
    const list = listRef.current;
    const active = list?.children[index] as HTMLElement | undefined;
    if (!list || !active) return;
    if (active.offsetTop < list.scrollTop) {
      list.scrollTop = active.offsetTop - 4;
    } else if (
      active.offsetTop + active.offsetHeight >
      list.scrollTop + list.clientHeight
    ) {
      list.scrollTop =
        active.offsetTop + active.offsetHeight - list.clientHeight + 4;
    }
  }, []);

  const moveActive = useCallback(
    (delta: number) => {
      const next = Math.max(-1, Math.min(hits.length - 1, activeIndex + delta));
      setActiveIndex(next);
      scrollActiveIntoView(next);
    },
    [activeIndex, hits.length, scrollActiveIntoView],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveActive(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        moveActive(-1);
      } else if (event.key === "Enter") {
        const target = activeIndex >= 0 ? hits[activeIndex] : undefined;
        event.preventDefault();
        if (target) {
          navigate(target.to);
          onClose();
        } else if (hasQuery) {
          navigate(`/search?q=${encodeURIComponent(normalizedQuery)}`);
          onClose();
        } else {
          onKeyDown(event);
        }
      } else if (event.key === "Escape") {
        onClose();
        inputRef.current?.blur();
      } else {
        onKeyDown(event);
      }
    },
    [activeIndex, hits, moveActive, navigate, onClose, onKeyDown, hasQuery, normalizedQuery],
  );


  return (
    <div className="relative">
      <div className="flex min-h-10 w-full items-center gap-2 rounded-lg border border-zinc-800 bg-[#121215] px-3 transition-colors focus-within:border-orange-500 focus-within:bg-[#121215]">
        <svg className="size-3.5 shrink-0 text-white/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
        </svg>
        <input
          ref={inputRef}
          type="text"
          inputMode="search"
          placeholder="Search titles..."
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (value.trim()) setActiveIndex(-1); }}
          className="h-9 min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-white/30"
          autoComplete="off"
          enterKeyHint="search"
          aria-label="Search titles"
          aria-autocomplete="list"
          aria-controls="header-search-results"
          aria-expanded={open}
        />
        {hasQuery ? (
          <button type="button" onClick={() => { onClear(); inputRef.current?.focus(); }} className="shrink-0 rounded text-white/40 transition-colors hover:text-white/70" aria-label="Clear search">
            <svg className="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        ) : null}
      </div>

      {open ? (
        <>
          <button
            type="button"
            tabIndex={-1}
            aria-label="Close search results"
            className="fixed inset-x-0 bottom-0 top-[var(--header-height)] z-40 cursor-default bg-black/70 backdrop-blur-[2px]"
            onClick={onClose}
          />
          <section
            id="header-search-results"
            role="dialog"
            aria-modal="true"
            aria-label={`Search results for ${normalizedQuery}`}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                onClose();
                inputRef.current?.focus();
              }
            }}
            className="fixed left-1/2 top-[calc(var(--header-height)+0.75rem)] z-40 w-[calc(100vw-1.5rem)] max-w-2xl -translate-x-1/2 overflow-hidden rounded-2xl border border-white/10 bg-[#101012] shadow-[0_24px_100px_rgb(0_0_0/0.7)]"
          >
            <div className="flex items-center justify-between gap-4 border-b border-white/10 px-5 py-4">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-400">Catalogue search</p>
                <p className="mt-1 truncate text-sm text-white/75">Results for <span className="font-semibold text-white">{normalizedQuery}</span></p>
              </div>
              <button type="button" onClick={onClose} aria-label="Close search results" className="grid size-9 shrink-0 place-items-center rounded-full border border-white/10 text-white/60 transition-colors hover:bg-white/10 hover:text-white">
                <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="m18 6-12 12M6 6l12 12" /></svg>
              </button>
            </div>
            <div ref={listRef} className="max-h-[min(66vh,38rem)] overflow-y-auto p-2" role="listbox" aria-label="Matching catalogue titles">
              {loading ? (
                <div className="space-y-1" aria-label="Loading search results">
                  {Array.from({ length: 5 }).map((_, index) => (
                    <div key={index} className="flex animate-pulse items-center gap-3 rounded-xl px-3 py-2.5">
                      <div className="h-[68px] w-[46px] shrink-0 rounded bg-zinc-800/70" />
                      <div className="min-w-0 flex-1 space-y-2"><div className="h-3 w-2/3 rounded bg-zinc-800/70" /><div className="h-2.5 w-1/3 rounded bg-zinc-800/50" /></div>
                    </div>
                  ))}
                </div>
              ) : error ? (
                <p className="px-5 py-10 text-center text-sm text-red-300" role="alert">{error}</p>
              ) : !hasQuery ? (
                <p className="px-5 py-10 text-center text-sm text-white/45">Type a title to search the CineRank catalogue.</p>
              ) : hits.length === 0 ? (
                <div className="px-5 py-12 text-center"><p className="text-sm font-medium text-white/80">No matching titles found</p><p className="mt-1 text-xs text-white/40">Try a different title or spelling.</p></div>
              ) : (
                <div className="space-y-1">
                  {hits.map((hit, index) => (
                    <div
                      key={hit.id}
                      className={`flex min-w-0 items-center gap-3 rounded-xl px-3 py-2.5 transition-colors ${index === activeIndex ? "bg-white/10" : "hover:bg-white/[0.06]"}`}
                    >
                      <Link
                        to={hit.to}
                        onClick={onClose}
                        onMouseEnter={() => setActiveIndex(index)}
                        className="flex min-w-0 flex-1 items-center gap-3"
                      >
                        {hit.poster ? (
                          <img src={hit.poster} alt="" className="h-[68px] w-[46px] shrink-0 rounded-md bg-white/5 object-cover" loading="lazy" />
                        ) : (
                          <div className="grid h-[68px] w-[46px] shrink-0 place-items-center rounded-md bg-gradient-to-br from-[#3a0e14] to-[#0b0304] text-xs font-semibold uppercase text-orange-200/80" aria-hidden="true">
                            {hit.title.trim().split(/\s+/)[0]?.slice(0, 2).toUpperCase() || "CR"}
                          </div>
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-white">{displayText(hit)}</p>
                          <p className="mt-1 truncate text-xs text-white/50">
                            {hit.year ?? "Year unavailable"}{hit.genre ? ` · ${hit.genre}` : ""}{hit.type ? ` · ${hit.type}` : ""}
                          </p>
                        </div>
                        <span className="hidden shrink-0 text-xs font-medium text-orange-400 sm:inline">View title</span>
                      </Link>
                      <WatchlistButton titleId={hit.id} size="sm" className="w-auto shrink-0 px-2.5" />
                    </div>
                  ))}
                </div>
              )}
            </div>
            {!loading && !error && hits.length > 0 ? (
              <div className="flex items-center justify-between gap-4 border-t border-white/10 px-5 py-3">
                <span className="text-xs text-white/40">{moreAvailable ? "Showing top matches" : `${hits.length} result${hits.length === 1 ? "" : "s"}`}</span>
                <button type="button" className="text-xs font-semibold text-orange-400 transition-colors hover:text-orange-300" onClick={() => { navigate(`/search?q=${encodeURIComponent(normalizedQuery || value)}`); onClose(); }}>View all results</button>
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </div>
  );
}

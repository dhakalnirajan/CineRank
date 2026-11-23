import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, SlidersHorizontal } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { ErrorState } from "../components/feedback/ErrorState";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { PageHeader } from "../components/ui/PageHeader";
import { Button } from "../components/ui/Button";
import { useAuth } from "../features/auth/AuthProvider";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import type { UserPreferences } from "../types/api";

const DEFAULTS: UserPreferences = {
  preferred_genres: [], excluded_genres: [], include_adult: false,
  min_year: null, max_runtime: null,
};

export default function PreferencesPage() {
  useDocumentTitle("Taste settings");
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const preferences = useQuery({
    queryKey: ["preferences", user?.id ?? 0],
    queryFn: ({ signal }) => api.getPreferences(signal),
    enabled: Boolean(user),
  });
  const facets = useQuery({
    queryKey: ["catalogue", "facets"],
    queryFn: ({ signal }) => api.catalogueFacets(signal),
    staleTime: 10 * 60_000,
  });
  const [draft, setDraft] = useState<UserPreferences>(DEFAULTS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (preferences.data) setDraft({ ...DEFAULTS, ...preferences.data });
  }, [preferences.data]);

  const genres = useMemo(
    () => (facets.data?.genres ?? []).map((item) => item.value).filter(Boolean).sort(),
    [facets.data],
  );

  const save = useMutation({
    mutationFn: () => api.updatePreferences({
      preferred_genres: draft.preferred_genres,
      excluded_genres: draft.excluded_genres,
      include_adult: draft.include_adult,
      min_year: draft.min_year,
      max_runtime: draft.max_runtime,
    }),
    onSuccess: (value) => {
      setDraft({ ...DEFAULTS, ...value });
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["preferences", user?.id ?? 0] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations", user?.id ?? 0] });
      void queryClient.invalidateQueries({ queryKey: ["home", user?.id ?? 0] });
    },
  });

  const toggle = (field: "preferred_genres" | "excluded_genres", genre: string) => {
    setSaved(false);
    setDraft((current) => {
      const values = current[field];
      const next = values.includes(genre)
        ? values.filter((value) => value !== genre)
        : [...values, genre];
      const other = field === "preferred_genres" ? "excluded_genres" : "preferred_genres";
      return { ...current, [field]: next, [other]: current[other].filter((value) => !next.includes(value)) };
    });
  };

  if (preferences.isLoading) {
    return <div className="page-shell py-12"><p className="text-sm text-white/55">Loading taste settings…</p></div>;
  }
  if (preferences.isError) {
    return <div className="page-shell py-12"><ErrorState title="Couldn't load preferences" message={isApiError(preferences.error) ? preferences.error.message : "Try again."} onRetry={() => void preferences.refetch()} /></div>;
  }

  return (
    <div className="page-shell py-10 sm:py-12">
      <Link to="/profile" className="mb-6 inline-flex items-center gap-2 text-sm text-white/55 transition-colors hover:text-white">
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to profile
      </Link>
      <PageHeader
        eyebrow="Personalization"
        title="Taste settings"
        description="Choose genres and content limits to shape your recommendations. Your ratings and viewing activity remain separate signals."
      />

      {saved ? <div className="mt-5"><InlineNotice tone="success">Preferences saved. Your recommendations will reflect these settings.</InlineNotice></div> : null}
      {save.isError ? <div className="mt-5"><InlineNotice tone="error">{isApiError(save.error) ? save.error.message : "Preferences could not be saved."}</InlineNotice></div> : null}

      <section className="mt-8 rounded-xl border border-white/10 bg-white/[0.025] p-5 sm:p-7">
        <div className="mb-5 flex items-center gap-3">
          <SlidersHorizontal className="size-5 text-accent" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-white">Genre preferences</h2>
        </div>
        <p className="mb-4 text-sm text-white/50">Preferred genres receive a modest ranking boost. Excluded genres are filtered out.</p>
        {facets.isLoading ? <p className="text-sm text-white/50">Loading available genres…</p> : null}
        {facets.isError ? <p className="text-sm text-amber-200">Genre list unavailable. You can still save other settings.</p> : null}
        <div className="grid gap-5 md:grid-cols-2">
          <GenreSelector title="Prefer" selected={draft.preferred_genres} genres={genres} onToggle={(genre) => toggle("preferred_genres", genre)} />
          <GenreSelector title="Exclude" selected={draft.excluded_genres} genres={genres} onToggle={(genre) => toggle("excluded_genres", genre)} />
        </div>
      </section>

      <section className="mt-5 rounded-xl border border-white/10 bg-white/[0.025] p-5 sm:p-7">
        <h2 className="text-lg font-semibold text-white">Content controls</h2>
        <label className="mt-5 flex cursor-pointer items-start gap-3 text-sm text-white/80">
          <input type="checkbox" className="mt-0.5 size-4 accent-red-500" checked={draft.include_adult} onChange={(event) => { setSaved(false); setDraft((current) => ({ ...current, include_adult: event.target.checked })); }} />
          <span><span className="block font-medium text-white">Include adult titles</span><span className="mt-1 block text-xs text-white/45">Off by default. When enabled, titles marked adult by the catalogue may appear.</span></span>
        </label>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <label className="text-sm text-white/70">Minimum release year
            <input type="number" min={1888} max={2100} value={draft.min_year ?? ""} onChange={(event) => { setSaved(false); setDraft((current) => ({ ...current, min_year: event.target.value ? Number(event.target.value) : null })); }} placeholder="Any year" className="mt-2 h-11 w-full rounded-control border border-white/15 bg-black/30 px-3 text-white outline-none focus:border-white/50" />
          </label>
          <label className="text-sm text-white/70">Maximum runtime (minutes)
            <input type="number" min={30} max={600} value={draft.max_runtime ?? ""} onChange={(event) => { setSaved(false); setDraft((current) => ({ ...current, max_runtime: event.target.value ? Number(event.target.value) : null })); }} placeholder="No limit" className="mt-2 h-11 w-full rounded-control border border-white/15 bg-black/30 px-3 text-white outline-none focus:border-white/50" />
          </label>
        </div>
      </section>

      <div className="mt-6 flex justify-end">
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={save.isPending}>
          <Check className="size-4" aria-hidden="true" /> Save preferences
        </Button>
      </div>
    </div>
  );
}

function GenreSelector({ title, selected, genres, onToggle }: {
  title: string; selected: string[]; genres: string[]; onToggle: (genre: string) => void;
}) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-white">{title}</h3>
      <div className="flex max-h-64 flex-wrap gap-2 overflow-y-auto pr-1">
        {genres.map((genre) => {
          const active = selected.includes(genre);
          return <button key={genre} type="button" aria-label={`${title} ${genre}`} aria-pressed={active} onClick={() => onToggle(genre)} className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${active ? "border-accent bg-accent/15 text-white" : "border-white/10 bg-white/[0.03] text-white/55 hover:border-white/30 hover:text-white"}`}>{genre}</button>;
        })}
        {!genres.length ? <span className="text-xs text-white/40">No genres available.</span> : null}
      </div>
    </div>
  );
}

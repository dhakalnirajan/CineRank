import { CineRankMark } from "../navigation/Logo";

export function PageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div
      className="flex min-h-[50vh] flex-col items-center justify-center gap-5 px-6"
      role="status"
      aria-live="polite"
    >
      <div className="relative grid place-items-center">
        <span
          className="absolute size-16 rounded-full bg-accent/15 blur-xl"
          aria-hidden="true"
        />
        <CineRankMark className="relative size-11" />
      </div>
      <div
        className="h-0.5 w-28 overflow-hidden rounded-full bg-white/10"
        aria-hidden="true"
      >
        <span className="loader-sweep block h-full w-1/2 rounded-full bg-accent" />
      </div>
      <span className="text-sm text-muted">{label}</span>
    </div>
  );
}

import { Link } from "react-router-dom";

export function CineRankMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="0.75"
        y="0.75"
        width="62.5"
        height="62.5"
        rx="13.25"
        fill="#050505"
        stroke="#262626"
        strokeWidth="1.5"
      />
      <path
        d="M43.6 18.2A18 18 0 1 0 43.6 45.8"
        fill="none"
        stroke="#ffffff"
        strokeWidth="7"
      />
      <path d="M27.5 23.5 40 32 27.5 40.5Z" fill="#e50914" />
    </svg>
  );
}

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link
      to="/"
      className="group inline-flex shrink-0 items-center gap-2.5 focus-visible:outline-offset-4"
      aria-label="CineRank home"
    >
      <CineRankMark className={compact ? "size-7" : "size-8"} />
      <span
        className={
          compact
            ? "font-display text-lg font-extrabold leading-none tracking-[-0.045em]"
            : "font-display text-[1.35rem] font-extrabold leading-none tracking-[-0.045em]"
        }
      >
        <span className="text-white transition-colors group-hover:text-white/85">Cine</span>
        <span className="text-accent">Rank</span>
      </span>
    </Link>
  );
}

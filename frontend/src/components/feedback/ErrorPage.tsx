import type { ReactNode } from "react";

interface ErrorPageProps {
  code: string;
  title: string;
  message: string;
  actions: ReactNode;
}

export function ErrorPage({ code, title, message, actions }: ErrorPageProps) {
  return (
    <div className="relative isolate flex min-h-[72vh] items-center overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(90%_120%_at_10%_0%,rgb(229_9_20/0.16),transparent_58%),linear-gradient(145deg,#0d0506_0%,#000000_52%,#080303_100%)]"
        aria-hidden="true"
      />

      <div className="page-shell grid w-full gap-10 py-16 sm:py-20 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <div>
          <p className="type-badge text-accent">Error {code}</p>
          <h1 className="mt-4 max-w-2xl text-4xl font-bold leading-[1.05] text-white sm:text-6xl">
            {title}
          </h1>
          <p className="mt-5 max-w-lg text-sm leading-relaxed text-white/60 sm:text-base">
            {message}
          </p>
          <div className="mt-9 flex flex-wrap gap-3">{actions}</div>
        </div>

        <div
          className="relative hidden aspect-square max-h-[28rem] justify-self-end overflow-hidden rounded-2xl border border-white/10 bg-[#0c0c0c] lg:block"
          aria-hidden="true"
        >
          <div className="absolute inset-0 bg-[radial-gradient(120%_100%_at_22%_10%,rgb(229_9_20/0.36),transparent_60%),linear-gradient(145deg,#241014_0%,#080606_58%,#030303_100%)]" />
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 border-y border-white/10 py-5">
            <p className="text-center font-display text-[7.5rem] font-extrabold leading-none tracking-[-0.08em] text-white/[0.07]">
              {code}
            </p>
          </div>
          <div className="absolute inset-x-6 bottom-6 flex items-center justify-between text-[0.625rem] font-semibold uppercase tracking-[0.18em] text-white/30">
            <span>CineRank</span>
            <span>Off screen</span>
          </div>
        </div>
      </div>
    </div>
  );
}

import { cn } from "../../utils/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded-control", className)} aria-hidden="true" />;
}

export function PosterCardSkeleton() {
  return (
    <div>
      <Skeleton className="poster-frame w-full rounded-poster" />
      <Skeleton className="mt-3 h-4 w-4/5" />
      <Skeleton className="mt-2 h-3 w-1/2" />
    </div>
  );
}

export function HomeHeroSkeleton() {
  return (
    <section
      className="relative flex min-h-[36rem] items-end overflow-hidden bg-[#080808] sm:min-h-[40rem] lg:min-h-[46rem]"
      role="status"
      aria-label="Loading your top pick"
    >
      <div className="page-shell w-full pb-14 pt-36 sm:pb-16 lg:pb-24">
        <div className="max-w-2xl space-y-4">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-14 w-4/5 max-w-xl" />
          <Skeleton className="h-4 w-24" />
          <div className="flex gap-2">
            <Skeleton className="h-7 w-20" />
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-7 w-16" />
          </div>
          <Skeleton className="h-4 w-72" />
          <div className="flex gap-3 pt-3">
            <Skeleton className="h-12 w-44" />
            <Skeleton className="h-12 w-36" />
          </div>
        </div>
      </div>
    </section>
  );
}

export function PosterGridSkeleton({ count = 12 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
      role="status"
      aria-label="Loading titles"
    >
      {Array.from({ length: count }, (_, index) => (
        <PosterCardSkeleton key={index} />
      ))}
    </div>
  );
}

export function RecommendationRowSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading recommendations">
      <Skeleton className="h-6 w-48" />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, index) => (
          <PosterCardSkeleton key={index} />
        ))}
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { cn } from "../../utils/cn";
import { isRenderableImageUrl } from "../../utils/format";
import { PosterShapeArt } from "./PosterShapeArt";
import { posterShape } from "./posterShapeMath";

interface PosterProps {
  src: string | null | undefined;
  title: string;
  year?: string | null;
  genre?: string | null;
  className?: string;
  priority?: boolean;
}

export function Poster({
  src,
  title,
  year,
  genre,
  className,
  priority = false,
}: PosterProps) {
  const [failed, setFailed] = useState(false);
  const url = isRenderableImageUrl(src);
  const shape = useMemo(() => posterShape(`${title}|${year ?? ""}`), [title, year]);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  return (
    <div className={cn("poster-frame relative overflow-hidden bg-raised", className)}>
      {url && !failed ? (
        <>
          <img
            src={url}
            alt=""
            loading={priority ? "eager" : "lazy"}
            decoding="async"
            className="size-full object-cover"
            onError={() => setFailed(true)}
          />
          <PosterShapeArt
            shape={shape}
            intensity={0.8}
            className="mix-blend-screen"
          />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />
        </>
      ) : (
        <div
          role="img"
          aria-label="Artwork unavailable"
          className="poster-fallback-art relative size-full overflow-hidden"
        >
          <div className="absolute inset-0 bg-[radial-gradient(120%_90%_at_18%_8%,rgb(229_9_20/0.42),transparent_55%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(100%_75%_at_88%_92%,rgb(120_42_8/0.42),transparent_62%)]" />
          <PosterShapeArt shape={shape} intensity={1.6} className="mix-blend-screen" />
          <div className="relative flex size-full flex-col justify-between p-3 sm:p-4">
            <span className="poster-blurb w-fit border border-white/20 bg-black/20 px-1.5 py-0.5 text-[0.5625rem] font-semibold uppercase tracking-[0.12em] text-white/70">
              {genre ?? "CineRank"}
            </span>
            <div className="poster-blurb-body">
              <p className="poster-blurb-title line-clamp-4 font-display text-[0.95rem] font-bold leading-tight text-white/90 sm:text-base">
                {title}
              </p>
              {year ? (
                <p className="meta-numeric mt-1.5 text-[0.6875rem] font-medium tracking-[0.12em] text-white/45">
                  {year}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

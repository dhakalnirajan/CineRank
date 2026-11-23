import { useEffect, useState } from "react";
import { cn } from "../../utils/cn";
import { isRenderableImageUrl } from "../../utils/format";

interface BackdropProps {
  src: string | null | undefined;
  title: string;
  className?: string;
}

export function Backdrop({ src, title, className }: BackdropProps) {
  const [failed, setFailed] = useState(false);
  const url = isRenderableImageUrl(src);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  return (
    <div
      className={cn(
        "backdrop-frame relative overflow-hidden bg-gradient-to-br from-[#1a0b0e] via-black to-black",
        className,
      )}
    >
      {url && !failed ? (
        <img
          src={url}
          alt={`Backdrop for ${title}`}
          loading="eager"
          decoding="async"
          className="size-full object-cover object-center"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="hero-glow size-full" aria-hidden="true" />
      )}
    </div>
  );
}

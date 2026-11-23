import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { IconButton } from "../ui/IconButton";

interface ScrollRowProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  /** Called while the rail is still about a viewport away from its end. */
  onNearEnd?: () => void;
  trailing?: ReactNode;
}

export function ScrollRow({
  title,
  subtitle,
  action,
  children,
  onNearEnd,
  trailing,
}: ScrollRowProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const nearEndRef = useRef(onNearEnd);
  const hasNearEnd = Boolean(onNearEnd);

  useEffect(() => {
    nearEndRef.current = onNearEnd;
  }, [onNearEnd]);

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node || !hasNearEnd) {
      return;
    }
    let frame = 0;
    const check = () => {
      frame = 0;
      const remaining = node.scrollWidth - node.scrollLeft - node.clientWidth;
      // Load roughly one viewport early so new cards arrive before the edge.
      if (remaining <= node.clientWidth * 1.2) {
        nearEndRef.current?.();
      }
    };
    const onScroll = () => {
      if (frame) {
        return;
      }
      frame = requestAnimationFrame(check);
    };
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      node.removeEventListener("scroll", onScroll);
      if (frame) {
        cancelAnimationFrame(frame);
      }
    };
  }, [hasNearEnd]);
  const headingId = `row-${title.replace(/\s+/g, "-").toLowerCase()}`;

  const scrollByPage = (direction: -1 | 1) => {
    const node = scrollerRef.current;
    if (!node) {
      return;
    }
    node.scrollBy({ left: direction * node.clientWidth * 0.82, behavior: "smooth" });
  };

  return (
    <section aria-labelledby={headingId} className="group/row relative">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id={headingId} className="type-rail-title text-white">
            {title}
          </h2>
          {subtitle ? (
            <p className="mt-1 max-w-2xl text-[0.8125rem] leading-relaxed text-white/50">
              {subtitle}
            </p>
          ) : null}
        </div>
        {action ? <div>{action}</div> : null}
      </div>

      <div className="relative">
        <div
          ref={scrollerRef}
          className="rail-fade hide-scrollbar flex snap-x snap-mandatory gap-5 overflow-x-auto overscroll-x-contain px-1 py-3 sm:gap-6"
        >
          {children}
          {trailing}
        </div>

        <IconButton
          label={`Scroll ${title} left`}
          onClick={() => scrollByPage(-1)}
          className="absolute left-0 top-1/2 z-10 hidden -translate-y-1/2 opacity-0 group-hover/row:opacity-100 group-focus-within/row:opacity-100 lg:inline-flex"
        >
          <ChevronLeft className="size-5" aria-hidden="true" />
        </IconButton>
        <IconButton
          label={`Scroll ${title} right`}
          onClick={() => scrollByPage(1)}
          className="absolute right-0 top-1/2 z-10 hidden -translate-y-1/2 opacity-0 group-hover/row:opacity-100 group-focus-within/row:opacity-100 lg:inline-flex"
        >
          <ChevronRight className="size-5" aria-hidden="true" />
        </IconButton>
      </div>
    </section>
  );
}

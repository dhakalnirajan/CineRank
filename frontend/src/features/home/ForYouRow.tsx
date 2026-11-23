import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../../api/endpoints";
import { PosterRow } from "../../components/media/PosterRow";
import { buttonClasses } from "../../components/ui/Button";
import type { RecommendationItem } from "../../types/api";

const MORE_COUNT = 6;

interface ForYouRowProps {
  userId: number;
  items: RecommendationItem[];
  nextCursor: string | null;
  action?: ReactNode;
}

export function ForYouRow({ userId, items, nextCursor, action }: ForYouRowProps) {
  const [extra, setExtra] = useState<RecommendationItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(nextCursor);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const loadingRef = useRef(false);

  useEffect(() => {
    setExtra([]);
    setCursor(nextCursor);
    setFailed(false);
  }, [items, nextCursor]);

  const loadMore = useCallback(() => {
    if (!cursor || loadingRef.current) {
      return;
    }
    loadingRef.current = true;
    setLoading(true);
    setFailed(false);
    void api
      .homeMore(userId, MORE_COUNT, cursor)
      .then((page) => {
        setExtra((previous) => {
          const known = new Set([...items, ...previous].map((item) => item.title_id));
          return [...previous, ...page.items.filter((item) => !known.has(item.title_id))];
        });
        setCursor(page.next_cursor);
      })
      .catch(() => setFailed(true))
      .finally(() => {
        loadingRef.current = false;
        setLoading(false);
      });
  }, [cursor, items, userId]);

  const combined = [...items, ...extra];
  const trailing = loading ? (
    <p className="w-36 shrink-0 self-center text-xs text-white/45" role="status">
      Loading more titles
    </p>
  ) : failed ? (
    <button
      type="button"
      className={buttonClasses("ghost", "sm", "shrink-0 self-center")}
      onClick={loadMore}
    >
      Retry
    </button>
  ) : null;

  return (
    <PosterRow
      title="For you"
      subtitle="Shaped by your ratings and recent activity."
      items={combined}
      action={action}
      onNearEnd={loadMore}
      trailing={trailing}
    />
  );
}

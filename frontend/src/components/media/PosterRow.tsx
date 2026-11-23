import type { ReactNode } from "react";
import { PosterCard } from "./PosterCard";
import { ScrollRow } from "./ScrollRow";
import type { CardTitle } from "./cardTypes";

interface PosterRowProps {
  title: string;
  subtitle?: string;
  items: CardTitle[];
  action?: ReactNode;
  emptyMessage?: string;
  onNearEnd?: () => void;
  trailing?: ReactNode;
}

export function PosterRow({
  title,
  subtitle,
  items,
  action,
  emptyMessage,
  onNearEnd,
  trailing,
}: PosterRowProps) {
  if (items.length === 0 && !emptyMessage) {
    return null;
  }

  return (
    <ScrollRow
      title={title}
      subtitle={subtitle}
      action={action}
      onNearEnd={onNearEnd}
      trailing={trailing}
    >
      {items.length === 0 ? (
        <p className="py-4 text-sm text-white/60">{emptyMessage}</p>
      ) : (
        items.map((item) => (
          <div
            key={item.title_id}
            className="w-[9.5rem] shrink-0 snap-start sm:w-[11rem] lg:w-[12rem]"
          >
            <PosterCard item={item} />
          </div>
        ))
      )}
    </ScrollRow>
  );
}

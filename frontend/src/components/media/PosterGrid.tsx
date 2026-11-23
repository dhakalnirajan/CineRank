import { PosterCard } from "./PosterCard";
import type { CardTitle } from "./cardTypes";

interface PosterGridProps {
  items: CardTitle[];
}

export function PosterGrid({ items }: PosterGridProps) {
  return (
    <ul className="grid grid-cols-2 gap-x-4 gap-y-9 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {items.map((item, index) => (
        <li key={item.title_id}>
          <PosterCard item={item} priority={index < 5} />
        </li>
      ))}
    </ul>
  );
}

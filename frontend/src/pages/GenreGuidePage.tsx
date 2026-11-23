import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { GENRES } from "../features/catalogue/genres";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function GenreGuidePage() {
  useDocumentTitle("Genre guide");

  return (
    <div className="page-shell py-12">
      <PageHeader
        eyebrow="Discover"
        title="Genre guide"
        description="Pick a mood, then browse what fits."
      />

      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {GENRES.map((genre) => (
          <li key={genre}>
            <Link
              to={`/explore?genre=${encodeURIComponent(genre)}`}
              className="group flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#0c0c0c] px-4 py-4 text-sm font-medium text-white/70 transition-[border-color,background-color,color] duration-[var(--motion-fast)] hover:border-white/25 hover:bg-white/[0.04] hover:text-white"
            >
              {genre}
              <ArrowUpRight
                className="size-4 shrink-0 text-white/25 transition-colors group-hover:text-accent"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

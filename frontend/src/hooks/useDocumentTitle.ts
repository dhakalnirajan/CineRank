import { useEffect } from "react";

export function useDocumentTitle(title: string | null | undefined): void {
  useEffect(() => {
    const previous = document.title;
    if (title) {
      document.title = `${title} | CineRank`;
    }
    return () => {
      document.title = previous;
    };
  }, [title]);
}

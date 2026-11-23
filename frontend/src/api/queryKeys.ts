import type { CatalogueParams } from "./endpoints";

export const queryKeys = {
  me: ["auth", "me"] as const,
  catalogue: (filters: Pick<CatalogueParams, "genre" | "mediaType">, resetKey: number) =>
    ["catalogue", filters.mediaType ?? null, filters.genre ?? null, resetKey] as const,
  title: (mediaType: "movie" | "tv", serialNumber: string) =>
    ["title", mediaType, serialNumber] as const,
  similarTitles: (mediaType: "movie" | "tv", serialNumber: string) =>
    ["title", mediaType, serialNumber, "similar"] as const,
  legacyTitle: (titleId: string) => ["title-legacy", titleId] as const,
  search: (query: string) => ["search", query] as const,
  watchlist: ["watchlist"] as const,
  history: (userId: number) => ["history", userId] as const,
  home: (userId: number, k: number) => ["home", userId, k] as const,
  recommendations: (userId: number, k: number) => ["recommendations", userId, k] as const,
  cataloguePreview: ["catalogue-preview"] as const,
  facets: ["catalogue", "facets"] as const,
};

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/endpoints";
import { queryKeys } from "../../api/queryKeys";
import type { WatchlistEntry } from "../../types/api";
import { useAuth } from "../auth/AuthProvider";

export function useWatchlist() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.watchlist,
    queryFn: ({ signal }) => api.watchlist(signal),
    enabled: Boolean(user),
    staleTime: 30_000,
  });
}

export function useAddToWatchlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (titleId: string) => api.addToWatchlist(titleId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      void queryClient.invalidateQueries({ queryKey: ["home"] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

interface RemoveContext {
  previous?: WatchlistEntry[];
}

export function useRemoveFromWatchlist() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string, RemoveContext>({
    mutationFn: (titleId) => api.removeFromWatchlist(titleId),
    onMutate: async (titleId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.watchlist });
      const previous = queryClient.getQueryData<WatchlistEntry[]>(queryKeys.watchlist);
      queryClient.setQueryData<WatchlistEntry[]>(queryKeys.watchlist, (current) =>
        current ? current.filter((entry) => entry.title.title_id !== titleId) : current,
      );
      return { previous };
    },
    onError: (_error, _titleId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.watchlist, context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      void queryClient.invalidateQueries({ queryKey: ["home"] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

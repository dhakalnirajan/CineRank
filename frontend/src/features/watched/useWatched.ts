import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/endpoints";
import { useAuth } from "../auth/AuthProvider";

export function useWatchedEntry(titleId: string) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["watched-entry", titleId],
    queryFn: () => api.watchedEntry(titleId),
    enabled: Boolean(user),
    staleTime: 30_000,
  });
}

export function useAddToWatched() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (titleId: string) => api.addToWatched(titleId),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["watched-entry", variables] });
      void queryClient.invalidateQueries({ queryKey: ["home"] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}

export function useRemoveFromWatched() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (titleId) => api.removeFromWatched(titleId),
    onSuccess: (_, titleId) => {
      void queryClient.invalidateQueries({ queryKey: ["watched-entry", titleId] });
      void queryClient.invalidateQueries({ queryKey: ["home"] });
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}
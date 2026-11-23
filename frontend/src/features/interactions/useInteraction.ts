import { useCallback, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/endpoints";
import type { InteractionEventType } from "../../types/api";
import { useAuth } from "../auth/AuthProvider";

const lastRecordedAt = new Map<string, number>();
const EVENT_DEDUPE_MS = 10 * 60_000;

function trackOnce(
  userId: number,
  titleId: string,
  eventType: InteractionEventType,
  onRecorded?: () => void,
): void {
  const key = `${userId}:${eventType}:${titleId}`;
  const now = Date.now();
  const previous = lastRecordedAt.get(key);
  if (previous !== undefined && now - previous < EVENT_DEDUPE_MS) return;

  for (const [recordKey, timestamp] of lastRecordedAt) {
    if (now - timestamp >= 60 * 60_000) lastRecordedAt.delete(recordKey);
  }
  lastRecordedAt.set(key, now);
  void api.recordInteraction(titleId, eventType).then(() => {
    onRecorded?.();
  }).catch(() => {
    if (lastRecordedAt.get(key) === now) lastRecordedAt.delete(key);
  });
}

export function useTitleClick(titleId: string | null): void {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  useEffect(() => {
    if (user && titleId) {
      trackOnce(user.id, titleId, "click", () => {
        void queryClient.invalidateQueries({ queryKey: ["home", user.id] });
        void queryClient.invalidateQueries({ queryKey: ["recommendations", user.id] });
      });
    }
  }, [user, titleId, queryClient]);
}

export function useImpression(titleId: string): (node: HTMLElement | null) => (() => void) | void {
  const { user } = useAuth();

  return useCallback(
    (node: HTMLElement | null) => {
      if (!node || !user || typeof IntersectionObserver === "undefined") {
        return;
      }
      const observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            trackOnce(user.id, titleId, "impression");
            observer.disconnect();
          }
        },
        { threshold: 0.5 },
      );
      observer.observe(node);
      return () => observer.disconnect();
    },
    [user, titleId],
  );
}

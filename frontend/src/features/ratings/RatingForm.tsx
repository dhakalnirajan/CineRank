import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { isApiError } from "../../api/errors";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../components/ui/Button";
import { useAuth } from "../auth/AuthProvider";
import { RatingStars } from "./RatingStars";

interface RatingFormProps {
  titleId: string;
  initialRating: number | null;
}

export function RatingForm({ titleId, initialRating }: RatingFormProps) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [value, setValue] = useState<number | null>(initialRating);
  const [savedValue, setSavedValue] = useState<number | null>(initialRating);
  const initialized = useRef(false);

  useEffect(() => {
    if (!initialized.current) {
      setValue(initialRating);
      setSavedValue(initialRating);
      initialized.current = true;
    }
  }, [initialRating]);

  const mutation = useMutation({
    mutationFn: (rating: number) => api.rate(titleId, rating),
    onSuccess: (response) => {
      setSavedValue(response.rating);
      setValue(response.rating);
      if (user) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.history(user.id) });
        void queryClient.invalidateQueries({ queryKey: ["home", user.id] });
        void queryClient.invalidateQueries({ queryKey: ["recommendations", user.id] });
      }
    },
  });

  const unchanged = value !== null && savedValue !== null && value === savedValue;

  return (
    <div className="border border-white/10 bg-[#0c0c0c] p-5">
      <h2 className="text-base font-semibold text-white">Your rating</h2>
      <p className="mt-1 text-sm leading-relaxed text-white/60">
        Your rating helps tune your picks.
      </p>
      <div className="mt-4">
        <RatingStars value={value} onChange={setValue} disabled={mutation.isPending} />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          onClick={() => {
            if (value !== null) {
              mutation.mutate(value);
            }
          }}
          disabled={value === null || unchanged}
          loading={mutation.isPending}
          size="sm"
        >
          {savedValue === null ? "Save rating" : "Update rating"}
        </Button>
        {savedValue !== null && unchanged ? (
          <span className="text-xs text-success">Saved</span>
        ) : null}
      </div>
      {mutation.isError ? (
        <p className="mt-3 text-sm text-danger" role="alert">
          {isApiError(mutation.error)
            ? mutation.error.message
            : "Couldn't save your rating. Please try again."}
        </p>
      ) : null}
    </div>
  );
}

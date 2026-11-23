import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../ui/Button";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  action?: ReactNode;
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  retryLabel = "Try again",
  action,
}: ErrorStateProps) {
  return (
    <div
      className="border border-white/10 bg-[#0c0c0c] px-6 py-12 text-center"
      role="alert"
    >
      <AlertTriangle className="mx-auto size-7 text-warning" aria-hidden="true" />
      <h2 className="mt-4 text-xl font-semibold text-ink">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-white/60">{message}</p>
      {onRetry || action ? (
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          {onRetry ? <Button onClick={onRetry}>{retryLabel}</Button> : null}
          {action}
        </div>
      ) : null}
    </div>
  );
}

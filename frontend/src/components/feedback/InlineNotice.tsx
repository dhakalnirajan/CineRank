import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

interface InlineNoticeProps {
  tone?: "info" | "warning" | "error" | "success";
  children: ReactNode;
  action?: ReactNode;
}

const tones = {
  info: "border-info/40 bg-info/10 text-info",
  warning: "border-warning/40 bg-warning/10 text-warning",
  error: "border-danger/40 bg-danger/10 text-danger",
  success: "border-success/40 bg-success/10 text-success",
} as const;

export function InlineNotice({ tone = "info", children, action }: InlineNoticeProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 rounded-control border px-4 py-3 text-sm",
        tones[tone],
      )}
      role={tone === "error" ? "alert" : "status"}
    >
      <span>{children}</span>
      {action}
    </div>
  );
}

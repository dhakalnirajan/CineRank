import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import { Spinner } from "../feedback/Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const variants: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-accent-ink hover:bg-accent-strong active:bg-[#c40812]",
  secondary:
    "bg-white/20 text-white hover:bg-white/30 active:bg-white/25 supports-[backdrop-filter]:backdrop-blur-sm",
  ghost: "text-white/75 hover:bg-white/10 hover:text-white",
  danger:
    "border border-danger/50 bg-transparent text-danger hover:border-danger hover:bg-danger/10",
};

const sizes: Record<ButtonSize, string> = {
  sm: "h-8 px-4 text-[0.8125rem]",
  md: "h-10 px-5 text-sm",
  lg: "h-12 px-7 text-base",
};

export function buttonClasses(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className?: string,
): string {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-control font-semibold transition-colors duration-[var(--motion-fast)] disabled:cursor-not-allowed disabled:opacity-50",
    variants[variant],
    sizes[size],
    className,
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={buttonClasses(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Spinner className="size-4 border-white/40 border-t-white" /> : null}
      {children}
    </button>
  );
}

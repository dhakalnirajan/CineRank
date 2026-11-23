import { useId, type ComponentProps } from "react";
import { cn } from "../../utils/cn";

interface TextFieldProps extends ComponentProps<"input"> {
  label: string;
  error?: string;
  hint?: string;
  containerClassName?: string;
}

export function TextField({
  label,
  error,
  hint,
  id,
  className,
  containerClassName,
  ...props
}: TextFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const describedBy = [error ? `${fieldId}-error` : null, hint ? `${fieldId}-hint` : null]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={containerClassName}>
      <label htmlFor={fieldId} className="mb-2 block text-sm text-white/70">
        {label}
      </label>
      <input
        id={fieldId}
        className={cn(
          "h-12 w-full rounded-none border border-line-strong bg-[#161616] px-4 text-base text-ink placeholder:text-faint transition-colors duration-[var(--motion-fast)] hover:border-white/80 focus:border-white disabled:cursor-not-allowed disabled:opacity-60",
          error && "border-danger",
          className,
        )}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        {...props}
      />
      {hint ? (
        <p id={`${fieldId}-hint`} className="mt-2 text-xs leading-relaxed text-faint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${fieldId}-error`} className="mt-2 text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

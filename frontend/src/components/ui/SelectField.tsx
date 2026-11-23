import { useId, type ComponentProps } from "react";
import { cn } from "../../utils/cn";

interface Option {
  value: string;
  label: string;
}

interface SelectFieldProps extends ComponentProps<"select"> {
  label: string;
  options: Option[];
  error?: string;
  containerClassName?: string;
}

export function SelectField({
  label,
  options,
  error,
  id,
  className,
  containerClassName,
  ...props
}: SelectFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;

  return (
    <div className={containerClassName}>
      <label htmlFor={fieldId} className="mb-2 block text-xs font-medium uppercase tracking-[0.14em] text-white/60">
        {label}
      </label>
      <select
        id={fieldId}
        className={cn(
          "h-10 w-full appearance-none rounded-none border border-line-strong bg-black px-3 pr-9 text-sm text-ink transition-colors duration-[var(--motion-fast)] hover:border-white focus:border-white",
          error && "border-danger",
          className,
        )}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${fieldId}-error` : undefined}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? (
        <p id={`${fieldId}-error`} className="mt-2 text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

import { Star, StarHalf } from "lucide-react";
import { useId } from "react";
import { ratingLabel } from "../../utils/format";

interface RatingStarsProps {
  value: number | null;
  onChange: (value: number) => void;
  disabled?: boolean;
}

const STARS = [1, 2, 3, 4, 5];

export function RatingStars({ value, onChange, disabled }: RatingStarsProps) {
  const id = useId();

  return (
    <div>
      <div className="flex items-center gap-3">
        <div className="flex gap-1" aria-hidden="true">
          {STARS.map((star) => {
            const filled = value !== null && value >= star;
            const half = value !== null && value >= star - 0.5 && value < star;
            if (half) {
              return <StarHalf key={star} className="size-6 fill-accent text-accent" />;
            }
            return (
              <Star
                key={star}
                className={
                  filled ? "size-6 fill-accent text-accent" : "size-6 fill-transparent text-line-strong"
                }
              />
            );
          })}
        </div>
        <span className="meta-numeric text-sm text-muted">
          {value === null ? "No rating selected" : ratingLabel(value)}
        </span>
      </div>
      <label htmlFor={id} className="sr-only">
        Your rating from 0.5 to 5 stars
      </label>
      <input
        id={id}
        type="range"
        min={0.5}
        max={5}
        step={0.5}
        value={value ?? 0.5}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-valuetext={value === null ? "No rating selected" : ratingLabel(value)}
        className="mt-3 h-2 w-full cursor-pointer accent-[var(--color-accent)] disabled:cursor-not-allowed disabled:opacity-50"
      />
      <div className="mt-1 flex justify-between text-[0.6875rem] text-faint" aria-hidden="true">
        <span>0.5</span>
        <span>5.0</span>
      </div>
    </div>
  );
}

import type { JSX } from "react";
import "./Segmented.css";

export interface SegmentedOption<T extends string = string> {
  value: T;
  label: string;
  testId?: string;
}

export interface SegmentedProps<T extends string = string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  "aria-label"?: string;
}

export function Segmented<T extends string = string>({
  options,
  value,
  onChange,
  "aria-label": ariaLabel,
}: SegmentedProps<T>): JSX.Element {
  return (
    <div className="ef-segmented" role="group" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={[
            "ef-segmented__option",
            option.value === value ? "ef-segmented__option--active" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          aria-pressed={option.value === value}
          data-testid={option.testId}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

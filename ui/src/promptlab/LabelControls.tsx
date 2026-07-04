import type { JSX } from "react";

import "./LabelControls.css";

export interface LabelControlsProps {
  label?: string;
  onLabel: (label: string) => void;
}

export function LabelControls({
  label,
  onLabel,
}: LabelControlsProps): JSX.Element {
  return (
    <div className="ef-promptlab-labelcontrols" data-testid="label-controls">
      <button
        type="button"
        className={
          label === "pass"
            ? "ef-promptlab-labelcontrols__button ef-promptlab-labelcontrols__button--active-pass"
            : "ef-promptlab-labelcontrols__button"
        }
        onClick={() => onLabel("pass")}
        data-testid="label-pass"
        aria-pressed={label === "pass"}
      >
        Pass
      </button>
      <button
        type="button"
        className={
          label === "fail"
            ? "ef-promptlab-labelcontrols__button ef-promptlab-labelcontrols__button--active-fail"
            : "ef-promptlab-labelcontrols__button"
        }
        onClick={() => onLabel("fail")}
        data-testid="label-fail"
        aria-pressed={label === "fail"}
      >
        Fail
      </button>
    </div>
  );
}

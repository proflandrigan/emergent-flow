import { useState, type JSX, type ReactElement } from "react";
import "./Tooltip.css";

export interface TooltipProps {
  label: string;
  children: ReactElement;
}

export function Tooltip({ label, children }: TooltipProps): JSX.Element {
  const [visible, setVisible] = useState(false);

  return (
    <span
      className="ef-tooltip"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span className="ef-tooltip__label" role="tooltip">
          {label}
        </span>
      )}
    </span>
  );
}

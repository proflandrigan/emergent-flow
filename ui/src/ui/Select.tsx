import type { JSX, SelectHTMLAttributes } from "react";
import "./Select.css";

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export function Select({
  className = "",
  children,
  ...rest
}: SelectProps): JSX.Element {
  const classes = ["ef-select", className].filter(Boolean).join(" ");
  return (
    <select className={classes} {...rest}>
      {children}
    </select>
  );
}

import type { ButtonHTMLAttributes, JSX } from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "icon";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

export function Button({
  variant = "secondary",
  className = "",
  children,
  ...rest
}: ButtonProps): JSX.Element {
  const classes = [`ef-button`, `ef-button--${variant}`, className]
    .filter(Boolean)
    .join(" ");

  return (
    <button type="button" className={classes} {...rest}>
      {children}
    </button>
  );
}

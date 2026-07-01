import type { ButtonHTMLAttributes, JSX } from "react";
import { Button } from "./Button";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  "aria-label": string;
}

export function IconButton({
  "aria-label": ariaLabel,
  children,
  ...rest
}: IconButtonProps): JSX.Element {
  return (
    <Button variant="icon" aria-label={ariaLabel} {...rest}>
      {children}
    </Button>
  );
}

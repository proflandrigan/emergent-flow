import type { InputHTMLAttributes, JSX, ReactNode } from "react";
import "./Input.css";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  pill?: boolean;
  leadingIcon?: ReactNode;
}

export function Input({
  pill = false,
  leadingIcon,
  className = "",
  ...rest
}: InputProps): JSX.Element {
  const inputClasses = [
    "ef-input",
    pill ? "ef-input--pill" : "",
    leadingIcon ? "ef-input--with-icon" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const input = <input className={inputClasses} {...rest} />;

  if (leadingIcon) {
    return (
      <div className="ef-input-wrapper">
        <span className="ef-input__icon">{leadingIcon}</span>
        {input}
      </div>
    );
  }

  return input;
}

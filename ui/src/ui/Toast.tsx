import type { JSX } from "react";
import "./Toast.css";

export interface ToastProps {
  message: string;
  variant?: "info" | "error";
  onDismiss?: () => void;
}

export function Toast({
  message,
  variant = "info",
  onDismiss,
}: ToastProps): JSX.Element {
  return (
    <div className={`ef-toast glass ef-toast--${variant}`} role="alert">
      <span className="ef-toast__message">{message}</span>
      {onDismiss && (
        <button
          className="ef-toast__dismiss"
          onClick={onDismiss}
          aria-label="Dismiss"
          type="button"
        >
          ×
        </button>
      )}
    </div>
  );
}

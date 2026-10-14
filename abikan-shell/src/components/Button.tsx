import type { ButtonHTMLAttributes, ReactNode } from "react";
import "./Button.css";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  busy?: boolean;
  busyLabel?: ReactNode;
}

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  busy = false,
  busyLabel,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`abikan-button abikan-button--${variant} ${className}`.trim()}
      disabled={Boolean(disabled || busy)}
      aria-busy={busy || undefined}
      {...props}
    >
      {busy ? <span className="abikan-button__spinner" aria-hidden="true" /> : null}
      {busy ? busyLabel || children : children}
    </button>
  );
}

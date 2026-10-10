import type { ButtonHTMLAttributes } from "react";
import "./button.css";

export function Button({ variant = "primary", loading = false, disabled, children, className = "", type = "button", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger"; loading?: boolean }) {
  return <button {...props} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
    className={`ds-button ds-button-${variant} ${className}`}>
    {loading && <span className="button-spinner" aria-hidden="true" />}{children}
  </button>;
}

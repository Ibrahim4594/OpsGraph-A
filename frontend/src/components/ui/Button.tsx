import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-[color:var(--color-primary)] text-white hover:bg-[color:var(--color-primary-hover)]",
  secondary:
    "border border-[color:var(--color-border-strong)] bg-[color:var(--color-bg-elev)] text-[color:var(--color-fg)] hover:bg-[color:var(--color-bg-elev-2)]",
  ghost:
    "text-[color:var(--color-fg)] hover:bg-[color:var(--color-bg-elev-2)]",
  danger:
    "border border-[color:rgba(239,68,68,0.4)] bg-transparent text-[color:var(--color-danger)] hover:bg-[color:rgba(239,68,68,0.12)]",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-4 text-sm",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { variant = "primary", size = "md", className, type, ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type ?? "button"}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-[var(--radius-sm)]",
          "font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className,
        )}
        {...props}
      />
    );
  },
);

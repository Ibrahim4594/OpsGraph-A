import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export type BadgeTone = "neutral" | "primary" | "success" | "warning" | "danger";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral:
    "border-[color:var(--color-border-strong)] bg-[color:var(--color-bg-elev-2)] text-[color:var(--color-fg-muted)]",
  primary:
    "border-[color:rgba(12,92,171,0.4)] bg-[color:var(--color-primary-soft)] text-[color:var(--color-fg)]",
  success:
    "border-[color:rgba(16,185,129,0.4)] bg-[color:rgba(16,185,129,0.12)] text-[color:var(--color-success)]",
  warning:
    "border-[color:rgba(245,158,11,0.4)] bg-[color:rgba(245,158,11,0.12)] text-[color:var(--color-warning)]",
  danger:
    "border-[color:rgba(239,68,68,0.4)] bg-[color:rgba(239,68,68,0.12)] text-[color:var(--color-danger)]",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({
  tone = "neutral",
  className,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
        "text-xs font-medium leading-none",
        TONE_CLASSES[tone],
        className,
      )}
      {...props}
    />
  );
}

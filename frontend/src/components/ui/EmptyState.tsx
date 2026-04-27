import { type ReactNode } from "react";

import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  body,
  className,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-[var(--radius)]",
        "border border-dashed border-[color:var(--color-border-strong)]",
        "bg-[color:var(--color-bg-elev)] px-6 py-12 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="text-[color:var(--color-fg-dim)]" aria-hidden>
          {icon}
        </div>
      ) : null}
      <h3 className="text-sm font-medium text-[color:var(--color-fg)]">{title}</h3>
      {body ? (
        <p className="max-w-md text-sm text-[color:var(--color-fg-muted)]">{body}</p>
      ) : null}
    </div>
  );
}

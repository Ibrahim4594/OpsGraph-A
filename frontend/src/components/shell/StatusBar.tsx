import { ShieldCheck, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/Badge";

export interface StatusBarProps {
  version: string;
  agenticEnabled: boolean;
}

export function StatusBar({ version, agenticEnabled }: StatusBarProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-[color:var(--color-border)] bg-[color:var(--color-bg)] px-6">
      <div className="text-sm text-[color:var(--color-fg-muted)]">
        Operator console
      </div>
      <div className="flex items-center gap-3">
        <Badge tone="neutral" aria-label={`Backend version ${version}`}>
          v{version}
        </Badge>
        {agenticEnabled ? (
          <Badge
            tone="success"
            aria-label="Agentic workflows enabled"
            role="status"
          >
            <ShieldCheck size={12} aria-hidden /> Agentic on
          </Badge>
        ) : (
          <Badge
            tone="warning"
            aria-label="Agentic workflows disabled"
            role="status"
          >
            <ShieldAlert size={12} aria-hidden /> Agentic off
          </Badge>
        )}
      </div>
    </header>
  );
}

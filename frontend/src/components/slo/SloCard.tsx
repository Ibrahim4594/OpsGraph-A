import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

export type SloBand = "success" | "warning" | "danger" | "empty";

export interface SloCardProps {
  label: string;
  value: number | null;
  target: number;
  hint?: string;
}

function bandFor(value: number | null, target: number): SloBand {
  if (value === null || Number.isNaN(value)) return "empty";
  if (value >= target) return "success";
  if (target - value < 0.01) return "warning";
  return "danger";
}

const BAND_TEXT: Record<SloBand, string> = {
  success: "text-[color:var(--color-success)]",
  warning: "text-[color:var(--color-warning)]",
  danger: "text-[color:var(--color-danger)]",
  empty: "text-[color:var(--color-fg-dim)]",
};

export function SloCard({ label, value, target, hint }: SloCardProps) {
  const band = bandFor(value, target);
  return (
    <Card role="status" data-band={band} aria-label={`${label} SLO`}>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
      </CardHeader>
      <CardBody>
        <div
          className={cn(
            "text-[32px] font-semibold leading-tight tabular-nums",
            BAND_TEXT[band],
          )}
        >
          {formatPercent(value)}
        </div>
        <div className="mt-2 text-xs text-[color:var(--color-fg-muted)]">
          target {formatPercent(target)}
          {hint ? <span className="ml-2 opacity-80">· {hint}</span> : null}
        </div>
      </CardBody>
    </Card>
  );
}

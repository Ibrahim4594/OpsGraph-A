import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { formatBurnRate } from "@/lib/format";
import type { BurnBand } from "@/lib/api";

const BAND_TONE: Record<BurnBand, BadgeTone> = {
  ok: "success",
  slow: "warning",
  fast: "danger",
};

const BAND_LABEL: Record<BurnBand, string> = {
  ok: "Within budget",
  slow: "Over budget — slow burn",
  fast: "Over budget — fast burn",
};

export function BurnRateBadge({
  band,
  rate,
}: {
  band: BurnBand;
  rate: number | null;
}) {
  return (
    <Badge tone={BAND_TONE[band]} data-band={band} aria-label={BAND_LABEL[band]}>
      <span className="font-semibold">{formatBurnRate(rate)}</span>
      <span className="opacity-80">{BAND_LABEL[band]}</span>
    </Badge>
  );
}

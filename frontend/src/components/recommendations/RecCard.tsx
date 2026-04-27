import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { ApprovalActions } from "@/components/recommendations/ApprovalActions";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import type { ActionCategory, Recommendation, RiskLevel } from "@/lib/api";
import { runbookFor } from "@/lib/runbooks";

const CATEGORY_TONE: Record<ActionCategory, BadgeTone> = {
  observe: "neutral",
  triage: "primary",
  escalate: "warning",
  rollback: "danger",
};

const RISK_TONE: Record<RiskLevel, BadgeTone> = {
  low: "neutral",
  medium: "warning",
  high: "danger",
};

export function RecCard({ rec }: { rec: Recommendation }) {
  const runbook = runbookFor(rec.action_category);
  return (
    <Card>
      <CardBody className="flex flex-col gap-4 px-6 py-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={CATEGORY_TONE[rec.action_category]}>
                {rec.action_category}
              </Badge>
              <Badge tone={RISK_TONE[rec.risk_level]}>
                risk: {rec.risk_level}
              </Badge>
              <span className="text-xs text-[color:var(--color-fg-muted)]">
                confidence {(rec.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <span className="font-mono text-xs text-[color:var(--color-fg-dim)]">
              incident {rec.incident_id.slice(0, 8)}…
            </span>
          </div>
          <ApprovalActions id={rec.recommendation_id} initialState={rec.state} />
        </div>

        <details className="rounded-[var(--radius-sm)] border border-[color:var(--color-border)] bg-[color:var(--color-bg-elev-2)] open:bg-[color:var(--color-bg-elev-2)]">
          <summary className="cursor-pointer list-none px-3 py-2 text-xs text-[color:var(--color-fg-muted)]">
            Evidence trace ({rec.evidence_trace.length})
          </summary>
          <ul className="space-y-1 border-t border-[color:var(--color-border)] px-4 py-3 text-xs leading-relaxed text-[color:var(--color-fg-muted)]">
            {rec.evidence_trace.map((line, idx) => (
              <li key={idx} className="font-mono">
                {line}
              </li>
            ))}
          </ul>
        </details>

        {runbook ? (
          <Link
            href={runbook}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-xs text-[color:var(--color-primary)] hover:underline"
          >
            <ExternalLink size={12} aria-hidden /> Open runbook for{" "}
            {rec.action_category}
          </Link>
        ) : null}
      </CardBody>
    </Card>
  );
}

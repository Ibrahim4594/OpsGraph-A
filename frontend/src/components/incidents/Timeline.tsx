import { Activity } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import type { IncidentSummary } from "@/lib/api";
import { formatRelative } from "@/lib/format";

export function Timeline({
  incidents,
  now,
}: {
  incidents: IncidentSummary[];
  now?: Date;
}) {
  if (incidents.length === 0) {
    return (
      <EmptyState
        icon={<Activity size={28} aria-hidden />}
        title="No incidents observed yet"
        body="Once events and anomalies arrive, the orchestrator groups related signals into incidents and lists them here, newest first."
      />
    );
  }
  return (
    <ol className="flex flex-col gap-3">
      {incidents.map((incident) => {
        const startedAt = new Date(incident.started_at);
        const endedAt = new Date(incident.ended_at);
        const durationSec = Math.max(
          0,
          Math.round((endedAt.getTime() - startedAt.getTime()) / 1000),
        );
        return (
          <li key={incident.incident_id}>
            <Card>
              <CardBody className="flex flex-col gap-3 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium tabular-nums">
                      {formatRelative(startedAt, now)}
                    </span>
                    <span className="text-xs text-[color:var(--color-fg-dim)]">
                      · {durationSec}s window
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {incident.sources.map((source) => (
                      <Badge key={source} tone="primary">
                        {source}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-[color:var(--color-fg-muted)]">
                  <span className="rounded-md border border-[color:var(--color-border)] px-2 py-1">
                    {incident.anomaly_count}{" "}
                    {incident.anomaly_count === 1 ? "anomaly" : "anomalies"}
                  </span>
                  <span className="rounded-md border border-[color:var(--color-border)] px-2 py-1">
                    {incident.event_count}{" "}
                    {incident.event_count === 1 ? "event" : "events"}
                  </span>
                </div>
              </CardBody>
            </Card>
          </li>
        );
      })}
    </ol>
  );
}

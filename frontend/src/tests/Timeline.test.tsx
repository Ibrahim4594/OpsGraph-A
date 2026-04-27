import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Timeline } from "@/components/incidents/Timeline";
import type { IncidentSummary } from "@/lib/api";

const NOW = new Date("2026-04-27T12:30:00Z");

function inc(
  id: string,
  startedSeconds: number,
  sources: string[],
  anomalies = 1,
  events = 1,
): IncidentSummary {
  const start = new Date("2026-04-27T12:00:00Z").getTime() + startedSeconds * 1000;
  return {
    incident_id: id,
    started_at: new Date(start).toISOString(),
    ended_at: new Date(start + 60_000).toISOString(),
    sources,
    anomaly_count: anomalies,
    event_count: events,
  };
}

describe("Timeline", () => {
  it("renders empty state when there are no incidents", () => {
    render(<Timeline incidents={[]} now={NOW} />);
    expect(screen.getByRole("status")).toHaveTextContent(/no incidents/i);
  });

  it("renders one row per incident with sources", () => {
    render(
      <Timeline
        incidents={[
          inc("a", 0, ["github", "otel-metrics"]),
          inc("b", 600, ["otel-logs"]),
        ]}
        now={NOW}
      />,
    );
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("github");
    expect(rows[0]).toHaveTextContent("otel-metrics");
    expect(rows[1]).toHaveTextContent("otel-logs");
  });

  it("shows anomaly + event counts", () => {
    render(
      <Timeline
        incidents={[inc("a", 0, ["github"], 3, 7)]}
        now={NOW}
      />,
    );
    expect(screen.getByText(/3 anomalies/i)).toBeInTheDocument();
    expect(screen.getByText(/7 events/i)).toBeInTheDocument();
  });

  it("renders relative start time", () => {
    render(
      <Timeline
        incidents={[inc("a", 0, ["github"])]}
        now={NOW}
      />,
    );
    expect(screen.getByText(/30m ago/i)).toBeInTheDocument();
  });
});

import { ServerCrash } from "lucide-react";

import { Timeline } from "@/components/incidents/Timeline";
import { EmptyState } from "@/components/ui/EmptyState";
import { getIncidents, type IncidentsResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

async function loadIncidents(): Promise<
  IncidentsResponse | { error: string }
> {
  try {
    return await getIncidents();
  } catch (exc) {
    return { error: exc instanceof Error ? exc.message : String(exc) };
  }
}

export default async function IncidentsPage() {
  const data = await loadIncidents();
  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Incidents</h1>
        <p className="mt-1 text-sm text-[color:var(--color-fg-muted)]">
          Time-windowed groupings of correlated anomalies and events.
        </p>
      </div>
      {"error" in data ? (
        <EmptyState
          icon={<ServerCrash size={28} aria-hidden />}
          title="Backend unreachable"
          body={`Could not load /api/v1/incidents. ${data.error}`}
        />
      ) : (
        <Timeline incidents={data.incidents} />
      )}
    </div>
  );
}

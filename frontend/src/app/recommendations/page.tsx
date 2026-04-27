import { Inbox, ServerCrash } from "lucide-react";

import { RecCard } from "@/components/recommendations/RecCard";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  getRecommendations,
  type RecommendationsResponse,
} from "@/lib/api";

export const dynamic = "force-dynamic";

async function loadRecs(): Promise<
  RecommendationsResponse | { error: string }
> {
  try {
    return await getRecommendations({ limit: 50 });
  } catch (exc) {
    return { error: exc instanceof Error ? exc.message : String(exc) };
  }
}

export default async function RecommendationsPage() {
  const data = await loadRecs();
  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Recommendations</h1>
        <p className="mt-1 text-sm text-[color:var(--color-fg-muted)]">
          Ranked recommendations awaiting your call. Approving never executes a
          destructive action automatically — see ADR-004.
        </p>
      </div>
      {"error" in data ? (
        <EmptyState
          icon={<ServerCrash size={28} aria-hidden />}
          title="Backend unreachable"
          body={`Could not load /api/v1/recommendations. ${data.error}`}
        />
      ) : data.count === 0 ? (
        <EmptyState
          icon={<Inbox size={28} aria-hidden />}
          title="Inbox is clear"
          body="No recommendations are awaiting attention. R1 (observe) recommendations are auto-observed and listed in the action history."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {data.recommendations.map((rec) => (
            <RecCard key={rec.recommendation_id} rec={rec} />
          ))}
        </div>
      )}
    </div>
  );
}

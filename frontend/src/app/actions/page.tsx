import { History, ServerCrash } from "lucide-react";

import { HistoryTable } from "@/components/actions/KindFilter";
import { EmptyState } from "@/components/ui/EmptyState";
import { getActions, type ActionsResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

async function loadActions(): Promise<ActionsResponse | { error: string }> {
  try {
    return await getActions({ limit: 100 });
  } catch (exc) {
    return { error: exc instanceof Error ? exc.message : String(exc) };
  }
}

export default async function ActionsPage() {
  const data = await loadActions();
  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Action history
        </h1>
        <p className="mt-1 text-sm text-[color:var(--color-fg-muted)]">
          Operator approvals, system observe events, and agentic workflow runs
          in one chronological feed.
        </p>
      </div>
      {"error" in data ? (
        <EmptyState
          icon={<ServerCrash size={28} aria-hidden />}
          title="Backend unreachable"
          body={`Could not load /api/v1/actions. ${data.error}`}
        />
      ) : data.count === 0 ? (
        <EmptyState
          icon={<History size={28} aria-hidden />}
          title="No actions yet"
          body="Once recommendations are approved or rejected, or agentic workflows run, the audit feed appears here."
        />
      ) : (
        <HistoryTable actions={data.actions} />
      )}
    </div>
  );
}

import { ServerCrash } from "lucide-react";

import { BurnRateBadge } from "@/components/slo/BurnRateBadge";
import { SloCard } from "@/components/slo/SloCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { getSlo, type SloResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

async function loadSlo(): Promise<SloResponse | { error: string }> {
  try {
    return await getSlo();
  } catch (exc) {
    return { error: exc instanceof Error ? exc.message : String(exc) };
  }
}

export default async function HomePage() {
  const slo = await loadSlo();

  if ("error" in slo) {
    return (
      <PageHeader title="SLO board" subtitle="Service-level state at a glance">
        <EmptyState
          icon={<ServerCrash size={28} aria-hidden />}
          title="Backend unreachable"
          body={`Could not load /api/v1/slo. ${slo.error}`}
        />
      </PageHeader>
    );
  }

  const errorBudget =
    slo.error_budget_remaining >= 0 ? slo.error_budget_remaining : 0;

  return (
    <PageHeader title="SLO board" subtitle="Service-level state at a glance">
      <div className="mb-6 flex items-center gap-3">
        <BurnRateBadge band={slo.burn_band} rate={slo.burn_rate} />
        <span className="text-xs text-[color:var(--color-fg-muted)]">
          {slo.total_events.toLocaleString()} events ·{" "}
          {slo.error_events.toLocaleString()} errors
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SloCard
          label="Availability"
          value={slo.total_events === 0 ? null : slo.availability}
          target={slo.target}
          hint={slo.total_events === 0 ? "no traffic yet" : undefined}
        />
        <SloCard
          label="Error budget"
          value={errorBudget}
          target={1 - slo.target}
          hint="remaining of allowed errors"
        />
        <SloCard
          label="Burn rate"
          value={slo.total_events === 0 ? null : Math.min(slo.burn_rate / 100, 1)}
          target={1 / 100}
          hint={`${slo.burn_rate.toFixed(2)}× actual`}
        />
      </div>
    </PageHeader>
  );
}

function PageHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle ? (
          <p className="mt-1 text-sm text-[color:var(--color-fg-muted)]">
            {subtitle}
          </p>
        ) : null}
      </div>
      {children}
    </div>
  );
}

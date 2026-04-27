"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { HistoryRow } from "@/components/actions/HistoryRow";
import type { ActionEntry, ActionKind } from "@/lib/api";
import { cn } from "@/lib/utils";

type Filter = "all" | ActionKind;
const FILTERS: Filter[] = ["all", "approve", "reject", "observe", "workflow-run"];

export function HistoryTable({ actions }: { actions: ActionEntry[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const filtered =
    filter === "all" ? actions : actions.filter((entry) => entry.kind === filter);
  return (
    <div className="flex flex-col gap-4">
      <div
        className="flex flex-wrap gap-2"
        role="tablist"
        aria-label="Filter by kind"
      >
        {FILTERS.map((option) => {
          const active = filter === option;
          return (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setFilter(option)}
              className={cn(
                "h-9 rounded-full border px-3 text-xs transition-colors",
                active
                  ? "border-[color:var(--color-primary)] bg-[color:var(--color-primary-soft)] text-[color:var(--color-fg)]"
                  : "border-[color:var(--color-border-strong)] bg-[color:var(--color-bg-elev)] text-[color:var(--color-fg-muted)] hover:text-[color:var(--color-fg)]",
              )}
            >
              {option}
            </button>
          );
        })}
        <Badge tone="neutral">{filtered.length} entries</Badge>
      </div>
      <div className="overflow-hidden rounded-[var(--radius)] border border-[color:var(--color-border)] bg-[color:var(--color-bg-elev)]">
        <table className="w-full text-left">
          <thead className="border-b border-[color:var(--color-border)] bg-[color:var(--color-bg-elev-2)]">
            <tr>
              <th className="px-4 py-2 text-xs font-medium uppercase tracking-wider text-[color:var(--color-fg-muted)]">
                When
              </th>
              <th className="px-4 py-2 text-xs font-medium uppercase tracking-wider text-[color:var(--color-fg-muted)]">
                Kind
              </th>
              <th className="px-4 py-2 text-xs font-medium uppercase tracking-wider text-[color:var(--color-fg-muted)]">
                Actor
              </th>
              <th className="px-4 py-2 text-xs font-medium uppercase tracking-wider text-[color:var(--color-fg-muted)]">
                Summary
              </th>
              <th className="px-4 py-2 text-xs font-medium uppercase tracking-wider text-[color:var(--color-fg-muted)]">
                Rec
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((entry, idx) => (
              <HistoryRow
                key={`${entry.at}-${idx}`}
                entry={entry}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

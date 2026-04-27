import Link from "next/link";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { ActionEntry, ActionKind } from "@/lib/api";
import { formatRelative } from "@/lib/format";

const KIND_TONE: Record<ActionKind, BadgeTone> = {
  approve: "success",
  reject: "danger",
  observe: "neutral",
  "workflow-run": "primary",
};

export function HistoryRow({
  entry,
  now,
}: {
  entry: ActionEntry;
  now?: Date;
}) {
  return (
    <tr className="border-b border-[color:var(--color-border)] last:border-b-0">
      <td className="px-4 py-3 text-xs tabular-nums text-[color:var(--color-fg-muted)]">
        {formatRelative(entry.at, now)}
      </td>
      <td className="px-4 py-3">
        <Badge tone={KIND_TONE[entry.kind]}>{entry.kind}</Badge>
      </td>
      <td className="px-4 py-3 text-sm">{entry.actor}</td>
      <td className="px-4 py-3 text-xs text-[color:var(--color-fg-muted)]">
        {entry.summary || "—"}
      </td>
      <td className="px-4 py-3 font-mono text-xs">
        {entry.recommendation_id ? (
          <Link
            href={`/recommendations#${entry.recommendation_id}`}
            className="text-[color:var(--color-primary)] hover:underline"
          >
            {entry.recommendation_id.slice(0, 8)}…
            <span className="sr-only"> {entry.recommendation_id}</span>
          </Link>
        ) : (
          <span className="text-[color:var(--color-fg-dim)]">—</span>
        )}
      </td>
    </tr>
  );
}

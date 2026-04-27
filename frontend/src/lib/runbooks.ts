/**
 * Maps an ``action_category`` to its operator-facing runbook URL.
 *
 * Returns ``null`` for unknown categories so callers can render a
 * "no runbook" affordance rather than a broken link.
 */

const BASE = "https://github.com/Ibrahim4594/OpsGraph-A/blob/main/docs/runbooks";

const RUNBOOKS: Record<string, string> = {
  observe: `${BASE}/observe.md`,
  triage: `${BASE}/triage.md`,
  escalate: `${BASE}/escalate.md`,
  rollback: `${BASE}/rollback.md`,
};

export function runbookFor(actionCategory: string): string | null {
  return RUNBOOKS[actionCategory] ?? null;
}

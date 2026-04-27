/**
 * Display-formatters for dashboard cards.
 *
 * Pure functions — no React, no Date.now() inside (caller passes a clock
 * for deterministic tests).
 */

export function formatPercent(
  value: number | null | undefined,
  decimals = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatRelative(
  at: Date | string | number,
  now: Date = new Date(),
): string {
  const ts = typeof at === "string" || typeof at === "number" ? new Date(at) : at;
  const seconds = Math.max(0, Math.round((now.getTime() - ts.getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
}

export function formatBurnRate(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value > 99) return "99+×";
  return `${value.toFixed(1)}×`;
}

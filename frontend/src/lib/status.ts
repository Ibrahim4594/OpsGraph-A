/**
 * Server-side health probe used by the dashboard shell. Never throws —
 * during the build (when the backend isn't running) we return a graceful
 * "unknown" so the page renders.
 */

export interface DashboardStatus {
  version: string;
  agenticEnabled: boolean;
}

const FALLBACK: DashboardStatus = {
  version: "—",
  agenticEnabled: true,
};

function backendBaseUrl(): string {
  const env = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";
  return env.trim().replace(/\/+$/, "");
}

export async function loadStatus(): Promise<DashboardStatus> {
  const url = `${backendBaseUrl()}/healthz`;
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return FALLBACK;
    const body = (await response.json()) as { version?: string };
    const version = typeof body.version === "string" ? body.version : "—";
    // The frontend has no read-only signal for the backend's
    // REPOPULSE_AGENTIC_ENABLED state; treat as "on" by default and rely
    // on the backend's own 202 disabled response if a workflow tries to
    // call while disabled (matches the M5 ADR-003 trust model).
    return { version, agenticEnabled: true };
  } catch {
    return FALLBACK;
  }
}

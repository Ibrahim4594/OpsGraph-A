/**
 * Server-side health probe used by the dashboard shell. Never throws —
 * during the build (when the backend isn't running) we return a graceful
 * "unknown" so the page renders.
 *
 * ``agenticEnabled`` reads the kill-switch state from /healthz, which
 * itself reads ``REPOPULSE_AGENTIC_ENABLED`` per request (see ADR-003 §3).
 * That keeps the StatusBar honest: a flipped env var shows up in the UI
 * on the very next dashboard refresh, no restart needed.
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
    const body = (await response.json()) as {
      version?: string;
      agentic_enabled?: boolean;
    };
    return {
      version: typeof body.version === "string" ? body.version : "—",
      agenticEnabled:
        typeof body.agentic_enabled === "boolean" ? body.agentic_enabled : true,
    };
  } catch {
    return FALLBACK;
  }
}

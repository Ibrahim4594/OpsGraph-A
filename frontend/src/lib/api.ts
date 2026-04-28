/**
 * Typed fetch wrapper for the RepoPulse backend.
 *
 * All requests are same-origin in production (operator UI behind reverse
 * proxy) and target ``NEXT_PUBLIC_BACKEND_URL`` in development.
 */

export type RecommendationState = "pending" | "approved" | "rejected" | "observed";
export type ActionCategory = "observe" | "triage" | "escalate" | "rollback";
export type RiskLevel = "low" | "medium" | "high";
export type BurnBand = "ok" | "slow" | "fast";
export type ActionKind = "approve" | "reject" | "observe" | "workflow-run";

export interface Recommendation {
  recommendation_id: string;
  incident_id: string;
  action_category: ActionCategory;
  confidence: number;
  risk_level: RiskLevel;
  evidence_trace: string[];
  state: RecommendationState;
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
  count: number;
}

export interface IncidentSummary {
  incident_id: string;
  started_at: string;
  ended_at: string;
  sources: string[];
  anomaly_count: number;
  event_count: number;
}

export interface IncidentsResponse {
  incidents: IncidentSummary[];
  count: number;
}

export interface ActionEntry {
  at: string;
  kind: ActionKind;
  recommendation_id: string | null;
  actor: string;
  summary: string;
}

export interface ActionsResponse {
  actions: ActionEntry[];
  count: number;
}

export interface SloResponse {
  service: string;
  total_events: number;
  error_events: number;
  availability: number;
  target: number;
  error_budget_remaining: number;
  burn_rate: number;
  burn_band: BurnBand;
}

export interface ApprovalResponse {
  recommendation_id: string;
  state: RecommendationState;
  actor: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function backendBaseUrl(): string {
  const env =
    typeof process !== "undefined"
      ? (process.env.NEXT_PUBLIC_BACKEND_URL ?? "")
      : "";
  return env.trim().replace(/\/+$/, "");
}

/** Bearer for pipeline APIs (must match ``REPOPULSE_API_SHARED_SECRET``). */
function pipelineAuthHeaders(): HeadersInit {
  const secret =
    typeof process !== "undefined"
      ? (process.env.NEXT_PUBLIC_API_SHARED_SECRET ?? "").trim()
      : "";
  if (!secret) return {};
  return { Authorization: `Bearer ${secret}` };
}

async function request<T>(
  path: string,
  init?: RequestInit & { signal?: AbortSignal },
): Promise<T> {
  const url = `${backendBaseUrl()}${path}`;
  const headers = new Headers(init?.headers);
  const auth = pipelineAuthHeaders();
  if (typeof auth === "object" && !Array.isArray(auth)) {
    for (const [k, v] of Object.entries(auth)) {
      if (v) headers.set(k, v);
    }
  }
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(url, {
    ...init,
    headers,
    cache: "no-store",
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : `request failed (${response.status})`,
      detail,
    );
  }
  return body as T;
}

export async function getRecommendations(
  init?: { limit?: number },
): Promise<RecommendationsResponse> {
  const limit = init?.limit ?? 10;
  return request<RecommendationsResponse>(
    `/api/v1/recommendations?limit=${limit}`,
  );
}

export async function getIncidents(init?: {
  limit?: number;
}): Promise<IncidentsResponse> {
  const limit = init?.limit ?? 50;
  return request<IncidentsResponse>(`/api/v1/incidents?limit=${limit}`);
}

export async function getActions(init?: {
  limit?: number;
}): Promise<ActionsResponse> {
  const limit = init?.limit ?? 50;
  return request<ActionsResponse>(`/api/v1/actions?limit=${limit}`);
}

export async function getSlo(init?: { target?: number }): Promise<SloResponse> {
  const target = init?.target ?? 0.99;
  return request<SloResponse>(`/api/v1/slo?target=${target}`);
}

export async function approveRecommendation(
  id: string,
): Promise<ApprovalResponse> {
  return request<ApprovalResponse>(`/api/v1/recommendations/${id}/approve`, {
    method: "POST",
  });
}

export async function rejectRecommendation(
  id: string,
  reason?: string,
): Promise<ApprovalResponse> {
  const body: Record<string, string | undefined> = {};
  if (reason !== undefined) body.reason = reason;
  return request<ApprovalResponse>(`/api/v1/recommendations/${id}/reject`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

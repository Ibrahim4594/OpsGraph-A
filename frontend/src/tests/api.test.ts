import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  approveRecommendation,
  getActions,
  getIncidents,
  getRecommendations,
  getSlo,
  rejectRecommendation,
} from "@/lib/api";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function ok(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("getRecommendations", () => {
  it("parses count + recommendations", async () => {
    fetchMock.mockResolvedValueOnce(
      ok({
        recommendations: [
          {
            recommendation_id: "r1",
            incident_id: "i1",
            action_category: "triage",
            confidence: 0.7,
            risk_level: "low",
            evidence_trace: ["R2: ..."],
            state: "pending",
          },
        ],
        count: 1,
      }),
    );
    const r = await getRecommendations();
    expect(r.count).toBe(1);
    expect(r.recommendations[0].state).toBe("pending");
    expect(r.recommendations[0].action_category).toBe("triage");
  });

  it("hits the configured base URL", async () => {
    fetchMock.mockResolvedValueOnce(ok({ recommendations: [], count: 0 }));
    await getRecommendations();
    const callUrl = fetchMock.mock.calls[0][0] as string;
    expect(callUrl).toContain("/api/v1/recommendations");
  });
});

describe("getIncidents / getActions / getSlo", () => {
  it("getIncidents returns parsed body", async () => {
    fetchMock.mockResolvedValueOnce(ok({ incidents: [], count: 0 }));
    const out = await getIncidents();
    expect(out.count).toBe(0);
  });

  it("getActions returns parsed body", async () => {
    fetchMock.mockResolvedValueOnce(ok({ actions: [], count: 0 }));
    const out = await getActions();
    expect(out.count).toBe(0);
  });

  it("getSlo returns parsed body", async () => {
    fetchMock.mockResolvedValueOnce(
      ok({
        service: "RepoPulse",
        total_events: 0,
        error_events: 0,
        availability: 1.0,
        target: 0.99,
        error_budget_remaining: 0.01,
        burn_rate: 0.0,
        burn_band: "ok",
      }),
    );
    const out = await getSlo();
    expect(out.burn_band).toBe("ok");
    expect(out.target).toBe(0.99);
  });
});

describe("approve/reject", () => {
  it("approveRecommendation POSTs operator and returns the new state", async () => {
    fetchMock.mockResolvedValueOnce(
      ok({ recommendation_id: "r1", state: "approved", actor: "alice" }),
    );
    const out = await approveRecommendation("r1", "alice");
    expect(out.state).toBe("approved");
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ operator: "alice" });
  });

  it("rejectRecommendation POSTs operator + reason", async () => {
    fetchMock.mockResolvedValueOnce(
      ok({ recommendation_id: "r1", state: "rejected", actor: "bob" }),
    );
    const out = await rejectRecommendation("r1", "bob", "false positive");
    expect(out.state).toBe("rejected");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init?.body as string)).toEqual({
      operator: "bob",
      reason: "false positive",
    });
  });

  it("throws ApiError on 409", async () => {
    fetchMock.mockResolvedValueOnce(
      ok({ detail: "cannot transition approved → approved" }, 409),
    );
    await expect(approveRecommendation("r1", "alice")).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it("throws ApiError on 404", async () => {
    fetchMock.mockResolvedValueOnce(ok({ detail: "not found" }, 404));
    await expect(
      rejectRecommendation("r1", "alice", undefined),
    ).rejects.toMatchObject({ status: 404 });
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApprovalActions } from "@/components/recommendations/ApprovalActions";

const mocks = vi.hoisted(() => ({
  approve: vi.fn(),
  reject: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  approveRecommendation: mocks.approve,
  rejectRecommendation: mocks.reject,
}));

beforeEach(() => {
  mocks.approve.mockReset();
  mocks.reject.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApprovalActions", () => {
  it("renders approve + reject buttons when state is pending", () => {
    render(<ApprovalActions id="r1" initialState="pending" />);
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
  });

  it("hides action buttons when state is non-pending", () => {
    render(<ApprovalActions id="r1" initialState="approved" />);
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(screen.getByText(/approved/i)).toBeInTheDocument();
  });

  it("calls approveRecommendation and shows the new state on click", async () => {
    mocks.approve.mockResolvedValueOnce({
      recommendation_id: "r1",
      state: "approved",
      actor: "alice",
    });
    render(<ApprovalActions id="r1" initialState="pending" operator="alice" />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(mocks.approve).toHaveBeenCalledWith("r1", "alice");
    expect(await screen.findByText(/approved/i)).toBeInTheDocument();
  });

  it("calls rejectRecommendation with the typed reason", async () => {
    mocks.reject.mockResolvedValueOnce({
      recommendation_id: "r1",
      state: "rejected",
      actor: "alice",
    });
    render(<ApprovalActions id="r1" initialState="pending" operator="alice" />);
    await userEvent.click(screen.getByRole("button", { name: /reject/i }));
    const textarea = await screen.findByRole("textbox", { name: /reason/i });
    await userEvent.type(textarea, "false positive");
    await userEvent.click(
      screen.getByRole("button", { name: /confirm reject/i }),
    );
    expect(mocks.reject).toHaveBeenCalledWith("r1", "alice", "false positive");
  });

  it("shows an error message if the API call fails", async () => {
    mocks.approve.mockRejectedValueOnce(new Error("boom"));
    render(<ApprovalActions id="r1" initialState="pending" operator="alice" />);
    await userEvent.click(screen.getByRole("button", { name: /approve/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/boom/i);
  });
});

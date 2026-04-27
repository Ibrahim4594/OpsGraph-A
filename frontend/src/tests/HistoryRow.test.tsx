import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HistoryRow } from "@/components/actions/HistoryRow";
import type { ActionEntry } from "@/lib/api";

const NOW = new Date("2026-04-27T12:30:00Z");

function entry(overrides: Partial<ActionEntry> = {}): ActionEntry {
  return {
    at: "2026-04-27T12:00:00Z",
    kind: "approve",
    recommendation_id: "rec-1",
    actor: "alice",
    summary: "",
    ...overrides,
  };
}

describe("HistoryRow", () => {
  it("renders kind, actor and relative time", () => {
    render(<HistoryRow entry={entry()} now={NOW} />);
    expect(screen.getByText("approve")).toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText(/30m ago/i)).toBeInTheDocument();
  });

  it("renders a 'system' actor for auto-observed entries", () => {
    render(
      <HistoryRow
        entry={entry({ kind: "observe", actor: "system" })}
        now={NOW}
      />,
    );
    expect(screen.getByText("system")).toBeInTheDocument();
    expect(screen.getByText("observe")).toBeInTheDocument();
  });

  it("renders the summary when present", () => {
    render(
      <HistoryRow
        entry={entry({ kind: "reject", summary: "false positive" })}
        now={NOW}
      />,
    );
    expect(screen.getByText("false positive")).toBeInTheDocument();
  });

  it("links the recommendation_id when present", () => {
    render(<HistoryRow entry={entry()} now={NOW} />);
    const link = screen.getByRole("link", { name: /rec-1/i });
    expect(link).toHaveAttribute(
      "href",
      "/recommendations#rec-1",
    );
  });

  it("renders no link for entries without a recommendation_id", () => {
    render(
      <HistoryRow
        entry={entry({ kind: "workflow-run", recommendation_id: null })}
        now={NOW}
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
  });
});

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { HistoryTable } from "@/components/actions/KindFilter";
import type { ActionEntry } from "@/lib/api";

function entry(
  kind: ActionEntry["kind"],
  actor: string,
  at = "2026-04-27T12:00:00Z",
): ActionEntry {
  return {
    at,
    kind,
    recommendation_id: kind === "workflow-run" ? null : "rec-1",
    actor,
    summary: "",
  };
}

describe("HistoryTable", () => {
  it("renders all action entries by default", () => {
    render(
      <HistoryTable
        actions={[
          entry("approve", "alice"),
          entry("reject", "bob"),
          entry("observe", "system"),
          entry("workflow-run", "agentic-issue-triage"),
        ]}
      />,
    );
    expect(screen.getAllByRole("row")).toHaveLength(5); // 1 header + 4 body
  });

  it("narrows to approve rows when the approve filter is selected", async () => {
    render(
      <HistoryTable
        actions={[
          entry("approve", "alice"),
          entry("reject", "bob"),
          entry("observe", "system"),
        ]}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "approve" }));
    const rows = screen.getAllByRole("row");
    // header + 1 approve row only
    expect(rows).toHaveLength(2);
    expect(within(rows[1]).getByText("alice")).toBeInTheDocument();
  });

  it("narrows to workflow-run rows", async () => {
    render(
      <HistoryTable
        actions={[
          entry("approve", "alice"),
          entry("workflow-run", "agentic-issue-triage"),
          entry("workflow-run", "agentic-doc-drift"),
        ]}
      />,
    );
    await userEvent.click(screen.getByRole("tab", { name: "workflow-run" }));
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3); // header + 2 workflow-run
  });

  it("aria-selected reflects the active filter", async () => {
    render(<HistoryTable actions={[entry("approve", "alice")]} />);
    expect(screen.getByRole("tab", { name: "all" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await userEvent.click(screen.getByRole("tab", { name: "approve" }));
    expect(screen.getByRole("tab", { name: "approve" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "all" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });
});

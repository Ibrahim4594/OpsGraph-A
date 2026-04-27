import { describe, expect, it } from "vitest";

import { runbookFor } from "@/lib/runbooks";

describe("runbookFor", () => {
  it("maps each known action category to a runbook URL", () => {
    expect(runbookFor("observe")).toMatch(/observe\.md$/);
    expect(runbookFor("triage")).toMatch(/triage\.md$/);
    expect(runbookFor("escalate")).toMatch(/escalate\.md$/);
    expect(runbookFor("rollback")).toMatch(/rollback\.md$/);
  });

  it("returns null for unknown categories", () => {
    expect(runbookFor("invent")).toBeNull();
  });

  it("URLs all share the same /docs/runbooks/ base", () => {
    expect(runbookFor("triage")).toContain("/docs/runbooks/");
  });
});

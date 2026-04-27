import { describe, expect, it } from "vitest";

import { formatPercent, formatRelative, formatBurnRate } from "@/lib/format";

describe("formatPercent", () => {
  it("formats with two decimals by default", () => {
    expect(formatPercent(0.985)).toBe("98.50%");
  });

  it("returns em-dash for null", () => {
    expect(formatPercent(null)).toBe("—");
  });
});

describe("formatRelative", () => {
  it("returns 'just now' for < 5 s ago", () => {
    const now = new Date("2026-04-27T12:00:00Z");
    const at = new Date("2026-04-27T11:59:58Z");
    expect(formatRelative(at, now)).toBe("just now");
  });

  it("returns Ns for sub-minute deltas", () => {
    const now = new Date("2026-04-27T12:00:30Z");
    const at = new Date("2026-04-27T12:00:00Z");
    expect(formatRelative(at, now)).toBe("30s ago");
  });

  it("returns Nm for sub-hour deltas", () => {
    const now = new Date("2026-04-27T12:30:00Z");
    const at = new Date("2026-04-27T12:00:00Z");
    expect(formatRelative(at, now)).toBe("30m ago");
  });

  it("returns Nh for sub-day deltas", () => {
    const now = new Date("2026-04-27T15:00:00Z");
    const at = new Date("2026-04-27T12:00:00Z");
    expect(formatRelative(at, now)).toBe("3h ago");
  });

  it("returns Nd for ≥ 1 day deltas", () => {
    const now = new Date("2026-04-30T12:00:00Z");
    const at = new Date("2026-04-27T12:00:00Z");
    expect(formatRelative(at, now)).toBe("3d ago");
  });
});

describe("formatBurnRate", () => {
  it("formats with one decimal and × suffix", () => {
    expect(formatBurnRate(2.0)).toBe("2.0×");
  });

  it("clamps to 99+× above 99", () => {
    expect(formatBurnRate(150)).toBe("99+×");
  });

  it("returns — for null", () => {
    expect(formatBurnRate(null)).toBe("—");
  });
});

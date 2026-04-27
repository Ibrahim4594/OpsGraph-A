import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SloCard } from "@/components/slo/SloCard";

describe("SloCard", () => {
  it("renders the value as percent and the target", () => {
    render(<SloCard label="Availability" value={0.985} target={0.99} />);
    expect(screen.getByText("98.50%")).toBeInTheDocument();
    expect(screen.getByText(/target 99\.00%/i)).toBeInTheDocument();
  });

  it("marks below-target with a warning band", () => {
    render(<SloCard label="Availability" value={0.985} target={0.99} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-band", "warning");
  });

  it("marks at-or-above target with success band", () => {
    render(<SloCard label="Availability" value={0.999} target={0.99} />);
    expect(screen.getByRole("status")).toHaveAttribute("data-band", "success");
  });

  it("renders '—' and an empty band when value is null", () => {
    render(<SloCard label="Availability" value={null} target={0.99} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute("data-band", "empty");
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BurnRateBadge } from "@/components/slo/BurnRateBadge";

describe("BurnRateBadge", () => {
  it("ok band uses success tone", () => {
    const { container } = render(<BurnRateBadge band="ok" rate={0.5} />);
    const badge = container.querySelector("[data-band='ok']");
    expect(badge).toBeTruthy();
    expect(screen.getByText("0.5×")).toBeInTheDocument();
  });

  it("slow band uses warning tone", () => {
    const { container } = render(<BurnRateBadge band="slow" rate={2.0} />);
    expect(container.querySelector("[data-band='slow']")).toBeTruthy();
  });

  it("fast band uses danger tone", () => {
    const { container } = render(<BurnRateBadge band="fast" rate={20.0} />);
    expect(container.querySelector("[data-band='fast']")).toBeTruthy();
  });
});

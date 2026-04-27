import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ToastProvider, useToast } from "@/components/ui/toast";

function Probe() {
  const toast = useToast();
  return (
    <div>
      <button onClick={() => toast.success("Approved", "rec-1 by alice")}>
        success
      </button>
      <button onClick={() => toast.error("Failed", "boom")}>error</button>
      <button onClick={() => toast.warning("Heads up")}>warning</button>
      <button onClick={() => toast.info("Note")}>info</button>
    </div>
  );
}

describe("ToastProvider + useToast", () => {
  it("renders a success toast with title and description", async () => {
    render(
      <ToastProvider>
        <Probe />
      </ToastProvider>,
    );
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "success" }));
    });
    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(await screen.findByText("rec-1 by alice")).toBeInTheDocument();
  });

  it("renders an error toast title", async () => {
    render(
      <ToastProvider>
        <Probe />
      </ToastProvider>,
    );
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "error" }));
    });
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });

  it("renders a warning toast", async () => {
    render(
      <ToastProvider>
        <Probe />
      </ToastProvider>,
    );
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "warning" }));
    });
    expect(await screen.findByText("Heads up")).toBeInTheDocument();
  });

  it("renders an info toast (default tone)", async () => {
    render(
      <ToastProvider>
        <Probe />
      </ToastProvider>,
    );
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "info" }));
    });
    expect(await screen.findByText("Note")).toBeInTheDocument();
  });
});

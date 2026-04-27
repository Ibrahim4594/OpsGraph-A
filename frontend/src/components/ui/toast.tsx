"use client";

/**
 * Toast layer for the operator dashboard.
 *
 * Adapted from `https://21st.dev/r/base-ui/toast-1` (Base UI primitive).
 * Differences from the upstream registry component:
 * - Import path: `@base-ui/react/toast` (current Base UI package; the
 *   registry references the now-renamed `@base-ui-components/react`).
 * - Theming uses our M4 design tokens (--color-bg-elev, --color-border,
 *   --color-success, --color-warning, --color-danger) instead of raw
 *   Tailwind grays.
 * - Exposes a `useToast()` helper with success/error/info/warning
 *   variants that map to our band tones.
 * - Provider lives once in the root layout; consumers only call
 *   `useToast()` from client components.
 */

import { Toast } from "@base-ui/react/toast";
import * as React from "react";

import { cn } from "@/lib/utils";

type ToastTone = "neutral" | "success" | "warning" | "error";

const TONE_BORDER: Record<ToastTone, string> = {
  neutral: "border-[color:var(--color-border-strong)]",
  success: "border-[color:rgba(16,185,129,0.4)]",
  warning: "border-[color:rgba(245,158,11,0.4)]",
  error: "border-[color:rgba(239,68,68,0.4)]",
};

const TONE_ACCENT: Record<ToastTone, string> = {
  neutral: "before:bg-[color:var(--color-fg-dim)]",
  success: "before:bg-[color:var(--color-success)]",
  warning: "before:bg-[color:var(--color-warning)]",
  error: "before:bg-[color:var(--color-danger)]",
};

interface ToastData {
  tone?: ToastTone;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  return (
    <Toast.Provider timeout={5000}>
      {children}
      <Toast.Portal>
        <Toast.Viewport className="fixed bottom-4 right-4 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col">
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  );
}

function ToastList() {
  const { toasts } = Toast.useToastManager();
  return toasts.map((toast) => {
    const tone = ((toast.data as ToastData)?.tone ?? "neutral") as ToastTone;
    return (
      <Toast.Root
        key={toast.id}
        toast={toast}
        className={cn(
          "absolute right-0 bottom-0 left-auto z-[calc(1000-var(--toast-index))]",
          "w-full rounded-[var(--radius)] border bg-[color:var(--color-bg-elev)]",
          "px-4 py-3 pl-5",
          "text-[color:var(--color-fg)]",
          "shadow-[0_4px_20px_rgba(0,0,0,0.5)]",
          "transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
          "[transition-property:opacity,transform]",
          "[transform:translateX(var(--toast-swipe-movement-x))_translateY(calc(var(--toast-swipe-movement-y)+calc(min(var(--toast-index),10)*-15px)))_scale(calc(max(0,1-(var(--toast-index)*0.06))))]",
          "data-[expanded]:[transform:translateX(var(--toast-swipe-movement-x))_translateY(calc(var(--toast-offset-y)*-1+calc(var(--toast-index)*var(--gap)*-1)+var(--toast-swipe-movement-y)))]",
          "data-[starting-style]:[transform:translateY(150%)]",
          "data-[ending-style]:opacity-0",
          "data-[ending-style]:[&:not([data-limited])]:[transform:translateY(150%)]",
          "data-[limited]:opacity-0",
          // Left accent stripe in tone color.
          "before:absolute before:left-0 before:top-3 before:bottom-3 before:w-1 before:rounded-r-full",
          TONE_BORDER[tone],
          TONE_ACCENT[tone],
        )}
        style={
          {
            "--gap": "0.75rem",
          } as React.CSSProperties
        }
      >
        <Toast.Title className="text-sm font-medium leading-snug" />
        <Toast.Description className="mt-1 text-xs leading-snug text-[color:var(--color-fg-muted)]" />
        <Toast.Close
          aria-label="Dismiss notification"
          className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded text-[color:var(--color-fg-muted)] hover:bg-[color:var(--color-bg-elev-2)] hover:text-[color:var(--color-fg)] focus-visible:outline-2 focus-visible:outline-[color:var(--color-primary)]"
        >
          <XIcon className="h-3.5 w-3.5" />
        </Toast.Close>
      </Toast.Root>
    );
  });
}

function XIcon(props: React.ComponentProps<"svg">) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

/**
 * Hook callable from any client component under <ToastProvider>.
 * Returns four convenience methods that pre-set the visual tone.
 */
export function useToast() {
  const manager = Toast.useToastManager();
  return React.useMemo(
    () => ({
      success(title: string, description?: string) {
        manager.add({ title, description, data: { tone: "success" } });
      },
      error(title: string, description?: string) {
        manager.add({ title, description, data: { tone: "error" } });
      },
      warning(title: string, description?: string) {
        manager.add({ title, description, data: { tone: "warning" } });
      },
      info(title: string, description?: string) {
        manager.add({ title, description, data: { tone: "neutral" } });
      },
    }),
    [manager],
  );
}

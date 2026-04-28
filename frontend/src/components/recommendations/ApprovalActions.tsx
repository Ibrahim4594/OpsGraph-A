"use client";

import { useState, useTransition } from "react";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/toast";
import {
  approveRecommendation,
  rejectRecommendation,
  type RecommendationState,
} from "@/lib/api";

const STATE_TONE: Record<RecommendationState, BadgeTone> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  observed: "neutral",
};

const STATE_LABEL: Record<RecommendationState, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  observed: "Observed",
};

export function ApprovalActions({
  id,
  initialState,
}: {
  id: string;
  initialState: RecommendationState;
}) {
  const [state, setState] = useState<RecommendationState>(initialState);
  const [error, setError] = useState<string | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  function onApprove() {
    setError(null);
    startTransition(async () => {
      try {
        const out = await approveRecommendation(id);
        setState(out.state);
        toast.success(
          "Recommendation approved",
          `${id.slice(0, 8)}… (${out.actor})`,
        );
      } catch (exc) {
        const msg = exc instanceof Error ? exc.message : String(exc);
        setError(msg);
        toast.error("Approve failed", msg);
      }
    });
  }

  function onConfirmReject() {
    setError(null);
    startTransition(async () => {
      try {
        const out = await rejectRecommendation(id, reason || undefined);
        setState(out.state);
        setRejectOpen(false);
        setReason("");
        toast.success(
          "Recommendation rejected",
          `${id.slice(0, 8)}… (${out.actor})`,
        );
      } catch (exc) {
        const msg = exc instanceof Error ? exc.message : String(exc);
        setError(msg);
        toast.error("Reject failed", msg);
      }
    });
  }

  if (state !== "pending") {
    return (
      <Badge tone={STATE_TONE[state]} aria-label={`State: ${STATE_LABEL[state]}`}>
        {STATE_LABEL[state]}
      </Badge>
    );
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex gap-2">
        <Button
          variant="primary"
          size="sm"
          onClick={onApprove}
          disabled={pending}
          aria-label="Approve recommendation"
        >
          {pending ? "Working…" : "Approve"}
        </Button>
        <Button
          variant="danger"
          size="sm"
          onClick={() => setRejectOpen(true)}
          disabled={pending}
          aria-label="Reject recommendation"
        >
          Reject
        </Button>
      </div>
      {rejectOpen ? (
        <div
          role="dialog"
          aria-modal="false"
          aria-label="Reject reason"
          className="flex flex-col gap-2 rounded-[var(--radius-sm)] border border-[color:var(--color-border)] bg-[color:var(--color-bg-elev-2)] p-3"
        >
          <label
            htmlFor={`reason-${id}`}
            className="text-xs text-[color:var(--color-fg-muted)]"
          >
            Reason (optional)
          </label>
          <textarea
            id={`reason-${id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            aria-label="Reason"
            className="w-64 resize-none rounded-[var(--radius-sm)] border border-[color:var(--color-border)] bg-[color:var(--color-bg)] px-2 py-1 text-sm focus:outline-none"
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setRejectOpen(false);
                setReason("");
              }}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={onConfirmReject}
              disabled={pending}
              aria-label="Confirm reject"
            >
              Confirm reject
            </Button>
          </div>
        </div>
      ) : null}
      {error ? (
        <div
          role="alert"
          className="rounded-[var(--radius-sm)] border border-[color:rgba(239,68,68,0.4)] bg-[color:rgba(239,68,68,0.08)] px-3 py-2 text-xs text-[color:var(--color-danger)]"
        >
          {error}
        </div>
      ) : null}
    </div>
  );
}

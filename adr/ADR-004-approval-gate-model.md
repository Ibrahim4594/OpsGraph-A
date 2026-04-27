# ADR-004: Approval Gate State Model

- **Status:** Accepted
- **Date:** 2026-04-27
- **Deciders:** Project owner (Ibrahim)
- **Supersedes:** —
- **Superseded by:** —

## Context

Milestone 4 ships an operator dashboard. Operators need to approve or reject ranked recommendations and see an audit trail. The M3 `Recommendation` dataclass has no concept of state — every recommendation is just "emitted" — and the orchestrator has no audit log. The M5 agentic workflows produce automated effects that should also surface in the same audit feed so operators can see "what humans did" and "what automation did" in one timeline.

We have three real choices for where the approval state and audit log live, and we need a state machine simple enough that the dashboard can render it without ambiguity.

## Decision

### 1. Recommendation gains a `state` field with four values

```
state: Literal["pending", "approved", "rejected", "observed"]
```

Initial state at emit time:

- `action_category == "observe"` (R1 fallback) → `state = "observed"` immediately. R1 is the "no-op recommendation" for incidents that don't match a real rule; gating it behind a human approval would create thousands of items the operator has to clear by hand. Auto-observe matches what the operator would do anyway.
- All other categories (`triage`, `escalate`, `rollback`) → `state = "pending"`.

Allowed transitions:

```
pending → approved   (operator chose to act)
pending → rejected   (operator dismissed — false positive, irrelevant, etc.)
```

No other transitions. Re-approving an approved recommendation, undoing a rejection, or transitioning observed → anything returns 409 Conflict from the API.

### 2. Action history is a separate, bounded deque on the orchestrator

```python
@dataclass(frozen=True)
class ActionHistoryEntry:
    at: datetime
    kind: Literal["approve", "reject", "observe", "workflow-run"]
    recommendation_id: UUID | None
    actor: str   # "alice", "bob@team", or "system"
    summary: str  # operator's reason, or workflow run name + conclusion
```

Bounded `deque(maxlen=200)` — same cap as incidents, so memory stays predictable. When the cap is hit the oldest entry falls off; the audit trail is intentionally **not** durable in M4 (matches ADR-002's no-persistence stance). Every transition writes one entry, including the auto-observe transition for R1 (so the audit shows even the "system did nothing" decisions).

### 3. M5 agentic-workflow events feed into the same history

The M5 `/api/v1/github/usage` endpoint already produces a `NormalizedEvent` with `source="agentic-workflow"`. M4 also writes a `kind="workflow-run"` `ActionHistoryEntry` for the same event so the dashboard can render human and automated actions in one feed. Operator can filter by kind in the UI.

### 4. State changes happen via dedicated POST endpoints, not via PATCH or generic mutators

Two narrow routes — `POST /api/v1/recommendations/{id}/approve` and `/reject` — each with a small body model that requires `operator: str` (and `reason` on reject). The narrow shape:

- Makes audit logging trivial (every successful POST writes one history entry).
- Surfaces "operator" as a first-class concept that the dashboard can require (in M4 it's a free-text field; in a future milestone it becomes a session identity).
- Makes 409 unambiguous: "you tried to do X, but state is already Y."

### 5. R1 auto-observed entries record `actor="system"`

So the audit is complete and "what was decided automatically" is visible at a glance. The dashboard can dim system rows so they don't dominate the operator's attention.

## Alternatives considered

### State on the orchestrator's recommendation deque (mutate in place)

Rejected. The M3 deque holds frozen `Recommendation` dataclasses. Mutating them would either require unfreezing (loses immutability guarantees) or replacing entries in the deque (awkward — deques aren't index-friendly). A side dict `{recommendation_id: state}` lookup, combined with a `dataclasses.replace` at read-out time, keeps the M3 invariant.

### Generic PATCH `/api/v1/recommendations/{id}`

Rejected. Generic PATCH is a footgun for state machines: the body shape grows over time, validation becomes a maze, and the API contract no longer says what *transitions* are legal — only what *fields* exist. Two narrow endpoints encode the legal transitions in the URL.

### Persistent action history in a database

Rejected for M4. Persistence is deferred per ADR-002. The bounded in-memory deque matches what M3 incidents do; both can move to durable storage in the same future milestone without changing the API shape.

### Auto-approving `escalate` and `rollback` after a timeout

Considered and rejected. The whole point of the approval gate is that destructive recommendations don't fire without human attention. A timeout would re-introduce the failure mode (automation acting unattended) the gate exists to prevent. If operators want auto-approval for some categories later, that's an explicit follow-up ADR with its own risk analysis — not the default.

## Consequences

### Positive

- **State machine is small and verifiable.** Four states, two transitions. Property-based testing-friendly.
- **Audit log is unified.** Humans + automation share one feed; operators see both in one place.
- **API surface stays narrow.** Two new POST endpoints, no generic mutator. 404/409/200 are unambiguous.
- **R1 auto-observe keeps the inbox readable.** The high-volume "no-op" recommendations don't drown out the items needing attention.
- **Rollback is just `git revert`.** The state field is additive; removing it is trivial.

### Negative

- **No durable audit trail in M4.** Restart loses history. Acceptable per the persistence-deferral story; documented in `docs/agentic-workflows.md` and the M4 handoff.
- **Single-operator concurrency only.** Two operators racing to approve the same recommendation will see one 200 and one 409. That's the right outcome, but if two-operator workflows become common, a richer concurrency model (last-writer-wins with a `requested_by` queue) would be needed.
- **Free-text `operator` field is not authenticated.** Any caller can claim to be "alice." Auth for the operator UI is explicitly out of scope for M4 (UI is local-only / behind reverse-proxy in prod). When SSO lands, `operator` becomes derived from the session.

### Neutral / future work

- A `revoke_approval` transition could be added later if the surface need arises (e.g. operator approved by mistake before the action ran). Today, rolling forward is faster than rolling back through state.
- Persistence: when the orchestrator gets a real store, the action-history deque + recommendation-state map become two tables; the API contract doesn't change.
- Optional `expected_state` field on the POST body for compare-and-swap semantics, blocking lost-update problems if/when concurrency grows.

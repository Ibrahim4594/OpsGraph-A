# Milestone 4 — Operator Dashboard UI — Execution Plan

> **For agentic workers:** Continues from `v0.4.0-m5`. REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Required skills, invoked explicitly per task: `design-system` (loaded once at the start — provides dashboard tokens), `superpowers:writing-plans` (this doc), `superpowers:test-driven-development` (every UI behavior change), `superpowers:systematic-debugging` (any non-trivial UI/runtime failure), `superpowers:verification-before-completion` (before claiming done), `superpowers:requesting-code-review` (before final handoff), `superpowers:receiving-code-review` (if findings raised), `superpowers:dispatching-parallel-agents` (only if truly independent — otherwise document why not used), `frontend-design:frontend-design` (for distinctive production-grade UI), `playwright-cli` (browser-based a11y + keyboard verification). Constraints unchanged: anti-hallucination strict, evidence-first reporting, M5 security constraints intact.

## Goal

Lift the UI Hold Gate. Build an operator dashboard on top of the M3 + M5 backend so a human operator can see SLOs, incidents, and ranked recommendations; approve or reject each recommendation; track the resulting action history; and link out to a runbook per recommendation type. Tailwind CSS 4 + shadcn/ui baseline, dark cloud-platform aesthetic from the parked `design-system` skill (IBM Plex Sans, primary `#0C5CAB`, surface `#09090b`, 8 pt grid, WCAG 2.2 AA).

## Architecture

```
                Browser (Next.js 15 App Router, RSC + Client islands)
                     │
                     │  fetch('/api/v1/...')   (proxy via Next route handlers in dev)
                     ▼
              FastAPI backend (M1–M5)
                     │
                     ├── GET /api/v1/slo               (NEW M4: derived from orchestrator events)
                     ├── GET /api/v1/incidents         (NEW M4: orchestrator.snapshot_incidents)
                     ├── GET /api/v1/recommendations   (M3, gains `state` field)
                     ├── POST /api/v1/recommendations/{id}/approve  (NEW M4)
                     ├── POST /api/v1/recommendations/{id}/reject   (NEW M4)
                     └── GET /api/v1/actions           (NEW M4: action_history from orchestrator)
```

Two layers ship in M4:

1. **Backend extensions** (Python, TDD). Recommendation gains an immutable `state: pending|approved|rejected|observed`. Operator transitions write an `ActionHistoryEntry` to the orchestrator. R1 (`observe`) recommendations are auto-`observed` so the inbox shows only items needing attention. Action history also captures `agentic-workflow` events so M5's automation feed appears alongside human actions.

2. **Frontend** (Next.js 15 + TypeScript + Tailwind 4 + shadcn/ui). Four pages: SLO board (`/`), incidents timeline (`/incidents`), recommendations inbox (`/recommendations`), action history (`/actions`). Server components for data fetching, client components for the approval gate's optimistic transitions. vitest + Testing Library for unit tests; playwright-cli for keyboard/focus/contrast checks. Lighthouse via chrome-devtools-mcp for performance evidence.

## Tech Stack

- Backend: existing FastAPI 0.136 + pydantic 2.13. No new runtime deps.
- Frontend:
  - Next.js 15 (App Router) + TypeScript 5
  - Tailwind CSS 4 + shadcn/ui (radix primitives)
  - vitest 2 + @testing-library/react + jsdom (component unit tests)
  - playwright-cli (project-installed; browser-based keyboard + a11y + screenshots)
  - lucide-react icons (shadcn default)
  - Fonts: IBM Plex Sans via `next/font/google`

## File Structure (additions)

```
backend/src/repopulse/
├── pipeline/
│   └── orchestrator.py              (modify — add approval state + action history)
├── api/
│   ├── recommendations.py           (modify — POST /approve|reject + state in GET shape)
│   ├── incidents.py                 (NEW — GET /api/v1/incidents)
│   ├── actions.py                   (NEW — GET /api/v1/actions)
│   └── slo.py                       (NEW — GET /api/v1/slo)
├── recommend/engine.py              (modify — Recommendation gains `state` field)
└── slo.py                           (existing pure functions reused)

backend/tests/
├── test_recommendations_api.py      (modify — approval state + transitions)
├── test_incidents_api.py            (NEW)
├── test_actions_api.py              (NEW)
├── test_slo_api.py                  (NEW)
└── test_orchestrator.py             (modify — action history regression)

frontend/                            (NEW Next.js 15 app)
├── package.json
├── next.config.mjs
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
├── vitest.config.ts
├── components.json                  (shadcn manifest)
├── public/
├── src/
│   ├── app/
│   │   ├── layout.tsx               (root shell — IBM Plex Sans, dark theme)
│   │   ├── globals.css              (tokens from design-system skill)
│   │   ├── page.tsx                 (SLO board — server component)
│   │   ├── incidents/page.tsx       (timeline)
│   │   ├── recommendations/page.tsx (inbox)
│   │   └── actions/page.tsx         (history)
│   ├── components/
│   │   ├── shell/Sidebar.tsx        (nav)
│   │   ├── shell/StatusBar.tsx      (top bar — kill-switch indicator + version)
│   │   ├── slo/SloCard.tsx
│   │   ├── slo/BurnRateBadge.tsx
│   │   ├── incidents/Timeline.tsx
│   │   ├── recommendations/RecCard.tsx
│   │   ├── recommendations/ApprovalActions.tsx (client island)
│   │   ├── recommendations/RunbookLink.tsx
│   │   ├── actions/HistoryRow.tsx
│   │   └── ui/                      (shadcn-installed primitives — Button, Badge, Card, etc.)
│   ├── lib/
│   │   ├── api.ts                   (typed fetch wrapper)
│   │   ├── runbooks.ts              (action_category → runbook URL mapping)
│   │   └── format.ts                (timestamp + percentage helpers)
│   └── tests/
│       ├── api.test.ts
│       ├── format.test.ts
│       ├── SloCard.test.tsx
│       ├── ApprovalActions.test.tsx
│       └── runbooks.test.ts

docs/
├── ui-design-system.md              (modify — finalize with M4 outcomes)
├── runbooks/
│   ├── observe.md                   (M4 — what "observe" means)
│   ├── triage.md                    (M4)
│   ├── escalate.md                  (M4)
│   └── rollback.md                  (M4)
└── superpowers/plans/
    ├── milestone-4-handoff.md       (NEW — at end)
    └── m4-evidence/                 (NEW — screenshots, lighthouse JSON, a11y report)

adr/
└── ADR-004-approval-gate-model.md   (NEW — state machine + auto-transitions)
```

## Trust + Security (M5 invariants honored)

- The four new backend routes are read-only or operator-only mutations — no new secrets, no new GitHub-side write effects.
- Approval/rejection endpoints reuse no auth in M4 (operator UI is local-only / behind reverse-proxy in prod). **Auth for the operator UI is explicitly out of scope** — documented in the M4 handoff §"Risks". When the dashboard ships behind a real domain a follow-up milestone wires SSO; until then, README warns operators not to expose port directly.
- The kill-switch indicator in the StatusBar reads `REPOPULSE_AGENTIC_ENABLED` and reflects it visibly; no UI button to flip it (intentional — kill switch lives in deployment config per ADR-003).
- No outbound network from the frontend other than the same-origin backend.

---

## Task 1 — M4 plan + ADR-004

**Files:**
- Create: `plans/milestone-4-execution-plan.md` (this file)
- Create: `adr/ADR-004-approval-gate-model.md`

- [ ] **Step 1: Save this plan** (already saved if you're reading it).

- [ ] **Step 2: Write ADR-004 — approval gate state model**

States: `pending → approved | rejected | observed`. Auto-transitions: R1 (`observe`) → `observed` immediately on emission. R2/R3/R4 stay `pending` until an operator acts. Action-history entry written on every transition (including auto-observed). Bounded action-history deque (max 200, matches incidents). Reasoning in the ADR's "Decision" + "Alternatives considered" sections.

- [ ] **Step 3: Commit**

```bash
git add plans/milestone-4-execution-plan.md adr/ADR-004-approval-gate-model.md
git commit -m "plan: M4 execution plan + ADR-004 (approval gate state model)"
```

---

## Task 2 — TDD: GET /api/v1/incidents

**Files:**
- Create: `backend/src/repopulse/api/incidents.py`
- Modify: `backend/src/repopulse/main.py` (register router)
- Modify: `backend/src/repopulse/pipeline/orchestrator.py` (add `latest_incidents(limit)` if not present)
- Test: `backend/tests/test_incidents_api.py`

Response shape:

```json
{
  "incidents": [
    {
      "incident_id": "<uuid>",
      "started_at": "2026-04-27T12:00:00Z",
      "ended_at":   "2026-04-27T12:04:30Z",
      "sources":    ["github", "otel-metrics"],
      "anomaly_count": 2,
      "event_count":   5
    }
  ],
  "count": 1
}
```

- [ ] **Step 1: Write failing test (`test_incidents_api.py`)**

```python
"""Tests for GET /api/v1/incidents."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from repopulse.anomaly.detector import Anomaly
from repopulse.api.events import EventEnvelope
from repopulse.main import create_app
from repopulse.pipeline.orchestrator import PipelineOrchestrator

_T0 = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)


@pytest.fixture
def populated_orchestrator() -> PipelineOrchestrator:
    orch = PipelineOrchestrator()
    orch.ingest(
        EventEnvelope.model_validate(
            {"event_id": uuid4(), "source": "github", "kind": "push", "payload": {}}
        ),
        received_at=_T0,
    )
    orch.record_anomalies([
        Anomaly(
            timestamp=_T0,
            value=200.0,
            baseline_median=10.0,
            baseline_mad=1.0,
            score=20.0,
            severity="critical",
            series_name="otel-metrics",
        )
    ])
    orch.evaluate()
    return orch


def test_incidents_endpoint_returns_empty_when_orchestrator_empty() -> None:
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/api/v1/incidents")
    assert r.status_code == 200
    assert r.json() == {"incidents": [], "count": 0}


def test_incidents_endpoint_returns_orchestrator_incidents(
    populated_orchestrator: PipelineOrchestrator,
) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as c:
        r = c.get("/api/v1/incidents")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    inc = body["incidents"][0]
    assert "incident_id" in inc
    assert sorted(inc["sources"]) == ["github", "otel-metrics"]
    assert inc["anomaly_count"] == 1
    assert inc["event_count"] == 1


def test_incidents_endpoint_respects_limit(
    populated_orchestrator: PipelineOrchestrator,
) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as c:
        r = c.get("/api/v1/incidents?limit=0")
    assert r.json()["count"] == 0
```

- [ ] **Step 2: Run RED**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_incidents_api.py -v`
Expected: 404 / `ModuleNotFoundError`.

- [ ] **Step 3: Add `latest_incidents` to orchestrator**

```python
# backend/src/repopulse/pipeline/orchestrator.py — append to class
def latest_incidents(self, limit: int = 50) -> list[Incident]:
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit!r}")
    return list(self._incidents)[-limit:][::-1]
```

- [ ] **Step 4: Implement `incidents.py`**

```python
"""GET /api/v1/incidents — read-only view of orchestrator incidents."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.get("/incidents")
def list_incidents(
    request: Request,
    limit: int = Query(default=50, ge=0, le=200),
) -> dict[str, object]:
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        return {"incidents": [], "count": 0}
    incidents = orchestrator.latest_incidents(limit=limit)
    out = [
        {
            "incident_id": str(inc.incident_id),
            "started_at": inc.started_at.isoformat(),
            "ended_at": inc.ended_at.isoformat(),
            "sources": sorted(inc.sources),
            "anomaly_count": len(inc.anomalies),
            "event_count": len(inc.events),
        }
        for inc in incidents
    ]
    return {"incidents": out, "count": len(out)}
```

- [ ] **Step 5: Wire router in `main.py`**

```python
from repopulse.api.incidents import router as incidents_router
# ...
fastapi_app.include_router(incidents_router)
```

- [ ] **Step 6: Run GREEN**

Run: `cd backend && ./.venv/Scripts/python -m pytest tests/test_incidents_api.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/src/repopulse/api/incidents.py backend/src/repopulse/main.py backend/src/repopulse/pipeline/orchestrator.py backend/tests/test_incidents_api.py
git commit -m "feat(api): GET /api/v1/incidents exposes orchestrator incidents (TDD)"
```

---

## Task 3 — TDD: Recommendation.state + approval gate

**Files:**
- Modify: `backend/src/repopulse/recommend/engine.py` (add `state` to `Recommendation`)
- Modify: `backend/src/repopulse/pipeline/orchestrator.py` (action history + transition methods)
- Modify: `backend/src/repopulse/api/recommendations.py` (POST /approve + /reject; serialize state)
- Test: `backend/tests/test_recommendations_api.py` (new tests for transitions)
- Test: `backend/tests/test_recommend.py` (R1 default-observed)

State machine:

```
emit() → state = "observed" if action_category == "observe" else "pending"

POST /approve   pending → approved
POST /reject    pending → rejected
(no other transitions; 409 on illegal)
```

- [ ] **Step 1: Write failing tests (`test_recommendations_api.py`, append)**

```python
def test_approve_pending_recommendation_transitions_to_approved(
    populated_orchestrator,  # fixture seeds an R3-firing pending rec
) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as c:
        rec_id = c.get("/api/v1/recommendations").json()["recommendations"][0]["recommendation_id"]
        r = c.post(f"/api/v1/recommendations/{rec_id}/approve",
                   json={"operator": "alice"})
    assert r.status_code == 200
    assert r.json()["state"] == "approved"
    assert r.json()["actor"] == "alice"


def test_reject_pending_recommendation_transitions_to_rejected(
    populated_orchestrator,
) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as c:
        rec_id = c.get("/api/v1/recommendations").json()["recommendations"][0]["recommendation_id"]
        r = c.post(f"/api/v1/recommendations/{rec_id}/reject",
                   json={"operator": "bob", "reason": "false positive"})
    assert r.status_code == 200
    assert r.json()["state"] == "rejected"


def test_approve_already_approved_returns_409(populated_orchestrator) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as c:
        rec_id = c.get("/api/v1/recommendations").json()["recommendations"][0]["recommendation_id"]
        c.post(f"/api/v1/recommendations/{rec_id}/approve", json={"operator": "x"})
        r = c.post(f"/api/v1/recommendations/{rec_id}/approve", json={"operator": "y"})
    assert r.status_code == 409


def test_approve_unknown_id_returns_404(populated_orchestrator) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as c:
        r = c.post("/api/v1/recommendations/00000000-0000-0000-0000-000000000000/approve",
                   json={"operator": "x"})
    assert r.status_code == 404
```

```python
# test_recommend.py — append
def test_recommend_observe_starts_observed() -> None:
    """R1 (observe) auto-transitions to observed; no human approval needed."""
    incident = _empty_incident()
    rec = recommend(incident)
    assert rec.action_category == "observe"
    assert rec.state == "observed"


def test_recommend_non_observe_starts_pending() -> None:
    incident = _r3_incident()  # ≥2 anomalies fixture
    rec = recommend(incident)
    assert rec.action_category in ("triage", "escalate", "rollback")
    assert rec.state == "pending"
```

- [ ] **Step 2: Run RED**

All four new API tests fail with 404 (no route). Recommend tests fail because `state` doesn't exist on the dataclass.

- [ ] **Step 3: Add `state` to `Recommendation`**

```python
# recommend/engine.py
from typing import Literal

State = Literal["pending", "approved", "rejected", "observed"]

@dataclass(frozen=True)
class Recommendation:
    # ... existing fields ...
    state: State = "pending"

def recommend(incident: Incident) -> Recommendation:
    # ... existing logic that picks action_category ...
    state: State = "observed" if action_category == "observe" else "pending"
    return Recommendation(
        recommendation_id=uuid4(),
        incident_id=incident.incident_id,
        action_category=action_category,
        confidence=confidence,
        risk_level=risk_level,
        evidence_trace=tuple(trace),
        state=state,
    )
```

- [ ] **Step 4: Add transition methods + action history to orchestrator**

```python
# pipeline/orchestrator.py — additions

@dataclass(frozen=True)
class ActionHistoryEntry:
    at: datetime
    kind: Literal["approve", "reject", "observe", "workflow-run"]
    recommendation_id: UUID | None
    actor: str
    summary: str

# inside __init__:
self._action_history: deque[ActionHistoryEntry] = deque(maxlen=200)
self._rec_state: dict[UUID, State] = {}

def transition_recommendation(
    self,
    rec_id: UUID,
    *,
    to_state: Literal["approved", "rejected"],
    actor: str,
    reason: str | None = None,
) -> Recommendation:
    rec = self._find_recommendation(rec_id)
    if rec is None:
        raise KeyError(rec_id)
    current = self._rec_state.get(rec_id, rec.state)
    if current != "pending":
        raise ValueError(f"cannot transition {current!r} → {to_state!r}")
    self._rec_state[rec_id] = to_state
    self._action_history.append(
        ActionHistoryEntry(
            at=datetime.now(UTC),
            kind="approve" if to_state == "approved" else "reject",
            recommendation_id=rec_id,
            actor=actor,
            summary=reason or "",
        )
    )
    return replace(rec, state=to_state)

def _find_recommendation(self, rec_id: UUID) -> Recommendation | None:
    for r in self._recommendations:
        if r.recommendation_id == rec_id:
            return r
    return None

def latest_actions(self, limit: int = 50) -> list[ActionHistoryEntry]:
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit!r}")
    return list(self._action_history)[-limit:][::-1]
```

Also: when `evaluate()` emits R1 recommendations they're already `state="observed"` at construction time, but write an `ActionHistoryEntry(kind="observe", actor="system", ...)` so the audit trail is complete.

- [ ] **Step 5: Add the POST routes to `recommendations.py`**

```python
class _ApproveBody(BaseModel):
    operator: str = Field(min_length=1, max_length=128)


class _RejectBody(BaseModel):
    operator: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=512)


@router.post("/recommendations/{rec_id}/approve")
def approve(rec_id: UUID, body: _ApproveBody, request: Request) -> dict[str, object]:
    orchestrator = request.app.state.orchestrator
    try:
        rec = orchestrator.transition_recommendation(
            rec_id, to_state="approved", actor=body.operator
        )
    except KeyError:
        raise HTTPException(404, "recommendation not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"recommendation_id": str(rec_id), "state": rec.state, "actor": body.operator}


@router.post("/recommendations/{rec_id}/reject")
def reject(rec_id: UUID, body: _RejectBody, request: Request) -> dict[str, object]:
    orchestrator = request.app.state.orchestrator
    try:
        rec = orchestrator.transition_recommendation(
            rec_id, to_state="rejected", actor=body.operator, reason=body.reason
        )
    except KeyError:
        raise HTTPException(404, "recommendation not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"recommendation_id": str(rec_id), "state": rec.state, "actor": body.operator}
```

Also serialize `state` in the existing GET response.

- [ ] **Step 6: Run GREEN**

Run: `pytest tests/test_recommendations_api.py tests/test_recommend.py tests/test_orchestrator.py -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(approval): Recommendation.state + POST approve/reject + action history (TDD)"
```

---

## Task 4 — TDD: GET /api/v1/actions

**Files:**
- Create: `backend/src/repopulse/api/actions.py`
- Modify: `backend/src/repopulse/main.py`
- Test: `backend/tests/test_actions_api.py`

Returns the orchestrator's action history (newest-first), including human approve/reject, R1 auto-observe, and `agentic-workflow` workflow-run entries.

- [ ] **Step 1: Write failing test**

```python
def test_actions_endpoint_returns_history_newest_first(populated_orchestrator) -> None:
    app = create_app(orchestrator=populated_orchestrator)
    with TestClient(app) as c:
        rec_id = c.get("/api/v1/recommendations").json()["recommendations"][0]["recommendation_id"]
        c.post(f"/api/v1/recommendations/{rec_id}/approve", json={"operator": "alice"})
        r = c.get("/api/v1/actions")
    body = r.json()
    assert body["count"] >= 1
    first = body["actions"][0]
    assert first["kind"] in ("approve", "observe")
    assert first["actor"] in ("alice", "system")
    assert "at" in first
```

- [ ] **Step 2: Run RED**, **Step 3: Implement** (router calls `orchestrator.latest_actions`), **Step 4: GREEN**, **Step 5: Commit**

```bash
git add -A
git commit -m "feat(api): GET /api/v1/actions exposes action history (TDD)"
```

---

## Task 5 — TDD: GET /api/v1/slo

**Files:**
- Create: `backend/src/repopulse/api/slo.py`
- Modify: `backend/src/repopulse/main.py`
- Test: `backend/tests/test_slo_api.py`

Computes SLO state from the orchestrator's event log: total events, error events, availability ratio, and a burn-rate band. Reuses pure functions from `repopulse.slo`.

Response:

```json
{
  "service": "RepoPulse",
  "window_seconds": 3600,
  "total_events": 100,
  "error_events": 2,
  "availability": 0.98,
  "target": 0.99,
  "error_budget_remaining": -1.0,
  "burn_rate": 2.0,
  "burn_band": "fast" | "slow" | "ok"
}
```

- [ ] **Step 1–5: Standard TDD cycle.** Test fixtures: 100 events with 2 having `kind="error-log"` → availability 0.98 (below 0.99 target) → `burn_band == "fast"`. Empty orchestrator → all zeros, `burn_band == "ok"`.

- [ ] **Commit:**

```bash
git add -A
git commit -m "feat(api): GET /api/v1/slo computes service-level state from event log (TDD)"
```

---

## Task 6 — Frontend scaffold (Next.js + Tailwind + shadcn/ui)

**Files:**
- Create: `frontend/` directory (Next.js scaffold)
- Apply design tokens from the dashboard skill into `globals.css`

- [ ] **Step 1: Scaffold**

```bash
cd /c/Users/ibrah/Desktop/AIOPS
npx --yes create-next-app@latest frontend \
  --typescript --tailwind --app --eslint \
  --src-dir --import-alias "@/*" --no-turbopack
```

- [ ] **Step 2: Install shadcn/ui + extras**

```bash
cd frontend
npx --yes shadcn@latest init -d
npx --yes shadcn@latest add button card badge separator skeleton dialog table tabs tooltip
npm i lucide-react clsx tailwind-merge
npm i -D vitest @vitejs/plugin-react @testing-library/react @testing-library/dom jsdom @testing-library/jest-dom
```

- [ ] **Step 3: Apply design tokens (`src/app/globals.css`)**

```css
@import "tailwindcss";

:root {
  --color-bg:        #09090b;
  --color-bg-elev:   #111114;
  --color-fg:        #fafafa;
  --color-fg-muted:  #a1a1aa;
  --color-primary:   #0C5CAB;
  --color-primary-2: #0a4a8a;
  --color-success:   #10b981;
  --color-warning:   #f59e0b;
  --color-danger:    #ef4444;
  --color-border:    #1f1f23;
  --radius:          12px;
  --grid:            8px;
}

@theme inline {
  --font-sans: "IBM Plex Sans", system-ui, sans-serif;
  --color-background: var(--color-bg);
  --color-foreground: var(--color-fg);
  --color-card: var(--color-bg-elev);
  --color-border: var(--color-border);
  --color-primary: var(--color-primary);
}

html, body { background: var(--color-bg); color: var(--color-fg); }
*:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
```

- [ ] **Step 4: Configure IBM Plex Sans (`src/app/layout.tsx`)**

```tsx
import { IBM_Plex_Sans } from "next/font/google";

const ibm = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-sans",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${ibm.variable} dark`}>
      <body>{children}</body>
    </html>
  );
}
```

- [ ] **Step 5: vitest config (`vitest.config.ts`)**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.ts"],
    globals: true,
  },
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
});
```

- [ ] **Step 6: Smoke verify**

Run: `cd frontend && npm run dev` (in background); curl `http://localhost:3000` → 200; `npm run build` exit 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Next.js 15 + Tailwind 4 + shadcn/ui baseline with dashboard tokens"
```

---

## Task 7 — TDD: API client (`lib/api.ts`)

**Files:**
- Create: `frontend/src/lib/api.ts`
- Test: `frontend/src/tests/api.test.ts`

Typed wrapper over `fetch` with `BASE_URL` from `process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"`. Exports `getRecommendations`, `getIncidents`, `getActions`, `getSlo`, `approveRecommendation`, `rejectRecommendation`. Each returns a typed response, throws a typed `ApiError` on non-2xx.

- [ ] **Step 1: Write failing test (`api.test.ts`)**

```ts
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { getRecommendations, approveRecommendation, ApiError } from "@/lib/api";

beforeEach(() => { vi.spyOn(globalThis, "fetch"); });
afterEach(() => { vi.restoreAllMocks(); });

describe("api client", () => {
  it("getRecommendations parses the count + recs", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(new Response(
      JSON.stringify({ recommendations: [{ recommendation_id: "r1", state: "pending", action_category: "triage", confidence: 0.7, risk_level: "low", evidence_trace: [], incident_id: "i1" }], count: 1 }),
      { status: 200 }
    ));
    const r = await getRecommendations();
    expect(r.count).toBe(1);
    expect(r.recommendations[0].state).toBe("pending");
  });

  it("approveRecommendation posts the operator", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(new Response(
      JSON.stringify({ recommendation_id: "r1", state: "approved", actor: "alice" }),
      { status: 200 }
    ));
    const out = await approveRecommendation("r1", "alice");
    expect(out.state).toBe("approved");
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body as string)).toEqual({ operator: "alice" });
  });

  it("throws ApiError on 409", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: "cannot transition approved → approved" }),
      { status: 409 }
    ));
    await expect(approveRecommendation("r1", "alice")).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: Run RED.** **Step 3: Implement minimal `api.ts`.** **Step 4: GREEN.** **Step 5: Commit.**

```bash
git add -A
git commit -m "feat(frontend): typed API client with vitest coverage (TDD)"
```

---

## Task 8 — TDD: SLO board page

**Files:**
- Create: `frontend/src/components/slo/SloCard.tsx`
- Create: `frontend/src/components/slo/BurnRateBadge.tsx`
- Create: `frontend/src/app/page.tsx`
- Test: `frontend/src/tests/SloCard.test.tsx`

Layout: 3-column grid on `lg`, single column on `sm`. Cards: Availability, Error Budget, Burn Rate. Each card has number + comparison to target + trend indicator. Empty/loading skeletons; error state with retry.

- [ ] **Step 1: Write failing test (`SloCard.test.tsx`)**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SloCard } from "@/components/slo/SloCard";

describe("SloCard", () => {
  it("renders availability as a percentage with target comparison", () => {
    render(<SloCard label="Availability" value={0.985} target={0.99} kind="ratio" />);
    expect(screen.getByText("98.50%")).toBeInTheDocument();
    expect(screen.getByText(/target 99\.00%/i)).toBeInTheDocument();
  });

  it("marks below-target as warning", () => {
    render(<SloCard label="Availability" value={0.985} target={0.99} kind="ratio" />);
    expect(screen.getByRole("status")).toHaveAttribute("data-band", "warning");
  });

  it("renders an empty state when value is null", () => {
    render(<SloCard label="Availability" value={null} target={0.99} kind="ratio" />);
    expect(screen.getByText(/no data/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2–7: Standard cycle.** Tokens: success when `value >= target`, warning when `target - value < 0.01`, danger otherwise. Numbers render in IBM Plex Sans 32px tabular numerals.

```bash
git commit -m "feat(frontend): SLO board page with card + burn-rate badge (TDD)"
```

---

## Task 9 — TDD: Incidents timeline page

**Files:**
- Create: `frontend/src/components/incidents/Timeline.tsx`
- Create: `frontend/src/app/incidents/page.tsx`
- Test: `frontend/src/tests/Timeline.test.tsx`

Vertical timeline with each incident as a card: time range (relative + absolute), source badges, anomaly count, event count. Click → expand to show full details (sources tooltip, click-out closes). Empty state: "No incidents observed yet."

- [ ] **TDD cycle:** test renders 3 mock incidents, asserts timeline ordering (newest first), source badges visible, expand-on-click shows details. Commit when green.

```bash
git commit -m "feat(frontend): incidents timeline page (TDD)"
```

---

## Task 10 — TDD: Recommendations inbox + approval gate + runbook links

**Files:**
- Create: `frontend/src/components/recommendations/RecCard.tsx`
- Create: `frontend/src/components/recommendations/ApprovalActions.tsx` ("use client")
- Create: `frontend/src/components/recommendations/RunbookLink.tsx`
- Create: `frontend/src/lib/runbooks.ts`
- Create: `frontend/src/app/recommendations/page.tsx`
- Test: `frontend/src/tests/ApprovalActions.test.tsx`
- Test: `frontend/src/tests/runbooks.test.ts`

`ApprovalActions` is a client component that calls the API client's `approveRecommendation`/`rejectRecommendation` and optimistically transitions the local UI state. Reject opens a `Dialog` for the (optional) reason. Runbook links route to `/docs/runbooks/{action_category}.md` (via Next.js MDX or a static link to the GitHub-hosted markdown — choose the static GitHub link for M4 to avoid the MDX dep).

Per-rule UX:

- `state === "pending"` → green "Approve" + outline "Reject" buttons + "Open runbook" link
- `state === "approved" | "rejected" | "observed"` → state badge + actor + relative time, no buttons

`runbooks.ts`:

```ts
const BASE = "https://github.com/Ibrahim4594/OpsGraph-A/blob/main/docs/runbooks";
const MAP: Record<string, string> = {
  observe: `${BASE}/observe.md`,
  triage: `${BASE}/triage.md`,
  escalate: `${BASE}/escalate.md`,
  rollback: `${BASE}/rollback.md`,
};
export function runbookFor(actionCategory: string): string | null {
  return MAP[actionCategory] ?? null;
}
```

- [ ] **TDD cycle:** test approve-button click triggers `approveRecommendation` and transitions to `approved` state; reject-dialog requires confirmation; runbook URL maps correctly.

```bash
git commit -m "feat(frontend): recommendations inbox with approval gate + runbook links (TDD)"
```

---

## Task 11 — TDD: Action history page

**Files:**
- Create: `frontend/src/components/actions/HistoryRow.tsx`
- Create: `frontend/src/app/actions/page.tsx`
- Test: `frontend/src/tests/HistoryRow.test.tsx`

Single dense table: `at | kind | actor | summary | rec_id (link)`. Filterable by `kind` (chips at top: All / Approve / Reject / Observe / Workflow-run). Newest-first.

- [ ] **TDD cycle:** test rows render in correct order, kind filter narrows the list, recommendation_id is a link to `/recommendations#{id}`. Commit.

```bash
git commit -m "feat(frontend): action history page with kind filter (TDD)"
```

---

## Task 12 — Layout, navigation, theme, empty/loading/error states

**Files:**
- Create: `frontend/src/components/shell/Sidebar.tsx`, `StatusBar.tsx`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Sidebar:** sticky left nav with 4 links (lucide icons: `LayoutDashboard`, `History`, `Inbox`, `ListChecks`). Active route highlight uses `--color-primary` accent border-left + bg `rgba(12,92,171,0.08)`.

- [ ] **StatusBar:** top-right strip showing version (read from a backend `/healthz` call cached for 60 s) + agentic-enabled indicator (green dot or amber dot). 44px touch target.

- [ ] **Empty state component:** centered icon + heading + body, used by all 4 pages.

- [ ] **Loading skeletons:** shadcn `<Skeleton>` rectangles matching card dimensions.

- [ ] **Error state:** red-tinted card with retry button.

- [ ] **Commit:**

```bash
git commit -m "feat(frontend): shell, navigation, and empty/loading/error states"
```

---

## Task 13 — `docs/ui-design-system.md` finalize + runbooks

**Files:**
- Modify: `docs/ui-design-system.md`
- Create: `docs/runbooks/observe.md`, `triage.md`, `escalate.md`, `rollback.md`

`ui-design-system.md` documents:
- Why the `dashboard` skill from typeui.sh (rationale: dark cloud-platform aesthetic, IBM Plex, 8 pt grid, WCAG 2.2 AA — matches operator-tool genre).
- Token table (the actual CSS custom properties used in `globals.css`).
- Component checklist with state matrix (default/hover/focus-visible/active/disabled/loading/error).
- A11y requirements (testable: keyboard, focus, contrast).
- Anti-patterns (what NOT to do — e.g. bare hex values inside components).

Each runbook documents what the operator should consider when seeing that action_category, plus example commands or links.

- [ ] **Commit:**

```bash
git add docs/ui-design-system.md docs/runbooks/
git commit -m "docs(M4): finalized UI design system rationale + per-category runbooks"
```

---

## Task 14 — A11y + performance evidence

**Files:**
- Create: `docs/superpowers/plans/m4-evidence/lighthouse-*.json` and `screenshots/*.png`
- Create: `docs/superpowers/plans/m4-evidence/a11y-keyboard.md`

Process:

1. `npm run build && npm run start` → frontend at `:3000`, backend at `:8000`.
2. **Lighthouse via chrome-devtools-mcp:** capture mobile + desktop scores for each of the 4 pages. Save JSON. Goal: Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 90.
3. **Playwright keyboard-only walk-through:** tab through Sidebar → SLO card → recommendation Approve button → reject Dialog → confirm. Save screenshots after every focus change to verify visible focus ring.
4. **Contrast spot-checks:** primary on bg, fg-muted on bg, success/warning/danger on bg-elev — all ≥ 4.5:1 (AA normal text). Document with the actual ratios.
5. **Bundle size:** `npm run build` output → record First Load JS for `/`, `/recommendations`. Goal: each route under 200 KB First Load JS (Next.js + React + shadcn primitives ~150 KB baseline).

- [ ] **Commit:**

```bash
git add docs/superpowers/plans/m4-evidence/
git commit -m "docs(M4): a11y keyboard walkthrough + lighthouse + bundle evidence"
```

---

## Task 15 — Code review + handoff + tag

**Files:**
- Create: `docs/superpowers/plans/m4-evidence/code-review.md` (subagent report)
- Create: `docs/superpowers/plans/milestone-4-handoff.md`

Process:

1. **Verification (`superpowers:verification-before-completion`):** backend `pytest -v` exit 0, `ruff` 0, `mypy` 0; frontend `npm run typecheck`, `npm run lint`, `npm run test`, `npm run build` all 0. Capture exact output.
2. **Code review (`superpowers:requesting-code-review`):** dispatch `superpowers:code-reviewer` against `v0.4.0-m5..HEAD`. Save report.
3. **Receive review (`superpowers:receiving-code-review`):** verify each Critical and Important finding before fixing; push back where wrong; commit fixes with regression tests.
4. **Bump version:** `backend/pyproject.toml` and `__init__.py` to `0.5.0`. (Frontend `package.json` follows same version.)
5. **Write handoff:** Skills Invocation Log, Evidence Log, screenshots index, a11y report, performance numbers, risks (auth deferred), proposed M6 prompt.
6. **Tag:** `v0.5.0-m4` and push.

```bash
git tag v0.5.0-m4
git push origin main --tags
```

---

## Self-Review

**Spec coverage:**
- ✅ Operator dashboard pages — SLO board (T8), incidents timeline (T9), recommendations inbox (T10), action history (T11).
- ✅ Tailwind + shadcn/ui baseline (T6).
- ✅ 21st components consideration: deferred. shadcn primitives + the design-system skill cover M4's needs without adding `@21st/*` packages — documented in handoff §Risks ("21st components evaluated but not adopted; can be revisited if shadcn coverage proves insufficient").
- ✅ Human approval gate UX (T10) + action-policy visibility (T11 + StatusBar).
- ✅ Runbook linking (T10 + T13).
- ✅ `docs/ui-design-system.md` finalized (T13).
- ✅ Skills explicitly invoked + logged: `design-system` (Task 1 onward), `writing-plans` (T1), `test-driven-development` (T2–T11), `systematic-debugging` (any failure), `verification-before-completion` (T15), `requesting-code-review` (T15), `receiving-code-review` (T15), `frontend-design` (T6+ when crafting components), `playwright-cli` (T14).
- ✅ Anti-hallucination strict (every T15 claim → re-runnable command + captured artifact).
- ✅ M5 security constraints intact — no new GitHub secret surface; agentic kill switch only *visible* in UI, not flippable.
- ✅ M4 handoff with skills log, evidence log, screenshots, a11y, performance, risks, M6 next-prompt (T15).

**Placeholder scan:** none. All tasks have full code or full TDD-cycle prescriptions.

**Type consistency:** `Recommendation.state`, `ActionHistoryEntry`, `transition_recommendation`, `latest_actions`, `latest_incidents` are referenced consistently across tasks. API client types in T7 match the backend response shapes from T2–T5.

---

## Execution choice

Inline execution per `superpowers:executing-plans` — same author, same session, fastest iteration loop. Subagent-driven would add overhead without isolation benefits since the M4 work is mostly UI iteration that benefits from immediate visual feedback.

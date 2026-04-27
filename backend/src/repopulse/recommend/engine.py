"""Rule-based recommendation engine with explicit evidence trace.

R2–R4 are evaluated in priority order high → low; the highest-priority
firing rule sets ``action_category``, ``confidence``, and ``risk_level``.
R1 is the explicit fallback — it fires whenever none of R2–R4 fire — so
the evidence trace never reports a misleading "fired=False" line.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from repopulse.correlation.engine import Incident

ActionCategory = Literal["observe", "triage", "escalate", "rollback"]
RiskLevel = Literal["low", "medium", "high"]
State = Literal["pending", "approved", "rejected", "observed"]


@dataclass(frozen=True)
class Recommendation:
    recommendation_id: UUID
    incident_id: UUID
    action_category: ActionCategory
    confidence: float
    risk_level: RiskLevel
    evidence_trace: tuple[str, ...]
    state: State = "pending"


@dataclass(frozen=True)
class _RuleOutcome:
    rule_id: str
    fired: bool
    explanation: str
    category: ActionCategory
    confidence: float
    risk: RiskLevel


def _has_critical(incident: Incident) -> bool:
    if any(a.severity == "critical" for a in incident.anomalies):
        return True
    return any(e.severity == "critical" for e in incident.events)


def _r2(incident: Incident) -> _RuleOutcome:
    """Exactly 1 anomaly, no critical events → triage."""
    fired = (
        len(incident.anomalies) == 1
        and not _has_critical(incident)
    )
    return _RuleOutcome(
        rule_id="R2",
        fired=fired,
        explanation=(
            f"R2: 1 anomaly + 0 critical → triage "
            f"(anomalies={len(incident.anomalies)}, fired={fired})"
        ),
        category="triage",
        confidence=0.70,
        risk="low",
    )


def _r3(incident: Incident) -> _RuleOutcome:
    """≥2 anomalies OR any critical → escalate."""
    fired = len(incident.anomalies) >= 2 or _has_critical(incident)
    return _RuleOutcome(
        rule_id="R3",
        fired=fired,
        explanation=(
            f"R3: ≥2 anomalies OR ≥1 critical → escalate "
            f"(anomalies={len(incident.anomalies)}, "
            f"any_critical={_has_critical(incident)}, fired={fired})"
        ),
        category="escalate",
        confidence=0.85,
        risk="medium",
    )


def _r4(incident: Incident) -> _RuleOutcome:
    """Multi-source AND any critical → rollback."""
    fired = len(incident.sources) >= 2 and _has_critical(incident)
    return _RuleOutcome(
        rule_id="R4",
        fired=fired,
        explanation=(
            f"R4: multi-source ({len(incident.sources)}) AND ≥1 critical → rollback "
            f"(sources={list(incident.sources)}, fired={fired})"
        ),
        category="rollback",
        confidence=0.90,
        risk="high",
    )


# Priority order high-to-low for the actionable rules.
_PRIORITY_RULES = (_r4, _r3, _r2)


def _r1_fallback(incident: Incident) -> _RuleOutcome:
    """Synthesised explanation for the implicit fallback (R1)."""
    explanation = (
        f"R1: no higher-priority rule fired → observe "
        f"(anomalies={len(incident.anomalies)}, events={len(incident.events)}, "
        f"sources={list(incident.sources)}, fired=True)"
    )
    return _RuleOutcome(
        rule_id="R1",
        fired=True,
        explanation=explanation,
        category="observe",
        confidence=0.50,
        risk="low",
    )


def recommend(incident: Incident) -> Recommendation:
    higher_fired = [out for rule in _PRIORITY_RULES if (out := rule(incident)).fired]
    if higher_fired:
        primary = higher_fired[0]
        evidence: list[str] = [out.explanation for out in higher_fired]
    else:
        primary = _r1_fallback(incident)
        evidence = [primary.explanation]

    state: State = "observed" if primary.category == "observe" else "pending"
    return Recommendation(
        recommendation_id=uuid4(),
        incident_id=incident.incident_id,
        action_category=primary.category,
        confidence=primary.confidence,
        risk_level=primary.risk,
        evidence_trace=tuple(evidence),
        state=state,
    )

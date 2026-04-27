"""Rule-based recommendation engine with explicit evidence trace.

Rules are evaluated in priority order high → low. The highest-priority
firing rule sets ``action_category``, ``confidence``, and ``risk_level``;
every firing rule contributes a one-line entry to ``evidence_trace`` so
operators can audit the decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from repopulse.correlation.engine import Incident

ActionCategory = Literal["observe", "triage", "escalate", "rollback"]
RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Recommendation:
    recommendation_id: UUID
    incident_id: UUID
    action_category: ActionCategory
    confidence: float
    risk_level: RiskLevel
    evidence_trace: tuple[str, ...]


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


def _r1(incident: Incident) -> _RuleOutcome:
    """Empty incident → observe."""
    fired = not incident.anomalies and not incident.events
    return _RuleOutcome(
        rule_id="R1",
        fired=fired,
        explanation=f"R1: incident has 0 anomalies + 0 events → observe (fired={fired})",
        category="observe",
        confidence=0.50,
        risk="low",
    )


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


# Priority order: R4 > R3 > R2 > R1.
_RULES_HIGH_TO_LOW = (_r4, _r3, _r2, _r1)


def recommend(incident: Incident) -> Recommendation:
    outcomes = [rule(incident) for rule in _RULES_HIGH_TO_LOW]
    fired = [o for o in outcomes if o.fired]
    primary = fired[0] if fired else outcomes[-1]  # R1 is the fallback default

    evidence: list[str] = [o.explanation for o in fired] or [outcomes[-1].explanation]

    return Recommendation(
        recommendation_id=uuid4(),
        incident_id=incident.incident_id,
        action_category=primary.category,
        confidence=primary.confidence,
        risk_level=primary.risk,
        evidence_trace=tuple(evidence),
    )

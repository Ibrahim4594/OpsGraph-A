"""Rule-based GitHub issue triage classifier.

Mirrors the M3 recommendation engine pattern: deterministic rules,
priority-ordered, every firing rule contributes to ``evidence_trace``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from repopulse.github.payloads import IssuePayload

Severity = Literal["critical", "major", "minor"]
Category = Literal["feature-request", "docs", "uncategorized"]

_T1 = re.compile(r"\b(crash|outage|production|sev[\s-]?1)\b", re.IGNORECASE)
_T2 = re.compile(
    r"\b(error|exception|failure|broken|stack\s*trace)\b", re.IGNORECASE
)
_T3 = re.compile(r"\b(feature|enhancement|proposal|request)\b", re.IGNORECASE)
_T4 = re.compile(r"\b(docs?|documentation|typo|readme)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TriageRecommendation:
    issue_number: int
    severity: Severity
    category: Category
    suggested_labels: tuple[str, ...]
    confidence: float
    evidence_trace: tuple[str, ...] = field(default_factory=tuple)


def classify_issue(payload: IssuePayload) -> TriageRecommendation:
    text = f"{payload.issue.title}\n{payload.issue.body or ''}"

    severity: Severity = "minor"
    category: Category = "uncategorized"
    labels: list[str] = []
    trace: list[str] = []
    confidence = 0.4

    if _T1.search(text):
        severity = "critical"
        labels.extend(["severity:critical", "triage"])
        confidence = 0.9
        trace.append(
            f"T1: critical signal matched ({_T1.pattern}) → severity=critical"
        )
    elif _T2.search(text):
        severity = "major"
        labels.extend(["severity:major", "triage"])
        confidence = 0.75
        trace.append(
            f"T2: major signal matched ({_T2.pattern}) → severity=major"
        )

    if _T3.search(text):
        category = "feature-request"
        labels.append("type:feature")
        trace.append(
            f"T3: feature signal matched ({_T3.pattern}) → category=feature-request"
        )

    if _T4.search(text):
        category = "docs"
        labels.append("type:docs")
        trace.append(
            f"T4: docs signal matched ({_T4.pattern}) → category=docs"
        )

    if not trace:
        labels.append("triage")
        trace.append(
            "T5 fallback: no rule matched → severity=minor, category=uncategorized"
        )

    seen: set[str] = set()
    deduped: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            deduped.append(label)

    return TriageRecommendation(
        issue_number=payload.issue.number,
        severity=severity,
        category=category,
        suggested_labels=tuple(deduped),
        confidence=confidence,
        evidence_trace=tuple(trace),
    )

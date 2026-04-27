"""Tests for the GitHub issue triage classifier."""
from __future__ import annotations

from repopulse.github.payloads import IssuePayload
from repopulse.github.triage import TriageRecommendation, classify_issue


def _issue(
    title: str, body: str = "", labels: tuple[str, ...] = ()
) -> IssuePayload:
    return IssuePayload.model_validate(
        {
            "action": "opened",
            "issue": {
                "number": 1,
                "title": title,
                "body": body,
                "labels": [{"name": n} for n in labels],
                "user": {"login": "tester"},
            },
            "repository": {"full_name": "x/y"},
        }
    )


def test_classify_critical_outage() -> None:
    rec = classify_issue(_issue("Production outage — checkout broken"))
    assert isinstance(rec, TriageRecommendation)
    assert rec.severity == "critical"
    assert "severity:critical" in rec.suggested_labels
    assert any("T1" in line for line in rec.evidence_trace)
    assert rec.confidence == 0.9


def test_classify_major_on_stack_trace() -> None:
    rec = classify_issue(
        _issue("App throws NullPointerException", body="Stack trace below")
    )
    assert rec.severity == "major"
    assert "severity:major" in rec.suggested_labels
    assert any("T2" in line for line in rec.evidence_trace)
    assert rec.confidence == 0.75


def test_classify_feature_request_overlay() -> None:
    rec = classify_issue(
        _issue("Feature: dark mode", body="Proposal to add dark mode")
    )
    assert rec.category == "feature-request"
    assert "type:feature" in rec.suggested_labels


def test_classify_docs_overlay() -> None:
    rec = classify_issue(_issue("Typo in README", body="Fix typo"))
    assert rec.category == "docs"
    assert "type:docs" in rec.suggested_labels


def test_classify_fallback_when_no_rule_matches() -> None:
    rec = classify_issue(
        _issue("Question about config", body="How do I set X")
    )
    assert rec.severity == "minor"
    assert rec.category == "uncategorized"
    assert "triage" in rec.suggested_labels
    assert rec.confidence == 0.4
    assert any("T5 fallback" in line for line in rec.evidence_trace)


def test_classify_critical_overrides_major() -> None:
    rec = classify_issue(
        _issue("Production crash with stack trace exception")
    )
    assert rec.severity == "critical"
    # Should not contain major signal — T1 short-circuits T2.
    assert "severity:major" not in rec.suggested_labels


def test_classify_carries_issue_number() -> None:
    payload = IssuePayload.model_validate(
        {
            "action": "opened",
            "issue": {
                "number": 9999,
                "title": "x",
                "body": "x",
                "labels": [],
                "user": {"login": "u"},
            },
            "repository": {"full_name": "x/y"},
        }
    )
    rec = classify_issue(payload)
    assert rec.issue_number == 9999


def test_classify_dedupes_labels() -> None:
    rec = classify_issue(_issue("docs typo in feature proposal docs"))
    # T3 + T4 both fire; "type:feature" and "type:docs" each appear once.
    assert rec.suggested_labels.count("type:feature") == 1
    assert rec.suggested_labels.count("type:docs") == 1


# Post-review fixes (I1, I6) regression tests:


def test_classify_production_ready_is_not_critical() -> None:
    """Regression: 'production-ready logging' must NOT match T1.
    The benign phrase 'production-ready' was over-triggering critical
    severity in the initial M5 release.
    """
    rec = classify_issue(
        _issue("Add production-ready logging", body="for observability")
    )
    assert rec.severity != "critical"


def test_classify_production_outage_is_critical() -> None:
    rec = classify_issue(_issue("Production outage on payments"))
    assert rec.severity == "critical"


def test_classify_crash_word_stems_match() -> None:
    """Regression: T1 must match 'crashed', 'crashing', 'crashes'.
    The original ``\\bcrash\\b`` regex missed verb stems because
    word-boundaries don't fire between word characters.
    """
    for verb in ("crashed", "crashing", "crashes"):
        rec = classify_issue(_issue(f"App {verb} on startup"))
        assert rec.severity == "critical", f"failed for stem {verb!r}"


def test_classify_t3_t4_collision_t4_wins_category() -> None:
    """When T3 (feature) and T4 (docs) both match, T4 wins ``category``
    but both labels are emitted. This is documented in the module
    docstring; the test pins the precedence.
    """
    rec = classify_issue(_issue("Feature: docs proposal", body=""))
    assert rec.category == "docs"
    assert "type:feature" in rec.suggested_labels
    assert "type:docs" in rec.suggested_labels

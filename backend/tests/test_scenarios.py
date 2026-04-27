"""Scenario JSON loader contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from repopulse.scripts.scenarios import load_scenario


def test_load_scenario_parses_minimal_quiet(tmp_path: Path) -> None:
    payload = {
        "name": "quiet",
        "expected_action_category": "observe",
        "events": [
            {"offset_seconds": 0, "source": "github", "kind": "push", "payload": {}}
        ],
        "anomalies": [],
    }
    path = tmp_path / "quiet.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    scenario = load_scenario(path)
    assert scenario.name == "quiet"
    assert scenario.expected_action_category == "observe"
    assert len(scenario.events) == 1
    assert scenario.events[0].offset_seconds == 0


def test_load_scenario_parses_anomaly_block(tmp_path: Path) -> None:
    payload = {
        "name": "single-anomaly",
        "expected_action_category": "triage",
        "events": [
            {"offset_seconds": 0, "source": "github", "kind": "push", "payload": {}}
        ],
        "anomalies": [
            {
                "offset_seconds": 10,
                "value": 11.5,
                "baseline_median": 10.0,
                "baseline_mad": 1.0,
                "score": 5.06,
                "severity": "warning",
                "series_name": "otel-metrics",
            }
        ],
    }
    path = tmp_path / "x.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    scenario = load_scenario(path)
    assert len(scenario.anomalies) == 1
    assert scenario.anomalies[0].severity == "warning"
    assert scenario.anomalies[0].series_name == "otel-metrics"


def test_load_scenario_rejects_unknown_action_category(tmp_path: Path) -> None:
    payload = {
        "name": "bad",
        "expected_action_category": "explode",
        "events": [],
        "anomalies": [],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="expected_action_category"):
        load_scenario(path)


def test_load_scenario_loads_canonical_fixtures() -> None:
    """The four hand-authored scenarios under scenarios/ all parse."""
    fixtures_dir = Path(__file__).resolve().parents[2] / "scenarios"
    files = sorted(fixtures_dir.glob("*.json"))
    assert len(files) == 4, f"expected 4 fixtures, found {len(files)}"
    for path in files:
        scenario = load_scenario(path)
        assert scenario.name
        assert scenario.expected_action_category in {
            "observe",
            "triage",
            "escalate",
            "rollback",
        }

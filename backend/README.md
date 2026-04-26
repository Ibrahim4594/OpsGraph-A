# RepoPulse Backend

FastAPI service hosting the AIOps core (ingest, anomaly detection, correlation, recommendations). Milestone 1 ships the health endpoint and settings model only.

## Bring-up

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn repopulse.main:app --reload --port 8000
curl http://localhost:8000/healthz
```

## Quality Gates

```bash
ruff check src tests
mypy
pytest
```

All three must exit 0 in CI.

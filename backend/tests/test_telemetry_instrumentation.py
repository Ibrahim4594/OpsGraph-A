"""End-to-end check: FastAPI auto-instrumentation produces a span per request."""
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from repopulse.main import create_app


def test_healthz_request_emits_server_span() -> None:
    span_exporter = InMemorySpanExporter()
    app = create_app(span_exporter=span_exporter)

    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
        app.state.tracer_provider.force_flush()
        spans = span_exporter.get_finished_spans()

    assert len(spans) >= 1, "expected at least one span captured for GET /healthz"

    server_spans = [
        s
        for s in spans
        if s.attributes is not None and s.attributes.get("http.method") == "GET"
    ]
    assert server_spans, "expected an HTTP server span with http.method=GET"


def test_create_app_default_uses_console_exporter() -> None:
    """Default app construction must not require a span_exporter parameter."""
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200

"""Telemetry init module contract."""
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from repopulse import __version__
from repopulse.config import Settings
from repopulse.telemetry import init_telemetry


def test_init_telemetry_returns_providers() -> None:
    settings = Settings()
    tp, mp = init_telemetry(settings)
    assert isinstance(tp, TracerProvider)
    assert isinstance(mp, MeterProvider)


def test_init_telemetry_resource_attrs() -> None:
    settings = Settings()
    tp, _mp = init_telemetry(settings)
    attrs = tp.resource.attributes
    assert attrs["service.name"] == "repopulse-backend"
    assert attrs["service.version"] == __version__
    assert attrs["deployment.environment"] == settings.environment


def test_init_telemetry_resource_reflects_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REPOPULSE_ENVIRONMENT", "staging")
    settings = Settings()
    tp, _mp = init_telemetry(settings)
    assert tp.resource.attributes["deployment.environment"] == "staging"


def test_init_telemetry_with_in_memory_span_exporter_captures_spans() -> None:
    settings = Settings()
    span_exporter = InMemorySpanExporter()
    tp, _mp = init_telemetry(settings, span_exporter=span_exporter)
    tracer = tp.get_tracer("test")
    with tracer.start_as_current_span("unit-test-span"):
        pass
    tp.force_flush()
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "unit-test-span"


def test_init_telemetry_with_in_memory_metric_reader() -> None:
    settings = Settings()
    metric_reader = InMemoryMetricReader()
    _tp, mp = init_telemetry(settings, metric_reader=metric_reader)
    meter = mp.get_meter("test")
    counter = meter.create_counter("test_counter")
    counter.add(3)
    counter.add(2)
    metrics = metric_reader.get_metrics_data()
    assert metrics is not None
    rms = metrics.resource_metrics
    assert len(rms) >= 1


def test_init_telemetry_idempotent_does_not_raise() -> None:
    settings = Settings()
    tp1, mp1 = init_telemetry(settings)
    tp2, mp2 = init_telemetry(settings)
    assert isinstance(tp1, TracerProvider)
    assert isinstance(tp2, TracerProvider)
    assert isinstance(mp1, MeterProvider)
    assert isinstance(mp2, MeterProvider)

"""OpenTelemetry initialization for the RepoPulse backend.

`init_telemetry` builds and returns a `TracerProvider` and a `MeterProvider`
configured with a service-identifying `Resource`. Globals are intentionally
NOT modified — callers (for example the FastAPI lifespan) are responsible
for `trace.set_tracer_provider(...)` if they want auto-instrumentation to
pick up these providers. Keeping the function side-effect-free makes it
trivially testable with in-memory exporters.
"""
from __future__ import annotations

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from repopulse import __version__
from repopulse.config import Settings

SERVICE_NAME = "repopulse-backend"


def _build_resource(settings: Settings) -> Resource:
    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": __version__,
            "deployment.environment": settings.environment,
        }
    )


def init_telemetry(
    settings: Settings,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> tuple[TracerProvider, MeterProvider]:
    """Build and return ``(TracerProvider, MeterProvider)`` for the backend.

    - ``span_exporter`` defaults to ``ConsoleSpanExporter`` so the local-dev
      experience prints spans to stdout without extra setup. Tests should
      pass an ``InMemorySpanExporter``.
    - ``metric_reader`` defaults to a ``PeriodicExportingMetricReader`` over
      the console metric exporter (60 s interval). Tests should pass an
      ``InMemoryMetricReader``.
    - Span processor selection: ``SimpleSpanProcessor`` for in-memory
      exporters (so tests see spans synchronously), ``BatchSpanProcessor``
      for any other exporter (production-friendly batching).
    """
    resource = _build_resource(settings)

    if span_exporter is None:
        span_exporter = ConsoleSpanExporter()

    tracer_provider = TracerProvider(resource=resource)
    if isinstance(span_exporter, InMemorySpanExporter):
        tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    else:
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))

    if metric_reader is None:
        metric_reader = PeriodicExportingMetricReader(
            ConsoleMetricExporter(),
            export_interval_millis=60_000,
        )

    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    return tracer_provider, meter_provider
